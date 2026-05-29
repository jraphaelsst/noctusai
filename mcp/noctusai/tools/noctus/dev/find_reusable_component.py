"""``noctus.dev.find_reusable_component`` — query the organ catalog by intent.

Purpose
-------
"I need a component that does credentials list with multi-account selector."
This tool answers that query by vector-searching the code-embeddings cache
(chunk_kind='organ') and returning the top-K matches enriched with their
component_bundle data.

Architecture (per PROJECT.md §3b)
-----------------------------------
1. Embed the query via the shared seed embedding pipeline (same model as all
   other caches — OpenAI text-embedding-3-small, no new dep).
2. Cosine-top-K vector search over ``code_chunks WHERE chunk_kind='organ'``
   in the code-embeddings.sqlite cache.
3. Optionally filter by ``validation_status`` (validated/emerging/shelfware).
4. Enrich each match with the ``component_bundle`` wiring_snippet.
5. Falls back to graph keyword search if the embedding provider is unreachable.

Organ registration (W4 write path)
------------------------------------
``register_organ(name, repo_root)`` builds the embedding chunk from the organ
bundle (source + types + tests + organ.yaml 8 knowledge fields), embeds it
via the seed LLM pipeline, and inserts a row into code_chunks with
``chunk_kind='organ'``.  Source-SHA invariant: any change to source/tests/
knowledge MUST produce a different hash → idempotent re-register is
automatically correct.

Cost logging
------------
Calls ``vector_costs.log_refresh_batch`` so every organ embed is in the ledger.

KB § PATTERNS/architect/seed-organ-canonical-set.md
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

import yaml  # PyYAML — available in the venv (used by other tools)

from pydantic import BaseModel

from settings import REPO_ROOT

# Shared embedding helpers — the §3b META-RULE: embed via noctusai_lib LLM,
# persist in the existing code-embeddings cache (extend, don't proliferate).
from . import _embedding_corpus as _ec
from ._embedding_corpus import HAS_VEC as _HAS_VEC
from .cache_backend import cache_path as _cache_path

# The code-embeddings cache that we EXTEND with chunk_kind='organ'.
CACHE_PATH = _cache_path("code-embeddings")

# NEW chunk kind — does NOT conflict with existing 'function'|'async_function'|
# 'class'|'file' kinds.  The search function in code_embeddings.py supports an
# optional ``kind`` filter; we extend that filter vocabulary here.
ORGAN_CHUNK_KIND = "organ"

EMBEDDING_DIM = _ec.EMBEDDING_DIM
MAX_ORGAN_CHUNK_CHARS = 8000  # organs are richer than code symbols; allow up to ~2000 tokens

logger = logging.getLogger(__name__)


# ── Result model ──────────────────────────────────────────────────────────────


class ReusableComponentMatch(BaseModel):
    """One match returned by ``find_reusable_component``."""

    name: str
    path: Optional[str]
    score: float
    validation_status: str
    consumers_count: int
    snippet: str


# ── Organ yaml sidecar helper ─────────────────────────────────────────────────


def _find_organ_yaml(name: str, repo_root: Path) -> Path | None:
    """Locate <Name>.organ.yaml by searching known seed lib paths."""
    candidate_dirs = [
        repo_root / "seed" / "lib" / "frontend" / "src" / "components",
        repo_root / "seed" / "lib" / "frontend" / "src" / "design-system" / "components",
        repo_root / "seed" / "lib" / "frontend" / "src" / "design-system" / "ai",
        repo_root / "seed" / "lib" / "frontend" / "src" / "design-system",
        repo_root / "seed" / "lib" / "frontend" / "src",
    ]
    for d in candidate_dirs:
        p = d / f"{name}.organ.yaml"
        if p.exists():
            return p
    # Exhaustive fallback
    lib_root = repo_root / "seed" / "lib" / "frontend"
    if lib_root.exists():
        hits = list(lib_root.rglob(f"{name}.organ.yaml"))
        if hits:
            return hits[0]
    return None


def _load_organ_yaml(name: str, repo_root: Path) -> dict:
    """Return parsed organ.yaml or {} if not found."""
    p = _find_organ_yaml(name, repo_root)
    if p is None:
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("find_reusable_component: failed to load organ yaml for %r: %s", name, exc)
        return {}


# ── Organ chunk builder ───────────────────────────────────────────────────────


def _build_organ_chunk(name: str, repo_root: Path) -> str | None:
    """Concatenate source + types + tests + organ.yaml fields into one embedding chunk.

    This is the rich semantic payload that makes intent-based queries work.
    The chunk includes:
      - Component name + path
      - Full source text (capped)
      - Exported type signatures
      - Test source (capped)
      - All 8 knowledge fields from the organ.yaml sidecar (as YAML text)
    """
    from .component_bundle import bundle_component

    bundle = bundle_component(name, fallback_when_w1_missing=True, repo_root=repo_root)
    if bundle is None:
        logger.debug("find_reusable_component: bundle_component returned None for %r", name)
        return None

    organ_data = _load_organ_yaml(name, repo_root)

    parts: list[str] = [
        f"Component: {name}",
        f"Path: {bundle.source[:20]}",  # just a marker; full source follows
    ]

    # Source (capped to avoid over-budget embedding)
    source_cap = bundle.source[:4000] if len(bundle.source) > 4000 else bundle.source
    parts.append(f"Source:\n{source_cap}")

    # Type signatures
    if bundle.types:
        parts.append("Exported types:\n" + "\n".join(bundle.types))

    # Tests (capped)
    if bundle.tests:
        test_cap = bundle.tests[:2000] if len(bundle.tests) > 2000 else bundle.tests
        parts.append(f"Tests:\n{test_cap}")

    # Knowledge fields from organ.yaml
    if organ_data:
        # Serialize the 8 knowledge fields as plain text for embedding
        knowledge_text = yaml.dump(
            {k: v for k, v in organ_data.items()
             if k in (
                 "known_facts", "errors_encountered", "drifts_surfaced",
                 "alternatives_considered", "manual_validation_log",
                 "integration_test_status", "e2e_test", "bugs_fixed_during_dev",
             )},
            default_flow_style=False,
            allow_unicode=True,
        )
        parts.append(f"Knowledge bundle:\n{knowledge_text}")

    chunk = "\n\n".join(parts)
    if len(chunk) > MAX_ORGAN_CHUNK_CHARS:
        chunk = chunk[:MAX_ORGAN_CHUNK_CHARS]
    return chunk


def _organ_source_sha(chunk_text: str) -> str:
    """SHA-256 of the chunk text — the source-sha invariant for idempotency."""
    return hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()


# ── DB schema extension ───────────────────────────────────────────────────────


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure code_chunks + vec/json tables exist (delegated to code_embeddings schema)."""
    from . import code_embeddings as _ce
    _ce._init_schema(conn)


def _connect() -> sqlite3.Connection:
    """Open the code-embeddings cache (shared with code_embeddings.py)."""
    return _ec.connect_cache(CACHE_PATH)


# ── Public write path: register_organ ────────────────────────────────────────


def register_organ(
    name: str,
    *,
    force: bool = False,
    repo_root: Path | None = None,
) -> dict:
    """Embed a seed organ into the code-embeddings cache with chunk_kind='organ'.

    Idempotent: if the organ chunk already has the current source_sha, skips.
    ``force=True`` re-embeds regardless.

    Returns ``{ok, status, name, source_sha, rows_written}``.
    """
    root = repo_root or REPO_ROOT
    chunk_text = _build_organ_chunk(name, root)
    if chunk_text is None:
        return {"ok": False, "status": "bundle-not-found", "name": name,
                "source_sha": "", "rows_written": 0}

    source_sha = _organ_source_sha(chunk_text)

    conn = _connect()
    _ensure_schema(conn)

    # Idempotency check
    if not force:
        row = conn.execute(
            "SELECT source_sha FROM code_chunks WHERE symbol_name=? AND kind=? LIMIT 1",
            (name, ORGAN_CHUNK_KIND),
        ).fetchone()
        if row and row[0] == source_sha:
            conn.close()
            return {"ok": True, "status": "already-current", "name": name,
                    "source_sha": source_sha, "rows_written": 0}

    # Clear existing organ row for this name (path-keyed by symbol_name+kind)
    old_rows = conn.execute(
        "SELECT rowid_alias FROM code_chunks WHERE symbol_name=? AND kind=?",
        (name, ORGAN_CHUNK_KIND),
    ).fetchall()
    if old_rows:
        old_ids = [r[0] for r in old_rows]
        placeholders = ",".join("?" * len(old_ids))
        if _HAS_VEC:
            conn.execute(f"DELETE FROM code_vec WHERE rowid IN ({placeholders})", old_ids)
        else:
            conn.execute(
                f"DELETE FROM code_embeddings_json WHERE chunk_rowid IN ({placeholders})",
                old_ids,
            )
        conn.execute(
            "DELETE FROM code_chunks WHERE symbol_name=? AND kind=?",
            (name, ORGAN_CHUNK_KIND),
        )

    # Determine path for the path column
    organ_yaml = _find_organ_yaml(name, root)
    organ_data = _load_organ_yaml(name, root)
    component_path = organ_data.get("path", str(organ_yaml.relative_to(root)) if organ_yaml else f"seed/lib/frontend/src/{name}")

    # Embed — capture the REAL provider token usage (ground truth for the
    # cost ledger, not the len//4 estimate).
    usage = None
    try:
        with _ec.capture_embedding_usage() as usage:
            vec = _ec.embed_sync(chunk_text)
    except Exception as exc:
        conn.close()
        logger.error("find_reusable_component: embed failed for %r: %s", name, exc)
        return {"ok": False, "status": f"embed-error: {exc}", "name": name,
                "source_sha": source_sha, "rows_written": 0}

    now = _ec.now_iso()
    cur = conn.execute(
        "INSERT INTO code_chunks(path,chunk_idx,symbol_name,kind,chunk_text,source_sha,cached_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (component_path, 0, name, ORGAN_CHUNK_KIND, chunk_text, source_sha, now),
    )
    row_id = cur.lastrowid

    if _HAS_VEC:
        conn.execute(
            "INSERT INTO code_vec(rowid, embedding) VALUES (?, ?)",
            (row_id, _ec.pack_vec(vec)),
        )
    else:
        conn.execute(
            "INSERT INTO code_embeddings_json(chunk_rowid, embedding) VALUES (?, ?)",
            (row_id, json.dumps(vec)),
        )

    conn.execute(
        "INSERT OR REPLACE INTO cache_meta(key,value) VALUES (?,?)",
        ("populated_at", now),
    )
    conn.commit()
    conn.close()

    # Cost logging — record the real token usage when the provider reported it,
    # alongside the estimate (estimate-vs-actual drift calibrates future runs).
    try:
        from . import vector_costs as _vc
        estimated_tokens = len(chunk_text) // 4
        actual_tokens = usage.total_tokens if (usage and usage.has_data) else None
        actual_cost = usage.cost_usd if (usage and usage.has_data) else None
        _vc.log_refresh_batch(
            namespace="code-embeddings-organs",
            model="text-embedding-3-small",
            doc_count=1,
            chunk_count=1,
            estimated_tokens=estimated_tokens,
            provider="openai",
            source_ref=f"organ:{name}:{now[:10]}",
            actual_tokens=actual_tokens,
            actual_cost_usd=actual_cost,
        )
    except Exception as exc:
        logger.warning("find_reusable_component: vector_costs log failed: %s", exc)

    return {"ok": True, "status": "registered", "name": name,
            "source_sha": source_sha, "rows_written": 1}


# ── Public read path: find_reusable_component ─────────────────────────────────


def find_reusable_component(
    query: str,
    *,
    top_k: int = 5,
    filter_status: list[str] | None = None,
    repo_root: Path | None = None,
) -> list[ReusableComponentMatch]:
    """Find reusable seed organs matching a semantic query.

    Embeds ``query`` via the seed LLM pipeline → cosine-top-K search over
    code_chunks WHERE kind='organ' → optionally filter by validation_status →
    enrich with component_bundle wiring_snippet.

    Falls back to graph keyword search if the embedding provider is unreachable.

    Parameters
    ----------
    query:
        Natural-language intent, e.g. "credentials list with multi-account selector".
    top_k:
        Number of results to return (default 5).
    filter_status:
        Optional list of validation statuses to include (e.g. ``["validated"]``).
    repo_root:
        Override repo root (mainly for testing).
    """
    root = repo_root or REPO_ROOT

    # Try embedding-based search first
    try:
        results = _embedding_search(query, top_k=top_k, filter_status=filter_status, root=root)
        if results:
            return results
        # Empty result from embedding search → try fallback
        logger.debug("find_reusable_component: embedding search returned empty, trying keyword fallback")
    except Exception as exc:
        logger.warning(
            "find_reusable_component: embedding search failed (%s) — falling back to keyword search",
            exc,
        )

    # Keyword fallback via graph
    return _keyword_fallback(query, top_k=top_k, filter_status=filter_status, root=root)


def _embedding_search(
    query: str,
    *,
    top_k: int,
    filter_status: list[str] | None,
    root: Path,
) -> list[ReusableComponentMatch]:
    """Vector-similarity search over organ chunks in code-embeddings.sqlite."""
    if not CACHE_PATH.exists():
        logger.debug("find_reusable_component: cache not found at %s", CACHE_PATH)
        return []

    q_vec = _ec.embed_sync(query)
    conn = _connect()
    _ensure_schema(conn)

    rows: list[dict] = []

    if _HAS_VEC:
        q_blob = _ec.pack_vec(q_vec)
        fetch_k = top_k * 4  # fetch extra; we filter by kind + status in Python
        cur = conn.execute(
            """
            SELECT c.path, c.chunk_idx, c.symbol_name, c.kind, c.chunk_text, v.distance
            FROM code_vec v
            JOIN code_chunks c ON c.rowid_alias = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (q_blob, fetch_k),
        )
        for r in cur.fetchall():
            if r["kind"] != ORGAN_CHUNK_KIND:
                continue
            distance = float(r["distance"])
            score = 1.0 / (1.0 + distance)
            rows.append({
                "name": r["symbol_name"],
                "path": r["path"],
                "score": score,
                "chunk_text": r["chunk_text"],
            })
            if len(rows) >= top_k * 2:
                break
    else:
        all_rows = conn.execute(
            """
            SELECT c.path, c.symbol_name, c.kind, c.chunk_text, j.embedding
            FROM code_chunks c
            JOIN code_embeddings_json j ON j.chunk_rowid = c.rowid_alias
            WHERE c.kind = ?
            """,
            (ORGAN_CHUNK_KIND,),
        ).fetchall()
        scored: list[tuple[float, dict]] = []
        for r in all_rows:
            try:
                vec = json.loads(r["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            score = _ec.cosine(q_vec, vec)
            scored.append((score, {
                "name": r["symbol_name"],
                "path": r["path"],
                "score": score,
                "chunk_text": r["chunk_text"],
            }))
        scored.sort(key=lambda t: t[0], reverse=True)
        rows = [d for _, d in scored[: top_k * 2]]

    conn.close()

    return _enrich_matches(rows, filter_status=filter_status, top_k=top_k, root=root)


def _keyword_fallback(
    query: str,
    *,
    top_k: int,
    filter_status: list[str] | None,
    root: Path,
) -> list[ReusableComponentMatch]:
    """Fallback: search organ names by keyword match against query words.

    Not semantic — but works when the embedding provider is unreachable and
    the query mentions a component name or known keyword.
    """
    if not CACHE_PATH.exists():
        return []

    try:
        conn = _connect()
        _ensure_schema(conn)
        organ_rows = conn.execute(
            "SELECT path, symbol_name, chunk_text FROM code_chunks WHERE kind = ?",
            (ORGAN_CHUNK_KIND,),
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.warning("find_reusable_component: keyword fallback DB read failed: %s", exc)
        return []

    query_lower = query.lower()
    query_words = set(query_lower.split())

    scored: list[tuple[int, dict]] = []
    for r in organ_rows:
        name = r["symbol_name"]
        text = (r["chunk_text"] or "").lower()
        # Score = number of query words found in the chunk text
        hits = sum(1 for w in query_words if w in text or w in name.lower())
        if hits > 0:
            scored.append((hits, {"name": name, "path": r["path"], "score": hits / len(query_words),
                                  "chunk_text": r["chunk_text"]}))

    scored.sort(key=lambda t: t[0], reverse=True)
    rows = [d for _, d in scored[: top_k * 2]]
    return _enrich_matches(rows, filter_status=filter_status, top_k=top_k, root=root)


def _enrich_matches(
    rows: list[dict],
    *,
    filter_status: list[str] | None,
    top_k: int,
    root: Path,
) -> list[ReusableComponentMatch]:
    """Enrich raw search rows with validation_status + consumers_count + snippet."""
    from .component_bundle import bundle_component
    from .component_list import list_components

    # Build a status+consumers lookup from component_list (fast — in-process cache)
    status_map: dict[str, str] = {}
    consumers_map: dict[str, int] = {}
    try:
        all_components = list_components(repo_root=root)
        for entry in all_components:
            status_map[entry.name] = entry.validation_status
            consumers_map[entry.name] = entry.consumers_count
    except Exception as exc:
        logger.debug("find_reusable_component: list_components failed: %s", exc)

    results: list[ReusableComponentMatch] = []
    for row in rows:
        name = row["name"]
        validation_status = status_map.get(name, "unknown")

        if filter_status and validation_status not in filter_status:
            continue

        consumers_count = consumers_map.get(name, 0)

        # Get wiring snippet from bundle (lazy, per match)
        snippet = f"<{name} />"
        try:
            bundle = bundle_component(name, fallback_when_w1_missing=True, repo_root=root)
            if bundle:
                snippet = bundle.wiring_snippet
        except Exception:
            pass

        results.append(ReusableComponentMatch(
            name=name,
            path=row.get("path"),
            score=float(row["score"]),
            validation_status=validation_status,
            consumers_count=consumers_count,
            snippet=snippet,
        ))

        if len(results) >= top_k:
            break

    return results


# ── Bulk registration (used in W4 registration script) ───────────────────────


CANONICAL_ORGANS = [
    "LoginForm",
    "ForgotPasswordPage",
    "AcceptInvitePage",
    "ResourceManager",
    "DigestCard",
]

# Phase 2 — emerging organs formalized 2026-05-29 (W2.3).
# Sidecar ships organ_version + kind fields for hooks/helpers.
PHASE_2_ORGANS = [
    "AppShell",
    "Sidebar",
    "Header",
    "ScorePill",
    "RankBadge",
    "NotificationBell",
    "LLMProviderSelector",
    "ProgressRing",
    "AIBadgeStack",
    "AIFeedbackButtons",
    "AIIndicator",
    "InactivityWarning",
    "useActivityRefresh",
    "useTheme",
    "splitProseIntoParagraphs",
]

# Hooks and helpers within Phase 2 that carry kind=hook or kind=helper.
PHASE_2_HOOKS_AND_HELPERS = [
    "useActivityRefresh",
    "useTheme",
    "splitProseIntoParagraphs",
]

SHELFWARE_ORGANS = [
    "PageSkeleton",
    "LLMSpendBadge",
    "FakeModeBadge",
    "ErrorBoundary",
]


def register_all_canonical_organs(
    *,
    force: bool = False,
    repo_root: Path | None = None,
) -> list[dict]:
    """Register all 5 canonical Phase-1 organs. Idempotent.

    Returns a list of registration results, one per organ.
    """
    root = repo_root or REPO_ROOT
    results = []
    for name in CANONICAL_ORGANS:
        result = register_organ(name, force=force, repo_root=root)
        logger.info(
            "find_reusable_component: organ=%r status=%s sha=%s",
            name, result.get("status"), result.get("source_sha", "")[:12],
        )
        results.append(result)
    return results


# ── MCP registration ──────────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.find_reusable_component",
        description=(
            "Query the seed organ catalog by intent. "
            "Embeds the query via OpenAI text-embedding-3-small → cosine-top-K "
            "search over code-embeddings.sqlite WHERE chunk_kind='organ' → "
            "optionally filters by validation_status → returns top-K matches "
            "with name, path, score, validation_status, consumers_count, and "
            "wiring_snippet from the component_bundle. "
            "Falls back to keyword search if the embedding provider is unreachable. "
            "Example: find_reusable_component('credentials list with multi-account selector') "
            "→ returns ResourceManager in top-3. "
            "KB § PATTERNS/architect/seed-organ-canonical-set.md"
        ),
    )
    def _find_reusable_component(
        query: str,
        top_k: int = 5,
        filter_status: Optional[list[str]] = None,
    ) -> list[dict]:
        results = find_reusable_component(query, top_k=top_k, filter_status=filter_status)
        return [r.model_dump() for r in results]

    @server.tool(
        name="noctus.dev.register_organ",
        description=(
            "Embed a seed organ into the code-embeddings cache (chunk_kind='organ'). "
            "Idempotent: skips if source_sha matches current. "
            "``force=True`` re-embeds regardless. "
            "Called once per organ on registration; called again when the "
            "organ's source, tests, or knowledge bundle changes. "
            "Returns {ok, status, name, source_sha, rows_written}."
        ),
    )
    def _register_organ(name: str, force: bool = False) -> dict:
        return register_organ(name, force=force)

    @server.tool(
        name="noctus.dev.register_all_canonical_organs",
        description=(
            "Register all 5 Phase-1 canonical seed organs (LoginForm, "
            "ForgotPasswordPage, AcceptInvitePage, ResourceManager, DigestCard) "
            "into the code-embeddings cache. Idempotent. "
            "``force=True`` re-embeds all regardless of source_sha. "
            "Returns list of {ok, status, name, source_sha, rows_written}."
        ),
    )
    def _register_all(force: bool = False) -> list[dict]:
        return register_all_canonical_organs(force=force)


__all__ = [
    "ReusableComponentMatch",
    "CANONICAL_ORGANS",
    "PHASE_2_ORGANS",
    "PHASE_2_HOOKS_AND_HELPERS",
    "SHELFWARE_ORGANS",
    "ORGAN_CHUNK_KIND",
    "register_organ",
    "register_all_canonical_organs",
    "find_reusable_component",
    "register",
]
