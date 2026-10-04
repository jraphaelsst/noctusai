"""`noctus.dev.agent_learnings_push` — consumer → Studio: push LEARNINGS.md rows (CONTRACT §H1/§H2).

For every agent pinned in the consumer's ``agents.lock.json`` ``agents`` list, parses
``agents/<key>/LEARNINGS.md`` with the wave-1 parser (``agent_package_build.parse_learnings`` — row identity
``row_sha`` is the SAME formula the server uses, never re-implemented here) and POSTs the rows to
``/api/studio/agents/{key}/learnings`` with ``project_slug`` taken from the lock's ``project.slug``.
The server dedups on ``row_sha`` (idempotent): the report says how many were new vs already known.

* no ``project`` block / slug ⇒ ``no_project_block`` (nothing invented); missing LEARNINGS.md ⇒ skipped;
* malformed rows are reported (``parse_errors``) and skipped, never silently dropped.

DRY-RUN by default; ``confirm=True`` sends. Creds: see ``agent_sync_client``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .agent_context_sync import LOCK_NAME, read_project_block
from .agent_package_build import parse_learnings
from .agent_sync_client import (
    SyncError,
    credentials_or_error,
    http_failure,
    http_json,
    load_credentials,
)

logger = logging.getLogger("noctus.dev.agent_learnings_push")

BATCH = 500  # server cap per POST (LEARNINGS_MAX_ROWS)


def _consumed_keys(repo: Path) -> list[str]:
    data = json.loads((repo / LOCK_NAME).read_text(encoding="utf-8"))
    return [a["key"] for a in data.get("agents", []) if isinstance(a, dict) and isinstance(a.get("key"), str)]


def agent_learnings_push(
    repo: str,
    confirm: bool = False,
    env: dict[str, str] | None = None,
    env_file: str | None = None,
) -> dict[str, Any]:
    repo_path = Path(repo)
    if not repo_path.is_dir():
        return {"ok": False, "status": "invalid", "errors": [f"repo not found: {repo}"]}
    try:
        project = read_project_block(repo_path)
        keys = _consumed_keys(repo_path)
    except SyncError as exc:
        return {"ok": False, "status": "failed", "error_code": exc.code, "errors": [exc.message]}
    slug = project.get("slug") if project else None
    if not slug:
        return {"ok": True, "status": "no_project_block", "repo": str(repo_path),
                "message": f"{LOCK_NAME} has no `project.slug` (§G1) — learnings need a project to attach to; nothing pushed"}
    plan: dict[str, list[dict[str, str]]] = {}
    parse_errors: list[str] = []
    skipped: list[str] = []
    for key in keys:
        f = repo_path / "agents" / key / "LEARNINGS.md"
        if not f.is_file():
            skipped.append(f"{key}: no agents/{key}/LEARNINGS.md")
            continue
        rows, errs = parse_learnings(f.read_text(encoding="utf-8"))
        parse_errors += [f"{key}: {e}" for e in errs]
        if rows:
            plan[key] = [{"data": r.data, "tipo": r.tipo, "texto": r.texto, "evidencia": r.evidencia,
                          "status": r.status, "row_sha": r.sha} for r in rows]
    out: dict[str, Any] = {
        "ok": True, "repo": str(repo_path), "project": slug,
        "rows": {k: len(v) for k, v in plan.items()}, "skipped": skipped, "parse_errors": parse_errors,
        "credentials": "present" if load_credentials(env, env_file) else "missing",
    }
    if not confirm:
        out["status"] = "planned"
        return out
    if not plan:
        out["status"] = "nothing_to_push"
        return out
    try:
        creds = credentials_or_error(env, env_file)
    except SyncError as exc:
        out.update(ok=False, status="failed", error_code=exc.code, errors=[exc.message])
        return out
    pushed: dict[str, Any] = {}
    errors: list[str] = []
    for key, rows in plan.items():
        novas = dup = 0
        try:
            for i in range(0, len(rows), BATCH):
                res = http_json("POST", creds, f"/api/studio/agents/{key}/learnings",
                                body={"project_slug": slug, "rows": rows[i:i + BATCH]})
                if not res.ok:
                    raise http_failure(res, f"learnings POST for {key}")
                data = res.data or {}
                novas += int(data.get("novas") or 0)
                dup += int(data.get("duplicadas") or 0)
            pushed[key] = {"new": novas, "duplicate": dup}
        except SyncError as exc:
            pushed[key] = {"error": exc.code}
            errors.append(f"{key}: {exc.message}")
    out["pushed"] = pushed
    if errors:
        out.update(ok=False, status="failed", error_code="push_failed", errors=errors)
    else:
        out["status"] = "pushed"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_learnings_push` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_learnings_push",
        description=(
            "Consumer → Agent Studio learnings push (CONTRACT agent-packages §H2): parse each pinned agent's "
            "agents/<key>/LEARNINGS.md (wave-1 parser + row_sha identity) and POST the rows to "
            "/api/studio/agents/{key}/learnings with the lock's project.slug; the server dedups by row_sha. "
            "No project block ⇒ no_project_block. DRY-RUN by default; confirm=True sends. Creds: "
            "NOCTUS_AGENTS_URL/TOKEN from env or ~/.config/noctus/agents.env."
        ),
    )
    def _agent_learnings_push(repo: str, confirm: bool = False) -> dict[str, Any]:
        return agent_learnings_push(repo=repo, confirm=confirm)
