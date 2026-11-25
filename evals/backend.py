"""Fake loan system for text-mode evals.

Implements the agent's tools and records everything the agent does,
so the checker can compare the final state with the scenario's expected result.
"""

import re
from dataclasses import dataclass, field

OUTCOMES = [
    "NO_ANSWER", "BUSY", "UNREACHABLE", "INVALID_NUMBER", "VOICEMAIL", "CALL_FAILED",
    "THIRD_PARTY", "WRONG_NUMBER", "DECEASED_REPORTED", "NOT_VERIFIED",
    "PAID_ON_CALL", "CLAIMS_PAID", "PTP", "CALLBACK_REQUESTED", "REFUSED", "DISPUTE",
    "HARDSHIP", "STOP_CONTACT", "HUMAN_REQUESTED", "COMPLAINT", "LEGAL",
    "LANGUAGE_UNSUPPORTED", "DISTRESS",
    "HUNG_UP", "ENDED_ABUSIVE", "DROPPED", "SYSTEM_FAILURE",
]

ESCALATION_REASONS = [
    "hardship", "distress", "dispute", "fraud", "human_requested",
    "repeat_broken_promise", "other",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "verify_identity",
            "description": "Check the caller's identity. Pass what the caller said.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dob": {"type": "string", "description": "Date of birth as YYYY-MM-DD"},
                    "postal_code": {"type": "string", "description": "PIN code or ZIP code"},
                },
                "required": ["dob", "postal_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_promise",
            "description": "Record a promise to pay.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instalments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "amount": {"type": "number"},
                                "date": {"type": "string", "description": "YYYY-MM-DD"},
                            },
                            "required": ["amount", "date"],
                        },
                    },
                    "method": {"type": "string", "enum": ["link", "branch", "auto_debit"]},
                },
                "required": ["instalments", "method"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": "Hand the case to a human team.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "enum": ESCALATION_REASONS},
                    "summary": {"type": "string"},
                },
                "required": ["reason", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": "End the call and record its outcome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "outcome": {"type": "string", "enum": OUTCOMES},
                    "notes": {"type": "string"},
                    "callback_at": {
                        "type": "string",
                        "description": "ISO datetime, only for CALLBACK_REQUESTED",
                    },
                },
                "required": ["outcome"],
            },
        },
    },
]


def digits(text):
    return re.sub(r"\D", "", str(text))


@dataclass
class Backend:
    account: dict
    verified: bool = False
    verify_attempts: int = 0
    promises: list = field(default_factory=list)
    escalations: list = field(default_factory=list)
    outcome: str | None = None
    callback_at: str | None = None
    ended: bool = False

    def call(self, name, args):
        handlers = {
            "verify_identity": self.verify_identity,
            "create_promise": self.create_promise,
            "escalate": self.escalate,
            "end_call": self.end_call,
        }
        if name not in handlers:
            return {"error": f"unknown tool {name}"}
        try:
            return handlers[name](**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}

    def verify_identity(self, dob, postal_code):
        self.verify_attempts += 1
        ok = (digits(dob) == digits(self.account["dob"])
              and digits(postal_code) == digits(self.account["pincode"]))
        if ok:
            self.verified = True
        return {"verified": ok}

    def create_promise(self, instalments, method):
        # v0: no validation. Whatever the agent sends is recorded.
        self.promises.append({"instalments": instalments, "method": method})
        return {"status": "recorded"}

    def escalate(self, reason, summary):
        self.escalations.append({"reason": reason, "summary": summary})
        return {"status": "escalated"}

    def end_call(self, outcome, notes="", callback_at=None):
        self.outcome = outcome
        self.callback_at = callback_at
        self.ended = True
        return {"status": "ended"}

    def snapshot(self):
        return {
            "verified": self.verified,
            "verify_attempts": self.verify_attempts,
            "promises": self.promises,
            "escalations": self.escalations,
            "outcome": self.outcome,
            "callback_at": self.callback_at,
        }
