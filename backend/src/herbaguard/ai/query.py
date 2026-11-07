"""Deterministic question understanding: entities and intent. No language model is involved.

Entities are found by looking up every 1–5-word n-gram of the question in the existing name tables
(plant names incl. synonyms and common names, drug names, constituent names) with indexed
equality queries, so lookup cost does not grow with the size of those tables. Matches are then
resolved with the existing services (``resolve_herb`` — ambiguity gives candidates, never a guess;
``drugs.resolve`` — optional RxNav lookup for brand names). Enzymes and transporters are found with
the Phase 4 target table (``find_targets``).

Intent comes from fixed rules over the entities and cue words (see ``_intent``).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herbaguard.api.schemas.resources import HerbRef
from herbaguard.core.config import Settings
from herbaguard.ingestion.normalize.names import normalize_for_lookup
from herbaguard.ingestion.normalize.targets import find_targets
from herbaguard.models import Constituent, Drug, Target, TaxonName
from herbaguard.repositories import plants as plant_repo
from herbaguard.services import drugs as drug_service
from herbaguard.services import plants as plant_service


class Intent(StrEnum):
    HERB_DRUG_INTERACTION = "herb_drug_interaction"
    PLANT_SAFETY = "plant_safety"
    PLANT_INFORMATION = "plant_information"
    DRUG_INFORMATION = "drug_information"
    MECHANISM = "mechanism"
    CONSTITUENTS = "constituents"
    EVIDENCE_COMPARISON = "evidence_comparison"
    EVIDENCE_LOOKUP = "evidence_lookup"
    SOURCE_PROVENANCE = "source_provenance"
    DATA_COVERAGE = "data_coverage"
    GENERAL = "general"


_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-.]*")
_STOP = {
    "the", "and", "with", "does", "do", "is", "are", "can", "what", "which", "how", "about", "for",
    "of", "a", "an", "in", "on", "to", "or", "my", "i", "me", "it", "be", "if", "any", "there",
    "take", "taking", "use", "using", "while", "between", "interact", "interaction", "safe",
}  # fmt: skip
_CUES: dict[Intent, re.Pattern[str]] = {
    Intent.EVIDENCE_COMPARISON: re.compile(r"\b(compare|comparison|versus|vs\.?|differ\w*|disagree\w*|conflict\w*)\b", re.I),
    Intent.SOURCE_PROVENANCE: re.compile(r"\b(source|sources|reference|references|cite|citation|provenance|licen[cs]e|where does .* come from)\b", re.I),
    Intent.DATA_COVERAGE: re.compile(r"\b(which herbs|which plants|how many|coverage|covered|dataset|database contain\w*|what data)\b", re.I),
    Intent.MECHANISM: re.compile(r"\b(mechanism\w*|enzyme\w*|transporter\w*|metaboli[sz]\w*|induc\w*|inhibit\w*|cyp\w*|p-?gp|p-glycoprotein|pharmacokinetic\w*)\b", re.I),
    Intent.CONSTITUENTS: re.compile(r"\b(constituent\w*|compound\w*|active (ingredient|substance)\w*|chemical\w*|contain\w*)\b", re.I),
    Intent.PLANT_SAFETY: re.compile(r"\b(safe\w*|side effect\w*|adverse|risk\w*|warning\w*|contraindicat\w*|pregnan\w*|lactation|breast-?feeding|toxic\w*|precaution\w*)\b", re.I),
    Intent.EVIDENCE_LOOKUP: re.compile(r"\b(evidence|stud(y|ies)|trial\w*|research|literature|pubmed|meta-analys\w*|systematic review\w*)\b", re.I),
}  # fmt: skip
_ADVICE = re.compile(
    r"\b(should i|can i (take|use|stop|start|combine)|is it safe for me|my (doctor|medication|dose)|"
    r"what dose|how much should|how many (mg|tablets|capsules)|stop taking|start taking|"
    r"replace my|instead of my)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class FoundHerb:
    mention: str
    herb: HerbRef
    substance_ids: tuple[uuid.UUID, ...]
    wfo_ids: tuple[str, ...]
    scientific_names: tuple[str, ...]
    note: str | None


@dataclass(frozen=True, slots=True)
class FoundDrug:
    mention: str
    drug_id: uuid.UUID
    rxcui: str
    name: str
    via: str  # "name" | "first_word" | "rxnav"


@dataclass(frozen=True, slots=True)
class AmbiguousMention:
    mention: str
    kind: str  # "herb" | "drug"
    candidates: tuple[dict[str, object], ...]


@dataclass(slots=True)
class QuestionAnalysis:
    question: str
    intent: Intent
    herbs: list[FoundHerb] = field(default_factory=list)
    drugs: list[FoundDrug] = field(default_factory=list)
    targets: list[tuple[str, uuid.UUID]] = field(default_factory=list)  # (symbol, id)
    constituents: list[tuple[str, uuid.UUID]] = field(default_factory=list)
    ambiguous: list[AmbiguousMention] = field(default_factory=list)
    asks_for_personal_advice: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def expansions(self) -> tuple[str, ...]:
        """Entity names for the keyword query (accepted, pharmaceutical and common names)."""
        names: list[str] = []
        for h in self.herbs:
            names += [h.herb.pharmaceutical_name, h.herb.common_name or "", *h.scientific_names]
        names += [d.name for d in self.drugs]
        names += [symbol for symbol, _ in self.targets]
        names += [name for name, _ in self.constituents]
        return tuple(dict.fromkeys(n for n in names if n))


def _tokens(question: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).rstrip(".'’"), m.start(), m.end()) for m in _WORD.finditer(question)]


def _ngrams(tokens: list[tuple[str, int, int]], max_n: int = 5) -> list[tuple[str, int, int, int]]:
    """(normalised phrase, n, start token, end token) — longest first."""
    out = []
    for n in range(min(max_n, len(tokens)), 0, -1):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(t[0] for t in tokens[i : i + n])
            out.append((normalize_for_lookup(phrase), n, i, i + n))
    return out


def _usable(phrase: str, n: int) -> bool:
    return not (n == 1 and (len(phrase) < 4 or phrase in _STOP))


def analyse(
    session: Session, settings: Settings, question: str, *, allow_remote_drug_lookup: bool
) -> QuestionAnalysis:
    tokens = _tokens(question)
    grams = [g for g in _ngrams(tokens) if _usable(g[0], g[1])]
    keys = list({g[0] for g in grams})
    used: set[int] = set()

    plant_keys = set(
        session.scalars(
            select(TaxonName.normalized_name).where(TaxonName.normalized_name.in_(keys))
        )
    )
    drug_rows = {
        name.lower(): (drug_id, rxcui, name)
        for drug_id, rxcui, name in session.execute(
            select(Drug.id, Drug.rxcui, Drug.name).where(func.lower(Drug.name).in_(keys))
        )
    }
    constituent_rows = {
        name.lower(): cid
        for cid, name in session.execute(
            select(Constituent.id, Constituent.name).where(func.lower(Constituent.name).in_(keys))
        )
    }

    analysis = QuestionAnalysis(question=question, intent=Intent.GENERAL)
    seen_herbs: set[str] = set()
    seen_drugs: set[str] = set()
    for phrase, _n, start, end in grams:  # longest first; a token belongs to one entity
        span = set(range(start, end))
        if span & used:
            continue
        if phrase in plant_keys:
            resolution = plant_service.resolve_herb(session, phrase)
            if resolution.status == "ambiguous":
                analysis.ambiguous.append(
                    AmbiguousMention(
                        phrase, "herb", tuple(c.model_dump() for c in resolution.candidates)
                    )
                )
                used |= span
            elif resolution.status == "resolved" and resolution.herb is not None:
                herb = resolution.herb
                if herb.pharmaceutical_name not in seen_herbs:
                    seen_herbs.add(herb.pharmaceutical_name)
                    group = plant_repo.herb_group(session, herb.pharmaceutical_name)
                    analysis.herbs.append(
                        FoundHerb(
                            phrase,
                            herb,
                            tuple(s.id for s in group),
                            tuple(t.wfo_id for t in resolution.taxa),
                            tuple(t.scientific_name for t in resolution.taxa),
                            resolution.note,
                        )
                    )
                used |= span
        elif phrase in drug_rows:
            drug_id, rxcui, name = drug_rows[phrase]
            if rxcui not in seen_drugs:
                seen_drugs.add(rxcui)
                analysis.drugs.append(FoundDrug(phrase, drug_id, rxcui, name, "name"))
            used |= span
        elif phrase in constituent_rows:
            analysis.constituents.append((phrase, constituent_rows[phrase]))
            used |= span

    mentions = find_targets(question)
    for mention in mentions:
        for i, (_w, start, end) in enumerate(tokens):
            if start < mention.end and mention.start < end:
                used.add(i)
    for i, (word, _s, _e) in enumerate(tokens):
        if re.fullmatch(r"p-?gp|p-glycoprotein|bcrp|oatp\w*", word, re.I):
            used.add(i)

    # a single word that starts stored drug names: unique → that drug ("ibuprofen" style);
    # several (e.g. "lithium" → lithium carbonate / lithium citrate) → ambiguous, never a guess
    for i, (word, _s, _e) in enumerate(tokens):
        key = word.lower()
        if i in used or not _usable(key, 1):
            continue
        rows = session.execute(
            select(Drug.id, Drug.rxcui, Drug.name).where(func.split_part(func.lower(Drug.name), " ", 1) == key)
        ).all()  # fmt: skip
        if len(rows) == 1 and rows[0][1] not in seen_drugs:
            seen_drugs.add(rows[0][1])
            analysis.drugs.append(FoundDrug(word, rows[0][0], rows[0][1], rows[0][2], "first_word"))
            used.add(i)
        elif len(rows) > 1:
            options = tuple({"name": r[2], "rxcui": r[1]} for r in sorted(rows, key=lambda r: r[2]))
            analysis.ambiguous.append(AmbiguousMention(word, "drug", options))
            used.add(i)

    # unknown capitalised words may be brand names (e.g. "Coumadin"): RxNav, at most three lookups
    if allow_remote_drug_lookup:
        lookups = 0
        for i, (word, _s, _e) in enumerate(tokens):
            if lookups >= 3 or i in used or i == 0 or not word[:1].isupper() or len(word) < 5:
                continue
            if word.lower() in _STOP:
                continue
            lookups += 1
            found = drug_service.resolve(session, settings, word, allow_remote=True)
            if found.status == "resolved" and found.drug is not None:
                stored = session.scalar(select(Drug).where(Drug.rxcui == found.drug.rxcui))
                if stored is not None and stored.rxcui not in seen_drugs:
                    seen_drugs.add(stored.rxcui)
                    analysis.drugs.append(
                        FoundDrug(word, stored.id, stored.rxcui, stored.name, "rxnav")
                    )
                    used.add(i)

    symbols = list(dict.fromkeys(s for m in mentions for s in m.symbols))
    if re.search(r"\bp-?gp\b", question, re.I) and "ABCB1" not in symbols:
        symbols.append("ABCB1")
    if symbols:
        analysis.targets = [
            (t.symbol, t.id)
            for t in session.scalars(select(Target).where(Target.symbol.in_(symbols)))
        ]

    analysis.asks_for_personal_advice = bool(_ADVICE.search(question))
    analysis.intent = _intent(analysis, question)
    return analysis


def _intent(a: QuestionAnalysis, question: str) -> Intent:
    """First matching rule wins."""
    if a.herbs and a.drugs:
        return Intent.HERB_DRUG_INTERACTION
    if _CUES[Intent.DATA_COVERAGE].search(question) and not a.drugs:
        return Intent.DATA_COVERAGE
    if _CUES[Intent.SOURCE_PROVENANCE].search(question):
        return Intent.SOURCE_PROVENANCE
    if _CUES[Intent.EVIDENCE_COMPARISON].search(question) or len(a.herbs) > 1:
        return Intent.EVIDENCE_COMPARISON
    if a.targets or _CUES[Intent.MECHANISM].search(question):
        return Intent.MECHANISM
    if a.constituents or (a.herbs and _CUES[Intent.CONSTITUENTS].search(question)):
        return Intent.CONSTITUENTS
    if a.herbs and _CUES[Intent.PLANT_SAFETY].search(question):
        return Intent.PLANT_SAFETY
    if _CUES[Intent.EVIDENCE_LOOKUP].search(question):
        return Intent.EVIDENCE_LOOKUP
    if a.herbs:
        return Intent.PLANT_INFORMATION
    if a.drugs:
        return Intent.DRUG_INFORMATION
    return Intent.GENERAL
