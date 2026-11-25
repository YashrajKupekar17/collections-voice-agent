# Decisions

One entry per decision. Newest at the bottom.

Format:

```
## D-NNN: title (date)
Chose:
Rejected:
Why:
Cost:
How we reduce the cost:
```

## D-001: Domain and workflow (2026-11-24)
Chose: loan servicing and collections for a consumer/auto lender in India and the US, framed as borrower-friendly servicing.
Rejected: healthcare payer calls (US-only market, demo limited to a simulator since we cannot legitimately call real payers), freight carrier sales (dominated by HappyRobot, no India demand), insurance FNOL and recruiting (no verified demand).
Why: verified buyers in both India (Navana, GreyLabs) and the US (Salient); compliance rules can be enforced in code; anyone can call a live demo number.
Cost: less technical depth than payer calls (no IVR navigation, no long holds); ethical risk if it reads as an aggressive collections bot.
How we reduce the cost: add depth through durable workflows, memory and compliance; later add Hinglish on phone audio; keep the framing and guardrails borrower-friendly.

## D-002: Client is an Indian lender; US is a second rule set (2026-11-24)
Chose: model one client, YK Finance, a mid-size Indian NBFC. Support US lenders through a second compliance rule set (TCPA consent, Reg F limits, FDCPA disclosures) loaded as configuration and tested in evals.
Rejected: one lender running collections in both India and the US.
Why: a single mid-size lender operating both markets is unrealistic, and a believable client makes the engagement credible.
Cost: no modelled US client, so the US story is weaker in demos.
How we reduce the cost: jurisdiction is configuration in the compliance engine; the eval suite runs both rule sets.

## D-003: Compliance engine fails closed; safety-critical state lives with it (2026-11-24)
Chose: if the compliance engine cannot decide, no call is made. Consent, stop-contact flags and contact counts are stored in the compliance engine's own store, not in agent memory.
Rejected: failing open to protect the 48-hour SLA.
Why: a wrong allow (calling outside hours, calling someone who asked us to stop) is illegal and cannot be undone. A wrong deny only delays a call, and the 48-hour window absorbs short delays.
Cost: a compliance-engine outage stops all outbound calling.
How we reduce the cost: keep the engine small and highly available; outbound work queues during outages and catches up; optional components (memory, RAG, telemetry) fail open so they never block calls.

## D-004: Identity verification on calls (2026-11-25)
Chose: registered phone number plus two spoken knowledge factors (DOB, PIN code, last 4 of loan number), checked by a code tool the LLM cannot see into; max 2 tries; OTP added for inbound calls; actions tiered by verification level.
Rejected: voice biometrics (cloned voices defeat it, needs enrollment); OTP on outbound calls (we already dialed the registered phone, so it repeats the possession factor); asking only for the loan number (most borrowers don't know it).
Why: matches common bank and collector practice, and keeps secrets out of the model's context.
Cost: a household member with the phone and the borrower's details can pass. STT errors on spoken numbers cause false failures.
How we reduce the cost: verified callers can only see the amount due and pay or promise, never change contact details; normalize spoken dates and numbers; measure false-fail rate in evals.

## D-005: Promise-to-pay rules enforced in a tool, not the prompt (2026-11-25)
Chose: `create_promise(amount, dates, method)` validates against client policy (amount limits, max 7 days, before 31 DPD, max 2 instalments) and is called only after the borrower confirms a read-back. Kept/broken decided by payment records plus a 2-day grace period.
Rejected: letting the prompt enforce policy (the model can be talked into "next month"); requiring a time of day (adds friction, payments post in batches anyway).
Why: a promise outside policy is a false commitment the lender can't honour or track. Collections platforms such as FICO Debt Manager store PTPs as structured records with amount, date, tolerance and kept/broken status.
Cost: strict rules turn some borrowers away; a rejected promise mid-call adds a turn.
How we reduce the cost: limits are client config; out-of-policy requests go to partial payment or hardship instead of a dead end; measure PTP rate and kept rate per rule change.

## D-006: US rule set follows FDCPA/Reg F even for lenders collecting their own loans (2026-11-25)
Chose: the US profile applies FDCPA and Reg F limits (7-in-7, conduct rules) plus TCPA, whether the client is a lender or a collection agency.
Rejected: applying only TCPA for original creditors.
Why: FDCPA covers third-party collectors, not lenders collecting their own debts, but state laws (e.g. California's Rosenthal Act) extend similar rules to lenders, and agencies are a large share of buyers. One stricter profile is simpler and safe for both.
Cost: fewer attempts allowed than some lenders would use.
How we reduce the cost: frequency limits are config; a lender-only profile can relax them after legal review.

## D-007: Simulator consistency through scripts, pinning and repeated runs (2026-11-25)
Chose: scripted scenarios (hidden facts, reveal and accept rules), pinned model and prompt versions, simulator fidelity checks, k = 3 runs per scenario, a measured noise floor, and fixed-history tests for exact regressions. Judge at temperature 0; simulator at a moderate temperature for varied wording.
Rejected: relying on temperature 0 for reproducibility.
Why: temperature 0 is not deterministic in practice (GPU batching and floating-point order, per Thinking Machines' 2025 analysis; provider model updates), and even a deterministic simulator diverges as soon as the agent's reply changes. Real borrowers also vary, so some variety is wanted.
Cost: 3x eval runs; fidelity checks add judge calls.
How we reduce the cost: text mode with a cheap model for the simulator; run the full k = 3 suite only before merges, a single pass during development.

## D-008: Three process types from one codebase; compliance as a library; no Redis in v1 (2026-11-25)
Chose: voice workers, workflow workers and an API, built from one codebase and image. Compliance runs in-process as a library over its own Postgres schema. Postgres and Temporal are the only stateful infrastructure.
Rejected: one process for everything (a voice CPU spike or crash would stall workflows and webhooks; inbound and outbound load could not scale separately); a microservice per domain (compliance, promises, memory) — network hops on the hot path and more failure points for a one-person team; Redis for now.
Why: the three parts scale on different signals (concurrent calls, backlog, requests) and must fail independently. OPA is commonly embedded as a library or sidecar for the same latency reason.
Cost: a bug in the shared library ships to all three processes; Postgres is a single dependency for compliance.
How we reduce the cost: one test suite and CI for the whole codebase; managed Postgres with failover in production; compliance fails closed when Postgres is unreachable.

## D-009: Pipecat as the voice framework (2026-11-25)
Chose: Pipecat (open-source Python) for the voice worker.
Rejected: LiveKit Agents (strong, with built-in worker dispatch, but needs a LiveKit server as one more stateful piece of infrastructure, or LiveKit Cloud); writing our own pipeline (interruptions, voice activity detection and turn-taking are the hard parts and would take most of the 4 weeks).
Why: the team already knows it, which matters in a 4-week plan; its pipeline of processors lets us insert our own steps (compliance checks, timing) between STT, LLM and TTS; it ships telephony integrations (Twilio, Plivo and others) and OpenTelemetry tracing.
Cost: no built-in dispatch of calls to workers (Pipecat Cloud sells that).
How we reduce the cost: a simple dispatch path (the telephony provider connects each call's audio to a voice worker behind a load balancer); most of the value is in the system around the framework, so the framework stays replaceable.

## D-010: Cascaded voice pipeline, not speech-to-speech (2026-11-25)
Chose: STT → LLM → TTS with text in the middle.
Rejected: a speech-to-speech model (e.g. OpenAI's realtime models) that takes audio in and returns audio.
Why: we need to check every reply before it is spoken (compliance, disclosures before verification), enforce tool rules in code, keep exact transcripts for audit, and measure each stage. Speech-to-speech hides the text and the stages.
Cost: higher latency (three stages, each with network time) and less natural prosody.
How we reduce the cost: streaming at every stage (partial transcripts, streamed tokens, streamed audio), warm connections, pre-synthesized fixed phrases; measured in P10.

## D-011: Demo telephony on Twilio with a US number; production India path documented (2026-11-25)
Chose: Twilio with a US number for the demo (calls to and from the developer's verified phone), plus a browser call option so anyone can try it free. The voice worker uses Pipecat's telephony serializers, so the provider is swappable.
Rejected: Indian numbers for the demo. Twilio allows outbound calls to India only from non-Indian numbers; Indian providers (Exotel, Plivo) need business KYC; RBI-regulated lenders must make service calls from 1600-series numbers (TRAI).
Why: an individual developer cannot get a compliant Indian number, and the demo must be callable.
Cost: the demo does not show India-specific telephony (Indian caller ID, 1600 series, local latency).
How we reduce the cost: document the production path (Exotel or Plivo with a 1600-series number); keep the dial call behind one small function.

## D-012: Models are provisional; chosen by evals and latency measurements (2026-11-25)
Chose: Deepgram (STT), gpt-4.1-mini (LLM), Cartesia (TTS) as starting points, with OpenAI STT/TTS and a second LLM provider as backups. Final choices come from the eval suite plus P4 latency numbers: the cheapest option that meets the quality and latency targets.
Rejected: picking by reputation or benchmarks published by vendors; reasoning models on the live turn (they think before the first token, adding latency).
Why: model choice is a cost/quality/latency trade-off that only our own measurements can settle.
Cost: two extra vendor accounts; re-running evals per candidate.
How we reduce the cost: free tiers for Deepgram and Cartesia; text-mode evals cost cents per run.

## D-013: Run locally with Docker Compose; one VM in a Mumbai region when hosting (2026-11-25)
Update (same day): no VM yet. Everything runs locally in Docker Compose until we host the demo.
Chose: a single VM (~$25–50/month) running Postgres, Temporal, the three app processes and Caddy (HTTPS, needed for telephony webhooks and audio streams). Local development uses a tunnel to expose the laptop.
Rejected: Kubernetes or a managed container platform for v1.
Why: fits the budget and the timeline; the design (stateless processes, separate process types) already allows scaling out later.
Cost: no autoscaling and a single point of failure; claims about 200 concurrent sessions are extrapolated from a one-worker load test.
How we reduce the cost: say so plainly in the results; document what a multi-node deployment would change.
