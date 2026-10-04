"""`noctus.dev.agent_learnings_promote` — noc: bring accepted learnings into the package (CONTRACT §H3, A7).

``GET /api/studio/agents/{key}/learnings?status=aceito`` (scope ``learnings:read``) → append the rows
not already present (row_sha identity, the wave-1 ``merge_learnings``) to
``products/agents/packages/<key>/LEARNINGS.md`` with status ``promoted``/``promovido`` (per package
language), in the CURRENT checkout/worktree. Prints, per learning, the package knowledge files whose
text overlaps it most — the author edits those, bumps ``versao`` (+ CHANGELOG) and pushes (§F publishes).

DRY-RUN by default (shows the unified diff); ``confirm=True`` writes the file. It never marks rows
``promovido`` in Studio (review is a user action) — re-running is idempotent via row_sha.
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any

import yaml

from .agent_package_build import LEARNINGS_HEADER, LEARNINGS_SEPARATOR, _SLUG_RE, _roots, merge_learnings
from .agent_sync_client import (
    SyncError,
    credentials_or_error,
    http_failure,
    http_json,
    load_credentials,
)

logger = logging.getLogger("noctus.dev.agent_learnings_promote")

_WORD = re.compile(r"[a-zà-ú0-9]{4,}", re.IGNORECASE)


def _cell(s: str) -> str:
    return " ".join((s or "").split())


def _suggest(texto: str, pkg_root, top: int = 2) -> list[str]:
    want = set(w.lower() for w in _WORD.findall(texto))
    if not want:
        return []
    scored: list[tuple[int, str]] = []
    kdir = pkg_root / "knowledge"
    for f in sorted(kdir.rglob("*.md")) if kdir.is_dir() else []:
        have = set(w.lower() for w in _WORD.findall(f.read_text(encoding="utf-8")))
        n = len(want & have)
        if n:
            scored.append((n, f.relative_to(pkg_root).as_posix()))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [p for _, p in scored[:top]]


def agent_learnings_promote(
    key: str,
    confirm: bool = False,
    project: str | None = None,
    worktree_path: str | None = None,
    packages_dir: str | None = None,
    repo_root: str | None = None,
    env: dict[str, str] | None = None,
    env_file: str | None = None,
) -> dict[str, Any]:
    if not _SLUG_RE.match(key or ""):
        return {"ok": False, "status": "invalid", "errors": [f"key {key!r} must be kebab-case"]}
    pk_dir, _ = _roots(worktree_path, packages_dir, repo_root)
    root = pk_dir / key
    if not (root / "package.yaml").is_file():
        return {"ok": False, "status": "invalid", "key": key, "errors": [f"package not found: {root}"]}
    idioma = str((yaml.safe_load((root / "package.yaml").read_text(encoding="utf-8")) or {}).get("idioma", "en"))
    promoted_word = "promovido" if idioma.lower().startswith("pt") else "promoted"
    out: dict[str, Any] = {"ok": True, "key": key, "credentials": "present" if load_credentials(env, env_file) else "missing"}
    try:
        creds = credentials_or_error(env, env_file)
        res = http_json("GET", creds, f"/api/studio/agents/{key}/learnings",
                        query={"status": "aceito", **({"project": project} if project else {})})
        if not res.ok:
            raise http_failure(res, "learnings GET")
    except SyncError as exc:
        out.update(ok=False, status="failed", error_code=exc.code, errors=[exc.message])
        return out
    items = (res.data or {}).get("items", [])
    lf = root / "LEARNINGS.md"
    current = lf.read_text(encoding="utf-8") if lf.is_file() else None
    lines = [f"| {_cell(i['data'])} | {_cell(i['tipo'])} | {_cell(i['texto'])} | {_cell(i.get('evidencia', ''))} | {promoted_word} |"
             for i in items]
    upstream = "\n".join([LEARNINGS_HEADER, LEARNINGS_SEPARATOR, *lines]) + "\n"
    merged, added = merge_learnings(current if current is not None else LEARNINGS_HEADER + "\n" + LEARNINGS_SEPARATOR + "\n", upstream)
    out["accepted"] = len(items)
    out["added"] = [{"data": r.data, "tipo": r.tipo, "texto": r.texto, "sha": r.sha,
                     "suggested_knowledge": _suggest(r.texto, root)} for r in added]
    out["already_present"] = len(items) - len(added)
    old = current or ""
    out["diff"] = "".join(difflib.unified_diff(old.splitlines(True), merged.splitlines(True),
                                               fromfile=f"{key}/LEARNINGS.md", tofile=f"{key}/LEARNINGS.md (promoted)", n=1))
    if added:
        out["next"] = ("edit the suggested knowledge files, bump `versao` + CHANGELOG, push — §F publishes; "
                       "consumers then agent_pull")
    if not confirm:
        out["status"] = "planned"
        return out
    if added:
        lf.write_text(merged, encoding="utf-8")
    out["status"] = "promoted" if added else "up_to_date"
    return out


def register(server) -> None:
    """Register the `noctus.dev.agent_learnings_promote` MCP tool."""

    @server.tool(
        name="noctus.dev.agent_learnings_promote",
        description=(
            "Promote accepted Studio learnings into a package (CONTRACT agent-packages §H3): GET "
            "/api/studio/agents/{key}/learnings?status=aceito (scope learnings:read), append the unseen rows "
            "(row_sha identity) to products/agents/packages/<key>/LEARNINGS.md with status promoted/promovido in "
            "the CURRENT checkout, and print suggested knowledge files to edit. DRY-RUN by default (shows the "
            "diff); confirm=True writes. Then bump versao + CHANGELOG and push (§F publishes). Creds: "
            "NOCTUS_AGENTS_URL/TOKEN from env or ~/.config/noctus/agents.env."
        ),
    )
    def _agent_learnings_promote(key: str, confirm: bool = False, project: str | None = None,
                                 worktree_path: str | None = None) -> dict[str, Any]:
        return agent_learnings_promote(key=key, confirm=confirm, project=project, worktree_path=worktree_path)
