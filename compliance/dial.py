"""Checkpoint 1: may we dial this loan's borrower now?"""

from datetime import time, timedelta
from zoneinfo import ZoneInfo

from compliance.rules import CONVERSATION_OUTCOMES, DIALABLE_STATES, RULES


def check_dial(loan, attempts, flags, now, consented=False):
    """Returns the rules a dial would break now.

    loan: jurisdiction, timezone, case_state, number_status, consent.
    attempts: earlier attempts on this loan, each with started_at (aware datetime) and outcome.
    flags: the borrower's contact rules, each with kind and value.
    now: aware datetime.
    consented: the borrower asked for this call (a callback). Frequency limits then don't apply
      (Reg F excludes calls the consumer agreed to in the last 7 days); the calling window still does.
    """
    rules = RULES[loan["jurisdiction"]]
    local = now.astimezone(ZoneInfo(loan["timezone"]))
    broken = []

    start, end = rules["window"]
    if not time(start) <= local.time() < time(end):
        broken.append("outside_calling_window")

    for flag in flags:
        if flag["kind"] == "stop_contact":
            broken.append("stop_contact")
        elif flag["kind"] == "channel_only":
            broken.append("voice_not_allowed")
        elif flag["kind"] == "avoid_time" and in_range(local.time(), flag["value"]):
            broken.append("borrower_avoid_time")

    if loan["case_state"] not in DIALABLE_STATES:
        broken.append("case_not_dialable")
    if loan.get("number_status") == "bad":
        broken.append("bad_number")
    if rules.get("needs_consent") and not loan.get("consent"):
        broken.append("no_consent")

    if not consented:
        broken += frequency(rules, local, attempts, now)
    return broken


def frequency(rules, local, attempts, now):
    broken = []
    if "max_attempts_per_day" in rules:
        today = [a for a in attempts
                 if a["started_at"].astimezone(local.tzinfo).date() == local.date()]
        if len(today) >= rules["max_attempts_per_day"]:
            broken.append("daily_attempt_limit")
    if "max_attempts_7_days" in rules:
        week = [a for a in attempts if now - a["started_at"] < timedelta(days=7)]
        if len(week) >= rules["max_attempts_7_days"]:
            broken.append("weekly_attempt_limit")
    if "quiet_days_after_conversation" in rules:
        quiet = timedelta(days=rules["quiet_days_after_conversation"])
        if any(a.get("outcome") in CONVERSATION_OUTCOMES and now - a["started_at"] < quiet
               for a in attempts):
            broken.append("quiet_period_after_conversation")
    return broken


def in_range(t, value):
    """value: {"from": "HH:MM", "to": "HH:MM"} in the borrower's local time."""
    return time.fromisoformat(value["from"]) <= t < time.fromisoformat(value["to"])
