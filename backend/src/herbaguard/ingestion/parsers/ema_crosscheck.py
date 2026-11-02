"""Independent verification of EMA monograph extraction against the original PDF.

The parser (pdfplumber/pdfminer word coordinates) is checked against **PDFium** (pypdfium2), a
separate PDF engine with its own text extraction. For every required section and every use
category column, PDFium extracts the text inside the column's rectangle between the section
heading and the next heading (across pages, excluding each page's footnote/footer zone). The
two token sequences are compared:

* **recall** — share of PDFium tokens present in the parser output (missed text lowers it);
* **precision** — share of parser tokens present in PDFium's text (text from the wrong column
  or section lowers it);
* **sequence ratio** — difflib similarity of the token *order* (mixed columns lower it even
  when the bag of words is identical).

Tokens are lower-case letter runs and digit runs, so superscript markers ("interaction6" vs.
"interaction [6]"), hyphenation and punctuation do not cause false mismatches.
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

import pypdfium2 as pdfium

from herbaguard.domain.enums import UseCategory
from herbaguard.ingestion.parsers.ema_monograph import REQUIRED_SECTIONS, Monograph

THRESHOLD_RECALL = 0.98
THRESHOLD_PRECISION = 0.98
THRESHOLD_SEQUENCE = 0.95
EDGE_MARGIN = 3.0  # pt

_TOKEN = re.compile(r"[a-z]+|\d+")
_COLUMN_HEADERS = {"well-established use", "traditional use"}


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).replace("￾", "-").lower()
    return _TOKEN.findall(text)


@dataclass(frozen=True, slots=True)
class ColumnCheck:
    section: str
    use_category: UseCategory
    parser_tokens: int
    reference_tokens: int
    recall: float
    precision: float
    sequence_ratio: float

    @property
    def status(self) -> str:
        if self.parser_tokens == 0 and self.reference_tokens == 0:
            return "both_empty"
        ok = (
            self.recall >= THRESHOLD_RECALL
            and self.precision >= THRESHOLD_PRECISION
            and self.sequence_ratio >= THRESHOLD_SEQUENCE
        )
        return "verified" if ok else "mismatch"


def _overlap(a: list[str], b: list[str]) -> int:
    return sum((Counter(a) & Counter(b)).values())


def _bounded_text(
    page: pdfium.PdfPage, left: float, right: float, top: float, bottom: float, height: float
) -> str:
    """Text inside a rectangle given in top-left coordinates (pdfplumber convention)."""
    if bottom <= top:
        return ""
    text_page = page.get_textpage()
    try:
        raw = text_page.get_text_bounded(
            left=left, bottom=height - bottom, right=right, top=height - top
        )
    finally:
        text_page.close()
    lines = [ln for ln in raw.splitlines() if ln.strip().lower() not in _COLUMN_HEADERS]
    return "\n".join(lines)


def crosscheck(
    pdf_bytes: bytes, monograph: Monograph, sections: tuple[str, ...] = REQUIRED_SECTIONS
) -> list[ColumnCheck]:
    """Compare parser output with PDFium for each required section and covered column."""
    if not monograph.has_use_columns or monograph.column_split_x is None:
        return []
    split_x = monograph.column_split_x
    ordered = monograph.sections
    results: list[ColumnCheck] = []
    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    try:
        for number in sections:
            section = monograph.section(number)
            if section is None:
                continue
            index = ordered.index(section)
            nxt = ordered[index + 1] if index + 1 < len(ordered) else None
            end_page = nxt.first_page if nxt else monograph.page_count
            for category, (x_left, x_right) in (
                (UseCategory.WELL_ESTABLISHED, (0.0, split_x)),
                (UseCategory.TRADITIONAL, (split_x, None)),
            ):
                reference: list[str] = []
                for page_number in range(section.first_page, end_page + 1):
                    width, height = monograph.page_sizes[page_number]
                    # Edge margins: a rectangle edge that cuts through a neighbouring line makes
                    # PDFium return only the glyph ascenders of that line (e.g. "42Pld thd" for
                    # "4.2 Posology and ..."), which would count as false misses.
                    top = (
                        (section.body_top + EDGE_MARGIN)
                        if page_number == section.first_page
                        else 0.0
                    )
                    bottom = monograph.content_bottom.get(page_number, height) - EDGE_MARGIN
                    if nxt is not None and page_number == nxt.first_page:
                        bottom = min(bottom, nxt.heading_top - EDGE_MARGIN)
                    right = x_right if x_right is not None else width
                    reference += tokens(
                        _bounded_text(pdf[page_number - 1], x_left, right, top, bottom, height)
                    )
                parsed = tokens(section.texts.get(category, ""))
                overlap = _overlap(parsed, reference)
                results.append(
                    ColumnCheck(
                        section=number,
                        use_category=category,
                        parser_tokens=len(parsed),
                        reference_tokens=len(reference),
                        recall=overlap / len(reference) if reference else 1.0,
                        precision=overlap / len(parsed) if parsed else 1.0,
                        sequence_ratio=SequenceMatcher(
                            None, parsed, reference, autojunk=False
                        ).ratio()
                        if parsed or reference
                        else 1.0,
                    )
                )
    finally:
        pdf.close()
    return results


def document_token_coverage(pdf_bytes: bytes, monograph: Monograph) -> float:
    """Share of all PDFium tokens in the document accounted for by *some* parser output
    (sections, headings, front matter, footnotes or discarded lines). Below ~0.99 means text
    was lost somewhere."""
    accounted: list[str] = tokens(monograph.front_matter)
    for section in monograph.sections:
        accounted += tokens(f"{section.number} {section.title}")
        for text in section.texts.values():
            accounted += tokens(text)
    for footnote in monograph.footnotes.values():
        accounted += tokens(f"{footnote.number} {footnote.text}")
    for line in monograph.discarded:
        accounted += tokens(line.text)
    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    try:
        reference: list[str] = []
        for page in pdf:
            text_page = page.get_textpage()
            try:
                reference += tokens(text_page.get_text_range())
            finally:
                text_page.close()
    finally:
        pdf.close()
    return _overlap(accounted, reference) / len(reference) if reference else 1.0
