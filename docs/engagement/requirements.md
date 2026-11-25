# Requirements (draft v0)

Numbers come from `estimates.md` unless stated. Targets marked (assumed) get confirmed in discovery.

## Users

- Borrower: gets reminders, makes promises, asks for help.
- Collections operations manager: runs campaigns, watches results, handles escalations.
- Compliance officer: needs proof that every call followed the rules.
- Human agent: takes over hard cases.

## Functional requirements

F1. Trigger: receive "payment failed" and "payment due soon" events from the loan system and schedule calls.
F2. Compliance gate: before every call, check calling window (8 AM–7 PM borrower local time), consent, contact limits and stop-contact flags. Block the call if any check fails.
F3. Outbound call: verify the borrower's identity before discussing the loan; give the AI-agent and recording disclosures.
F4. Context: load the account and the borrower's memory before the call; refer to earlier promises and stated situations.
F5. Promise to pay: capture amount, date and method as validated structured data; send a payment link by SMS/WhatsApp.
F6. Retries: if not reached, retry according to a configurable client policy (attempts, spacing, time of day, channel switch).
F7. Memory write: after each call, store a summary, outcome and extracted facts for future calls.
F8. Escalation: hand over to a human with a summary for hardship, disputes, distress, stop-contact requests and wrong-party calls.
F9. Follow-up: if a promised payment does not arrive by its date, schedule a follow-up call.
F10. Inbound: answer borrower calls 24/7, identify the borrower, continue from the current state.
F11. Operations dashboard: campaign progress, reach, promises, kept rate, escalations.
F12. Audit log: every compliance decision, disclosure and outcome recorded and queryable.

## Non-functional requirements

| ID | Quality | Target |
|---|---|---|
| N1 | Latency | Agent response after the borrower stops speaking: p50 ≤ 800 ms, p95 ≤ 1.2 s, measured caller-side (assumed; Twilio's published target is 1.1 s median mouth-to-ear) |
| N2 | Scale | 3.3 attempts/s peak, ~270 phone channels, ~200 concurrent AI sessions, plus inbound |
| N3 | Business SLA | First attempt for every failed-payment account within 24 h; all attempts within 48 h |
| N4 | Availability | Inbound line 99.9% per month (assumed). Outbound campaigns tolerate short outages if the 48 h SLA still holds |
| N5 | Correctness | Zero lost or duplicated promises or payment links, including under retries and crashes |
| N6 | Compliance | Zero calls outside the allowed window; 100% of calls give the required disclosures; every decision auditable |
| N7 | Safety | Zero threats, false statements or offers outside policy in the eval suite |
| N8 | Privacy | Personal data redacted in logs and traces; encrypted at rest; retention per client policy (DPDP) |
| N9 | Accuracy | Promise fields correct ≥ 98%; required escalations caught ≥ 95% (assumed) |
| N10 | Cost | ≤ ₹10 per conversation, all-in |
| N11 | Failure behaviour | If the compliance engine is unavailable, no calls are made (fail closed). If an AI provider is down, switch to a fallback or pause dialing; never leave a borrower in silence |
| N12 | Observability | Every turn traced with per-stage timings; every call linked to its audit record |
