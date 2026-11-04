"""Extractive answer (pure): quoted source sentences, no generation.

Used when no LLM is configured or reachable, when the user asks for it, and when a generated
answer fails citation validation twice. Every sentence is verbatim from a retrieved passage and
cites it, so this mode cannot fabricate content.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from herbaguard.ai.text import content_terms, split_sentences, truncate


@dataclass(frozen=True, slots=True)
class ExtractivePassage:
    marker: str
    title: str
    text: str
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class Quote:
    marker: str
    sentence: str
    score: float


def _stem(word: str) -> str:
    """Crude plural folding so "contraceptives" matches "contraceptive"."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _score(sentence: str, terms: set[str], entity_terms: set[str]) -> float:
    words = {_stem(w) for w in content_terms(sentence)}
    if not words:
        return 0.0
    overlap = len(words & terms)
    entity = len(words & entity_terms)
    return overlap + 1.5 * entity


def best_quotes(
    question: str,
    passages: Sequence[ExtractivePassage],
    *,
    entity_names: Sequence[str] = (),
    max_quotes: int = 4,
    per_passage: int = 2,
    max_sentence_chars: int = 400,
) -> list[Quote]:
    """Pick the sentences that share most content words with the question and entity names."""
    terms = {_stem(t) for t in content_terms(question)}
    entity_terms = {_stem(t) for name in entity_names for t in content_terms(name)}
    quotes: list[Quote] = []
    for rank, passage in enumerate(passages):
        scored = []
        for sentence in split_sentences(passage.text):
            if len(sentence) < 20:
                continue
            score = _score(sentence, terms, entity_terms)
            if passage.pinned:
                score += 2.0
            score -= rank * 0.05  # prefer better-ranked passages on ties
            scored.append(Quote(passage.marker, truncate(sentence, max_sentence_chars), score))
        scored.sort(key=lambda q: -q.score)
        quotes.extend(q for q in scored[:per_passage] if q.score > 0)
    quotes.sort(key=lambda q: -q.score)
    chosen = quotes[:max_quotes]
    if not chosen and passages:  # nothing overlaps: show the opening of the top passage
        first = split_sentences(passages[0].text)
        if first:
            chosen = [Quote(passages[0].marker, truncate(first[0], max_sentence_chars), 0.0)]
    return chosen


def compose(quotes: Sequence[Quote], *, lead: str | None = None) -> str:
    lines = [lead] if lead else ["The retrieved sources say:"]
    lines.extend(f"“{q.sentence}” [{q.marker}]" for q in quotes)
    return "\n".join(lines)
