"""kb_recurrence_radar — semantic consult-before-editing for auto-improvement.

Why this exists
    Before editing a KB doc / writing a new pattern / refactoring an
    agent, the architect SHOULD know what `auto-improvement.ndjson`
    already says about that surface. The existing
    `auto_improvement.query` is keyword-based: it returns entries whose
    target string matches. But auto-improvement entries are often phrased
    abstractly — an entry about "engineer dispatch stale-base hazard"
    might never mention "task_branch" by name, even though it's load-
    bearing context if you're touching task_branch.py.

    THIS module bridges that gap: given a path being edited OR free text
    being authored, embed it and find auto-improvement entries by
    SEMANTIC similarity (cosine over description). Same engine as
    kb-embeddings (OpenAI text-embedding-3-small via seed lib) — no new
    external dep.

Sibling pattern
    `code_recurrence_promote` (W3-E1) was discovery for CODE; this is
    consult-before-edit for KB/decisions. Together they close two
    different feedback loops:

       code_recurrence_promote → "what similar code exists?"
       kb_recurrence_radar     → "what decisions exist about this surface?"

How it works
    1. Load open auto-improvement entries via `auto_improvement.query`.
    2. Embed each entry's description ONCE per session (cache in-memory
       keyed by entry sha — descriptions are stable text). For a small
       open set (≤100 entries) this is one API batch.
    3. Embed the query (anchor path / free text).
    4. Compute cosine vs every cached description embedding.
    5. Return top-K ranked entries.

KB § CONTEXT/PATTERNS/common/kb-recurrence-radar.md.
"""
from __future__ import annotations

import hashlib
from typing import Any


# Module-level in-session embedding cache: entry_sha → vector.
# Survives across calls within one process; drops on restart.
_DESCRIPTION_EMBEDDING_CACHE: dict[str, list[float]] = {}


def _entry_sha(entry: dict) -> str:
    """Stable hash of an entry's description — embedding cache key."""
    desc = entry.get("description", "")
    return hashlib.sha256(desc.encode("utf-8")).hexdigest()


def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine. Reuse kb_embeddings's tuned version when available
    (cleaner) with a local fallback so this module stays import-safe."""
    try:
        from . import kb_embeddings as kbe
        return kbe._cosine(a, b)
    except Exception:  # noqa: BLE001
        import math
        dot = na = nb = 0.0
        for x, y in zip(a, b):
            dot += x * y
            na += x * x
            nb += y * y
        if na == 0 or nb == 0:
            return 0.0
        return dot / (math.sqrt(na) * math.sqrt(nb))


def _embed(text: str) -> list[float] | None:
    """Embed `text` via the shared seed embedder. Returns None on failure
    (advisory layer — never crash on provider unavailability)."""
    if not text or not text.strip():
        return None
    try:
        from . import vectorize
        result = vectorize.embed_text(text, namespace="kb_recurrence_radar")
        if result.get("ok") and "vector" in result:
            return result["vector"]
    except Exception:  # noqa: BLE001
        return None
    return None


def _populate_entry_embeddings(entries: list[dict]) -> dict[str, list[float]]:
    """Ensure every entry has a cached embedding; return {sha → vector}.

    Skips entries whose descriptions fail to embed (advisory degrade).
    """
    out: dict[str, list[float]] = {}
    for e in entries:
        sha = _entry_sha(e)
        if sha in _DESCRIPTION_EMBEDDING_CACHE:
            out[sha] = _DESCRIPTION_EMBEDDING_CACHE[sha]
            continue
        vec = _embed(e.get("description", ""))
        if vec is None:
            continue
        _DESCRIPTION_EMBEDDING_CACHE[sha] = vec
        out[sha] = vec
    return out


# ── Public API ───────────────────────────────────────────────────────────────
def consult(
    text: str | None = None,
    path: str | None = None,
    top_k: int = 5,
    min_score: float = 0.0,
    open_only: bool = True,
    limit_entries: int = 500,
) -> dict:
    """Semantic search over auto-improvement entries.

    Provide EITHER `text` (free-form draft / question) OR `path` (a file
    path being edited; the consult uses the path string + any frontmatter
    H1 if a `.md` file). Returns top-K ranked entries.

    Args:
      text: free-form anchor. Embeds verbatim.
      path: repo-relative file path. When provided, the query is the path
        string + (if a markdown file) the H1 title for stronger signal.
      top_k: number of hits to return (default 5).
      min_score: filter floor (default 0.0).
      open_only: read only s1/s2/s3 entries (default True; s4-keeper +
        closed are noise for "what should I know about this surface?").
      limit_entries: cap on how many entries to scan (default 500).

    Returns:
      `{ok, query, hits: [{entry, score, key_overlap}], message?}`.
      `entry` is the full auto-improvement record; `score` is the cosine
      similarity in [-1, 1]; `key_overlap` is a coarse target-string
      substring check for transparency (does the hit happen to share
      keywords too?).

    Graceful-degrade: empty `hits` when provider unreachable / no entries.
    """
    if not text and not path:
        return {"ok": False, "error": "provide either `text` or `path`."}

    # Build the query string.
    query = text or ""
    if path and not query:
        query = path
        # If a markdown file, prepend the H1 title for better signal.
        if path.endswith(".md"):
            try:
                from settings import REPO_ROOT
                md = REPO_ROOT / path
                if md.is_file():
                    for line in md.read_text(encoding="utf-8").splitlines():
                        ln = line.strip()
                        if ln.startswith("# "):
                            query = f"{ln[2:].strip()} — {path}"
                            break
            except Exception:  # noqa: BLE001
                pass

    # Pull entries.
    try:
        from . import auto_improvement as ai
        entries = ai.query(open_only=open_only, limit=limit_entries)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"auto_improvement query failed: {e}"}

    if not entries:
        return {
            "ok": True, "query": query, "hits": [],
            "message": "no open auto-improvement entries to consult.",
        }

    # Ensure descriptions embedded.
    sha_to_vec = _populate_entry_embeddings(entries)
    if not sha_to_vec:
        return {
            "ok": True, "query": query, "hits": [],
            "message": "embedding provider unreachable — consult skipped.",
        }

    # Embed query.
    q_vec = _embed(query)
    if q_vec is None:
        return {
            "ok": True, "query": query, "hits": [],
            "message": "could not embed query — provider unreachable.",
        }

    # Score every entry.
    scored: list[tuple[float, dict[str, Any]]] = []
    q_lower = query.lower()
    for e in entries:
        sha = _entry_sha(e)
        vec = sha_to_vec.get(sha)
        if vec is None:
            continue
        score = _cosine(q_vec, vec)
        if score < min_score:
            continue
        # Coarse keyword overlap (substring) — surfaces "this hit also
        # mentions the surface" alongside the semantic score so the
        # architect can sanity-check.
        target = (e.get("target") or "").lower()
        desc = (e.get("description") or "").lower()
        keyword_overlap = bool(
            (path and (path.lower() in target or path.lower() in desc))
            or (text and any(tok in target or tok in desc
                             for tok in q_lower.split() if len(tok) > 4))
        )
        scored.append((score, {
            "entry": e,
            "score": score,
            "key_overlap": keyword_overlap,
        }))
    scored.sort(key=lambda t: t[0], reverse=True)
    return {
        "ok": True,
        "query": query,
        "hits": [d for _, d in scored[:top_k]],
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.kb_recurrence_radar",
        description=(
            "Semantic consult-before-editing over auto-improvement.ndjson. "
            "Given a path being edited OR free-form text being authored, "
            "find open auto-improvement entries semantically related (cosine "
            "over description). Complements `auto_improvement.query` "
            "(keyword-based) by surfacing entries that DESCRIBE the surface "
            "without naming it. Use BEFORE editing a KB doc / pattern / "
            "agent — the related decisions might constrain your change. "
            "Returns [{entry, score, key_overlap}]. Graceful-degrades to "
            "empty hits on provider failure (advisory layer). "
            "KB § CONTEXT/PATTERNS/common/kb-recurrence-radar.md."
        ),
    )
    def _radar(text: str | None = None, path: str | None = None,
               top_k: int = 5, min_score: float = 0.0,
               open_only: bool = True, limit_entries: int = 500) -> dict:
        return consult(text=text, path=path, top_k=top_k,
                       min_score=min_score, open_only=open_only,
                       limit_entries=limit_entries)


__all__ = ["consult", "register"]
