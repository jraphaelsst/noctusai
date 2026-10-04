"""`noctus.dev.safety_pack_sync` - refresh the vendored Limiar safety pack from limiar-app.

The pack (``safety/regras.json`` + ``safety/conformance.json``) is authored in the public repo
``jraphaelsst/limiar-app``; the server vendors a byte-identical copy under
``products/agents/backend/app/public_ask/safety_pack/limiar/`` pinned by ``SOURCE.lock``
(``{repo, commit, versao, files:{name: sha256}}``). This tool fetches both files at a ref,
rewrites the copy + lock, then RUNS the conformance test; a pack that fails it is rolled
back to the previous bytes (never left half-applied).

``confirm=False`` (default) is a dry run: it fetches (read-only) and reports the versao/commit/
file diff plus a STALENESS note (lock versao vs the fetched ref's versao) - the CI-visible
warning that limiar-app moved on. Offline fetch failure is reported, never raised.

Project: projects/limiar-open-question (S1 + S5 sync leg).
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("noctus.dev.safety_pack_sync")

_APPS = {"limiar": "limiar"}
_DEFAULT_REPO = "jraphaelsst/limiar-app"
_FILES = ("regras.json", "conformance.json")
_SRC_DIR = "safety"
_PACK_REL = Path("products/agents/backend/app/public_ask/safety_pack")
_BACKEND_REL = Path("products/agents/backend")
_TEST_REL = "tests/public_ask/test_safety_pack_conformance.py"

# fetcher(repo, path_in_repo, ref) -> bytes ; resolver(repo, ref) -> full commit sha
Fetcher = Callable[[str, str, str], bytes]
Resolver = Callable[[str, str], str]
Validator = Callable[[Path], tuple[bool, str]]


def _gh_fetch(repo: str, path: str, ref: str) -> bytes:
    proc = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{path}?ref={ref}"],
        capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {path}@{ref} failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout


def _gh_resolve(repo: str, ref: str) -> str:
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/commits/{ref}", "--jq", ".sha"], capture_output=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api commit {ref} failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout.decode().strip()


def _local_fetcher(clone: str) -> tuple[Fetcher, Resolver]:
    def fetch(_repo: str, path: str, ref: str) -> bytes:
        proc = subprocess.run(["git", "-C", clone, "show", f"{ref}:{path}"], capture_output=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"git show {ref}:{path} failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
        return proc.stdout

    def resolve(_repo: str, ref: str) -> str:
        proc = subprocess.run(["git", "-C", clone, "rev-parse", ref], capture_output=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(f"git rev-parse {ref} failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
        return proc.stdout.decode().strip()

    return fetch, resolve


def _pytest_validator(root: Path) -> tuple[bool, str]:
    backend = root / _BACKEND_REL
    venv_py = root / "venv/bin/python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    proc = subprocess.run(
        [py, "-m", "pytest", _TEST_REL, "-q", "-x", "-p", "no:cacheprovider"],
        cwd=backend, capture_output=True, timeout=600,
    )
    tail = proc.stdout.decode(errors="replace")[-600:]
    return proc.returncode == 0, tail


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def safety_pack_sync(
    *,
    app: str = "limiar",
    repo: str = _DEFAULT_REPO,
    ref: str = "main",
    confirm: bool = False,
    local_clone: str | None = None,
    root: Path | None = None,
    fetcher: Fetcher | None = None,
    resolver: Resolver | None = None,
    validator: Validator | None = None,
) -> dict[str, Any]:
    if app not in _APPS:
        return {"ok": False, "status": "error", "error": f"unknown app {app!r}; known: {sorted(_APPS)}"}
    if root is None:
        from settings import REPO_ROOT

        root = REPO_ROOT
    pack_root = root / _PACK_REL
    pack_dir = pack_root / _APPS[app]
    lock_path = pack_root / "SOURCE.lock"
    if fetcher is None:
        if local_clone:
            fetcher, resolver = _local_fetcher(local_clone)
        else:
            fetcher, resolver = _gh_fetch, resolver or _gh_resolve
    resolver = resolver or _gh_resolve

    try:
        commit = resolver(repo, ref)
        new = {name: fetcher(repo, f"{_SRC_DIR}/{name}", commit) for name in _FILES}
        new_versao = json.loads(new["regras.json"])["versao"]
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        logger.warning("safety_pack_sync: fetch failed (offline? bad ref?): %s", exc)
        return {"ok": False, "status": "fetch_failed", "error": str(exc)}

    old_lock: dict[str, Any] = {}
    if lock_path.exists():
        try:
            old_lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except ValueError:
            old_lock = {}
    new_shas = {n: _sha(b) for n, b in new.items()}
    changed = sorted(n for n in _FILES if (old_lock.get("files") or {}).get(n) != new_shas[n])
    diff = {
        "versao": {"lock": old_lock.get("versao"), "fetched": new_versao},
        "commit": {"lock": old_lock.get("commit"), "fetched": commit},
        "changed_files": changed,
    }
    # Staleness warning: the lock's versao is behind what the ref carries.
    stale = bool(old_lock.get("versao")) and old_lock.get("versao") != new_versao
    base = {"app": app, "repo": repo, "ref": ref, "diff": diff, "stale": stale}
    if stale:
        base["warning"] = f"vendored pack versao {old_lock.get('versao')!r} is behind {repo}@{ref} {new_versao!r}"
    if not confirm:
        return {**base, "ok": True, "status": "planned", "applied": False}
    if not changed and old_lock.get("commit") == commit:
        return {**base, "ok": True, "status": "up_to_date", "applied": False}

    previous = {n: (pack_dir / n).read_bytes() if (pack_dir / n).exists() else None for n in _FILES}
    previous_lock = lock_path.read_text(encoding="utf-8") if lock_path.exists() else None

    def restore() -> None:
        for n, data in previous.items():
            if data is None:
                (pack_dir / n).unlink(missing_ok=True)
            else:
                (pack_dir / n).write_bytes(data)
        if previous_lock is None:
            lock_path.unlink(missing_ok=True)
        else:
            lock_path.write_text(previous_lock, encoding="utf-8")

    pack_dir.mkdir(parents=True, exist_ok=True)
    for n, data in new.items():
        (pack_dir / n).write_bytes(data)
    # Server-authored pack files (e.g. posfiltro.json) are not fetched from the source repo;
    # keep their lock entries so a sync never silently drops them from SOURCE.lock.
    kept = {n: v for n, v in (old_lock.get("files") or {}).items() if n not in _FILES}
    lock = {"repo": repo, "commit": commit, "versao": new_versao, "files": {**new_shas, **kept}}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    ok, detail = (validator or _pytest_validator)(root)
    if not ok:
        restore()
        logger.error("safety_pack_sync: conformance failed; previous pack restored")
        return {**base, "ok": False, "status": "conformance_failed", "applied": False,
                "restored": True, "detail": detail}
    return {**base, "ok": True, "status": "synced", "applied": True, "stale": False, "detail": detail}


def register(server) -> None:
    """Register the `noctus.dev.safety_pack_sync` MCP tool."""

    @server.tool(
        name="noctus.dev.safety_pack_sync",
        description=(
            "Refresh the vendored Limiar safety pack (regras.json + conformance.json) in "
            "products/agents/backend/app/public_ask/safety_pack/ from limiar-app at a ref "
            "(gh api, or local_clone fallback). DRY-RUN by default: shows the versao/commit/"
            "changed-file diff + a staleness warning (lock behind ref). confirm=True writes the "
            "files + SOURCE.lock, RUNS the conformance test and rolls back if it fails. "
            "worktree_path: pin the tree when called from a git worktree."
        ),
    )
    def _safety_pack_sync(
        app: str = "limiar",
        repo: str = _DEFAULT_REPO,
        ref: str = "main",
        confirm: bool = False,
        local_clone: str | None = None,
        worktree_path: str | None = None,
    ) -> dict[str, Any]:
        return safety_pack_sync(
            app=app, repo=repo, ref=ref, confirm=confirm, local_clone=local_clone,
            root=Path(worktree_path) if worktree_path else None,
        )
