"""Unit tests for the conversation_module's pure routing helpers.

Focus on the regex extractor + unanswered-inbound join — the
state-aware dispatch is exercised at the integration level.
"""
from __future__ import annotations

import pytest

from app.services.conversation_module import (
    _join_unanswered_inbound,
    _regex_extract,
)


def test_regex_extracts_code_and_url_from_single_message():
    text = "ONE7360 https://drive.google.com/drive/folders/1abc?usp=drive_link"
    code, url = _regex_extract(text)
    assert code == "ONE7360"
    assert url == "https://drive.google.com/drive/folders/1abc?usp=drive_link"


def test_regex_extracts_lowercase_code_uppercased():
    code, _ = _regex_extract("one1234 https://drive.google.com/file/d/xyz/view")
    assert code == "ONE1234"


def test_regex_extracts_across_multi_line_input():
    """The buffer joins multi-message inbounds with \\n; the regex must
    find code + URL across the joined blob."""
    text = "ONE7360\nhttps://drive.google.com/drive/folders/1xyz"
    code, url = _regex_extract(text)
    assert code == "ONE7360"
    assert url == "https://drive.google.com/drive/folders/1xyz"


def test_regex_misses_when_code_absent():
    code, url = _regex_extract("https://drive.google.com/drive/folders/1xyz")
    assert code is None
    assert url == "https://drive.google.com/drive/folders/1xyz"


def test_regex_misses_when_url_absent():
    code, url = _regex_extract("oi, sobe esse aí pra mim: ONE7360")
    assert code == "ONE7360"
    assert url is None


def test_regex_ignores_short_codes():
    """ONE12 (4-digit minimum) should NOT match — codes are ONE\\d{3,6}."""
    code, _ = _regex_extract("ONE12 https://drive.google.com/drive/folders/abc")
    assert code is None


def test_regex_accepts_docs_google_com_url():
    code, url = _regex_extract("ONE7360 https://docs.google.com/file/d/abc/view")
    assert code == "ONE7360"
    assert "docs.google.com" in url


def test_join_returns_empty_for_empty_memory():
    assert _join_unanswered_inbound([]) == ""


def test_join_returns_empty_when_no_inbound_after_outbound():
    memory = [
        {"direction": "inbound", "text": "ONE7360"},
        {"direction": "outbound", "text": "ok, sobe"},
    ]
    assert _join_unanswered_inbound(memory) == ""


def test_join_returns_trailing_inbound_run():
    memory = [
        {"direction": "inbound", "text": "old message"},
        {"direction": "outbound", "text": "old reply"},
        {"direction": "inbound", "text": "ONE7360"},
        {"direction": "inbound", "text": "https://drive.google.com/..."},
    ]
    joined = _join_unanswered_inbound(memory)
    assert joined == "ONE7360\nhttps://drive.google.com/..."


def test_join_handles_memory_with_no_outbound():
    """First-message scenario — no prior outbound; the whole inbound run
    counts as unanswered."""
    memory = [
        {"direction": "inbound", "text": "ONE7360"},
        {"direction": "inbound", "text": "https://drive.google.com/x"},
    ]
    joined = _join_unanswered_inbound(memory)
    assert joined == "ONE7360\nhttps://drive.google.com/x"


def test_join_strips_whitespace_from_each_entry():
    memory = [
        {"direction": "inbound", "text": "  ONE7360  "},
        {"direction": "inbound", "text": " https://drive.google.com/x "},
    ]
    joined = _join_unanswered_inbound(memory)
    assert joined == "ONE7360\nhttps://drive.google.com/x"


def test_join_skips_empty_entries():
    memory = [
        {"direction": "inbound", "text": "ONE7360"},
        {"direction": "inbound", "text": ""},
        {"direction": "inbound", "text": "https://drive.google.com/x"},
    ]
    joined = _join_unanswered_inbound(memory)
    assert joined == "ONE7360\nhttps://drive.google.com/x"
