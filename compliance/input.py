"""Checkpoint 3: what the borrower said that the agent must act on, whatever the model thinks.

A signal changes the call's state: after distress, the output check blocks all money talk.
Keyword lists miss indirect phrasing; the model and the eval judge cover those.
"""

import re

SIGNALS = {
    "distress": re.compile(
        r"\b(kill (myself|me)|end (my|it all|my life)|suicid\w*|don'?t want to (live|be alive)"
        r"|no (point|reason) (in )?living|hurt myself|take my (own )?life|better off dead|want to die"
        r"|mar ja(un|ana|unga)|jeena nahi)\b",
        re.I,
    ),
    "stop_contact": re.compile(
        r"\b(stop calling|don'?t call( me)?( again)?|do not call|never call|remove my number"
        r"|cease (all )?(contact|communication))\b",
        re.I,
    ),
}

NOTES = {
    "distress": "The caller may be in distress. Stop all talk about money now. Respond with care, "
                "call escalate with reason distress, then end the call as DISTRESS. A support line is read "
                "out by code when the call ends. "
                "A code check blocks money talk for the rest of this call.",
    "stop_contact": "The caller asked us to stop calling. Confirm we will stop, don't try to collect, "
                    "then end the call as STOP_CONTACT.",
}


# Spoken by code when a call with a distress signal ends: the model skipped it in evals when asked to say it.
DISTRESS_CLOSING = {
    "IN": "I'm really sorry you're going through this. Someone from our team will reach out to you. "
          "If you need to talk to someone now, you can call Tele-MANAS on 14416, free, any time. Take care.",
    "US": "I'm really sorry you're going through this. Someone from our team will reach out to you. "
          "If you need to talk to someone now, you can call or text 988, any time. Take care.",
}


def check_input(text):
    text = text.replace("’", "'")
    return [name for name, pattern in SIGNALS.items() if pattern.search(text)]
