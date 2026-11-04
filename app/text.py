"""Text helpers shared by ingestion, the golden-set checker and the citation validator."""

import html
import re
import unicodedata

# Characters that look alike to a reader but differ byte-for-byte.
_LOOKALIKES = str.maketrans(
    {
        "‘": "'",  # left single quote
        "’": "'",  # right single quote / apostrophe
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "–": "-",  # en dash
        "—": "-",  # em dash
        "‑": "-",  # non-breaking hyphen
    }
)
_WHITESPACE = re.compile(r"\s+")

# Tags that start a new line or cell when a browser renders them.
_BLOCK_TAG = re.compile(
    r"</?(?:p|div|br|tr|td|th|li|ul|ol|table|h[1-6]|hr|center)\b[^>]*>", re.IGNORECASE
)
_ANY_TAG = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)


def decode_html(raw: bytes) -> str:
    """Decode EDGAR bytes. Most filings are UTF-8 or ASCII; older ones are Windows-1252."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def strip_html(markup: str) -> str:
    """Rough HTML-to-text for checks. The Week 2 parser replaces this for chunking.

    Block tags become spaces (they separate words); inline tags such as <font> or
    <span> are removed outright, because EDGAR often splits a single word across them.
    """
    text = _SCRIPT_STYLE.sub(" ", markup)
    text = _BLOCK_TAG.sub(" ", text)
    text = _ANY_TAG.sub("", text)
    return html.unescape(text)


def normalize(text: str) -> str:
    """Canonical form for comparing quotes with source text."""
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)  # turns non-breaking spaces into spaces
    text = text.translate(_LOOKALIKES)
    return _WHITESPACE.sub(" ", text).strip()


def contains_quote(haystack: str, quote: str) -> bool:
    """True if `quote` appears in `haystack` once both are normalized."""
    needle = normalize(quote)
    return bool(needle) and needle in normalize(haystack)
