"""Evidence assembly: the structured, traceable context given to the answer generator.

Item kinds and labels (labels are what the model may cite):

* ``C#`` — deterministic classification of a herb–drug pair, copied from the interaction service
  (class, finding, explanation, caveats, mechanism finding). The model explains it; it never
  produces one.
* ``S#`` — a source statement (verbatim sentence) that the interaction service used (decisive or
  context), with its conditions, use category, severity wording and subject check.
* ``M#`` — a mechanism path or herb effect from the knowledge graph. Its text is a deterministic
  description built from stored rows, including the source's hedging word ("may inhibit"); it is
  marked as graph context, never as a direct source quotation.
* ``E#`` — a retrieved excerpt (verbatim slice of stored source text).
* ``F#`` — a catalogue fact (source registry, coverage, FDA role listing).
* ``X#`` — an experimental record from an external research dataset (DDID).
* ``H#`` — LiverTox hepatotoxicity evidence (NIDDK/NLM): the likelihood-of-liver-injury assessments
  as published (master list and chapter, both kept when they differ) and verbatim chapter text.
  About liver injury only; the LiverTox likelihood score is never an interaction class.
* ``U#`` — a SUPP.AI supplementary interaction mention: one sentence selected automatically by the
  SUPP.AI model from a paper, with the paper's PMID, study flags and HerbaGuard's negation flag.
  Never a confirmed interaction and never part of the A–E classification. (``S#`` is taken by
  source statements, hence ``U``.)
* ``P#`` — a manufacturer product-label record from NIH DSLD: product name, brand and identifiers,
  the labelled amount of the matched herb ingredient and a "Precautions" statement, all verbatim.
  Product-label information only: never clinical evidence, an interaction assertion, a safety
  finding or an A–E class.

Rules:

* Text is never shortened. If the token budget is exceeded, whole items are left out (lowest
  priority first) and the number left out is reported as a limitation.
* SUPP.AI mentions (``U#``) are considered last: they have no reserved slot, they are placed only
  after every other kind of evidence, and at most one mention is included in a context.
* Items are de-duplicated: a retrieved excerpt that repeats a statement already present is dropped.
* Every item carries its source code, evidence type, location, URL and provenance from the
  database, and whether its source is registered as redistributable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from herbaguard.ai.retrieval import RetrievedEvidence
from herbaguard.api.schemas.mechanism_core import HerbEffectOut, MechanismPathOut
from herbaguard.api.schemas.provenance import EVIDENCE_TYPE_LABELS, ProvenanceOut
from herbaguard.api.schemas.resources import DrugCheckResult, StatementOut
from herbaguard.services.mappers import provenance_out

Kind = Literal[
    "classification",
    "statement",
    "mechanism",
    "excerpt",
    "fact",
    "observation",
    "hepatotoxicity",
    "mention",
    "product_label",
]
Role = Literal[
    "deterministic_classification",
    "direct_evidence",
    "graph_context",
    "catalogue",
    "experimental_evidence",
    "hepatotoxicity_evidence",
    "supplementary_mention",
    "product_label_information",
]


@dataclass(slots=True)
class ContextItem:
    label: str
    kind: Kind
    role: Role
    text: str
    source_code: str | None = None
    evidence_item_id: str | None = None
    external_id: str | None = None
    evidence_type: str | None = None
    title: str | None = None
    location: str | None = None
    url: str | None = None
    qualifiers: list[str] = field(default_factory=list)
    provenance: list[ProvenanceOut] = field(default_factory=list)
    redistributable: bool | None = None
    priority: int = 50  # lower = kept first under the budget

    @property
    def tokens(self) -> int:
        """Approximate tokens (≈4 characters per token for English text) incl. markup."""
        return math.ceil((len(self.text) + sum(len(q) for q in self.qualifiers)) / 4) + 40


@dataclass(slots=True)
class EvidenceContext:
    items: list[ContextItem]
    omitted: int = 0
    excluded_for_licence: int = 0
    notes: list[str] = field(default_factory=list)

    def by_label(self) -> dict[str, ContextItem]:
        return {i.label: i for i in self.items}

    @property
    def citable(self) -> list[ContextItem]:
        return [i for i in self.items if i.kind != "classification"]

    @property
    def tokens(self) -> int:
        return sum(i.tokens for i in self.items)


def _type_label(code: str | None) -> str | None:
    if code is None:
        return None
    return (
        f"{code} ({EVIDENCE_TYPE_LABELS.get(code, code)})" if code in EVIDENCE_TYPE_LABELS else code
    )


# --------------------------------------------------------------------------- builders


def classification_items(results: Iterable[DrugCheckResult], herb_name: str) -> list[ContextItem]:
    out = []
    for result in results:
        c = result.classification
        drug = result.drug.drug.name if result.drug.drug else result.drug.query
        lines = [
            f"Pair: {herb_name} + {drug}",
            f"Class {c.interaction_class.value} — {c.class_label}; finding: {c.finding_label}.",
            f"Explanation: {c.explanation}",
        ]
        if c.severity_wordings:
            lines.append("Severity wording quoted from sources: " + "; ".join(c.severity_wordings))
        if result.mechanism_assessment is not None:
            m = result.mechanism_assessment
            lines.append(f"Mechanism finding: {m.label}. {m.explanation}")
        lines += [f"Caveat: {caveat}" for caveat in c.caveats]
        out.append(
            ContextItem(
                label="",
                kind="classification",
                role="deterministic_classification",
                text="\n".join(lines),
                qualifiers=[c.method],
                priority=0,
            )
        )
    return out


def statement_item(s: StatementOut, *, priority: int) -> ContextItem | None:
    if not s.excerpt:
        return None
    qualifiers = [f"statement type: {s.statement_type.value} ({s.statement_type_note})"]
    if s.use_category and s.use_category != "not_applicable":
        qualifiers.append(f"use category: {s.use_category.replace('_', ' ')}")
    if s.conditions:
        qualifiers.append(f"conditions: {s.conditions}")
    if s.severity_wording:
        qualifiers.append(f"severity wording: {s.severity_wording}")
    if s.subject_check_note:
        qualifiers.append(f"subject check: {s.subject_check_note}")
    target = (
        s.drug.name if s.drug else (s.drug_class.code if s.drug_class else s.object_label_verbatim)
    )
    qualifiers.append(f"about: {target} ({'drug' if s.matched_via == 'drug' else 'drug class'})")
    return ContextItem(
        label="", kind="statement", role="direct_evidence", text=s.excerpt,
        source_code=s.source_code, evidence_item_id=s.evidence.id, external_id=s.evidence.external_id,
        evidence_type=s.evidence.evidence_type.code.value, title=s.evidence.title,
        location=f"section {s.source_section}" if s.source_section else None,
        url=s.evidence.url or (s.provenance[0].retrieved_url if s.provenance else None),
        qualifiers=qualifiers, provenance=list(s.provenance), priority=priority,
    )  # fmt: skip


def mechanism_path_item(p: MechanismPathOut) -> ContextItem:
    qualifiers = ["graph relationship (herb effect + FDA drug role), not a direct quotation"]
    qualifiers.append("meets the class-B rules" if p.qualifies_for_class_b else
                      "does not meet the class-B rules: " + " ".join(p.reasons_not_qualifying))  # fmt: skip
    if p.herb_effect.hedge_wording:
        qualifiers.append(f"source wording is hedged: '{p.herb_effect.hedge_wording}'")
    if p.experimental:
        qualifiers.append("herb-side evidence is in-vitro or animal")
    if p.conflicting:
        qualifiers.append("sources state opposite effects on this target")
    evidence = p.herb_effect.evidence
    return ContextItem(
        label="", kind="mechanism", role="graph_context", text=p.description,
        source_code=p.herb_effect.source_code, evidence_item_id=evidence.id if evidence else None,
        external_id=evidence.external_id if evidence else None,
        evidence_type=p.herb_effect.evidence_type.code.value, title=evidence.title if evidence else None,
        url=(evidence.url if evidence else None) or (p.herb_effect.provenance[0].retrieved_url if p.herb_effect.provenance else None),
        qualifiers=qualifiers, provenance=list(p.herb_effect.provenance) + list(p.drug_role.provenance),
        priority=10 if p.qualifies_for_class_b else 30,
    )  # fmt: skip


def herb_effect_item(e: HerbEffectOut) -> ContextItem:
    verb = f"{e.hedge_wording} {e.effect.removesuffix('s')}" if e.hedge_wording else e.effect
    strength = f" ({e.potency})" if e.potency else ""
    subject = (
        e.subject_label
        if e.subject_kind == "herbal_substance"
        else f"{e.subject_label} (a constituent of {e.herb})"
    )
    qualifiers = ["graph relationship, not a direct quotation"]
    if e.conditions:
        qualifiers.append(f"conditions: {e.conditions}")
    if e.subject_kind == "constituent":
        qualifiers.append(
            "stated for a constituent; does not show that the herbal preparation has this effect"
        )
    if e.evidence_type.code.value in ("INVITRO", "ANIMAL"):
        qualifiers.append("in-vitro or animal finding; not clinical evidence")
    quote = e.provenance[0].excerpt if e.provenance and e.provenance[0].excerpt else None
    text = f"{subject} {verb}{strength} {e.target.symbol} ({e.target.name})."
    if quote:
        text += f' Source sentence: "{quote}"'
    return ContextItem(
        label="", kind="mechanism", role="graph_context", text=text, source_code=e.source_code,
        evidence_item_id=e.evidence.id if e.evidence else None,
        external_id=e.evidence.external_id if e.evidence else None,
        evidence_type=e.evidence_type.code.value, title=e.evidence.title if e.evidence else None,
        url=(e.evidence.url if e.evidence else None) or (e.provenance[0].retrieved_url if e.provenance else None),
        qualifiers=qualifiers, provenance=list(e.provenance), priority=15,
    )  # fmt: skip


def excerpt_item(r: RetrievedEvidence, *, rank: int) -> ContextItem:
    qualifiers = [f"retrieved passage (rank {rank}); retrieval rank is not evidence quality"]
    if r.publication_year:
        qualifiers.append(f"publication year: {r.publication_year}")
    if r.document_date:
        qualifiers.append(f"document date: {r.document_date.isoformat()}")
    if r.herbs:
        qualifiers.append("linked herbs: " + ", ".join(r.herbs))
    return ContextItem(
        label="", kind="excerpt", role="direct_evidence", text=r.excerpt, source_code=r.source_code,
        evidence_item_id=str(r.evidence_item_id), external_id=r.external_id,
        evidence_type=r.evidence_type, title=r.title,
        location=f"{r.section}, characters {r.char_start}–{r.char_end}" if r.section else f"characters {r.char_start}–{r.char_end}",
        url=r.url, qualifiers=qualifiers, provenance=[provenance_out(p) for p in r.provenance],
        redistributable=r.redistributable, priority=20 + rank,
    )  # fmt: skip


STUDY_CONTEXT_NOTE = {
    "human": "human study (as stated by the dataset); a single study, not a confirmed clinical interaction",
    "animal": "animal study: NOT human clinical evidence",
    "unknown": "species not stated: NOT human clinical evidence",
}


def observation_item(
    *, text: str, study_context: str, effect_label: str, evidence_item_id: str | None,
    external_id: str | None, url: str | None, title: str | None, location: str,
    provenance: list[ProvenanceOut], plant_part_note: str | None, priority: int,
) -> ContextItem:  # fmt: skip
    """An experimental record from an external dataset (e.g. DDID). The dataset's own effect label
    is shown as such; it is never a HerbaGuard class."""
    qualifiers = [
        f"study context: {STUDY_CONTEXT_NOTE.get(study_context, study_context)}",
        f"dataset label '{effect_label}' is the database's own label, not a HerbaGuard A-E class",
        "secondary database record; licence of the dataset not verified",
    ]
    if plant_part_note:
        qualifiers.append(plant_part_note)
    evidence_type = {"human": "CLIN", "animal": "ANIMAL"}.get(study_context, "OTHER")
    return ContextItem(
        label="", kind="observation", role="experimental_evidence", text=text, source_code="ddid",
        evidence_item_id=evidence_item_id, external_id=external_id, evidence_type=evidence_type,
        title=title, location=location, url=url, qualifiers=qualifiers, provenance=provenance,
        redistributable=False, priority=priority,
    )  # fmt: skip


LIVERTOX_QUALIFIERS = (
    "LiverTox (NIDDK/NLM) hepatotoxicity evidence: about liver injury only, not about interactions",
    "the LiverTox likelihood score (A-E, X; [HD] = high doses) grades how likely the agent is to cause "
    "clinically apparent liver injury; it is NOT a HerbaGuard interaction class",
    "'unlikely cause of liver injury' does not mean safe; no LiverTox record does not mean safe",
)


def hepatotoxicity_item(
    *, text: str, title: str | None, location: str, url: str | None, external_id: str | None,
    provenance: list[ProvenanceOut], extra_qualifiers: Iterable[str] = (), priority: int,
) -> ContextItem:  # fmt: skip
    """LiverTox hepatotoxicity evidence for a herb whose LiverTox entry is mapped by a resolved
    (exact, reviewed) name match. Text is verbatim or a deterministic statement of the published
    assessments; the qualifiers say what it is and what it is not."""
    return ContextItem(
        label="", kind="hepatotoxicity", role="hepatotoxicity_evidence", text=text, source_code="livertox",
        external_id=external_id, title=title, location=location, url=url,
        qualifiers=[*LIVERTOX_QUALIFIERS, *extra_qualifiers], provenance=provenance, priority=priority,
    )  # fmt: skip


SUPP_AI_QUALIFIERS = (
    "SUPP.AI machine-extracted supplementary interaction mention: the sentence was selected automatically "
    "by a model; it is NOT a confirmed interaction and NOT a HerbaGuard classification",
    "a mention alone never establishes an interaction, and no mention never shows that there is no "
    "interaction; the HerbaGuard A-E class (C#) is authoritative",
    "SUPP.AI licence not verified: local models only, never sent to cloud models",
)
# Study type (ai/mentions.study_type). Only "clinical" and "human" notes contain "human study".
STUDY_TYPE_NOTE = {
    "clinical": "study type: clinical study (SUPP.AI paper flags clinical_study and human_study): one paper, "
                "human study, not a confirmed clinical interaction",
    "human": "study type: human study, not flagged as a clinical study (SUPP.AI paper flag)",
    "animal_and_human": "study type: paper flagged as both animal and human research; which part this sentence "
                        "reports is not stated: do not present it as human clinical evidence",
    "in_vitro": "study type: in-vitro or cell-based work (cells, hepatocytes, microsomes or similar are named), "
                "whatever the SUPP.AI flags say: NOT patient or clinical evidence",
    "animal_wording": "study type: animals are named in the paper title or sentence, whatever the SUPP.AI flags "
                      "say: NOT patient or clinical evidence",
    "conflicting": "study type: SUPP.AI flags conflict (clinical flag without a human flag; may be a veterinary "
                   "or animal study): NOT patient or clinical evidence",
    "animal": "study type: animal study (SUPP.AI paper flag): NOT human clinical evidence",
    "unknown": "study type: not stated by SUPP.AI: NOT human clinical evidence",
}  # fmt: skip
HUMAN_STUDY_NOTES = frozenset({STUDY_TYPE_NOTE["clinical"], STUDY_TYPE_NOTE["human"]})
NEGATION_NOTE = (
    "negation applies to this herb-drug pair ({cue}): the sentence may report that no effect was found for "
    "this pair; report it that way and never as evidence of an interaction, or as proof of no interaction"
)
WARNING_NOTE = (
    "warning wording ({cue}): the source advises against the combination; this is neither a confirmed "
    "interaction nor evidence that there is no interaction"
)
ELSEWHERE_NOTE = (
    "the sentence contains negation wording ({cue}) that does not appear to apply to this herb-drug pair "
    "(it concerns another substance or finding)"
)


def mention_item(
    *, text: str, study_type: str, negation_cue: str | None, external_id: str | None, url: str | None,
    title: str | None, location: str, provenance: list[ProvenanceOut], priority: int,
    warning_cue: str | None = None, other_negation_cue: str | None = None,
) -> ContextItem:  # fmt: skip
    """A SUPP.AI interaction mention for a herb–drug pair whose herb and drug are both mapped by a
    resolved name match. Supplementary context only; never a confirmed interaction."""
    qualifiers = [*SUPP_AI_QUALIFIERS, STUDY_TYPE_NOTE.get(study_type, STUDY_TYPE_NOTE["unknown"])]
    if negation_cue:
        qualifiers.append(NEGATION_NOTE.format(cue=f"'{negation_cue}'"))
    if warning_cue:
        qualifiers.append(WARNING_NOTE.format(cue=f"'{warning_cue}'"))
    if other_negation_cue and not negation_cue:
        qualifiers.append(ELSEWHERE_NOTE.format(cue=f"'{other_negation_cue}'"))
    return ContextItem(
        label="", kind="mention", role="supplementary_mention", text=text, source_code="supp_ai",
        external_id=external_id, title=title, location=location, url=url, qualifiers=qualifiers,
        provenance=provenance, redistributable=False, priority=priority,
    )  # fmt: skip


def mention_is_human(item: ContextItem) -> bool:
    return item.kind == "mention" and any(q in HUMAN_STUDY_NOTES for q in item.qualifiers)


def fact_item(text: str, *, source_code: str | None = None, priority: int = 40) -> ContextItem:
    return ContextItem(label="", kind="fact", role="catalogue", text=text, source_code=source_code,
                       qualifiers=["HerbaGuard catalogue information"], priority=priority)  # fmt: skip


PRODUCT_LABEL_QUALIFIERS = (
    "NIH DSLD product-label information: a manufacturer's label statement, NOT clinical evidence, "
    "NOT a study and NOT a HerbaGuard finding",
    "a label is not evidence of an interaction, efficacy or safety; a product listing or a missing "
    "listing says nothing about whether the herb or product is safe, effective or interacts with a "
    "medicine",
    "label wording may be marketing or precautionary text; report a precaution only as the "
    "manufacturer's wording, never as HerbaGuard's warning or advice",
    "NIH DSLD licence not verified: local models only, never sent to cloud models",
)


def product_label_item(
    *, text: str, title: str | None, location: str, url: str | None, external_id: str | None,
    provenance: list[ProvenanceOut], extra_qualifiers: Iterable[str] = (), priority: int = 55,
) -> ContextItem:  # fmt: skip
    """A manufacturer product-label record from NIH DSLD. It is product information, never clinical
    evidence, and it never feeds the A–E classification."""
    return ContextItem(
        label="", kind="product_label", role="product_label_information", text=text,
        source_code="nih_dsld", external_id=external_id, title=title, location=location, url=url,
        qualifiers=[*PRODUCT_LABEL_QUALIFIERS, *extra_qualifiers], provenance=provenance,
        redistributable=False, priority=priority,
    )  # fmt: skip


# --------------------------------------------------------------------------- assembly

_PREFIX: dict[Kind, str] = {
    "observation": "X",
    "hepatotoxicity": "H",
    "mention": "U",
    "product_label": "P",
    "classification": "C",
    "statement": "S",
    "mechanism": "M",
    "excerpt": "E",
    "fact": "F",
}


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


# Reserved slots for evidence from external datasets. SUPP.AI mentions are deliberately absent.
RESERVED_SLOTS: dict[str, int] = {"observation": 2, "hepatotoxicity": 2}
# At most one SUPP.AI mention reaches an assembled context, across all herb–drug pairs. It is only
# placed in capacity that every other item leaves free, so it can never displace or replace evidence.
MENTION_LIMIT = 1


def assemble(
    items: list[ContextItem],
    *,
    max_tokens: int,
    max_items: int,
    redistributable: dict[str, bool] | None = None,
    cloud_only_redistributable: bool = False,
    reserved: dict[str, int] | None = None,
) -> EvidenceContext:
    """Order by priority, de-duplicate, apply licence and budget limits, then assign labels.

    ``reserved`` (default: two slots for experimental records) is filled first, in priority order,
    so records of an external dataset are not crowded out by retrieved passages; the reserved
    items count against ``max_items`` and the token budget like any other item. Text is never
    shortened: an item that does not fit is left out whole.

    Supplementary mentions (``mention``, SUPP.AI ``U#``) are not part of those passes: they are
    considered only after every other kind of item has been chosen, and at most ``MENTION_LIMIT``
    of them is included, from capacity that nothing else needs."""
    reserved = RESERVED_SLOTS if reserved is None else reserved
    ordered = sorted(items, key=lambda i: i.priority)
    excluded = 0
    eligible: list[ContextItem] = []
    for item in ordered:
        if redistributable is not None and item.source_code and item.redistributable is None:
            item.redistributable = redistributable.get(item.source_code, False)
        if (
            cloud_only_redistributable
            and item.kind != "classification"
            and item.redistributable is False
        ):
            excluded += 1
            continue
        eligible.append(item)

    kept: set[int] = set()
    texts: list[str] = []
    budget = max_tokens
    evidence_count = 0
    omitted = 0

    def duplicate(item: ContextItem) -> bool:
        norm = _normalise(item.text)
        if item.kind != "classification" and norm in texts:
            return True  # identical item (e.g. the same effect stated for several species)
        return item.kind == "excerpt" and any(
            norm in t or (len(t) > 40 and t in norm) for t in texts
        )

    def take(index: int, item: ContextItem) -> None:
        nonlocal budget, evidence_count
        kept.add(index)
        texts.append(_normalise(item.text))
        budget -= item.tokens
        if item.kind != "classification":
            evidence_count += 1

    # Supplementary mentions wait until every other kind has been placed (pass 3).
    primary = [(index, item) for index, item in enumerate(eligible) if item.kind != "mention"]
    mentions = [(index, item) for index, item in enumerate(eligible) if item.kind == "mention"]

    # pass 1: classifications (always) and the reserved kinds, up to their slot count
    used = dict.fromkeys(reserved, 0)
    for index, item in primary:
        if item.kind == "classification":
            take(index, item)
        elif (
            item.kind in reserved
            and used[item.kind] < reserved[item.kind]
            and evidence_count < max_items
        ):
            if duplicate(item) or item.tokens > budget:
                continue
            used[item.kind] += 1
            take(index, item)
    # pass 2: everything else in priority order
    for index, item in primary:
        if index in kept or duplicate(item):
            continue
        if evidence_count >= max_items or item.tokens > budget:
            omitted += 1
            continue
        take(index, item)
    # pass 3: at most one supplementary mention, in its own ranked order, and only from capacity
    # that nothing stronger needs. A mention never evicts, replaces or reorders anything chosen
    # above. One that does not fit is left out whole and counted like any other item; candidates
    # beyond MENTION_LIMIT are excluded by that policy, not by the context limit, so they are not
    # reported as omissions.
    included = 0
    for index, item in mentions:
        if included >= MENTION_LIMIT:
            break
        if duplicate(item):
            continue
        if evidence_count >= max_items or item.tokens > budget:
            omitted += 1
            continue
        take(index, item)
        included += 1

    chosen = [item for index, item in enumerate(eligible) if index in kept]
    counters: dict[str, int] = {}
    for item in chosen:
        prefix = _PREFIX[item.kind]
        counters[prefix] = counters.get(prefix, 0) + 1
        item.label = f"{prefix}{counters[prefix]}"
    notes = []
    if omitted:
        notes.append(
            f"{omitted} further evidence item(s) were found but left out to stay within the context limit."
        )
    if excluded:
        notes.append(
            f"{excluded} evidence item(s) from sources not registered as redistributable were not sent to "
            "the cloud model (licensing guard)."
        )
    return EvidenceContext(chosen, omitted, excluded, notes)


def render(context: EvidenceContext) -> str:
    """Prompt text. Source text is wrapped in tags and its angle brackets are escaped, so retrieved
    documents cannot close the data block or inject instructions as markup."""
    blocks = []
    for item in context.items:
        attrs = [f'id="{item.label}"', f'role="{item.role}"']
        for name, value in (("source", item.source_code), ("evidence_type", _type_label(item.evidence_type)),
                            ("document", item.external_id), ("location", item.location)):  # fmt: skip
            if value:
                attrs.append(f'{name}="{_escape(value)}"')
        tag = {"classification": "classification", "fact": "fact"}.get(item.kind, "evidence")
        qualifiers = "".join(f"\n[{_escape(q)}]" for q in item.qualifiers)
        blocks.append(f"<{tag} {' '.join(attrs)}>\n{_escape(item.text)}{qualifiers}\n</{tag}>")
    return "\n\n".join(blocks)


def _escape(text: str) -> str:
    # U+2039/U+203A single angle quotation marks replace < and >.
    return text.replace("<", chr(0x2039)).replace(">", chr(0x203A)).replace(chr(34), "'")
