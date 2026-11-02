"""EMA monograph parser on synthetic page layouts.

The layouts are SYNTHETIC (word coordinates written by hand), modelled on the real EMA
monographs examined on 2026-11-02: A4 page, body 9 pt, left margin 62 pt, right column from
x ≈ 303 pt, footnotes 7.6 pt, running footer 7 pt at y ≈ 785–793. Each test reproduces a
failure mode found during parser validation.
"""

from __future__ import annotations

from herbaguard.domain.enums import UseCategory
from herbaguard.ingestion.parsers.ema_monograph import (
    REQUIRED_SECTIONS,
    PageInput,
    Word,
    parse_pages,
)

WEU = UseCategory.WELL_ESTABLISHED
TU = UseCategory.TRADITIONAL
RIGHT = 303.0


def line(
    text: str, x0: float, top: float, size: float = 9.0, char_width: float = 4.6
) -> list[Word]:
    """Words of one line starting at x0; x positions approximate a proportional font."""
    words, x = [], x0
    for token in text.split():
        width = len(token) * char_width * size / 9.0
        words.append(Word(token, x, x + width, top, top + size, size))
        x += width + 2.5
    return words


def footer(page: int, total: int) -> list[Word]:
    return line("European Union herbal monograph on Testus plantus L., herba", 62, 785, 7.0) + line(
        f"EMA/HMPC/1234/2020 Page {page}/{total}", 62, 793, 7.0
    )


def front_page(total: int) -> PageInput:
    words = (
        line("12 March 2020", 62, 60)
        + line("EMA/HMPC/1234/2020", 62, 74)
        + line("European Union herbal monograph on Testus plantus L., herba", 62, 120, 14.0)
        + line("Final", 62, 160)
        + line(
            "© European Medicines Agency, 2020. Reproduction is authorised provided the source is acknowledged.",
            114,
            818,
            7.0,
        )
    )
    return PageInput(1, 595, 842, words)


def column_header(top: float) -> list[Word]:
    return line("Well-established use", 68, top) + line("Traditional use", RIGHT + 5, top)


def body_page(number: int, total: int, words: list[Word]) -> PageInput:
    return PageInput(number, 595, 842, words + footer(number, total))


def required_stub_sections(start_top: float, skip: set[str] = frozenset()) -> list[Word]:  # type: ignore[assignment]
    """Short headings + one line of text for every required section not in ``skip``."""
    words: list[Word] = []
    top = start_top
    for number in REQUIRED_SECTIONS:
        if number in skip:
            continue
        words += line(f"{number}. Section {number.replace('.', '')} title", 62, top, 11.0)
        words += column_header(top + 18)
        words += line(f"WEU text {number}.", 68, top + 34) + line(
            f"TU text {number}.", RIGHT + 5, top + 34
        )
        top += 60
    return words


# --------------------------------------------------------------------------- regressions


def test_heading_spanning_both_columns_is_recognised() -> None:
    """Regression: long headings run past the column boundary and were dropped (4.4/4.5/4.7)."""
    words = (
        line("4. Clinical particulars", 62, 60, 13.5)
        + line("4.4. Special warnings and precautions for use", 62, 90, 11.0, char_width=6.5)
        + column_header(110)
        + line("Not recommended in children.", 68, 126)
        + line("Not recommended in children.", RIGHT + 5, 126)
        + line(
            "4.5. Interactions with other medicinal products and other forms of",
            62,
            160,
            11.0,
            char_width=6.5,
        )
        + line("interaction", 62, 175, 11.0)
        + [Word("6", 125, 129, 173, 179, 6.0)]  # superscript footnote marker
        + column_header(195)
        + line("Concomitant use with warfarin is contraindicated.", 68, 211)
        + line("None reported.", RIGHT + 5, 211)
        + line(
            "4.7. Effects on ability to drive and use machines, if applicable",
            62,
            245,
            11.0,
            char_width=6.5,
        )
        + column_header(265)
        + line("No studies performed.", 68, 281)
        + line("No studies performed.", RIGHT + 5, 281)
        + line("6", 62, 745, 5.0)
        + line("See the Assessment report EMA/HMPC/9999/2016 chapter 5.5.4.", 68, 746, 7.6)
    )
    # Sanity check: the 4.4 heading really crosses the column boundary in this layout.
    assert max(w.x1 for w in words if w.top == 90) > RIGHT

    monograph = parse_pages([front_page(2), body_page(2, 2, words)])

    s44, s45, s47 = (monograph.section(n) for n in ("4.4", "4.5", "4.7"))
    assert s44 is not None and s45 is not None and s47 is not None
    assert s44.title == "Special warnings and precautions for use"
    assert s45.title == "Interactions with other medicinal products and other forms of interaction"
    assert s45.footnote_refs == ["6"]
    assert monograph.footnotes["6"].text.startswith("See the Assessment report EMA/HMPC/9999/2016")
    assert s45.texts[WEU] == "Concomitant use with warfarin is contraindicated."
    assert s45.texts[TU] == "None reported."
    assert s47.title == "Effects on ability to drive and use machines, if applicable"


def test_columns_are_not_mixed() -> None:
    words = (
        line("4.5. Interactions", 62, 90, 11.0)
        + column_header(110)
        + line("Left first line", 68, 126)
        + line("Right first line", RIGHT + 5, 126)
        + line("left second line.", 68, 138)
        + line("right second line.", RIGHT + 5, 138)
    )
    section = parse_pages([front_page(2), body_page(2, 2, words)]).section("4.5")
    assert section is not None
    assert section.texts[WEU] == "Left first line left second line."
    assert section.texts[TU] == "Right first line right second line."


def test_sentence_continuing_on_next_page_is_joined() -> None:
    """Regression: page breaks inserted paragraph breaks mid-sentence."""
    page2 = (
        line("4.5. Interactions", 62, 600, 11.0)
        + column_header(620)
        + line("Hormonal contraceptives: reduced safety in", 68, 636)
    )
    page3 = (
        column_header(60)
        + line("birth control. Use additional measures.", 68, 76)
        + line("4.6. Fertility, pregnancy and lactation", 62, 120, 11.0)
        + column_header(140)
        + line("Not recommended.", 68, 156)
    )
    section = parse_pages([front_page(3), body_page(2, 3, page2), body_page(3, 3, page3)]).section(
        "4.5"
    )
    assert section is not None
    assert section.texts[WEU] == (
        "Hormonal contraceptives: reduced safety in birth control. Use additional measures."
    )
    assert (section.first_page, section.last_page) == (2, 3)
    assert section.spans_pages


def test_page_break_after_full_sentence_starts_new_paragraph() -> None:
    page2 = (
        line("4.4. Warnings", 62, 600, 11.0)
        + column_header(620)
        + line("First paragraph.", 68, 636)
    )
    page3 = column_header(60) + line("Second paragraph.", 68, 76)
    section = parse_pages([front_page(3), body_page(2, 3, page2), body_page(3, 3, page3)]).section(
        "4.4"
    )
    assert section is not None
    assert section.texts[WEU] == "First paragraph.\n\nSecond paragraph."


def test_footnote_with_stray_body_size_character_is_still_a_footnote() -> None:
    """Regression: a 9 pt full stop inside a 7.6 pt footnote moved the footnote into the body."""
    words = (
        line("2. Qualitative and quantitative composition", 62, 90, 13.5)
        + [
            Word("1,", 380, 386, 89, 98, 9.0),
            Word("2", 388, 393, 89, 98, 9.0),
        ]  # 9 pt markers on 13.5 pt heading
        + column_header(110)
        + line("Testus plantus L., herba", 68, 126)
        + line("Testus plantus L., herba", RIGHT + 5, 126)
        + line("1", 62, 723, 6.0)
        + line(
            "The declaration of the active substance should be in accordance with herbal",
            69,
            726,
            7.6,
        )
        + line("quality guidance", 62, 737, 7.6)
        + [Word(".", 124, 126, 736, 745, 9.0)]
        + line("2", 62, 746, 7.0)
        + line("The material complies with the Ph. Eur. monograph (ref. 2543).", 69, 750, 7.6)
    )
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    section = monograph.section("2")
    assert section is not None
    assert section.title == "Qualitative and quantitative composition"
    assert section.footnote_refs == ["1", "2"]
    assert monograph.footnotes["1"].text.endswith("quality guidance .")
    assert (
        monograph.footnotes["2"].text
        == "The material complies with the Ph. Eur. monograph (ref. 2543)."
    )
    assert "Ph. Eur." not in section.texts[WEU]


def test_running_footers_and_boilerplate_are_recorded_not_silently_dropped() -> None:
    words = (
        line("4.1. Therapeutic indications", 62, 90, 11.0)
        + column_header(110)
        + line("Indication text.", 68, 126)
    )
    monograph = parse_pages(
        [front_page(3), body_page(2, 3, words), body_page(3, 3, line("More.", 68, 100))]
    )
    reasons = {d.reason for d in monograph.discarded}
    assert {"running_footer", "publisher_boilerplate", "column_header"} <= reasons
    footer_texts = [d.text for d in monograph.discarded if d.reason == "running_footer"]
    assert any("Page 2/3" in t for t in footer_texts)


# --------------------------------------------------------------------------- completeness


def test_missing_required_section_is_reported_not_assumed_empty() -> None:
    words = required_stub_sections(80, skip={"4.5"})
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    assert monograph.completeness()["4.5"] == "missing"
    codes = [(w.code, w.section) for w in monograph.warnings]
    assert ("required_section_missing", "4.5") in codes
    message = next(w.message for w in monograph.warnings if w.section == "4.5")
    assert "does not mean" in message


def test_empty_required_section_is_reported() -> None:
    words = required_stub_sections(80, skip={"4.5", "4.6", "4.7", "4.8"})
    words += line("4.5. Interactions", 62, 400, 11.0) + column_header(420)
    words += line("4.6. Fertility", 62, 450, 11.0) + column_header(470) + line("Text.", 68, 486)
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    assert monograph.completeness()["4.5"] == "empty"
    assert any(
        w.code == "required_section_empty" and w.section == "4.5" for w in monograph.warnings
    )


def test_single_use_category_monograph_is_complete() -> None:
    """Traditional-use-only monographs leave the WEU column blank; that is not a gap."""
    words: list[Word] = []
    top = 80.0
    for number in REQUIRED_SECTIONS:
        words += line(f"{number}. Title {number}", 62, top, 11.0) + column_header(top + 18)
        words += line(f"Traditional text {number}.", RIGHT + 5, top + 34)
        top += 60
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    assert monograph.use_categories == [TU]
    assert set(monograph.completeness().values()) == {"complete"}


def test_partial_section_when_covered_column_is_blank() -> None:
    words = required_stub_sections(80, skip={"4.5", "4.6", "4.7", "4.8"})
    words += (
        line("4.5. Interactions", 62, 400, 11.0) + column_header(420) + line("Only WEU.", 68, 436)
    )
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    assert monograph.completeness()["4.5"] == "partial"


# --------------------------------------------------------------------------- robustness


def test_out_of_sequence_heading_like_line_is_kept_as_text() -> None:
    words = (
        line("4.5. Interactions", 62, 90, 11.0)
        + column_header(110)
        + line("4.1. Something that looks like a heading", 62, 126)
        + line("4.6. Fertility", 62, 160, 11.0)
    )
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    section = monograph.section("4.5")
    assert section is not None
    assert "Something that looks like a heading" in section.texts[WEU]
    assert any(w.code == "heading_like_line_kept_as_text" for w in monograph.warnings)


def test_document_without_use_columns_is_flagged() -> None:
    words = line("4.5. Interactions", 62, 90, 11.0) + line("Single column text.", 68, 110)
    monograph = parse_pages([front_page(2), body_page(2, 2, words)])
    assert not monograph.has_use_columns
    assert any(w.code == "no_use_columns" for w in monograph.warnings)
    section = monograph.section("4.5")
    assert section is not None
    assert section.texts[UseCategory.NOT_APPLICABLE] == "Single column text."


def test_front_matter_metadata() -> None:
    monograph = parse_pages(
        [front_page(2), body_page(2, 2, line("4.1. Indications", 62, 90, 11.0))]
    )
    assert monograph.document_number == "EMA/HMPC/1234/2020"
    assert str(monograph.document_date) == "2020-03-12"
    assert monograph.title == "European Union herbal monograph on Testus plantus L., herba"
