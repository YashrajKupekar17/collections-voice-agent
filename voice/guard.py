"""Checkpoint 5 on a live call: check each sentence of the LLM's reply before TTS speaks it.

Sits between the LLM and TTS. TTS already waits for a full sentence before synthesizing,
so checking per sentence adds no extra wait.
"""

import re

from loguru import logger
from pipecat.frames.frames import (
    EndWorkerFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from compliance.output import blocked_note, sentences

COMPLETE = re.compile(r"^(.*[.!?])\s+(.*)$", re.S)  # everything up to the last sentence end, and the rest


def split_complete(buffer):
    """Returns (complete sentences, unfinished tail). A sentence is complete once whitespace follows its end."""
    m = COMPLETE.match(buffer)
    return (m.group(1), m.group(2)) if m else ("", buffer)


class InputGuard(FrameProcessor):
    """Checkpoint 3 on a live call: sits after STT and adds a note to the context when the caller
    says something the agent must act on (distress, stop calling)."""

    def __init__(self, backend, context):
        super().__init__()
        self._backend = backend
        self._context = context

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            for note in self._backend.hear(frame.text):
                logger.warning(f"caller signal: {note[:60]}")
                self._context.add_message({"role": "system", "content": note})
        await self.push_frame(frame, direction)


class ReplyGuard(FrameProcessor):
    """After a blocked sentence the rest of that reply is dropped and the safe line is spoken instead."""

    def __init__(self, backend, context):
        super().__init__()
        self._backend = backend
        self._context = context
        self._buffer = ""
        self._dropping = False

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, (InterruptionFrame, LLMFullResponseStartFrame)):
            self._buffer, self._dropping = "", False
        elif isinstance(frame, LLMTextFrame):
            if not self._dropping:
                self._buffer += frame.text
                done, self._buffer = split_complete(self._buffer)
                if done:
                    await self._check(done)
            return
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._buffer.strip() and not self._dropping:
                await self._check(self._buffer)
            self._buffer = ""
        await self.push_frame(frame, direction)

    async def _check(self, text):
        for sentence in sentences(text):
            broken = self._backend.check(sentence)
            if not broken:
                await self.push_frame(LLMTextFrame(sentence + " "))
                continue
            self._dropping = True
            logger.warning(f"blocked before speaking {broken}: {sentence!r}")
            line = self._backend.block(sentence, broken)
            self._context.add_message({"role": "system", "content": blocked_note(broken, line)})
            await self.push_frame(LLMTextFrame(line))
            if self._backend.ended:
                await self.push_frame(EndWorkerFrame())
            return
