"""Rule settings per jurisdiction. Sources are in docs/engagement/discovery.md, section 6."""

RULES_VERSION = "2026-11-26"

RULES = {
    "IN": {
        "window": (8, 19),           # 8 AM to 7 PM local (RBI, from 1 Jan 2027)
        "max_attempts_per_day": 3,   # client cap, per loan
    },
    "US": {
        "window": (8, 21),           # 8 AM to 9 PM local (FDCPA, TCPA)
        "max_attempts_7_days": 7,    # per debt (Reg F 1006.14)
        "quiet_days_after_conversation": 7,
        "needs_consent": True,       # AI voice to a mobile is an artificial voice call (TCPA, FCC 2024)
    },
}

PROMISE = {
    "max_days": 7,
    "max_instalments": 2,
    "dpd_limit": 31,                 # the last promised date must come before the account reaches 31 DPD
    "methods": {"link", "branch", "auto_debit"},
}

MAX_VERIFY_ATTEMPTS = 2
MAX_BROKEN_PROMISES = 2

DIALABLE_STATES = {"OPEN", "CONTACTING", "UNREACHABLE"}

# Outcomes where we spoke with the borrower. They start the US quiet period.
CONVERSATION_OUTCOMES = {
    "PAID_ON_CALL", "CLAIMS_PAID", "PTP", "CALLBACK_REQUESTED", "REFUSED", "DISPUTE",
    "HARDSHIP", "STOP_CONTACT", "HUMAN_REQUESTED", "COMPLAINT", "LEGAL", "DISTRESS",
}
