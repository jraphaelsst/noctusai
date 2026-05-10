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
import re
from pathlib import Path

from settings import PRODUCTS_DIR, REPO_ROOT

from ._filewalk import walk_files

logger = logging.getLogger(__name__)


_TEMPLATE_ROOT = REPO_ROOT / "templates" / "product-seed"


# Placeholder names that the scaffold tool's mechanical substitution writes.
# When auditing drift, we substitute these in the template using each
# product's actual metadata BEFORE diffing — so successful substitution
# doesn't show up as drift. Keep in sync with `scaffold_product`'s
# `replacements` dict.
_PLACEHOLDER_NAMES: tuple[str, ...] = (
    "PRODUCT_NAME",
    "PRODUCT_SLUG",
    "SCHEMA_NAME",
    "BACKEND_PORT",
    "FRONTEND_PORT",
    "PRODUCT_ICON",
)

_START_SH_PRODUCT_RE = re.compile(
    r'"(?P<slug>[a-z0-9][a-z0-9-]*):(?P<name>[^:]+):(?P<bp>\d+):(?P<fp>\d+)"'
)
_SEED_ROW_NAME_RE = re.compile(
    r"INSERT INTO public\.products[^;]*VALUES\s*\(\s*'([^']+)'",
    re.DOTALL | re.IGNORECASE,
)
_SEED_ROW_ICON_RE = re.compile(
    r"'([A-Z][A-Za-z0-9]+)'\s*,\s*'http",
)


def _read_product_metadata(products_dir: Path, slug: str) -> dict[str, str]:
    """Best-effort read of product metadata for placeholder substitution.

    Returns the dict the scaffold tool's mechanical pass uses. Falls back
    to slug-derived defaults when the source-of-truth files aren't present
    (so the function never raises and audit_drift can always proceed).

    Sources, in priority order:
    1. ``start.sh`` PRODUCTS array — display name + ports.
    2. ``products/core/backend/migrations/NNN_seed_<slug>_product.sql`` —
       display name (canonical) + icon.
    3. Slug-derived defaults — name = title-cased slug, ports = "0", icon = "Box".
    """
    metadata: dict[str, str] = {
        "PRODUCT_SLUG": slug,
        "SCHEMA_NAME": slug.replace("-", "_"),
        "PRODUCT_NAME": slug.replace("-", " ").title(),
        "BACKEND_PORT": "0",
        "FRONTEND_PORT": "0",
        "PRODUCT_ICON": "Box",
    }

    # start.sh registry — ports + display name
    start_sh = products_dir.parent / "start.sh"
    if start_sh.is_file():
        try:
            content = start_sh.read_text(encoding="utf-8")
        except OSError:
            content = ""
        for match in _START_SH_PRODUCT_RE.finditer(content):
            if match.group("slug") == slug:
                metadata["PRODUCT_NAME"] = match.group("name")
                metadata["BACKEND_PORT"] = match.group("bp")
                metadata["FRONTEND_PORT"] = match.group("fp")
                break

    # Seed-row migration — name (canonical) + icon
    core_migrations = products_dir / "core" / "backend" / "migrations"
    if core_migrations.is_dir():
        slug_for_filename = slug.replace("-", "_")
        for migration in core_migrations.glob(
            f"*_seed_{slug_for_filename}_product.sql"
        ):
            try:
                content = migration.read_text(encoding="utf-8")
            except OSError:
                continue
            name_match = _SEED_ROW_NAME_RE.search(content)
            if name_match:
                metadata["PRODUCT_NAME"] = name_match.group(1)
            icon_match = _SEED_ROW_ICON_RE.search(content)
            if icon_match:
                metadata["PRODUCT_ICON"] = icon_match.group(1)
            break

    return metadata


def _substitute_placeholders(template_text: str, metadata: dict[str, str]) -> str:
    """Apply the same mechanical substitution scaffold_product does, using
    the product's resolved metadata. Returns the substituted text — caller
    diffs THIS against the product file."""
    out = template_text
    for key in _PLACEHOLDER_NAMES:
        value = metadata.get(key, "")
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


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
    mask_placeholders: bool = True,
) -> dict:
    """Diff every product against the canonical template.

    Args:
        template_root: Override (test seam). Defaults to
            ``REPO_ROOT/templates/product-seed/``.
        products_dir: Override (test seam). Defaults to :data:`PRODUCTS_DIR`.
        drift_threshold_lines: Files with drift_lines ≤ this count are
            classified ``small_drift`` (good convergence candidates).
            Files above are ``large_drift`` (intentional divergence likely).
        mask_placeholders: When True (default), apply the scaffold tool's
            mechanical substitution to the template (using each product's
            resolved metadata) BEFORE diffing. So lines that ONLY differ in
            successful substitution don't surface as drift. Set False to
            see the raw template-vs-product diff (useful for debugging the
            substitution itself).

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

    # Pre-resolve each product's placeholder metadata once — read once,
    # used per-file. Cheap (a few file reads per product).
    product_metadata: dict[str, dict[str, str]] = {}
    if mask_placeholders:
        for slug in product_slugs:
            product_metadata[slug] = _read_product_metadata(base_products_dir, slug)

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

            # Substitute placeholders in the template using THIS product's
            # metadata before diffing — so successful mechanical
            # substitution doesn't show as drift. Small-drift findings now
            # reflect REAL per-product divergence, not boilerplate noise.
            template_for_diff = template_text
            if mask_placeholders:
                template_for_diff = _substitute_placeholders(
                    template_text, product_metadata.get(slug, {}),
                )
                # If substitution made the template byte-equal the product
                # file, it's effectively identical — early-out.
                if template_for_diff == product_text:
                    per_product.append({
                        "slug": slug, "status": "identical", "drift_lines": 0,
                    })
                    counts["identical_count"] += 1
                    continue

            drift = _diff_lines(template_for_diff, product_text)
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
            "large_drift / missing. By default, mechanical placeholders in "
            "the template ({{PRODUCT_NAME}}, {{PRODUCT_SLUG}}, etc.) are "
            "substituted with each product's resolved metadata BEFORE diffing "
            "— so successful substitution doesn't surface as drift. Pass "
            "mask_placeholders=False to see raw diffs (debugging the "
            "substitution itself)."
        ),
    )
    def _audit(
        drift_threshold_lines: int = 20,
        mask_placeholders: bool = True,
    ) -> dict:
        return audit_drift(
            drift_threshold_lines=drift_threshold_lines,
            mask_placeholders=mask_placeholders,
        )
