"""Parser for EMA/HMPC European Union herbal monograph PDFs.

Layout facts (checked on all 16 curated monographs, 2026-11-02):

* Sections 2–5 are a two-column table: *Well-established use* (left) and *Traditional use*
  (right). The right column starts at x ≈ 280–306 pt on an A4 page (595 pt wide); the header
  row "Well-established use | Traditional use" gives the exact boundary per document.
* Body text is 9 pt. Smaller text is one of: running page footers (7 pt), footnotes
  (7.6 pt text with 5–6.5 pt numbers), superscript footnote markers inside body text or
  headings (e.g. "interaction⁶"), subscripts in pharmacokinetic text (C_max, t½), and
  publisher boilerplate on page 1.
* Long section headings run across the column boundary.

Design rules:

* **Nothing is dropped silently.** Every extracted line ends up in exactly one place: a section
  column, a section heading, the front matter, a footnote, or ``discarded`` with a reason.
* Unexpected situations produce typed ``ExtractionWarning``s, which ingestion stores as
  ``data_quality_issue`` rows.
* A missing or empty section is reported as such; it is never interpreted as "no interactions"
  or "no warnings".

``parse_pages`` is pure (word coordinates in, structured monograph out) so it can be tested
without PDF files; ``parse_monograph`` adds the pdfplumber-specific extraction.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pdfplumber

from herbaguard.domain.enums import UseCategory

PARSER_VERSION = "ema_monograph_v2"

# Sections HerbaGuard relies on; their absence is reported, never treated as "nothing to say".
REQUIRED_SECTIONS: tuple[str, ...] = ("4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8")

BODY_FONT_MIN = 8.4  # pt; body text is 9 pt, headings 9–14 pt
LINE_TOLERANCE = 3.0  # pt; words within this vertical distance form one line
SMALL_WORD_ATTACH_DISTANCE = 7.0  # pt; superscripts/subscripts sit this close to their line

_SUB_HEADING = re.compile(r"^(?P<top>[1-9])\.(?P<sub>[0-9]{1,2})\.?\s+(?P<title>[A-Z].*)$")
_TOP_HEADING = re.compile(r"^(?P<top>[1-9])\.\s+(?P<title>[A-Z].*)$")
_PAGE_NUMBER = re.compile(r"\bPage\s+\d+\s*/\s*\d+\b")
_DOC_NUMBER = re.compile(r"\b((?:EMA|EMEA)/HMPC/\d+/\d{4}(?:\s+Rev\.?\s*\d+)?)\b")
_DATE = re.compile(r"^\s*(\d{1,2} [A-Z][a-z]+ \d{4})\s*$")
_FOOTNOTE_REF = re.compile(r"\[(\d{1,2})\]")
_BOILERPLATE = re.compile(
    r"(Official address|Address for visits|Send (us )?a question|Telephone|Facsimile|"
    r"Churchill Place|Domenico Scarlattilaan|An agency of the European Union|"
    r"© European Medicines Agency|Reproduction is authorised|^[●\s]+$)"
)


# --------------------------------------------------------------------------- data classes


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float


@dataclass(frozen=True, slots=True)
class PageInput:
    number: int
    width: float
    height: float
    words: list[Word]
    multi_column_tables: int = 0  # tables with more than two columns (pdfplumber)


@dataclass(frozen=True, slots=True)
class ExtractionWarning:
    code: str
    message: str
    page: int | None = None
    section: str | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class DiscardedLine:
    page: int
    reason: str  # running_footer | page_number | publisher_boilerplate | column_header
    text: str


@dataclass(slots=True)
class Footnote:
    number: str
    page: int
    text: str


@dataclass(slots=True)
class MonographSection:
    number: str  # "4.5" (sub-section) or "4" (top-level section)
    title: str
    first_page: int
    last_page: int
    texts: dict[UseCategory, str] = field(default_factory=dict)
    footnote_refs: list[str] = field(default_factory=list)
    # Geometry for verification: the heading's top and the y where body text starts (pt from
    # the top of ``first_page``).
    heading_top: float = 0.0
    body_top: float = 0.0

    @property
    def level(self) -> int:
        return 2 if "." in self.number else 1

    @property
    def spans_pages(self) -> bool:
        return self.last_page > self.first_page

    @property
    def is_empty(self) -> bool:
        return not any(text.strip() for text in self.texts.values())


@dataclass(slots=True)
class Monograph:
    document_number: str | None
    document_date: date | None
    title: str | None
    has_use_columns: bool
    column_split_x: float | None
    page_count: int
    sections: list[MonographSection]
    front_matter: str
    footnotes: dict[str, Footnote]
    discarded: list[DiscardedLine]
    warnings: list[ExtractionWarning]
    # Per page: y (from top) where the page-bottom zone (footnotes/footers) begins, and size.
    content_bottom: dict[int, float] = field(default_factory=dict)
    page_sizes: dict[int, tuple[float, float]] = field(default_factory=dict)

    def section(self, number: str) -> MonographSection | None:
        return next((s for s in self.sections if s.number == number), None)

    @property
    def use_categories(self) -> list[UseCategory]:
        """Use categories this monograph covers, judged by §4.1 (therapeutic indications).

        EMA leaves a column blank throughout when a monograph covers only one category
        (e.g. garlic: traditional use only; senna: well-established use only).
        """
        indications = self.section("4.1")
        if indications is None:
            return sorted({c for s in self.sections for c, t in s.texts.items() if t.strip()})
        return sorted(c for c, t in indications.texts.items() if t.strip())

    def completeness(self, required: tuple[str, ...] = REQUIRED_SECTIONS) -> dict[str, str]:
        """Per required section: ``complete``, ``partial`` (a covered use category has no text),
        ``empty`` or ``missing``. Only text presence is assessed, not correctness; ``missing``
        and ``empty`` never mean "the monograph says nothing"."""
        covered = self.use_categories
        result: dict[str, str] = {}
        for number in required:
            section = self.section(number)
            if section is None:
                result[number] = "missing"
            elif section.is_empty:
                result[number] = "empty"
            elif any(not section.texts.get(c, "").strip() for c in covered):
                result[number] = "partial"
            else:
                result[number] = "complete"
        return result


@dataclass(slots=True)
class _Line:
    page: int
    top: float
    bottom: float
    words: list[Word]
    left: str = ""
    right: str = ""

    @property
    def full(self) -> str:
        return f"{self.left} {self.right}".strip()

    @property
    def is_small(self) -> bool:
        return all(w.size < BODY_FONT_MIN for w in self.words)


# --------------------------------------------------------------------------- helpers


def _group(words: list[Word], page: int) -> list[_Line]:
    lines: list[_Line] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(lines[-1].top - word.top) <= LINE_TOLERANCE:
            lines[-1].words.append(word)
            lines[-1].bottom = max(lines[-1].bottom, word.bottom)
        else:
            lines.append(_Line(page=page, top=word.top, bottom=word.bottom, words=[word]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    return lines


_MARKER = re.compile(r"^(\d{1,2}(?:,\d{1,2})*)(,?)$")  # "6", "1,", "1,2"


def _is_footnote_marker(word: Word, line_words: list[Word]) -> bool:
    """A footnote marker is a 1–2 digit token that is either small or raised.

    Most monographs set markers at 5–7 pt; some use 8.5 pt, so position matters too: a marker
    sits above the line's baseline (its top is higher than that of the main text).
    """
    if not _MARKER.match(word.text):
        return False
    body = [w for w in line_words if w is not word and not _MARKER.match(w.text)]
    if not body:
        return word.size < BODY_FONT_MIN
    main_size = max(w.size for w in body)
    main_top = sorted(w.top for w in body)[len(body) // 2]
    if word.size < BODY_FONT_MIN or word.size < main_size * 0.8:
        return True  # clearly smaller than its line (e.g. 9 pt marker on a 13.5 pt heading)
    return word.size < main_size - 0.3 and word.top < main_top - 1.0


def _render(words: list[Word], context: list[Word] | None = None) -> str:
    """Join words; superscript footnote numbers become ``[n]`` references.

    ``context`` is the whole line: marker detection compares a digit with its full line, not
    only with the words in its column (a marker can sit alone in the right half of a heading).
    """
    parts: list[str] = []
    for word in words:
        if _is_footnote_marker(word, context or words):
            match = _MARKER.match(word.text)
            assert match is not None  # noqa: S101 - guaranteed by _is_footnote_marker
            parts.append("".join(f"[{n}]" for n in match.group(1).split(",")))
            continue
        if parts and parts[-1].startswith("[") and parts[-1].endswith("]"):
            parts.append(" " + word.text)
        else:
            parts.append((" " if parts else "") + word.text)
    return "".join(parts).replace(" [", "[")


def _split_columns(line: _Line, split_x: float | None) -> None:
    if split_x is None:
        line.left, line.right = _render(line.words), ""
        return
    left = [w for w in line.words if w.x0 < split_x]
    right = [w for w in line.words if w.x0 >= split_x]
    line.left, line.right = _render(left, line.words), _render(right, line.words)


def _crossing_warning(line: _Line, split_x: float) -> ExtractionWarning | None:
    """Two-column line where a left word reaches into the right column: possible mis-split."""
    left = [w for w in line.words if w.x0 < split_x]
    right = [w for w in line.words if w.x0 >= split_x]
    crossing = [w for w in left if w.x1 > split_x + 2]
    if crossing and right:
        return ExtractionWarning(
            code="word_crosses_column_boundary",
            message="A left-column word extends into the right column on a two-column line.",
            page=line.page,
            text=" ".join(w.text for w in crossing),
        )
    return None


def _mostly_small(line: _Line) -> bool:
    chars = sum(len(w.text) for w in line.words)
    small = sum(len(w.text) for w in line.words if w.size < BODY_FONT_MIN)
    return chars > 0 and small / chars >= 0.6


def _find_column_split(pages: list[PageInput]) -> float | None:
    for page in pages:
        body = [w for w in page.words if w.size >= BODY_FONT_MIN]
        for line in _group(body, page.number):
            texts = [w.text for w in line.words]
            if "Well-established" in texts and "Traditional" in texts:
                trad = next(w for w in line.words if w.text == "Traditional")
                return trad.x0 - 4.0
    return None


def _join_column(parts: list[tuple[str, int, float, float]]) -> str:
    """Join column fragments (text, page, top, height) into paragraphs.

    A vertical gap of more than ~1.9 line heights starts a new paragraph. A page break only
    starts a new paragraph if the previous fragment ends a sentence, so sentences that
    continue on the next page stay intact.
    """
    out: list[str] = []
    prev_page, prev_top, prev_height = None, 0.0, 10.0
    for text, page, top, height in parts:
        if not text:
            continue
        if out:
            if page != prev_page:
                new_paragraph = out[-1].rstrip().endswith((".", ":", ";"))
            else:
                new_paragraph = (top - prev_top) > 1.9 * prev_height
            if new_paragraph:
                out.append("\n\n")
            elif not out[-1].endswith("-"):
                out.append(" ")
        out.append(text)
        prev_page, prev_top, prev_height = page, top, max(height, 6.0)
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


def _parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%d %B %Y").date()  # noqa: DTZ007 - calendar date only
    except ValueError:
        return None


def _section_order(number: str) -> tuple[int, int]:
    top, _, sub = number.partition(".")
    return int(top), int(sub or 0)


# --------------------------------------------------------------------------- main logic


def parse_pages(pages: list[PageInput]) -> Monograph:
    warnings: list[ExtractionWarning] = []
    discarded: list[DiscardedLine] = []
    footnotes: dict[str, Footnote] = {}
    page_count = len(pages)
    split_x = _find_column_split(pages)
    if split_x is None:
        warnings.append(
            ExtractionWarning(
                code="no_use_columns",
                message="No 'Well-established use | Traditional use' header found; text kept as a "
                "single column with use category 'not_applicable'.",
            )
        )

    # 1. Build lines: body words grouped; small words attached to nearby body lines, or kept
    #    in the page-bottom zone (footers, footnotes, boilerplate).
    content_lines: list[_Line] = []
    bottom_lines: list[_Line] = []
    content_bottom: dict[int, float] = {}
    page_sizes: dict[int, tuple[float, float]] = {}
    for page in pages:
        if page.multi_column_tables:
            warnings.append(
                ExtractionWarning(
                    code="complex_table",
                    message=f"{page.multi_column_tables} table(s) with more than two columns; "
                    "cell text is extracted line by line and the table structure is not kept.",
                    page=page.number,
                )
            )
        # Page-bottom zone (footers, footnotes, boilerplate): scanning upwards from the bottom,
        # every line made mostly of small text. Detected per line, not by a y threshold, because
        # footnotes may contain stray body-size characters (e.g. a 9 pt full stop).
        all_lines = _group(page.words, page.number)
        bottom_zone: list[Word] = []
        while all_lines and _mostly_small(all_lines[-1]):
            bottom_zone.extend(all_lines.pop().words)
        content_bottom[page.number] = min((w.top for w in bottom_zone), default=page.height)
        page_sizes[page.number] = (page.width, page.height)
        remaining = [w for ln in all_lines for w in ln.words]
        body = [w for w in remaining if w.size >= BODY_FONT_MIN]
        small = [w for w in remaining if w.size < BODY_FONT_MIN]
        lines = _group(body, page.number)
        for word in small:
            nearest = min(lines, key=lambda ln: abs(ln.top - word.top), default=None)
            if nearest is not None and abs(nearest.top - word.top) <= SMALL_WORD_ATTACH_DISTANCE:
                nearest.words.append(word)
                nearest.words.sort(key=lambda w: w.x0)
            else:
                orphan = _Line(page.number, word.top, word.bottom, [word])
                lines.append(orphan)
                warnings.append(
                    ExtractionWarning(
                        code="unattached_small_text",
                        message="Small-font text not near any body line; kept as its own line.",
                        page=page.number,
                        text=word.text,
                    )
                )
        lines.sort(key=lambda ln: ln.top)
        content_lines.extend(lines)
        bottom_lines.extend(_group(bottom_zone, page.number))

    # 2. Classify the page-bottom zone.
    def normalise_footer(text: str) -> str:
        return _PAGE_NUMBER.sub("Page #", text)

    footer_counts = Counter(
        normalise_footer(" ".join(w.text for w in ln.words))
        for ln in {
            (ln.page, " ".join(w.text for w in ln.words)): ln for ln in bottom_lines
        }.values()
    )
    open_footnote: Footnote | None = None
    for line in bottom_lines:
        text = " ".join(w.text for w in line.words)
        if _PAGE_NUMBER.search(text) or (
            page_count > 2 and footer_counts[normalise_footer(text)] >= page_count / 2
        ):
            discarded.append(DiscardedLine(line.page, "running_footer", text))
            open_footnote = None
        elif text.startswith(
            ("European Union herbal monograph on", "Community herbal monograph on")
        ):
            # Running footer carrying the document title (not always on half of the pages).
            discarded.append(DiscardedLine(line.page, "running_footer", text))
            open_footnote = None
        elif _BOILERPLATE.search(text):
            discarded.append(DiscardedLine(line.page, "publisher_boilerplate", text))
            open_footnote = None
        elif _MARKER.match(line.words[0].text):
            note_number = line.words[0].text.rstrip(",").split(",")[0]
            open_footnote = Footnote(
                note_number, line.page, " ".join(w.text for w in line.words[1:])
            )
            key = note_number
            if note_number in footnotes:
                # Numbering restarts in some documents (front matter vs. body). Both are kept;
                # the later one is stored under a page-qualified key.
                key = f"{note_number}@p{line.page}"
                warnings.append(
                    ExtractionWarning(
                        code="duplicate_footnote_number",
                        message=f"Footnote number {note_number} is used more than once; the occurrence "
                        f"on page {line.page} is stored as '{key}'.",
                        page=line.page,
                        text=text,
                    )
                )
            footnotes[key] = open_footnote
        elif open_footnote is not None and open_footnote.page == line.page:
            open_footnote.text = f"{open_footnote.text} {text}".strip()
        else:
            # Unknown small text at the page bottom: keep it as content, flag it.
            warnings.append(
                ExtractionWarning(
                    code="unclassified_page_bottom_text",
                    message="Small text at the bottom of a page is neither footer, boilerplate "
                    "nor footnote; kept as section content.",
                    page=line.page,
                    text=text,
                )
            )
            content_lines.append(line)
    content_lines.sort(key=lambda ln: (ln.page, ln.top))

    # 3. Walk content lines: front matter, headings, column text.
    for line in content_lines:
        _split_columns(line, split_x)

    sections: list[MonographSection] = []
    front: list[str] = []
    buffers: dict[UseCategory, list[tuple[str, int, float, float]]] = {}
    current: MonographSection | None = None
    expect_continuation = False
    left_margin = min((w.x0 for p in pages for w in p.words if w.size >= BODY_FONT_MIN), default=0)

    def flush() -> None:
        if current is None:
            return
        for category, parts in buffers.items():
            text = _join_column(parts)
            if text:
                current.texts[category] = text
        refs = sorted(
            {m for t in current.texts.values() for m in _FOOTNOTE_REF.findall(t)}
            | set(current.footnote_refs),
            key=int,
        )
        current.footnote_refs = refs

    def is_heading_start(line: _Line) -> bool:
        first = line.words[0]
        return first.x0 <= left_margin + 15 and (split_x is None or first.x0 < split_x)

    def accept(number: str) -> bool:
        if current is None:
            return True
        return _section_order(number) > _section_order(current.number)

    for line in content_lines:
        text = line.full
        sub = _SUB_HEADING.match(text) if is_heading_start(line) else None
        top = _TOP_HEADING.match(text) if is_heading_start(line) and sub is None else None
        match = sub or top
        number: str | None = None
        if sub:
            number = f"{sub['top']}.{sub['sub']}"
        elif top:
            number = str(top["top"])
        if match and number and accept(number):
            if current is not None and sections:
                prev = _section_order(current.number)
                new = _section_order(number)
                if new[0] == prev[0] and new[1] > prev[1] + 1:
                    warnings.append(
                        ExtractionWarning(
                            code="section_numbering_gap",
                            message=f"Section {number} follows {current.number}.",
                            page=line.page,
                            section=number,
                        )
                    )
            flush()
            title = match["title"]
            refs = _FOOTNOTE_REF.findall(title)
            current = MonographSection(
                number=number,
                title=_FOOTNOTE_REF.sub("", title).strip().rstrip(",").strip(),
                first_page=line.page,
                last_page=line.page,
                footnote_refs=refs,
                heading_top=line.top,
                body_top=line.bottom,
            )
            sections.append(current)
            buffers = (
                {UseCategory.WELL_ESTABLISHED: [], UseCategory.TRADITIONAL: []}
                if split_x is not None
                else {UseCategory.NOT_APPLICABLE: []}
            )
            expect_continuation = not title.rstrip().endswith((".", ")"))
            continue
        if match and number and not accept(number):
            warnings.append(
                ExtractionWarning(
                    code="heading_like_line_kept_as_text",
                    message=f"Line looks like heading {number} but is out of sequence after "
                    f"{current.number if current else '-'}; kept as text.",
                    page=line.page,
                    text=text,
                )
            )
        if current is None:
            front.append(text)
            continue
        current.last_page = line.page
        if expect_continuation and text and text[0].islower():
            refs = _FOOTNOTE_REF.findall(text)
            current.title = f"{current.title} {_FOOTNOTE_REF.sub('', text)}".strip()
            current.footnote_refs.extend(refs)
            current.body_top = line.bottom
            expect_continuation = False
            continue
        expect_continuation = False
        if line.left.startswith("Well-established") and line.right.startswith("Traditional"):
            discarded.append(DiscardedLine(line.page, "column_header", text))
            continue
        height = max(line.bottom - line.top, 6.0)
        if split_x is not None and (crossing := _crossing_warning(line, split_x)):
            warnings.append(
                ExtractionWarning(
                    code=crossing.code,
                    message=crossing.message,
                    page=crossing.page,
                    section=current.number,
                    text=crossing.text,
                )
            )
        if split_x is None:
            buffers[UseCategory.NOT_APPLICABLE].append((text, line.page, line.top, height))
        else:
            buffers[UseCategory.WELL_ESTABLISHED].append((line.left, line.page, line.top, height))
            buffers[UseCategory.TRADITIONAL].append((line.right, line.page, line.top, height))
    flush()

    # 4. Document metadata from the front matter.
    document_number = next((m.group(1) for t in front if (m := _DOC_NUMBER.search(t))), None)
    document_date = next(
        (d for t in front[:6] if (m := _DATE.match(t)) and (d := _parse_date(m.group(1)))), None
    )
    title = None
    for i, t in enumerate(front):
        if t.startswith(("European Union herbal monograph", "Community herbal monograph")):
            title = t
            nxt = front[i + 1] if i + 1 < len(front) else ""
            if (
                nxt
                and not _DOC_NUMBER.search(nxt)
                and not nxt.startswith(("Final", "Draft", "Initial"))
            ):
                title = f"{t} {nxt}"
            break

    # 5. Cross-checks.
    present = {s.number for s in sections}
    for number in REQUIRED_SECTIONS:
        section = next((s for s in sections if s.number == number), None)
        if number not in present:
            warnings.append(
                ExtractionWarning(
                    code="required_section_missing",
                    message=f"Required section {number} was not found. This does not mean the "
                    "monograph has no content for it.",
                    section=number,
                )
            )
        elif section is not None and section.is_empty:
            warnings.append(
                ExtractionWarning(
                    code="required_section_empty",
                    message=f"Section {number} heading found but no text extracted.",
                    section=number,
                    page=section.first_page,
                )
            )
    for section in sections:
        for ref in section.footnote_refs:
            if ref not in footnotes:
                warnings.append(
                    ExtractionWarning(
                        code="unresolved_footnote_reference",
                        message=f"Footnote [{ref}] referenced but its text was not found.",
                        section=section.number,
                        page=section.first_page,
                    )
                )
    if document_number is None:
        warnings.append(
            ExtractionWarning(
                code="document_number_missing", message="No EMA document number found."
            )
        )

    return Monograph(
        document_number=document_number,
        document_date=document_date,
        title=title,
        has_use_columns=split_x is not None,
        column_split_x=split_x,
        page_count=page_count,
        sections=sections,
        front_matter="\n".join(front),
        footnotes=footnotes,
        discarded=discarded,
        warnings=warnings,
        content_bottom=content_bottom,
        page_sizes=page_sizes,
    )


def _page_input(page: Any) -> PageInput:
    words = [
        Word(
            text=w["text"],
            x0=float(w["x0"]),
            x1=float(w["x1"]),
            top=float(w["top"]),
            bottom=float(w["bottom"]),
            size=float(w.get("size", 9.0)),
        )
        for w in page.extract_words(extra_attrs=["size"])
    ]
    multi = 0
    for table in page.find_tables():
        rows = table.extract()
        if rows and max(len(r) for r in rows) > 2:
            multi += 1
    return PageInput(page.page_number, float(page.width), float(page.height), words, multi)


def parse_monograph(pdf_bytes: bytes) -> Monograph:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [_page_input(page) for page in pdf.pages]
    return parse_pages(pages)
