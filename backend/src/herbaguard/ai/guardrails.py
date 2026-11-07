"""Deterministic question screening, applied before retrieval and before any model call.

HerbaGuard explains what sources say. It never handles emergencies and never gives individual
dosing advice; both are recognised by fixed patterns (no model), so the behaviour is predictable
and testable. Patterns adapted from the parallel Phase 5 implementation on ``main`` (commit
e491d02, ``ai/guardrails.py``) and kept compatible with this architecture.

* ``EMERGENCY`` — overdose, poisoning, acute severe symptoms, self-harm: no retrieval, no
  generation, a referral message only.
* ``DOSING`` — "how much should I take", "what dose": no generated text; the official posology
  passages (e.g. EU monograph section 4.2) are quoted verbatim with a statement that they are not
  a recommendation for the reader.
* ``EVIDENCE`` — everything else.

Symptoms count as an emergency only when someone is having them now ("I have chest pain"), so
evidence questions such as "can ginkgo lower the seizure threshold?" are not refused.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class QuestionKind(StrEnum):
    EVIDENCE = "evidence"
    DOSING = "dosing"
    EMERGENCY = "emergency"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class Screening:
    kind: QuestionKind
    reason: str | None = None


def fold(text: str) -> str:
    """Lower-case, ASCII-folded, single-spaced text with straight apostrophes."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text.lower()).strip()


_WHO = (
    r"(?:i|i'm|im|i am|i've|ive|my (?:\w+ )?(?:child|son|daughter|baby|husband|wife|partner|mother|"
    r"father|mom|mum|dad|friend)|he|she|he's|she's|they|they're|we)"
)
_EMERGENCY = [
    r"\boverdos(?:e|ed|ing)\b",
    r"\b(?:i|he|she|they|we|my \w+) (?:might have |may have |think i )?(?:been )?poisoned\b",
    r"\b(?:took|swallowed|ate|drank|taken|has taken|have taken) (?:too many|too much|a whole|the whole|an entire|all (?:of )?(?:the|my))\b",
    rf"\b{_WHO} (?:\w+ )?(?:have|has|having|got|feel|feels|feeling) (?:a |bad |severe |sudden )?(?:chest pain|seizures?|convulsions?)\b",
    rf"\b{_WHO} (?:\w+ )?(?:can'?t|cannot|is unable to|am unable to|are unable to) breathe?\b",
    rf"\b{_WHO} (?:\w+ )?(?:having|have|has) (?:trouble|difficulty) breathing\b",
    rf"\b{_WHO} (?:\w+ )?(?:is |are |am )?(?:unconscious|unresponsive|passed out|fainted|collapsed)\b",
    r"\b(?:is|are|am) having a seizure\b",
    r"\banaphylactic (?:shock|reaction)\b",
    r"\b(?:throat|tongue|face|lips) (?:is |are )?(?:swelling|swollen|closing)\b",
    r"\bbleeding (?:that )?(?:won'?t|will not|does ?n[o']t|doesnt) stop\b",
    r"\b(?:vomiting|throwing up|coughing up) blood\b",
    r"\b(?:kill|harm|hurt) (?:my|him|her|them)sel(?:f|ves)\b|\bsuicid|\bend my life\b",
]
_DOSING = [
    r"\bhow (?:much|many)\b.*\b(?:take|use|give|drink|have|dose|capsules?|tablets?|mg|grams?|cups?|drops?)\b",
    r"\bwhat (?:is the |'?s the )?(?:right |correct |safe |recommended |best |maximum |max )?(?:dose|dosage|amount)\b",
    r"\b(?:dose|dosage|posology)\b.*\b(?:should|for me|can i|do i|my)\b",
    r"\b(?:should|can|may) i (?:take|use|give|double|increase|decrease|reduce)\b.*\b(?:mg|grams?|capsules?|tablets?|doses?|times a day|daily)\b",
    r"\bhow (?:often|long) should i (?:take|use)\b",
    r"\bmaximum (?:daily )?(?:dose|amount)\b",
]
_EMERGENCY_RE = [re.compile(p) for p in _EMERGENCY]
_DOSING_RE = [re.compile(p) for p in _DOSING]

EMERGENCY_MESSAGE = (
    "This sounds like it may be urgent. HerbaGuard cannot help in an emergency. Contact your local "
    "emergency number (112 in the EU) or a poison control centre now, or go to the nearest "
    "emergency department. Bring the product packaging and a list of all medicines you take."
)
DOSING_MESSAGE = (
    "HerbaGuard does not give individual dosing advice. The right amount depends on the product, "
    "the preparation, your other medicines and your health, so please ask a pharmacist or doctor. "
    "The passages below show what official documents state about posology; they are not a "
    "recommendation for you."
)
REFERRAL = (
    "Before starting, stopping or combining a herbal product with medicines, talk to your doctor "
    "or pharmacist and tell them about every product you use."
)
POSOLOGY_TERMS = ("posology", "method of administration", "daily dose", "dosage", "duration of use")


def screen(question: str) -> Screening:
    """Emergency wins over dosing; everything else is an evidence question."""
    text = fold(question)
    if not re.search(r"[a-z]", text):
        return Screening(QuestionKind.EMPTY, "The question contains no words.")
    for pattern in _EMERGENCY_RE:
        if pattern.search(text):
            return Screening(QuestionKind.EMERGENCY, "emergency wording")
    for pattern in _DOSING_RE:
        if pattern.search(text):
            return Screening(QuestionKind.DOSING, "dosing wording")
    return Screening(QuestionKind.EVIDENCE)
