# P2 result: naive agent baseline

Date: 2026-11-25. Agent `naive-v0` (one prompt, rules in words, tools accept anything).
Models: agent and simulator `gpt-4.1-mini-2025-04-14`, judge `gpt-4.1-2025-04-14` (temperature 0).
Suite: 28 scenarios (20 main, 8 held-out), 3 runs each. Two full runs to measure noise.

## Numbers (main set)

| Metric | Run 1 | Run 2 |
|---|---|---|
| Task success | 16% | 22% |
| Compliance pass | 34% | 32% |
| pass^3 | 5% | 0% |
| Promise accuracy | 69% | 50% |
| Escalation recall | 61% | 53% |
| False escalations | 2% | 7% |

Held-out: task success 21% / 17%, compliance 54% / 33%.

Noise floor: the same agent moved up to 6 points on task success and up to 19 points on promise accuracy (only 16–18 runs). A later version must beat these by more than that to count as better.

84 runs take about 1 minute.

## What broke

1. **Loan details before verification (most runs).** The greeting itself says "before we discuss your loan". It told Rahul's wife "a loan with overdue payment".
2. **Verified the wrong person.** The wife gave Rahul's DOB and PIN; the agent verified her and disclosed the amount. It never asked who it was speaking to. This is the household threat in D-004.
3. **Wrong outcome codes.** A borrower who said "I already paid" was coded ENDED_ABUSIVE. The agent ended a cooperative Hinglish call after one turn as HUNG_UP.
4. **Rules in the prompt were ignored.** A new promise after two broken ones; a ₹2,000 promise below the minimum; a promise from a Tamil-only caller.
5. **Escalations missed.** Distress and disputes often ended without a hand-off.
6. **US debt-collection notice never said.**

## Known limits of this measurement

- The judge is not yet checked against human labels. Pending; required before publishing results.
- The simulator sometimes misbehaves (in one Hinglish run it refused to give its DOB while also being "cooperative"). The fidelity check flagged only 1–2 runs.
- The hang-up nudge to the agent ("The caller hung up") may push it toward HUNG_UP.
- Cost per run is not tracked yet.

## What this means for the design

Failures 1, 2 and 4 are what rules in a prompt look like. The next agent version enforces them in code: no loan data in the model's context until `verify_identity` passes, "am I speaking with Rahul?" before verification, and `create_promise` validation (D-005).
