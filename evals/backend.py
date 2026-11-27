"""Fake loan system for text-mode evals.

Implements the agent's tools and records everything the agent does,
so the checker can compare the final state with the scenario's expected result.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from compliance.input import DISTRESS_CLOSING, NOTES, check_input
from compliance.output import check_reply, safe_line
from compliance.rules import PROMISE
from compliance.tools import check_tool

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


PROMISE_RULES = (f"A promise needs: amount above zero, at least the minimum partial and at most the overdue; "
                 f"dates from today to {PROMISE['max_days']} days ahead; at most {PROMISE['max_instalments']} "
                 f"instalments; method link, branch or auto_debit.")
REJECT_HINTS = {
    "create_promise": PROMISE_RULES + " Read back amount, date and method and get a yes first. "
                      "Offer what fits, or move to hardship if nothing does.",
    "end_call": "No promise is recorded. If the borrower said yes to the read-back, call create_promise again "
                "with the same details; otherwise end with the outcome that fits.",
    "verify_identity": "No verification attempts left. Don't discuss the account; end the call as NOT_VERIFIED.",
}
DEBT_NOTICE = "This is an attempt to collect a debt, and any information obtained will be used for that purpose."
GOODBYE = "Thank you for your time. Goodbye."
TECHNICAL_PROBLEM = "I'm sorry, I'm having a technical problem on my side. We'll call you back later. Goodbye."
BLOCKED_TWICE = " I'll ask a colleague from our team to follow up with you. Goodbye."


METHOD_WORDS = {"link": "by payment link", "branch": "at a branch", "auto_debit": "by auto debit"}


def read_back(promise, account):
    symbol = "₹" if account.get("currency", "INR") == "INR" else "$"
    parts = [f"{symbol}{i['amount']:,.0f} on {date.fromisoformat(i['date']):%-d %B}" for i in promise["instalments"]]
    return f"So that's {' and '.join(parts)}, {METHOD_WORDS.get(promise['method'], promise['method'])}. Is that right?"


@dataclass
class Backend:
    """enforce=False is the naive agent: tools accept anything.
    enforce=True runs the compliance checks inside the tools and reveals the account only after verification."""

    account: dict
    enforce: bool = False
    today: date = date(2026, 11, 25)
    verified: bool = False
    verify_attempts: int = 0
    promises: list = field(default_factory=list)
    escalations: list = field(default_factory=list)
    outcome: str | None = None
    callback_at: str | None = None
    ended: bool = False
    rejected: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    heard: list = field(default_factory=list)  # what the caller said, for the read-back rule
    partial_postal: str = ""
    pending_promise: dict | None = None  # read back, waiting for the borrower's yes
    closing: str | None = None   # words code speaks after end_call, whatever the model did
    say_now: str | None = None   # words code speaks now, ending the model's turn (the promise read-back)

    def call(self, name, args):
        handlers = {
            "verify_identity": self.verify_identity,
            "create_promise": self.create_promise,
            "escalate": self.escalate,
            "end_call": self.end_call,
        }
        if name not in handlers:
            return {"error": f"unknown tool {name}"}
        if self.enforce:
            call = {"verified": self.verified, "verify_attempts": self.verify_attempts,
                    "promises": len(self.promises)}
            broken = check_tool(name, args, call, self.account, self.today)
            if broken:
                self.rejected.append({"tool": name, "args": args, "rules": broken})
                return {"status": "rejected", "rules": broken, "hint": REJECT_HINTS[name]}
        try:
            return handlers[name](**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}

    def verify_identity(self, dob, postal_code, speaking_with_borrower=True):
        if self.enforce:
            postal_code = self.join_postal(postal_code)
        if self.enforce and not self.complete_identity(dob, postal_code):
            return {"verified": False, "error": "Incomplete: the date of birth needs day, month and year, and the "
                                                f"postal code {self.postal_digits()} digits. Pass any new digits the "
                                                "caller says; they are joined with the earlier part. "
                                                "This did not count as an attempt."}
        self.verify_attempts += 1
        ok = (speaking_with_borrower
              and digits(dob) == digits(self.account["dob"])
              and digits(postal_code) == digits(self.account["pincode"]))
        if ok:
            self.verified = True
        if not self.enforce:
            return {"verified": ok}
        if not ok:
            # Never say which field was wrong.
            return {"verified": False, "attempts_left": max(0, 2 - self.verify_attempts)}
        return {"verified": True, "account": self.account_details(), "next": self.next_step()}

    def postal_digits(self):
        return 5 if self.account.get("jurisdiction") == "US" else 6

    def join_postal(self, postal_code):
        """Callers pause mid-number ("four one one ... zero one four"), so turn detection can split a PIN
        across turns. Keep a short piece and join it with the next one."""
        code = digits(postal_code)
        if len(code) < self.postal_digits() and len(self.partial_postal + code) <= self.postal_digits():
            code = self.partial_postal + code
        self.partial_postal = code if len(code) < self.postal_digits() else ""
        return code

    def complete_identity(self, dob, postal_code):
        return len(digits(dob)) == 8 and len(digits(postal_code)) == self.postal_digits()

    def account_details(self):
        a = self.account
        keys = ["loan_number", "currency", "emi", "overdue", "dpd", "min_partial", "history"]
        return {k: a[k] for k in keys if k in a}

    def last_promise_date(self):
        days = min(PROMISE["max_days"], PROMISE["dpd_limit"] - 1 - int(self.account["dpd"]))
        return self.today + timedelta(days=days)

    def next_step(self):
        steps = ("Tell the borrower the overdue amount and ask when they can pay. "
                 f"The latest date a promise can be for is {self.last_promise_date().isoformat()}.")
        if self.account.get("jurisdiction") == "US":
            steps = f'First say exactly: "{DEBT_NOTICE}" Then: {steps}'
        return steps

    def create_promise(self, instalments, method):
        # With enforce=True, call() has already checked the promise rules.
        promise = {"instalments": instalments, "method": method}
        if self.enforce and not self.confirmed(promise):
            # Two steps, so the read-back can't be skipped: the first call only proposes. The same promise
            # is recorded on a later call, after the caller has spoken. The model judges that they said yes.
            # Code speaks the read-back and ends the turn, so the model can't skip it or confirm in the same breath.
            self.pending_promise = {**promise, "heard_at": len(self.heard)}
            self.say_now = read_back(promise, self.account)
            return {"status": "read_back_spoken", "read_back": self.say_now,
                    "next": "The system has read this back to the borrower. If they say yes, call create_promise "
                            "again with the same details. If they change it, use the new details."}
        self.pending_promise = None
        self.promises.append(promise)
        return {"status": "recorded"}

    def confirmed(self, promise):
        p = self.pending_promise
        return (p is not None and p["instalments"] == promise["instalments"] and p["method"] == promise["method"]
                and len(self.heard) > p["heard_at"])

    def escalate(self, reason, summary):
        self.escalations.append({"reason": reason, "summary": summary})
        return {"status": "escalated"}

    def end_call(self, outcome, notes="", callback_at=None):
        if self.enforce:
            distress = "distress" in self.signals
            self.closing = DISTRESS_CLOSING[self.account.get("jurisdiction", "IN")] if distress else GOODBYE
        self.outcome = outcome
        self.callback_at = callback_at
        self.ended = True
        return {"status": "ended"}

    def fail(self, reason):
        """The agent can't continue (e.g. the LLM is down). Code says a fixed line and ends the call."""
        self.end_call("SYSTEM_FAILURE", notes=reason)
        self.closing = TECHNICAL_PROBLEM

    def hear(self, text):
        """Checkpoint 3: returns notes for the model about new signals in what the caller said."""
        self.heard.append(text)
        new = [s for s in check_input(text) if s not in self.signals]
        self.signals += new
        return [NOTES[s] for s in new]

    def check(self, sentence):
        """Checkpoint 5 for one sentence, with this call's state."""
        return check_reply(sentence, self.account, self.verified, distress="distress" in self.signals,
                           caller_said=" ".join(self.heard))

    def block(self, text, broken):
        """A sentence failed the output check. Returns the line to say instead.
        The same rule blocked twice means the model is stuck: hand over to a human and end the call."""
        repeat = any(r in b["rules"] for b in self.blocks for r in broken)
        self.blocks.append({"text": text, "rules": broken})
        line = safe_line(broken)
        if repeat:
            self.escalate("other", f"reply blocked twice for {broken}")
            self.end_call("SYSTEM_FAILURE", notes="output check blocked the same rule twice")
            line += BLOCKED_TWICE
        return line

    def snapshot(self):
        return {
            "verified": self.verified,
            "verify_attempts": self.verify_attempts,
            "promises": self.promises,
            "escalations": self.escalations,
            "outcome": self.outcome,
            "callback_at": self.callback_at,
            "rejected": self.rejected,
            "blocks": self.blocks,
            "signals": self.signals,
        }
