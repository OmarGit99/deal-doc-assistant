from app.ingest.chunk import (
    CHARS_PER_TOKEN,
    Chunk,
    DealInfo,
    chunk_agreement,
    chunk_stats,
    slug,
)
from app.ingest.parse import html_to_lines
from app.ingest.sections import parse_structure
from tests.agreement_fixtures import ARABIC_PREFIXED, LONG, TENDER_OFFER

DEAL = DealInfo(
    "juniper-hpe-2024",
    "Juniper Networks, Inc.",
    "Hewlett Packard Enterprise Company",
    "https://www.sec.gov/Archives/edgar/data/1/2/x.htm",
)


def chunks_for(markup: str, **kwargs: int) -> list[Chunk]:
    return chunk_agreement(parse_structure(html_to_lines(markup), DEAL.deal_id), DEAL, **kwargs)


def by_id(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {c.chunk_id: c for c in chunks}


def test_section_chunk_has_context_header_and_readable_id() -> None:
    chunk = by_id(chunks_for(ARABIC_PREFIXED))["juniper-hpe-2024-2.02-01"]
    assert chunk.kind == "section"
    assert chunk.header == (
        "Deal: Juniper Networks, Inc. / Hewlett Packard Enterprise Company"
        " · ARTICLE 2 THE MERGER · Section 2.02 Conversion of Shares"
    )
    assert chunk.text.startswith(chunk.header + "\n\n")
    assert "$40.00 per Share" in chunk.body
    assert chunk.defined_terms == ["Merger Consideration"]


def test_long_section_is_split_into_numbered_overlapping_parts() -> None:
    long_section = f"<p>Section 2.01.</p><p>The Merger.</p>{f'<p>{LONG}</p>' * 40}"
    markup = ARABIC_PREFIXED.replace(
        "<p>Section 2.01.</p>\n<p>The Merger.</p>", long_section.replace("{", "{{")
    )
    parts = [
        c
        for c in chunks_for(markup, chunk_tokens=300, overlap_tokens=50)
        if c.section_number == "2.01"
    ]
    assert len(parts) > 2
    assert [c.part for c in parts] == list(range(1, len(parts) + 1))
    assert parts[0].header.endswith(f"(part 1/{len(parts)})")
    assert parts[0].chunk_id.endswith("-01") and parts[1].chunk_id.endswith("-02")
    # Consecutive parts share text, so a clause cut at the boundary appears whole once.
    assert parts[0].body[-100:] in parts[1].body or parts[1].body[:100] in parts[0].body
    assert all(len(c.text) <= 300 * CHARS_PER_TOKEN for c in parts)


def test_definitions_become_their_own_chunks() -> None:
    chunks = chunks_for(ARABIC_PREFIXED)
    definitions = {c.term: c for c in chunks if c.kind == "definition"}
    assert set(definitions) == {
        "Acquisition Proposal",
        "Company Material Adverse Effect",
        "Superior Proposal",
    }
    mae = definitions["Company Material Adverse Effect"]
    assert mae.chunk_id == "juniper-hpe-2024-def-company-material-adverse-effect-01"
    assert mae.section_number == "1.01"
    assert 'Definition of "Company Material Adverse Effect" (Section 1.01)' in mae.header
    assert "(ii) changes in law." in mae.body


def test_definitions_section_is_not_duplicated() -> None:
    sections = [c for c in chunks_for(ARABIC_PREFIXED) if c.section_number == "1.01"]
    leftover = [c for c in sections if c.kind == "section"]
    # Only the intro and the term index remain; the definition entries are not repeated.
    for chunk in leftover:
        assert '"Acquisition Proposal" means' not in chunk.body


def test_empty_reserved_sections_have_no_chunks() -> None:
    assert not [c for c in chunks_for(ARABIC_PREFIXED) if c.section_number == "3.02"]


def test_preamble_chunk() -> None:
    chunk = by_id(chunks_for(ARABIC_PREFIXED))["juniper-hpe-2024-preamble-01"]
    assert chunk.kind == "preamble"
    assert chunk.body.startswith("AGREEMENT AND PLAN OF MERGER (this")


def test_annexes_and_their_definitions() -> None:
    chunks = by_id(chunks_for(TENDER_OFFER))
    conditions = chunks["juniper-hpe-2024-annex-i-01"]
    assert conditions.kind == "annex"
    assert conditions.header.endswith("· Annex I Conditions to the Offer")
    affiliate = chunks["juniper-hpe-2024-def-affiliate-01"]
    assert affiliate.section_number == "Exhibit A"
    assert "(Exhibit A)" in affiliate.header


def test_chunk_ids_are_unique_and_stable() -> None:
    first = [c.chunk_id for c in chunks_for(ARABIC_PREFIXED)]
    second = [c.chunk_id for c in chunks_for(ARABIC_PREFIXED)]
    assert len(first) == len(set(first))
    assert first == second


def test_document_carries_the_spec_metadata() -> None:
    chunk = by_id(chunks_for(ARABIC_PREFIXED))["juniper-hpe-2024-2.02-01"]
    doc = chunk.to_document()
    assert doc.id == chunk.chunk_id
    assert doc.page_content == chunk.text
    for key in ("deal_id", "target", "acquirer", "article", "section_number", "section_title",
                "page", "source_url", "chunk_id", "text_hash"):  # fmt: skip
        assert key in doc.metadata
    assert "body" not in doc.metadata


def test_text_hash_changes_only_with_text() -> None:
    a, b = chunks_for(ARABIC_PREFIXED), chunks_for(ARABIC_PREFIXED)
    assert a[0].text_hash == b[0].text_hash
    assert a[0].text_hash != a[1].text_hash


def test_slug() -> None:
    assert slug("Annex I") == "annex-i"
    assert slug("11.04") == "11.04"
    assert slug('"Company" MAE') == "company-mae"


def test_stats() -> None:
    stats = chunk_stats(chunks_for(ARABIC_PREFIXED))
    assert stats["chunks"] == sum(stats["by_kind"].values())
    assert stats["tokens_max"] >= stats["tokens_p50"]
