-- Initial schema. Design: docs/engagement/discovery.md section 7, docs/engagement/design.md section 3.

-- Copies from the lender's loan system (the system of record), only for accounts with an open case.

CREATE TABLE borrower (
    id               bigserial PRIMARY KEY,
    lms_id           text UNIQUE NOT NULL,
    name             text NOT NULL,
    language         text NOT NULL DEFAULT 'hi',
    timezone         text NOT NULL,
    jurisdiction     text NOT NULL CHECK (jurisdiction IN ('IN', 'US')),
    dob_hash         text NOT NULL,          -- verification compares hashes, never raw values
    postal_code_hash text NOT NULL
);

CREATE TABLE loan (
    id             bigserial PRIMARY KEY,
    lms_id         text UNIQUE NOT NULL,
    borrower_id    bigint NOT NULL REFERENCES borrower(id),
    emi            numeric(12, 2) NOT NULL,
    overdue_amount numeric(12, 2) NOT NULL,
    dpd            int NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE payment (
    id          bigserial PRIMARY KEY,
    external_id text UNIQUE NOT NULL,        -- a re-delivered payment event is ignored
    loan_id     bigint NOT NULL REFERENCES loan(id),
    amount      numeric(12, 2) NOT NULL,
    posted_at   timestamptz NOT NULL
);

-- Ours: everything about contacting the borrower.

CREATE TABLE contact_point (
    id          bigserial PRIMARY KEY,
    borrower_id bigint NOT NULL REFERENCES borrower(id),
    phone       text NOT NULL,
    status      text NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'bad')),
    consent     boolean NOT NULL DEFAULT false,
    UNIQUE (borrower_id, phone)
);

CREATE TABLE collection_case (
    id        bigserial PRIMARY KEY,
    loan_id   bigint NOT NULL REFERENCES loan(id),
    state     text NOT NULL CHECK (state IN ('OPEN', 'CONTACTING', 'PROMISED', 'UNREACHABLE',
                                             'CURED', 'ROLLED', 'ESCALATED', 'DO_NOT_CONTACT')),
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz
);

-- At most one open case per loan.
CREATE UNIQUE INDEX one_open_case_per_loan ON collection_case (loan_id) WHERE closed_at IS NULL;

CREATE TABLE case_event (
    id         bigserial PRIMARY KEY,
    case_id    bigint NOT NULL REFERENCES collection_case(id),
    from_state text,
    to_state   text NOT NULL,
    event      text NOT NULL,
    at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE attempt (
    id               bigserial PRIMARY KEY,
    case_id          bigint NOT NULL REFERENCES collection_case(id),
    borrower_id      bigint NOT NULL REFERENCES borrower(id),   -- for counting contacts per borrower
    contact_point_id bigint REFERENCES contact_point(id),
    direction        text NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    status           text NOT NULL DEFAULT 'DIALING',           -- written before the dial request
    outcome          text,
    reasons          jsonb NOT NULL DEFAULT '[]',
    callback_at      timestamptz,
    recording_key    text,
    started_at       timestamptz NOT NULL DEFAULT now(),
    ended_at         timestamptz
);

-- "Calls this week" is counted from here, never stored.
CREATE INDEX attempt_by_borrower_time ON attempt (borrower_id, started_at);

CREATE TABLE promise (
    id              bigserial PRIMARY KEY,
    case_id         bigint NOT NULL REFERENCES collection_case(id),
    attempt_id      bigint REFERENCES attempt(id),
    idempotency_key text UNIQUE NOT NULL,    -- a retried create_promise cannot make a second promise
    instalments     jsonb NOT NULL,          -- [{"amount": 2500, "date": "2026-11-28"}, ...]
    method          text NOT NULL CHECK (method IN ('link', 'branch', 'auto_debit')),
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'kept', 'broken')),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE escalation (
    id         bigserial PRIMARY KEY,
    case_id    bigint NOT NULL REFERENCES collection_case(id),
    attempt_id bigint REFERENCES attempt(id),
    reason     text NOT NULL,
    summary    text NOT NULL,
    status     text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Side effects to run after the transaction that created them (SMS, payment links).
CREATE TABLE outbox (
    id              bigserial PRIMARY KEY,
    idempotency_key text UNIQUE NOT NULL,
    kind            text NOT NULL,
    payload         jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'dead')),
    tries           int NOT NULL DEFAULT 0,
    next_try_at     timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Compliance store (D-003): its own schema.

CREATE SCHEMA compliance;

CREATE TABLE compliance.contact_rule (
    id          bigserial PRIMARY KEY,
    borrower_id bigint NOT NULL REFERENCES borrower(id),
    kind        text NOT NULL CHECK (kind IN ('stop_contact', 'avoid_time', 'channel_only')),
    value       jsonb NOT NULL DEFAULT '{}',
    set_by      text NOT NULL,
    at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE compliance.decision (
    id            bigserial PRIMARY KEY,
    attempt_id    bigint REFERENCES attempt(id),
    rules_version text NOT NULL,
    inputs        jsonb NOT NULL,
    allowed       boolean NOT NULL,
    reasons       jsonb NOT NULL DEFAULT '[]',
    at            timestamptz NOT NULL DEFAULT now()
);

-- History tables are append-only: updates and deletes are rejected.

CREATE FUNCTION reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER case_event_append_only BEFORE UPDATE OR DELETE ON case_event
    FOR EACH ROW EXECUTE FUNCTION reject_change();

CREATE TRIGGER decision_append_only BEFORE UPDATE OR DELETE ON compliance.decision
    FOR EACH ROW EXECUTE FUNCTION reject_change();
