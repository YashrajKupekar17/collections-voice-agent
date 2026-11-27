"""Reads the compliance checks need, and the audit log they write."""

from psycopg.types.json import Jsonb

from compliance.rules import RULES_VERSION


def loan_attempts(conn, loan_id, since):
    """Attempts on this loan since a time, across all its cases (Reg F counts per debt)."""
    rows = conn.execute(
        "SELECT a.started_at, a.outcome FROM attempt a JOIN collection_case c ON c.id = a.case_id "
        "WHERE c.loan_id = %s AND a.started_at >= %s ORDER BY a.started_at",
        (loan_id, since)).fetchall()
    return [{"started_at": r[0], "outcome": r[1]} for r in rows]


def contact_rules(conn, borrower_id):
    rows = conn.execute("SELECT kind, value FROM compliance.contact_rule WHERE borrower_id = %s",
                        (borrower_id,)).fetchall()
    return [{"kind": r[0], "value": r[1]} for r in rows]


def record_decision(conn, point, inputs, broken, attempt_id=None):
    """Append one decision to the audit log. The caller commits, with the action it describes."""
    conn.execute(
        "INSERT INTO compliance.decision (attempt_id, point, rules_version, inputs, allowed, reasons) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (attempt_id, point, RULES_VERSION, Jsonb(inputs), not broken, Jsonb(broken)))
