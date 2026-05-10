"""``noctus.seed.report`` — unified triage queue cross-referencing
``scan_repetition`` (cross-product duplication) and ``audit_drift``
(product ↔ template divergence).

Highest-leverage absorption opportunities sit where BOTH scans agree:
a file duplicated byte-identical across N≥3 products AND tracked in
``templates/product-seed/`` — one absorption move closes the duplication
AND lets the template push forward to the absorbed shape so future
scaffolds inherit it.

Lowest-leverage entries (`divergent` scan results, `large_drift`
template entries with no duplication) are still surfaced so an
architect can confirm intentional divergence and catalog with
``accept-with-rationale`` instead of leaving the finding silent.

Read-only; this tool composes the two upstream tools' outputs without
touching either implementation.

Priority bands:

- **P0** — byte_identical N≥3 AND template ships file AND ≥1 product
  drifts. One move resolves duplication + template convergence.
- **P1** — byte_identical N≥3, template-status irrelevant. Recurrence
  rule MUST formalize (`KB § PATTERNS/project-execution.md § 2.7`).
- **P2** — byte_identical N=2, recurrence rule triage time.
- **P3** — near_identical N≥2; reconcile drift, then absorb.
- **P4** — template ships file but ≥1 product is missing it; push the
  missing product to inherit.
- **P5** — divergent / large_drift; likely intentional, surface for
  review-and-catalog.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .audit_drift import audit_drift
from .scan_repetition import scan_repetition

logger = logging.getLogger(__name__)


_PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3", "P4", "P5")


def _drift_status_map(file_entry: dict) -> dict[str, str]:
    """Flatten an audit_drift `files[i]` entry to ``{slug: status}``."""
    return {p["slug"]: p["status"] for p in file_entry.get("products", [])}


def _classify_item(
    *,
    rel_path: str,
    scan_group: dict | None,
    drift_entry: dict | None,
    suggested_destination: str | None,
) -> dict:
    """Decide priority + rationale + suggested action for one (file) row.

    Either ``scan_group`` or ``drift_entry`` may be None — the rollup
    surfaces files that appear in either scan, even if not both.
    """
    in_template = drift_entry is not None
    drift_status_per_product = _drift_status_map(drift_entry) if drift_entry else {}
    has_drift = any(
        s in {"small_drift", "large_drift"} for s in drift_status_per_product.values()
    )
    has_missing = any(s == "missing" for s in drift_status_per_product.values())
    has_large_drift = any(s == "large_drift" for s in drift_status_per_product.values())

    if scan_group is not None:
        classification = scan_group["classification"]
        occurrences = scan_group["occurrences"]
        products = scan_group["products"]

        if classification == "byte_identical" and occurrences >= 3:
            if in_template and has_drift:
                return {
                    "priority": "P0",
                    "rationale": (
                        f"byte_identical across {occurrences} products AND template ships it; "
                        f"≥1 product drifts. Absorb the file → re-export from products → "
                        "push template forward to match. One move, three wins."
                    ),
                    "suggested_action": "absorb_and_push_template",
                    "suggested_destination": suggested_destination,
                    "in_template": in_template,
                    "scan_classification": classification,
                    "scan_occurrences": occurrences,
                    "scan_products": products,
                    "drift_status_per_product": drift_status_per_product,
                }
            return {
                "priority": "P1",
                "rationale": (
                    f"byte_identical across {occurrences} products. Recurrence rule MUST "
                    "formalize (N≥3); absorb into seed."
                ),
                "suggested_action": "absorb_to_seed",
                "suggested_destination": suggested_destination,
                "in_template": in_template,
                "scan_classification": classification,
                "scan_occurrences": occurrences,
                "scan_products": products,
                "drift_status_per_product": drift_status_per_product,
            }
        if classification == "byte_identical" and occurrences == 2:
            return {
                "priority": "P2",
                "rationale": (
                    f"byte_identical across {occurrences} products. Recurrence rule triage "
                    "time — formalize / refactor / accept-with-rationale."
                ),
                "suggested_action": "triage",
                "suggested_destination": suggested_destination,
                "in_template": in_template,
                "scan_classification": classification,
                "scan_occurrences": occurrences,
                "scan_products": products,
                "drift_status_per_product": drift_status_per_product,
            }
        if classification == "near_identical":
            return {
                "priority": "P3",
                "rationale": (
                    f"near_identical (similarity={scan_group['similarity']}) across "
                    f"{occurrences} products. Reconcile per-product tweaks, THEN absorb."
                ),
                "suggested_action": "converge_then_absorb",
                "suggested_destination": suggested_destination,
                "in_template": in_template,
                "scan_classification": classification,
                "scan_occurrences": occurrences,
                "scan_products": products,
                "drift_status_per_product": drift_status_per_product,
            }
        # divergent
        return {
            "priority": "P5",
            "rationale": (
                f"divergent (similarity={scan_group['similarity']}) across "
                f"{occurrences} products. Likely intentional — review and catalog if so."
            ),
            "suggested_action": "review_intent",
            "suggested_destination": None,
            "in_template": in_template,
            "scan_classification": classification,
            "scan_occurrences": occurrences,
            "scan_products": products,
            "drift_status_per_product": drift_status_per_product,
        }

    # No scan_group → drift-only signal.
    if has_missing and not has_large_drift:
        return {
            "priority": "P4",
            "rationale": (
                "Template ships file; ≥1 product is missing it. Push the missing "
                "product to inherit."
            ),
            "suggested_action": "scaffold_missing",
            "suggested_destination": None,
            "in_template": True,
            "scan_classification": None,
            "scan_occurrences": None,
            "scan_products": None,
            "drift_status_per_product": drift_status_per_product,
        }
    if has_large_drift:
        return {
            "priority": "P5",
            "rationale": (
                "Template ships file; ≥1 product has large_drift (likely intentional "
                "divergence). Review and catalog if intentional."
            ),
            "suggested_action": "review_intent",
            "suggested_destination": None,
            "in_template": True,
            "scan_classification": None,
            "scan_occurrences": None,
            "scan_products": None,
            "drift_status_per_product": drift_status_per_product,
        }
    # Drift entry exists but every product is identical or only small_drift —
    # nothing actionable; skip.
    return {
        "priority": "_skip",
        "rationale": "",
        "suggested_action": "",
        "suggested_destination": None,
        "in_template": True,
        "scan_classification": None,
        "scan_occurrences": None,
        "scan_products": None,
        "drift_status_per_product": drift_status_per_product,
    }


def report(
    *,
    products_dir: Path | None = None,
    template_root: Path | None = None,
    near_identical_threshold: float = 0.95,
    drift_threshold_lines: int = 20,
    min_products: int = 2,
    mask_placeholders: bool = True,
    max_items: int | None = None,
) -> dict:
    """Cross-reference scan_repetition + audit_drift into a triage queue.

    Args:
        products_dir / template_root: Test seams; default to platform paths.
        near_identical_threshold: Forwarded to scan_repetition (0.95 default).
        drift_threshold_lines: Forwarded to audit_drift (20 default).
        min_products: Forwarded to scan_repetition (2 default; pass 3 to
            see only the recurrence-rule MUST-formalize cases).
        mask_placeholders: Forwarded to audit_drift (True default — apply
            scaffold's placeholder substitution before diffing).
        max_items: Optional cap on the returned items list. None = no cap.
            The summary counts always reflect the full pre-cap result.

    Returns:
        ``{
          "scanned_products": [slug, ...],
          "items": [
            {
              "priority": "P0"|"P1"|"P2"|"P3"|"P4"|"P5",
              "rel_path": str,
              "rationale": str,
              "suggested_action": str,
              "suggested_destination": str | None,
              "in_template": bool,
              "scan_classification": str | None,
              "scan_occurrences": int | None,
              "scan_products": [slug, ...] | None,
              "drift_status_per_product": {slug: status},
            },
            ...
          ],
          "summary": {
            "P0_count": int, ..., "P5_count": int,
            "total_items": int,                     # actionable items (P0-P5)
            "skipped_no_action": int,               # files audit_drift surfaced
                                                    # but no action applies
            "scan_total_groups": int,
            "audit_files_audited": int,
          },
          "upstream": {
            "scan_summary": {...},                  # scan_repetition summary
            "audit_summary": {...},                 # audit_drift summary
          },
        }``
    """
    scan_result = scan_repetition(
        products_dir=products_dir,
        near_identical_threshold=near_identical_threshold,
        min_products=min_products,
    )
    drift_result = audit_drift(
        template_root=template_root,
        products_dir=products_dir,
        drift_threshold_lines=drift_threshold_lines,
        mask_placeholders=mask_placeholders,
    )

    # If either upstream errored on root-not-found, surface the error.
    if "error" in scan_result:
        return {
            "scanned_products": [],
            "items": [],
            "summary": {f"{p}_count": 0 for p in _PRIORITIES} | {
                "total_items": 0,
                "skipped_no_action": 0,
                "scan_total_groups": 0,
                "audit_files_audited": 0,
            },
            "upstream": {
                "scan_summary": scan_result.get("summary", {}),
                "audit_summary": drift_result.get("summary", {}),
            },
            "error": scan_result["error"],
        }
    if "error" in drift_result:
        return {
            "scanned_products": scan_result.get("scanned_products", []),
            "items": [],
            "summary": {f"{p}_count": 0 for p in _PRIORITIES} | {
                "total_items": 0,
                "skipped_no_action": 0,
                "scan_total_groups": scan_result["summary"]["total_groups"],
                "audit_files_audited": 0,
            },
            "upstream": {
                "scan_summary": scan_result.get("summary", {}),
                "audit_summary": drift_result.get("summary", {}),
            },
            "error": drift_result["error"],
        }

    # Index drift report by rel_path for O(1) cross-reference.
    drift_by_path: dict[str, dict] = {
        f["rel_path"]: f for f in drift_result.get("files", [])
    }
    scan_groups_by_path: dict[str, dict] = {
        g["rel_path"]: g for g in scan_result.get("groups", [])
    }

    # Visit every rel_path that surfaced in either scan — union semantics.
    every_path: set[str] = set(drift_by_path) | set(scan_groups_by_path)

    items: list[dict] = []
    skipped_no_action = 0
    for rel_path in sorted(every_path):
        scan_group = scan_groups_by_path.get(rel_path)
        drift_entry = drift_by_path.get(rel_path)
        suggested_destination = (
            scan_group.get("suggested_destination") if scan_group else None
        )
        item = _classify_item(
            rel_path=rel_path,
            scan_group=scan_group,
            drift_entry=drift_entry,
            suggested_destination=suggested_destination,
        )
        if item["priority"] == "_skip":
            skipped_no_action += 1
            continue
        item["rel_path"] = rel_path
        items.append(item)

    # Order: priority asc (P0 first), then by occurrence count desc (more
    # leverage first), then by path for stable output.
    priority_order = {p: i for i, p in enumerate(_PRIORITIES)}
    items.sort(
        key=lambda it: (
            priority_order.get(it["priority"], 99),
            -(it.get("scan_occurrences") or 0),
            it["rel_path"],
        )
    )

    summary: dict = {f"{p}_count": 0 for p in _PRIORITIES}
    for item in items:
        summary[f"{item['priority']}_count"] += 1
    summary["total_items"] = len(items)
    summary["skipped_no_action"] = skipped_no_action
    summary["scan_total_groups"] = scan_result["summary"]["total_groups"]
    summary["audit_files_audited"] = drift_result["summary"]["files_audited"]

    if max_items is not None and max_items >= 0:
        items = items[:max_items]

    # Use the union of upstream scanned_products (audit_drift may include
    # products without duplication; scan_repetition skips them).
    scanned_products = sorted(
        set(scan_result.get("scanned_products", []))
        | set(drift_result.get("scanned_products", []))
    )

    return {
        "scanned_products": scanned_products,
        "items": items,
        "summary": summary,
        "upstream": {
            "scan_summary": scan_result["summary"],
            "audit_summary": drift_result["summary"],
        },
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.report",
        description=(
            "Unified triage queue: composes scan_repetition + audit_drift "
            "into one prioritized list. P0 (highest leverage) = byte_identical "
            "N≥3 AND template ships file AND ≥1 product drifts (one absorb "
            "move closes both gaps). P1 = byte_identical N≥3 alone "
            "(recurrence rule MUST formalize). P2 = N=2 triage. P3 = "
            "near_identical (converge first). P4 = template gap (≥1 product "
            "missing). P5 = divergent / large_drift (review intent). Read-only."
        ),
    )
    def _report(
        near_identical_threshold: float = 0.95,
        drift_threshold_lines: int = 20,
        min_products: int = 2,
        mask_placeholders: bool = True,
        max_items: int | None = None,
    ) -> dict:
        return report(
            near_identical_threshold=near_identical_threshold,
            drift_threshold_lines=drift_threshold_lines,
            min_products=min_products,
            mask_placeholders=mask_placeholders,
            max_items=max_items,
        )
