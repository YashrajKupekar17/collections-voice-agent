-- Contact limits count per loan (Reg F counts per debt): attempts join to their case, the case to its loan.
CREATE INDEX attempt_by_case_time ON attempt (case_id, started_at);

-- Which checkpoint made each decision.
ALTER TABLE compliance.decision ADD COLUMN point text NOT NULL DEFAULT 'dial'
    CHECK (point IN ('dial', 'tool', 'output'));
ALTER TABLE compliance.decision ALTER COLUMN point DROP DEFAULT;
