# Plan

4 weeks. One end-to-end flow working by the end of week 2, then deepen.

Every phase follows the same loop:

1. Problem and requirements for this component.
2. Design questions and options.
3. Prior art: how named production systems solve it (short targeted search).
4. Decide, write it in `DECISIONS.md`.
5. Build the smallest version that works.
6. Test: unit (mocks) + integration (real Postgres/Redis/Temporal in CI).
7. Measure. A phase is not done without a number.
8. Write up the result in `docs/results/`.

Exit criteria for every phase: runs on the real stack, tests pass in CI, its metric is recorded.

---

## Week 1: requirements, evals, architecture

### P0. Engagement and requirements (days 1–2)

Goal: know exactly what we are building and the numbers that size it.

Questions:
- Who is the client (size, products, India/US split) and who are the users (borrower, collections ops manager, compliance officer, human agent)?
- Which single business metric would they pay to move?
- Functional requirements for v1, and what is explicitly out of scope?
- Non-functional: latency SLO per turn, availability, compliance, data retention, cost per call ceiling.
- Estimates: accounts in delinquency, calls per day, peak calls per second, average call length. Concurrent calls by Little's Law (L = λ × W). Cost per call (telephony + STT + LLM + TTS).

Deliverables: `docs/engagement/brief.md`, `requirements.md`, `estimates.md`.
Measured: the estimates themselves, with assumptions stated.

### P1. Discovery and domain model (days 2–3)

Goal: the workflow, call types, compliance rules and data model.

Questions: What are the call types and their outcomes? Which conversations must stay human? What are the entities (account, borrower, contact, consent, interaction, promise-to-pay, case) and their states? Which rules apply where (TCPA/FCC 24-17, Reg F, FDCPA, RBI recovery directions, DPDP)?

Prior art: public collections workflows (Salient, Navana), CFPB Reg F text, RBI directions.
Deliverables: `docs/engagement/discovery.md` (workflow map, call taxonomy, compliance matrix, entity/state diagrams), interview requests sent to 2–3 practitioners.

### P2. Eval harness and naive baseline (days 3–5)

Goal: measure before building. A simulated borrower, a scenario suite, automatic checks, and baseline numbers from a deliberately simple agent.

Questions: What makes a call a success? Which checks are deterministic (disclosure said, promise fields valid) and which need an LLM judge (tone)? How do we keep the simulator consistent across runs? How do we validate the judge against human labels?

Prior art: tau-bench / tau-Voice, EVA-Bench, Sierra's simulation testing.
Build: text-mode first (cheap, fast), voice-mode later. Personas: cooperative, distressed, angry, disputing, wrong party, asks to stop calls.
Measured: baseline task success, compliance pass rate, promise extraction accuracy, judge agreement with human labels.
Status: done except judge agreement (labeling deferred; required before publishing numbers). Results: `docs/results/p2-baseline.md`.

### P3. Architecture (day 5)

Goal: the system design doc, driven by the P0 numbers.

Questions: Which parts are on the real-time path and which are async? Service boundaries: one process or several? Where does state live? What happens when each dependency is down?

Deliverables: `docs/engagement/design.md`, first `DECISIONS.md` entries (stack, voice framework, workflow engine, LLM selection method, deployment). Repo skeleton, CI with Postgres/Redis/Temporal service containers.
Status: done. No Redis (D-008); Temporal joins compose and CI in P7. Schema in `db/migrations/001_init.sql`.

---

## Week 2: core domain, first working flow

### P4. Voice skeleton and telephony

Goal: a phone number that connects to a streaming STT → LLM → TTS pipeline, with per-turn timing recorded from day one.
Questions: SIP trunk vs media streams? How do we detect answering machines on outbound calls? What do we measure per turn?
Measured: per-stage latency (STT final, LLM first token, TTS first byte), turn p50/p95.

### P5. Compliance engine

Goal: deterministic "may we call / say / offer this?" checks that the LLM cannot bypass. Every decision written to an audit log.
Questions: Rules in code or in data? Where is the check enforced (dialer, tool layer, both)? What does the system do when it cannot decide (fail closed)? How do we prove a call was compliant?
Prior art: Open Policy Agent, rules engines in lending, Reg F 7-in-7 implementations.
Measured: zero violations across the full scenario suite plus adversarial cases.

### P6. Data layer and idempotency

Goal: Postgres schema for accounts, consents, interactions, promises, cases. No duplicate promises or payment links under retries.
Questions: Idempotency key design? How do we publish events without dual-write bugs? What needs a transaction?
Prior art: Stripe idempotency keys, transactional outbox (Debezium).
Measured: duplicate rate under retry and crash tests (target 0).

### P7. Durable workflows

Goal: each account's journey (reminder → promise → payment check → follow-up) as a durable workflow with quiet hours, retries and scheduling.
Questions: Why not cron plus a queue? What survives a worker crash? How do we pace a campaign so we don't exceed concurrency or provider limits?
Prior art: Temporal (Uber Cadence lineage), Netflix Conductor, AWS Step Functions.
Measured: workflow completion under worker kills, campaign throughput.

Milestone: a real outbound reminder call ends with a validated promise-to-pay in Postgres and a scheduled follow-up.

---

## Week 3: intelligence

### P8. RAG
Goal: hardship and policy answers with citations, inside a retrieval budget.
Questions: Corpus size and update rate? Hybrid or vector-only? Reranker worth its latency? Retrieve on interim transcripts?
Prior art: VoiceAgentRAG, Stream RAG, production hybrid search (Elasticsearch/BM25 + vectors).
Measured: recall@k vs p95 latency curve, faithfulness, cited-clause accuracy.

### P9. Memory
Goal: what the agent knows about a borrower across calls, without growing the prompt.
Questions: What is worth remembering? Write path (when, sync or async)? Read path (pre-dial load)? Compaction within a call? How do we evaluate recall?
Prior art: Zep/Graphiti, Mem0, Letta, LangMem.
Measured: memory recall accuracy, tokens in prompt, LLM first-token time at turn 2 vs turn 30, ablation across 2–3 designs.

### P10. Latency
Goal: a measured latency budget and the optimizations that pay for themselves.
Questions: Where does time go today? Which optimizations are worth their cost (speculative retrieval, early generation, warm connections, smaller model)?
Measured: waterfall from baseline through each optimization at p50/p95, plus wasted-compute cost.

### P11. Guardrails and escalation
Goal: no threats, no false statements, no offers outside policy; warm transfer to a human with a summary.
Questions: Which guardrails are deterministic and which are model-based? What triggers escalation? What does the human receive?
Prior art: OpenAI agent guide escalation triggers, Sierra guardrails.
Measured: guardrail catch rate on adversarial scenarios, false escalation rate.

---

## Week 4: production and proof

### P12. Observability
Goal: trace every turn, measure caller-side latency, redact personal data, dashboards and SLOs.
Prior art: Pipecat/LiveKit OpenTelemetry tracing, OTel GenAI conventions.
Measured: SLO compliance, trace coverage, zero unredacted PII in traces (checked by test).

### P13. Load and chaos tests
Goal: know the limits. A 10k-account campaign at rising concurrency; kill workers, slow providers, take Postgres/Redis/Temporal down.
Measured: max concurrent calls at p95 SLO, error rates, what broke, what we fixed.

### P14. Release, results, handoff
Goal: versioned releases (code + prompts + model + knowledge base), a shadow-mode and canary rollout design, and the final package.
Deliverables: results report (honest numbers), runbooks, ROI estimate, demo video, write-up.

---

## Deferred after v1

Hinglish on 8 kHz phone audio, Indian phone numbers (KYC), multi-tenancy, durable voice sessions (crash recovery mid-call).

## Slip rule

If we fall behind, P13 and P14 move to week 5. Evals, compliance, memory and RAG are never cut.
