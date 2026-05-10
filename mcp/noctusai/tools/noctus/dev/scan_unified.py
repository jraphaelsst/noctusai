"""``noctus.dev.scan_unified`` — absorption-search sextet rollup.

CLAUDE.md `KB § 06-AGENTS.md § Absorption-search sextet` says:

> Run **all relevant modes from the sextet**, notably
> `scan_cross_product_helpers` + `scan_within_product_helpers`
> (catches N≥3 within one product) + `scan_service_line_recurrence`
> + `scan_block_patterns`. Use BEFORE writing a new helper/DTO/service
> shell; use AFTER a cleanup pass as the calibration check.

This rollup composes all 8 absorption scanners (sextet + 2 newer
additions) into a single call:

- ``scan_recurrence`` — verbatim line repetition in main.py / conftest.py / vitest.config.ts.
- ``scan_cross_product_helpers`` — function/class NAMES recurring across products.
- ``scan_within_product_helpers`` — helper duplication INSIDE one product (N≥3).
- ``scan_service_line_recurrence`` — verbatim lines in service / router files.
- ``scan_block_patterns`` — try/except + handler shapes via AST normalization.
- ``scan_pydantic_model_shapes`` — recurring Pydantic field-sets.
- ``scan_test_fixture_recurrence`` — pytest fixtures + test helpers.
- ``scan_migration_patterns`` — RLS / FK / trigger pattern recurrence.

Each scanner's findings carry a ``severity`` (high / warning / info,
keyed off N≥3 → MUST formalize vs N=2 → triage). The unified queue
sorts by severity desc, then by per-finding occurrence count desc, so
the highest-leverage absorption candidates surface first.

Read-only; pure composition. Each scanner stays the source of truth
for its slice; the rollup adds source-tagging + cross-scanner ranking.

Surfaced as fusion candidate by ``noctus.seed.scan_fusions`` (8 pairs
above 0.50 from this cluster — strongest cluster in the live tree).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# Scanner registry — name → (impl callable, default kwargs).
# Order matters for stable output when severity ties: earlier scanners
# rank first.
def _build_registry() -> dict[str, tuple[Callable, dict]]:
    from .recurrence import (
        scan_block_patterns,
        scan_cross_product_helpers,
        scan_migration_patterns,
        scan_pydantic_model_shapes,
        scan_recurrence,
        scan_service_line_recurrence,
        scan_test_fixture_recurrence,
        scan_within_product_helpers,
    )
    return {
        "recurrence": (scan_recurrence, {}),
        "cross_product_helpers": (scan_cross_product_helpers, {}),
        "within_product_helpers": (scan_within_product_helpers, {}),
        "service_line_recurrence": (scan_service_line_recurrence, {}),
        "block_patterns": (scan_block_patterns, {}),
        "pydantic_model_shapes": (scan_pydantic_model_shapes, {}),
        "test_fixture_recurrence": (scan_test_fixture_recurrence, {}),
        "migration_patterns": (scan_migration_patterns, {}),
    }


_SEVERITY_ORDER: dict[str, int] = {
    "high": 0,        # N≥3 → MUST formalize
    "warning": 1,     # N=2 → triage
    "medium": 1,      # alias used by some scanners
    "info": 2,        # observational
    "low": 3,
}


def _occurrence_count(finding: dict) -> int:
    """Best-effort occurrence count from heterogeneous finding shapes."""
    for key in (
        "count", "occurrence_count", "total_occurrences", "product_count",
        "file_count",
    ):
        val = finding.get(key)
        if isinstance(val, int):
            return val
    occurrences = finding.get("occurrences")
    if isinstance(occurrences, list):
        return len(occurrences)
    return 0


def _label(finding: dict) -> str:
    """Best-effort short label for a finding (used in unified output)."""
    for key in (
        "helper_name", "pattern_name", "signature", "line_text",
    ):
        val = finding.get(key)
        if isinstance(val, str) and val:
            # Truncate long line_text for readability.
            return val if len(val) <= 80 else val[:77] + "..."
    return "<unlabeled>"


def scan_unified(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
    include: list[str] | None = None,
    max_findings: int | None = None,
) -> dict[str, Any]:
    """Run every absorption scanner, return unified ranked findings.

    Args:
        repo_root: Override repo root (test seam).
        min_count: Forwarded to scanners that accept it (default 2,
            recurrence rule's triage threshold).
        must_formalize_threshold: Forwarded (default 3).
        include: Optional whitelist of scanner names to run. Subset of
            ``["recurrence", "cross_product_helpers",
            "within_product_helpers", "service_line_recurrence",
            "block_patterns", "pydantic_model_shapes",
            "test_fixture_recurrence", "migration_patterns"]``.
            None = run all 8.
        max_findings: Optional cap on the unified findings list. None
            = no cap. Summary always reflects pre-cap counts.

    Returns:
        ``{
          "scanners_run": [name, ...],
          "findings": [           # unified, sorted by severity + occ desc
            {
              "scanner": str,           # which scanner surfaced this
              "label": str,             # short identifier (helper_name / pattern_name / etc.)
              "severity": str,          # "high" | "warning" | "info" | ...
              "occurrence_count": int,  # best-effort N-count
              "raw": {...},             # the scanner's original finding dict
            },
            ...
          ],
          "per_scanner": {           # un-merged per-scanner outputs
            "recurrence": {...},
            "cross_product_helpers": {...},
            ...
          },
          "summary": {
            "total_findings": int,
            "high_count": int,
            "warning_count": int,
            "info_count": int,
            "by_scanner": {scanner: count},
          },
          "errors": [str, ...],      # soft errors per scanner
        }``
    """
    registry = _build_registry()
    requested = include if include else list(registry.keys())
    unknown = [s for s in requested if s not in registry]
    if unknown:
        return {
            "scanners_run": [],
            "findings": [],
            "per_scanner": {},
            "summary": {
                "total_findings": 0,
                "high_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "by_scanner": {},
            },
            "errors": [
                f"unknown scanner(s): {unknown}. Valid: {sorted(registry.keys())}"
            ],
        }

    per_scanner: dict[str, dict] = {}
    unified: list[dict] = []
    errors: list[str] = []
    by_scanner_count: dict[str, int] = {}
    severity_counts = {"high_count": 0, "warning_count": 0, "info_count": 0}

    for scanner_name in requested:
        impl, defaults = registry[scanner_name]
        kwargs: dict[str, Any] = dict(defaults)
        # Forward common kwargs only when the scanner accepts them.
        # Cheap approach: pass and catch TypeError for any scanner whose
        # signature doesn't include the kwarg. (within_product_helpers,
        # for example, doesn't accept must_formalize_threshold.)
        for k, v in (
            ("min_count", min_count),
            ("must_formalize_threshold", must_formalize_threshold),
        ):
            kwargs.setdefault(k, v)
        try:
            payload = impl(repo_root=repo_root, **kwargs)
        except TypeError:
            # Re-try without the optional kwarg this scanner doesn't accept.
            kwargs.pop("must_formalize_threshold", None)
            try:
                payload = impl(repo_root=repo_root, **kwargs)
            except Exception as exc:  # noqa: BLE001 — soft-fail
                errors.append(f"{scanner_name}: {type(exc).__name__}: {exc}")
                continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{scanner_name}: {type(exc).__name__}: {exc}")
            continue

        per_scanner[scanner_name] = payload
        findings = payload.get("findings") if isinstance(payload, dict) else None
        if not isinstance(findings, list):
            continue

        by_scanner_count[scanner_name] = len(findings)
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            severity = finding.get("severity") or "info"
            unified.append({
                "scanner": scanner_name,
                "label": _label(finding),
                "severity": severity,
                "occurrence_count": _occurrence_count(finding),
                "raw": finding,
            })
            sev_key = f"{severity}_count"
            if sev_key in severity_counts:
                severity_counts[sev_key] += 1

    # Stable sort: severity asc (high first), then occurrence count desc,
    # then scanner registration order (built into the dict iteration order).
    scanner_order = {name: i for i, name in enumerate(registry.keys())}
    unified.sort(
        key=lambda f: (
            _SEVERITY_ORDER.get(f["severity"], 99),
            -f["occurrence_count"],
            scanner_order.get(f["scanner"], 99),
            f["label"],
        )
    )

    summary = {
        "total_findings": len(unified),
        **severity_counts,
        "by_scanner": by_scanner_count,
    }

    if max_findings is not None and max_findings >= 0:
        unified = unified[:max_findings]

    return {
        "scanners_run": [s for s in requested if s in per_scanner],
        "findings": unified,
        "per_scanner": per_scanner,
        "summary": summary,
        "errors": errors,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_unified",
        description=(
            "Absorption-search sextet rollup: composes all 8 absorption "
            "scanners (recurrence, cross/within_product_helpers, "
            "service_line_recurrence, block_patterns, "
            "pydantic_model_shapes, test_fixture_recurrence, "
            "migration_patterns) into one prioritized findings list. "
            "Sorted high → warning → info, then occurrence count desc. "
            "Pass `include=[...]` to run a subset. Implements the "
            "'run all relevant modes' rule from CLAUDE.md `KB § "
            "06-AGENTS.md § Absorption-search sextet`."
        ),
    )
    def _scan_unified(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
        include: list[str] | None = None,
        max_findings: int | None = None,
    ) -> dict:
        return scan_unified(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
            include=include,
            max_findings=max_findings,
        )
