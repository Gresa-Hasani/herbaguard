"""PubMed (NCBI E-utilities): herb–drug interaction literature and high-level clinical evidence.

Two queries per herb (MeSH descriptor from ``herbs.yaml``):

* ``interaction``: ``"<MeSH>"[MeSH Terms] AND "Herb-Drug Interactions"[MeSH Terms]``
* ``clinical``: ``"<MeSH>"[MeSH Terms] AND (systematic review / meta-analysis / RCT)``

Evidence type comes from Publication Types and MeSH (``normalize.evidence_type``), never from an
LLM. Abstracts are stored only in the local database (publisher copyright) — never committed.
"""

from __future__ import annotations

import hashlib
import os

from herbaguard.domain.enums import EvidenceRelation
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.curation import load_herbs
from herbaguard.ingestion.loaders import (
    link_substance_evidence,
    replace_chunks,
    substances_for_herb,
    upsert_evidence,
)
from herbaguard.ingestion.normalize.evidence_type import classify_pubmed
from herbaguard.ingestion.parsers.pubmed_xml import parse_efetch

SOURCE = "pubmed"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
METHOD = "pubmed_v1"
QUERIES = {
    EvidenceRelation.LITERATURE_INTERACTION: (
        '"{mesh}"[MeSH Terms] AND "Herb-Drug Interactions"[MeSH Terms]',
        60,
    ),
    EvidenceRelation.LITERATURE_CLINICAL: (
        '"{mesh}"[MeSH Terms] AND (systematic review[pt] OR meta-analysis[pt] OR randomized controlled trial[pt])',
        25,
    ),
}
BATCH = 100


def _common_params(ctx: IngestionContext) -> dict[str, str]:
    params = {"tool": "herbaguard"}
    if key := os.environ.get("NCBI_API_KEY"):
        params["api_key"] = key
    return params


def run(ctx: IngestionContext, herb_keys: list[str] | None = None) -> None:
    links: dict[str, set[tuple[str, str]]] = {}  # pmid -> {(herb_key, relation)}
    query_info: dict[str, list[str]] = {}
    for herb in load_herbs().herbs:
        if herb_keys and herb.key not in herb_keys:
            continue
        for relation, (template, retmax) in QUERIES.items():
            term = template.format(mesh=herb.pubmed_mesh)
            fetched = ctx.fetch(
                f"{EUTILS}/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": term,
                    "retmode": "json",
                    "retmax": retmax,
                    "sort": "relevance",
                    **_common_params(ctx),
                },
                native_id=f"esearch:{herb.key}:{relation.value}",
            )
            result = fetched.json().get("esearchresult", {}) if fetched.ok else {}
            ids = result.get("idlist") or []
            ctx.stats[f"esearch_hits_{relation.value}"] += int(result.get("count", 0))
            for pmid in ids:
                links.setdefault(pmid, set()).add((herb.key, relation.value))
                query_info.setdefault(pmid, []).append(f"{relation.value}:{term}")

    pmids = sorted(links)
    for start in range(0, len(pmids), BATCH):
        batch = pmids[start : start + BATCH]
        digest = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
        fetched = ctx.fetch(
            f"{EUTILS}/efetch.fcgi",
            method="POST",
            data={"db": "pubmed", "id": ",".join(batch), "retmode": "xml", **_common_params(ctx)},
            native_id=f"efetch:{digest}",
        )
        if not fetched.ok:
            ctx.issue(
                "pubmed_efetch_failed",
                f"HTTP {fetched.result.status_code} for {len(batch)} PMIDs.",
                record=fetched.record,
            )
            continue
        for article in parse_efetch(fetched.content):
            evidence_type = classify_pubmed(article.publication_types, article.mesh_terms)
            evidence_id = upsert_evidence(
                ctx.session,
                source_code=SOURCE,
                external_id=article.pmid,
                evidence_type=evidence_type.value,
                title=article.title or f"PMID {article.pmid}",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/",
                pmid=article.pmid,
                doi=article.doi,
                publication_year=article.year,
                metadata_={
                    "journal": article.journal,
                    "publication_types": article.publication_types,
                    "mesh_terms": article.mesh_terms,
                    "language": article.language,
                    "queries": sorted(set(query_info.get(article.pmid, []))),
                    "has_abstract": bool(article.abstract),
                },
            )
            text = f"{article.title}\n\n{article.abstract}".strip()
            replace_chunks(
                ctx.session, evidence_id, [("title_abstract", text, {"pmid": article.pmid})]
            )
            for herb_key, relation_name in links.get(article.pmid, set()):
                link_substance_evidence(
                    ctx.session,
                    [s.id for s in substances_for_herb(ctx.session, herb_key)],
                    evidence_id,
                    relation_name,
                )
            ctx.provenance(
                "evidence_item",
                evidence_id,
                fetched.record,
                METHOD,
                location=f"PMID {article.pmid}",
            )
            ctx.stats[f"evidence_{evidence_type.value}"] += 1
            ctx.stats["articles"] += 1
        ctx.session.commit()
    missing = len(pmids) - ctx.stats["articles"]
    if missing > 0:
        ctx.issue(
            "pubmed_records_missing",
            f"{missing} PMIDs from esearch were not returned by efetch.",
            pmids_requested=len(pmids),
        )
