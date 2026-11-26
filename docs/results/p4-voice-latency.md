# P4 result: voice latency

Server-side voice-to-voice latency: from the moment the user stops speaking to the first bot audio leaving the server. Measured by Pipecat's `UserBotLatencyObserver`; parts add up to the total. Browser call (WebRTC), turn detection by Silero VAD (200 ms stop) + Smart Turn v3.2, LLM `gpt-4.1-mini` with the naive agent.

## Run 1: OpenAI STT + OpenAI TTS (2026-11-26, 10 turns, 1 session)

| Stage | p50 ms | p95 ms |
|---|---|---|
| Speech synthesis (OpenAI TTS) | 968 | 1493 |
| LLM inference | 849 | 1855 |
| Turn detection (user turn strategies) | 794 | 2271 |
| Transcription (OpenAI realtime STT) | 691 | 902 |
| Endpointing wait (VAD stop_secs) | 200 | 200 |
| Sentence aggregation | 81 | 338 |
| LLM tool call (3 turns) | 216 | 394 |
| **Total** | **3799** | **6229** |

Greeting (connect to first audio): 3116 ms.

Every stage is over the budget, and the total is ~4.7x the 800 ms target. The call worked end to end: identity verified, promise recorded (₹5,000 on 30 Nov via link), call ended as PTP.

Open questions: why turn detection adds ~800 ms after the 200 ms VAD wait (p95 2.3 s); whether the LLM time includes a growing prompt.

## Run 2: Deepgram STT + Deepgram TTS (2026-11-26, 4 turns, 1 session)

| Stage | Run 1 p50 (OpenAI) | Run 2 p50 (Deepgram) | Run 2 p95 |
|---|---|---|---|
| Speech synthesis | 968 | **294** | 295 |
| Transcription | 691 | **200** | 259 |
| Turn detection | 794 | 1381 | 2843 |
| LLM inference | 849 | 1047 | 1791 |
| Endpointing wait | 200 | 200 | 200 |
| **Total** | **3799** | **3552** | **5434** |

Greeting: 1503 ms (first record of the session).

Only 4 turns, so p95 is not reliable yet.

What changed: TTS fell by 674 ms and transcription by 491 ms. The total barely moved, because two other stages dominate.

### Finding 1: turn detection is bimodal

Per turn, turn detection was either ~10–15 ms or ~2.7–2.9 s. The log shows why: when Smart Turn v3.2 judges the turn COMPLETE, the turn ends at once. When it judges INCOMPLETE, nothing ends the turn until its 3-second silence fallback (`End of Turn complete due to stop_secs. Silence in ms: 3000`). In this call Smart Turn returned INCOMPLETE on more than half its checks, including finished answers like a date of birth read out as digits. That matches public results that Smart Turn is weaker on Indian-accented speech (TamilEOT: ~70% zero-shot).

### Finding 2: every tool call costs a second LLM round trip

Turns with a tool call show two LLM inferences (~0.7 s each): one to decide the call, one to speak after the result. A single LLM inference is already 0.7–1.1 s.

### Measurement fix

The latency observer emits a "client_connected" record after a tool call when there is no fresh user silence to anchor on; that record spans the whole call so far (27.7 s here). The report now counts only the first such record per session as the greeting.

## Run 3: Deepgram, Smart Turn with a 1.2 s fallback, 2-word interruptions (2026-11-26, 9 turns, 2 sessions)

| Stage | Run 2 p50 (3 s fallback) | Run 3 p50 (1.2 s fallback) | Run 3 p95 |
|---|---|---|---|
| Turn detection | 1381 | **28** | 999 |
| LLM inference (per call) | 1047 | 880 | 1756 |
| Speech synthesis | 294 | 351 | 362 |
| Transcription | 200 | 304 | 354 |
| **Total** | **3552** | **2268** | **5493** |

Cut-ins (user spoke < 1 s after the bot started): 0 of 9 turns.

- The fallback now caps a missed end of turn at ~1 s instead of ~2.8 s. No cut-ins in this small sample, so the shorter wait did not visibly cut the user off.
- The LLM is now the largest cost. Turns with tool calls run two or three LLM inferences in a row (one turn: 3 inferences, 4.2 s total).
- One turn shows a 5.0 s "pipeline" gap with no service owning it. Not explained yet; to investigate.
- One session (1 turn) ran before the 2-word interruption fix, during the echo problem.

## Run 4: Deepgram Flux end-of-turn (2026-11-26, 3 turns, 1 session)

| Stage | p50 | p95 |
|---|---|---|
| Transcription incl. Flux end-of-turn decision | 654 | 680 |
| LLM inference (per call) | 1681 | 2215 |
| Speech synthesis | 283 | 292 |
| Turn detection (pipeline side) | 12 | 20 |
| **Total** | **2815** | **4069** |

Cut-ins: 0 of 3 turns. All Flux turn ends had `trigger='model'` (none hit the 1.5 s timeout).

Only 3 turns, so this run can't rank Flux against Smart Turn. With Flux, the end-of-turn wait shows up inside "transcription" (~650 ms) rather than as a separate turn-detection stage.

## Comparison so far

| Setup | Turns | Total p50 | Turn end cost p50 (VAD wait + STT tail + turn decision) | Cut-ins |
|---|---|---|---|---|
| OpenAI STT/TTS, Smart Turn 3 s | 10 | 3799 | ~1690 | not measured |
| Deepgram, Smart Turn 3 s | 4 | 3552 | ~1780 | not measured |
| Deepgram, Smart Turn 1.2 s | 9 | **2268** | ~530 (misses capped near 1.5 s) | 0 |
| Deepgram, Flux | 3 | 2815 | ~850 | 0 |

Decision for now: Smart Turn with a 1.2 s fallback is the default (best measured p50, bounded misses). Flux stays as an option. The samples are too small to settle it; the next comparison should use automated voice tests with many turns, not manual calls.

In every setup the LLM is now the largest cost (0.6–1.7 s per inference, two or three inferences on tool turns). That's the next thing to attack.

## Run 5: real phone call, Twilio US number → mobile in India (2026-11-26, 4 turns)

Deepgram STT/TTS, Smart Turn 1.2 s, 8 kHz phone audio over a cloudflared tunnel.

| Stage | p50 | p95 |
|---|---|---|
| LLM inference (per call) | 1454 | 2338 |
| Speech synthesis | 305 | 308 |
| Transcription | 206 | 274 |
| Endpointing wait | 200 | 200 |
| Turn detection | 12 | 36 |
| **Total (server side)** | **2433** | **3681** |

Cut-ins: 1 of 4 turns. Greeting: 2.0 s after the call connected.

What the phone call exposed:
- **Misheard digits on phone audio.** The first identity check sent DOB 1990-05-05 instead of 1992-05-05 and failed; the second try passed. This is the false-fail risk from D-004, now seen on real 8 kHz audio.
- **`end_call` didn't hang up.** The agent recorded PTP and called `end_call`, but the call stayed open. Later the agent called `end_call` again with the wrong code (ENDED_ABUSIVE for a polite goodbye). Fixed: `end_call` now ends the pipeline after the goodbye plays, with no further LLM turn.
- **Server-side numbers only.** These don't include the phone network in each direction (Twilio edge to India and back). Caller-side latency needs a recording of both sides; not measured yet.
