"""Recognise enzyme and transporter names in source text and map them to HerbaGuard target symbols.

Symbols are the keys of ``data/curated/targets.yaml``: CYP enzymes by their CYP name (``CYP3A4``,
and ``CYP3A`` for the FDA's CYP3A4/5 grouping), transporters by their HGNC gene symbol
(``ABCB1`` = P-gp). The mapping is a fixed table, not fuzzy matching: an unknown token is never
guessed, it is left in the text for the caller to report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Transporter spellings seen in the FDA table and EMA monographs → gene symbols.
# "OATP1B" without a number is used by FDA for "OATP1B transporters" (OATP1B1 and OATP1B3).
TRANSPORTER_ALIASES: dict[str, tuple[str, ...]] = {
    "p-glycoprotein": ("ABCB1",),
    "p-gp": ("ABCB1",),
    "pgp": ("ABCB1",),
    "bcrp": ("ABCG2",),
    "oatp1b1": ("SLCO1B1",),
    "oatp1b3": ("SLCO1B3",),
    "oatp1b": ("SLCO1B1", "SLCO1B3"),
    "oat1": ("SLC22A6",),
    "oat3": ("SLC22A8",),
    "mate1": ("SLC47A1",),
    "mate2-k": ("SLC47A2",),
    "mate-2k": ("SLC47A2",),
    "mate2k": ("SLC47A2",),
    "oct2": ("SLC22A2",),
}

CYP_ISOFORMS = ("1A2", "2B6", "2C8", "2C9", "2C19", "2D6", "3A4", "3A5", "3A")

# Longest alternatives first so that e.g. "OATP1B1" is not read as "OATP1B" + "1" and "2C19"
# is not read as "2C1…". No right-hand word boundary: FDA cells sometimes glue footnote numbers
# to a token ("1A220" = 1A2 + footnote 20) when the <sup> markup is lost.
_TRANSPORTER_PATTERN = "|".join(
    re.escape(alias) for alias in sorted(TRANSPORTER_ALIASES, key=len, reverse=True)
)
_CYP_PATTERN = "|".join(sorted(CYP_ISOFORMS, key=len, reverse=True))
_LEFT = r"(?<![A-Za-z0-9-])"

_CYP_PREFIXED = re.compile(_LEFT + r"CYP\s?(" + _CYP_PATTERN + r")", re.IGNORECASE)
_CYP_ANY = re.compile(_LEFT + r"(?:CYP\s?)?(" + _CYP_PATTERN + r")", re.IGNORECASE)
_TRANSPORTER = re.compile(_LEFT + r"(" + _TRANSPORTER_PATTERN + r")", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TargetMention:
    verbatim: str  # text as written in the source, e.g. "P-glycoprotein", "3A", "OATP1B"
    symbols: tuple[str, ...]  # HerbaGuard target symbols, e.g. ("ABCB1",), ("CYP3A",)
    start: int
    end: int
    system: str  # "cyp" | "transporter"


def find_targets(text: str, *, cyp_prefix_required: bool = True) -> list[TargetMention]:
    """All enzyme/transporter mentions in ``text``, in order.

    ``cyp_prefix_required``: free text (EMA monographs) must say "CYP3A4"; the FDA table's CYP
    columns use bare isoform names ("3A", "2C19").
    """
    found: list[TargetMention] = []
    cyp = _CYP_PREFIXED if cyp_prefix_required else _CYP_ANY
    for match in cyp.finditer(text):
        isoform = match.group(1).upper()
        found.append(
            TargetMention(match.group(0), (f"CYP{isoform}",), match.start(), match.end(), "cyp")
        )
    for match in _TRANSPORTER.finditer(text):
        if any(m.start <= match.start() < m.end for m in found):
            continue
        symbols = TRANSPORTER_ALIASES[match.group(1).lower()]
        found.append(
            TargetMention(match.group(0), symbols, match.start(), match.end(), "transporter")
        )
    return sorted(found, key=lambda m: m.start)


def remove_mentions(text: str, mentions: list[TargetMention]) -> str:
    """``text`` with the mentions blanked out (used to detect unparsed leftovers)."""
    out = text
    for mention in sorted(mentions, key=lambda m: m.start, reverse=True):
        out = out[: mention.start] + " " + out[mention.end :]
    return out
