"""Deterministic question screening, applied before retrieval and before any LLM call.

The assistant answers questions about what sources say. It never gives individual dosing
advice and never handles emergencies; those are recognised by fixed patterns (no model), so the
behaviour is predictable and testable (docs/api/assistant.md §4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from herbaguard.ai.text import fold


class QuestionKind(StrEnum):
    EVIDENCE = "evidence"  # normal question about what sources say
    DOSING = "dosing"  # "how much / how many / what dose should I take"
    EMERGENCY = "emergency"  # overdose, poisoning, severe acute symptoms
    EMPTY = "empty"  # nothing left after normalisation


@dataclass(frozen=True, slots=True)
class Screening:
    kind: QuestionKind
    reason: str | None = None


# Symptoms count only when someone is having them now ("I have chest pain"), so that evidence
# questions such as "can ginkgo lower the seizure threshold?" are not treated as emergencies.
_WHO = r"(?:i|i'm|im|i am|i've|ive|my (?:\w+ )?(?:child|son|daughter|baby|husband|wife|partner|mother|father|mom|mum|dad|friend)|he|she|he's|she's|they|they're|we)"
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
    # An amount must be asked about: "can I take 600 mg", "should I take two capsules".
    # "Can I take ginseng with my blood pressure tablets?" is an interaction question.
    r"\b(?:should|can|may|could) i (?:take|use|give|have)\s+(?:\d+|one|two|three|four|five|more|less|extra|another|a second|a higher|a lower|a bigger|a double)\b",
    r"\b(?:double|increase|decrease|reduce|lower|raise) (?:my|the|his|her) (?:dose|dosage|amount)\b",
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
    "The sources below show what the official documents say about posology; they are not a "
    "recommendation for you."
)
REFERRAL = (
    "Before starting, stopping or combining a herbal product with medicines, talk to your doctor "
    "or pharmacist and tell them about every product you use."
)


def screen(question: str) -> Screening:
    """Classify a question. Emergency wins over dosing; everything else is an evidence question."""
    text = fold(question)
    if not re.search(r"[a-z]", text):
        return Screening(QuestionKind.EMPTY, "The question contains no words.")
    for pattern in _EMERGENCY_RE:
        if pattern.search(text):
            return Screening(QuestionKind.EMERGENCY, f"emergency pattern: {pattern.pattern}")
    for pattern in _DOSING_RE:
        if pattern.search(text):
            return Screening(QuestionKind.DOSING, f"dosing pattern: {pattern.pattern}")
    return Screening(QuestionKind.EVIDENCE)
