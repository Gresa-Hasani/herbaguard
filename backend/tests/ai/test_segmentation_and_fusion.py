"""Segmentation (never splits a sentence or its qualifiers) and Reciprocal Rank Fusion."""

from __future__ import annotations

import pytest

from herbaguard.ai.fusion import rrf
from herbaguard.ai.indexing.segmenter import (
    StrategyParams,
    segment,
    sentence_spans,
    sentence_window,
    strategy_version,
    whole_chunk,
)

# Real EU monograph wording (EMA/HMPC/321097/2012, Ginkgo folium, section 4.5)
GINKGO = (
    "Concomitant use of G. biloba preparations and efavirenz is not recommended; plasma concentrations "
    "of efavirenz may be decreased because of induction of CYP3A4 (see also section 4.4). "
    "An interaction study with talinolol indicates that G. biloba may inhibit P-glycoprotein at the "
    "intestinal level.\n\nThis may give rise to increased exposure of drugs markedly affected by "
    "P-glycoprotein in the intestine such as dabigatran etexilate."
)


def texts(text: str, spans: list[tuple[int, int]]) -> list[str]:
    return [text[s:e] for s, e in spans]


def test_sentences_keep_abbreviations_semicolons_and_qualifiers() -> None:
    sentences = texts(GINKGO, sentence_spans(GINKGO))
    assert len(sentences) == 3
    assert sentences[0].startswith("Concomitant use of G. biloba")
    assert (
        "is not recommended; plasma concentrations" in sentences[0]
    )  # semicolon is not a boundary
    assert sentences[1].endswith("may inhibit P-glycoprotein at the intestinal level.")


def test_offsets_point_into_the_original_text() -> None:
    for start, end in sentence_window(GINKGO, StrategyParams(max_chars=200, overlap_sentences=1)):
        assert GINKGO[start:end] == GINKGO[start:end].strip()
        assert GINKGO[start:end] in GINKGO


def test_window_never_splits_a_sentence_and_overlaps() -> None:
    spans = sentence_window(GINKGO, StrategyParams(max_chars=200, overlap_sentences=1))
    pieces = texts(GINKGO, spans)
    sentences = texts(GINKGO, sentence_spans(GINKGO))
    for piece in pieces:  # each segment is a run of whole sentences
        assert any(piece.startswith(s) for s in sentences)
        assert any(piece.endswith(s) for s in sentences)
    assert len(pieces) == 3  # sentences are 182, 112 and 132 chars: no two fit in 200
    assert sentences[1] in pieces[0] or sentences[1] in pieces[1]


def test_long_sentence_becomes_its_own_segment() -> None:
    long = "Hyperici herba preparations induce " + "CYP3A4, " * 60 + "and P-glycoprotein."
    spans = sentence_window(long, StrategyParams(max_chars=100, overlap_sentences=0))
    assert texts(long, spans) == [long]


def test_whole_chunk_and_empty_text() -> None:
    assert whole_chunk("  text.  ", StrategyParams()) == [(2, 7)]
    assert sentence_window("   ", StrategyParams()) == []
    assert whole_chunk("", StrategyParams()) == []


def test_strategy_version_changes_with_parameters() -> None:
    a = strategy_version("sentence_window", StrategyParams(max_chars=1200, overlap_sentences=1))
    b = strategy_version("sentence_window", StrategyParams(max_chars=800, overlap_sentences=1))
    assert a != b and a.startswith("v1-")
    with pytest.raises(ValueError, match="Unknown segmentation strategy"):
        segment("x.", "no_such_strategy", StrategyParams())


def test_rrf_combines_ranks_and_breaks_ties_deterministically() -> None:
    fused = rrf({"keyword": ["a", "b", "c"], "semantic": ["c", "a", "d"]}, k=60)
    assert [f.key for f in fused] == ["a", "c", "b", "d"]
    assert fused[0].ranks == {"keyword": 1, "semantic": 2}
    tie = rrf({"x": ["b"], "y": ["a"]}, k=60)
    assert [f.key for f in tie] == ["a", "b"]  # equal score → ordered by key
    assert rrf({"x": ["b"], "y": ["a"]}, k=60) == tie  # identical input, identical output


def test_rrf_weights_multipliers_and_duplicates() -> None:
    weighted = rrf({"keyword": ["a"], "semantic": ["b"]}, k=60, weights={"semantic": 2.0})
    assert weighted[0].key == "b"
    boosted = rrf({"keyword": ["a", "b"]}, k=60, multipliers={"b": 1.5})
    assert boosted[0].key == "b"
    dup = rrf({"keyword": ["a", "a", "b"]}, k=60)
    assert dup[0].ranks == {"keyword": 1} and dup[1].ranks == {"keyword": 2}
    assert rrf({}, k=60) == []
