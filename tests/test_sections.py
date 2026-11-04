import pytest

from app.ingest.parse import html_to_lines
from app.ingest.sections import (
    ARTICLE_RE,
    SECTION_RE,
    ParsedAgreement,
    article_number,
    parse_structure,
    section_key,
    section_matches,
    term_index,
)
from tests.agreement_fixtures import (
    ARABIC_PREFIXED,
    LONG,
    ROMAN_BARE,
    SAME_LINE,
    SECTION_TOP_LEVEL,
    TENDER_OFFER,
)


def parse(markup: str) -> ParsedAgreement:
    return parse_structure(html_to_lines(markup), "test-deal")


def titles(parsed: ParsedAgreement) -> dict[str, str]:
    return {s.number: s.title for s in parsed.sections}


# --- heading regexes ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "major", "minor"),
    [
        ("Section 8.03", "8", "03"),
        ("Section 10.01.", "10", "01"),
        ("SECTION 8.3.", "8", "3"),
        ("8.3", "8", "3"),
        ("8.2 Termination by Either Parent", "8", "2"),
        ("Sec. 1.1 Definitions.", "1", "1"),
    ],
)
def test_section_heading_formats(line: str, major: str, minor: str) -> None:
    match = SECTION_RE.match(line)
    assert match is not None
    assert (match["major"], match["minor"]) == (major, minor)


@pytest.mark.parametrize(("token", "number"), [("VIII", 8), ("IV", 4), ("10", 10), ("ONE", 1)])
def test_article_numbers(token: str, number: int) -> None:
    assert article_number(token) == number


def test_article_number_rejects_words_that_are_not_numbers() -> None:
    assert article_number("TERMINATION") is None


def test_article_regex_reads_same_line_title() -> None:
    match = ARTICLE_RE.match("ARTICLE ONE THE MERGER")
    assert match is not None
    assert (match["num"], match["rest"]) == ("ONE", "THE MERGER")


# --- section keys -----------------------------------------------------------------------


def test_section_key_ignores_prefix_and_zero_padding() -> None:
    assert section_key("Section 8.03(b)(i).") == (8, 3, ("b", "i"))
    assert section_key("8.3(b)(i)") == section_key("Section 8.03(b)(i)")


@pytest.mark.parametrize(
    ("reference", "retrieved", "expected"),
    [
        ("2.02(a)", "2.02", True),  # section-level chunk contains the subsection
        ("2.02(a)", "Section 2.2", True),
        ("2.02", "2.02(a)", False),  # a subsection does not cover the whole section
        ("2.02(a)", "2.02(b)", False),
        ("2.02(a)", "2.03", False),
    ],
)
def test_section_matches(reference: str, retrieved: str, expected: bool) -> None:
    assert section_matches(reference, retrieved) is expected


# --- style 1: arabic, "Section 10.01." on its own line ---------------------------------


def test_arabic_style_structure() -> None:
    parsed = parse(ARABIC_PREFIXED)
    assert [(a.number, a.title) for a in parsed.articles] == [
        (1, "DEFINITIONS"),
        (2, "THE MERGER"),
        (3, "TERMINATION"),
    ]
    assert titles(parsed) == {
        "1.01": "Definitions",
        "1.02": "Other Definitional and Interpretative Provisions",
        "2.01": "The Merger",
        "2.02": "Conversion of Shares",
        "3.01": "Termination",
        "3.02": "[Reserved]",
    }
    assert parsed.warnings == []


def test_contents_page_and_page_numbers_are_not_in_sections() -> None:
    parsed = parse(ARABIC_PREFIXED)
    all_text = "\n".join(s.text for s in parsed.sections)
    assert "Table of Contents" not in all_text
    assert "\n1\n" not in all_text
    assert len(parsed.sections) == 6  # no duplicates from the contents page


def test_cross_reference_paragraph_stays_in_its_section() -> None:
    section = {s.number: s for s in parse(ARABIC_PREFIXED).sections}["2.02"]
    assert "Section 2.02(b) shall not apply to Dissenting Shares." in section.text


def test_signature_pages_and_exhibits_are_cut() -> None:
    parsed = parse(ARABIC_PREFIXED)
    assert parsed.end_marker_found
    assert "JUNIPER NETWORKS" not in parsed.sections[-1].text
    assert parsed.trailing_chars > 0


def test_definitions_include_their_sub_clauses() -> None:
    parsed = parse(ARABIC_PREFIXED)
    by_term = {d.term: d for d in parsed.definitions}
    assert set(by_term) == {
        "Acquisition Proposal",
        "Company Material Adverse Effect",
        "Superior Proposal",
    }
    assert "(ii) changes in law." in by_term["Company Material Adverse Effect"].text
    assert by_term["Acquisition Proposal"].section_number == "1.01"


def test_term_index_table_is_read() -> None:
    index = parse(ARABIC_PREFIXED).term_index
    assert index["Company Termination Fee"] == "11.04(b)(i)"
    assert index["End Date"] == "10.01(b)(i)"
    assert len(index) == 5


def test_inline_defined_terms_are_recorded_per_section() -> None:
    sections = {s.number: s for s in parse(ARABIC_PREFIXED).sections}
    assert "End Date" in sections["3.01"].defined_terms
    assert "Merger Consideration" in sections["2.02"].defined_terms


def test_preamble_is_kept_separately() -> None:
    parsed = parse(ARABIC_PREFIXED)
    assert parsed.preamble.startswith("AGREEMENT AND PLAN OF MERGER (this")
    assert "WHEREAS" in parsed.preamble


# --- style 2: roman, bare "8.2", titles split over lines --------------------------------


def test_roman_style_structure() -> None:
    parsed = parse(ROMAN_BARE)
    assert [a.label for a in parsed.articles] == ["I", "II", "III"]
    assert parsed.articles[2].title == "TERMINATION"  # lowercase in the source
    assert parsed.articles[1].title == (
        "ORGANIZATIONAL DOCUMENTS, DIRECTORS AND OFFICERS OF THE SURVIVING CORPORATION"
    )
    assert titles(parsed) == {
        "1.1": "The Merger",
        "1.2": "Closing",
        "2.1": "Certificate of Incorporation",
        "3.1": "Termination by Either Parent or the Company",
        "3.2": "Definitions",
    }
    assert parsed.warnings == []


def test_split_title_lines_are_not_left_in_the_body() -> None:
    section = {s.number: s for s in parse(ROMAN_BARE).sections}["3.1"]
    assert section.lines[0].startswith("This Agreement may be terminated")


def test_front_matter_index_of_defined_terms_is_read() -> None:
    parsed = parse(ROMAN_BARE)
    assert parsed.term_index["Go-Shop Period"] == "6.2(a)(i)"
    assert parsed.term_index["Agreement"] == "Preamble"
    assert len(parsed.term_index) == 5
    assert [d.term for d in parsed.definitions] == ["Excluded Party"]


# --- style 3: heading and body on one line ------------------------------------------------


def test_same_line_style_structure() -> None:
    parsed = parse(SAME_LINE)
    assert [(a.number, a.title) for a in parsed.articles] == [(1, "THE MERGER"), (2, "TERMINATION")]
    assert titles(parsed) == {
        "1.1": "Definitions",
        "1.2": "Certain U.S. Tax Matters",
        "2.01": "Termination",
        "2.02": "Termination Fee",
    }


def test_body_text_after_a_same_line_title_is_kept() -> None:
    section = {s.number: s for s in parse(SAME_LINE).sections}["2.02"]
    assert section.lines[0].startswith("(a) The Company shall pay $10,000,000")


def test_paragraphs_starting_with_numbers_or_references_are_not_headings() -> None:
    sections = {s.number: s for s in parse(SAME_LINE).sections}
    assert "1.5 million shares" in sections["1.2"].text
    assert "Section 2.03 shall survive" in sections["2.01"].text


def test_lettered_definitions_and_their_clauses() -> None:
    parsed = parse(SAME_LINE)
    by_term = {d.term: d for d in parsed.definitions}
    assert "Acceptable Confidentiality Agreement" in by_term
    assert "(i) for this purpose" in by_term["Business Day"].text


def test_definition_inside_a_paragraph_keeps_only_its_sentence() -> None:
    by_term = {d.term: d for d in parse(SAME_LINE).definitions}
    tax = by_term["Tax"]
    assert tax.section_number == "1.2"
    assert tax.text == '"Tax" or "Taxes" means all federal and state taxes.'


@pytest.mark.parametrize(
    ("line", "is_heading"),
    [
        ("ARTICLE V", True),
        ("ARTICLE V REPRESENTATIONS AND WARRANTIES", True),
        ("Article V Representations and Warranties", True),
        ("Article V of this Agreement", False),
        ("ARTICLE V shall survive the Closing", False),
    ],
)
def test_article_heading_versus_reference(line: str, is_heading: bool) -> None:
    lines = [f'AGREEMENT AND PLAN OF MERGER (this "Agreement") among the parties {"x" * 80}']
    lines += [f"ARTICLE {n}" for n in ("I", "II", "III", "IV")] + [line, "5.1 Title. Text."]
    parsed = parse_structure(lines)
    assert (len(parsed.articles) == 5) is is_heading


# --- style 4: tender offer with annexes after the signatures ------------------------------


def test_tender_offer_body_and_end() -> None:
    parsed = parse(TENDER_OFFER)
    assert parsed.body_start_method == "preamble"
    assert parsed.end_marker_found
    body = [s for s in parsed.sections if s.article_number != 0]
    assert [s.number for s in body] == ["1.1", "2.1"]
    assert "GILEAD SCIENCES" not in body[-1].text


def test_definition_and_condition_annexes_are_kept() -> None:
    parsed = parse(TENDER_OFFER)
    annexes = {s.number: s for s in parsed.sections if s.article_number == 0}
    assert set(annexes) == {"Exhibit A", "Annex I"}
    assert annexes["Annex I"].title == "Conditions to the Offer"
    assert "Minimum Condition" in annexes["Annex I"].text
    assert len(parsed.dropped_annexes) == 1
    assert parsed.dropped_annexes[0].startswith("Annex II: Amended and Restated Certificate")


def test_definitions_in_an_annex_span_repeated_page_headings() -> None:
    parsed = parse(TENDER_OFFER)
    by_term = {d.term: d.section_number for d in parsed.definitions}
    assert by_term == {
        "Affiliate": "Exhibit A",
        "Agreement": "Exhibit A",
        "Company RSUs": "Exhibit A",
    }


def test_annex_labels_match_as_text() -> None:
    assert section_matches("Annex I", "annex i")
    assert not section_matches("Annex I", "Annex II")
    assert not section_matches("Annex I", "1.1")


# --- index tables found by their shape -----------------------------------------------------


def test_index_without_a_heading_is_found() -> None:
    lines = ["Surviving Corporation", "1.01", "Takeover Proposal", "5.06(b)", "Tax", "3.15"]
    lines += ["Merger", "1.01", "Parent Termination Fee", "7.03(c)", LONG]
    assert term_index(lines)["Takeover Proposal"] == "5.06(b)"


def test_contents_page_is_not_read_as_an_index() -> None:
    # Title, then the next section's number: the same rhythm as an index, but in order.
    lines = ["Section 1.01", "The Merger", "Section 1.02", "Closing", "Section 1.03", "Effective"]
    lines += ["Section 1.04", "Charter", "Section 1.05", "Bylaws", "Section 1.06", "Directors"]
    assert term_index(lines) == {}


# --- style 5: "Section 1." as the top level -------------------------------------------------


def test_section_number_as_top_level() -> None:
    parsed = parse(SECTION_TOP_LEVEL)
    assert [(a.word, a.number, a.title) for a in parsed.articles] == [
        ("SECTION", 1, "THE TRANSACTION"),
        ("SECTION", 2, "MISCELLANEOUS PROVISIONS"),
    ]
    assert titles(parsed) == {
        "1.1": "The Merger",
        "1.2": "Effects of the Merger",
        "2.1": "Amendment",
    }


def test_section_reference_is_not_a_top_level_heading() -> None:
    sections = {s.number: s for s in parse(SECTION_TOP_LEVEL).sections}
    assert "Section 5 of the Securities Act" in sections["1.2"].text


def test_agreements_with_articles_ignore_section_n_lines() -> None:
    lines = [f'AGREEMENT AND PLAN OF MERGER (this "Agreement") {"x" * 90}']
    lines += ["ARTICLE I", "THE MERGER", "1.1 The Merger. Text.", "Section 2. THE TRANSACTION"]
    parsed = parse_structure(lines)
    assert len(parsed.articles) == 1
    assert "Section 2. THE TRANSACTION" in parsed.sections[0].text


def test_scanned_filing_is_flagged() -> None:
    page = "AGREEMENT AND PLAN OF MERGER " + "word " * 1000
    parsed = parse_structure([page] * 100)
    assert any("scanned" in w for w in parsed.warnings)
