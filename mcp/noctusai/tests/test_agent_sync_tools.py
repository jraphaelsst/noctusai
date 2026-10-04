"""Tests for the agent-packages wave-3 client side: agent_package_publish, agent_context_sync,
agent_learnings_push, agent_learnings_promote, agent_pull install_hook, the hook runner and the hook scripts.

A real HTTP fixture server (stdlib, thread) stands in for Agent Studio — the tools talk real HTTP to it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.test_agent_package_build import KEY, LEARN_HEAD, UP_ROW_A, make_package
from tools.noctus.dev import agent_context_sync as acs
from tools.noctus.dev import agent_learnings_promote as alp
from tools.noctus.dev import agent_learnings_push as alpush
from tools.noctus.dev import agent_package_build as apb
from tools.noctus.dev import agent_package_publish as app_
from tools.noctus.dev import agent_pull as ap
from tools.noctus.dev import agent_sync_client as cl

REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_ROOT = REPO_ROOT / "mcp" / "noctusai"
TOKEN = "pk_SECRET_TOKEN_123"


# ── fixture HTTP server ─────────────────────────────────────────────────────


class Studio:
    """Programmable fake. ``routes[(METHOD, path)]`` = (status, obj) | callable(body)->(status, obj) | list of those
    (consumed in order, last repeats). Records every call."""

    def __init__(self) -> None:
        self.routes: dict = {}
        self.calls: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                body = json.loads(raw) if raw else None
                path, _, qs = self.path.partition("?")
                outer.calls.append({"method": self.command, "path": path, "query": qs, "body": body,
                                    "auth": self.headers.get("Authorization")})
                route = outer.routes.get((self.command, path), (404, {"detail": "no route", "code": "not_found"}))
                if isinstance(route, list):
                    route = route.pop(0) if len(route) > 1 else route[0]
                status, obj = route(body) if callable(route) else route
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_PATCH = _do

            def log_message(self, *a):  # silence
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def env(self, **extra):
        return {"NOCTUS_AGENTS_URL": self.url, "NOCTUS_AGENTS_TOKEN": TOKEN, **extra}

    def paths(self):
        return [(c["method"], c["path"]) for c in self.calls]

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def studio():
    s = Studio()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NOCTUS_AGENTS_LOCK_DIR", str(tmp_path / "locks"))
    for k in ("NOCTUS_AGENTS_URL", "NOCTUS_AGENTS_TOKEN", "NOCTUS_AGENTS_ENV_FILE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


# ── credentials / redaction ─────────────────────────────────────────────────


def test_credentials_env_beats_file_and_repr_hides_token(tmp_path):
    f = tmp_path / "agents.env"
    f.write_text('# c\nexport NOCTUS_AGENTS_URL="https://file.example/"\nNOCTUS_AGENTS_TOKEN=pk_file\n')
    c = cl.load_credentials({}, f)
    assert c.url == "https://file.example" and c.token == "pk_file" and c.source == "file"
    c2 = cl.load_credentials({"NOCTUS_AGENTS_TOKEN": TOKEN}, f)
    assert c2.token == TOKEN and c2.source == "env+file"
    assert TOKEN not in repr(c2) and "<redacted>" in repr(c2)
    assert cl.load_credentials({}, tmp_path / "missing.env") is None


def test_default_env_file_is_home_config(tmp_path, monkeypatch):
    d = tmp_path / "home" / ".config" / "noctus"
    d.mkdir(parents=True)
    (d / "agents.env").write_text("NOCTUS_AGENTS_URL=https://x.test\nNOCTUS_AGENTS_TOKEN=pk_home\n")
    assert cl.load_credentials({}).token == "pk_home"


def test_agent_lock_times_out_when_held(tmp_path):
    with cl.agent_lock("a-key", tmp_path):
        with pytest.raises(cl.SyncError) as ei:
            with cl.agent_lock("a-key", tmp_path, timeout_s=0.3):
                pass
        assert ei.value.code == "lock_timeout"
    with cl.agent_lock("a-key", tmp_path, timeout_s=0.3):  # released
        pass


# ── agent_package_publish ───────────────────────────────────────────────────

EVAL_OK = {"id": "run-1", "status": "concluida", "score": 0.9, "limiar": 0.8, "total": 3, "aprovados": 3,
           "completa": True, "custo_usd": 0.1}


@pytest.fixture
def pk(tmp_path):
    p = tmp_path / "packages"
    make_package(p)
    return p


def publish(studio, pk, **kw):
    return app_.agent_package_publish(KEY, packages_dir=str(pk), repo_root=str(REPO_ROOT), env=studio.env(),
                                      env_file=str(pk / "none.env"), poll_interval_s=0, sleep=lambda s: None, **kw)


def happy_routes(studio, gate=EVAL_OK):
    b = f"/api/studio/agents/{KEY}"
    studio.routes = {
        ("POST", f"{b}/import"): (200, {"rascunho": {"version_id": "v-1"}}),
        ("POST", f"{b}/evals/runs"): (202, {"id": "run-1", "status": "pendente"}),
        ("GET", f"{b}/evals/runs/run-1"): [(200, {"id": "run-1", "status": "executando"}), (200, gate)],
        ("POST", f"{b}/draft/publish"): (200, {"id": "v-1", "status": "publicada"}),
    }


def test_publish_dry_run_builds_but_sends_nothing(studio, pk):
    r = publish(studio, pk)
    assert r["ok"] and r["status"] == "planned" and r["credentials"] == "present"
    assert studio.calls == []
    assert (pk / KEY / "dist" / "bundle.json").is_file()


def test_publish_confirm_happy_path_orders_calls_and_sends_claude_tree(studio, pk):
    happy_routes(studio)
    r = publish(studio, pk, confirm=True)
    assert r["ok"] and r["status"] == "published", r
    b = f"/api/studio/agents/{KEY}"
    assert studio.paths() == [("POST", f"{b}/import"), ("POST", f"{b}/evals/runs"), ("GET", f"{b}/evals/runs/run-1"),
                              ("GET", f"{b}/evals/runs/run-1"), ("POST", f"{b}/draft/publish")]
    assert all(c["auth"] == f"Bearer {TOKEN}" for c in studio.calls)
    imported = studio.calls[0]["body"]
    assert imported["versao"]["package_sha"] == r["sha"] and imported["claude"]
    assert studio.calls[1]["body"] == {"version_id": "v-1"}
    assert TOKEN not in json.dumps(r)


def test_publish_gate_failure_leaves_draft_and_reports_score(studio, pk):
    happy_routes(studio, gate={**EVAL_OK, "score": 0.5})
    r = publish(studio, pk, confirm=True)
    assert r["ok"] and r["status"] == "gate_failed"
    assert r["eval"]["score"] == 0.5 and r["eval"]["limiar"] == 0.8
    assert ("POST", f"/api/studio/agents/{KEY}/draft/publish") not in studio.paths()
    assert "score=0.5" in r["warnings"][0] and "limiar=0.8" in r["warnings"][0]


def test_publish_incomplete_run_does_not_pass_gate(studio, pk):
    happy_routes(studio, gate={**EVAL_OK, "completa": False})
    assert publish(studio, pk, confirm=True)["status"] == "gate_failed"


def test_publish_semver_already_published_is_reported_not_failed(studio, pk):
    studio.routes = {("POST", f"/api/studio/agents/{KEY}/import"): (409, {"detail": "x", "code": "semver_published"})}
    r = publish(studio, pk, confirm=True)
    assert r["ok"] and r["status"] == "already_published" and "bump" in r["warnings"][0]
    assert len(studio.calls) == 1


def test_publish_user_only_route_is_reported_as_auth_insufficient(studio, pk):
    studio.routes = {("POST", f"/api/studio/agents/{KEY}/import"): (403, {"detail": "no", "code": "user_required"})}
    r = publish(studio, pk, confirm=True)
    assert not r["ok"] and r["status"] == "failed" and r["error_code"] == "auth_insufficient"
    assert "user-only" in r["errors"][0]


def test_publish_eval_timeout_leaves_draft(studio, pk):
    b = f"/api/studio/agents/{KEY}"
    studio.routes = {
        ("POST", f"{b}/import"): (200, {"rascunho": {"version_id": "v-1"}}),
        ("POST", f"{b}/evals/runs"): (202, {"id": "run-1", "status": "pendente"}),
        ("GET", f"{b}/evals/runs/run-1"): (200, {"id": "run-1", "status": "executando"}),
    }
    r = publish(studio, pk, confirm=True, eval_timeout_s=0.0)
    assert not r["ok"] and r["error_code"] == "eval_timeout"


def test_publish_missing_credentials_is_not_configured(pk):
    r = app_.agent_package_publish(KEY, confirm=True, packages_dir=str(pk), repo_root=str(REPO_ROOT), env={},
                                   env_file=str(pk / "none.env"))
    assert not r["ok"] and r["error_code"] == "not_configured"


def test_publish_network_error_never_leaks_token(pk):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    r = app_.agent_package_publish(KEY, confirm=True, packages_dir=str(pk), repo_root=str(REPO_ROOT),
                                   env={"NOCTUS_AGENTS_URL": f"http://127.0.0.1:{port}/{TOKEN}",
                                        "NOCTUS_AGENTS_TOKEN": TOKEN}, env_file=str(pk / "none.env"))
    assert not r["ok"] and r["error_code"] == "network"
    assert TOKEN not in json.dumps(r)


def test_publish_logs_never_contain_token(studio, pk, caplog):
    caplog.set_level(logging.DEBUG)
    happy_routes(studio)
    publish(studio, pk, confirm=True)
    assert TOKEN not in caplog.text


def test_publish_invalid_package_reports_errors(studio, pk):
    (pk / KEY / "CHANGELOG.md").write_text("# c\n")
    r = publish(studio, pk, confirm=True)
    assert not r["ok"] and r["status"] == "invalid" and studio.calls == []


# ── agent_context_sync ──────────────────────────────────────────────────────

GHP = "ghp_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bD1fH3jK5"


def _w(p: Path, text: str | bytes = "x\n") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")


def make_consumer(tmp_path, project=True, agentes=(KEY, "mobile-dev")) -> Path:
    repo = tmp_path / "consumer"
    lock = {"formato": "noctus.agents-lock/v1", "agents": [{"key": KEY, "versao": "0.1.0", "sha": "a"}]}
    if project:
        lock["project"] = {"slug": "limiar", "agentes": list(agentes), "fontes": {
            "docs": ["docs/**/*.md", "CLAUDE.md"], "codigo": ["src/**/*.ts", "package.json"],
            "quadro": "docs/design/decision-board.json"}}
    _w(repo / "agents.lock.json", json.dumps(lock))
    _w(repo / "CLAUDE.md", "# Limiar\n")
    _w(repo / "docs/a.md", "# A\nolá\n")
    _w(repo / "src/x.ts", "export const x = 1\n")
    _w(repo / "src/deep/y.ts", "export const y = 2\n")
    _w(repo / "package.json", '{"name": "limiar"}\n')
    _w(repo / "docs/design/decision-board.json", '{"itens": []}\n')
    return repo


def sources_ok(body):
    return 200, {"projeto": "limiar", "total": len(body), "criados": len(body), "atualizados": 0,
                 "inalterados": 0, "removidos": 1, "ignorados": [], "avisos": []}


def sync(studio, repo, **kw):
    return acs.agent_context_sync(str(repo), env=studio.env(), env_file=str(repo / "none.env"), **kw)


def test_context_sync_no_project_block_invents_nothing(studio, tmp_path):
    repo = make_consumer(tmp_path, project=False)
    r = sync(studio, repo, confirm=True)
    assert r["ok"] and r["status"] == "no_project_block" and studio.calls == []


def test_context_sync_dry_run_collects_and_excludes(studio, tmp_path):
    repo = make_consumer(tmp_path)
    _w(repo / "docs/big.md", "x" * (201 * 1024))
    _w(repo / "docs/.env.md", "A=1\n")  # `.env*` basename: hard-excluded even when a glob matches
    _w(repo / "docs/notes.md", "ok\n")
    _w(repo / "docs/node_modules/pkg/readme.md", "dep\n")
    _w(repo / "src/blob.ts", b"\x00\x01\x02")
    r = sync(studio, repo)
    assert r["status"] == "planned" and studio.calls == []
    assert set(r["paths"]) == {"CLAUDE.md", "docs/a.md", "docs/notes.md", "src/x.ts", "src/deep/y.ts", "package.json",
                               "docs/design/decision-board.json"}
    reasons = {s["path"]: s["motivo"] for s in r["skipped"]}
    assert reasons["docs/big.md"] == "too_large" and reasons["docs/.env.md"] == "env_file"
    assert reasons["src/blob.ts"] == "binary"
    assert "docs/node_modules/pkg/readme.md" not in r["paths"]  # pruned from the walk, never a candidate


@pytest.mark.parametrize("rel,why", [(".env", "env_file"), (".env.local", "env_file"), ("a/server.key", "forbidden_suffix"),
                                     ("node_modules/x/y.md", "forbidden_directory"), ("img/a.png", "forbidden_suffix"),
                                     ("secrets.json", "forbidden_name"), ("docs/ok.md", None)])
def test_forbidden_reason(rel, why):
    assert acs.forbidden_reason(rel) == why


def test_context_sync_confirm_puts_full_manifest_per_agent(studio, tmp_path):
    repo = make_consumer(tmp_path)
    for k in (KEY, "mobile-dev"):
        studio.routes[("PUT", f"/api/studio/agents/{k}/projects/limiar/sources")] = sources_ok
    r = sync(studio, repo, confirm=True)
    assert r["ok"] and r["status"] == "synced", r
    assert [c["path"] for c in studio.calls] == [f"/api/studio/agents/{k}/projects/limiar/sources" for k in (KEY, "mobile-dev")]
    body = studio.calls[0]["body"]
    assert isinstance(body, list) and len(body) == 6
    item = next(i for i in body if i["path"] == "docs/a.md")
    assert item["sha256"] == hashlib.sha256("# A\nolá\n".encode("utf-8")).hexdigest() and item["tipo"] == "doc"
    assert next(i for i in body if i["path"] == "docs/design/decision-board.json")["tipo"] == "quadro"
    assert next(i for i in body if i["path"] == "src/x.ts")["tipo"] == "codigo"
    assert r["summary"] == {"created": 12, "updated": 0, "unchanged": 0, "deleted": 2, "skipped": 0}
    assert all(c["auth"] == f"Bearer {TOKEN}" for c in studio.calls)


def test_context_sync_secret_scan_aborts_and_sends_nothing(studio, tmp_path):
    repo = make_consumer(tmp_path)
    _w(repo / "docs/leak.md", f"token {GHP}\n")
    r = sync(studio, repo, confirm=True)
    assert not r["ok"] and r["error_code"] == "secret_detected" and studio.calls == []
    assert r["secrets"][0]["path"] == "docs/leak.md"
    assert GHP not in json.dumps(r)  # pattern NAME only, never the value


def test_context_sync_empty_manifest_refused(studio, tmp_path):
    repo = make_consumer(tmp_path)
    lock = json.loads((repo / "agents.lock.json").read_text())
    lock["project"]["fontes"] = {"docs": ["nothing/**/*.md"]}
    (repo / "agents.lock.json").write_text(json.dumps(lock))
    r = sync(studio, repo, confirm=True)
    assert not r["ok"] and r["error_code"] == "empty_manifest" and studio.calls == []


def test_context_sync_respects_gitignore_in_git_repos(studio, tmp_path):
    repo = make_consumer(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _w(repo / ".gitignore", "docs/private.md\n")
    _w(repo / "docs/private.md", "nao\n")
    assert "docs/private.md" not in sync(studio, repo)["paths"]


def test_context_sync_server_error_is_failure_with_code(studio, tmp_path):
    repo = make_consumer(tmp_path, agentes=(KEY,))
    studio.routes[("PUT", f"/api/studio/agents/{KEY}/projects/limiar/sources")] = (
        422, {"detail": "x", "code": "forbidden_path"})
    r = sync(studio, repo, confirm=True)
    assert not r["ok"] and r["error_code"] == "sync_failed" and "forbidden_path" in r["errors"][0]


def test_context_sync_missing_token_not_configured(tmp_path):
    repo = make_consumer(tmp_path)
    r = acs.agent_context_sync(str(repo), confirm=True, env={}, env_file=str(tmp_path / "none.env"))
    assert not r["ok"] and r["error_code"] == "not_configured"


# ── agent_learnings_push ────────────────────────────────────────────────────

ROW_B = "| 2026-10-02 | decisão | Prefira Y | PR 12 | novo |\n"


def make_learnings_consumer(tmp_path, project=True) -> Path:
    repo = make_consumer(tmp_path, project=project)
    _w(repo / f"agents/{KEY}/LEARNINGS.md", "# L\n\n" + LEARN_HEAD + UP_ROW_A + ROW_B + "| 2026 | nonsense | z | e | new |\n")
    return repo


def push(studio, repo, **kw):
    return alpush.agent_learnings_push(str(repo), env=studio.env(), env_file=str(repo / "none.env"), **kw)


def test_learnings_push_dry_run_and_no_project_block(studio, tmp_path):
    repo = make_learnings_consumer(tmp_path)
    r = push(studio, repo)
    assert r["status"] == "planned" and r["rows"] == {KEY: 2} and len(r["parse_errors"]) == 1 and studio.calls == []
    r2 = push(studio, make_learnings_consumer(tmp_path / "b", project=False), confirm=True)
    assert r2["status"] == "no_project_block" and studio.calls == []


def test_learnings_push_confirm_posts_rows_with_wave1_row_sha(studio, tmp_path):
    repo = make_learnings_consumer(tmp_path)
    studio.routes[("POST", f"/api/studio/agents/{KEY}/learnings")] = (
        200, {"recebidas": 2, "novas": 1, "duplicadas": 1, "novos": []})
    r = push(studio, repo, confirm=True)
    assert r["ok"] and r["status"] == "pushed" and r["pushed"][KEY] == {"new": 1, "duplicate": 1}
    body = studio.calls[0]["body"]
    assert body["project_slug"] == "limiar" and len(body["rows"]) == 2
    assert body["rows"][0]["row_sha"] == apb.row_sha("2026-10-01", "Nunca assuma X")
    assert body["rows"][1]["tipo"] == "decisão" and studio.calls[0]["auth"] == f"Bearer {TOKEN}"


def test_learnings_push_server_error_is_failure(studio, tmp_path):
    repo = make_learnings_consumer(tmp_path)
    studio.routes[("POST", f"/api/studio/agents/{KEY}/learnings")] = (403, {"detail": "n", "code": "scope_missing"})
    r = push(studio, repo, confirm=True)
    assert not r["ok"] and r["error_code"] == "push_failed" and "scope" in r["errors"][0]


# ── agent_learnings_promote ─────────────────────────────────────────────────


def accepted(*rows):
    return (200, {"items": [{"id": f"i{n}", "project_slug": "limiar", "row_sha": "x", "data": d, "tipo": t, "texto": x,
                             "evidencia": e, "row_status": "novo", "status": "aceito", "nota": None, "reviewed_by": None,
                             "reviewed_at": None, "created_at": "2026-10-03T00:00:00Z"}
                            for n, (d, t, x, e) in enumerate(rows)]})


def promote(studio, pk, **kw):
    return alp.agent_learnings_promote(KEY, packages_dir=str(pk), repo_root=str(REPO_ROOT), env=studio.env(),
                                       env_file=str(pk / "none.env"), **kw)


def test_promote_dry_run_shows_diff_then_confirm_appends_idempotently(studio, pk):
    studio.routes[("GET", f"/api/studio/agents/{KEY}/learnings")] = accepted(
        ("2026-10-01", "pitfall", "Nunca assuma X", "commit abc"),  # already in the package
        ("2026-10-03", "practice", "Documente o corpo do doc sempre", "sessão"))
    before = (pk / KEY / "LEARNINGS.md").read_text()
    r = promote(studio, pk)
    assert r["status"] == "planned" and r["accepted"] == 2 and r["already_present"] == 1 and len(r["added"]) == 1
    assert "+| 2026-10-03 | practice | Documente o corpo do doc sempre | sessão | promovido |" in r["diff"]
    assert (pk / KEY / "LEARNINGS.md").read_text() == before
    assert "status=aceito" in studio.calls[0]["query"] and studio.calls[0]["auth"] == f"Bearer {TOKEN}"
    assert "knowledge/base/doc-um.md" in r["added"][0]["suggested_knowledge"]
    r2 = promote(studio, pk, confirm=True)
    assert r2["status"] == "promoted" and "Documente o corpo" in (pk / KEY / "LEARNINGS.md").read_text()
    assert apb.parse_learnings((pk / KEY / "LEARNINGS.md").read_text())[1] == []
    assert promote(studio, pk, confirm=True)["status"] == "up_to_date"


def test_promote_missing_scope_or_package_fail_loud(studio, pk):
    studio.routes[("GET", f"/api/studio/agents/{KEY}/learnings")] = (403, {"detail": "n", "code": "scope_missing"})
    r = promote(studio, pk)
    assert not r["ok"] and r["error_code"] == "auth_insufficient"
    bad = alp.agent_learnings_promote("nope", packages_dir=str(pk), repo_root=str(REPO_ROOT), env=studio.env())
    assert not bad["ok"] and bad["status"] == "invalid"


# ── agent_pull install_hook ─────────────────────────────────────────────────


def pull_hook(pk, repo, **kw):
    return ap.agent_pull(KEY, str(repo), packages_dir=str(pk), repo_root=str(REPO_ROOT), install_hook=True, **kw)


def git_repo(tmp_path) -> Path:
    repo = tmp_path / "gitconsumer"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def hooks_path(repo):
    return subprocess.run(["git", "-C", str(repo), "config", "--get", "core.hooksPath"], capture_output=True, text=True).stdout.strip()


def test_install_hook_dry_run_writes_nothing(pk, tmp_path):
    repo = git_repo(tmp_path)
    r = pull_hook(pk, repo)
    assert r["status"] == "planned" and r["install_hook"]["hook"] == "install" and r["install_hook"]["hooks_path"] == "set"
    assert not (repo / ".githooks").exists() and hooks_path(repo) == ""


def test_install_hook_installs_sets_hookspath_once_and_is_idempotent(pk, tmp_path):
    repo = git_repo(tmp_path)
    r = pull_hook(pk, repo, confirm=True)
    hook = repo / ".githooks" / "pre-push"
    assert r["status"] == "pulled" and hook.is_file() and os.access(hook, os.X_OK)
    assert ap.HOOK_MARK in hook.read_text() and hooks_path(repo) == ".githooks"
    assert ".agents-sync-pending" in (repo / ".gitignore").read_text().splitlines()
    r2 = pull_hook(pk, repo, confirm=True)
    assert r2["install_hook"]["hook"] == "unchanged" and r2["install_hook"]["hooks_path"] == "ok"
    assert (repo / ".gitignore").read_text().count(".agents-sync-pending") == 1


def test_install_hook_never_overwrites_foreign_hook_or_existing_hookspath(pk, tmp_path):
    repo = git_repo(tmp_path)
    _w(repo / ".githooks/pre-push", "#!/bin/sh\necho mine\n")
    r = pull_hook(pk, repo, confirm=True)
    assert r["install_hook"]["hook"] == "exists_foreign" and "mine" in (repo / ".githooks/pre-push").read_text()
    assert hooks_path(repo) == "" and r["install_hook"]["notes"]
    repo2 = git_repo(tmp_path / "two")
    subprocess.run(["git", "-C", str(repo2), "config", "core.hooksPath", "husky"], check=True)
    r2 = pull_hook(pk, repo2, confirm=True)
    assert r2["install_hook"]["hooks_path"] == "conflict:husky" and hooks_path(repo2) == "husky"
    assert (repo2 / ".githooks/pre-push").is_file()  # file installed, activation left to the owner
    assert any("core.hooksPath" in n for n in r2["install_hook"]["notes"])


# ── runner + consumer hook (end to end through real processes) ──────────────


def run_runner(repo, env_extra, mode="consumer", extra=()):
    env = {**os.environ, "NOCTUS_HOME": str(REPO_ROOT), **env_extra}
    return subprocess.run([sys.executable, str(REPO_ROOT / "scripts/agent-hooks/agent_sync_runner.py"), mode, *extra],
                          capture_output=True, text=True, env=env, timeout=120)


def test_runner_failure_is_loud_writes_marker_exit0_then_success_clears(studio, tmp_path):
    repo = make_learnings_consumer(tmp_path)
    lock = json.loads((repo / "agents.lock.json").read_text())
    lock["project"]["agentes"] = [KEY]
    (repo / "agents.lock.json").write_text(json.dumps(lock))
    put = f"/api/studio/agents/{KEY}/projects/limiar/sources"
    studio.routes = {("PUT", put): (500, {"detail": "boom", "code": "internal"}),
                     ("POST", f"/api/studio/agents/{KEY}/learnings"): (200, {"novas": 0, "duplicadas": 2})}
    env = studio.env(HOME=str(tmp_path / "home"), NOCTUS_AGENTS_LOCK_DIR=str(tmp_path / "locks"))
    p = run_runner(repo, env, extra=("--repo", str(repo)))
    assert p.returncode == 0
    assert "FAILED" in p.stderr and "context_sync" in p.stderr and TOKEN not in p.stderr + p.stdout
    marker = cl.read_marker(repo)
    assert marker and marker["failures"][0]["step"] == "context_sync" and TOKEN not in json.dumps(marker)
    studio.routes[("PUT", put)] = sources_ok
    p2 = run_runner(repo, env, extra=("--repo", str(repo)))
    assert p2.returncode == 0 and "retrying" in p2.stderr and "marker cleared" in p2.stderr
    assert not (repo / ".agents-sync-pending").exists()


def test_runner_without_credentials_is_loud_and_marks(tmp_path):
    repo = make_learnings_consumer(tmp_path)
    p = run_runner(repo, {"HOME": str(tmp_path / "home")}, extra=("--repo", str(repo)))
    assert p.returncode == 0 and "FAILED" in p.stderr and "not_configured" in p.stderr
    assert (repo / ".agents-sync-pending").is_file()


def _fake_noctus_home(tmp_path) -> Path:
    home = tmp_path / "noctus_home"
    (home / "mcp/noctusai/.venv/bin").mkdir(parents=True)
    (home / "mcp/noctusai/.venv/bin/python").symlink_to(sys.executable)
    for entry in MCP_ROOT.iterdir():
        if entry.name != ".venv":
            (home / "mcp/noctusai" / entry.name).symlink_to(entry)
    (home / "scripts").mkdir()
    (home / "scripts/agent-hooks").symlink_to(REPO_ROOT / "scripts/agent-hooks")
    (home / "seed/lib").mkdir(parents=True)
    (home / "seed/lib/backend").symlink_to(REPO_ROOT / "seed/lib/backend")
    return home


def run_hook(repo, env_extra):
    # Hermetic: never read the developer's real ~/.config/noctus/agents.env (it may define NOCTUS_HOME).
    env = {k: v for k, v in os.environ.items() if k not in ("NOCTUS_HOME", "XDG_CONFIG_HOME")}
    env["HOME"] = str(Path(repo).parent / "hook-home")
    env.update(env_extra)
    return subprocess.run(["bash", str(REPO_ROOT / "scripts/agent-hooks/consumer-pre-push.sh")], cwd=repo, input="",
                          capture_output=True, text=True, env=env, timeout=120)


def test_consumer_hook_without_noctus_home_never_blocks_but_marks(tmp_path):
    repo = git_repo(tmp_path)
    p = run_hook(repo, {})
    assert p.returncode == 0 and "NOCTUS_HOME is not set" in p.stderr and "NOT blocked" in p.stderr
    assert (repo / ".agents-sync-pending").is_file()
    p2 = run_hook(repo, {"NOCTUS_HOME": str(tmp_path / "nowhere")})
    assert p2.returncode == 0 and "toolkit not found" in p2.stderr


def test_consumer_hook_reads_noctus_home_from_the_env_file(tmp_path):
    repo = git_repo(tmp_path)
    home = tmp_path / "hook-home" / ".config" / "noctus"
    home.mkdir(parents=True)
    (home / "agents.env").write_text(f"NOCTUS_AGENTS_URL=http://x\nNOCTUS_HOME={tmp_path / 'from-file'}\n")
    p = run_hook(repo, {"HOME": str(tmp_path / "hook-home")})
    assert p.returncode == 0 and "NOCTUS_HOME is not set" not in p.stderr
    assert f"NOCTUS_HOME={tmp_path / 'from-file'}" in p.stderr  # it used the file's value (toolkit not there → loud, not silent)


def test_consumer_hook_end_to_end_syncs_then_clears_marker(studio, tmp_path):
    repo = make_learnings_consumer(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    lock = json.loads((repo / "agents.lock.json").read_text())
    lock["project"]["agentes"] = [KEY]
    (repo / "agents.lock.json").write_text(json.dumps(lock))
    studio.routes = {("PUT", f"/api/studio/agents/{KEY}/projects/limiar/sources"): sources_ok,
                     ("POST", f"/api/studio/agents/{KEY}/learnings"): (200, {"novas": 2, "duplicadas": 0})}
    (repo / ".agents-sync-pending").write_text("{}\n")
    home = _fake_noctus_home(tmp_path)
    p = run_hook(repo, {**studio.env(), "NOCTUS_HOME": str(home), "HOME": str(tmp_path / "home"),
                        "NOCTUS_AGENTS_LOCK_DIR": str(tmp_path / "locks")})
    assert p.returncode == 0, p.stderr
    assert not (repo / ".agents-sync-pending").exists() and len(studio.calls) == 2


# ── noc pre-push leg ────────────────────────────────────────────────────────


def _noc_repo(tmp_path):
    repo = tmp_path / "noc"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/agent-hooks").symlink_to(REPO_ROOT / "scripts/agent-hooks")
    g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    _w(repo / "README.md", "r\n")
    g("add", "-A")
    g("commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return repo, g, base


def _stub_python(tmp_path) -> Path:
    stub = tmp_path / "stubpy"
    stub.write_text(f'#!/usr/bin/env bash\necho "$@" >> "{tmp_path}/stub.log"\n')
    stub.chmod(0o755)
    return stub


def _head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def run_noc_leg(repo, stub, lines):
    return subprocess.run(["bash", str(REPO_ROOT / "scripts/agent-hooks/noc-pre-push-publish.sh"), str(stub), str(repo)],
                          input=lines, capture_output=True, text=True, timeout=60)


def test_noc_leg_is_a_noop_when_nothing_under_packages_changed(tmp_path):
    repo, g, base = _noc_repo(tmp_path)
    _w(repo / "docs/x.md", "x\n")
    g("add", "-A")
    g("commit", "-qm", "other")
    stub = _stub_python(tmp_path)
    p = run_noc_leg(repo, stub, f"refs/heads/dev {_head(repo)} refs/heads/dev {base}\n")
    assert p.returncode == 0 and p.stderr == "" and not (tmp_path / "stub.log").exists()


def test_noc_leg_publishes_changed_keys_only_for_dev_pushes_and_excludes_dist(tmp_path):
    repo, g, base = _noc_repo(tmp_path)
    _w(repo / "products/agents/packages/mobile-dev/package.yaml", "a\n")
    _w(repo / "products/agents/packages/nos-no-limiar/sections/10-a.md", "a\n")
    _w(repo / "products/agents/packages/ghost/dist/bundle.json", "{}\n")
    g("add", "-Af")
    g("commit", "-qm", "pk")
    stub = _stub_python(tmp_path)
    run_noc_leg(repo, stub, f"refs/heads/feat/x {_head(repo)} refs/heads/feat/x {base}\n")
    assert not (tmp_path / "stub.log").exists()  # not a dev push
    p = run_noc_leg(repo, stub, f"refs/heads/dev {_head(repo)} refs/heads/dev {base}\n")
    assert p.returncode == 0
    log = (tmp_path / "stub.log").read_text()
    assert "publish" in log and "--keys mobile-dev,nos-no-limiar" in log and "ghost" not in log


def test_noc_leg_failure_never_blocks_and_marks_for_retry(tmp_path):
    repo, g, base = _noc_repo(tmp_path)
    _w(repo / "products/agents/packages/mobile-dev/package.yaml", "a\n")
    g("add", "-Af")
    g("commit", "-qm", "pk")
    p = run_noc_leg(repo, tmp_path / "does-not-exist", f"refs/heads/dev {_head(repo)} refs/heads/dev {base}\n")
    assert p.returncode == 0 and "NOT blocked" in p.stderr
    marker = json.loads((repo / ".agents-sync-pending").read_text())
    assert marker["keys"] == ["mobile-dev"]
    stub = _stub_python(tmp_path)  # a later push with NO package change still retries the marker
    run_noc_leg(repo, stub, f"refs/heads/dev {_head(repo)} refs/heads/dev {_head(repo)}\n")
    assert "publish" in (tmp_path / "stub.log").read_text()


def test_existing_pre_push_still_syntactically_valid_and_calls_leg_last():
    text = (REPO_ROOT / "scripts/hooks/pre-push").read_text()
    assert subprocess.run(["bash", "-n", str(REPO_ROOT / "scripts/hooks/pre-push")]).returncode == 0
    assert text.rstrip().endswith("exit 0")
    assert text.index("noc-pre-push-publish.sh") > text.index('if [[ "$blocked" -ne 0 ]]')


# ── nao_segredos: human-acknowledged scanner hits (fingerprint, exact token) ─────────────────────────────

def _ack_repo(tmp_path, files, nao_segredos=None):
    repo = tmp_path / "consumer"
    for rel, text in files.items():
        _w(repo / rel, text)
    project = {"slug": "app", "fontes": {"docs": [], "codigo": ["src/**/*.ts"]}, "agentes": ["mobile-dev"]}
    if nao_segredos is not None:
        project["nao_segredos"] = nao_segredos
    _w(repo / "agents.lock.json", json.dumps({"formato": "noctus.agents-lock/v1", "agents": [], "project": project}))
    return repo


_FONT = "CormorantGaramond_600SemiBold"  # trips the entropy heuristic, not a secret
_REAL = "pk_" + "Q7xZ2mK9vR4tL8nB3wY6pD1sF5hJ0cGa"  # a real-looking random token


def test_entropy_false_positive_blocks_with_a_fingerprint_and_never_the_value(tmp_path):
    from tools.noctus.dev.agent_context_sync import agent_context_sync, secret_fingerprint
    repo = _ack_repo(tmp_path, {"src/fonts.ts": f"export const f = '{_FONT}';\n"})
    out = agent_context_sync(str(repo), env={})
    assert out["ok"] is False and out["error_code"] == "secret_detected"
    assert out["secrets"] == [{"path": "src/fonts.ts", "padrao": "high_entropy_token", "impressao": secret_fingerprint(_FONT)}]
    assert _FONT not in json.dumps(out)


def test_acknowledged_fingerprint_lets_that_exact_token_through(tmp_path):
    from tools.noctus.dev.agent_context_sync import agent_context_sync, secret_fingerprint
    ack = [{"impressao": secret_fingerprint(_FONT), "nota": "font family name"}]
    repo = _ack_repo(tmp_path, {"src/fonts.ts": f"export const f = '{_FONT}';\n"}, ack)
    out = agent_context_sync(str(repo), env={})
    assert out.get("error_code") != "secret_detected", out
    assert out["nao_segredos_reconhecidos"] == 1 and out["paths"] == ["src/fonts.ts"]


def test_a_real_secret_in_the_same_file_still_blocks(tmp_path):
    from tools.noctus.dev.agent_context_sync import agent_context_sync, secret_fingerprint
    ack = [{"impressao": secret_fingerprint(_FONT), "nota": "font family name"}]
    repo = _ack_repo(tmp_path, {"src/fonts.ts": f"export const f = '{_FONT}';\nconst k = '{_REAL}';\n"}, ack)
    out = agent_context_sync(str(repo), env={})
    assert out["ok"] is False and out["error_code"] == "secret_detected"
    assert [s["impressao"] for s in out["secrets"]] == [secret_fingerprint(_REAL)]
    assert _REAL not in json.dumps(out)


def test_bad_nao_segredos_entry_is_rejected_not_ignored(tmp_path):
    from tools.noctus.dev.agent_context_sync import agent_context_sync
    repo = _ack_repo(tmp_path, {"src/a.ts": "x\n"}, [{"impressao": "not-hex", "nota": ""}])
    out = agent_context_sync(str(repo), env={})
    assert out["ok"] is False and out["error_code"] == "bad_project"
