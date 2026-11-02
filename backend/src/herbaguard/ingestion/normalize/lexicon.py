"""Matching curated drug / drug-class phrases in text (longest match first, word boundaries)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from herbaguard.ingestion.curation import Lexicon

Kind = Literal["drug", "class", "unmapped"]


@dataclass(frozen=True, slots=True)
class LexiconHit:
    kind: Kind
    key: str  # drug name (RxNorm ingredient) | class label | unmapped phrase
    atc: tuple[str, ...]
    matched_text: str  # exact text as it appears in the source
    start: int
    end: int


class LexiconMatcher:
    def __init__(self, lexicon: Lexicon) -> None:
        entries: list[tuple[str, Kind, str, tuple[str, ...]]] = []
        for drug in lexicon.drugs:
            entries += [(p, "drug", drug.name, ()) for p in drug.patterns]
        for cls in lexicon.classes:
            entries += [(p, "class", cls.label, tuple(cls.atc)) for p in cls.patterns]
        for item in lexicon.unmapped:
            entries.append((item.phrase, "unmapped", item.phrase, ()))
        # Longest patterns first so "coumarin-type anticoagulants" wins over "anticoagulants".
        entries.sort(key=lambda e: len(e[0]), reverse=True)
        self._entries = [
            (re.compile(rf"(?<![\w-]){re.escape(p)}(?![\w-])", re.IGNORECASE), kind, key, atc)
            for p, kind, key, atc in entries
        ]

    def find(self, text: str) -> list[LexiconHit]:
        hits: list[LexiconHit] = []
        taken: list[tuple[int, int]] = []
        for pattern, kind, key, atc in self._entries:
            for match in pattern.finditer(text):
                span = match.span()
                if any(span[0] < end and start < span[1] for start, end in taken):
                    continue
                taken.append(span)
                hits.append(LexiconHit(kind, key, atc, match.group(0), span[0], span[1]))
        return sorted(hits, key=lambda h: h.start)
