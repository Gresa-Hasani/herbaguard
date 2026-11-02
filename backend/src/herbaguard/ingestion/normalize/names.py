"""Scientific-name and identifier normalisation."""

from __future__ import annotations

import re
import unicodedata

# Author glued to the epithet in EMA exports, e.g. "Hypericum perforatumL.",
# "Zingiber officinaleRoscoe" or "C. laevigata(Poir.) DC.": a lower-case letter directly
# followed by an upper-case letter or an opening parenthesis.
_GLUED_AUTHOR = re.compile(r"(?<=[a-z])(?=[A-Z(])")
_BINOMIAL = re.compile(r"^([A-Z][a-z-]+)\s+([a-z][a-z-]+)(?:\s+(.*))?$")


def clean_name(raw: str) -> str:
    """Normalise whitespace (incl. non-breaking spaces) and split glued author abbreviations."""
    text = unicodedata.normalize("NFKC", raw).replace("\xa0", " ")
    text = _GLUED_AUTHOR.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_binomial(raw: str) -> str | None:
    """'Hypericum perforatum L.' -> 'Hypericum perforatum'; None if not a binomial."""
    match = _BINOMIAL.match(clean_name(raw))
    return f"{match.group(1)} {match.group(2)}" if match else None


def split_ema_botanical_names(raw: str) -> list[str]:
    """EMA lists several taxa separated by ';' and abbreviates repeated genera ('C. laevigata')."""
    names: list[str] = []
    genus: str | None = None
    for part in re.split(r";", clean_name(raw)):
        part = part.strip()
        part = re.sub(r"\(syn\..*?\)\s*$", "", part).strip()
        if not part:
            continue
        abbreviated = re.match(r"^([A-Z])\.\s+([a-z].*)$", part)
        if abbreviated and genus and genus.startswith(abbreviated.group(1)):
            part = f"{genus} {abbreviated.group(2)}"
        first = part.split()[0]
        if not first.endswith("."):
            genus = first
        names.append(part)
    return names


def normalize_for_lookup(name: str) -> str:
    """Lower-case, single-spaced, ASCII-folded key for name lookups."""
    text = unicodedata.normalize("NFKD", clean_name(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text.lower()).strip()


def format_wfo_id(value: int | str) -> str:
    """728093 / '728093' / 'wfo-0000728093' -> 'wfo-0000728093'."""
    text = str(value).strip()
    if text.startswith("wfo-"):
        text = text[4:]
    if not text.isdigit():
        msg = f"Not a WFO identifier: {value!r}"
        raise ValueError(msg)
    return f"wfo-{int(text):010d}"
