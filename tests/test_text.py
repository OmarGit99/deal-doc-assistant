from app.text import contains_quote, decode_html, normalize, strip_html


def test_normalize_collapses_whitespace_and_newlines() -> None:
    assert normalize("  the   Merger\n\tConsideration ") == "the Merger Consideration"


def test_normalize_straightens_curly_quotes() -> None:
    assert normalize("the “Agreement” and Parent’s") == 'the "Agreement" and Parent\'s'


def test_normalize_turns_nbsp_and_entities_into_spaces() -> None:
    assert normalize("$40.00 per&nbsp;Share") == "$40.00 per Share"


def test_strip_html_joins_words_split_by_inline_tags() -> None:
    assert normalize(strip_html("Ter<font>mination</font> Fee")) == "Termination Fee"


def test_strip_html_separates_block_elements() -> None:
    assert normalize(strip_html("<p>ARTICLE 10</p><p>TERMINATION</p>")) == "ARTICLE 10 TERMINATION"


def test_strip_html_drops_style_blocks() -> None:
    assert normalize(strip_html("<style>p {color: red}</style><p>Text</p>")) == "Text"


def test_contains_quote_ignores_formatting_differences() -> None:
    source = "<p>a fee equal to $123,000,000 (the “Company Termination Fee”)</p>"
    assert contains_quote(strip_html(source), 'a fee equal to $123,000,000 (the "Company')


def test_contains_quote_rejects_changed_wording() -> None:
    assert not contains_quote("a fee equal to $123,000,000", "a fee of $123,000,000")


def test_contains_quote_rejects_empty_quote() -> None:
    assert not contains_quote("anything", "   ")


def test_decode_html_falls_back_to_cp1252() -> None:
    assert decode_html("Parent’s".encode("cp1252")) == "Parent’s"
