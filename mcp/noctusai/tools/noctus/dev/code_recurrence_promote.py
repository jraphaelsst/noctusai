"""code_recurrence_promote — close the cross-product recurrence loop.

Why this exists
    The code-embeddings cache (W2-E3') gave us `code_neighbors(path,
    symbol_name)` — find code symbols semantically similar to an anchor.
    Useful, but PASSIVE: the architect has to remember to ask. The DRY
    recurrence rule (N=3+ MUST formalize) wants this to be AUTOMATIC.

    THIS module is the active side: scan the WHOLE code corpus for
    same-shape pairs above a similarity threshold, dedupe, group by
    score-band, then PROMOTE each cluster to `auto-improvement.ndjson`
    as an `s1-emergent` entry. The codification_radar (W2-E4') then
    picks up clusters and surfaces s1→s2→s3 promotion candidates on
    the next pass.

Pipeline now closed
    code_embeddings (W2-E3') → code_recurrence_promote (THIS) →
    auto-improvement.ndjson → codification_radar (W2-E4') → surfaces
    s3-kb candidates for the architect to absorb to seed.

How it works
    1. `scan(threshold, top_k_per_file, limit)`:
       - Loads every chunk from the code-embeddings cache.
       - For each unique (path, symbol_name) anchor, runs
         `code_neighbors` with the same anchor (top_k_per_file).
       - Filters to score >= threshold.
       - Dedupes pairs ({A, B} == {B, A}; canonical-orders by sorted
         path+symbol).
       - Groups results by score-band (≥0.9 strong / 0.8-0.9 medium /
         0.7-0.8 weak).
       - Returns `{ok, threshold, total_pairs, strong, medium, weak,
         clusters: [...]}`.

    2. `promote(matches, target_status='s1-emergent', source_ref=None)`:
       - For each match, calls `auto_improvement.log_entry()` with:
         * scope: 'broad' (cross-product surface)
         * kind: 'recurrence'
         * target: 'code-recurrence:<path1>::<sym1> ≈ <path2>::<sym2>'
         * description: structured pair info + score + band
       - Returns `{ok, promoted, skipped, errors}`.
       - Idempotent guard: skips pairs already promoted (by target string
         match against the in-memory entries from auto_improvement.query).

KB § CONTEXT/PATTERNS/common/code-embeddings.md § Deferred next-slices.
"""
from __future__ import annotations

from typing import Any


# ── Score-band thresholds (tunable; tracked in KB doc) ─────────────────────
BAND_STRONG = 0.90
BAND_MEDIUM = 0.80
BAND_WEAK = 0.70   # below this = noise; not promoted by default


def _band(score: float) -> str:
    if score >= BAND_STRONG:
        return "strong"
    if score >= BAND_MEDIUM:
        return "medium"
    return "weak"


def _pair_key(a_path: str, a_sym: str, b_path: str, b_sym: str) -> tuple[str, str, str, str]:
    """Canonical-order a pair so {A,B} == {B,A} in dedupe set.

    Order by (path, symbol_name) lex so A→B and B→A canonicalize to the
    same tuple regardless of which was the anchor when scoring."""
    left = (a_path, a_sym)
    right = (b_path, b_sym)
    if left <= right:
        return (a_path, a_sym, b_path, b_sym)
    return (b_path, b_sym, a_path, a_sym)


def _target_string(p1: str, s1: str, p2: str, s2: str) -> str:
    """The target string written to auto-improvement.ndjson — also the
    idempotency key for `promote()` (skip-if-exists check matches this)."""
    return f"code-recurrence:{p1}::{s1} ≈ {p2}::{s2}"


# ── Public API ───────────────────────────────────────────────────────────────
def scan(
    threshold: float = BAND_WEAK,
    top_k_per_file: int = 3,
    limit: int = 200,
) -> dict:
    """Scan the code corpus for symbol pairs above similarity threshold.

    Args:
      threshold: minimum cosine score to keep (default: BAND_WEAK = 0.7).
      top_k_per_file: how many neighbors per anchor to consider (default 3
        — keeps signal sharp; raise for fuzzier recall).
      limit: cap on total pairs returned (default 200 — for large corpora).

    Returns: `{ok, threshold, total_pairs, by_band: {strong, medium, weak},
              clusters: [{score, band, a: {path, symbol_name, kind},
                          b: {path, symbol_name, kind}}, ...]}`
    Ordered: strong first, then medium, then weak; within band by score desc.

    Graceful-degrade: empty `clusters` when the cache is missing or empty.
    """
    try:
        from . import code_embeddings as ce
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "code_embeddings module unimportable"}

    rows = ce._load_all_chunk_vectors()
    if not rows:
        return {
            "ok": True, "threshold": threshold, "total_pairs": 0,
            "by_band": {"strong": 0, "medium": 0, "weak": 0},
            "clusters": [],
            "message": "code-embeddings cache empty — run "
                       "`noctus.dev.code_embeddings_refresh` first.",
        }

    # Build the set of unique anchors (one per chunk).
    anchors = [(p, idx, sym, k) for p, idx, sym, k, _txt, _vec in rows]

    seen_pairs: set[tuple[str, str, str, str]] = set()
    clusters: list[dict[str, Any]] = []

    for path, _idx, symbol, kind in anchors:
        if len(clusters) >= limit:
            break
        neighbors = ce.code_neighbors(path, symbol_name=symbol, top_k=top_k_per_file)
        for n in neighbors:
            score = n["score"]
            if score < threshold:
                continue
            key = _pair_key(path, symbol, n["path"], n["symbol_name"])
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            clusters.append({
                "score": score,
                "band": _band(score),
                "a": {"path": key[0], "symbol_name": key[1], "kind": kind},
                "b": {"path": key[2], "symbol_name": key[3], "kind": n["kind"]},
            })
    # Sort: band priority (strong > medium > weak) then score desc.
    band_rank = {"strong": 0, "medium": 1, "weak": 2}
    clusters.sort(key=lambda c: (band_rank[c["band"]], -c["score"]))
    by_band = {
        "strong": sum(1 for c in clusters if c["band"] == "strong"),
        "medium": sum(1 for c in clusters if c["band"] == "medium"),
        "weak":   sum(1 for c in clusters if c["band"] == "weak"),
    }
    return {
        "ok": True,
        "threshold": threshold,
        "total_pairs": len(clusters),
        "by_band": by_band,
        "clusters": clusters[:limit],
    }


def promote(
    matches: list[dict],
    target_status: str = "s1-emergent",
    source_ref: str | None = None,
    skip_existing: bool = True,
) -> dict:
    """Write each match to auto-improvement.ndjson as a recurrence entry.

    Args:
      matches: list from scan()['clusters'] — each must have a/b/score/band.
      target_status: starting codification stage (default s1-emergent).
      source_ref: optional provenance string (e.g. 'session:2026-05-26').
      skip_existing: if True, skip pairs already in the ledger (idempotency).

    Returns: `{ok, promoted: [{target, status}], skipped: [target,...],
              errors: [...]}`.

    Composes with `codification_radar.cluster` — after promote, the radar
    picks up these s1-emergent entries on its next pass and surfaces
    s2/s3 candidates when N≥3 cluster at high cosine.
    """
    try:
        from . import auto_improvement as ai
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"auto_improvement unimportable: {e}"}

    if target_status not in ai.STATUSES:
        return {
            "ok": False,
            "error": f"target_status must be one of {sorted(ai.STATUSES)}; got {target_status!r}",
        }

    # Build the existing-target set once for the idempotency guard.
    existing_targets: set[str] = set()
    if skip_existing:
        try:
            current = ai.query(open_only=False, limit=10_000)
            existing_targets = {e["target"] for e in current if "target" in e}
        except Exception:  # noqa: BLE001 — never crash on query failure
            existing_targets = set()

    promoted: list[dict] = []
    skipped: list[str] = []
    errors: list[dict] = []

    for m in matches:
        try:
            a, b = m["a"], m["b"]
            score = float(m["score"])
            band = m.get("band") or _band(score)
        except (KeyError, ValueError, TypeError) as e:
            errors.append({"match": m, "error": f"malformed match: {e}"})
            continue
        # Re-canonicalize even when scan was the source: defensive for
        # hand-crafted matches, and the idempotency key MUST be order-stable.
        canon = _pair_key(a["path"], a["symbol_name"], b["path"], b["symbol_name"])
        # Find which input side ended up first in canonical order so the
        # `a`/`b` kinds we emit match the canonical paths.
        if (a["path"], a["symbol_name"]) == (canon[0], canon[1]):
            ca, cb = a, b
        else:
            ca, cb = b, a
        target = _target_string(canon[0], canon[1], canon[2], canon[3])
        if skip_existing and target in existing_targets:
            skipped.append(target)
            continue
        description = (
            f"Cross-product recurrence candidate: `{ca['path']}::{ca['symbol_name']}` "
            f"({ca.get('kind', 'unknown')}) ≈ `{cb['path']}::{cb['symbol_name']}` "
            f"({cb.get('kind', 'unknown')}); cosine={score:.3f} band={band}. "
            f"Surfaced by code_recurrence_promote.scan. If N≥3 such pairs "
            f"cluster on the same surface, consider absorption to seed "
            f"(DRY recurrence rule)."
        )
        # `kind=improvement`: cross-product recurrence is a class of
        # codification-pipeline improvement. The `code-recurrence:` prefix
        # in `target` carries the slice-specific provenance; downstream
        # filters key on the prefix.
        result = ai.log_entry(
            scope="broad",
            kind="improvement",
            target=target,
            description=description,
            agent="code_recurrence_promote",
            status=target_status,
            source_ref=source_ref,
        )
        if not result.get("ok"):
            errors.append({"target": target, "error": result.get("error", "log_entry failed")})
            continue
        promoted.append({"target": target, "status": target_status, "score": score})

    return {
        "ok": not errors,
        "promoted": promoted,
        "skipped": skipped,
        "errors": errors,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.code_recurrence_scan",
        description=(
            "Scan the code corpus for symbol pairs above a cosine similarity "
            "threshold (default 0.7). Dedupes pair direction, groups by "
            "score-band (strong ≥0.9 / medium ≥0.8 / weak ≥0.7), returns "
            "ordered clusters. The ACTIVE side of code_neighbors: instead "
            "of waiting for the architect to ask, surfaces recurrence "
            "candidates corpus-wide. Pair with code_recurrence_promote to "
            "feed s1-emergent entries into the codification pipeline. "
            "KB § CONTEXT/PATTERNS/common/code-embeddings.md."
        ),
    )
    def _scan(threshold: float = BAND_WEAK, top_k_per_file: int = 3,
              limit: int = 200) -> dict:
        return scan(threshold=threshold, top_k_per_file=top_k_per_file, limit=limit)

    @server.tool(
        name="noctus.dev.code_recurrence_promote",
        description=(
            "Write each match from code_recurrence_scan to "
            "auto-improvement.ndjson as a recurrence entry (default status "
            "s1-emergent). codification_radar picks these up on its next "
            "cluster pass to surface s2/s3 candidates when N≥3 pairs "
            "cluster on the same surface. Idempotent — skips pairs already "
            "in the ledger by target-string match. Closes the cross-product "
            "recurrence loop (code_embeddings → recurrence_promote → "
            "auto-improvement → codification_radar)."
        ),
    )
    def _promote(matches: list[dict], target_status: str = "s1-emergent",
                 source_ref: str | None = None, skip_existing: bool = True) -> dict:
        return promote(matches, target_status=target_status,
                       source_ref=source_ref, skip_existing=skip_existing)


__all__ = [
    "BAND_STRONG",
    "BAND_MEDIUM",
    "BAND_WEAK",
    "scan",
    "promote",
    "register",
]
