"""Deterministic extraction of herb → enzyme/transporter effects from regulatory text.

Input: one sentence from an EU herbal monograph (section 4.5, already stored by Phase 2).
Output: the effect (``induces`` / ``inhibits``) and the targets it names, or nothing.

The rules are deliberately narrow (precision before recall; every miss can be added later with a
test, a false edge would silently create mechanism-based "potential interaction" results):

1. The sentence must use a *verb* form ("induce(s)", "inhibit(s)", "induced", "inhibited") or
   "is/are a/an (potent/strong) inducer/inhibitor of". Nouns such as "inhibitors" alone describe
   other drugs ("Concomitant use with CYP3A4 inhibitors ...") and never produce an edge.
2. The grammatical subject must be the herbal preparation: the text before the verb must name it
   (the monograph's Latin name stem, "preparation", "extract", "herbal", the herb's common name or
   a configured constituent such as hyperforin). Otherwise the sentence is reported as
   ``subject_unclear``.
3. Relative clauses about other medicines ("medicinal products that inhibit CYP3A4") and negations
   ("does not inhibit", "no induction") never produce an edge.
4. The targets are read only from the text *after* the verb, with the fixed table in
   ``normalize/targets.py`` ("CYP" prefix required).
5. Sentences reporting in-vitro or animal findings are flagged (``study_context``) so the edge is
   stored with that evidence type and can never support class B.
6. A modal word directly before the verb ("may inhibit", "might induce", "can inhibit") is kept as
   ``hedge`` and stored with the edge, so the source's own uncertainty stays visible.
7. Sentences that name an enzyme/transporter without a recognised effect verb ("might affect the
   activity of CYP3A4", "because of induction of CYP3A4") give ``no_effect_verb``; the pipeline
   logs them for review instead of dropping them silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from herbaguard.domain.enums import ModulationEffect
from herbaguard.ingestion.normalize.targets import find_targets

EXTRACTION_VERSION = "ema_mechanism_sentence_v1"

_VERB = re.compile(
    r"\b(?P<verb>induc(?:e|es|ed|ing)|inhibit(?:s|ed|ing)?)\b"
    r"|\b(?:is|are|being)\s+(?:a|an)\s+(?:(?:potent|strong|moderate|weak)\s+)?"
    r"(?P<noun>inducer|inhibitor)s?\s+of\b",
    re.IGNORECASE,
)
_OTHER_DRUGS_CLAUSE = re.compile(
    r"\b(medicinal products|medicines|drugs|substances|agents|active substances)\s+"
    r"(that|which|known to)\s*$",
    re.IGNORECASE,
)
_HEDGE_BEFORE = re.compile(
    r"\b(?P<hedge>may|might|could|can|possibly|probably|potentially)\s+(?:also\s+)?$",
    re.IGNORECASE,
)
_NEGATION_BEFORE = re.compile(r"\b(not|no|neither|nor|without)\s+(\w+\s+){0,2}$", re.IGNORECASE)
_GENERIC_SUBJECTS = (r"preparations?", r"extracts?", r"herbal", r"herbal substances?")
# Phase 0 principle 2: in-vitro / animal findings are not clinical evidence. A monograph sentence
# that reports such a finding keeps that study type instead of the document's REG type.
_IN_VITRO = re.compile(
    r"\b(in vitro|in-vitro|microsom\w*|hepatocytes?|cell lines?)\b", re.IGNORECASE
)
_ANIMAL = re.compile(
    r"\b(in animals?|animal (studies|study|experiments?)|in (rats|mice|dogs))\b", re.IGNORECASE
)


class Outcome(StrEnum):
    EXTRACTED = "extracted"
    NO_MECHANISM = "no_mechanism"  # no effect verb or no enzyme/transporter
    SUBJECT_UNCLEAR = "subject_unclear"
    OTHER_DRUGS = "other_drugs"  # the verb belongs to a clause about other medicines
    NEGATED = "negated"
    NO_EFFECT_VERB = "no_effect_verb"  # names an enzyme/transporter, but no induce/inhibit verb


@dataclass(frozen=True, slots=True)
class MechanismStatement:
    effect: ModulationEffect
    targets: tuple[str, ...]  # HerbaGuard target symbols, in source order
    target_labels: tuple[str, ...]  # source wording, e.g. "CYP3A4", "P-glycoprotein"
    sentence: str  # verbatim
    study_context: str | None = None  # "in_vitro" | "animal" when the sentence says so
    hedge: str | None = None  # modal word before the verb, lower case ("may", "might")


def study_context(sentence: str) -> str | None:
    if _IN_VITRO.search(sentence):
        return "in_vitro"
    if _ANIMAL.search(sentence):
        return "animal"
    return None


@dataclass(slots=True)
class SentenceResult:
    outcome: Outcome
    statements: list[MechanismStatement] = field(default_factory=list)


def subject_patterns(latin_names: list[str], terms: list[str]) -> list[str]:
    """Regex alternatives that identify the herb as subject: generic words, the first word of each
    EMA Latin name (e.g. "Hyperici" for "Hyperici herba") and curated terms (whole phrases)."""
    stems = {n.split()[0] for n in latin_names if n.split()}
    return [
        *_GENERIC_SUBJECTS,
        *(re.escape(w) for w in sorted(stems)),
        *(re.escape(t) for t in sorted(set(terms))),
    ]


def extract_mechanisms(sentence: str, subject_names: list[str]) -> SentenceResult:
    """Apply the rules in the module docstring to one sentence."""
    verbs = list(_VERB.finditer(sentence))
    if not find_targets(sentence):
        return SentenceResult(Outcome.NO_MECHANISM)
    if not verbs:
        return SentenceResult(Outcome.NO_EFFECT_VERB)
    subject = re.compile(r"\b(" + "|".join(subject_names) + r")", re.IGNORECASE)
    result = SentenceResult(Outcome.NO_MECHANISM)
    rejected = Outcome.NO_EFFECT_VERB
    for index, match in enumerate(verbs):
        before = sentence[: match.start()]
        if _OTHER_DRUGS_CLAUSE.search(before):
            rejected = Outcome.OTHER_DRUGS
            continue
        if _NEGATION_BEFORE.search(before):
            rejected = Outcome.NEGATED
            continue
        if not subject.search(before):
            rejected = Outcome.SUBJECT_UNCLEAR
            continue
        end = verbs[index + 1].start() if index + 1 < len(verbs) else len(sentence)
        mentions = find_targets(sentence[match.end() : end])
        if not mentions:
            continue
        word = (match.group("verb") or match.group("noun") or "").lower()
        hedge = _HEDGE_BEFORE.search(before)
        effect = ModulationEffect.INDUCES if word.startswith("induc") else ModulationEffect.INHIBITS
        symbols: list[str] = []
        for mention in mentions:
            for symbol in mention.symbols:
                if symbol not in symbols:
                    symbols.append(symbol)
        result.statements.append(
            MechanismStatement(
                effect=effect,
                targets=tuple(symbols),
                target_labels=tuple(m.verbatim for m in mentions),
                sentence=sentence,
                study_context=study_context(sentence),
                hedge=hedge.group("hedge").lower() if hedge else None,
            )
        )
    result.outcome = Outcome.EXTRACTED if result.statements else rejected
    return result
