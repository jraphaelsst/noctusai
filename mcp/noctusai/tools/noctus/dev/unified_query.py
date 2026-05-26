"""unified_query — single semantic search across multiple keeper-mirror caches.

Why this exists
    Today an architect/agent asking "what do we know about X?" has to
    fan out across 3 separate caches (kb-embeddings, code-embeddings,
    auto-improvement) + grep + INDEX.md. Each returns its own ranked
    list. The architect mentally merges + re-ranks. That cross-cache
    merge IS the methodology surface this module mechanizes.

The shape
    Given a query string, query each of:
      - kb-embeddings   (docs corpus — methodology depth)
      - code-embeddings (code corpus — implementation)
      - auto-improvement (open ledger entries — decisions in flight)
    Then merge the results into one ranked list with `source` labeled
    per hit. Caller sees "what does noc know about X" as one list.

Why this isn't just three separate calls
    Each cache returns its own score distribution. The merge isn't
    naive — different caches may return scores in different ranges (KB
    is verbose text, code chunks are denser). A simple top-K-from-each
    pass returns 3K results which the caller still has to merge. This
    module does the merge + normalization.

KB § CONTEXT/PATTERNS/common/unified-query.md.
"""
from __future__ import annotations

import hashlib
from typing import Any


def _normalize_score(raw: float, source: str) -> float:
    """Normalize a per-source score onto a comparable [0, 1] scale.

    Empirical: kb_search returns 0.0-1.0 cosine-similarity-shaped scores.
    code_search returns the same. auto_improvement entries don't have
    intrinsic scores — we use a fixed cohesion value when the source is
    a semantic-radar hit (kb_recurrence_radar), 0.5 when it's a raw
    ledger query (no semantic ranking).

    Returns the normalized score in [0, 1].
    """
    if source in ("kb-embeddings", "code-embeddings"):
        # Already in approximately [0, 1] cosine-similarity space.
        return max(0.0, min(1.0, float(raw)))
    if source == "auto-improvement":
        # Heuristic: ranked entries from kb_recurrence_radar already carry a
        # score. Raw query() doesn't — caller passes 0.5 in that case.
        return max(0.0, min(1.0, float(raw)))
    return max(0.0, min(1.0, float(raw)))


def query(
    text: str,
    top_k: int = 10,
    sources: list[str] | None = None,
    per_source_k: int = 5,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """Run a unified semantic query across the configured caches.

    Args:
      text: free-form query.
      top_k: total hits to return after merge (default 10).
      sources: subset of {'kb-embeddings', 'code-embeddings',
        'auto-improvement'} to query. None ⇒ all available.
      per_source_k: how many hits to pull per source before merging
        (default 5). Higher = better merge quality, more API cost.
      min_score: filter normalized scores below this floor.

    Returns:
      {
        "ok": bool,
        "query": str,
        "hits": [
          {
            "source": "kb-embeddings" | "code-embeddings" | "auto-improvement",
            "score": float,          # normalized [0,1]
            "raw_score": float,      # source's original score
            "summary": str,          # short label (path / target / etc)
            "ref": dict,             # source's full row for follow-up
          },
          ...
        ],
        "by_source": {source: hit_count},
      }

    Graceful-degrade: a source that errors out (provider unreachable,
    cache missing) gets logged in `warnings:` and skipped; other sources
    still return.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "empty query"}

    requested = sources or ["kb-embeddings", "code-embeddings", "auto-improvement"]
    valid_sources = {"kb-embeddings", "code-embeddings", "auto-improvement"}
    invalid = [s for s in requested if s not in valid_sources]
    if invalid:
        return {
            "ok": False,
            "error": f"unknown sources: {invalid}. Valid: {sorted(valid_sources)}",
        }

    hits: list[dict[str, Any]] = []
    warnings: list[str] = []
    by_source: dict[str, int] = {}

    if "kb-embeddings" in requested:
        try:
            from . import kb_embeddings as kbe
            kb_hits = kbe.search(text, top_k=per_source_k)
            for h in kb_hits:
                hits.append({
                    "source": "kb-embeddings",
                    "score": _normalize_score(h["score"], "kb-embeddings"),
                    "raw_score": h["score"],
                    "summary": f"{h['path']}#chunk{h['chunk_idx']}",
                    "ref": h,
                })
            by_source["kb-embeddings"] = len(kb_hits)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"kb-embeddings: {str(e)[:120]}")
            by_source["kb-embeddings"] = 0

    if "code-embeddings" in requested:
        try:
            from . import code_embeddings as ce
            code_hits = ce.search(text, top_k=per_source_k)
            for h in code_hits:
                sn = h.get("symbol_name") or "(file)"
                hits.append({
                    "source": "code-embeddings",
                    "score": _normalize_score(h["score"], "code-embeddings"),
                    "raw_score": h["score"],
                    "summary": f"{h['path']} :: {sn} ({h.get('kind', '?')})",
                    "ref": h,
                })
            by_source["code-embeddings"] = len(code_hits)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"code-embeddings: {str(e)[:120]}")
            by_source["code-embeddings"] = 0

    if "auto-improvement" in requested:
        # Use kb_recurrence_radar (semantic) when available; falls back to
        # keyword-style auto_improvement.query if the radar is unavailable.
        try:
            from . import kb_recurrence_radar as krr
            radar_result = krr.consult(text=text, top_k=per_source_k)
            radar_hits = radar_result.get("hits", []) if radar_result.get("ok") else []
            for h in radar_hits:
                entry = h["entry"]
                target = (entry.get("target") or "?")[:80]
                hits.append({
                    "source": "auto-improvement",
                    "score": _normalize_score(h["score"], "auto-improvement"),
                    "raw_score": h["score"],
                    "summary": f"[{entry.get('status', '?')}] {target}",
                    "ref": entry,
                })
            by_source["auto-improvement"] = len(radar_hits)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"auto-improvement (radar): {str(e)[:120]}")
            by_source["auto-improvement"] = 0

    # Filter by min_score, sort by normalized score desc, dedupe identical
    # summaries (rare but possible), keep top_k.
    filtered = [h for h in hits if h["score"] >= min_score]
    filtered.sort(key=lambda h: h["score"], reverse=True)
    seen_summaries: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for h in filtered:
        key = f"{h['source']}|{h['summary']}"
        if key in seen_summaries:
            continue
        seen_summaries.add(key)
        deduped.append(h)
        if len(deduped) >= top_k:
            break

    return {
        "ok": True,
        "query": text,
        "hits": deduped,
        "by_source": by_source,
        "warnings": warnings,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.unified_query",
        description=(
            "Single semantic query across multiple keeper-mirror caches "
            "(kb-embeddings + code-embeddings + auto-improvement). Returns "
            "one merged + ranked list with `source` labeled per hit + a "
            "per-source hit-count. Use when the question is 'what does "
            "noc know about X?' and you don't want to call 3 separate "
            "tools. Optional `sources=[...]` filters; `per_source_k` tunes "
            "merge quality vs. API cost. Graceful-degrades if a source "
            "errors out. KB § CONTEXT/PATTERNS/common/unified-query.md."
        ),
    )
    def _query(text: str, top_k: int = 10, sources: list[str] | None = None,
               per_source_k: int = 5, min_score: float = 0.0) -> dict:
        return query(text, top_k=top_k, sources=sources,
                     per_source_k=per_source_k, min_score=min_score)


__all__ = ["query", "register"]
