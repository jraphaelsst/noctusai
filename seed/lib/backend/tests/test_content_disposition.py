"""`attachment_disposition` — the RFC 6266 header must be latin-1-safe."""
from __future__ import annotations

from noctusai_lib.primitives.content_disposition import attachment_disposition


def test_accented_name_folds_ascii_and_keeps_utf8_form():
    v = attachment_disposition("certidões_João.zip")
    assert v == "attachment; filename=\"certidoes_Joao.zip\"; filename*=UTF-8''certid%C3%B5es_Jo%C3%A3o.zip"
    v.encode("latin-1")  # the whole point: Starlette must be able to encode it


def test_quotes_dropped_and_all_non_ascii_falls_back():
    assert 'filename="a b.pdf"' in attachment_disposition('a "b".pdf'.replace('"b"', 'b'))
    assert 'filename="x.pdf"' in attachment_disposition('"x".pdf')
    assert 'filename="download"' in attachment_disposition("日本")
    assert 'filename="zip"' in attachment_disposition("日本", fallback="zip")
