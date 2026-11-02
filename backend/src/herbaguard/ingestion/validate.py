"""Post-ingestion data validation (``herbaguard validate``). Read-only.

Each check returns pass / warn / fail with a short detail. ``fail`` means a rule from the
scientific framework or data model is violated; ``warn`` means something needs attention but the
data is still usable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from herbaguard.ingestion.curation import load_herbs
from herbaguard.ingestion.parsers.ema_monograph import REQUIRED_SECTIONS

PROVENANCE_TABLES = (
    "taxon",
    "herbal_substance",
    "evidence_item",
    "interaction_assertion",
    "indication",
    "drug",
    "drug_class",
    # Phase 4 — mechanism layer
    "target",
    "target_modulation",
    "drug_target_role",
    "constituent",
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str  # pass | warn | fail
    detail: str


def _scalar(session: Session, sql: str, **params: object) -> int:
    return int(session.execute(text(sql), params).scalar() or 0)


def check_curated_herbs(session: Session) -> CheckResult:
    problems = []
    for herb in load_herbs().herbs:
        count = _scalar(
            session,
            "SELECT count(*) FROM herbal_substance WHERE pharmaceutical_name = :n AND in_curated_scope",
            n=herb.ema_latin_name,
        )
        if count != len(herb.taxa):
            problems.append(f"{herb.key}: {count}/{len(herb.taxa)} substances")
    status = "fail" if problems else "pass"
    return CheckResult(
        "curated_herbs_resolved",
        status,
        "; ".join(problems)
        or f"{len(load_herbs().herbs)} herbs, every curated taxon resolved to one accepted WFO taxon",
    )


def check_provenance(session: Session) -> list[CheckResult]:
    results = []
    for table in PROVENANCE_TABLES:
        key = "code" if table == "drug_class" else "id"
        missing = _scalar(
            session,
            f"SELECT count(*) FROM {table} t WHERE NOT EXISTS (SELECT 1 FROM provenance p "  # noqa: S608 - fixed table names
            f"WHERE p.entity_table = :t AND p.entity_id = t.{key}::text)",
            t=table,
        )
        total = _scalar(session, f"SELECT count(*) FROM {table}")  # noqa: S608
        results.append(
            CheckResult(
                f"provenance:{table}",
                "fail" if missing else "pass",
                f"{total - missing}/{total} rows have provenance",
            )
        )
    orphans = 0
    for table in (
        "taxon",
        "herbal_substance",
        "evidence_item",
        "interaction_assertion",
        "indication",
        "drug",
        "target",
        "target_modulation",
        "drug_target_role",
        "constituent",
    ):
        orphans += _scalar(
            session,
            f"SELECT count(*) FROM provenance p WHERE p.entity_table = :t AND NOT EXISTS "  # noqa: S608
            f"(SELECT 1 FROM {table} e WHERE e.id::text = p.entity_id)",
            t=table,
        )
    results.append(
        CheckResult(
            "provenance:orphans",
            "fail" if orphans else "pass",
            f"{orphans} provenance rows point to missing entities",
        )
    )
    return results


def check_no_superseded_evidence(session: Session) -> CheckResult:
    n = _scalar(
        session,
        "SELECT count(*) FROM interaction_assertion_evidence l JOIN evidence_item e ON e.id = l.evidence_item_id WHERE e.is_superseded",
    )
    return CheckResult(
        "no_superseded_evidence",
        "fail" if n else "pass",
        f"{n} assertions rely on superseded documents",
    )


def check_excerpts(session: Session) -> CheckResult:
    rows = session.execute(
        text(
            "SELECT a.id, p.verbatim_excerpt, string_agg(c.text, ' ') AS source_text "
            "FROM interaction_assertion a "
            "JOIN provenance p ON p.entity_table = 'interaction_assertion' AND p.entity_id = a.id::text "
            "JOIN interaction_assertion_evidence l ON l.interaction_assertion_id = a.id "
            "JOIN chunk c ON c.evidence_item_id = l.evidence_item_id "
            "GROUP BY a.id, p.verbatim_excerpt"
        )
    ).all()
    bad = 0
    for _, excerpt, source in rows:
        if not excerpt or re.sub(r"\s+", " ", excerpt) not in re.sub(r"\s+", " ", source or ""):
            bad += 1
    return CheckResult(
        "assertion_excerpts_in_source",
        "fail" if bad else "pass",
        f"{len(rows) - bad}/{len(rows)} excerpts found verbatim in stored source text",
    )


def check_ema_completeness(session: Session) -> CheckResult:
    rows = session.execute(
        text(
            "SELECT metadata->>'herb_key', metadata->'extraction'->'completeness' FROM evidence_item WHERE source_code='ema_hmpc' AND metadata ? 'extraction'"
        )
    ).all()
    gaps = [
        f"{herb}:{sec}={status}"
        for herb, comp in rows
        for sec, status in (comp or {}).items()
        if status != "complete"
    ]
    herbs = len(load_herbs().herbs)
    if len(rows) < herbs:
        return CheckResult(
            "ema_required_sections", "fail", f"only {len(rows)}/{herbs} monographs ingested"
        )
    return CheckResult(
        "ema_required_sections",
        "warn" if gaps else "pass",
        "; ".join(gaps)
        or f"{len(rows)} monographs × {len(REQUIRED_SECTIONS)} required sections complete for every covered use category",
    )


def check_ema_crosscheck(session: Session) -> CheckResult:
    rows = session.execute(
        text(
            "SELECT metadata->>'herb_key', x->>'section', x->>'use_category', x->>'status' FROM evidence_item, "
            "jsonb_array_elements(metadata->'extraction'->'crosscheck') x WHERE source_code='ema_hmpc'"
        )
    ).all()
    mismatches = [f"{h}:{s}:{c}" for h, s, c, st in rows if st == "mismatch"]
    return CheckResult(
        "ema_extraction_verified_against_pdfium",
        "fail" if mismatches or not rows else "pass",
        "; ".join(mismatches) or f"{len(rows)} section columns verified or consistently empty",
    )


def check_identifier_agreement(session: Session) -> CheckResult:
    n = _scalar(
        session,
        "SELECT count(*) FROM data_quality_issue i JOIN ingestion_run r ON r.id = i.ingestion_run_id "
        "WHERE i.rule = 'identifier_mismatch' AND r.id = (SELECT id FROM ingestion_run WHERE source_code='wfo_ethcstwin' "
        "AND status <> 'failed' ORDER BY started_at DESC LIMIT 1)",
    )
    return CheckResult(
        "cross_backbone_identifiers",
        "warn" if n else "pass",
        f"{n} identifier disagreements in the latest taxonomy run",
    )


def check_mechanism_edges(session: Session) -> list[CheckResult]:
    """Phase 4: every mechanism edge names its citable evidence item; EMA-derived effects quote a
    sentence that is present in the stored monograph section; no superseded document is used."""
    without_evidence = _scalar(
        session,
        "SELECT (SELECT count(*) FROM target_modulation WHERE evidence_item_id IS NULL) + "
        "(SELECT count(*) FROM drug_target_role WHERE evidence_item_id IS NULL)",
    )
    superseded = _scalar(
        session,
        "SELECT count(*) FROM target_modulation m JOIN evidence_item e ON e.id = m.evidence_item_id "
        "WHERE e.is_superseded",
    )
    rows = session.execute(
        text(
            "SELECT m.id, p.verbatim_excerpt, string_agg(c.text, ' ') FROM target_modulation m "
            "JOIN provenance p ON p.entity_table = 'target_modulation' AND p.entity_id = m.id::text "
            "JOIN chunk c ON c.evidence_item_id = m.evidence_item_id "
            "WHERE m.source_code = 'ema_hmpc' GROUP BY m.id, p.verbatim_excerpt"
        )
    ).all()
    bad = sum(
        1
        for _, excerpt, source in rows
        if not excerpt or re.sub(r"\s+", " ", excerpt) not in re.sub(r"\s+", " ", source or "")
    )
    return [
        CheckResult(
            "mechanism_edges_have_evidence",
            "fail" if without_evidence else "pass",
            f"{without_evidence} mechanism edges without an evidence item",
        ),
        CheckResult(
            "mechanism_no_superseded_evidence",
            "fail" if superseded else "pass",
            f"{superseded} herb effects rely on superseded documents",
        ),
        CheckResult(
            "mechanism_excerpts_in_source",
            "fail" if bad else "pass",
            f"{len(rows) - bad}/{len(rows)} EMA effect sentences found verbatim in stored section text",
        ),
    ]


def run_all(session: Session) -> list[CheckResult]:
    results = [check_curated_herbs(session)]
    results += check_provenance(session)
    results += [
        check_no_superseded_evidence(session),
        check_excerpts(session),
        check_ema_completeness(session),
        check_ema_crosscheck(session),
        check_identifier_agreement(session),
    ]
    results += check_mechanism_edges(session)
    return results
