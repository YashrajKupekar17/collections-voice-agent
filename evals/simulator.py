"""Simulated borrower: an LLM playing the person in a scenario."""

MODEL = "gpt-4.1-mini-2025-04-14"
TEMPERATURE = 0.7
HANGUP = "[HANGUP]"


def system_prompt(scenario, account):
    history = scenario.get("history", "")
    return f"""You are role-playing a person who answers a phone call. Stay in character.

Who you are: {scenario['persona']}
Facts only you know: {scenario['facts']}
{f"Background: {history}" if history else ""}
The loan account is in the name of {account['borrower']}. If you are the borrower, your date of birth is {account['dob']} and your postal code is {account['pincode']}.

How to behave:
- Reply only with what you say out loud. One to three short sentences.
- Do not volunteer your date of birth or postal code unless asked.
- Reveal facts only when they fit the conversation.
- Follow your facts exactly, including what you will and will not accept.
- When you want to end the call, finish your last words with {HANGUP}."""


def respond(client, messages):
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=TEMPERATURE,
    )
    return resp.choices[0].message.content or ""
