"""Deterministic reading of SUPP.AI interaction mentions: study type and pair-specific negation.

SUPP.AI gives paper-level study flags and no negation field. HerbaGuard derives two things from
the stored values, without a language model:

* **Study type.** From the flags, downgraded when the paper title or the sentence names cells,
  hepatocytes, microsomes or similar (``in_vitro``) or animals (``animal_wording``): the release
  flags such work as human research or even as clinical.
* **Negation for this pair.** The sentence is split into clauses (``;``, "but", "whereas",
  "however", …). A negation counts only if it is in a clause that names both this herb and this
  drug. Warnings ("not recommended", "should not be used") are a separate label, and phrases such
  as "not only" or "has not been studied" are not negations of an effect.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

# study types that may be presented as human evidence; everything else is NOT patient evidence
HUMAN_STUDY_TYPES = frozenset({"clinical", "human"})
STUDY_ORDER = {"clinical": 0, "human": 1, "animal_and_human": 2, "in_vitro": 3, "animal_wording": 4,
               "conflicting": 5, "unknown": 6, "animal": 7}  # fmt: skip
CONSISTENT_FLAGS = frozenset({"clinical", "human", "animal_and_human", "animal", "unknown"})

IN_VITRO = re.compile(
    r"\b(in[- ]vitro|ex[- ]vivo|cell[- ]?lines?|cells|cultured|cultures?|hepatocytes?|microsom\w*|"
    r"monolayers?|hepg2|caco-?2|ls180|hek ?293|hela|transfected|recombinant enzymes?|perfused (?:rat )?liver)\b",
    re.I,
)
ANIMAL = re.compile(
    r"\b(rats?|mice|mouse|murine|dogs?|canine|beagles?|rabbits?|pigs?|piglets?|porcine|monkeys?|"
    r"primates?|hamsters?|guinea pigs?|broilers?|chickens?|cattle|sheep|zebrafish|rodents?|veterinary)\b",
    re.I,
)


def study_type(paper: dict[str, Any] | None, sentence: str | None = None) -> str:
    """clinical / human / animal_and_human / in_vitro / animal_wording / conflicting / animal / unknown.

    "clinical" needs both clinical_study and human_study. Human, clinical and unflagged papers whose
    title or sentence names in-vitro work become ``in_vitro``; human, clinical and unflagged papers
    naming animals become ``animal_wording``."""
    if not paper:
        return "unknown"
    human, animal = bool(paper.get("human_study")), bool(paper.get("animal_study"))
    if paper.get("clinical_study"):
        base = "clinical" if human else "conflicting"
    elif human and animal:
        base = "animal_and_human"
    else:
        base = "human" if human else "animal" if animal else "unknown"
    described = f"{paper.get('title') or ''} {sentence or ''}"
    if base in ("clinical", "human", "animal_and_human", "unknown") and IN_VITRO.search(described):
        return "in_vitro"
    if base in ("clinical", "human", "unknown") and ANIMAL.search(described):
        return "animal_wording"
    return base


# --------------------------------------------------------------------------- negation

_CLAUSE = re.compile(
    r";|:|(?<=[.!?])\s+|\b(?:but|whereas|while|however|in contrast|by contrast|unlike)\b", re.I
)
WARNING = re.compile(
    r"\b(?:should|must|ought to) not be (?:used|given|taken|combined|co-?administered|prescribed|"
    r"administered|recommended)\b|\bshould be avoided\b|\b(?:is|are|was|were|be) (?:currently )?not "
    r"(?:recommended|advised|advisable)\b|\bnot recommended\b|\bcannot be given safely\b|"
    r"\bcontraindicated\b|\bavoid(?:ed|ance)?\b",
    re.I,
)
# negation words that do not deny an effect: emphasis, conditions, uncertainty, study limits
NOT_A_NEGATION = re.compile(
    r"\bnot only\b|\bif not\b|\bwhether or not\b|\bno longer\b|\bnot necessarily\b|"
    r"\b(?:has|have|had)? ?not (?:yet )?(?:been )?(?:well |fully )?(?:studied|investigated|evaluated|"
    r"established|known|reported|clear|understood|determined|examined|elucidated)\b|"
    r"\b(?:can|could|should|may)? ?not be (?:extrapolated|generali[sz]ed|excluded|ruled out)\b|"
    r"\bcannot be (?:excluded|ruled out)\b|\bwith or without\b",
    re.I,
)
# a clause that starts with the negation continues the previous clause's subject ("…, but did not …")
ELLIPTIC = re.compile(
    r"^\W*(?:(?:did|does|do|was|were|has|had|have)\s*)?(?:not|n't|no|never|failed to)\b", re.I
)
SINGLE_AGENT = re.compile(r"\b(?:alone|by itself|on its own|monotherapy)\b", re.I)
NEGATION_CUE = re.compile(
    r"\b(no|not|never|neither|nor|without|none|did ?n[o']t|does ?n[o']t|do ?n[o']t|was ?n[o']t|"
    r"were ?n[o']t|failed to|lack(?:ed|s)? of|absence of|unaffected|unchanged|unaltered|"
    r"insignificant|non-?significant)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class PairNegation:
    negated: str | None  # negation cue in a clause naming this herb AND this drug
    warning: str | None  # warning wording ("not recommended"), never a negation
    elsewhere: str | None  # negation wording that does not apply to this pair


def _terms_re(terms: Iterable[str]) -> re.Pattern[str] | None:
    usable = sorted({t.strip() for t in terms if t and len(t.strip()) >= 3}, key=len, reverse=True)
    if not usable:
        return None
    return re.compile(
        r"(?<![\w-])(?:" + "|".join(re.escape(t) for t in usable) + r")(?![\w-])", re.I
    )


def tagged_span(sentence: str, arg: Any) -> str | None:
    """The text SUPP.AI tagged for an argument, or None when the span is missing or misaligned
    (cuts a word, or has leading/trailing spaces; a few release spans are shifted)."""
    span = arg.get("span") if isinstance(arg, dict) else None
    if not (isinstance(span, list) and len(span) == 2 and all(isinstance(x, int) for x in span)):
        return None
    start, end = span
    text = sentence[start:end]
    if not text.strip() or text != text.strip() or not 0 <= start < end <= len(sentence):
        return None
    if (start > 0 and sentence[start - 1].isalnum() and text[0].isalnum()) or (
        end < len(sentence) and sentence[end].isalnum() and text[-1].isalnum()
    ):
        return None
    return text


def pair_negation(
    sentence: str, herb_terms: Sequence[str], drug_terms: Sequence[str]
) -> PairNegation:
    """Clause-aware negation for one herb–drug pair (see the module docstring)."""
    herb_re, drug_re = _terms_re(herb_terms), _terms_re(drug_terms)
    negated = warning = elsewhere = None
    herb_before = False  # the herb was named in an earlier clause of the sentence
    for clause in (c for c in _CLAUSE.split(sentence) if c and c.strip()):
        has_herb = bool(herb_re and herb_re.search(clause))
        has_drug = bool(drug_re and drug_re.search(clause))
        inherited = herb_before and not has_herb and bool(ELLIPTIC.match(clause))
        herb_before = herb_before or has_herb
        if (w := WARNING.search(clause)) is not None:
            warning = warning or w.group(0)
            continue  # a negation inside a warning clause belongs to the warning ("cannot … without")
        cue = NEGATION_CUE.search(NOT_A_NEGATION.sub(" ", clause))
        if cue is None:
            continue
        # The clause must name the drug and the herb, or continue the herb's clause without a new
        # subject ("St John's wort decreased A, but did not alter B"). "X alone did not …" is about
        # one substance by itself, not about the combination.
        names_pair = has_drug and (has_herb or inherited) and not SINGLE_AGENT.search(clause)
        if names_pair and negated is None:
            negated = cue.group(0)
        elif not names_pair and elsewhere is None:
            elsewhere = cue.group(0)
    return PairNegation(negated, warning, elsewhere)
