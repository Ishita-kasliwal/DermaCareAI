"""Caring, human wording for result pages (Task 6).

Each situation has a few ways of saying the same thing, so results don't all read like a form letter. The
choice comes from the result's id, so one result always reads the same when you open it again, while different
results get different wording. Plain words only: no medical jargon, no "probability", no "inconclusive".

Serious results are never played down: they stay calm but clearly say "see a skin doctor soon".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# --------------------------------------------------------------------------------------------- wording
OPENERS = [
    "Thank you for checking with us. Here's what we found.",
    "Thanks for sharing your photo. We've had a careful look.",
    "We've looked closely at your photo. Here's what it shows.",
    "Thank you for trusting us with your photo. Here's our best reading of it.",
]

LEAD_IN = [  # small line above the name, for a clear result
    "Your photo looks most like",
    "This looks most like",
    "From your photo, this is most likely",
]

CALLOUT_TITLE = {
    "low": ["This is usually nothing serious", "Good news: this is usually harmless",
            "Most of the time, this isn't serious"],
    "medium": ["It's a good idea to have this checked", "We'd suggest showing this to a doctor",
               "Worth having a doctor take a look"],
    "high": ["Please see a skin doctor soon", "We'd really encourage you to see a skin doctor soon",
             "Please book a visit with a skin doctor soon"],
}

REASSURE = {
    "low": ["You're doing the right thing by checking.",
            "Lots of people have this, so you're not alone.",
            "Small, simple steps at home often help a lot."],
    "medium": ["There's no need to panic: this is usually easy to treat when it's looked at early.",
               "Getting it checked early usually makes treatment simple.",
               "A quick visit to a doctor can put your mind at rest."],
    "high": ["This doesn't mean you have it. Only a doctor can tell, and checking early is the best thing you can do.",
             "Try not to worry: this is not a diagnosis. A doctor can examine it properly, and early checks make a real difference.",
             "Many spots that look like this turn out to be fine, but this one should be seen by a doctor to be sure."],
}

UNCLEAR_TITLE = ["We're not sure about this one", "This photo is hard for the AI to read",
                 "The AI couldn't decide on this photo"]
UNCLEAR_BODY = [
    "Rather than guess, we'd prefer to be honest: the AI isn't confident enough to name one condition.",
    "The answers are too close to call, so we won't name one condition.",
    "We don't want to give you a wrong answer, so we won't name one condition this time.",
]

UNFAMILIAR_TITLE = ["This doesn't look like a skin problem we know", "We couldn't find a skin problem we know in this photo",
                    "This photo doesn't match the skin problems we can check"]

CLOSING = [
    "Take care of yourself, and please see a doctor if anything changes or worries you.",
    "Look after yourself, and don't hesitate to see a doctor if you're worried.",
    "Wishing you well. If anything gets worse or worries you, a doctor is the best person to ask.",
]

SCORE_NOTE = "The % shows how closely your photo matches. It isn't the chance that you have it."


@dataclass
class ResultWording:
    opener: str
    title: str            # big heading line (for unclear / unfamiliar) or the small lead-in (clear result)
    callout_title: str
    reassure: str
    closing: str
    score_note: str = SCORE_NOTE


def _pick(options: list[str], seed: str, salt: str) -> str:
    h = int(hashlib.sha1(f"{salt}:{seed}".encode()).hexdigest(), 16)
    return options[h % len(options)]


def wording_for(seed: str, kind: str, risk: str = "low") -> ResultWording:
    """kind: "clear" | "unclear" | "unfamiliar"; risk: "low" | "medium" | "high"; seed: the result's id."""
    risk = risk if risk in CALLOUT_TITLE else "low"
    if kind == "unfamiliar":
        title, callout, reassure = _pick(UNFAMILIAR_TITLE, seed, "uf"), "What you can do next", ""
    elif kind == "unclear":
        title, callout, reassure = _pick(UNCLEAR_TITLE, seed, "ut"), "What you can do next", _pick(UNCLEAR_BODY, seed, "ub")
    else:
        title = _pick(LEAD_IN, seed, "lead")
        callout = _pick(CALLOUT_TITLE[risk], seed, "ct")
        reassure = _pick(REASSURE[risk], seed, "re")
    return ResultWording(opener=_pick(OPENERS, seed, "op"), title=title, callout_title=callout,
                         reassure=reassure, closing=_pick(CLOSING, seed, "cl"))
