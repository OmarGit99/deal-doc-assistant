import pytest

from app.ingest.parse import find_body_end, find_body_start, html_to_lines
from tests.agreement_fixtures import ARABIC_PREFIXED, LONG


def test_inline_tags_are_joined_and_blocks_split() -> None:
    lines = html_to_lines("<p>Ter<font>mination</font> <b>Fee</b></p><p>Next paragraph</p>")
    assert lines == ["Termination Fee", "Next paragraph"]


def test_table_cells_become_separate_lines() -> None:
    lines = html_to_lines("<table><tr><td>Section 1.01.</td><td>Definitions.</td></tr></table>")
    assert lines == ["Section 1.01.", "Definitions."]


def test_page_furniture_is_removed() -> None:
    markup = "<p>Text</p><p>12</p><p>A-12</p><p>- 3 -</p><p>iv</p><p>Table of Contents</p>"
    assert html_to_lines(markup) == ["Text"]


def test_left_blank_markers_are_removed() -> None:
    markup = "<p>Text</p><p>[Remainder of page intentionally left blank]</p>"
    assert html_to_lines(markup) == ["Text"]


def test_body_starts_at_the_preamble_not_the_contents_page() -> None:
    lines = html_to_lines(ARABIC_PREFIXED)
    start, method = find_body_start(lines)
    assert method == "preamble"
    assert lines[start].startswith('AGREEMENT AND PLAN OF MERGER (this "Agreement")')


def test_body_start_falls_back_to_the_last_real_first_article() -> None:
    lines = ["ARTICLE I", "THE MERGER", "1.1", "The Merger", "ARTICLE I", "THE MERGER", LONG]
    assert find_body_start(lines) == (4, "article")


def test_body_ends_at_signature_pages_follow_line() -> None:
    lines = html_to_lines(ARABIC_PREFIXED)
    end, found = find_body_end(lines, 0)
    assert found
    assert lines[end] == "[Remainder of page intentionally left blank; signature page follows]"


def test_body_ends_at_in_witness_whereof() -> None:
    lines = ["Section 9.1 Notices.", LONG, "IN WITNESS WHEREOF, the parties have signed.", "By:"]
    assert find_body_end(lines, 0) == (2, True)


@pytest.mark.parametrize(
    "preamble",
    [
        'This AGREEMENT AND PLAN OF MERGER (this "Agreement") is made as of',
        'THIS AGREEMENT AND PLAN OF MERGER ("Agreement") is made and entered into as of',
        'This AGREEMENT AND PLAN OF MERGER, dated as of July 7, 2024 (this "Agreement" and, '
        'such date, the "Agreement Date"), is entered into by',
        'AGREEMENT AND PLAN OF MERGER (as amended from time to time, this "Agreement")',
    ],
)
def test_preamble_variants(preamble: str) -> None:
    lines = ["TABLE OF CONTENTS", "ARTICLE I", f"{preamble} {LONG}", "ARTICLE I"]
    assert find_body_start(lines) == (2, "preamble")


def test_source_line_wrapping_does_not_split_paragraphs() -> None:
    # EDGAR HTML wraps long paragraphs across source lines; that is not a line break.
    assert html_to_lines("<p>converted into the right\n  to receive $40.00</p>") == [
        "converted into the right to receive $40.00"
    ]
