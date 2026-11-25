# Problem statement (draft v0)

Status: draft for review. The client is fictional. Numbers marked [src] come from public data or vendor sources; numbers marked [assumed] are ours and must be checked in discovery.

## Client

YK Finance (fictional), a mid-size Indian NBFC.

- Products: two-wheeler loans and small personal loans.
- ~800,000 active loans [assumed]. Average EMI ₹4,500 [assumed].
- EMIs are collected by NACH auto-debit. Most Indian lenders collect EMIs this way [src: IIFL].
- In-house telecalling team of ~200 agents on a predictive/progressive dialer, plus field agents for late stages [assumed].

## The problem

Every month a large share of NACH debits bounce. Historically 28–35% of all NACH debits (every purpose, including retries) bounced by volume, 2021–2023 [src: Business Standard, NPCI data 2022]. Insufficient balance is the main cause [src: IIFL]. For YK Finance we assume ~15% of EMIs bounce each month: about 120,000 accounts entering 1–30 days past due (DPD) [assumed].

Most of these borrowers will pay if reached early. Industry guides put the 1–30 DPD cure rate at 70–85% [src: unsourced guide]. The rest roll into 31–60 DPD, where recovery costs more, the borrower's credit score is hit, and field visits start.

The team cannot reach everyone early enough:

1. Contact capacity. Right-party contact on dialers is ~26% of attempts on average [src: MaxContact 2024], so each account needs several attempts. Agents reach many accounts only after 10–15 days, when the chance of cure has already fallen.
2. Cost. Human callers get only 90–120 minutes of real talk time a day [src: VoxTurn via Tribune India], about ₹10–18 per talk minute at an assumed ₹25–35k monthly cost [assumed]. (An earlier ₹38–62 per contact figure was removed: its source could not be found.)
3. Inconsistent compliance. RBI rules allow recovery calls only from 8 AM to 7 PM and forbid abusive or excessive calls. New directions take effect 1 Jan 2027 [src: RBI via Exotel]. Human agents break these rules occasionally, and every breach is a regulatory and reputational risk.
4. No memory across contacts. A borrower who explained a job loss to one agent has to explain it again to the next. Promises to pay are tracked in free-text notes.
5. Missed inbound calls. Borrowers who call back after 7 PM or on Sundays reach no one.

## Why a voice agent

Pre-due reminders and early-bucket (1–30 DPD) calls are high volume, short and mostly routine: confirm identity, remind, take a promise to pay, send a payment link. Vendors focus voice bots on these early buckets and keep humans for late-stage defaults [src: productgrowth.in on Spocto; Credgenics]. Salient reports the same split in US auto lending [src: Salient].

## Goal

Reach every borrower in early delinquency within 48 hours of a bounce, compliantly, and turn more of them into kept payments, so fewer accounts roll into 31–60 DPD.

## Scope for v1

In:
- Outbound pre-due reminders (3 days before the EMI date).
- Outbound early-bucket calls (1–30 DPD): verify the borrower, give the required disclosures, remind, take a promise to pay (amount, date, method), send a payment link.
- Inbound callbacks at any hour: recognise the borrower and continue from where things stood.
- Hardship intake: record the situation, check policy, create a case for a human. The agent never approves restructuring itself.
- Safe handling of: wrong person answering, disputes, requests to stop calling, distress. All of these go to a human.
- Broken-promise follow-up when a promised payment does not arrive.

Out:
- Late-stage collections (31+ DPD), settlements, field visits.
- Taking card or bank details on the call. Payment happens through a secure link.
- Languages other than Hindi and English in v1.

## Success metrics

Primary: roll rate from 1–30 DPD to 31–60 DPD.

Supporting:
- Share of bounced accounts contacted within 48 hours.
- Right-party contact rate, promise-to-pay rate, promise kept rate.
- Cost per right-party contact.
- Compliance violations: target zero.
- Borrower complaints per 10,000 calls.
- Escalation rate to humans, and time to human pickup.

Baselines and targets are set in discovery.

## Constraints

- RBI recovery directions (8 AM–7 PM, no harassment, identity disclosure), DPDP Act (consent, purpose limitation, retention).
- Calls are recorded; borrowers must be told the call is recorded and that they are speaking with an AI agent.
- No real borrower data in this project. We use a synthetic loan book.

## US variant

YK Finance is an Indian lender. To show the system also works for US lenders, the compliance engine takes the jurisdiction as configuration and ships a second rule set (TCPA consent, Reg F call limits, FDCPA disclosures), tested in the eval suite. No US client is modelled in v1.

## Open questions for discovery

- What are the real right-party contact, promise-to-pay and kept rates in the early bucket?
- How many attempts per account, over how many days, before an account rolls?
- Which conversations must always go to a human?
- How are consent and the recording notice captured today?
- What systems would the agent read from and write to (loan management system, dialer, payment gateway)?
- What would make the client switch the agent off?
