"""safety_pack_sync - fake fetcher, no network."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.noctus.dev.safety_pack_sync import _PACK_REL, safety_pack_sync


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _setup(tmp_path: Path) -> tuple[Path, bytes, bytes]:
    d = tmp_path / _PACK_REL
    (d / "limiar").mkdir(parents=True)
    r, c = json.dumps({"versao": "v1"}).encode(), b'{"x":1}'
    (d / "limiar/regras.json").write_bytes(r)
    (d / "limiar/conformance.json").write_bytes(c)
    (d / "SOURCE.lock").write_text(json.dumps({
        "repo": "o/r", "commit": "aaa", "versao": "v1",
        "files": {"regras.json": _sha(r), "conformance.json": _sha(c)}}))
    return tmp_path, r, c


def _fetch(versao: str):
    files = {"safety/regras.json": json.dumps({"versao": versao}).encode(), "safety/conformance.json": b'{"x":2}'}
    return (lambda repo, path, ref: files[path]), (lambda repo, ref: "bbb")


def test_dry_run_reports_diff_and_stale_without_writing(tmp_path):
    root, r, _ = _setup(tmp_path)
    f, res = _fetch("v2")
    out = safety_pack_sync(repo="o/r", confirm=False, root=root, fetcher=f, resolver=res)
    assert out["status"] == "planned" and out["stale"] is True and "warning" in out
    assert out["diff"]["versao"] == {"lock": "v1", "fetched": "v2"}
    assert out["diff"]["changed_files"] == ["conformance.json", "regras.json"]
    assert (root / _PACK_REL / "limiar/regras.json").read_bytes() == r


def test_confirm_writes_pack_and_lock_when_conformance_passes(tmp_path):
    root, _, _ = _setup(tmp_path)
    f, res = _fetch("v2")
    out = safety_pack_sync(repo="o/r", confirm=True, root=root, fetcher=f, resolver=res,
                           validator=lambda _r: (True, "ok"))
    assert out["status"] == "synced"
    lock = json.loads((root / _PACK_REL / "SOURCE.lock").read_text())
    assert lock["commit"] == "bbb" and lock["versao"] == "v2"
    new = (root / _PACK_REL / "limiar/regras.json").read_bytes()
    assert lock["files"]["regras.json"] == _sha(new)


def test_failed_conformance_restores_previous_pack(tmp_path):
    root, r, c = _setup(tmp_path)
    lock_before = (root / _PACK_REL / "SOURCE.lock").read_text()
    f, res = _fetch("v2")
    out = safety_pack_sync(repo="o/r", confirm=True, root=root, fetcher=f, resolver=res,
                           validator=lambda _r: (False, "boom"))
    assert out["status"] == "conformance_failed" and out["restored"] is True
    assert (root / _PACK_REL / "limiar/regras.json").read_bytes() == r
    assert (root / _PACK_REL / "limiar/conformance.json").read_bytes() == c
    assert (root / _PACK_REL / "SOURCE.lock").read_text() == lock_before


def test_offline_fetch_failure_is_reported_not_raised(tmp_path):
    root, _, _ = _setup(tmp_path)

    def boom(*_a):
        raise RuntimeError("offline")

    out = safety_pack_sync(repo="o/r", root=root, fetcher=boom, resolver=lambda *_: "x")
    assert out["status"] == "fetch_failed" and out["ok"] is False


def test_unknown_app_refused(tmp_path):
    assert safety_pack_sync(app="nope", root=tmp_path)["status"] == "error"
