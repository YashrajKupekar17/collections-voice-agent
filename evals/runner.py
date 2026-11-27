"""Runs one scenario: agent and simulated borrower talk until the call ends."""

import json
from datetime import date

from agent import guarded, naive
from compliance.output import blocked_note, sentences
from evals import simulator
from evals.backend import Backend

AGENTS = {"naive": naive, "guarded": guarded}
TODAY = "2026-11-25 (Wednesday)"
TODAY_DATE = date(2026, 11, 25)
MAX_TURNS = 20
MAX_TOOL_ROUNDS = 5


def build_account(defaults, scenario):
    account = {**defaults, **scenario.get("account", {})}
    account = {k: str(v) if isinstance(v, date) else v for k, v in account.items()}  # YAML parses dates
    if scenario.get("history"):
        account["history"] = scenario["history"]
    if scenario.get("jurisdiction"):
        account["jurisdiction"] = scenario["jurisdiction"]
    return account


def agent_step(client, agent, messages, backend, transcript):
    """One agent turn: call tools as needed, return what the agent says (may be empty)."""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=agent.MODEL, messages=messages, tools=agent.TOOLS,
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
        if backend.ended or backend.say_now:
            return msg.content or ""
    return ""


def guard_reply(said, backend, messages, transcript):
    """Checkpoint 5 in text mode: check each sentence before the borrower hears it.

    Sentences before a blocked one are spoken (in voice they have already gone to TTS); the blocked
    one is replaced by a safe line and the rest is dropped. The model's own message is rewritten to
    what was actually said, and a note tells it why.
    """
    spoken = []
    for sentence in sentences(said):
        broken = backend.check(sentence)
        if not broken:
            spoken.append(sentence)
            continue
        line = backend.block(sentence, broken)
        transcript.append({"blocked": sentence, "rules": broken})
        spoken.append(line)
        last = next(m for m in reversed(messages) if m["role"] == "assistant")
        last["content"] = " ".join(spoken)
        messages.append({"role": "system", "content": blocked_note(broken, line)})
        break
    return " ".join(spoken)


def run_scenario(client, scenario, defaults, agent=naive):
    account = build_account(defaults, scenario)
    backend = Backend(account, enforce=agent.ENFORCE, today=TODAY_DATE)
    direction = scenario.get("direction", "outbound")
    agent_msgs = [{"role": "system", "content": agent.system_prompt(account, TODAY, direction)}]
    sim_msgs = [{"role": "system", "content": simulator.system_prompt(scenario, account)}]
    transcript = []

    for turn in range(1, MAX_TURNS + 1):
        said = agent_step(client, agent, agent_msgs, backend, transcript)
        if said and agent.ENFORCE:
            said = guard_reply(said, backend, agent_msgs, transcript)
        if backend.say_now:
            said = f"{said} {backend.say_now}".strip()
            agent_msgs.append({"role": "assistant", "content": backend.say_now})
            backend.say_now = None
        if backend.closing:
            said = f"{said} {backend.closing}".strip()
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
        if agent.ENFORCE:
            for note in backend.hear(reply):
                transcript.append({"signal": note})
                agent_msgs.append({"role": "system", "content": note})

        if hung_up:
            agent_msgs.append({"role": "user", "content": "[The caller hung up. If they already confirmed a promise, record it; then call end_call with the outcome.]"})
            agent_step(client, agent, agent_msgs, backend, transcript)
            break

    return {
        "scenario": scenario["id"],
        "agent": agent.VERSION,
        "account": account,
        "turns": turn,
        "transcript": transcript,
        "state": backend.snapshot(),
    }
