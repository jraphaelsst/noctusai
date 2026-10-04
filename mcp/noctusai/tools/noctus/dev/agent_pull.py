"""`noctus.dev.agent_pull` — materialise an Agent Package into a consumer repo (CONTRACT §E, wave-1).

Wave-1 variant: builds LOCALLY from the noc tree (``products/agents/packages/<key>/``) via
``agent_package_build.build_package`` — no API yet (the §I fetch lands with BE-API, wave 2).

Writes into the consumer repo:

* ``.claude/agents/<key>.md`` + ``agents/<key>/{PACKAGE.json, skills/, knowledge/}`` — generated, overwritten;
  generated files that vanished upstream (a removed skill / knowledge doc) are deleted;
* ``agents/<key>/LEARNINGS.md`` — consumer-owned, MERGED (all consumer rows kept verbatim and in order;
  upstream rows whose row-sha §H1 is absent are appended; idempotent);
* ``agents.lock.json`` (``noctus.agents-lock/v1``) — the pin (A4); the ``project`` block is preserved.

DRY-RUN by default; ``confirm=True`` writes. ``install_hook`` is wave 3 (HOOKS slice) — accepted and
answered with a named ``not_yet``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent_package_build import (
    BuildResult,
    PackageError,
    StudioUnavailable,
    _SLUG_RE,
    _roots,
    _visible_files,
    build_package,
    merge_learnings,
    normalize_for_compare,
)

logger = logging.getLogger("noctus.dev.agent_pull")

LOCK_FORMAT = "noctus.agents-lock/v1"
LOCK_NAME = "agents.lock.json"


def _read_lock(repo: Path) -> dict[str, Any]:
    p = repo / LOCK_NAME
    if not p.is_file():
        return {"formato": LOCK_FORMAT, "agents": []}
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("formato") != LOCK_FORMAT or not isinstance(data.get("agents"), list):
        raise ValueError(f"{LOCK_NAME}: unexpected format (want {LOCK_FORMAT!r} with an agents list)")
    return data


def _updated_lock(lock: dict[str, Any], result: BuildResult) -> dict[str, Any]:
    agents = [a for a in lock["agents"] if a.get("key") != result.key]
    agents.append({"key": result.key, "versao": result.versao, "sha": result.sha})
    agents.sort(key=lambda a: a["key"])
    out: dict[str, Any] = {"formato": LOCK_FORMAT, "agents": agents}
    for k, v in lock.items():  # preserve `project` (and any future block) verbatim
        if k not in out:
            out[k] = v
    return out


def _lock_text(lock: dict[str, Any]) -> str:
    return json.dumps(lock, indent=2, ensure_ascii=False) + "\n"


def plan_pull(result: BuildResult, repo: Path) -> dict[str, Any]:
    """Compute the file actions without touching the repo."""
    writes: dict[str, str] = {}
    unchanged: list[str] = []
    learnings_added: list[dict[str, str]] = []
    for rel, text in sorted(result.claude_files.items()):
        p = repo / rel
        have = p.read_text(encoding="utf-8") if p.is_file() else None
        if rel.endswith("/LEARNINGS.md"):
            merged, added = merge_learnings(have, text)
            learnings_added = [{"data": r.data, "tipo": r.tipo, "texto": r.texto, "sha": r.sha} for r in added]
            if have is None or merged != have:
                writes[rel] = merged
            else:
                unchanged.append(rel)
            continue
        if have is not None and normalize_for_compare(rel, have) == normalize_for_compare(rel, text):
            unchanged.append(rel)  # keeps the existing built_at — an equal build is not a change
        else:
            writes[rel] = text
    removed: list[str] = []
    gen_root = repo / "agents" / result.key
    for sub in ("skills", "knowledge"):
        d = gen_root / sub
        if d.is_dir():
            removed.extend(f.relative_to(repo).as_posix() for f in _visible_files(d)
                           if f.relative_to(repo).as_posix() not in result.claude_files)
    lock = _read_lock(repo)
    new_lock = _updated_lock(lock, result)
    lock_changed = new_lock != lock or not (repo / LOCK_NAME).is_file()
    if lock_changed:
        writes[LOCK_NAME] = _lock_text(new_lock)
    return {"writes": writes, "unchanged": unchanged, "removed": sorted(removed),
            "learnings_added": learnings_added, "lock_changed": lock_changed}


def agent_pull(
    key: str,
    repo: str,
    install_hook: bool = False,
    confirm: bool = False,
    worktree_path: str | None = None,
    packages_dir: str | None = None,
    repo_root: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not _SLUG_RE.match(key or ""):
        return {"ok": False, "status": "invalid", "errors": [f"key {key!r} must be kebab-case"]}
    repo_path = Path(repo)
    if not repo_path.is_dir():
        return {"ok": False, "status": "invalid", "errors": [f"repo not found: {repo}"]}
    pk_dir, backend = _roots(worktree_path, packages_dir, repo_root)
    try:
        result = build_package(pk_dir / key, backend, now=now)
        plan = plan_pull(result, repo_path)
    except PackageError as exc:
        return {"ok": False, "status": "invalid", "key": key, "errors": exc.errors}
    except StudioUnavailable as exc:
        return {"ok": False, "status": "studio_unavailable", "key": key, "errors": [str(exc)]}
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "invalid", "key": key, "errors": [str(exc)]}
    out: dict[str, Any] = {
        "ok": True, "key": key, "versao": result.versao, "sha": result.sha,
        "to_write": sorted(plan["writes"]), "unchanged": plan["unchanged"], "to_remove": plan["removed"],
        "learnings_added": plan["learnings_added"], "lock_changed": plan["lock_changed"],
        "importer_validation": result.importer_validation["status"],
    }
    if install_hook:
        out["install_hook"] = {"status": "not_yet", "destination": "agent-packages wave 3 (HOOKS slice: consumer pre-push template)"}
    if not confirm:
        out["status"] = "planned"
        return out
    for rel, text in plan["writes"].items():
        p = repo_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for rel in plan["removed"]:
        (repo_path / rel).unlink()
    out["status"] = "pulled" if (plan["writes"] or plan["removed"]) else "up_to_date"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_pull` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_pull",
        description=(
            "Materialise an Agent Package into a consumer repo (CONTRACT agent-packages §E, wave-1: builds locally "
            "from the noc tree, no API): writes .claude/agents/<key>.md + agents/<key>/{PACKAGE.json,skills,knowledge}, "
            "MERGES agents/<key>/LEARNINGS.md (consumer rows kept verbatim; upstream rows with an unseen row-sha "
            "appended), updates agents.lock.json (noctus.agents-lock/v1). DRY-RUN by default — confirm=True writes. "
            "install_hook is wave 3 (returns not_yet). Run noctus.dev.agent_package_build check=<repo> in consumer CI."
        ),
    )
    def _agent_pull(
        key: str,
        repo: str,
        install_hook: bool = False,
        confirm: bool = False,
        worktree_path: str | None = None,
    ) -> dict[str, Any]:
        return agent_pull(key=key, repo=repo, install_hook=install_hook, confirm=confirm, worktree_path=worktree_path)
