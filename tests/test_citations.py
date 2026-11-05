from app.chains.citations import Citation, validate_citations
from app.retrieval.corpus import Candidate

BODY = (
    "(b) Company Termination Fee. If this Agreement is terminated by Parent, the Company "
    "shall pay Parent “$407,500,000” in immediately available cash (the “Company "
    "Termination Fee”)."
)
CHUNK = Candidate(
    "deal-11.04-01",
    "deal",
    "11.04",
    "section",
    f"Deal: Juniper / HPE · Section 11.04 Expenses\n\n{BODY}",
    {"deal_id": "deal", "section_number": "11.04", "kind": "section"},
)


def check(*citations: Citation) -> tuple[list[Citation], list[str]]:
    valid, rejected = validate_citations(list(citations), [CHUNK])
    return valid, [r.reason for r in rejected]


def test_exact_quote_from_a_retrieved_chunk_passes() -> None:
    valid, rejected = check(Citation(chunk_id="deal-11.04-01", section_number="11.04(b)",
                                     quote="in immediately available cash"))  # fmt: skip
    assert rejected == []
    assert valid[0].section_number == "11.04(b)"  # a subsection inside the chunk is kept


def test_quote_matching_ignores_curly_quotes_and_spacing() -> None:
    quote = 'shall pay Parent   "$407,500,000"'
    valid, _ = check(Citation(chunk_id="deal-11.04-01", section_number="11.04", quote=quote))
    assert len(valid) == 1


def test_chunk_that_was_not_retrieved_is_rejected() -> None:
    _, rejected = check(
        Citation(chunk_id="deal-8.03-01", section_number="8.03", quote="shall pay Parent")
    )
    assert rejected == ["chunk was not retrieved"]


def test_reworded_quote_is_rejected() -> None:
    _, rejected = check(Citation(chunk_id="deal-11.04-01", section_number="11.04",
                                 quote="the Company must pay Parent $407.5 million"))  # fmt: skip
    assert rejected == ["quote not found in the chunk"]


def test_quoting_our_own_header_is_rejected() -> None:
    _, rejected = check(Citation(chunk_id="deal-11.04-01", section_number="11.04",
                                 quote="Section 11.04 Expenses"))  # fmt: skip
    assert rejected == ["quote not found in the chunk"]


def test_trivially_short_quote_is_rejected() -> None:
    _, rejected = check(Citation(chunk_id="deal-11.04-01", section_number="11.04", quote="the"))
    assert rejected == ["quote too short to verify"]


def test_wrong_section_number_is_replaced_by_the_chunks() -> None:
    valid, _ = check(
        Citation(chunk_id="deal-11.04-01", section_number="8.3(b)", quote="shall pay Parent")
    )
    assert valid[0].section_number == "11.04"


def test_duplicate_citations_are_collapsed() -> None:
    c = Citation(chunk_id="deal-11.04-01", section_number="11.04", quote="shall pay Parent")
    valid, _ = check(c, c)
    assert len(valid) == 1
