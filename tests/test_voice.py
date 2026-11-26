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
