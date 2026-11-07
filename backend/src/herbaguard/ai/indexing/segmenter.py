"""Segmentation strategies: cut retrieval segments out of stored chunk text.

Pure functions; a segment is a ``(start, end)`` character range in the chunk text, so no text is
copied and every segment maps back to its chunk, evidence item and provenance.

Rules shared by all strategies (scientific integrity):

* A sentence is never split. Qualifiers, conditions and negations inside a sentence ("may inhibit",
  "is not recommended; plasma concentrations ... may be decreased") therefore always stay together.
  Semicolons are *not* sentence boundaries here.
* A sentence longer than the size limit becomes its own segment (it is not cut).
* Paragraph breaks are boundaries for sentence detection, not for packing.

Strategies are selected per source by configuration (``segment_strategy`` and
``segment_strategy_by_source``); a new source needs no code change unless it needs a new strategy,
which is registered in ``STRATEGIES``. The strategy *version* includes its parameters, so changing
a parameter makes existing segments stale and they are rebuilt by the indexer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from herbaguard.ingestion.normalize.statements import _ABBREVIATIONS

Span = tuple[int, int]

_SENTENCE_END = re.compile(r"([.!?])\s+(?=[A-Z0-9(\[‘'\"•\-])")
_PARAGRAPH = re.compile(r"\S(?:.*?\S)?(?=\s*\n\s*\n|\s*\Z)", re.DOTALL)


def sentence_spans(text: str) -> list[Span]:
    """Sentence ranges in ``text`` (whitespace trimmed), in order."""
    spans: list[Span] = []
    for paragraph in _PARAGRAPH.finditer(text):
        base, body = paragraph.start(), paragraph.group(0)
        start = 0
        for match in _SENTENCE_END.finditer(body):
            end = match.end(1)
            last_word = re.findall(r"([A-Za-z.]+)[.!?]$", body[start:end])
            token = last_word[0].lower().rstrip(".") if last_word else ""
            if match.group(1) == "." and (token in _ABBREVIATIONS or re.fullmatch(r"[a-z]", token)):
                continue
            spans.append((base + start, base + end))
            start = match.end()
        if body[start:].strip():
            spans.append((base + start, base + len(body)))
    return spans


@dataclass(frozen=True, slots=True)
class StrategyParams:
    max_chars: int = 1200
    overlap_sentences: int = 1


def sentence_window(text: str, params: StrategyParams) -> list[Span]:
    """Pack whole sentences into segments of at most ``max_chars``; consecutive segments share
    ``overlap_sentences`` sentences so a statement and its following qualifier are never only
    found apart."""
    sentences = sentence_spans(text)
    if not sentences:
        return []
    segments: list[Span] = []
    i = 0
    while i < len(sentences):
        start = sentences[i][0]
        j = i
        while j + 1 < len(sentences) and sentences[j + 1][1] - start <= params.max_chars:
            j += 1
        segments.append((start, sentences[j][1]))
        if j + 1 >= len(sentences):
            break
        i = max(j + 1 - params.overlap_sentences, i + 1)
    return segments


def whole_chunk(text: str, params: StrategyParams) -> list[Span]:
    """The whole chunk as one segment (for short, self-contained records)."""
    stripped = text.strip()
    if not stripped:
        return []
    start = text.index(stripped[0])
    return [(start, start + len(stripped))]


STRATEGIES: dict[str, tuple[str, Callable[[str, StrategyParams], list[Span]]]] = {
    # name: (code version, function)
    "sentence_window": ("1", sentence_window),
    "whole_chunk": ("1", whole_chunk),
}


def strategy_version(name: str, params: StrategyParams) -> str:
    code_version, _ = STRATEGIES[name]
    if name == "whole_chunk":
        return f"v{code_version}"
    return f"v{code_version}-max{params.max_chars}-ov{params.overlap_sentences}"


def segment(text: str, name: str, params: StrategyParams) -> list[Span]:
    if name not in STRATEGIES:
        msg = f"Unknown segmentation strategy '{name}'. Known: {', '.join(sorted(STRATEGIES))}."
        raise ValueError(msg)
    return STRATEGIES[name][1](text, params)
