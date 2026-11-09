"""`noctus.dev.agent_export` — write the git mirror of a DB-source dev agent into this repo (Agent Packages §M2).

The Studio DB is the source of truth for a DB-source agent (A11). Its publish renders the Claude Code tree and stores
it on the version; this tool fetches that tree over ``GET /api/agent-packages/{key}/{versao}`` (scope
``packages:read``), VERIFIES it (``fonte == "db"``, the ``.md`` is a mirror whose body hashes to its recorded
``compiled_hash``) and writes it:

* ``.claude/agents/<key>.md`` and ``agents/<key>/{PACKAGE.json, skills/…}`` — generated, overwritten; files under
  ``agents/<key>/skills/`` that the new tree no longer has are deleted;
* then the agent-context cache is refreshed for that agent in the SAME call (the eager leg of the mirror contract,
  so cache == ``.md`` == last export), and this agent's entry in ``.agents-mirror-pending`` (the §M5 online check's marker) is cleared.

DRY-RUN by default; ``confirm=True`` writes. It never writes to the DB (§M6: the mirror is never an input).
Credentials: ``NOCTUS_AGENTS_URL`` + ``NOCTUS_AGENTS_TOKEN`` (env, else ``~/.config/noctus/agents.env``), never echoed.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from . import agent_sync_client as sc
from .agent_package_build import _SLUG_RE, _surface, _visible_files

logger = logging.getLogger("noctus.dev.agent_export")

_REPO_ROOT = Path(__file__).resolve().parents[5]


def verify_tree(key: str, files: dict[str, str], package: dict[str, Any]) -> list[str]:
    """Problems that make the fetched tree unsafe to write (empty list = OK)."""
    errors: list[str] = []
    if package.get("fonte") != "db":
        errors.append(f"{key} is not a DB-source agent (package.fonte={package.get('fonte')!r}); use agent_pull")
    md_rel = f".claude/agents/{key}.md"
    md = files.get(md_rel)
    if md is None:
        return errors + [f"the tree has no {md_rel}"]
    surface = _surface()
    parsed = surface.split_db_mirror(md)
    if parsed is None:
        return errors + [f"{md_rel} is not a DB-source mirror (no studio: block or generated marker)"]
    meta, body = parsed
    if meta.get("compiled_hash") != surface.body_hash(body):
        errors.append(f"{md_rel}: body does not hash to its recorded compiled_hash (corrupt tree)")
    if meta.get("key") != key:
        errors.append(f"{md_rel}: studio.key={meta.get('key')!r} != {key!r}")
    for rel in files:
        if not (rel == md_rel or rel.startswith(f"agents/{key}/")) or ".." in rel.split("/"):
            errors.append(f"refusing a path outside the agent's mirror: {rel}")
    return errors


def plan_export(key: str, files: dict[str, str], repo: Path) -> dict[str, Any]:
    writes: dict[str, str] = {}
    unchanged: list[str] = []
    for rel, text in sorted(files.items()):
        p = repo / rel
        if p.is_file() and p.read_text(encoding="utf-8") == text:
            unchanged.append(rel)
        else:
            writes[rel] = text
    removed: list[str] = []
    skills_dir = repo / "agents" / key / "skills"
    if skills_dir.is_dir():
        removed = sorted(f.relative_to(repo).as_posix() for f in _visible_files(skills_dir)
                         if f.relative_to(repo).as_posix() not in files)
    return {"writes": writes, "unchanged": unchanged, "removed": removed}


#: §M5: the mirror check's OWN marker. The package publish leg rewrites/clears ``.agents-sync-pending`` on its own
#: runs, which would silently erase a stale-mirror entry; a separate file keeps each signal alive until its fix.
MIRROR_MARKER = ".agents-mirror-pending"


def _read_mirror_marker(repo: Path) -> list[dict[str, Any]]:
    p = repo / MIRROR_MARKER
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [{"key": "?", "motivo": "marker_unreadable"}]
    return [f for f in data.get("pendentes", []) if isinstance(f, dict)]


def _write_mirror_marker(repo: Path, pendentes: list[dict[str, Any]]) -> None:
    p = repo / MIRROR_MARKER
    if pendentes:
        p.write_text(json.dumps({"pendentes": pendentes}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif p.is_file():
        p.unlink()


def _clear_pending(repo: Path, key: str) -> bool:
    before = _read_mirror_marker(repo)
    left = [f for f in before if f.get("key") != key]
    if len(left) == len(before):
        return False
    _write_mirror_marker(repo, left)
    return True


def local_mirrors(repo: Path) -> dict[str, dict[str, Any]]:
    """``{key: studio-meta}`` of every DB-source mirror committed under ``.claude/agents/``."""
    surface = _surface()
    out: dict[str, dict[str, Any]] = {}
    d = repo / ".claude" / "agents"
    for md in (sorted(d.glob("*.md")) if d.is_dir() else []):
        parsed = surface.split_db_mirror(md.read_text(encoding="utf-8"))
        if parsed is not None:
            out[md.stem] = parsed[0]
    return out


def mirror_check(
    repo_root: str | None = None, env: dict[str, str] | None = None, env_file: str | None = None,
) -> dict[str, Any]:
    """§M5 online leg (pre-push; NEVER blocks, never silent): for each committed DB-source mirror, compare its
    ``version_id`` with the newest published version in the Studio. ``stale`` (a newer publish exists) and
    ``unverified`` (no credentials / network / HTTP failure) are written to ``.agents-mirror-pending``; a mirror
    that is current clears its entry. Returns per-key results for the hook to print."""
    repo = Path(repo_root) if repo_root else _REPO_ROOT
    mirrors = local_mirrors(repo)
    if not mirrors:
        return {"ok": True, "status": "no_mirrors", "results": {}}
    results: dict[str, dict[str, Any]] = {}
    try:
        creds = sc.credentials_or_error(env=env, env_file=env_file)
    except sc.SyncError as exc:
        creds = None
        for key in mirrors:
            results[key] = {"status": "unverified", "motivo": str(exc)}
    if creds is not None:
        for key, meta in mirrors.items():
            try:
                res = sc.http_json("GET", creds, f"/api/agent-packages/{key}/latest")
                if not res.ok:
                    raise sc.http_failure(res, f"GET package {key}@latest")
            except sc.SyncError as exc:
                results[key] = {"status": "unverified", "motivo": str(exc)}
                continue
            pkg = (res.data or {}).get("package") or {}
            latest = str(pkg.get("version_id") or "")
            if latest and latest == str(meta.get("version_id")):
                results[key] = {"status": "current", "versao": meta.get("versao")}
            else:
                results[key] = {"status": "stale", "local": meta.get("versao"), "publicada": pkg.get("versao"),
                                "fix": f"noctus.dev.agent_export key={key} confirm=True, then commit the mirror"}
    pendentes = [{"key": k, "motivo": r["status"], **({"detalhe": r["motivo"]} if "motivo" in r else {})}
                 for k, r in results.items() if r["status"] != "current"]
    keep = [f for f in _read_mirror_marker(repo) if f.get("key") not in results]
    _write_mirror_marker(repo, keep + pendentes)
    return {"ok": not pendentes, "status": "stale_or_unverified" if pendentes else "current", "results": results}


def agent_export(
    key: str, versao: str = "latest", confirm: bool = False, worktree_path: str | None = None,
    env: dict[str, str] | None = None, env_file: str | None = None,
) -> dict[str, Any]:
    if not _SLUG_RE.match(key or ""):
        return {"ok": False, "status": "invalid", "errors": [f"key {key!r} must be kebab-case"]}
    repo = Path(worktree_path) if worktree_path else _REPO_ROOT
    try:
        creds = sc.credentials_or_error(env=env, env_file=env_file)
        res = sc.http_json("GET", creds, f"/api/agent-packages/{key}/{versao}")
        if not res.ok:
            raise sc.http_failure(res, f"GET package {key}@{versao}")
    except sc.SyncError as exc:
        return {"ok": False, "status": exc.code, "key": key, "errors": [str(exc)]}
    data = res.data or {}
    files = {f["path"]: f["conteudo"] for f in data.get("files", [])}
    package = data.get("package") or {}
    errors = verify_tree(key, files, package)
    if errors:
        return {"ok": False, "status": "invalid_tree", "key": key, "errors": errors}
    plan = plan_export(key, files, repo)
    out: dict[str, Any] = {
        "ok": True, "key": key, "versao": package.get("versao"), "version_id": package.get("version_id"),
        "to_write": sorted(plan["writes"]), "unchanged": plan["unchanged"], "to_remove": plan["removed"],
    }
    if not confirm:
        return {**out, "status": "planned"}
    for rel, text in plan["writes"].items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for rel in plan["removed"]:
        (repo / rel).unlink()
    from . import agent_context_cache

    out["cache"] = agent_context_cache.refresh(agent_name=key, worktree_path=str(repo) if worktree_path else None)
    out["pending_cleared"] = _clear_pending(repo, key)
    out["status"] = "exported" if (plan["writes"] or plan["removed"]) else "up_to_date"
    out["next"] = "commit the mirror on a self-branch (it is a generated file: never edit it by hand)"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_export` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_export",
        description=(
            "Write the git mirror of a DB-source dev agent (Agent Packages A11/§M, e.g. media-analyst) into this repo: "
            "fetches GET /api/agent-packages/{key}/{versao} (the tree rendered at its publish), verifies it (fonte=db, "
            "the .md hashes to its studio.compiled_hash), writes .claude/agents/<key>.md + agents/<key>/ (stale "
            "skill files removed), refreshes the agent-context cache for that agent and clears its "
            ".agents-mirror-pending entry. DRY-RUN by default - confirm=True writes. Never writes to the DB. "
            "Credentials NOCTUS_AGENTS_URL + NOCTUS_AGENTS_TOKEN (packages:read), never echoed."
        ),
    )
    def _agent_export(key: str, versao: str = "latest", confirm: bool = False, worktree_path: str | None = None) -> dict[str, Any]:
        return agent_export(key=key, versao=versao, confirm=confirm, worktree_path=worktree_path)
