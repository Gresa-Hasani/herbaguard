"""Post-generation citation validation (pure).

A generated answer is accepted only if every citation marker resolves to a passage that was
actually retrieved, at least one passage is cited, most factual sentences carry a citation, and
the text contains no reference-like strings (PMID, DOI, URL) that are not in the passages.
Otherwise the service regenerates once and then falls back to the extractive answer.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field

from herbaguard.ai.text import split_sentences

# [S1], [S1, S3], [S1][S2], [s2], [S 4]
_GROUP = re.compile(r"\[\s*[Ss]\s*\d+(?:\s*[,;]\s*[Ss]?\s*\d+)*\s*\]")
_NUMBER = re.compile(r"\d+")
# Bracketed numerals the model may use instead ("[1]") — treated as unresolvable citations.
_BARE_NUMERIC = re.compile(r"\[\s*\d+(?:\s*[,;-]\s*\d+)*\s*\]")
_PMID = re.compile(r"\bPMID:?\s*(\d{5,9})\b", re.IGNORECASE)
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\]\)]+)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s\]\)]+", re.IGNORECASE)

# Sentences that need no citation: refusals, referral and "sources do not say" statements.
_NO_CITATION_NEEDED = re.compile(
    r"\b(?:do(?:es)? not (?:answer|say|mention|address|contain|provide|cover|report)|"
    r"no (?:information|data|evidence|passage|source)|not (?:covered|addressed|enough)|"
    r"(?:talk|speak) (?:to|with) (?:your|a) (?:doctor|pharmacist)|"
    r"(?:ask|consult) (?:your|a) (?:doctor|pharmacist|healthcare)|"
    r"not medical advice|cannot (?:give|provide|recommend))\b",
    re.IGNORECASE,
)

MIN_CITED_SENTENCE_SHARE = 0.6


@dataclass(frozen=True, slots=True)
class CitationCheck:
    ok: bool
    cited: list[str]  # markers used, e.g. ["S1", "S3"], in order of first use
    unknown: list[str]  # markers that do not resolve to a retrieved passage
    issues: list[str] = field(default_factory=list)
    uncited_sentences: int = 0
    factual_sentences: int = 0


def markers_in(text: str) -> list[str]:
    found: dict[str, None] = {}
    for group in _GROUP.findall(text):
        for number in _NUMBER.findall(group):
            found.setdefault(f"S{int(number)}", None)
    return list(found)


def normalise_markers(text: str) -> str:
    """Rewrite citation groups to the canonical form ``[S1][S3]``."""

    def repl(match: re.Match[str]) -> str:
        return "".join(f"[S{int(n)}]" for n in _NUMBER.findall(match.group(0)))

    return _GROUP.sub(repl, text)


def check_answer(text: str, allowed: Collection[str], *, reference_text: str = "") -> CitationCheck:
    """Validate ``text`` against the passage markers in ``allowed``.

    ``reference_text`` is the concatenated passage text; PMIDs, DOIs and URLs in the answer must
    appear there, otherwise they are treated as fabricated references.
    """
    allowed_set = set(allowed)
    issues: list[str] = []
    body = text.strip()
    if not body:
        return CitationCheck(False, [], [], ["empty answer"])

    cited = markers_in(body)
    unknown = [m for m in cited if m not in allowed_set]
    valid = [m for m in cited if m in allowed_set]
    if unknown:
        issues.append(f"citations that match no passage: {', '.join(unknown)}")
    if not valid:
        issues.append("no passage is cited")
    if _BARE_NUMERIC.search(body):
        issues.append("numeric citations like [1] are not allowed; use [S1]")

    reference = reference_text.lower()
    for kind, pattern in (("PMID", _PMID), ("DOI", _DOI), ("URL", _URL)):
        for value in pattern.findall(body):
            if value.lower().rstrip(".,;") not in reference:
                issues.append(f"{kind} not present in the passages: {value}")

    issues.extend(f"asserts safety: '{claim}'" for claim in safety_claims(body))

    factual = uncited = 0
    for sentence in split_sentences(_GROUP.sub(lambda m: f" {m.group(0)}", body)):
        if len(sentence) < 25 or _NO_CITATION_NEEDED.search(sentence):
            continue
        factual += 1
        if not _GROUP.search(sentence):
            uncited += 1
    if factual and (factual - uncited) / factual < MIN_CITED_SENTENCE_SHARE:
        issues.append(f"{uncited} of {factual} factual sentences have no citation")

    return CitationCheck(
        ok=not issues,
        cited=valid,
        unknown=unknown,
        issues=issues,
        uncited_sentences=uncited,
        factual_sentences=factual,
    )


_SAFETY_CLAIM = re.compile(
    r"\b(?:is|are|it'?s|that'?s|considered|completely|totally|perfectly) (?:generally )?safe to "
    r"(?:take|use|combine)\b|\bno (?:risk|danger) (?:of|in|when)\b|\bthere is no interaction\b",
    re.IGNORECASE,
)


def safety_claims(text: str) -> list[str]:
    """Phrases that assert safety. HerbaGuard never infers safety from missing evidence."""
    claims = []
    for match in _SAFETY_CLAIM.finditer(text):
        before = text[max(0, match.start() - 25) : match.start()].lower()
        if re.search(
            r"\b(?:whether|if|not|cannot say|can'?t say|doesn'?t mean|does not mean)\b", before
        ):
            continue  # "whether it is safe to take", "does not mean it is safe to combine"
        if re.match(r"(?:is|are|it'?s|that'?s) not\b", match.group(0), re.IGNORECASE):
            continue
        claims.append(match.group(0))
    return claims


_CLASS_MENTION = re.compile(r"\bclass(?:es)?\s+([A-E])\b")


def class_mismatches(text: str, computed: Collection[str]) -> list[str]:
    """Interaction-class letters the answer mentions that HerbaGuard did not compute.

    The class is decided by deterministic rules; a generated answer may repeat it but never
    change it (ADR-003).
    """
    allowed = set(computed)
    return sorted({m for m in _CLASS_MENTION.findall(text) if m not in allowed})
