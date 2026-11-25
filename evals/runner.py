"""Runs one scenario: agent and simulated borrower talk until the call ends."""

import json
from datetime import date

from agent import naive
from evals import simulator
from evals.backend import TOOLS, Backend

TODAY = "2026-11-25 (Wednesday)"
MAX_TURNS = 20
MAX_TOOL_ROUNDS = 5


def build_account(defaults, scenario):
    account = {**defaults, **scenario.get("account", {})}
    account = {k: str(v) if isinstance(v, date) else v for k, v in account.items()}  # YAML parses dates
    if scenario.get("history"):
        account["history"] = scenario["history"]
    return account


def agent_step(client, messages, backend, transcript):
    """One agent turn: call tools as needed, return what the agent says (may be empty)."""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=naive.MODEL, messages=messages, tools=TOOLS,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            return msg.content or ""
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result = backend.call(tc.function.name, args)
            transcript.append({"tool": tc.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
        if backend.ended:
            return msg.content or ""
    return ""


def run_scenario(client, scenario, defaults):
    account = build_account(defaults, scenario)
    backend = Backend(account)
    direction = scenario.get("direction", "outbound")
    agent_msgs = [{"role": "system", "content": naive.system_prompt(account, TODAY, direction)}]
    sim_msgs = [{"role": "system", "content": simulator.system_prompt(scenario, account)}]
    transcript = []

    for turn in range(1, MAX_TURNS + 1):
        said = agent_step(client, agent_msgs, backend, transcript)
        if said:
            transcript.append({"speaker": "agent", "text": said})
            sim_msgs.append({"role": "user", "content": said})
        if backend.ended:
            break

        reply = simulator.respond(client, sim_msgs)
        hung_up = simulator.HANGUP in reply
        reply = reply.replace(simulator.HANGUP, "").strip()
        transcript.append({"speaker": "borrower", "text": reply})
        sim_msgs.append({"role": "assistant", "content": reply})
        agent_msgs.append({"role": "user", "content": reply})

        if hung_up:
            agent_msgs.append({"role": "user", "content": "[The caller hung up. Call end_call with the outcome now.]"})
            agent_step(client, agent_msgs, backend, transcript)
            break

    return {
        "scenario": scenario["id"],
        "account": account,
        "turns": turn,
        "transcript": transcript,
        "state": backend.snapshot(),
    }
