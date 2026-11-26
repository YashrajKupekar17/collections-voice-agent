"""Voice bot: a browser call with the agent, logging per-stage latency on every turn.

Run:  uv run python -m voice.bot                    (Deepgram STT + TTS)
      VOICE_STACK=openai uv run python -m voice.bot  (OpenAI STT + TTS, the first baseline)

Turn detection (TURN_MODE):
      smartturn-short  Silero VAD + Smart Turn v3, 1.2 s fallback (default)
      smartturn        same, 3 s fallback (Pipecat's default)
      flux             Deepgram Flux decides end of turn (Deepgram stack only)
Then open http://localhost:7860 and click Connect.

Latency per turn is printed and appended to voice/results/latency.jsonl.
Summarize with: uv run python -m voice.latency_report
"""

import json
import os
import time
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import BotStartedSpeakingFrame, LLMRunFrame, VADUserStartedSpeakingFrame
from pipecat.observers.base_observer import BaseObserver
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAIRealtimeSTTService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_start.min_words_user_turn_start_strategy import MinWordsUserTurnStartStrategy
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import MergeMode, UserTurnStrategies, UserTurnStrategiesParams

from agent import naive
from evals.backend import TOOLS, Backend
from evals.runner import TODAY, build_account

load_dotenv()

ROOT = Path(__file__).parent
RESULTS = ROOT / "results" / "latency.jsonl"
SCENARIOS = ROOT.parent / "evals" / "scenarios.yaml"
STACK = os.environ.get("VOICE_STACK", "deepgram")
TURN_MODE = os.environ.get("TURN_MODE", "smartturn-short")
CUT_IN_SECS = 1.0  # user speaks this soon after the bot starts: the bot probably answered too early
MIN_INTERRUPT_WORDS = 2  # echo of the bot's own voice trips VAD but rarely produces two transcribed words
FLUX_EOT_THRESHOLD = 0.7
FLUX_EOT_TIMEOUT_MS = 1500


def demo_account():
    defaults = yaml.safe_load(SCENARIOS.read_text())["default_account"]
    return build_account(defaults, {})


def tool_schemas():
    schemas = []
    for tool in TOOLS:
        fn = tool["function"]
        params = fn["parameters"]
        schemas.append(FunctionSchema(name=fn["name"], description=fn["description"],
                                      properties=params["properties"], required=params["required"]))
    return schemas


def speech_services(stack, turn_mode):
    """STT and TTS for the chosen stack. The LLM stays the same, so stacks compare fairly."""
    if turn_mode == "flux":
        if stack != "deepgram":
            raise ValueError("TURN_MODE=flux needs VOICE_STACK=deepgram")
        key = os.environ["DEEPGRAM_API_KEY"]
        stt = DeepgramFluxSTTService(api_key=key, settings=DeepgramFluxSTTService.Settings(
            eot_threshold=FLUX_EOT_THRESHOLD, eot_timeout_ms=FLUX_EOT_TIMEOUT_MS))
        return stt, DeepgramTTSService(api_key=key)
    if stack == "openai":
        key = os.environ["OPENAI_API_KEY"]
        return OpenAIRealtimeSTTService(api_key=key), OpenAITTSService(api_key=key)
    if stack == "deepgram":
        key = os.environ["DEEPGRAM_API_KEY"]
        return DeepgramSTTService(api_key=key), DeepgramTTSService(api_key=key)
    raise ValueError(f"unknown VOICE_STACK {stack!r}")


def turn_strategies(turn_mode):
    """Returns (strategies, params) for the user aggregator.

    A turn starts (and interrupts the bot) only once the user has said MIN_INTERRUPT_WORDS words
    while the bot is talking, so the bot doesn't cut itself off when its own audio echoes back.
    """
    start = [MinWordsUserTurnStartStrategy(min_words=MIN_INTERRUPT_WORDS)]
    if turn_mode == "flux":
        # Keep the stop strategy Flux recommends (it decides end of turn).
        return UserTurnStrategies(start=start), UserTurnStrategiesParams(stop_merge_mode=MergeMode.EXTEND)
    stop_secs = {"smartturn": 3.0, "smartturn-short": 1.2}.get(turn_mode)
    if stop_secs is None:
        raise ValueError(f"unknown TURN_MODE {turn_mode!r}")
    analyzer = LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=stop_secs))
    stop = [TurnAnalyzerUserTurnStopStrategy(turn_analyzer=analyzer)]
    return UserTurnStrategies(start=start, stop=stop), UserTurnStrategiesParams()


class CutInObserver(BaseObserver):
    """Calls on_cut_in when the user starts speaking within CUT_IN_SECS of the bot starting."""

    def __init__(self, on_cut_in):
        super().__init__(observe_every_push=False)
        self._on_cut_in = on_cut_in
        self._bot_started = None

    async def on_push_frame(self, data):
        if isinstance(data.frame, BotStartedSpeakingFrame):
            self._bot_started = time.time()
        elif isinstance(data.frame, VADUserStartedSpeakingFrame) and self._bot_started:
            gap = time.time() - self._bot_started
            self._bot_started = None
            if gap < CUT_IN_SECS:
                await self._on_cut_in(gap)


def append_result(record):
    RESULTS.parent.mkdir(exist_ok=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def save_latency(session, breakdown):
    record = {
        "session": session,
        "stack": STACK,
        "turn_mode": TURN_MODE,
        "at": time.time(),
        "measured_from": breakdown.measured_from,
        "total_secs": breakdown.total_secs,
        "contributions": [{"label": c.label, "owner": c.owner, "secs": c.duration_secs}
                          for c in breakdown.contributions],
        "ttfb": [t.model_dump() for t in breakdown.ttfb],
    }
    append_result(record)


async def bot(runner_args: RunnerArguments):
    session = uuid.uuid4().hex[:8]
    api_key = os.environ["OPENAI_API_KEY"]
    account = demo_account()
    backend = Backend(account)

    transport = await create_transport(runner_args, {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    })

    stt, tts = speech_services(STACK, TURN_MODE)
    llm = OpenAILLMService(api_key=api_key, settings=OpenAILLMService.Settings(model=naive.MODEL))
    logger.info(f"session {session}: stack={STACK}, turn_mode={TURN_MODE}, llm={naive.MODEL}")

    async def run_tool(params):
        result = backend.call(params.function_name, dict(params.arguments))
        logger.info(f"tool {params.function_name}({dict(params.arguments)}) -> {result}")
        await params.result_callback(result)

    for tool in TOOLS:
        llm.register_function(tool["function"]["name"], run_tool)

    context = LLMContext(
        messages=[{"role": "system", "content": naive.system_prompt(account, TODAY)}],
        tools=tool_schemas(),
    )
    strategies, strategy_params = turn_strategies(TURN_MODE)
    aggregators = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(), user_turn_strategies=strategies,
        user_turn_strategies_params=strategy_params))

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_breakdown")
    async def on_breakdown(observer, breakdown):
        logger.info(f"latency ({breakdown.measured_from}):")
        for line in breakdown.turn_contribution_lines():
            logger.info(f"  {line}")
        save_latency(session, breakdown)

    async def on_cut_in(gap):
        logger.warning(f"cut-in: user spoke {gap:.2f}s after the bot started")
        append_result({"kind": "cut_in", "session": session, "stack": STACK,
                       "turn_mode": TURN_MODE, "at": time.time(), "gap_secs": gap})

    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[latency, CutInObserver(on_cut_in)],
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        await task.queue_frames([LLMRunFrame()])  # the agent speaks first

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info(f"session {session} ended, state: {backend.snapshot()}")
        await task.cancel()

    await PipelineRunner(handle_sigint=runner_args.handle_sigint).run(task)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
