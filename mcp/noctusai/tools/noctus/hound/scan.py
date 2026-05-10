"""``noctus.hound.scan`` — run the absorption + fusion + optimization trio.

Single entry-point that runs all three code-hygiene scanners in one
call and aggregates their findings. The hound is the keeper-analog
for code hygiene: keeper = compliance/regulatory; hound = hygiene/
curatorial.

Output schema is intentionally union-shaped: each scope's full result
is preserved verbatim under ``scopes.<name>``, plus a top-level
``unified`` summary that aggregates counts + opportunity surface
estimates across all three. Callers can walk the unified summary for
the dispatch decision, then drill into the per-scope detail.

Per-scope scanners pre-existed:

  - **absorption** — ``noctus.seed.report`` (cross-product, file-level)
  - **fusion**     — ``noctus.seed.scan_fusions`` (cross-tool, function-level)
  - **optimization** — ``noctus.seed.scan_optimizations`` (intra-file, line-level)

Read-only; this tool composes them without modifying anything.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_VALID_SCOPES: frozenset[str] = frozenset({
    "absorption", "fusion", "optimization",
})


def _absorption_summary(payload: dict) -> dict:
    """Squeeze ``noctus.seed.report`` output to the hound-level digest."""
    s = payload.get("summary", {})
    items = payload.get("items", [])
    p0_count = s.get("P0_count", 0)
    p1_count = s.get("P1_count", 0)
    p2_count = s.get("P2_count", 0)
    high_priority = p0_count + p1_count
    return {
        "candidates": s.get("total_items", len(items)),
        "high_priority_count": high_priority,  # P0+P1 → MUST formalize
        "files_absorbable_estimate": high_priority,
        "P0_count": p0_count,
        "P1_count": p1_count,
        "P2_count": p2_count,
        "P3_count": s.get("P3_count", 0),
        "P4_count": s.get("P4_count", 0),
        "P5_count": s.get("P5_count", 0),
    }


def _fusion_summary(payload: dict) -> dict:
    """Squeeze ``noctus.seed.scan_fusions`` output to the hound-level digest."""
    s = payload.get("summary", {})
    return {
        "candidates": s.get("pairs_above_threshold", 0),
        "subsume_count": s.get("subsume_candidates_count", 0),
        "compose_count": s.get("compose_candidates_count", 0),
        "estimated_savings_loc": s.get("estimated_savings_loc_total", 0),
        "scope": s.get("scope", "cross_file"),
    }


def _optimization_summary(payload: dict) -> dict:
    """Squeeze ``noctus.seed.scan_optimizations`` output to the digest."""
    s = payload.get("summary", {})
    by_severity = s.get("by_severity", {})
    return {
        "candidates": s.get("total_findings", 0),
        "high_count": by_severity.get("high", 0),
        "warning_count": by_severity.get("warning", 0),
        "info_count": by_severity.get("info", 0),
        "estimated_savings_loc": s.get("estimated_savings_loc_total", 0),
        "by_detector": s.get("by_detector", {}),
    }


def _next_action(unified: dict) -> str:
    """Pick the highest-leverage scope to attack first.

    Heuristic priority (in order):
      1. Absorption P0 candidates exist → cross-product duplication
         drifts; one absorb closes both the duplication and the template
         gap. Highest leverage per move.
      2. Optimization high-severity findings exist → confirmed dead
         code; safe to delete.
      3. Absorption P1 candidates exist → recurrence rule MUST formalize.
      4. Fusion subsume candidates with N≥3 cluster size exist → tool
         surface reduction.
      5. Optimization warning-severity findings exist → small inlines
         and wrapper unwraps.
      6. Otherwise — codebase clean enough that no single scope
         dominates; ad-hoc curation.
    """
    abs_s = unified.get("absorption", {})
    fus_s = unified.get("fusion", {})
    opt_s = unified.get("optimization", {})

    if abs_s.get("P0_count", 0) > 0:
        return (
            f"absorption: {abs_s['P0_count']} P0 candidates "
            "(byte_identical N≥3 + template drift). One absorb closes "
            "both gaps — start with `noctus.seed.report` to see the queue."
        )
    if opt_s.get("high_count", 0) > 0:
        return (
            f"optimization: {opt_s['high_count']} high-severity findings "
            "(confirmed dead code). Run `noctus.seed.scan_optimizations"
            "(min_severity='high')` and delete after grep verification."
        )
    if abs_s.get("P1_count", 0) > 0:
        return (
            f"absorption: {abs_s['P1_count']} P1 candidates "
            "(byte_identical N≥3, recurrence rule MUST formalize). Run "
            "`noctus.seed.report` and absorb top-of-queue."
        )
    if fus_s.get("subsume_count", 0) > 0:
        return (
            f"fusion: {fus_s['subsume_count']} subsume candidates "
            "(same-file or strong-overlap pairs). Run `noctus.seed."
            "scan_fusions(scope='same_file')` to see candidates."
        )
    if opt_s.get("warning_count", 0) > 0:
        return (
            f"optimization: {opt_s['warning_count']} warning-severity "
            "findings (small single-call helpers + wrappers). Run "
            "`noctus.seed.scan_optimizations(min_severity='warning')`."
        )
    return (
        "codebase clean enough that no single scope dominates. Ad-hoc "
        "curation (review individual files when touched)."
    )


def scan(
    *,
    scopes: list[str] | None = None,
    absorption_min_products: int = 2,
    fusion_min_score: float = 0.40,
    fusion_scope: str = "cross_file",
    optimization_min_severity: str = "warning",
    max_per_scope: int = 30,
) -> dict:
    """Run the absorption + fusion + optimization trio + emit unified report.

    Args:
        scopes: Optional whitelist (subset of ``["absorption", "fusion",
            "optimization"]``). None = run all three.
        absorption_min_products: Forwarded to ``noctus.seed.report``.
        fusion_min_score: Forwarded to ``noctus.seed.scan_fusions``.
        fusion_scope: Forwarded to ``noctus.seed.scan_fusions`` (one of
            ``"cross_file"`` / ``"same_file"`` / ``"all"``).
        optimization_min_severity: Forwarded to
            ``noctus.seed.scan_optimizations``.
        max_per_scope: Cap on items returned per scope inside ``scopes.<name>``.

    Returns:
        ``{
          "scopes_run": [name, ...],
          "scopes": {
            "absorption":   {<noctus.seed.report output, capped>},
            "fusion":       {<noctus.seed.scan_fusions output, capped>},
            "optimization": {<noctus.seed.scan_optimizations output, capped>},
          },
          "unified": {
            "absorption":   {<digest>},
            "fusion":       {<digest>},
            "optimization": {<digest>},
            "total_candidates": int,
            "total_loc_savings_estimate": int,
            "files_absorbable_estimate": int,
          },
          "next_action": str,             # plain-text dispatch recommendation
          "errors": [str, ...],           # per-scope errors (soft-fail)
        }``
    """
    requested = list(scopes) if scopes else list(_VALID_SCOPES)
    unknown = [s for s in requested if s not in _VALID_SCOPES]
    if unknown:
        return {
            "scopes_run": [],
            "scopes": {},
            "unified": {},
            "next_action": "",
            "errors": [f"unknown scope(s): {unknown}. Valid: {sorted(_VALID_SCOPES)}"],
        }

    scopes_out: dict[str, dict] = {}
    unified: dict[str, Any] = {}
    errors: list[str] = []

    if "absorption" in requested:
        try:
            from ..seed.report import report
            payload = report(
                min_products=absorption_min_products,
                max_items=max_per_scope,
            )
            scopes_out["absorption"] = payload
            unified["absorption"] = _absorption_summary(payload)
        except Exception as exc:  # noqa: BLE001 — soft-fail per scope
            errors.append(f"absorption: {type(exc).__name__}: {exc}")

    if "fusion" in requested:
        try:
            from ..seed.scan_fusions import scan_fusions
            payload = scan_fusions(
                min_score=fusion_min_score,
                max_pairs=max_per_scope,
                scope=fusion_scope,
            )
            scopes_out["fusion"] = payload
            unified["fusion"] = _fusion_summary(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fusion: {type(exc).__name__}: {exc}")

    if "optimization" in requested:
        try:
            from ..seed.scan_optimizations import scan_optimizations
            payload = scan_optimizations(
                min_severity=optimization_min_severity,
                max_findings=max_per_scope,
            )
            scopes_out["optimization"] = payload
            unified["optimization"] = _optimization_summary(payload)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"optimization: {type(exc).__name__}: {exc}")

    # Aggregate cross-scope numbers for the dispatch decision + reporting.
    total_candidates = sum(
        unified.get(s, {}).get("candidates", 0) for s in requested
    )
    total_loc_savings = sum(
        unified.get(s, {}).get("estimated_savings_loc", 0)
        for s in requested
    )
    files_absorbable = unified.get("absorption", {}).get(
        "files_absorbable_estimate", 0
    )
    unified.update({
        "total_candidates": total_candidates,
        "total_loc_savings_estimate": total_loc_savings,
        "files_absorbable_estimate": files_absorbable,
    })

    return {
        "scopes_run": [s for s in requested if s in scopes_out],
        "scopes": scopes_out,
        "unified": unified,
        "next_action": _next_action(unified),
        "errors": errors,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.hound.scan",
        description=(
            "Run the absorption + fusion + optimization trio + emit a "
            "unified prioritized triage queue. Per-scope detail under "
            "scopes.<name>; aggregated counts + LoC-savings estimate + "
            "files-absorbable estimate under unified; plain-text "
            "next_action picks the highest-leverage scope to attack "
            "first. Read-only."
        ),
    )
    def _scan(
        scopes: list[str] | None = None,
        absorption_min_products: int = 2,
        fusion_min_score: float = 0.40,
        fusion_scope: str = "cross_file",
        optimization_min_severity: str = "warning",
        max_per_scope: int = 30,
    ) -> dict:
        return scan(
            scopes=scopes,
            absorption_min_products=absorption_min_products,
            fusion_min_score=fusion_min_score,
            fusion_scope=fusion_scope,
            optimization_min_severity=optimization_min_severity,
            max_per_scope=max_per_scope,
        )
