from datetime import date, datetime, timedelta, timezone

import pytest

from compliance.dial import check_dial
from compliance.output import amount_forms, blocked_note, check_reply, safe_line
from compliance.tools import check_tool

IST = timezone(timedelta(hours=5, minutes=30))
ET = timezone(timedelta(hours=-5))

ACCOUNT = {"borrower": "Rahul Sharma", "dob": "1992-05-05", "pincode": "411014",
           "loan_number": "YK2W118842", "emi": 4500, "overdue": 5000, "min_partial": 4500, "dpd": 3}
TODAY = date(2026, 11, 25)


def india_loan(**kw):
    return {"jurisdiction": "IN", "timezone": "Asia/Kolkata", "case_state": "CONTACTING",
            "number_status": "ok", "consent": True, **kw}


def us_loan(**kw):
    return {"jurisdiction": "US", "timezone": "America/New_York", "case_state": "CONTACTING",
            "number_status": "ok", "consent": True, **kw}


# --- Checkpoint 1: before dial ---

def test_india_dial_inside_window_is_allowed():
    assert check_dial(india_loan(), [], [], datetime(2026, 11, 25, 11, 0, tzinfo=IST)) == []


@pytest.mark.parametrize("hour", [7, 19, 22])
def test_india_dial_outside_window_is_blocked(hour):
    now = datetime(2026, 11, 25, hour, 0, tzinfo=IST)
    assert check_dial(india_loan(), [], [], now) == ["outside_calling_window"]


def test_window_uses_the_borrowers_time_zone():
    # 20:30 in India is 10:00 in New York: fine for a US borrower.
    now = datetime(2026, 11, 25, 20, 30, tzinfo=IST)
    assert check_dial(us_loan(), [], [], now) == []
    assert check_dial(india_loan(), [], [], now) == ["outside_calling_window"]


def test_flags_block_the_dial():
    now = datetime(2026, 11, 25, 14, 0, tzinfo=IST)
    flags = [{"kind": "stop_contact", "value": {}},
             {"kind": "avoid_time", "value": {"from": "13:00", "to": "15:00"}},
             {"kind": "channel_only", "value": {"channel": "sms"}}]
    assert check_dial(india_loan(), [], flags, now) == \
        ["stop_contact", "borrower_avoid_time", "voice_not_allowed"]


def test_closed_case_bad_number_and_missing_consent():
    now = datetime(2026, 11, 25, 11, 0, tzinfo=ET)
    loan = us_loan(case_state="CURED", number_status="bad", consent=False)
    assert check_dial(loan, [], [], now) == ["case_not_dialable", "bad_number", "no_consent"]


def test_india_daily_cap_counts_today_only():
    now = datetime(2026, 11, 25, 16, 0, tzinfo=IST)
    today = [{"started_at": now - timedelta(hours=h), "outcome": "NO_ANSWER"} for h in (1, 2, 3)]
    assert check_dial(india_loan(), today, [], now) == ["daily_attempt_limit"]
    yesterday = [{"started_at": now - timedelta(days=1), "outcome": "NO_ANSWER"}] * 3
    assert check_dial(india_loan(), yesterday, [], now) == []


def test_us_seven_in_seven_days():
    now = datetime(2026, 11, 25, 11, 0, tzinfo=ET)
    six = [{"started_at": now - timedelta(days=d, hours=1), "outcome": "NO_ANSWER"} for d in range(6)]
    assert check_dial(us_loan(), six, [], now) == []
    seven = six + [{"started_at": now - timedelta(days=6, hours=23), "outcome": "NO_ANSWER"}]
    assert check_dial(us_loan(), seven, [], now) == ["weekly_attempt_limit"]
    old = six + [{"started_at": now - timedelta(days=7, hours=1), "outcome": "NO_ANSWER"}]
    assert check_dial(us_loan(), old, [], now) == []


def test_us_quiet_period_after_a_conversation():
    now = datetime(2026, 11, 25, 11, 0, tzinfo=ET)
    talked = [{"started_at": now - timedelta(days=3), "outcome": "REFUSED"}]
    assert check_dial(us_loan(), talked, [], now) == ["quiet_period_after_conversation"]
    voicemail = [{"started_at": now - timedelta(days=3), "outcome": "VOICEMAIL"}]
    assert check_dial(us_loan(), voicemail, [], now) == []


def test_requested_callback_skips_frequency_but_not_the_window():
    now = datetime(2026, 11, 25, 11, 0, tzinfo=ET)
    talked = [{"started_at": now - timedelta(hours=2), "outcome": "CALLBACK_REQUESTED"}]
    assert check_dial(us_loan(), talked, [], now, consented=True) == []
    late = datetime(2026, 11, 25, 22, 0, tzinfo=ET)
    assert check_dial(us_loan(), talked, [], late, consented=True) == ["outside_calling_window"]


# --- Checkpoint 4: tools ---

def promise(*instalments, method="link"):
    return {"instalments": [{"amount": a, "date": d} for a, d in instalments], "method": method}


VERIFIED = {"verified": True, "verify_attempts": 1}


def test_promise_needs_verification():
    call = {"verified": False, "verify_attempts": 0}
    assert check_tool("create_promise", promise((5000, "2026-11-25")), call, ACCOUNT, TODAY) == ["not_verified"]


def test_valid_promises_pass():
    assert check_tool("create_promise", promise((5000, "2026-11-25")), VERIFIED, ACCOUNT, TODAY) == []
    split = promise((2500, "2026-11-28"), (2500, "2026-12-02"))
    assert check_tool("create_promise", split, VERIFIED, ACCOUNT, TODAY) == []


@pytest.mark.parametrize("args,rule", [
    (promise((5000, "2026-12-03")), "date_too_far"),
    (promise((5000, "2026-11-24")), "date_in_past"),
    (promise((2000, "2026-11-26")), "amount_below_minimum"),
    (promise((6000, "2026-11-26")), "amount_above_overdue"),
    (promise((5000, "2026-11-26"), method="cash"), "bad_method"),
    (promise((2000, "2026-11-26"), (2000, "2026-11-27"), (1000, "2026-11-28")), "bad_instalment_count"),
    (promise((5000, "next month")), "bad_instalment"),
])
def test_out_of_policy_promises_are_refused(args, rule):
    assert rule in check_tool("create_promise", args, VERIFIED, ACCOUNT, TODAY)


def test_promise_date_must_land_before_31_dpd():
    late_account = {**ACCOUNT, "dpd": 27}
    assert check_tool("create_promise", promise((5000, "2026-11-29")), VERIFIED, late_account, TODAY) == \
        ["date_past_dpd_limit"]


def test_no_new_promise_after_two_broken():
    account = {**ACCOUNT, "broken_promises": 2}
    assert check_tool("create_promise", promise((5000, "2026-11-25")), VERIFIED, account, TODAY) == \
        ["too_many_broken_promises"]


def test_third_verification_attempt_is_refused():
    assert check_tool("verify_identity", {}, {"verified": False, "verify_attempts": 1}, ACCOUNT, TODAY) == []
    assert check_tool("verify_identity", {}, {"verified": False, "verify_attempts": 2}, ACCOUNT, TODAY) == \
        ["verify_attempts_used"]


# --- Checkpoint 5: output ---

@pytest.mark.parametrize("text", [
    "Your overdue amount is 5,000.",
    "Your EMI of ₹4500 bounced.",
    "I'm calling about loan YK2W118842.",
    "It's the account ending 8842.",
    "Please ask him to make the payment.",
])
def test_loan_details_before_verification_are_blocked(text):
    assert check_reply(text, ACCOUNT, verified=False) == ["loan_detail_unverified"]


def test_loan_details_after_verification_are_fine():
    assert check_reply("Your overdue amount is ₹5,000, due today.", ACCOUNT, verified=True) == []


def test_greeting_and_verification_request_pass():
    for text in ["Hi, this is Asha, an AI assistant from YK Finance. This call is recorded.",
                 "Could you please confirm your date of birth and PIN code?"]:
        assert check_reply(text, ACCOUNT, verified=False) == []


@pytest.mark.parametrize("text", [
    "Is your date of birth 5 May 1992?",
    "Is it the 5th of May?",
    "I have May 5th on file.",
    "Your DOB is 05/05/1992.",
    "Is your PIN code 411014?",
])
def test_secrets_are_never_read_aloud(text):
    assert "secret_read_back" in check_reply(text, ACCOUNT, verified=True)


@pytest.mark.parametrize("text", [
    "If you don't pay, the police may get involved.",
    "We will take legal action.",
    "We may have to inform your employer.",
    "Our team could visit your family.",
])
def test_threats_are_blocked(text):
    assert "threat" in check_reply(text, ACCOUNT, verified=True)


def test_offers_are_blocked_unless_negated():
    assert check_reply("I can waive the bounce charge for you.", ACCOUNT, True) == ["unauthorised_offer"]
    assert check_reply("We can offer a settlement.", ACCOUNT, True) == ["unauthorised_offer"]
    assert check_reply("I'm not able to offer a waiver on this call.", ACCOUNT, True) == []
    assert check_reply("I can't reduce the charges.", ACCOUNT, True) == []
    assert check_reply("I can\u2019t waive the fee.", ACCOUNT, True) == []
    assert check_reply("Shall we go ahead with 5000 today, without a waiver?", ACCOUNT, True) == []


def test_claiming_to_be_human_is_blocked():
    assert check_reply("Yes, I'm a real person.", ACCOUNT, True) == ["claims_human"]
    assert check_reply("I am not a bot.", ACCOUNT, True) == ["claims_human"]
    assert check_reply("No, I'm an AI assistant, not a person.", ACCOUNT, True) == []


def test_most_serious_rule_picks_the_safe_line():
    broken = check_reply("Your overdue is 5000 or the police will come.", ACCOUNT, verified=False)
    assert broken == ["loan_detail_unverified", "threat"]
    line = safe_line(broken)
    assert "date of birth" in line
    assert "loan_detail_unverified" in blocked_note(broken, line)


def test_indian_grouping_of_large_amounts():
    assert "1,25,000" in amount_forms(125000)
    assert "125,000" in amount_forms(125000)


# --- Checkpoint 3: input ---

from compliance.input import check_input


@pytest.mark.parametrize("text,signal", [
    ("Honestly I don't want to live anymore.", "distress"),
    ("Sometimes I think I should just end it all.", "distress"),
    ("I don’t want to be alive.", "distress"),
    ("Please stop calling me.", "stop_contact"),
    ("Don't call this number again.", "stop_contact"),
])
def test_input_signals(text, signal):
    assert check_input(text) == [signal]


def test_ordinary_replies_raise_no_signal():
    for text in ["I'll pay after salary.", "This is killing my budget, honestly.", "Call me at 6:30."]:
        assert check_input(text) == []


def test_money_talk_is_blocked_after_distress_even_when_verified():
    assert check_reply("Your overdue is 5000.", ACCOUNT, verified=True, distress=True) == \
        ["money_talk_after_distress"]
    assert check_reply("I'm sorry. Would it help to talk to someone?", ACCOUNT, True, distress=True) == []


def test_repeating_what_the_caller_just_said_is_allowed():
    said = "Yes it's me. 5th May 1992. PIN 4 1 1 0 1 4."
    assert check_reply("So that's 4 1 1 0 1 4, correct?", ACCOUNT, True, caller_said=said) == []
    assert check_reply("And your birth date is 5th May 1992?", ACCOUNT, True, caller_said=said) == []


def test_a_value_the_caller_did_not_say_is_still_blocked():
    said = "My date of birth is 5th May 1992."
    assert check_reply("Is your PIN 4-1-1-0-1-4?", ACCOUNT, True, caller_said=said) == ["secret_read_back"]
    assert check_reply("Is your DOB 5 May?", ACCOUNT, True, caller_said="PIN 411014") == ["secret_read_back"]


def test_amount_due_reveals_the_loan_before_verification():
    text = "It should be at least the minimum partial amount due."
    assert check_reply(text, ACCOUNT, verified=False) == ["loan_detail_unverified"]
    assert check_reply("I can't do that due to security rules.", ACCOUNT, verified=False) == []
