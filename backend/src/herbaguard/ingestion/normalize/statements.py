"""Sentence splitting and deterministic statement cues for interaction text.

The rules below were written against real sentences from EMA monographs, NCCIH fact sheets and
FDA labels (examples in the tests). They classify what a *sentence* says; they never decide the
final interaction class (Phase 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from herbaguard.domain.enums import StatementType

# Abbreviations that end with a full stop but do not end a sentence.
_ABBREVIATIONS = {
    "e.g", "i.e", "approx", "ca", "cf", "vs", "etc", "fig", "ref", "no", "nos", "st", "dr",
    "ph", "eur", "spp", "sp", "var", "subsp", "syn", "max", "min", "incl", "resp", "al",
}  # fmt: skip
_SENTENCE_END = re.compile(r"([.;!?])\s+(?=[A-Z(\[‘'\"])")


def split_sentences(text: str) -> list[str]:
    """Split into sentences without breaking at abbreviations or initials (``G. biloba``)."""
    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph:
            continue
        start = 0
        for match in _SENTENCE_END.finditer(paragraph):
            end = match.end(1)
            before = paragraph[start:end]
            last_word = re.findall(r"([A-Za-z.]+)[.;!?]$", before)
            token = last_word[0].lower().rstrip(".") if last_word else ""
            if match.group(1) == "." and (token in _ABBREVIATIONS or re.fullmatch(r"[a-z]", token)):
                continue
            sentences.append(paragraph[start:end].strip())
            start = match.end()
        tail = paragraph[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def split_paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


_NEGATION = re.compile(
    r"\b(no (clinically relevant |known |relevant |significant )?interactions? "
    r"(have|has|were|was|are)? ?(been )?(reported|observed|found|known|identified)"
    r"|do(es)? not (indicate|show|suggest)( that there is)? (an |any )?(clinically relevant )?interaction"
    r"|none (reported|known)"
    r"|no evidence of (an )?interaction"
    r"|did not (alter|affect|change|influence))",
    re.IGNORECASE,
)
_CONTRAINDICATION = re.compile(
    r"\b(contraindicated|not recommended|should be avoided|must be avoided|should not be used|"
    r"not to be used|do not use|avoid(ed)?)\b",
    re.IGNORECASE,
)
_CAUTION = re.compile(
    r"\b(caution|cautious|monitor(ing|ed)?|special care|consult|talk with your health care provider|"
    r"medical supervision|should be identified)\b",
    re.IGNORECASE,
)
_EFFECT = re.compile(
    r"\b(interact(s|ion|ions)?|increas\w*|decreas\w*|reduc\w*|induc\w*|inhibit\w*|potentiat\w*|"
    r"enhanc\w*|weaken\w*|counteract\w*|affect\w*|influenc\w*|lower\w*|rais\w*|risk|"
    r"aggravat\w*|interfere\w*)\b",
    re.IGNORECASE,
)
# Ordered by strength; the first match found in the sentence is relayed verbatim.
_SEVERITY_PHRASES = [
    r"is contraindicated", r"are contraindicated", r"contraindicated", r"not recommended",
    r"should be avoided", r"must be avoided", r"should not be used", r"not to be used",
    r"special care should be taken", r"caution is advised", r"used with caution",
    r"with caution", r"adequate monitoring is advised", r"monitor\w*",
]  # fmt: skip
_MECHANISM = re.compile(
    r"\b(induc\w*|inhibit\w*)\b[^.]{0,120}\b(CYP\s?\d[A-Z0-9]*|P-glycoprotein|P-gp|OATP\w*)",
    re.IGNORECASE,
)


_UNCERTAIN = re.compile(
    r"\b(conflicting evidence|evidence is (conflicting|inconclusive|unclear)|it is (not known|unclear)|"
    r"whether .{0,60}\binteract\w*|not enough (reliable )?information)\b",
    re.IGNORECASE,
)
# Generic advice that mentions interactions without asserting one for this sentence's drugs.
_BOILERPLATE = re.compile(
    r"[;,]?\s*some herbs and medicines (can )?interact in harmful ways\.?", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class StatementCues:
    statement_type: StatementType
    severity_wording: str | None
    negated: bool


def classify_statement(sentence: str, context: str | None = None) -> StatementCues:
    """Classify a sentence; ``context`` (e.g. a list lead-in) contributes cues but not wording."""
    sentence_core = _BOILERPLATE.sub("", sentence)
    context_core = _BOILERPLATE.sub("", context) if context else None
    combined = f"{context_core} {sentence_core}" if context_core else sentence_core
    negated = bool(_NEGATION.search(sentence_core))
    uncertain = bool(_UNCERTAIN.search(sentence_core))
    contraindication = bool(_CONTRAINDICATION.search(combined))
    caution = bool(_CAUTION.search(combined))
    effect = bool(_EFFECT.search(combined))

    if uncertain and not negated:
        statement = StatementType.UNCERTAIN
    elif negated and not (contraindication or caution):
        statement = StatementType.NO_INTERACTION_REPORTED
    elif negated:
        statement = (
            StatementType.PRECAUTION
        )  # e.g. "studies do not indicate ..., but monitoring is advised"
    elif contraindication or effect:
        statement = StatementType.INTERACTION
    elif caution:
        statement = StatementType.PRECAUTION
    else:
        statement = StatementType.UNCLASSIFIED

    severity = None
    for pattern in _SEVERITY_PHRASES:
        if match := re.search(pattern, sentence, re.IGNORECASE):
            severity = match.group(0)  # exact source wording
            break
    return StatementCues(statement, severity, negated)


def mechanism_sentence(sentences: list[str]) -> str | None:
    """First sentence naming an enzyme/transporter with induce/inhibit (verbatim)."""
    return next((s for s in sentences if _MECHANISM.search(s)), None)


_CONDITION_HEADER = re.compile(
    r"^(Indications? [\d), and]+|Daily dose of .{1,60}:?|Use as .{1,40}|"
    r"(Pharmacokinetic|Pharmacodynamic) interactions:?)$",
    re.IGNORECASE,
)


def is_condition_header(paragraph: str) -> bool:
    """Short sub-heading paragraphs that qualify what follows (EMA uses these heavily)."""
    return len(paragraph) <= 80 and bool(_CONDITION_HEADER.match(paragraph.strip()))
