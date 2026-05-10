"""``noctus.seed.scan_repetition`` — find files duplicated across products.

For every file path that appears in N≥2 products at the same relative location
(e.g. ``frontend/nginx.conf`` in core / erp-imobiliario / personal-finance),
group the contents and classify:

- **byte_identical** — every product's copy hashes to the same value.
- **near_identical** — pairwise similarity ≥ ``near_identical_threshold``
  (default 0.95). Likely the same template with tiny per-product drift
  that should converge.
- **divergent** — similarity below the threshold. Either intentional or
  drift that's grown beyond reasonable convergence.

Read-only; surfaces candidates. The mutation companion (``absorb_file``)
will land later once we've inspected the scan output and seen real shapes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

from settings import PRODUCTS_DIR

from ._filewalk import walk_files

logger = logging.getLogger(__name__)


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _pairwise_similarity(texts: list[str]) -> float:
    """Mean pairwise SequenceMatcher ratio across all pairs in ``texts``.

    Returns 1.0 when all texts are identical (cheap shortcut). Returns 0.0
    on empty / single input. Computation is O(n^2) over the pair count;
    fine for the small N we see (10 products max).
    """
    if len(texts) < 2:
        return 0.0
    if len(set(texts)) == 1:
        return 1.0

    ratios: list[float] = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ratios.append(SequenceMatcher(None, texts[i], texts[j]).ratio())
    return sum(ratios) / len(ratios) if ratios else 0.0


def _suggest_destination(rel_path: str) -> str:
    """Heuristic: where in seed should this file live if absorbed?

    Pure suggestion — caller decides. Based on the relative path's first
    segment (``frontend/`` vs ``backend/``) and known shapes.
    """
    if rel_path.startswith("frontend/"):
        return f"seed/framework/frontend/{rel_path[len('frontend/'):]}"
    if rel_path.startswith("backend/"):
        return f"seed/framework/backend/{rel_path[len('backend/'):]}"
    return f"seed/framework/{rel_path}"


# Patterns that signal "this file is a shim pointing at seed" — covers
# TS/JS factory calls, CSS @imports, Python re-exports, all the shapes
# we've absorbed before. Treat ANY such reference in a small file as
# evidence that the file IS the absorbed state.
_SEED_REFERENCE_FRAGMENTS: tuple[str, ...] = (
    "/seed/",
    "@noctusai/seed",
    "noctusai_seed",
    "noctusai_lib",
)

_SHIM_MAX_OPERATIVE_LINES = 5


def _is_structural_duplicate(content: bytes) -> bool:
    """True when the content is structural rather than value-bearing —
    empty-marker files (Python __init__.py / .gitkeep) or already-absorbed
    re-export shims.

    - Empty / whitespace-only: Python package markers, ``.gitkeep``,
      empty configs.
    - Small (≤5 operative lines) AND references the seed framework:
      already-absorbed shim (factory call, re-export, ``@import``,
      Python ``from noctusai_seed import ...``).
    """
    if not content.strip():
        return True
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    operative_lines = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "//", "/*", "*"))
    ]
    if len(operative_lines) > _SHIM_MAX_OPERATIVE_LINES:
        return False
    return any(frag in text for frag in _SEED_REFERENCE_FRAGMENTS)


def scan_repetition(
    *,
    products_dir: Path | None = None,
    near_identical_threshold: float = 0.95,
    min_products: int = 2,
    skip_structural_duplicates: bool = True,
) -> dict:
    """Group files across products by relative path and classify duplicates.

    Args:
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to :data:`PRODUCTS_DIR` from settings.
        near_identical_threshold: Mean pairwise similarity at or above this
            ratio classifies a non-byte-identical group as "near_identical".
            Default 0.95 — small per-product tweaks but obviously the same
            template.
        min_products: Group size threshold. Default 2 (DRY recurrence rule's
            triage point). Pass 3 to focus on N≥3 cases that have hit the
            mandatory-formalize threshold.

    Returns:
        ``{
          "scanned_products": [slug, ...],
          "groups": [
            {
              "rel_path": str,            # e.g. "frontend/nginx.conf"
              "occurrences": N,
              "products": [slug, ...],
              "classification": "byte_identical" | "near_identical" | "divergent",
              "similarity": float,        # mean pairwise ratio (1.0 for byte_identical)
              "suggested_destination": str,
            },
            ...
          ],
          "summary": {
            "byte_identical_count": int,
            "near_identical_count": int,
            "divergent_count": int,
            "total_groups": int,
          },
        }``
    """
    base_products_dir = products_dir if products_dir is not None else PRODUCTS_DIR

    # path-relative-to-product → list of (slug, content_bytes_or_None)
    path_to_files: dict[str, list[tuple[str, bytes | None]]] = {}
    scanned_products: list[str] = []

    if not base_products_dir.is_dir():
        return {
            "scanned_products": [],
            "groups": [],
            "summary": {
                "byte_identical_count": 0,
                "near_identical_count": 0,
                "divergent_count": 0,
                "total_groups": 0,
            },
            "error": f"products_dir not found: {base_products_dir}",
        }

    for product_root in sorted(base_products_dir.iterdir()):
        if not product_root.is_dir():
            continue
        slug = product_root.name
        scanned_products.append(slug)
        for file_path in walk_files(product_root):
            rel = file_path.relative_to(product_root).as_posix()
            try:
                content = file_path.read_bytes()
            except OSError:
                content = None
            path_to_files.setdefault(rel, []).append((slug, content))

    groups: list[dict] = []
    skipped_structural = 0
    for rel_path, entries in sorted(path_to_files.items()):
        if len(entries) < min_products:
            continue

        readable = [(slug, content) for slug, content in entries if content is not None]
        if len(readable) < min_products:
            continue

        hashes = {_hash_bytes(c) for _, c in readable}
        if len(hashes) == 1:
            classification = "byte_identical"
            similarity = 1.0
            # Skip empty markers + already-absorbed re-export shims —
            # they surface as byte_identical but aren't real candidates.
            if skip_structural_duplicates and _is_structural_duplicate(readable[0][1]):
                skipped_structural += 1
                continue
        else:
            texts: list[str] = []
            for _, content in readable:
                try:
                    texts.append(content.decode("utf-8"))
                except UnicodeDecodeError:
                    texts = []
                    break
            if not texts:
                classification = "divergent"
                similarity = 0.0
            else:
                similarity = _pairwise_similarity(texts)
                classification = (
                    "near_identical" if similarity >= near_identical_threshold else "divergent"
                )

        groups.append({
            "rel_path": rel_path,
            "occurrences": len(readable),
            "products": [slug for slug, _ in readable],
            "classification": classification,
            "similarity": round(similarity, 4),
            "suggested_destination": _suggest_destination(rel_path),
        })

    # Sort groups: byte_identical first (highest absorption value), then by
    # occurrence count desc, then by path for stable output.
    classification_order = {"byte_identical": 0, "near_identical": 1, "divergent": 2}
    groups.sort(
        key=lambda g: (
            classification_order.get(g["classification"], 9),
            -g["occurrences"],
            g["rel_path"],
        )
    )

    summary = {
        "byte_identical_count": sum(1 for g in groups if g["classification"] == "byte_identical"),
        "near_identical_count": sum(1 for g in groups if g["classification"] == "near_identical"),
        "divergent_count": sum(1 for g in groups if g["classification"] == "divergent"),
        "total_groups": len(groups),
        "skipped_structural_duplicates": skipped_structural,
    }

    return {
        "scanned_products": scanned_products,
        "groups": groups,
        "summary": summary,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.scan_repetition",
        description=(
            "Find files duplicated across N≥2 products. Classifies as "
            "byte_identical / near_identical / divergent. By default skips "
            "structural duplicates — empty markers (Python __init__.py, "
            ".gitkeep) and already-absorbed re-export shims — since those "
            "surface as identical but aren't real candidates. Read-only."
        ),
    )
    def _scan(
        near_identical_threshold: float = 0.95,
        min_products: int = 2,
        skip_structural_duplicates: bool = True,
    ) -> dict:
        return scan_repetition(
            near_identical_threshold=near_identical_threshold,
            min_products=min_products,
            skip_structural_duplicates=skip_structural_duplicates,
        )
