"""Single-source LLM-config bootstrap for the dev toolkit.

🔴 **The recurring drift this kills.** The seed LLM client requires
`configure_llm(config)` once at startup before any embed/chat call. A product
app auto-wires it via `create_product_app()`; the noctusai dev toolkit is NOT a
product app, so *something* has to call it. Historically only the CLI did
(`cli._ensure_llm_configured`), and the single embed funnel (`embed_sync`)
documented "caller MUST ensure configure_llm() was called" — offloading the
precondition onto callers. Every non-CLI caller forgot: the live FastMCP server
runs every tool in-process without ever sourcing `.env` or calling
`configure_llm`, so `noctus.dev.refresh_memory_embeddings` / `kb_embeddings_refresh`
/ `code_embeddings_refresh` / `find_reusable_component` all raised
`"LLM not configured. Call configure_llm(config) at application startup"`
whenever invoked from the MCP server (observed repeatedly through 2026-05-30).

**The fix — a funnel self-satisfies its config preconditions.** This module is
the single bootstrap; the embed funnel and the CLI both delegate to it, so the
LLM is configured for EVERY caller (CLI, MCP server, pre-push hook, tests) with
no per-caller ritual. `.env` is auto-sourced because the MCP server is launched
without it. Idempotent + graceful-degrade (no key / no lib → returns False, never
crashes). KB § PATTERNS/common/funnel-self-satisfies-preconditions.md.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_LLM_CONFIGURED = False


def _env_candidate_roots() -> list[Path]:
    """Repo roots that may hold `.env`: this tree's root plus the PRIMARY
    worktree's root. `.env` is gitignored, so it does NOT replicate into linked
    worktrees — a worktree must read the primary checkout's copy."""
    # mcp/noctusai/tools/noctus/dev/_llm_bootstrap.py → parents[5] == repo root.
    here = Path(__file__).resolve().parents[5]
    roots = [here]
    # Primary-worktree detection is a best-effort ENHANCEMENT — if git is
    # unavailable we degrade to this tree's root (where .env normally lives),
    # not a silent failure of the bootstrap itself.
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=here,
        )
        for line in out.stdout.splitlines():
            if line.startswith("worktree "):
                primary = Path(line[len("worktree ") :])
                if primary not in roots:
                    roots.append(primary)
                break  # first porcelain line is always the primary worktree
    except (OSError, subprocess.SubprocessError):
        pass
    return roots


def _source_env_for_key() -> None:
    """Populate OPENAI_API_KEY (and siblings) into os.environ from `.env` when
    absent — the MCP server process is launched without `source .env`."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    for root in _env_candidate_roots():
        env_file = root / ".env"
        if not env_file.exists():
            continue
        try:
            text = env_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        if os.environ.get("OPENAI_API_KEY"):
            break


def ensure_llm_configured() -> bool:
    """Idempotently configure the seed LLM client so any embed/chat works
    regardless of caller (CLI / MCP server / hook / test).

    Returns True when the LLM config is in place (either it already was — e.g.
    a product app wired it — or we configured it here), and False only when the
    seed lib isn't importable (fresh clone / no-key environment), in which case
    callers graceful-degrade rather than crash. Fires its real work once per
    process.
    """
    global _LLM_CONFIGURED
    if _LLM_CONFIGURED:
        return True
    _source_env_for_key()
    try:
        from noctusai_lib import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config
    except ImportError:
        return False
    try:
        get_llm_config()  # already configured by a host app?
        _LLM_CONFIGURED = True
        return True
    except RuntimeError:
        pass
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: os.environ.get(
                f"{provider.upper()}_API_KEY"
            ),
        )
    )
    _LLM_CONFIGURED = True
    return True
