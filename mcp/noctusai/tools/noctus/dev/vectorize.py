"""noctus.dev.vector_* — generic vector primitives.

The low-level platform tools other vector consumers stack on top of. While
`kb_embeddings.py` is KB-specific (chunking strategy tuned for markdown
docs, owns_kb integration, INDEX.md feeding), THIS module exposes the raw
operations any future vector use-case can reuse:

  - embed arbitrary text (calls the shared seed embedding model)
  - inspect the active stack (model + storage engine)
  - probe corpus stats across registered vector caches

Future cache modules (e.g. `code_embeddings.py` for cross-product code
similarity, `memory_embeddings.py` for semantic auto-improvement consult)
register themselves at import-time so `vector_status` reports the whole
fleet of caches.

The user mandate (2026-05-26 kb-vector-search):
  *"create an mcp to deal with vectors and vectorized db, so our life
   gets easier"*

This module IS that. The kb_embeddings tools (search / neighbors /
similar / validate_owns_kb) remain the high-level KB-specific surfaces;
these vector_* tools are the low-level platform layer.

KB § PATTERNS/common/kb-vector-search.md § Vector platform primitives.
"""
from __future__ import annotations

import asyncio
from typing import Any


# Module-level registry of active vector caches. Each cache module that
# wants to surface itself in vector_status() registers a small descriptor:
#   {"name": "kb-embeddings", "purpose": "KB semantic search", "rows_fn": <callable→int>}
# Populated by per-module side-effect on import. Kept tiny to stay
# import-cycle-safe.
_REGISTERED_CACHES: list[dict[str, Any]] = []


def register_cache(name: str, purpose: str, rows_fn: Any) -> None:
    """Register a vector cache so it shows up in `vector_status()`.

    `rows_fn` is a zero-arg callable that returns the current row count
    (int) or `None` if the cache isn't initialized. Other modules call
    this at import time.
    """
    _REGISTERED_CACHES.append({"name": name, "purpose": purpose, "rows_fn": rows_fn})


def embed_text(text: str) -> dict:
    """Embed any text via the shared seed embedder.

    Returns `{ok, vector, dim, model, provider}` on success or
    `{ok: False, error}` on failure (provider unconfigured, network, etc.).

    Use case: ad-hoc embedding for prototyping, debugging, or one-off
    cross-corpus comparisons before building a dedicated cache module.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "text is empty"}
    try:
        from noctusai_lib.integrations.llm import generate_embedding
        from noctusai_lib.integrations.llm.client import get_llm_config
        vec = asyncio.run(generate_embedding(text))
        cfg = get_llm_config()
        return {
            "ok": True,
            "vector": vec,
            "dim": len(vec),
            "model": cfg.default_embedding_model,
            "provider": cfg.default_provider,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def vector_status() -> dict:
    """Inspect the vector platform stack — model, storage engine, and a
    snapshot of every registered cache's row count.

    Use case: confirm the platform is configured (provider credential
    available, sqlite-vec loaded) + spot which caches are populated /
    empty before running searches.
    """
    # Probe sqlite-vec availability without importing the actual cache module.
    try:
        import sqlite_vec  # noqa: F401
        sqlite_vec_available = True
    except ImportError:
        sqlite_vec_available = False
    # Probe model config.
    try:
        from noctusai_lib.integrations.llm.client import get_llm_config
        cfg = get_llm_config()
        model = cfg.default_embedding_model
        provider = cfg.default_provider
    except Exception as e:  # noqa: BLE001
        model = None
        provider = None
        _ = e
    # Snapshot registered caches.
    caches: list[dict[str, Any]] = []
    for entry in _REGISTERED_CACHES:
        try:
            rows = entry["rows_fn"]()
        except Exception:  # noqa: BLE001
            rows = None
        caches.append({
            "name": entry["name"],
            "purpose": entry["purpose"],
            "rows": rows,
        })
    return {
        "ok": True,
        "embedding": {"provider": provider, "model": model},
        "storage": {
            "sqlite_vec_available": sqlite_vec_available,
            "engine_active": "sqlite-vec" if sqlite_vec_available else "pure-python",
        },
        "caches": caches,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.vector_embed",
        description=(
            "Generic vector primitive — embed arbitrary text via the shared "
            "seed embedder (OpenAI text-embedding-3-small by default, via "
            "noctusai_lib.integrations.llm). Returns "
            "{ok, vector, dim, model, provider}. Use for ad-hoc embedding "
            "outside the KB cache (prototyping new vector use-cases, "
            "debugging similarity calculations, one-off cross-corpus "
            "comparisons). For routine KB search, use noctus.dev.kb_search. "
            "KB § PATTERNS/common/kb-vector-search.md § Vector platform."
        ),
    )
    def _embed(text: str) -> dict:
        return embed_text(text)

    @server.tool(
        name="noctus.dev.vector_status",
        description=(
            "Inspect the vector platform stack: embedding model + provider "
            "(from seed config), storage engine (sqlite-vec or pure-python "
            "fallback), and row counts for every registered cache. Useful "
            "first call when troubleshooting vector tools."
        ),
    )
    def _status() -> dict:
        return vector_status()


# Auto-register the KB embeddings cache on import (lazy — only counts when called).
def _kb_rows_count() -> int | None:
    try:
        from . import kb_embeddings
        return len(kb_embeddings.list_docs())
    except Exception:  # noqa: BLE001
        return None


register_cache(
    name="kb-embeddings",
    purpose="KB semantic search (markdown-canonical, vector-DB-is-enrichment)",
    rows_fn=_kb_rows_count,
)


__all__ = ["embed_text", "vector_status", "register_cache", "register"]
