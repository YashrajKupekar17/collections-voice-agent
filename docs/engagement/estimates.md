# Estimates

All numbers are for the fictional client, YK Finance. Assumptions are marked.

## Step 1: accounts to call

| Input | Value |
|---|---|
| Active loans | 800,000 (assumed) |
| Payments that fail each month | 15% (assumed) |
| Contact goal | within 48 hours of the failure |
| Collection dates | 5th and 20th, half the loans each (assumed) |

| Result | Value |
|---|---|
| Failed payments per month | 120,000 |
| Failed per collection date | 60,000 |
| Accounts to call per day on a peak day (60,000 in 48 h) | 30,000 |
| Average if failures were spread over 30 days | 4,000 per day (about 8,000 waiting at any time with a 48 h window) |
| Peak to average | 7.5x |

Decision: size capacity for the peak (30,000 accounts per day). Cost follows the average, so capacity should scale with load, not stay fixed at peak.

## Step 2: attempts and reach

| Input | Value |
|---|---|
| Chance an attempt reaches the right person | 30% (assumed; industry average right-party contact is ~26%) |
| Max attempts per account in the 48 h window | 3 (assumed) |

| Attempt | Called | Reached | Not reached |
|---|---|---|---|
| 1 | 60,000 | 18,000 | 42,000 |
| 2 | 42,000 | 12,600 | 29,400 |
| 3 | 29,400 | 8,820 | 20,580 |
| Total | 131,400 attempts | 39,420 (65.7%) | 20,580 (34.3%) |

- About 3.3 attempts per conversation. Most attempts are short (ringing, no answer).
- Unreached accounts follow a client-defined policy (retry later at other times, switch to SMS/WhatsApp, respect contact limits, hand to humans). The retry policy must be configurable. Open question for discovery.

## Step 3: call rate

Calling window 8 AM–7 PM (RBI) = 11 hours a day, 2 days = 22 hours for one collection date.

| | Per day | Per hour | Per second |
|---|---|---|---|
| Average | 65,700 | ~6,000 | ~1.7 |
| Peak hour (2x average, assumed) | | ~12,000 | ~3.3 |

- Size for the peak hour: 3.3 attempts per second.
- Outbound load is controllable: our dialer sets the pace. We concentrate calls in hours when people answer, which is a trade-off between reach and capacity.
- Inbound callbacks are not controllable and add on top.

## Step 4: concurrency (Little's Law, L = λ × W)

| Attempt type | Share | Rate at peak (λ) | Duration (W, assumed) | In progress at once (L) |
|---|---|---|---|---|
| Answered | 30% | 0.99/s | 150 s | ~149 |
| Not answered | 70% | 2.31/s | 25 s | ~58 |
| All | | 3.3/s | 62.5 s (weighted) | ~206 |

- Phone channels are held by every attempt: ~206 at peak.
- The AI pipeline (STT, LLM, TTS) is needed only after someone answers: ~149 at peak. Start the pipeline on answer, not on dial.
- Little's Law gives the average during the peak hour; real load fluctuates above it. Add 20–30% headroom.
- Working targets: ~270 phone channels, ~200 concurrent AI sessions, plus inbound.

## Step 5: cost per call

Planning prices (assumed, to be replaced with real vendor quotes): telephony ₹0.60 per connected minute, unanswered attempts free; AI pipeline (STT + LLM + TTS) ₹3.00 per minute. Conversation length 2.5 min.

| | Value |
|---|---|
| Cost per minute | ₹3.60 |
| Cost per conversation | ₹9.00 |
| Per collection date (39,420 conversations) | ₹3.55 lakh |
| Per month (2 dates) | ₹7.1 lakh |
| Human caller per talk minute (assumed ₹25–35k/month, 90–120 talk min/day [VoxTurn via Tribune India]) | ₹10–18 |

- Not included: servers, SMS/WhatsApp, human escalations, billed unanswered attempts.
- The client's real unit is cost per kept promise, not cost per contact.
- The AI pipeline is 83% of the per-minute cost. Levers: pre-synthesized audio for fixed phrases (greeting, disclosures), small prompts via memory compaction, smaller models where evals allow, self-hosting STT/TTS at high volume. Call length multiplies everything.

## Summary (one collection date, peak)

| | Value |
|---|---|
| Accounts | 60,000 in 48 h |
| Attempts | 131,400 |
| Borrowers reached | 39,420 (65.7%) |
| Peak attempt rate | 3.3/s |
| Concurrent phone channels | ~270 with headroom |
| Concurrent AI sessions | ~200 with headroom |
| Cost per conversation | ~₹9 |
