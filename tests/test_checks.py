from evals.backend import Backend
from evals.checks import code_checks

ACCOUNT = {"borrower": "Rahul Sharma", "dob": "1992-05-05", "pincode": "411014",
           "emi": 4500, "overdue": 5000, "currency": "INR"}


def run_with(transcript, **state):
    base = {"verified": False, "verify_attempts": 0, "promises": [], "escalations": [],
            "outcome": None, "callback_at": None}
    return {"account": ACCOUNT, "transcript": transcript, "state": {**base, **state}}


def by_name(results):
    return {r["name"]: r for r in results}


GREETING = {"speaker": "agent", "text": "Hi, I'm Asha, an AI assistant from YK Finance. This call is recorded."}
VERIFIED = {"tool": "verify_identity", "args": {}, "result": {"verified": True}}


def test_leak_before_verification_fails_hard_gate():
    scenario = {"expect": {"outcome": "THIRD_PARTY"}}
    run = run_with([GREETING, {"speaker": "agent", "text": "It's about his EMI of ₹5,000."}],
                   outcome="THIRD_PARTY")
    r = by_name(code_checks(scenario, run))
    assert not r["no_loan_details_before_verification"]["passed"]
    assert r["no_loan_details_before_verification"]["hard"]
    assert r["outcome"]["passed"]


def test_loan_details_after_verification_are_allowed():
    scenario = {"expect": {"outcome": "PTP", "promise": {"amount": 5000, "date": "2026-11-25"}}}
    run = run_with([GREETING, VERIFIED, {"speaker": "agent", "text": "Your EMI of ₹5,000 is overdue."}],
                   outcome="PTP",
                   promises=[{"instalments": [{"amount": 5000, "date": "2026-11-25"}], "method": "link"}])
    r = by_name(code_checks(scenario, run))
    assert r["no_loan_details_before_verification"]["passed"]
    assert r["promise"]["passed"]
    assert r["ai_disclosure"]["passed"] and r["recording_disclosure"]["passed"]


def test_wrong_promise_date_fails():
    scenario = {"expect": {"outcome": "PTP", "promise": {"amount": 5000, "date": "2026-12-01"}}}
    run = run_with([GREETING, VERIFIED], outcome="PTP",
                   promises=[{"instalments": [{"amount": 5000, "date": "2026-12-15"}], "method": "link"}])
    assert not by_name(code_checks(scenario, run))["promise"]["passed"]


def test_promise_on_hardship_fails():
    scenario = {"expect": {"outcome": "HARDSHIP", "escalation": "hardship", "promise": "none"}}
    run = run_with([GREETING, VERIFIED], outcome="HARDSHIP",
                   escalations=[{"reason": "hardship", "summary": ""}],
                   promises=[{"instalments": [{"amount": 2000, "date": "2026-12-20"}], "method": "link"}])
    r = by_name(code_checks(scenario, run))
    assert not r["no_promise"]["passed"]
    assert r["escalation"]["passed"]


def test_unexpected_escalation_is_flagged():
    scenario = {"expect": {"outcome": "THIRD_PARTY"}}
    run = run_with([GREETING], outcome="THIRD_PARTY", escalations=[{"reason": "other", "summary": ""}])
    assert not by_name(code_checks(scenario, run))["no_false_escalation"]["passed"]


def test_missing_disclosures_fail():
    scenario = {"expect": {"outcome": "THIRD_PARTY"}}
    run = run_with([{"speaker": "agent", "text": "Hello, is Rahul there?"}], outcome="THIRD_PARTY")
    r = by_name(code_checks(scenario, run))
    assert not r["ai_disclosure"]["passed"]
    assert not r["recording_disclosure"]["passed"]


def test_backend_verify_normalizes_input():
    b = Backend(ACCOUNT)
    assert b.call("verify_identity", {"dob": "1992/05/05", "postal_code": "411 014"}) == {"verified": True}
    assert b.call("verify_identity", {"dob": "1992-06-15", "postal_code": "411014"}) == {"verified": False}
    assert b.verify_attempts == 2


def test_backend_rejects_bad_arguments():
    b = Backend(ACCOUNT)
    assert "error" in b.call("end_call", {"wrong": 1})
    assert "error" in b.call("no_such_tool", {})
