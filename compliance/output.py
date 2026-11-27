"""Checkpoint 5: may the agent say this sentence?

Regexes catch exact values and listed words. They miss paraphrases; the eval judge covers those.
"""

import re
from datetime import date

THREAT = re.compile(
    r"\b(arrest(ed)?|police|jail|prison|FIR|court|lawsuit|sue|legal (action|notice)|warrant"
    r"|seize|repossess\w*)\b"
    r"|\b(tell|inform|contact|call|notify|visit)\s+(your\s+)?(family|wife|husband|parents|employer"
    r"|boss|office|neighbou?rs|relatives|friends|references)\b",
    re.I,
)
OFFER = re.compile(
    r"\b(waive[sd]?|waiver|waiving|discount\w*|settle(ment)?|write[- ]off|forgive\w*"
    r"|reduc(e|ed|ing|tion)\s+(the\s+|your\s+)?(amount|interest|charges?|fees?|penalty))\b",
    re.I,
)
NEGATION = re.compile(r"\b(not|no|without|cannot|can't|can not|unable|won't|don't|isn't)\b", re.I)
HUMAN = re.compile(
    r"\bI('m| am)\s+(a\s+)?(real\s+)?(human|person|man|woman)\b"
    r"|\bI('m| am)\s+not\s+(an?\s+)?(AI|bot|robot|machine|computer)\b",
    re.I,
)
LOAN_WORDS = ["loan", "emi", "overdue", "dues", "due date", "(amount|minimum|past|partial)\\s+due",
              "minimum partial", "debt", "instal+ments?", "bounced?",
              "repay\\w*", "payments?", "rupees", "dollars", "outstanding"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

SAFE_LINES = {
    "money_talk_after_distress": "I'm really sorry you're going through this. I'm connecting you with "
                                 "someone from our team who can help.",
    "loan_detail_unverified": "Before I share any account details, I need to confirm I'm speaking "
                              "with the right person. Could you tell me your date of birth?",
    "secret_read_back": "For your security, I can't read personal details aloud.",
    "claims_human": "To be clear, I'm an AI assistant from YK Finance.",
    "threat": "I'm only here to help you find a way to pay that works for you.",
    "unauthorised_offer": "I can't change the amount or charges on this call, but I can connect you with our team.",
}


def check_reply(text, account, verified, distress=False, caller_said=""):
    """Returns the rules this text breaks, most serious first.
    distress: the caller showed distress (compliance.input); money talk is blocked from then on.
    caller_said: everything the caller said so far. Repeating a value back to the person who just
    said it ("4 1 1 0 1 4, right?") reveals nothing; saying a stored value they didn't say does."""
    text = text.replace("\u2019", "'")  # models often write curly apostrophes: can\u2019t
    broken = []
    if distress and loan_detail_pattern(account).search(text):
        broken.append("money_talk_after_distress")
    elif not verified and loan_detail_pattern(account).search(text):
        broken.append("loan_detail_unverified")
    if any(p.search(text) and not said_by_caller(name, p, account, caller_said)
           for name, p in secret_patterns(account).items()):
        broken.append("secret_read_back")
    if HUMAN.search(text):
        broken.append("claims_human")
    if THREAT.search(text):
        broken.append("threat")
    if any(not negated(text, m.start()) for m in OFFER.finditer(text)):
        broken.append("unauthorised_offer")
    return broken


SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentences(text):
    """Splits text into sentences, the unit the output check and TTS both work on."""
    return [s for s in SENTENCE_END.split(text.strip()) if s]


def safe_line(broken):
    return SAFE_LINES[broken[0]]


def blocked_note(broken, line):
    """Goes into the model's context so it doesn't repeat or build on the blocked reply."""
    return (f"Your last reply was not spoken because it broke these rules: {', '.join(broken)}. "
            f'The caller heard instead: "{line}" Continue from there and follow the rules.')


def negated(text, pos, window=6):
    """True if a negation word is among the few words before pos ("I can't offer a waiver")."""
    before = text[:pos].split()[-window:]
    return bool(NEGATION.search(" ".join(before)))


def amount_forms(n):
    n = int(float(n))
    forms = {str(n), f"{n:,}"}
    if n >= 100_000:  # Indian grouping: 1,25,000
        s = str(n)
        head, tail = s[:-3], s[-3:]
        forms.add(",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head)) + "," + tail)
    return forms


def loan_detail_pattern(account):
    amounts = set()
    for key in ("emi", "overdue"):
        amounts |= amount_forms(account[key])
    loan = account["loan_number"]
    terms = LOAN_WORDS + [re.escape(a) for a in amounts] + [re.escape(loan), re.escape(loan[-4:])]
    return re.compile(r"(₹|\$|\b(" + "|".join(terms) + r")\b)", re.I)


def secret_patterns(account):
    """Date of birth in common spoken and written forms, and the postal code."""
    d = date.fromisoformat(str(account["dob"]))
    month = MONTHS[d.month - 1]
    day = str(d.day)
    forms = [d.isoformat(), f"{d.day:02d}/{d.month:02d}/{d.year}", f"{d.day}/{d.month}/{d.year}",
             f"{d.day:02d}-{d.month:02d}-{d.year}", f"{d.month}/{d.day}/{d.year}"]
    spoken = [rf"{day}(st|nd|rd|th)?\s+(of\s+)?{month}", rf"{month}\s+{day}(st|nd|rd|th)?\b"]
    code = str(account["pincode"])
    dob = [re.escape(f) for f in forms] + spoken
    return {"dob": re.compile(r"\b(" + "|".join(dob) + r")\b", re.I),
            "postal_code": re.compile(r"\b" + r"[\s,-]?".join(code) + r"\b")}  # 411014, 411 014, 4-1-1-0-1-4


def said_by_caller(name, pattern, account, caller_said):
    """True if the caller said this value. Speech-to-text writes a PIN as separate digits ("4 1 1 0 1 4"),
    so the postal code is compared on digits alone."""
    if name == "postal_code":
        return str(account["pincode"]) in re.sub(r"\D", "", caller_said)
    return bool(pattern.search(caller_said))
