"""Ledger checksum verification (ledger_checksums.py; migrate_product sha= + predeploy leg)."""
from __future__ import annotations

import json

import pytest

from tools.noctus.dev import ledger_checksums as lc
from tools.noctus.dev.migrate_product import FakeSqlExecutor

V1 = "CREATE TABLE t (id int);\n"
V2 = "CREATE TABLE t (id int); -- edited after it ran\n"


def _row(name, content_or_hash, *, raw=False):
    return {"filename": name, "ledger_checksum": content_or_hash if raw else lc.sha256_text(content_or_hash)}


def _ack(name, ledger, current, cls="post-apply-edit-audit"):
    return {"file": name, "ledger_checksum": ledger, "file_checksum": current, "remediate": cls}


def test_matching_ledger_is_verified():
    v = lc.judge([_row("001.sql", V1)], {"001.sql": V1}, [])
    assert v["status"] == "verified" and v["checked"] == 1 and v["drift"] == []


def test_an_edited_applied_file_is_drift():
    v = lc.judge([_row("001.sql", V1)], {"001.sql": V2}, [])
    assert v["status"] == "drift"
    assert v["drift"][0]["kind"] == "content_changed"


def test_acknowledging_the_exact_state_passes():
    ack = [_ack("001.sql", lc.sha256_text(V1), lc.sha256_text(V2))]
    v = lc.judge([_row("001.sql", V1)], {"001.sql": V2}, ack)
    assert v["status"] == "verified" and v["acknowledged"] == ["001.sql"]


def test_a_further_edit_to_an_acknowledged_file_refuses_again():
    """Not a file-name allowlist: the ack pins (file, ledger_checksum, file_checksum)."""
    ack = [_ack("001.sql", lc.sha256_text(V1), lc.sha256_text(V2))]
    v = lc.judge([_row("001.sql", V1)], {"001.sql": V2 + "-- and again\n"}, ack)
    assert v["status"] == "drift"
    assert v["stale_ack"] == ["001.sql"]


def test_a_sentinel_ledger_value_is_acknowledged_by_value():
    sentinel = "applied-via-mcp-connector"
    ack = [_ack("074.sql", sentinel, lc.sha256_text(V1), "ledger-sentinel-checksum")]
    assert lc.judge([_row("074.sql", sentinel, raw=True)], {"074.sql": V1}, ack)["status"] == "verified"


def test_an_applied_file_missing_at_the_sha_is_drift():
    v = lc.judge([_row("001.sql", V1)], {}, [])
    assert v["drift"][0]["kind"] == "file_missing"


def test_ack_with_undeclared_class_or_missing_fields_is_refused():
    with pytest.raises(ValueError, match="NOC-REMEDIATE"):
        lc.parse_ack(json.dumps({"acknowledged": [_ack("a", "x", "y", "someday")]}), "t")
    with pytest.raises(ValueError, match="lacks"):
        lc.parse_ack(json.dumps({"acknowledged": [{"file": "a"}]}), "t")


def test_unreadable_ledger_is_inconclusive_never_a_pass(tmp_path):
    ex = FakeSqlExecutor(fail_on={"schema_migrations"})
    v = lc.verify(slug="demo", schema="demo", sha="abc", files={"001.sql": V1},
                  executor=ex, root=tmp_path, ack_raw=None)
    assert v["status"] == "inconclusive"


def test_verify_reads_the_ledger_and_judges(tmp_path):
    ex = FakeSqlExecutor(preset_rows={"checksum AS ledger_checksum": [_row("001.sql", V1)]})
    v = lc.verify(slug="demo", schema="demo", sha="abc", files={"001.sql": V2},
                  executor=ex, root=tmp_path, ack_raw="")
    assert v["status"] == "drift" and v["sha"] == "abc"
