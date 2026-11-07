"""SUPP.AI ingestion — supplement–drug interaction *mentions* extracted automatically from the
literature (Allen Institute for AI, https://supp.ai/).

Input: the JSON files of the SUPP.AI data release in ``data/raw/supp_ai/`` (never modified;
their SHA-256 is recorded in ``source_record``). Scope and rules (docs/data/external-datasets.md):

* Only supplements whose own name (or, as a reviewable candidate, a UMLS synonym listed by SUPP.AI)
  exactly matches a HerbaGuard herb name are imported, with every drug they are paired with.
  Supplement–supplement pairs and supplements that match no curated herb are counted and skipped.
* Each evidence sentence becomes one ``external_relation`` (predicate ``interaction_mentioned``)
  from the supplement to the drug, with the sentence, argument spans, SUPP.AI ids and the paper's
  metadata (PMID, DOI, title, year, study flags, retraction flag) stored verbatim.
* The sentences were selected by a machine-learning model. They are interaction *mentions*, not
  confirmed interactions: they are never written to ``interaction_assertion`` and never change the
  deterministic A–E classification.
* Idempotent (deterministic ids, upserts); after an error-free run, relations and entities of
  this source that are no longer produced are removed.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from herbaguard.domain.enums import IssueSeverity
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.pipelines.external_common import (
    CANDIDATE,
    UNRESOLVED,
    DrugMatcher,
    ExternalWriter,
    HerbMatcher,
    Mapping,
    delete_stale,
)

SOURCE = "supp_ai"
DOWNLOAD_PAGE = "https://supp.ai/"
FILES = {
    "meta": "meta.json",
    "cui": "cui_metadata.json",
    "pairs": "interaction_id_dict.json",
    "sentences": "sentence_dict.json",
    "papers": "paper_metadata.json",
}
PREDICATE = "interaction_mentioned"
_TOP_KEY = re.compile(r'^ {4}"((?:[^"\\]|\\.)*)": ?(.*)$')


def iter_top_level(path: Path, wanted: set[str]) -> Iterator[tuple[str, int, Any]]:
    """Stream ``(key, line number, value)`` for the wanted top-level keys of a large JSON object
    written with 4-space indentation (the SUPP.AI release format), without loading the file.
    Raises ``ValueError`` if the file does not have that layout."""
    with path.open(encoding="utf-8") as handle:
        first = handle.readline()
        if first.strip() != "{":
            msg = f"{path.name}: expected a JSON object starting with '{{' on its own line"
            raise ValueError(msg)
        key: str | None = None
        start = 0
        buffer: list[str] = []
        found_any = False

        def finish() -> tuple[str, int, Any] | None:
            if key is None or key not in wanted:
                return None
            text = "".join(buffer).rstrip().rstrip(",")
            return key, start, json.loads(text)

        for number, line in enumerate(handle, start=2):
            match = _TOP_KEY.match(line)
            if match or line.rstrip() == "}":
                done = finish()
                if done is not None:
                    yield done
                buffer = []
                key = None
                if match:
                    found_any = True
                    key, start = json.loads(f'"{match.group(1)}"'), number
                    buffer = [match.group(2) + "\n"]
                continue
            if key is not None and key in wanted:
                buffer.append(line)
        if not found_any:
            msg = f"{path.name}: no top-level keys found with 4-space indentation; format changed?"
            raise ValueError(msg)


def run(ctx: IngestionContext, directory: Path) -> None:
    writer = ExternalWriter(ctx, SOURCE, DOWNLOAD_PAGE)
    stats: Counter[str] = ctx.stats
    records = {
        key: writer.register(directory / name, f"data/raw/supp_ai/{name}", "application/json")
        for key, name in FILES.items()
    }
    meta = json.loads((directory / FILES["meta"]).read_text(encoding="utf-8"))
    release = meta.get("last_updated_on")
    cui = json.loads((directory / FILES["cui"]).read_text(encoding="utf-8"))
    pairs = json.loads((directory / FILES["pairs"]).read_text(encoding="utf-8"))
    herbs, drugs = HerbMatcher(ctx.session), DrugMatcher(ctx.session)

    # 1. supplements that are curated herbs (exact names only)
    supplements: dict[str, Mapping] = {}
    for code, item in cui.items():
        if item.get("ent_type") != "supplement":
            continue
        stats["supplements_in_release"] += 1
        mapping = herbs.map(item.get("preferred_name"), item.get("synonyms") or [])
        if mapping.status == UNRESOLVED:
            stats["supplements_skipped_no_curated_herb"] += 1
            continue
        supplements[code] = mapping

    # 2. supplement–drug pairs
    kept: dict[str, tuple[str, str]] = {}  # pair id → (supplement CUI, drug CUI)
    for code in supplements:
        for pair_id in pairs.get(code, []):
            a, _, b = pair_id.partition("-")
            other = b if a == code else a
            other_type = cui.get(other, {}).get("ent_type")
            if other_type is None:
                stats["pairs_rejected_unknown_cui"] += 1
                ctx.issue("supp_ai_unknown_cui", f"Pair {pair_id} names {other}, which cui_metadata does not define.",
                          severity=IssueSeverity.WARNING, record=records["pairs"])  # fmt: skip
                continue
            if other_type != "drug":
                stats["pairs_skipped_supplement_supplement"] += 1
                continue
            kept[pair_id] = (code, other)
    stats["pairs_kept"] = len(kept)

    # 3. evidence sentences of the kept pairs (streamed)
    sentences: dict[str, tuple[int, list[dict[str, Any]]]] = {}
    for pair_id, line, value in iter_top_level(directory / FILES["sentences"], set(kept)):
        sentences[pair_id] = (line, value)
    stats["pairs_without_sentences"] = len(set(kept) - set(sentences))
    paper_ids = {
        str(s.get("paper_id"))
        for _, items in sentences.values()
        for s in items
        if s.get("paper_id")
    }
    papers = {
        key: (line, value)
        for key, line, value in iter_top_level(directory / FILES["papers"], paper_ids)
    }
    stats["papers_missing_metadata"] = len(paper_ids - set(papers))

    # 4. entities
    entities: list[dict[str, Any]] = []
    for code, mapping in supplements.items():
        item = cui[code]
        entities.append(writer.entity("supplement", code, item.get("preferred_name"), item,
                                      {"umls_cui": code}, records["cui"], [], mapping))  # fmt: skip
        if mapping.status == CANDIDATE:
            ctx.issue("supp_ai_mapping_needs_review",
                      f"{code} '{item.get('preferred_name')}' matches a HerbaGuard herb only through a name variant.",
                      severity=IssueSeverity.INFO, record=records["cui"])  # fmt: skip
    for code in sorted({d for _, d in kept.values()}):
        item = cui[code]
        mapping = drugs.map(item.get("preferred_name"), item.get("synonyms") or [])
        entities.append(writer.entity("drug", code, item.get("preferred_name"), item,
                                      {"umls_cui": code}, records["cui"], [], mapping))  # fmt: skip
    writer.upsert_entities(entities)

    # 5. one relation per evidence sentence
    relations: list[dict[str, Any]] = []
    seen_uids: set[Any] = set()
    for pair_id, (supplement, drug) in sorted(kept.items()):
        line, items = sentences.get(pair_id, (0, []))
        for sentence in items:
            stats["sentences_read"] += 1
            if not sentence.get("sentence") or sentence.get("paper_id") is None:
                stats["sentences_rejected_incomplete"] += 1
                continue
            uid = sentence.get("uid")
            if uid is not None and uid in seen_uids:
                stats["sentences_duplicate_uid"] += 1
                continue
            seen_uids.add(uid)
            paper_line, paper = papers.get(str(sentence["paper_id"]), (0, None))
            if paper is not None and paper.get("retraction"):
                stats["sentences_from_retracted_papers"] += 1
            attributes = {"interaction_id": pair_id, "release": release, "sentence": sentence, "paper": paper,
                          "extraction": "automatic (SUPP.AI model); an interaction mention, not a confirmed interaction"}  # fmt: skip
            relations.append(writer.relation(writer.entity_id("supplement", supplement), PREDICATE,
                                              writer.entity_id("drug", drug), attributes, records["sentences"],
                                              [line] + ([paper_line] if paper_line else [])))  # fmt: skip
    stats["relations_stored"] = writer.upsert_relations(relations)

    # 6. stale rows of earlier releases (only after an error-free run)
    delete_stale(ctx, SOURCE, {e["id"] for e in entities}, {r["id"] for r in relations})
    ctx.session.flush()
