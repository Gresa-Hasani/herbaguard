# EMA Monograph Extraction — Validation Report

**Generated:** 2026-11-02 from the development database (`herbaguard ema-report`), after a clean ingestion of all 16 curated monographs. Parser `ema_monograph_v2`, cross-check `ema_crosscheck`.

## 1. How extraction was validated

1. **Independent second engine.** pdfplumber (pdfminer, word coordinates) output was compared with **PDFium** (pypdfium2), per required section and per use-category column. PDFium reads the text inside each column's rectangle between the section heading and the next heading, across pages and excluding the footnote/footer zone. Comparison metrics: recall, precision and token-order similarity (thresholds 0.98 / 0.98 / 0.95).
2. **Whole-document accounting.** Every PDFium token must be accounted for by *some* parser output (section text, heading, front matter, footnote, or a discarded line with a recorded reason). Coverage is 99.73–99.91 % per document; the remainder was inspected and consists only of footnote digits removed from headings (kept separately as references) and subscripts that PDFium joins (`tmax` vs `t max`).
3. **Visual inspection** of rendered pages for the risky layouts (St John's wort §4.5: heading spanning both columns with a superscript footnote, section crossing pages 9–10, footnote referring to the assessment report).
4. **Regression tests** on synthetic layouts for each failure mode found (`backend/tests/ingestion/test_ema_monograph_parser.py`).

## 2. Defects found and fixed during validation

| # | Defect in the first parser version | Effect | Fix | Test |
|---|---|---|---|---|
| 1 | Headings matched only when the line had no right-column text | **§4.4, §4.5 and §4.7 missing in all 16 monographs** (long headings cross the column boundary) | Match headings on the full line, anchored at the left margin, with sequence checks | `test_heading_spanning_both_columns_is_recognised` |
| 2 | Words < 8 pt dropped silently | Footnotes (incl. *"For a list of drugs … see the Assessment report EMA/HMPC/244315/2016 chapter 5.5.4"*), superscript markers and subscripts lost without trace | Page-bottom zone classified (footer / boilerplate / footnote); markers become `[n]` references; nothing is dropped without a recorded reason | `test_running_footers_and_boilerplate_are_recorded_not_silently_dropped`, `test_footnote_with_stray_body_size_character_is_still_a_footnote` |
| 3 | Unnumbered top-level sections (2., 3., 4., …) dropped | Composition text lost | Top-level headings become sections | (covered by coverage check) |
| 4 | Page breaks always started a new paragraph | Sentences split ("reduced safety in ⏎⏎ birth control") | Join across pages unless the previous text ends a sentence | `test_sentence_continuing_on_next_page_is_joined` |
| 5 | A 9 pt full stop inside a 7.6 pt footnote moved the footnote into the body | Footnote text inside section content | Footnote zone detected line by line from the page bottom | `test_footnote_with_stray_body_size_character_is_still_a_footnote` |
| 6 | 8.5 pt / 9 pt markers on large headings not recognised | "composition 1, 2" in titles | Marker detection by relative size and raised position, using the whole line | same |
| 7 | Single-use-category monographs reported as "partial" | False gaps | Completeness judged against the use categories the monograph covers (from §4.1) | `test_single_use_category_monograph_is_complete` |
| 8 | Cross-check rectangle edges clipped neighbouring lines | False mismatches ("42Pld thd f diit" = ascenders of "4.2 Posology …") | 3 pt edge margins in the verifier | — |

## 3. Results per monograph and required section

Legend: **complete** = every covered use category has text; ✓ = column verified against PDFium; ∅ = empty in both engines; ✗ = mismatch; *(none reported)* = the section text is exactly "None reported"/"None known".

| Herb | Document | Use categories | 4.1 | 4.2 | 4.3 | 4.4 | 4.5 | 4.6 | 4.7 | 4.8 | Token coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| black_cohosh | EMA/HMPC/48745/2017 (2018-03-27) | WEU | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ (none reported) | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | 0.9986 |
| cranberry | EMA/HMPC/49135/2017 (2022-11-23) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9985 |
| echinacea | EMA/HMPC/48704/2014 (2015-11-24) | TU, WEU | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓ (none reported), WEU ✓ (none reported) | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | 0.9989 |
| garlic | EMA/HMPC/7685/2013 (2017-07-18) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9985 |
| ginger | EMA/HMPC/885789/2022 (2025-05-07) | TU, WEU | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓ (none reported), WEU ✓ (none reported) | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | 0.9991 |
| ginkgo | EMA/HMPC/321097/2012 (2015-01-28) | TU, WEU | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | 0.9987 |
| ginseng | EMA/HMPC/27744/2023 (2024-05-29) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ (none reported) | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9985 |
| green_tea | EMA/HMPC/283630/2012 (2013-11-12) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9973 |
| hawthorn | EMA/HMPC/159075/2014 (2016-04-05) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ (none reported) | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9982 |
| liquorice | EMA/HMPC/108399/2024 (2026-03-04) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9978 |
| milk_thistle | EMA/HMPC/294187/2013 (2018-06-05) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ (none reported) | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9979 |
| saw_palmetto | EMA/HMPC/280079/2013 (2015-11-24) | TU, WEU | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | 0.9985 |
| senna | EMA/HMPC/625849/2015 (2018-09-25) | WEU | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | complete: WEU ✓ | 0.9987 |
| st_johns_wort | EMA/HMPC/7695/2021 (2022-11-23) | TU, WEU | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | 0.9979 |
| turmeric | EMA/HMPC/329755/2017 (2018-09-25) | TU | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ (none reported) | complete: TU ✓ | complete: TU ✓ | complete: TU ✓ | 0.9978 |
| valerian | EMA/HMPC/150848/2015 (2016-02-02) | TU, WEU | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓ (none reported), WEU ✓ (none reported) | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | complete: TU ✓, WEU ✓ | 0.9988 |

**Summary:** 16/16 monographs, 8/8 required sections each, all *complete*; 176 columns verified, 80 consistently empty (the unused column of single-use-category monographs), **0 mismatches**. 35 of the required sections span a page break; all verified.

Remaining extraction notes (informational, recorded as data-quality issues):

- Ginseng (p. 1) and valerian (p. 2): a table with more than two columns in the front matter — outside the required sections; cell text is kept line by line.
- Ginseng: footnote number 1 is used twice (front matter and body); both footnotes are kept (`1` and `1@p3`).

## 4. Interpretation rules (binding for later phases)

- An empty or missing section is **not** evidence that no interaction or warning exists; it is reported as an extraction gap.
- "None reported" in §4.5 is the *regulator's* statement at the monograph date — it is stored as such (`section_statement = none_reported`) and must be shown with that date, never as "safe".
- Traditional-use (TU) and well-established-use (WEU) text are stored as separate evidence items and must never be merged.
