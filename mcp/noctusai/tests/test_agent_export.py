"""`noctus.dev.agent_export` (Agent Packages §M2): fetch → verify → write the DB-source mirror + refresh the cache."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import agent_export as ax  # noqa: E402
from tools.noctus.dev import agent_sync_client as sc  # noqa: E402
from tools.noctus.dev.agent_package_build import _surface  # noqa: E402

ENV = {"NOCTUS_AGENTS_URL": "https://agents.example.test", "NOCTUS_AGENTS_TOKEN": "pk_secret_never_echoed"}


def _tree(key="media-analyst", fonte="db", tamper=False):
    md = _surface().db_mirror_markdown(
        key=key, descricao="Analisa vídeos.", idioma="pt-BR", compiled_text="# Prompt\n\nCorpo.", tools=["Bash", "Read"],
        model="opus", owns_kb=["CONTEXT/PATTERNS/x.md"], versao="2.0.0", version_id="v-2")
    if tamper:
        md = md.replace("Corpo.", "Corpo editado à mão.")
    files = [
        {"path": f".claude/agents/{key}.md", "conteudo": md},
        {"path": f"agents/{key}/PACKAGE.json", "conteudo": "{}\n"},
        {"path": f"agents/{key}/skills/transcrever/SKILL.md", "conteudo": "---\nname: transcrever\n---\nx\n"},
    ]
    return {"files": files, "package": {"key": key, "versao": "2.0.0", "fonte": fonte, "version_id": "v-2"}}


@pytest.fixture
def served(monkeypatch):
    box = {"data": _tree(), "status": 200, "calls": []}

    def fake_http(method, creds, path, body=None, query=None, timeout=60.0):
        box["calls"].append((method, path))
        return sc.HttpResult(status=box["status"], data=box["data"], text=json.dumps(box["data"]))

    monkeypatch.setattr(sc, "http_json", fake_http)
    refreshed = []
    from tools.noctus.dev import agent_context_cache

    monkeypatch.setattr(agent_context_cache, "refresh", lambda **kw: refreshed.append(kw) or {"refreshed": [kw.get("agent_name")]})
    box["refreshed"] = refreshed
    return box


def test_dry_run_plans_and_writes_nothing(served, tmp_path):
    out = ax.agent_export("media-analyst", worktree_path=str(tmp_path), env=ENV)
    assert out["status"] == "planned" and ".claude/agents/media-analyst.md" in out["to_write"]
    assert not (tmp_path / ".claude").exists() and served["refreshed"] == []
    assert served["calls"] == [("GET", "/api/agent-packages/media-analyst/latest")]


def test_confirm_writes_removes_stale_skills_refreshes_cache_and_clears_pending(served, tmp_path):
    stale = tmp_path / "agents/media-analyst/skills/antiga/SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("old")
    ax._write_mirror_marker(tmp_path, [{"key": "media-analyst", "motivo": "stale"}, {"key": "outro", "motivo": "x"}])
    out = ax.agent_export("media-analyst", confirm=True, worktree_path=str(tmp_path), env=ENV)
    assert out["status"] == "exported" and out["to_remove"] == ["agents/media-analyst/skills/antiga/SKILL.md"]
    assert (tmp_path / ".claude/agents/media-analyst.md").read_text().startswith("---\nname: media-analyst\n")
    assert not stale.exists() and served["refreshed"][0]["agent_name"] == "media-analyst"
    assert out["pending_cleared"] and [f["key"] for f in ax._read_mirror_marker(tmp_path)] == ["outro"]
    again = ax.agent_export("media-analyst", confirm=True, worktree_path=str(tmp_path), env=ENV)
    assert again["status"] == "up_to_date"


def test_a_git_source_package_is_refused(served, tmp_path):
    served["data"] = _tree(fonte="git")
    out = ax.agent_export("media-analyst", confirm=True, worktree_path=str(tmp_path), env=ENV)
    assert out["status"] == "invalid_tree" and "agent_pull" in out["errors"][0] and not (tmp_path / ".claude").exists()


def test_a_tree_whose_body_does_not_hash_is_refused(served, tmp_path):
    served["data"] = _tree(tamper=True)
    out = ax.agent_export("media-analyst", confirm=True, worktree_path=str(tmp_path), env=ENV)
    assert out["status"] == "invalid_tree" and "compiled_hash" in " ".join(out["errors"])


def test_a_path_outside_the_mirror_is_refused(served, tmp_path):
    served["data"]["files"].append({"path": "scripts/hooks/pre-commit", "conteudo": "rm -rf /"})
    out = ax.agent_export("media-analyst", confirm=True, worktree_path=str(tmp_path), env=ENV)
    assert out["status"] == "invalid_tree" and not (tmp_path / "scripts").exists()


def test_http_refusal_is_reported_and_the_token_never_echoed(served, tmp_path):
    served["status"], served["data"] = 404, {"detail": "Agente não encontrado.", "code": "agent_not_found"}
    out = ax.agent_export("media-analyst", worktree_path=str(tmp_path), env=ENV)
    assert out["ok"] is False and out["status"] == "agent_not_found"
    assert "pk_secret_never_echoed" not in json.dumps(out)


def _commit_mirror(tmp_path):
    p = tmp_path / ".claude/agents/media-analyst.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_tree()["files"][0]["conteudo"])


def test_mirror_check_current_stale_and_unverified(served, tmp_path):
    _commit_mirror(tmp_path)
    assert ax.mirror_check(str(tmp_path), env=ENV)["results"]["media-analyst"]["status"] == "current"
    assert not (tmp_path / ax.MIRROR_MARKER).exists()
    served["data"]["package"]["version_id"] = "v-3"
    out = ax.mirror_check(str(tmp_path), env=ENV)
    assert out["results"]["media-analyst"]["status"] == "stale" and not out["ok"]
    assert ax._read_mirror_marker(tmp_path)[0]["motivo"] == "stale"
    off = ax.mirror_check(str(tmp_path), env={}, env_file=str(tmp_path / "nope.env"))
    assert off["results"]["media-analyst"]["status"] == "unverified"  # never "current" without proof
    assert "pk_secret" not in json.dumps(out)


def test_mirror_check_without_mirrors_is_a_no_op(served, tmp_path):
    assert ax.mirror_check(str(tmp_path), env=ENV)["status"] == "no_mirrors" and served["calls"] == []
