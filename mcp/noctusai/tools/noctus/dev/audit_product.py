"""``noctus.dev.audit_product`` — phase-close per-product readiness gate.

Composite read-only audit across every per-slug check the toolkit ships:

- ``validate_one_product`` — seed-compliance keeper detectors.
- ``diff_product_against_seed`` — structural drift vs canonical seed.
- ``find_orphaned_files`` — unimported / dead files.
- ``check_api_consistency`` — endpoint pattern conformance.
- ``check_master_prompt_staleness`` — MASTER-PROMPT.md vs filesystem.

One call gives a phase-close gate decision: pass if all slices clean,
otherwise the per-slice findings tell you where to look. Eliminates the
4-call dance the agent currently does at phase-end.

Surfaced as fusion candidate by ``noctus.seed.scan_fusions`` (multiple
pairs above 0.50 — all components take ``slug`` and share product /
seed / check vocabulary).

Read-only — pure composition over upstream tools; no aggregation
beyond bundling per-slice outputs and summarizing pass/fail.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _summarize_slice(name: str, payload: Any) -> tuple[bool, str]:
    """Heuristic per-slice pass/fail. Tilts strict — any error or
    non-empty issues list flips the slice to fail. Each upstream tool
    has a slightly different shape; this is the union heuristic.

    Returns (passed: bool, reason: str).
    """
    if not isinstance(payload, dict):
        return False, f"{name}: unexpected return type {type(payload).__name__}"
    if "error" in payload and payload["error"]:
        return False, f"{name}: {payload['error']}"
    # Slice-specific keys — any non-empty failure surface flips to fail.
    issues = payload.get("issues") or []
    if isinstance(issues, list) and issues:
        return False, f"{name}: {len(issues)} issue(s)"
    if payload.get("stale") is True:
        return False, f"{name}: stale"
    failures = payload.get("failures") or []
    if isinstance(failures, list) and failures:
        return False, f"{name}: {len(failures)} failure(s)"
    drifted = payload.get("drifted") or []
    if isinstance(drifted, list) and drifted:
        return False, f"{name}: {len(drifted)} drifted file(s)"
    orphans = payload.get("orphans") or []
    if isinstance(orphans, list) and orphans:
        return False, f"{name}: {len(orphans)} orphan(s)"
    return True, f"{name}: OK"


def audit_product(
    slug: str,
    *,
    include: list[str] | None = None,
) -> dict[str, Any]:
    """Run every per-slug audit and return a unified report.

    Args:
        slug: Product slug to audit.
        include: Optional whitelist of slice names to run (subset of
            ``["validate", "diff_against_seed", "find_orphans",
            "check_api_consistency", "check_master_prompt"]``).
            None = run all.

    Returns:
        ``{
          "slug": str,
          "passed": bool,                  # all slices passed
          "summary": [str, ...],           # one line per slice
          "slices": {
            "validate": {...},
            "diff_against_seed": {...},
            "find_orphans": {...},
            "check_api_consistency": {...},
            "check_master_prompt": {...},
          },
          "errors": [str, ...],            # slices that raised; soft-fail
        }``
    """
    all_slices = (
        "validate", "diff_against_seed", "find_orphans",
        "check_api_consistency", "check_master_prompt",
    )
    requested = list(include) if include else list(all_slices)
    unknown = [s for s in requested if s not in all_slices]
    if unknown:
        return {
            "slug": slug,
            "passed": False,
            "summary": [],
            "slices": {},
            "errors": [
                f"unknown slice(s): {unknown}. Valid: {sorted(all_slices)}"
            ],
        }

    slices: dict[str, Any] = {}
    summary: list[str] = []
    errors: list[str] = []
    all_passed = True

    if "validate" in requested:
        try:
            from .compliance import validate_one_product
            slices["validate"] = validate_one_product(slug)
        except Exception as exc:  # noqa: BLE001 — soft-fail
            errors.append(f"validate: {type(exc).__name__}: {exc}")
            slices["validate"] = {"error": str(exc)}

    if "diff_against_seed" in requested:
        try:
            from .diff import diff_product_against_seed
            slices["diff_against_seed"] = diff_product_against_seed(slug)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"diff_against_seed: {type(exc).__name__}: {exc}")
            slices["diff_against_seed"] = {"error": str(exc)}

    if "find_orphans" in requested:
        try:
            from .diff import find_orphaned_files
            slices["find_orphans"] = find_orphaned_files(slug)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"find_orphans: {type(exc).__name__}: {exc}")
            slices["find_orphans"] = {"error": str(exc)}

    if "check_api_consistency" in requested:
        try:
            from .diff import check_api_consistency
            slices["check_api_consistency"] = check_api_consistency(slug)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"check_api_consistency: {type(exc).__name__}: {exc}")
            slices["check_api_consistency"] = {"error": str(exc)}

    if "check_master_prompt" in requested:
        try:
            from .master_prompts import check_master_prompt_staleness
            slices["check_master_prompt"] = check_master_prompt_staleness(slug)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"check_master_prompt: {type(exc).__name__}: {exc}")
            slices["check_master_prompt"] = {"error": str(exc)}

    for name in requested:
        if name in slices:
            passed, reason = _summarize_slice(name, slices[name])
            summary.append(reason)
            if not passed:
                all_passed = False

    return {
        "slug": slug,
        "passed": all_passed and not errors,
        "summary": summary,
        "slices": slices,
        "errors": errors,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.audit_product",
        description=(
            "Phase-close per-product readiness gate: composes "
            "validate_product + diff_against_seed + find_orphans + "
            "check_api_consistency + check_master_prompt into one "
            "report. `passed=True` means every slice clean. Pass "
            "`include=[...]` to run a subset. Read-only; soft-fails "
            "per slice (errors[] populated, other slices still run)."
        ),
    )
    def _audit_product(slug: str, include: list[str] | None = None) -> dict:
        return audit_product(slug, include=include)
