"""Summarize per-stage latency from voice/results/latency.jsonl.

Usage: uv run python -m voice.latency_report [--stack deepgram|openai] [--turn smartturn|smartturn-short|flux] [--session ID]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).parent / "results" / "latency.jsonl"


def percentile(values, p):
    values = sorted(values)
    k = (len(values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="")
    parser.add_argument("--stack", default="")
    parser.add_argument("--turn", default="")
    args = parser.parse_args()

    rows = [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]
    for r in rows:
        r.setdefault("stack", "openai")  # the first baseline was recorded before stacks were logged
        r.setdefault("turn_mode", "smartturn")
    if args.session:
        rows = [r for r in rows if r["session"] == args.session]
    if args.stack:
        rows = [r for r in rows if r["stack"] == args.stack]
    if args.turn:
        rows = [r for r in rows if r["turn_mode"] == args.turn]
    cut_ins = [r for r in rows if r.get("kind") == "cut_in"]
    rows = [r for r in rows if r.get("kind") != "cut_in"]
    turns = [r for r in rows if r["measured_from"] == "user_silence"]
    # Only the first client_connected record per session is the greeting. Later ones appear after a
    # tool call (no new user silence to anchor on) and span the whole call so far, so they're dropped.
    greetings, seen = [], set()
    for r in rows:
        if r["measured_from"] == "client_connected" and r["session"] not in seen:
            greetings.append(r)
            seen.add(r["session"])
    if not turns:
        print("no user turns recorded yet")
        return

    stages = defaultdict(list)
    for t in turns:
        per_turn = defaultdict(float)
        for c in t["contributions"]:
            per_turn[f"{c['label']} [{c['owner']}]"] += c["secs"]
        for name, secs in per_turn.items():
            stages[name].append(secs)

    print(f"{len(turns)} turns from {len({t['session'] for t in turns})} sessions\n")
    print(f"{'stage':<60} {'p50 ms':>8} {'p95 ms':>8} {'n':>4}")
    for name, vals in sorted(stages.items(), key=lambda kv: -percentile(kv[1], 50)):
        print(f"{name:<60} {percentile(vals, 50) * 1000:>8.0f} {percentile(vals, 95) * 1000:>8.0f} {len(vals):>4}")
    totals = [t["total_secs"] for t in turns]
    print(f"{'TOTAL voice-to-voice (server side)':<60} {percentile(totals, 50) * 1000:>8.0f} "
          f"{percentile(totals, 95) * 1000:>8.0f} {len(totals):>4}")
    print(f"\ncut-ins (user spoke < 1 s after the bot started): {len(cut_ins)} in {len(turns)} turns "
          f"({100 * len(cut_ins) / len(turns):.0f}%)")
    if greetings:
        g = [r["total_secs"] for r in greetings]
        print(f"\ngreeting (connect to first audio): p50 {percentile(g, 50) * 1000:.0f} ms, n={len(g)}")


if __name__ == "__main__":
    main()
