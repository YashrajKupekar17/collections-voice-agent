from agent import guarded, naive
from evals.backend import Backend
from evals.runner import guard_reply

ACCOUNT = {"borrower": "Rahul Sharma", "dob": "1992-05-05", "pincode": "411014", "loan_number": "YK2W118842",
           "emi": 4500, "overdue": 5000, "min_partial": 4500, "dpd": 3, "currency": "INR",
           "jurisdiction": "IN"}
GOOD_ID = {"dob": "1992-05-05", "postal_code": "411014", "speaking_with_borrower": True}
PROMISE = {"instalments": [{"amount": 5000, "date": "2026-11-26"}], "method": "link"}


def test_guarded_prompt_has_no_loan_details():
    prompt = guarded.system_prompt(ACCOUNT, "2026-11-25")
    for secret in ["5000", "4500", "YK2W118842", "1992", "411014"]:
        assert secret not in prompt
    assert "5000" in naive.system_prompt(ACCOUNT, "2026-11-25")  # the baseline it is measured against


def test_account_details_arrive_only_with_verification():
    b = Backend(dict(ACCOUNT), enforce=True)
    assert b.call("verify_identity", {**GOOD_ID, "dob": "1990-01-01"}) == {"verified": False, "attempts_left": 1}
    result = b.call("verify_identity", GOOD_ID)
    assert result["verified"] and result["account"]["overdue"] == 5000


def test_relative_with_the_right_dob_is_not_verified():
    b = Backend(dict(ACCOUNT), enforce=True)
    result = b.call("verify_identity", {**GOOD_ID, "speaking_with_borrower": False})
    assert result["verified"] is False and "account" not in result


def test_third_verification_attempt_is_refused():
    b = Backend(dict(ACCOUNT), enforce=True)
    bad = {**GOOD_ID, "dob": "1990-01-01"}
    b.call("verify_identity", bad)
    b.call("verify_identity", bad)
    assert b.call("verify_identity", GOOD_ID)["status"] == "rejected"
    assert not b.verified


def test_us_borrower_gets_the_debt_notice_step():
    b = Backend({**ACCOUNT, "jurisdiction": "US", "pincode": "30309"}, enforce=True)
    assert "attempt to collect a debt" in b.call("verify_identity", {**GOOD_ID, "postal_code": "30309"})["next"]


def test_promise_before_verification_is_refused_and_not_recorded():
    b = Backend(dict(ACCOUNT), enforce=True)
    result = b.call("create_promise", PROMISE)
    assert result["status"] == "rejected" and result["rules"] == ["not_verified"]
    assert b.promises == [] and b.rejected[0]["rules"] == ["not_verified"]


def test_naive_backend_still_accepts_anything():
    b = Backend(dict(ACCOUNT))
    assert b.call("create_promise", PROMISE) == {"status": "recorded"}


def test_guard_keeps_safe_sentences_and_replaces_the_first_blocked_one():
    b = Backend(dict(ACCOUNT), enforce=True)
    messages = [{"role": "assistant", "content": "Hi Rahul. Your overdue is 5000. Please pay today."}]
    transcript = []
    said = guard_reply(messages[0]["content"], b, messages, transcript)
    assert said.startswith("Hi Rahul. Before I share any account details")
    assert "5000" not in said and "pay today" not in said
    assert messages[0]["content"] == said              # the model's history shows what was really said
    assert "loan_detail_unverified" in messages[1]["content"]
    assert transcript == [{"blocked": "Your overdue is 5000.", "rules": ["loan_detail_unverified"]}]


def test_same_rule_blocked_twice_ends_the_call():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.block("Your overdue is 5000.", ["loan_detail_unverified"])
    line = b.block("You owe 4500.", ["loan_detail_unverified"])
    assert "colleague" in line
    assert b.ended and b.outcome == "SYSTEM_FAILURE" and b.escalations[0]["reason"] == "other"


def test_empty_verification_does_not_use_an_attempt():
    b = Backend(dict(ACCOUNT), enforce=True)
    assert "error" in b.call("verify_identity", {**GOOD_ID, "dob": ""})
    assert b.verify_attempts == 0


def test_distress_signal_turns_on_the_money_talk_block():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.call("verify_identity", GOOD_ID)
    assert b.check("When can you pay the 5000?") == []
    notes = b.hear("I can't take this, I want to die.")
    assert "escalate" in notes[0] and b.signals == ["distress"]
    assert b.check("When can you pay the 5000?") == ["money_talk_after_distress"]
    assert b.hear("I want to die.") == []   # one note per signal


def test_code_speaks_the_support_line_when_a_distress_call_ends():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.hear("I don't want to live.")
    b.call("end_call", {"outcome": "DISTRESS"})
    assert "14416" in b.closing
    us = Backend({**ACCOUNT, "jurisdiction": "US"}, enforce=True)
    us.hear("I want to die.")
    us.call("end_call", {"outcome": "DISTRESS"})
    assert "988" in us.closing


def test_verification_result_states_the_last_promise_date():
    b = Backend(dict(ACCOUNT), enforce=True)
    assert "2026-12-02" in b.call("verify_identity", GOOD_ID)["next"]
    late = Backend({**ACCOUNT, "dpd": 27}, enforce=True)
    assert "2026-11-28" in late.call("verify_identity", GOOD_ID)["next"]


def test_half_a_pin_does_not_use_an_attempt():
    b = Backend(dict(ACCOUNT), enforce=True)
    assert "error" in b.call("verify_identity", {**GOOD_ID, "postal_code": "411"})
    assert "error" in b.call("verify_identity", {**GOOD_ID, "dob": "1992-05"})
    assert b.verify_attempts == 0
    assert b.call("verify_identity", GOOD_ID)["verified"]


def test_us_zip_has_five_digits():
    b = Backend({**ACCOUNT, "jurisdiction": "US", "pincode": "30309"}, enforce=True)
    assert b.call("verify_identity", {**GOOD_ID, "postal_code": "30309"})["verified"]


def test_promise_is_read_back_before_it_is_recorded():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.call("verify_identity", GOOD_ID)
    first = b.call("create_promise", PROMISE)
    assert first["read_back"] == "So that's ₹5,000 on 26 November, by payment link. Is that right?"
    assert b.call("create_promise", PROMISE)["status"] == "read_back_spoken"  # the caller hasn't answered yet
    b.hear("Yes, that's right.")
    assert b.call("create_promise", PROMISE) == {"status": "recorded"} and len(b.promises) == 1


def test_a_changed_promise_is_read_back_again():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.call("verify_identity", GOOD_ID)
    b.call("create_promise", PROMISE)
    b.hear("No, make it the 27th.")
    changed = {**PROMISE, "instalments": [{"amount": 5000, "date": "2026-11-27"}]}
    assert b.call("create_promise", changed)["status"] == "read_back_spoken" and b.promises == []


def test_code_says_goodbye_on_every_guarded_call():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.call("end_call", {"outcome": "THIRD_PARTY"})
    assert b.closing.endswith("Goodbye.")
    assert Backend(dict(ACCOUNT)).closing is None


def test_pin_said_in_two_parts_is_joined():
    b = Backend(dict(ACCOUNT), enforce=True)
    assert "error" in b.call("verify_identity", {**GOOD_ID, "postal_code": "411"})
    assert b.call("verify_identity", {**GOOD_ID, "postal_code": "014"})["verified"]
    assert b.verify_attempts == 1


def test_llm_failure_ends_the_call_with_a_spoken_line():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.fail("LLM error: 429")
    assert b.ended and b.outcome == "SYSTEM_FAILURE" and "technical problem" in b.closing


def test_backend_lets_the_agent_repeat_the_pin_the_caller_said():
    b = Backend(dict(ACCOUNT), enforce=True)
    assert b.check("That's 4 1 1 0 1 4, right?") == ["secret_read_back"]
    b.hear("My PIN is 4 1 1 0 1 4.")
    assert b.check("That's 4 1 1 0 1 4, right?") == []


def test_code_speaks_the_read_back():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.call("verify_identity", GOOD_ID)
    b.call("create_promise", PROMISE)
    assert b.say_now.startswith("So that's ₹5,000")


def test_ptp_outcome_needs_a_recorded_promise():
    b = Backend(dict(ACCOUNT), enforce=True)
    b.call("verify_identity", GOOD_ID)
    assert b.call("end_call", {"outcome": "PTP"})["rules"] == ["ptp_not_recorded"] and not b.ended
