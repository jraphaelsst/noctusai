"""`noctus.dev.agent_package_publish` — noc → Studio: import + eval gate + publish (CONTRACT §F, D4).

build (``agent_package_build``) → ``POST /api/studio/agents/{key}/import`` → ``POST .../evals/runs`` on the
draft → poll ``GET .../evals/runs/{id}`` → ``POST .../draft/publish`` ONLY when the gate passes
(run ``concluida`` ∧ ``completa`` ∧ total ≥ 1 ∧ score ≥ limiar); otherwise the draft is left and the
score/threshold reported (``gate_failed``).

DRY-RUN by default (build only, no network); ``confirm=True`` sends. Credentials: see ``agent_sync_client``.
The whole pipeline holds the per-agent lock — a project-source sync moves the compiled hash and must not
interleave with import → eval → publish.

Statuses: ``planned`` · ``published`` · ``already_published`` (409 ``semver_published`` — bump ``versao``) ·
``gate_failed`` (draft left) · ``failed`` (``error_code`` set; callers write the A5 marker).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from .agent_package_build import (
    PackageError,
    StudioUnavailable,
    _SLUG_RE,
    _roots,
    build_package,
    write_dist,
)
from .agent_sync_client import (
    SyncError,
    agent_lock,
    credentials_or_error,
    http_failure,
    http_json,
    load_credentials,
)

logger = logging.getLogger("noctus.dev.agent_package_publish")

_BASE = "/api/studio/agents"
_FINAL = ("concluida", "falhou", "cancelada")
_TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})
_MAX_TRANSIENT = 5


def _fail(out: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    out.update(ok=False, status="failed", error_code=code, errors=[message])
    return out


def agent_package_publish(
    key: str,
    confirm: bool = False,
    worktree_path: str | None = None,
    packages_dir: str | None = None,
    repo_root: str | None = None,
    env: dict[str, str] | None = None,
    env_file: str | None = None,
    lock_dir: str | None = None,
    eval_timeout_s: float = 900.0,
    poll_interval_s: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not _SLUG_RE.match(key or ""):
        return {"ok": False, "status": "invalid", "errors": [f"key {key!r} must be kebab-case"]}
    pk_dir, backend = _roots(worktree_path, packages_dir, repo_root)
    root = pk_dir / key
    try:
        result = build_package(root, backend)
    except PackageError as exc:
        return {"ok": False, "status": "invalid", "key": key, "errors": exc.errors}
    except StudioUnavailable as exc:
        return {"ok": False, "status": "studio_unavailable", "key": key, "errors": [str(exc)]}
    write_dist(root, result)
    out: dict[str, Any] = {
        "ok": True, "key": key, "versao": result.versao, "sha": result.sha, "steps": ["built"],
        "credentials": "present" if load_credentials(env, env_file) else "missing",
    }
    if not confirm:
        out["status"] = "planned"
        out["plan"] = ["POST import", "POST evals/runs on the draft", "poll the run",
                       "POST draft/publish ONLY if the eval gate passes"]
        return out
    try:
        creds = credentials_or_error(env, env_file)
        with agent_lock(key, lock_dir):
            return _pipeline(out, creds, key, result.bundle, eval_timeout_s, poll_interval_s, sleep)
    except SyncError as exc:
        return _fail(out, exc.code, exc.message)


def _pipeline(out, creds, key, bundle, eval_timeout_s, poll_interval_s, sleep) -> dict[str, Any]:
    imp = http_json("POST", creds, f"{_BASE}/{key}/import", body=bundle, timeout=120)
    if imp.status == 409 and imp.code == "semver_published":
        out.update(status="already_published", steps=out["steps"] + ["import:semver_published"],
                   warnings=[f"{key} {out['versao']} is already published — bump `versao` (+ CHANGELOG) to ship changes"])
        return out
    if not imp.ok:
        raise http_failure(imp, "import")
    version_id = ((imp.data or {}).get("rascunho") or {}).get("version_id")
    if not version_id:
        raise SyncError("import_no_draft", "import succeeded but returned no rascunho.version_id")
    out["steps"].append("imported")
    out["version_id"] = version_id

    # Reuse a complete, passing run for THIS draft (e.g. a retry after a transient failure, or a push whose
    # content didn't change): ask the server to publish; it re-checks the run's compiled hash against the
    # draft's CURRENT hash and answers 409 eval_required if anything changed — then we run evals as usual.
    # The server stays the gate's sole arbiter; this only avoids paying for an identical eval run twice.
    reused = _try_publish_with_existing_run(creds, key, version_id)
    if reused is not None:
        out["steps"] += ["eval_reused", "published"]
        out["eval"] = reused["eval"]
        out["published"] = reused["published"]
        out["status"] = "published"
        return out

    run = http_json("POST", creds, f"{_BASE}/{key}/evals/runs", body={"version_id": version_id})
    if not run.ok:
        raise http_failure(run, "eval run")
    run_id = (run.data or {}).get("id")
    out["steps"].append("eval_started")
    deadline = time.monotonic() + eval_timeout_s
    state: dict[str, Any] = run.data or {}
    transient = 0
    while state.get("status") not in _FINAL:
        if time.monotonic() >= deadline:
            raise SyncError("eval_timeout", f"eval run {run_id} not finished after {eval_timeout_s:.0f}s (draft left)")
        sleep(poll_interval_s)
        # The run lives server-side: a transient edge/origin hiccup on ONE poll (502/503/504/429, network)
        # must not fail the publish (first prod push, 2026-10-04: a single Cloudflare 502). Keep polling
        # until the deadline; give up only after _MAX_TRANSIENT consecutive transient failures.
        try:
            poll = http_json("GET", creds, f"{_BASE}/{key}/evals/runs/{run_id}")
        except SyncError as exc:
            if exc.code != "network":
                raise
            transient += 1
            if transient >= _MAX_TRANSIENT:
                raise
            continue
        if not poll.ok:
            if poll.status in _TRANSIENT_STATUSES:
                transient += 1
                if transient >= _MAX_TRANSIENT:
                    raise http_failure(poll, "eval poll")
                continue
            raise http_failure(poll, "eval poll")
        transient = 0
        state = poll.data or {}
    out["eval"] = {k: state.get(k) for k in ("run_id", "status", "score", "limiar", "total", "aprovados", "completa", "custo_usd", "erro")}
    out["eval"]["run_id"] = run_id
    passes = (state.get("status") == "concluida" and bool(state.get("completa")) and (state.get("total") or 0) >= 1
              and state.get("score") is not None and state["score"] >= state.get("limiar", 1.0))
    if not passes:
        out.update(status="gate_failed", steps=out["steps"] + ["eval_done"],
                   warnings=[f"eval gate NOT passed for {key} {out['versao']}: status={state.get('status')} "
                             f"score={state.get('score')} limiar={state.get('limiar')} — draft left unpublished"])
        return out
    out["steps"].append("eval_passed")
    pub = http_json("POST", creds, f"{_BASE}/{key}/draft/publish", body={})
    if not pub.ok:
        raise http_failure(pub, "publish")
    out["steps"].append("published")
    out["published"] = {k: (pub.data or {}).get(k) for k in ("id", "numero", "status", "versao_semver")}
    out["status"] = "published"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_package_publish` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_package_publish",
        description=(
            "noc → Agent Studio publish (CONTRACT agent-packages §F): build the package, POST its bundle to "
            "/api/studio/agents/{key}/import, run evals on the draft, poll, and POST draft/publish ONLY if the eval "
            "gate passes (else leave the draft and report score/threshold). DRY-RUN by default (build only, no "
            "network); confirm=True sends. Reads NOCTUS_AGENTS_URL + NOCTUS_AGENTS_TOKEN from env or "
            "~/.config/noctus/agents.env (never the repo; token never logged). Holds a per-agent lock against a "
            "concurrent project sync. status: planned|published|already_published|gate_failed|failed."
        ),
    )
    def _agent_package_publish(key: str, confirm: bool = False, worktree_path: str | None = None) -> dict[str, Any]:
        return agent_package_publish(key=key, confirm=confirm, worktree_path=worktree_path)


def _try_publish_with_existing_run(creds: Any, key: str, version_id: str) -> dict[str, Any] | None:
    """Publish via an already-concluded passing run of this draft, or None (caller runs evals)."""
    runs = http_json("GET", creds, f"{_BASE}/{key}/evals/runs")
    if not runs.ok:
        return None
    candidates = [
        r for r in (runs.data or {}).get("items", [])
        if r.get("version_id") == version_id and r.get("status") == "concluida" and r.get("completa")
        and r.get("modelo_geracao") is None and r.get("score") is not None and r["score"] >= r.get("limiar", 1.0)
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: r.get("finished_at") or "")
    pub = http_json("POST", creds, f"{_BASE}/{key}/draft/publish", body={})
    if not pub.ok:
        return None  # e.g. 409 eval_required (content/knowledge changed since that run) → run evals
    return {
        "eval": {k: best.get(k) for k in ("status", "score", "limiar", "total", "aprovados", "completa")} | {"run_id": best.get("id"), "reused": True},
        "published": {k: (pub.data or {}).get(k) for k in ("id", "numero", "status", "versao_semver")},
    }
