"""`noctus.dev.agent_context_sync` — consumer → Studio: project context (CONTRACT §G, §J2).

Reads the ``project`` block of the consumer's ``agents.lock.json`` (§G1)::

    "project": {"slug": "...", "fontes": {"docs": [globs], "codigo": [globs], "quadro": "<path>"}, "agentes": [keys]}

collects the matching files, hard-excludes secrets/binaries, secret-scans (the shared
``noctusai_lib.security`` scanner — same one ``knowledge_bundle_export`` uses), hashes each UTF-8 text with
sha256 and PUTs the FULL manifest to ``/api/studio/agents/{key}/projects/{slug}/sources`` for every listed
agent (the server upserts on sha256 and deletes paths absent from the manifest — §G2).

* a secret hit ABORTS the whole sync (nothing is sent) and names only file + pattern, never the value;
* files > 200 KB are skipped with a listed warning; a manifest > 25 MB aborts;
* no ``project`` block ⇒ ``no_project_block`` (nothing invented); an empty manifest is refused (it would
  make the server delete every source).

DRY-RUN by default; ``confirm=True`` sends. Holds the per-agent lock (see ``agent_sync_client``).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .agent_sync_client import (
    SyncError,
    agent_lock,
    credentials_or_error,
    http_failure,
    http_json,
    load_credentials,
)

logger = logging.getLogger("noctus.dev.agent_context_sync")

LOCK_NAME = "agents.lock.json"
FILE_MAX_BYTES = 200 * 1024
MANIFEST_MAX_BYTES = 25 * 1024 * 1024
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

#: Mirrors the server's forbidden set (app/studio/project_sources.py) + extras; the client refuses first.
FORBIDDEN_SEGMENTS = frozenset({"node_modules", ".git", ".ssh", ".aws", ".gnupg", ".expo", "Pods", ".gradle"})
FORBIDDEN_SUFFIXES = (
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".der", ".crt", ".cer", ".p8", ".mobileprovision",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".heic",
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar",
    ".mp3", ".mp4", ".mov", ".wav", ".m4a", ".ogg", ".webm",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".jar", ".apk", ".ipa", ".aab",
    ".sqlite", ".db", ".lock",
)
FORBIDDEN_BASENAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "credentials", "secrets.json",
                                 "google-services.json", "GoogleService-Info.plist"})


def forbidden_reason(rel: str) -> str | None:
    parts = rel.split("/")
    if any(p in FORBIDDEN_SEGMENTS for p in parts[:-1]):
        return "forbidden_directory"
    base = parts[-1]
    if base.startswith(".env"):
        return "env_file"
    if base in FORBIDDEN_BASENAMES:
        return "forbidden_name"
    if base.lower().endswith(FORBIDDEN_SUFFIXES):
        return "forbidden_suffix"
    return None


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """``**`` spans directories (``src/**/*.ts`` also matches ``src/a.ts``); ``*``/``?`` stay in one segment."""
    i, out, n = 0, "", len(pattern)
    while i < n:
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(f"^{out}$")


def _candidates(repo: Path) -> list[str]:
    """Tracked + untracked-not-ignored files when the repo is git; else a pruned walk."""
    if (repo / ".git").exists():
        try:
            raw = subprocess.run(["git", "-C", str(repo), "ls-files", "-co", "--exclude-standard", "-z"],
                                 capture_output=True, check=True, timeout=60).stdout
            return sorted({p for p in raw.decode("utf-8", errors="replace").split("\0") if p})
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("git ls-files failed (%s) — falling back to a directory walk", exc)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in FORBIDDEN_SEGMENTS]
        for f in filenames:
            out.append((Path(dirpath) / f).relative_to(repo).as_posix())
    return sorted(out)


def read_project_block(repo: Path) -> dict[str, Any] | None:
    lock = repo / LOCK_NAME
    if not lock.is_file():
        raise SyncError("no_lock", f"{LOCK_NAME} not found in {repo}")
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError("bad_lock", f"{LOCK_NAME}: invalid JSON ({exc})") from exc
    project = data.get("project")
    return project if isinstance(project, dict) else None


def _validate_project(project: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    slug = project.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise SyncError("bad_project", "project.slug must be a kebab-case string")
    fontes = project.get("fontes")
    if not isinstance(fontes, dict):
        raise SyncError("bad_project", "project.fontes must be an object {docs, codigo, quadro}")
    agentes = project.get("agentes")
    if not isinstance(agentes, list) or not agentes or not all(isinstance(a, str) and _SLUG_RE.match(a) for a in agentes):
        raise SyncError("bad_project", "project.agentes must be a non-empty list of agent keys")
    for k in ("docs", "codigo"):
        v = fontes.get(k, [])
        if not isinstance(v, list) or not all(isinstance(g, str) and g and not g.startswith("/") and ".." not in g.split("/") for g in v):
            raise SyncError("bad_project", f"project.fontes.{k} must be a list of relative globs")
    q = fontes.get("quadro")
    if q is not None and (not isinstance(q, str) or q.startswith("/") or ".." in q.split("/")):
        raise SyncError("bad_project", "project.fontes.quadro must be a relative path")
    return slug, fontes, agentes


def collect_manifest(repo: Path, fontes: dict[str, Any]) -> dict[str, Any]:
    """-> {items: [{path,sha256,tipo,conteudo}], skipped: [{path,motivo}], secrets: [{path,padrao}], warnings: []}."""
    from noctusai_lib.security import find_secret

    wanted: dict[str, str] = {}  # path -> tipo (first source wins: docs, codigo, quadro)
    cand = _candidates(repo)
    for tipo in ("docs", "codigo"):
        regs = [glob_to_regex(g) for g in fontes.get(tipo, [])]
        for rel in cand:
            if rel not in wanted and any(r.match(rel) for r in regs):
                wanted[rel] = "doc" if tipo == "docs" else "codigo"
    warnings: list[str] = []
    quadro = fontes.get("quadro")
    if quadro:
        if (repo / quadro).is_file():
            wanted.setdefault(quadro, "quadro")
        else:
            warnings.append(f"quadro {quadro!r} not found — no board snapshot synced (§G4: the session writes it)")
    items: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    secrets: list[dict[str, str]] = []
    for rel in sorted(wanted):
        why = forbidden_reason(rel)
        p = repo / rel
        if why is None and (p.is_symlink() or not p.is_file()):
            why = "not_a_regular_file"
        if why is None:
            raw = p.read_bytes()
            if len(raw) > FILE_MAX_BYTES:
                why = "too_large"
            elif b"\0" in raw:
                why = "binary"
            else:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    why = "not_utf8"
        if why:
            skipped.append({"path": rel, "motivo": why})
            continue
        hit = find_secret(text)
        if hit:
            secrets.append({"path": rel, "padrao": hit})  # NAME of the pattern only, never the value
            continue
        items.append({"path": rel, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                      "tipo": wanted[rel], "conteudo": text})
    return {"items": items, "skipped": skipped, "secrets": secrets, "warnings": warnings}


def agent_context_sync(
    repo: str,
    confirm: bool = False,
    env: dict[str, str] | None = None,
    env_file: str | None = None,
    lock_dir: str | None = None,
) -> dict[str, Any]:
    repo_path = Path(repo)
    if not repo_path.is_dir():
        return {"ok": False, "status": "invalid", "errors": [f"repo not found: {repo}"]}
    try:
        project = read_project_block(repo_path)
        if project is None:
            return {"ok": True, "status": "no_project_block", "repo": str(repo_path),
                    "message": f"{LOCK_NAME} has no `project` block (§G1) — nothing to sync; add one to enable project context"}
        slug, fontes, agentes = _validate_project(project)
        man = collect_manifest(repo_path, fontes)
    except SyncError as exc:
        return {"ok": False, "status": "failed", "error_code": exc.code, "errors": [exc.message]}
    out: dict[str, Any] = {
        "ok": True, "repo": str(repo_path), "project": slug, "agentes": agentes,
        "files": len(man["items"]), "paths": [i["path"] for i in man["items"]],
        "skipped": man["skipped"], "warnings": man["warnings"],
        "credentials": "present" if load_credentials(env, env_file) else "missing",
    }
    if man["secrets"]:
        out.update(ok=False, status="failed", error_code="secret_detected", secrets=man["secrets"],
                   errors=[f"secret scan hit in {len(man['secrets'])} file(s) — sync aborted, nothing sent: "
                           + ", ".join(f"{s['path']} ({s['padrao']})" for s in man["secrets"])])
        return out
    if not man["items"]:
        out.update(ok=False, status="failed", error_code="empty_manifest",
                   errors=["no files matched the globs — refusing to send an empty manifest (the server would delete every source)"])
        return out
    size = sum(len(i["conteudo"].encode("utf-8")) for i in man["items"])
    out["bytes"] = size
    if size > MANIFEST_MAX_BYTES:
        out.update(ok=False, status="failed", error_code="manifest_too_large",
                   errors=[f"manifest is {size} bytes, over the 25 MB cap — narrow the globs"])
        return out
    if not confirm:
        out["status"] = "planned"
        return out
    totals = {"criados": 0, "atualizados": 0, "inalterados": 0, "removidos": 0}
    per_agent: dict[str, Any] = {}
    errors: list[str] = []
    try:
        creds = credentials_or_error(env, env_file)
    except SyncError as exc:
        out.update(ok=False, status="failed", error_code=exc.code, errors=[exc.message])
        return out
    for key in agentes:
        try:
            with agent_lock(key, lock_dir):
                res = http_json("PUT", creds, f"/api/studio/agents/{key}/projects/{slug}/sources",
                                body=man["items"], timeout=120)
            if not res.ok:
                raise http_failure(res, f"sources PUT for {key}")
            data = res.data or {}
            per_agent[key] = {k: data.get(k) for k in (*totals, "total", "ignorados", "avisos")}
            for k in totals:
                totals[k] += int(data.get(k) or 0)
        except SyncError as exc:
            per_agent[key] = {"error": exc.code}
            errors.append(f"{key}: {exc.message}")
    out["per_agent"] = per_agent
    out["summary"] = {"created": totals["criados"], "updated": totals["atualizados"],
                      "unchanged": totals["inalterados"], "deleted": totals["removidos"],
                      "skipped": len(man["skipped"])}
    if errors:
        out.update(ok=False, status="failed", error_code="sync_failed", errors=errors)
    else:
        out["status"] = "synced"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_context_sync` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_context_sync",
        description=(
            "Consumer → Agent Studio project-context sync (CONTRACT agent-packages §G): read agents.lock.json "
            "`project` block, collect docs/codigo/quadro files by glob (hard-exclude .env*, keys, node_modules, "
            "binaries; files >200 KB skipped), secret-scan (a hit aborts, nothing sent), sha256 each, PUT the full "
            "manifest to /api/studio/agents/{key}/projects/{slug}/sources for each listed agent. Reports "
            "created/updated/unchanged/deleted/skipped. No project block ⇒ no_project_block. DRY-RUN by default; "
            "confirm=True sends. Creds: NOCTUS_AGENTS_URL/TOKEN from env or ~/.config/noctus/agents.env."
        ),
    )
    def _agent_context_sync(repo: str, confirm: bool = False) -> dict[str, Any]:
        return agent_context_sync(repo=repo, confirm=confirm)
