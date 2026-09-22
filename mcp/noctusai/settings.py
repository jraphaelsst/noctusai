"""Settings shim for the MCP server.

For now the server reuses ``noctusai_lib.config.settings.BaseAppSettings``
so we keep a single ``.env`` source of truth across the repo. When this
MCP is extracted to its own NoctusAI repo, this module gets its own
``Settings`` class and the platform becomes one of N consumers reading
its own ``.env``.

Path constants — ``REPO_ROOT`` and ``PRODUCTS_DIR`` — also live here so
every tool module imports the same depth-independent definition.
Previously each module computed its own
``Path(__file__).resolve().parents[N]``, which broke when files moved
between directory levels (mcp-server-fastmcp-switch Phase 3 had to bump
18 modules from ``parents[3]`` to ``parents[5]``). The constants here
delegate to ``workspace.get_noctusai_home()`` — the canonical
marker-file-based resolver in ``mcp/noctusai/workspace.py`` — which
already handles primary-vs-seed-workspace resolution correctly. Any
module that needs the noc repo path imports ``REPO_ROOT`` from here
instead of computing its own.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from noctusai_lib.config.settings import BaseAppSettings

from workspace import get_ledger_root, get_noctusai_home, unwrap_worktree_root


Settings = BaseAppSettings

REPO_ROOT: Path = get_noctusai_home()
PRODUCTS_DIR: Path = REPO_ROOT / "products"

# LEDGER_ROOT resolves to the PRIMARY checkout even when the MCP server
# booted with cwd inside a worktree (get_ledger_root() UNWRAPS the
# worktree boundary that REPO_ROOT/get_noctusai_home() deliberately stops
# at). Repo-global append-only ledgers (project-history/*.ndjson) import
# THIS constant, never REPO_ROOT, for their default/implicit write target
# — a worktree is ephemeral and a ledger row written only there dies with
# it (KB § PATTERNS/common/claim-vs-evidence-shared-state.md; the fifth
# confirmed incident of the family, 2026-09-17). Equal to REPO_ROOT
# whenever the server did NOT boot inside a worktree.
LEDGER_ROOT: Path = get_ledger_root()


# accept-with-rationale: "MCP settings shim ships its own local
# get_settings() factory (not in noctusai_lib)" in
# KB § PATTERNS/accept-with-rationale.md — lib intentionally exposes
# only the BaseAppSettings shape; per-product Settings is the documented
# pattern. MCP-scoped factory is the right granularity. Revisit when a
# 2nd non-product process needs the same singleton.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def resolve_test_python() -> str:
    """Interpreter path for running product pytest. The repo-root ``venv``
    carries ``noctusai_lib`` + pytest + the product deps; a bare ``python``
    on PATH often resolves to a system interpreter WITHOUT pytest, which
    silently breaks the test runners — a false *block* in
    ``noctus.dev.predeploy_check`` (P5 gate) and a false *green* in
    ``noctus.dev.pytest`` (0 passed / 0 failed parsed as success). Both call
    sites resolve the interpreter here instead of hardcoding ``"python"``.

    Resolution order:
      1. ``<REPO_ROOT>/venv`` — the caller's own tree, when it has one.
      2. The PRIMARY checkout's ``venv`` when ``REPO_ROOT`` is a linked
         worktree. A worktree is a fresh checkout with NO ``venv/`` of its
         own (nobody runs `pip install` per worktree), so step 1 misses and
         the old code fell straight through to ``sys.executable`` — the MCP
         server's own venv, which lacks the product deps. Every product
         whose tests import one of those (``claude_agent_sdk`` for
         ``agents``) then failed at COLLECTION, and ``predeploy_check``
         reported ``status='blocked'``: a red that judges the HARNESS, not
         the code (2026-09-22, two sessions burned in one day, each
         re-running the suite by hand to discover the product was green —
         1209 passed). Mirrors ``env_bootstrap._candidate_roots``' existing
         worktree→primary fallback for ``.env``, via the same
         ``unwrap_worktree_root`` primitive ``get_ledger_root`` is built on.
      3. ``sys.executable`` — no venv anywhere (CI installs deps into the
         job interpreter; a contributor may too).

    Returns a path only. Whether that interpreter can actually import what
    a suite needs is the CALLER's verdict to make — see
    ``predeploy_check``'s ``classify_failure``, which now reads a
    collection-time ``ModuleNotFoundError`` as *unmeasurable*, never as a
    product failure (`KB § PATTERNS/common/methodology-execution-discipline.md`,
    verdict-channel integrity)."""
    for root in (REPO_ROOT, unwrap_worktree_root(REPO_ROOT)):
        if root is None:
            continue
        cand = root / "venv" / "bin" / "python"
        if cand.exists():
            return str(cand)
    return sys.executable


__all__ = [
    "Settings",
    "get_settings",
    "REPO_ROOT",
    "LEDGER_ROOT",
    "PRODUCTS_DIR",
    "resolve_test_python",
]
