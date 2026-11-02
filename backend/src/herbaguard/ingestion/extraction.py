"""Turn source text into candidate interaction statements using the curated lexicon.

Shared by the EMA, NCCIH and openFDA pipelines. Pure functions: no database or network.

Rules (all deterministic, all keep the source wording):

* Sentences are matched against the lexicon; each drug or class hit becomes a candidate.
* A class word used as a *description* right next to a named drug is skipped
  ("Warfarin, an anticoagulant (blood thinner)", "the drug nadolol, a beta-blocker"), so a
  statement about warfarin is not generalised to all anticoagulants.
* A class preceded by "some", "certain", "other", "several" or "many", or followed by
  "metabolised by …" / "transported by …", is a *partial* class reference. The qualifier is
  recorded in ``conditions`` so later phases cannot read it as the whole class.
* Unmapped lexicon phrases are reported, never mapped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from herbaguard.domain.enums import StatementType, UseCategory
from herbaguard.ingestion.normalize.lexicon import LexiconHit, LexiconMatcher
from herbaguard.ingestion.normalize.statements import (
    classify_statement,
    is_condition_header,
    mechanism_sentence,
    split_paragraphs,
    split_sentences,
)

# Only true appositions: "Warfarin, an anticoagulant", "anticoagulant (blood thinner)",
# "(blood thinner) warfarin". A bare comma is a list separator ("coumarin-type anticoagulants,
# cyclosporine, ...") and must NOT make the class descriptive.
_APPOSITION_GAP = re.compile(r"^\s*(,\s*(an?|the)\s+|\(\s*|\)\s*)$", re.IGNORECASE)
_PARTIAL_BEFORE = re.compile(r"\b(some|certain|other|several|many)\s+$", re.IGNORECASE)
_PARTIAL_AFTER = re.compile(
    r"^\s+((?:metaboli[sz]ed|transported)\s+(?:by|via)\s+[^.;]*?)(?=\s+(?:is|are|may|should)\b|[.;)]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    hit: LexiconHit
    sentence: str  # verbatim excerpt (must be a substring of the source text)
    statement_type: StatementType
    severity_wording: str | None
    conditions: str | None
    mechanism: str | None
    context: str | None  # lead-in sentence for list items


@dataclass(slots=True)
class ExtractionResult:
    candidates: list[Candidate] = field(default_factory=list)
    unmapped: list[tuple[str, str]] = field(default_factory=list)  # (phrase, sentence)
    descriptive_skipped: int = 0
    negated_sentences: int = 0


def _descriptive_classes(hits: list[LexiconHit], sentence: str) -> set[int]:
    """Indexes of class hits that only describe an adjacent named drug."""
    skip: set[int] = set()
    changed = True
    while changed:
        changed = False
        for i, hit in enumerate(hits):
            if hit.kind != "class" or i in skip:
                continue
            for j in (i - 1, i + 1):
                if not 0 <= j < len(hits):
                    continue
                other = hits[j]
                if other.kind != "drug" and j not in skip:
                    continue
                gap = sentence[other.end : hit.start] if j < i else sentence[hit.end : other.start]
                if _APPOSITION_GAP.match(gap):
                    skip.add(i)
                    changed = True
                    break
    return skip


def _partial_qualifier(hit: LexiconHit, sentence: str) -> str | None:
    before = _PARTIAL_BEFORE.search(sentence[: hit.start])
    after = _PARTIAL_AFTER.match(sentence[hit.end :])
    parts = []
    if before:
        parts.append(before.group(1))
    parts.append(hit.matched_text)
    if after:
        parts.append(after.group(1).strip())
    if before or after:
        return "Applies to part of the class only: '" + " ".join(parts) + "'"
    return None


def extract_from_sentence(
    matcher: LexiconMatcher,
    sentence: str,
    *,
    context: str | None = None,
    conditions: str | None = None,
    mechanism: str | None = None,
    result: ExtractionResult,
) -> None:
    hits = matcher.find(sentence)
    if not hits:
        return
    cues = classify_statement(sentence, context)
    if cues.negated:
        result.negated_sentences += 1
    descriptive = _descriptive_classes(hits, sentence)
    seen: set[tuple[str, str]] = set()
    for index, hit in enumerate(hits):
        if hit.kind == "unmapped":
            result.unmapped.append((hit.matched_text, sentence))
            continue
        if index in descriptive:
            result.descriptive_skipped += 1
            continue
        if (hit.kind, hit.key) in seen:
            continue  # same drug named twice in one sentence ("warfarin ... warfarin")
        seen.add((hit.kind, hit.key))
        hit_conditions = conditions
        if hit.kind == "class" and (partial := _partial_qualifier(hit, sentence)):
            hit_conditions = f"{conditions}; {partial}" if conditions else partial
        result.candidates.append(
            Candidate(
                hit=hit,
                sentence=sentence,
                statement_type=cues.statement_type,
                severity_wording=cues.severity_wording,
                conditions=hit_conditions,
                mechanism=mechanism,
                context=context,
            )
        )


def extract_from_monograph_text(
    matcher: LexiconMatcher,
    text: str,
    *,
    section_title: str | None = None,
    section_number: str | None = None,
) -> ExtractionResult:
    """EMA column text: tracks sub-headings ("Indications 1), 3) and 4)", "Daily dose of
    hyperforin > 1 mg:") as conditions and the paragraph's enzyme sentence as mechanism.

    In section 4.3 the heading itself ("Contraindications") carries the severity; when a
    sentence has no wording of its own, the heading is relayed verbatim.
    """
    result = ExtractionResult()
    indication_condition: str | None = None
    dose_condition: str | None = None
    for paragraph in split_paragraphs(text):
        if is_condition_header(paragraph):
            header = paragraph.rstrip(":")
            if header.lower().startswith("indication"):
                indication_condition, dose_condition = header, None
            elif header.lower().startswith(("daily dose", "use as")):
                dose_condition = header
            continue
        sentences = split_sentences(paragraph)
        mechanism = mechanism_sentence(sentences)
        conditions = "; ".join(c for c in (indication_condition, dose_condition) if c) or None
        for sentence in sentences:
            extract_from_sentence(
                matcher,
                sentence,
                conditions=conditions,
                mechanism=mechanism,
                result=result,
            )
    if section_number == "4.3" and section_title:
        result.candidates = [
            c
            if c.severity_wording
            else Candidate(
                hit=c.hit,
                sentence=c.sentence,
                statement_type=StatementType.INTERACTION,
                severity_wording=section_title,
                conditions=c.conditions,
                mechanism=c.mechanism,
                context=c.context,
            )
            for c in result.candidates
        ]
    return result


def none_reported(text: str) -> bool:
    """True when a section's entire text is an explicit 'none reported/known' statement."""
    return bool(re.fullmatch(r"\s*None (reported|known)\.?\s*", text, re.IGNORECASE))


SECTION_USE = {
    UseCategory.WELL_ESTABLISHED: "WEU",
    UseCategory.TRADITIONAL: "TU",
    UseCategory.NOT_APPLICABLE: "NA",
}
