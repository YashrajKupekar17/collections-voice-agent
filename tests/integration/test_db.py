"""Integration tests against a real Postgres (docker compose up -d, or the CI service)."""

import json

import psycopg
import pytest

from db.migrate import database_url, migrate


@pytest.fixture
def conn():
    with psycopg.connect(database_url()) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("DROP SCHEMA IF EXISTS compliance CASCADE")
        c.execute("CREATE SCHEMA public")
        c.commit()
        migrate(c)
        yield c


def make_case(conn):
    b = conn.execute("INSERT INTO borrower (lms_id, name, timezone, jurisdiction, dob_hash, postal_code_hash) "
                     "VALUES ('B1', 'Rahul Sharma', 'Asia/Kolkata', 'IN', 'h1', 'h2') RETURNING id").fetchone()[0]
    loan = conn.execute("INSERT INTO loan (lms_id, borrower_id, emi, overdue_amount, dpd) "
                        "VALUES ('L1', %s, 4500, 5000, 3) RETURNING id", (b,)).fetchone()[0]
    case = conn.execute("INSERT INTO collection_case (loan_id, state) VALUES (%s, 'CONTACTING') RETURNING id",
                        (loan,)).fetchone()[0]
    conn.commit()
    return b, loan, case


def test_migrate_is_idempotent(conn):
    assert migrate(conn) == []


def test_duplicate_promise_key_is_rejected(conn):
    _, _, case = make_case(conn)
    insert = ("INSERT INTO promise (case_id, idempotency_key, instalments, method) "
              "VALUES (%s, 'call-8812-promise', %s, 'link')")
    conn.execute(insert, (case, json.dumps([{"amount": 5000, "date": "2026-11-28"}])))
    conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (case, json.dumps([{"amount": 5000, "date": "2026-11-28"}])))
    conn.rollback()
    assert conn.execute("SELECT count(*) FROM promise").fetchone()[0] == 1


def test_redelivered_payment_is_ignored(conn):
    _, loan, _ = make_case(conn)
    insert = ("INSERT INTO payment (external_id, loan_id, amount, posted_at) "
              "VALUES ('UPI-123', %s, 5000, now()) ON CONFLICT (external_id) DO NOTHING")
    conn.execute(insert, (loan,))
    conn.execute(insert, (loan,))
    assert conn.execute("SELECT count(*) FROM payment").fetchone()[0] == 1


def test_only_one_open_case_per_loan(conn):
    _, loan, _ = make_case(conn)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO collection_case (loan_id, state) VALUES (%s, 'OPEN')", (loan,))
    conn.rollback()


def test_case_history_is_append_only(conn):
    _, _, case = make_case(conn)
    conn.execute("INSERT INTO case_event (case_id, from_state, to_state, event) "
                 "VALUES (%s, 'OPEN', 'CONTACTING', 'first_attempt')", (case,))
    conn.commit()
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE case_event SET to_state = 'CURED'")
    conn.rollback()
