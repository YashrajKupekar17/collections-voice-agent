"""Checkpoint 4: may the agent run this tool with these arguments?"""

from datetime import date, timedelta

from compliance.rules import MAX_BROKEN_PROMISES, MAX_VERIFY_ATTEMPTS, PROMISE


def check_tool(name, args, call, account, today):
    """Returns the rules a tool call would break.

    call: state of this call: verified, verify_attempts.
    account: overdue, min_partial, dpd, and broken_promises this cycle.
    today: date in the borrower's local time.
    """
    if name == "verify_identity":
        return ["verify_attempts_used"] if call["verify_attempts"] >= MAX_VERIFY_ATTEMPTS else []
    if name == "create_promise":
        return check_promise(args, call, account, today)
    if name == "end_call" and args.get("outcome") == "PTP" and not call.get("promises"):
        return ["ptp_not_recorded"]  # the outcome must match what was saved
    return []


def check_promise(args, call, account, today):
    if not call["verified"]:
        return ["not_verified"]
    if account.get("broken_promises", 0) >= MAX_BROKEN_PROMISES:
        return ["too_many_broken_promises"]

    broken = []
    if args.get("method") not in PROMISE["methods"]:
        broken.append("bad_method")
    instalments = args.get("instalments") or []
    if not 1 <= len(instalments) <= PROMISE["max_instalments"]:
        return broken + ["bad_instalment_count"]

    total = 0.0
    for i in instalments:
        try:
            amount = float(i["amount"])
            day = date.fromisoformat(str(i["date"]))
        except (KeyError, TypeError, ValueError):
            return broken + ["bad_instalment"]
        total += amount
        if amount <= 0:
            broken.append("amount_not_positive")
        if day < today:
            broken.append("date_in_past")
        if day > today + timedelta(days=PROMISE["max_days"]):
            broken.append("date_too_far")
        if account["dpd"] + (day - today).days >= PROMISE["dpd_limit"]:
            broken.append("date_past_dpd_limit")

    overdue = float(account["overdue"])
    if total > overdue:
        broken.append("amount_above_overdue")
    if total < min(float(account["min_partial"]), overdue):
        broken.append("amount_below_minimum")
    return sorted(set(broken), key=broken.index)
