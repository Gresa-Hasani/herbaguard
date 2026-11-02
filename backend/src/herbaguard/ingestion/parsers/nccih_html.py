"""Parser for NCCIH "Herbs at a Glance" fact-sheet pages.

Verified on 2026-11-02 for 15 pages: each has ``h2`` sections (Background, How Much Do We
Know?, What Have We Learned?, What Do We Know About Safety?, Keep in Mind, ...) and a
"Last Updated" date. Section content is nested in wrapper ``div``s, so blocks are collected in
document order between headings. Lists are kept as separate items with their lead-in paragraph
recorded as context (never merged into new sentences).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

# Sections that hold scientific/safety content; navigation and reference lists are skipped.
CONTENT_SECTIONS = ("Background", "How Much Do We Know?", "What Have We Learned?",
                    "What Do We Know About Safety?", "Keep in Mind")  # fmt: skip
SAFETY_SECTION = "What Do We Know About Safety?"


@dataclass(slots=True)
class Block:
    text: str
    is_list_item: bool
    lead_in: str | None = None  # paragraph introducing the list this item belongs to


@dataclass(slots=True)
class FactSheetSection:
    title: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


@dataclass(slots=True)
class FactSheet:
    title: str | None
    last_updated: str | None
    sections: list[FactSheetSection]

    def section(self, title: str) -> FactSheetSection | None:
        return next((s for s in self.sections if s.title == title), None)


def _own_text(element: Tag) -> str:
    """Text of an element without nested lists/paragraphs (they are separate blocks)."""
    clone = copy.copy(element)
    for nested in clone.find_all(["ul", "ol", "p"]):
        if nested is not clone:
            nested.decompose()
    return re.sub(r"\s+", " ", clone.get_text(" ", strip=True)).strip()


def parse_fact_sheet(html: str) -> FactSheet:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    title_tag = main.find("h1")
    full_text = main.get_text(" ", strip=True)
    updated = re.search(r"Last Updated:?\s*([A-Z][a-z]+ \d{4})", full_text)

    sections: list[FactSheetSection] = []
    for heading in main.find_all("h2"):
        title = heading.get_text(" ", strip=True)
        if title not in CONTENT_SECTIONS:
            continue
        section = FactSheetSection(title=title)
        last_paragraph: str | None = None
        for element in heading.find_all_next(["h2", "p", "li"]):
            if element.name == "h2":
                break
            if element.name == "p" and element.find_parent("li"):
                continue  # paragraph inside a list item: already part of that item's own text
            text = _own_text(element)
            if not text:
                continue
            parent_item = element.find_parent("li") if element.name == "li" else None
            if element.name == "li" and parent_item is not None:
                # Nested item ("Birth control pills") under a bullet that introduces it.
                section.blocks.append(
                    Block(text, is_list_item=True, lead_in=_own_text(parent_item) or last_paragraph)
                )
            elif (
                element.name == "li"
                and element.find("ul") is None
                and last_paragraph
                and last_paragraph.endswith(":")
            ):
                # Top-level item of a list introduced by a paragraph ending with a colon.
                section.blocks.append(Block(text, is_list_item=True, lead_in=last_paragraph))
            else:
                # Paragraph, or a top-level bullet used as a paragraph (NCCIH safety sections).
                section.blocks.append(Block(text, is_list_item=False))
                last_paragraph = text
        sections.append(section)
    return FactSheet(
        title=title_tag.get_text(" ", strip=True) if title_tag else None,
        last_updated=updated.group(1) if updated else None,
        sections=sections,
    )
