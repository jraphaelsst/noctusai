"""scan_repetition_semantic — semantic variant of seed.scan_repetition.

Why this exists
    The existing `noctus.seed.scan_repetition` is grep-based: it finds
    *literally* duplicated lines/blocks across products. It MISSES the
    common case where two products implement the same logic with
    different variable names + slightly different structure. The
    absorb-to-seed bottleneck IS exactly that case — semantically
    identical code with cosmetic differences.

    This module is the semantic variant: walks the code-embeddings
    cache (W2-E3'), finds clusters of similar symbols ACROSS products,
    surfaces absorption candidates.

Composition
    Builds on:
      - code_embeddings (the corpus + chunks)
      - code_recurrence_promote.scan (the cross-product pair-finding loop)

    Differs from code_recurrence_promote.scan in scope:
      - scan_repetition_semantic: emphasis on ABSORB-TO-SEED candidates;
        surfaces only pairs where the products differ (one isn't from
        seed) + groups by symbol-name similarity for cluster discovery.
      - code_recurrence_promote.scan: corpus-wide pair discovery for
        the codification pipeline (any pair, any band).

    Same underlying engine (cosine), different filtering + surface.

KB § CONTEXT/PATTERNS/common/scan-repetition-semantic.md.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


# Path-segment that marks the SEED. A pair where one side has this segment
# and the other doesn't is a STRONG absorb-to-seed signal (the non-seed
# product is implementing what the seed already provides).
_SEED_PATH_MARKERS = ("products/seed/", "seed/lib/")

# Path-segment that marks per-product code.
_PRODUCT_PATH_PATTERN = "products/"


def _path_kind(path: str) -> str:
    """Classify a code path into 'seed' / 'product:<slug>' / 'shared'."""
    if any(marker in path for marker in _SEED_PATH_MARKERS):
        return "seed"
    if _PRODUCT_PATH_PATTERN in path:
        # extract product slug
        parts = path.split("/")
        if "products" in parts:
            idx = parts.index("products")
            if idx + 1 < len(parts):
                return f"product:{parts[idx + 1]}"
    return "shared"


def _is_absorb_candidate(kind_a: str, kind_b: str) -> bool:
    """A pair is an absorption candidate when:
    - Both are products (different products) ⇒ recurrence candidate.
    - One is seed + other is product ⇒ the product is reimplementing seed.
    Same product OR both seed ⇒ not interesting for absorption.
    """
    if kind_a == kind_b:
        return False  # same source, no cross-product
    return True


def scan(
    threshold: float = 0.8,
    top_k_per_anchor: int = 5,
    limit: int = 200,
    band_strong: float = 0.9,
    band_medium: float = 0.8,
) -> dict[str, Any]:
    """Scan the code corpus for cross-product semantic repetition.

    Builds on `code_recurrence_promote.scan` filtering for absorb-to-seed
    candidates (same-product pairs excluded; seed-vs-product pairs
    flagged as 'reimplementation').

    Args:
      threshold: minimum cosine score (default 0.8 — stricter than
        code_recurrence_promote's 0.7; absorb-to-seed wants higher
        confidence).
      top_k_per_anchor: neighbors per anchor.
      limit: cap on returned candidates.
      band_strong / band_medium: re-band thresholds.

    Returns:
      {
        ok: bool,
        threshold: float,
        total_candidates: int,
        candidates: [
          {
            a: {path, symbol_name, kind, path_kind},
            b: {path, symbol_name, kind, path_kind},
            score: float,
            band: 'strong'|'medium',
            reimplementation_of_seed: bool,
            cluster_id: int,           # candidates that share a path-kind pair group together
          },
          ...
        ],
        clusters: { cluster_id: count },
      }
    """
    try:
        from . import code_embeddings as ce
        from . import code_recurrence_promote as crp
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"required modules unavailable: {e}"}

    rows = ce._load_all_chunk_vectors()
    if not rows:
        return {
            "ok": True, "threshold": threshold,
            "total_candidates": 0, "candidates": [], "clusters": {},
            "message": "code-embeddings cache empty — run "
                       "`noctus.dev.code_embeddings_refresh` first.",
        }

    # Reuse the pair-finding loop from code_recurrence_promote, then
    # filter for cross-source pairs.
    raw_result = crp.scan(threshold=threshold, top_k_per_file=top_k_per_anchor,
                          limit=limit * 3)  # 3x limit pre-filter
    if not raw_result.get("ok"):
        return raw_result

    candidates: list[dict[str, Any]] = []
    cluster_map: dict[tuple[str, str], int] = {}
    next_cluster_id = 0

    for cluster in raw_result.get("clusters", []):
        a = cluster["a"]
        b = cluster["b"]
        kind_a = _path_kind(a["path"])
        kind_b = _path_kind(b["path"])
        if not _is_absorb_candidate(kind_a, kind_b):
            continue
        score = cluster["score"]
        if score >= band_strong:
            band = "strong"
        elif score >= band_medium:
            band = "medium"
        else:
            # Below the absorb-emphasis threshold; the parent loop already
            # filtered by `threshold`, but defensive re-check.
            continue
        reimpl = (kind_a == "seed") ^ (kind_b == "seed")
        # Cluster by (path_kind pair) — canonical-ordered.
        kind_pair = tuple(sorted([kind_a, kind_b]))
        if kind_pair not in cluster_map:
            cluster_map[kind_pair] = next_cluster_id
            next_cluster_id += 1
        cluster_id = cluster_map[kind_pair]
        candidates.append({
            "a": {**a, "path_kind": kind_a},
            "b": {**b, "path_kind": kind_b},
            "score": score,
            "band": band,
            "reimplementation_of_seed": reimpl,
            "cluster_id": cluster_id,
        })
        if len(candidates) >= limit:
            break

    # Sort: reimpl-of-seed first (highest absorb-to-seed signal), then by
    # band priority, then by score desc.
    band_rank = {"strong": 0, "medium": 1}
    candidates.sort(key=lambda c: (
        0 if c["reimplementation_of_seed"] else 1,
        band_rank[c["band"]],
        -c["score"],
    ))

    clusters: dict[int, int] = defaultdict(int)
    for c in candidates:
        clusters[c["cluster_id"]] += 1

    return {
        "ok": True,
        "threshold": threshold,
        "total_candidates": len(candidates),
        "candidates": candidates[:limit],
        "clusters": dict(clusters),
        "reimplementation_count": sum(1 for c in candidates if c["reimplementation_of_seed"]),
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_repetition_semantic",
        description=(
            "Semantic variant of `noctus.seed.scan_repetition` — finds "
            "cross-product code patterns that LOOK similar even when the "
            "identifiers differ. Filters for absorb-to-seed candidates: "
            "same-product pairs excluded; seed-vs-product pairs flagged "
            "with `reimplementation_of_seed=True`. Returns ranked "
            "candidates with cluster grouping by path-kind pair. Default "
            "threshold 0.8 (stricter than code_recurrence_promote's 0.7 "
            "because absorb-to-seed needs higher confidence). "
            "KB § CONTEXT/PATTERNS/common/scan-repetition-semantic.md."
        ),
    )
    def _scan(threshold: float = 0.8, top_k_per_anchor: int = 5,
              limit: int = 200) -> dict:
        return scan(threshold=threshold, top_k_per_anchor=top_k_per_anchor,
                    limit=limit)


__all__ = ["scan", "register"]
