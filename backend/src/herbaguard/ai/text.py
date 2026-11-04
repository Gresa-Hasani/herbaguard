"""Small, deterministic text helpers shared by retrieval, guardrails and the extractive answer."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# English function words plus question words that carry no retrieval signal.
STOPWORDS = frozenset(
    """
    a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if in into is it
    its itself just me more most my myself no nor not now of off on once only or other our ours
    out over own same she should so some such than that the their theirs them themselves then
    there these they this those through to too under until up very was we were what when where
    which while who whom why will with would you your yours yourself yourselves
    take taking taken use using used safe ok okay together combine combined combining while
    tell know please much many may might
    """.split()  # noqa: SIM905 - a word list is easier to maintain as prose
)

_WORD = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(\[])")
# Abbreviations that must not end a sentence ("St. John's wort", "e.g. warfarin").
_ABBREVIATIONS = ("St.", "e.g.", "i.e.", "approx.", "Fig.", "No.", "vs.", "Dr.", "ca.")


def fold(text: str) -> str:
    """Lower-case, strip accents, unify apostrophes and collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    return " ".join(text.lower().split())


def content_terms(text: str) -> list[str]:
    """Distinct content words (order kept) used for full-text queries and overlap scoring."""
    seen: dict[str, None] = {}
    for word in _WORD.findall(fold(text)):
        word = word.removesuffix("'s")
        if len(word) < 3 or word in STOPWORDS or word.isdigit():
            continue
        seen.setdefault(word, None)
    return list(seen)


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences without breaking on common abbreviations."""
    protected = text
    for i, abbreviation in enumerate(_ABBREVIATIONS):
        protected = protected.replace(abbreviation, f"\x00{i}\x00")
    parts = []
    for paragraph in re.split(r"\n\s*\n", protected):
        parts.extend(_SENTENCE_END.split(" ".join(paragraph.split())))
    out = []
    for part in parts:
        for i, abbreviation in enumerate(_ABBREVIATIONS):
            part = part.replace(f"\x00{i}\x00", abbreviation)
        part = part.strip()
        if part:
            out.append(part)
    return out


@dataclass(frozen=True, slots=True)
class TermMatch:
    """A known name found in free text."""

    name: str  # the name as stored (used to resolve the entity)
    key: str  # entity key the name belongs to (e.g. pharmaceutical name, drug RxCUI)
    start: int
    end: int


def spot_terms(text: str, names: Mapping[str, str]) -> list[TermMatch]:
    """Find known names (``name -> entity key``) in ``text`` on word boundaries.

    Longer names win over names they contain ("Panax ginseng" over "ginseng"); overlapping
    matches are dropped; names shorter than 3 characters are ignored. Matching is case- and
    accent-insensitive; the returned offsets refer to the folded text.
    """
    folded = fold(text)
    candidates: list[TermMatch] = []
    for name, key in names.items():
        needle = fold(name)
        if len(needle) < 3:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
        candidates.extend(
            TermMatch(name=name, key=key, start=m.start(), end=m.end())
            for m in re.finditer(pattern, folded)
        )
    candidates.sort(key=lambda m: (-(m.end - m.start), m.start))
    chosen: list[TermMatch] = []
    for match in candidates:
        if all(match.end <= c.start or match.start >= c.end for c in chosen):
            chosen.append(match)
    return sorted(chosen, key=lambda m: m.start)


def unique_keys(matches: Iterable[TermMatch]) -> list[str]:
    return list(dict.fromkeys(m.key for m in matches))


def truncate(text: str, limit: int) -> str:
    """Cut at a word boundary and mark the cut with an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return f"{cut} …"
