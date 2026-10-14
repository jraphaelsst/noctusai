"""Attachments: magic-byte validation, caps, server-generated org-prefixed keys, signed URLs."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.finance import attachments as att
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, mk_entry, run

PDF = b"%PDF-1.7\n" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64
XML = b'<?xml version="1.0"?><nfe/>'


@pytest.mark.parametrize("ctype, data, ext", [
    ("application/pdf", PDF, "pdf"), ("image/png", PNG, "png"), ("image/jpeg", JPG, "jpg"),
    ("application/xml", XML, "xml"), ("text/xml; charset=utf-8", b"\xef\xbb\xbf  \n<root/>", "xml"),
])
def test_accepts_each_allowed_type(ctype, data, ext):
    assert att.validate_upload(ctype, data)[0] == ext


@pytest.mark.parametrize("ctype, data", [
    ("application/pdf", PNG),                   # declared type lies
    ("image/png", PDF),
    ("image/jpeg", b"not a jpeg"),
    ("application/pdf", b""),                   # empty
    ("text/html", b"<html></html>"),            # type not allowed
    ("application/x-msdownload", b"MZ..."),
    ("application/xml", b"plain text"),
    ("application/xml", b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>'),  # entity declaration
])
def test_rejects_mismatch_and_disallowed(ctype, data):
    with pytest.raises(FinanceError) as err:
        att.validate_upload(ctype, data)
    assert (err.value.status_code, err.value.code) == (422, "anexo_invalido")


def test_size_cap_is_413():
    with pytest.raises(FinanceError) as err:
        att.validate_upload("application/pdf", b"%PDF-" + b"0" * att.MAX_ATTACHMENT_BYTES)
    assert (err.value.status_code, err.value.code) == (413, "anexo_grande_demais")


def test_xml_is_stored_as_octet_stream_so_a_browser_will_not_render_it():
    assert att.validate_upload("application/xml", XML) == ("xml", "application/octet-stream")


@pytest.mark.parametrize("raw, safe", [
    ("../../etc/passwd", "passwd"), ("C:\\x\\nota.pdf", "nota.pdf"), (".hidden", "hidden"),
    ("a\x00b\nc.pdf", "abc.pdf"), (None, "anexo"), ("   ", "anexo"), ("x" * 300 + ".pdf", "x" * 120),
])
def test_safe_filename(raw, safe):
    assert att.safe_filename(raw) == safe


def test_key_is_server_generated_org_prefixed_and_url_is_short_lived(s):
    storage = FakeStorageBackend()
    e = mk_entry(s)
    out = run(att.add_attachment(s, storage, e["id"], filename="../../evil.pdf", content_type="application/pdf", data=PDF, user_id="u"))
    row = s.rows("attachments")[0]
    assert row["storage_path"] == f"{s.org_id}/entries/{e['id']}/{row['id']}.pdf"
    assert "evil" not in row["storage_path"] and row["filename"] == "evil.pdf"
    assert "storage_path" not in out and out["disposition"] == "attachment"
    assert out["expires_in_seconds"] <= 600 and out["url"]
    assert run(storage.exists(bucket=CFG.bucket, key=row["storage_path"]))


def test_list_and_delete_remove_the_object(s):
    storage = FakeStorageBackend()
    e = mk_entry(s)
    a = run(att.add_attachment(s, storage, e["id"], filename="a.png", content_type="image/png", data=PNG))
    assert [x["id"] for x in run(att.list_attachments(s, storage, e["id"]))] == [a["id"]]
    key = s.rows("attachments")[0]["storage_path"]
    run(att.delete_attachment(s, storage, a["id"]))
    assert s.rows("attachments") == [] and not run(storage.exists(bucket=CFG.bucket, key=key))
    with pytest.raises(NotFoundError):
        run(att.delete_attachment(s, storage, a["id"]))


def test_per_entry_limit(s):
    storage = FakeStorageBackend()
    e = mk_entry(s)
    for _ in range(att.MAX_ATTACHMENTS_PER_ENTRY):
        run(att.add_attachment(s, storage, e["id"], filename="a.png", content_type="image/png", data=PNG))
    with pytest.raises(FinanceError) as err:
        run(att.add_attachment(s, storage, e["id"], filename="a.png", content_type="image/png", data=PNG))
    assert err.value.code == "anexo_limite"


def test_cross_org_entry_and_attachment_are_404(s, s_b):
    storage = FakeStorageBackend()
    other = mk_entry(s_b)
    with pytest.raises(NotFoundError):
        run(att.add_attachment(s, storage, other["id"], filename="a.png", content_type="image/png", data=PNG))
    with pytest.raises(NotFoundError):
        run(att.list_attachments(s, storage, other["id"]))
    theirs = run(att.add_attachment(s_b, storage, other["id"], filename="a.png", content_type="image/png", data=PNG))
    with pytest.raises(NotFoundError):
        run(att.delete_attachment(s, storage, theirs["id"]))
    assert len(s_b.rows("attachments")) == 1  # untouched


def test_upload_override_constants_match_the_route():
    assert att.ATTACHMENT_UPLOAD_PATH_PATTERN == "/api/finance/entries/*/attachments"
    assert att.ATTACHMENT_UPLOAD_MAX_BYTES > att.MAX_ATTACHMENT_BYTES
