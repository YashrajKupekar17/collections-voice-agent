"""Run the scenario suite against the agent and print a score report.

Usage:
    uv run python -m evals.run_evals --k 1                     (naive agent)
    uv run python -m evals.run_evals --k 3 --agent guarded
    uv run python -m evals.run_evals --k 3 --only third-party-wife-pushes,hardship-job-loss
"""

import argparse
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from evals import judge as judge_mod
from evals import simulator
from evals.checks import code_checks
from evals.runner import AGENTS, run_scenario

ROOT = Path(__file__).parent


def evaluate(client, scenario, defaults, agent):
    try:
        run = run_scenario(client, scenario, defaults, agent)
        checks = code_checks(scenario, run)
        judged, sim_broke = judge_mod.judge(client, scenario, run)
        checks += judged
    except Exception as e:  # a crashed run is a failed run, not a crashed suite
        return {"scenario": scenario["id"], "error": repr(e), "checks": [], "passed": False,
                "compliant": False, "simulator_broke": False, "held_out": scenario.get("held_out", False)}
    run["checks"] = checks
    run["passed"] = all(c["passed"] for c in checks)
    run["compliant"] = all(c["passed"] for c in checks if c["hard"])
    run["simulator_broke"] = sim_broke
    run["held_out"] = scenario.get("held_out", False)
    return run


def rate(values):
    values = list(values)
    return f"{sum(values)}/{len(values)} ({100 * sum(values) / len(values):.0f}%)" if values else "n/a"


def report(runs, scenarios):
    by_id = {s["id"]: s for s in scenarios}
    valid = [r for r in runs if not r["simulator_broke"]]
    errors = [r for r in runs if "error" in r]

    def check_passed(r, name):
        return any(c["name"] == name and c["passed"] for c in r["checks"])

    lines = []
    for split, held in (("main", False), ("held-out", True)):
        rs = [r for r in valid if r["held_out"] == held]
        groups = defaultdict(list)
        for r in rs:
            groups[r["scenario"]].append(r["passed"])
        lines.append(f"\n== {split} ({len(rs)} runs) ==")
        lines.append(f"task success      {rate(r['passed'] for r in rs)}")
        lines.append(f"compliance pass   {rate(r['compliant'] for r in rs)}")
        lines.append(f"pass^k            {rate(all(v) for v in groups.values())}")
        ptp = [r for r in rs if isinstance(by_id[r['scenario']]['expect'].get('promise'), dict)]
        lines.append(f"promise accuracy  {rate(check_passed(r, 'promise') for r in ptp)}")
        esc = [r for r in rs if "escalation" in by_id[r["scenario"]]["expect"]]
        lines.append(f"escalation recall {rate(check_passed(r, 'escalation') for r in esc)}")
        no_esc = [r for r in rs if "escalation" not in by_id[r["scenario"]]["expect"] and r["checks"]]
        lines.append(f"false escalations {rate(not check_passed(r, 'no_false_escalation') for r in no_esc)}")

    blocks = [len(r["state"]["blocks"]) for r in runs if "state" in r]
    rejected = [len(r["state"]["rejected"]) for r in runs if "state" in r]
    lines.append(f"\nsentences blocked by the output check: {sum(blocks)} in {sum(b > 0 for b in blocks)} runs")
    lines.append(f"tool calls refused by the tool check: {sum(rejected)} in {sum(r > 0 for r in rejected)} runs")
    lines.append(f"simulator broke character: {len(runs) - len(valid)} runs (excluded)")
    lines.append(f"crashed runs: {len(errors)}")

    lines.append("\n== per scenario ==")
    results = defaultdict(list)
    for r in runs:
        results[r["scenario"]].append(r)
    for sid, rs in results.items():
        passes = sum(r["passed"] for r in rs)
        failed = Counter(c["name"] for r in rs for c in r["checks"] if not c["passed"])
        if any("error" in r for r in rs):
            failed["crashed"] += 1
        tag = " (held-out)" if by_id[sid].get("held_out") else ""
        lines.append(f"{passes}/{len(rs)}  {sid}{tag}  {', '.join(failed) if failed else ''}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=1, help="runs per scenario")
    parser.add_argument("--only", default="", help="comma-separated scenario ids")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--agent", default="naive", choices=sorted(AGENTS))
    args = parser.parse_args()

    agent = AGENTS[args.agent]
    load_dotenv()
    client = OpenAI(max_retries=5, timeout=60)
    data = yaml.safe_load((ROOT / "scenarios.yaml").read_text())
    scenarios = data["scenarios"]
    if args.only:
        wanted = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]

    jobs = [s for s in scenarios for _ in range(args.k)]
    start = time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        runs = list(pool.map(lambda s: evaluate(client, s, data["default_account"], agent), jobs))

    text = report(runs, scenarios)
    print(text)
    print(f"\n{len(runs)} runs in {time.time() - start:.0f}s")

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{agent.VERSION}-k{args.k}.json"
    meta = {"agent": agent.VERSION, "agent_model": agent.MODEL, "simulator_model": simulator.MODEL,
            "judge_model": judge_mod.MODEL, "k": args.k}
    out.write_text(json.dumps({"meta": meta, "runs": runs}, indent=1, ensure_ascii=False, default=str))
    print(f"saved {out.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
