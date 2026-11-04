"""findings_append mirrors each finding into the auto-improvement ledger."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import findings as f  # noqa: E402


def _setup(tmp_path, monkeypatch):
    d = tmp_path / "projects" / "demo"
    d.mkdir(parents=True)
    (d / "findings.md").write_text("# f\n\n## Lessons\n- _(none)_\n")
    monkeypatch.setattr(f, "REPO_ROOT", tmp_path)


def test_finding_logged_with_source_ref(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls = []
    def fake(**kw):
        calls.append(kw)
        return {"ok": True}
    r = f.findings_append("demo", "Lessons", "learned x", provenance="architect", ai_logger=fake)
    assert r["ok"] and r["ledger"]["ok"]
    assert calls[0]["kind"] == "finding" and calls[0]["source"]["tool"] == "findings"
    assert calls[0]["source"]["ref"] == r["finding_ref"]
    assert r["finding_ref"].startswith("demo:Lessons:")


def test_logger_failure_surfaced(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    def boom(**kw):
        raise RuntimeError("nope")
    r = f.findings_append("demo", "Lessons", "learned y", ai_logger=boom)
    assert r["ok"] and r["ledger"]["ok"] is False and "nope" in r["ledger"]["error"]
    assert "learned y" in (tmp_path / "projects/demo/findings.md").read_text()
