import pytest

from voice.bot import MIN_INTERRUPT_WORDS, turn_strategies
from voice.latency_report import percentile


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 95) == 5


@pytest.mark.parametrize("mode,stop_secs", [("smartturn", 3.0), ("smartturn-short", 1.2)])
def test_smart_turn_modes_set_fallback(mode, stop_secs):
    strategies, _ = turn_strategies(mode)
    assert strategies.start[0]._min_words == MIN_INTERRUPT_WORDS
    assert strategies.stop[0]._turn_analyzer.params.stop_secs == stop_secs


def test_flux_mode_keeps_flux_stop_strategy():
    _, params = turn_strategies("flux")
    assert params.stop_merge_mode.value == "extend"


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        turn_strategies("nope")


# --- Reply guard (checkpoint 5 on a live call) ---

import asyncio

from pipecat.frames.frames import EndWorkerFrame, LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests.utils import run_test

from evals.backend import Backend
from voice.guard import ReplyGuard, split_complete

GUARD_ACCOUNT = {"borrower": "Rahul Sharma", "dob": "1992-05-05", "pincode": "411014",
                 "loan_number": "YK2W118842", "emi": 4500, "overdue": 5000, "min_partial": 4500, "dpd": 3}


def spoken_by(guard, tokens):
    frames = [LLMFullResponseStartFrame(), *[LLMTextFrame(t) for t in tokens], LLMFullResponseEndFrame()]
    down, _ = asyncio.run(run_test(guard, frames_to_send=frames))
    return "".join(f.text for f in down if isinstance(f, LLMTextFrame)), down


def test_split_complete_waits_for_whitespace_after_the_sentence_end():
    assert split_complete("Hi Rahul. How are") == ("Hi Rahul.", "How are")
    assert split_complete("Hi Rahul.") == ("", "Hi Rahul.")


def test_guard_passes_safe_replies_through():
    guard = ReplyGuard(Backend(dict(GUARD_ACCOUNT), enforce=True), LLMContext())
    text, _ = spoken_by(guard, ["Hi, this is", " Asha from YK Finance.", " Am I speaking with Rahul?"])
    assert text.strip() == "Hi, this is Asha from YK Finance. Am I speaking with Rahul?"


def test_guard_replaces_a_leak_streamed_in_tokens():
    backend = Backend(dict(GUARD_ACCOUNT), enforce=True)
    context = LLMContext()
    guard = ReplyGuard(backend, context)
    text, _ = spoken_by(guard, ["Thanks.", " Your over", "due is 5,", "000.", " Please pay", " today."])
    assert "5,000" not in text and "pay today" not in text
    assert text.startswith("Thanks. Before I share any account details")
    assert backend.blocks[0]["rules"] == ["loan_detail_unverified"]
    assert "loan_detail_unverified" in context.get_messages()[-1]["content"]


def test_guard_ends_the_call_when_the_same_rule_is_blocked_twice():
    backend = Backend(dict(GUARD_ACCOUNT), enforce=True)
    backend.block("Your overdue is 5000.", ["loan_detail_unverified"])
    text, down = spoken_by(ReplyGuard(backend, LLMContext()), ["You owe 4500 rupees."])
    assert "colleague" in text and backend.ended
    assert any(isinstance(f, EndWorkerFrame) for f in down)


def test_input_guard_adds_a_note_when_the_caller_shows_distress():
    from pipecat.frames.frames import TranscriptionFrame

    from voice.guard import InputGuard

    backend = Backend(dict(GUARD_ACCOUNT), enforce=True)
    context = LLMContext()
    frame = TranscriptionFrame("I don't want to live anymore", user_id="u", timestamp="0")
    asyncio.run(run_test(InputGuard(backend, context), frames_to_send=[frame]))
    assert backend.signals == ["distress"]
    assert "DISTRESS" in context.get_messages()[-1]["content"]
