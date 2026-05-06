"""``noctus.seed.audit_drift`` — diff product files against the canonical
``templates/product-seed/`` shape.

For each file in ``templates/product-seed/`` (the source of every newly
scaffolded product), find the corresponding file in each product and
compute drift via line-level diff. Reports:

- **identical** — same bytes as the template canonical.
- **drifted** — content differs; reports diff_lines (count of changed lines
  per a unified-diff body).
- **missing** — file present in the template but absent from the product.

Read-only; surfaces convergence opportunities (small drift = good
candidate for re-syncing to canonical) and intentional divergence (large
drift = product genuinely customized; absorption may not apply).
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path

from settings import PRODUCTS_DIR, REPO_ROOT

from ._filewalk import walk_files

logger = logging.getLogger(__name__)


_TEMPLATE_ROOT = REPO_ROOT / "templates" / "product-seed"


def _read_text_or_bytes_marker(path: Path) -> tuple[str | None, bool]:
    """Try to read as utf-8 text. Returns (text, is_binary).
    is_binary=True when decode fails — caller can still byte-compare."""
    try:
        return path.read_text(encoding="utf-8"), False
    except (UnicodeDecodeError, OSError):
        return None, True


def _diff_lines(template_text: str, product_text: str) -> int:
    """Count of changed lines between two texts via unified diff."""
    if template_text == product_text:
        return 0
    diff = list(
        difflib.unified_diff(
            template_text.splitlines(),
            product_text.splitlines(),
            lineterm="",
            n=0,  # No context lines — count only +/- markers
        )
    )
    # Skip the header lines (--- / +++) and hunk headers (@@); count +/-.
    return sum(
        1 for line in diff
        if line and line[0] in "+-" and not line.startswith(("+++", "---"))
    )


def audit_drift(
    *,
    template_root: Path | None = None,
    products_dir: Path | None = None,
    drift_threshold_lines: int = 20,
) -> dict:
    """Diff every product against the canonical template.

    Args:
        template_root: Override (test seam). Defaults to
            ``REPO_ROOT/templates/product-seed/``.
        products_dir: Override (test seam). Defaults to :data:`PRODUCTS_DIR`.
        drift_threshold_lines: Files with drift_lines ≤ this count are
            classified ``small_drift`` (good convergence candidates).
            Files above are ``large_drift`` (intentional divergence likely).

    Returns:
        ``{
          "scanned_products": [slug, ...],
          "files": [
            {
              "rel_path": str,                    # relative to product root
              "products": [
                {
                  "slug": str,
                  "status": "identical" | "small_drift" | "large_drift" | "missing",
                  "drift_lines": int,             # 0 if identical, -1 if missing
                },
                ...
              ],
            },
            ...
          ],
          "summary": {
            "files_audited": int,
            "identical_count": int,    # total (file, product) pairs identical
            "small_drift_count": int,
            "large_drift_count": int,
            "missing_count": int,
          },
        }``
    """
    base_template_root = template_root if template_root is not None else _TEMPLATE_ROOT
    base_products_dir = products_dir if products_dir is not None else PRODUCTS_DIR

    if not base_template_root.is_dir():
        return {
            "scanned_products": [],
            "files": [],
            "summary": {"files_audited": 0, "identical_count": 0, "small_drift_count": 0, "large_drift_count": 0, "missing_count": 0},
            "error": f"template_root not found: {base_template_root}",
        }
    if not base_products_dir.is_dir():
        return {
            "scanned_products": [],
            "files": [],
            "summary": {"files_audited": 0, "identical_count": 0, "small_drift_count": 0, "large_drift_count": 0, "missing_count": 0},
            "error": f"products_dir not found: {base_products_dir}",
        }

    product_slugs: list[str] = sorted(
        p.name for p in base_products_dir.iterdir() if p.is_dir()
    )

    files_report: list[dict] = []
    counts = {"identical_count": 0, "small_drift_count": 0, "large_drift_count": 0, "missing_count": 0}

    for template_file in sorted(walk_files(base_template_root)):
        rel_path = template_file.relative_to(base_template_root).as_posix()
        template_text, template_is_binary = _read_text_or_bytes_marker(template_file)
        try:
            template_bytes = template_file.read_bytes()
        except OSError:
            continue

        per_product: list[dict] = []
        for slug in product_slugs:
            product_file = base_products_dir / slug / rel_path
            if not product_file.is_file():
                per_product.append({
                    "slug": slug,
                    "status": "missing",
                    "drift_lines": -1,
                })
                counts["missing_count"] += 1
                continue

            try:
                product_bytes = product_file.read_bytes()
            except OSError:
                per_product.append({
                    "slug": slug,
                    "status": "missing",
                    "drift_lines": -1,
                })
                counts["missing_count"] += 1
                continue

            if product_bytes == template_bytes:
                per_product.append({"slug": slug, "status": "identical", "drift_lines": 0})
                counts["identical_count"] += 1
                continue

            # Different bytes; compute line-level drift if both are text.
            product_text, product_is_binary = _read_text_or_bytes_marker(product_file)
            if template_is_binary or product_is_binary or template_text is None or product_text is None:
                # Binary or unreadable — count as large_drift since we can't
                # meaningfully diff.
                per_product.append({"slug": slug, "status": "large_drift", "drift_lines": -1})
                counts["large_drift_count"] += 1
                continue

            drift = _diff_lines(template_text, product_text)
            status = "small_drift" if drift <= drift_threshold_lines else "large_drift"
            per_product.append({"slug": slug, "status": status, "drift_lines": drift})
            counts[f"{status}_count"] += 1

        files_report.append({"rel_path": rel_path, "products": per_product})

    return {
        "scanned_products": product_slugs,
        "files": files_report,
        "summary": {
            "files_audited": len(files_report),
            **counts,
        },
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.audit_drift",
        description=(
            "Diff every product against the canonical templates/product-seed/ "
            "shape. For each (file, product) pair: identical / small_drift / "
            "large_drift / missing. Surfaces convergence candidates "
            "(small drift = re-sync opportunity) vs intentional divergence "
            "(large drift = product genuinely customized)."
        ),
    )
    def _audit(drift_threshold_lines: int = 20) -> dict:
        return audit_drift(drift_threshold_lines=drift_threshold_lines)
