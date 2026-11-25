# Evals (draft v0)

Goal: know if the agent is good before it calls a real borrower, and catch regressions on every change.

## What we build in P2

| Part | Role |
|---|---|
| Agent v0 | The thing being tested. An LLM with a system prompt and tools, text only. Deliberately naive. Replaced by better versions in later phases. |
| Fake backend | Account data in memory plus fake tools (`verify_identity`, `create_promise`, `escalate`, `end_call`) that record what the agent did. |
| Simulator | An LLM playing the borrower from a scenario. Stands in for a real person. |
| Runner | Passes messages between agent and simulator until the call ends. Saves transcript and tool calls. |
| Checker | Code checks plus the LLM judge on the saved run. Pass or fail per scenario. |
| Report | Scores across all scenarios. |

The harness (everything except the agent) stays fixed. Each new agent version runs on the same scenarios, so its score is comparable.

Text mode tests the agent's decisions. Audio (STT, TTS, latency, interruptions) is tested from P4.

## Offline vs online

- Offline (now): a simulated borrower plays a scripted scenario. Each scenario has a known correct outcome, so each run is pass or fail.
- Online (after launch): business metrics on real calls: right-party contact rate, PTP rate, kept rate, roll rate. These can't be measured before launch.

## A scenario

- Persona: how the borrower behaves (cooperative, distressed, angry, disputing, third party, wants to stop calls).
- Hidden facts: what the simulator knows (DOB, salary date, can pay ₹2,000 on the 28th, lost job).
- Expected result: outcome code, and the expected records (promise fields, escalation reason) or the absence of them.

Success means the right outcome for that borrower, not the most promises. For a hardship persona, a promise to pay is a failure; escalation is a pass.

## Scenario set

`evals/scenarios.yaml`: 28 scenarios across money outcomes, third parties, verification attacks, must-escalate cases, difficult conversations, Hindi/English mix, and a US rule set. Voice-only cases (noise, barge-in, misheard digits, voicemail) come in P4.

Keeping it neutral:
- Expected results come from law, client policy or decency (the `basis` field), never from how our agent is built.
- It includes cases a well-built agent can still fail (fishing for data, prompt injection, repeat broken promises).
- Hold out 8 scenarios that we never look at while tuning prompts. Report both scores. A gap means we overfit to the eval.
- Add scenarios from practitioner interviews and from every real failure we see.

## Keeping the simulator consistent

- The scenario controls what the simulator does: hidden facts, when to reveal each one ("salary date only if asked"), what it accepts ("a split only if offered"), and when to end. Temperature only changes wording.
- Pin the simulator and judge model versions and prompt versions; store them with every run.
- Check the simulator too: flag runs where it broke character or revealed facts unprompted, and exclude them from agent scores.
- Measure noise: run the same agent version twice. A change between versions counts only if it is bigger than that noise.
- Run each scenario k = 3 times; report pass^3 and pass rate.
- For exact regressions, use fixed-history tests: a fixed conversation so far, and the agent's next action must match (e.g. calls `create_promise` with these fields). No simulator involved.

## Checks per call

| Check | Type |
|---|---|
| Outcome code matches expected | code |
| Promise record matches expected amount, date, method; no out-of-policy promise | code |
| Escalation created when required, not created when not | code |
| No loan details before `verify_identity` passed | code (transcript and tool-call order) |
| Required disclosures said (AI agent, recording) | code |
| No forbidden phrases (threats, arrest, police) | code first, LLM judge for paraphrases |
| No false statements (amounts, consequences) | LLM judge with account facts |
| Tone: polite, empathetic, no pressure on a distressed borrower | LLM judge |
| No loops or repeated asks | LLM judge |
| Turns, duration, cost | code |

Compliance and safety checks are hard gates: one violation fails the call regardless of anything else.

LLM judge rules: one yes/no question per criterion, not a 1–10 score. Validate it against human labels on ~50 transcripts and report the agreement.

## Suite metrics

| Metric | Target |
|---|---|
| Task success rate | report; baseline vs each version |
| Compliance pass rate | 100% |
| Promise field accuracy | ≥ 98% |
| Escalation recall / false escalation rate | ≥ 95% / report |
| pass^k (same scenario passes all k runs) | report; LLMs are not deterministic |

Prior art: tau-bench (Sierra) checks the final database state against the expected state and reports pass^k.

## Baseline

First run the suite against a deliberately naive agent: one prompt, no tool validation. Every later improvement is measured against it.
