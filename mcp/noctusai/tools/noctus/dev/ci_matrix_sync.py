"""`noctus.dev.refresh_ci_matrix_coverage` — keep `.github/workflows/test.yml`'s
per-product `matrix: product:` lists in sync with which products actually
QUALIFY (have real test files), not just which products exist on disk.

WHY (2026-08-13, found while building the dependabot-coverage gate — see
`dependabot_sync.py`). SAME class, a second live instance found by looking for
siblings per this doc's "generalise if the evidence supports it" rule:

  `product-backend-tests` matrix (pytest): 9 of 12 products. Missing `igig`
  (17 test files), `orbity` (31 test files), `seed` (6 test files) — every one
  a product with REAL, currently-uncollected backend tests. The job's own
  comment says "Matrixed over ALL 9 products with a backend suite" — true when
  written (2026-05-31), stale the moment 3 more products joined the fleet and
  nobody updated the array.

  `product-frontend-tests` matrix (vitest): 8 of 12. `orbity` has real vitest
  spec files (`src/hooks/__tests__/*.test.ts`) and is ALSO missing — same
  drift. `knowledge-extractor` / `igig` / `products/seed` are legitimately
  absent: `vitest run` hard-fails on "no test files found" (the job's own
  comment states the rule), and none of the three has a single `*.test.ts(x)`
  file yet — NOT drift, so the required-set predicate is "has ≥1 vitest spec
  file", never "exists on disk".

BOTH are silent: a CI job staying green tells you nothing about a product that
was never IN the matrix — the same "an unenforced/uncovered gate is silent
debt" shape the job's own header comments already name for other incidents.

Two required-set predicates, ONE mechanism (mirrors `dependabot_sync.py`'s
targeted-repair contract — never a full-file rewrite, every comment survives):
  `product-backend-tests`  → `products/<slug>/backend/tests/**/test_*.py` exists
  `product-frontend-tests` → `products/<slug>/frontend/src/**/*.test.ts(x)` exists

Depth: `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

#: Relative to repo root.
TEST_WORKFLOW_REL = Path(".github") / "workflows" / "test.yml"

_JOBS_KEY_RE = re.compile(r"^jobs:\s*$")
_JOB_START_RE = re.compile(r"^  ([a-zA-Z][a-zA-Z0-9_-]*):\s*$")
_MATRIX_PRODUCT_KEY_RE = re.compile(r"^        product:\s*$")
_MATRIX_ITEM_RE = re.compile(r"^          - ([a-z0-9][a-z0-9-]*)\s*$")


def _has_backend_tests(root: Path, slug: str) -> bool:
    tests_dir = root / "products" / slug / "backend" / "tests"
    return tests_dir.is_dir() and any(tests_dir.rglob("test_*.py"))


def _has_frontend_spec_files(root: Path, slug: str) -> bool:
    src_dir = root / "products" / slug / "frontend" / "src"
    if not src_dir.is_dir():
        return False
    return any(src_dir.rglob("*.test.ts")) or any(src_dir.rglob("*.test.tsx"))


#: `{job name: (required-slugs predicate, human label)}` — the surface
#: registry. Only these two jobs carry a per-product `matrix: product:` list
#: in `test.yml` today; a THIRD would just add a row here.
_JOB_PREDICATES: dict[str, callable] = {
    "product-backend-tests": _has_backend_tests,
    "product-frontend-tests": _has_frontend_spec_files,
}


@dataclass
class _MatrixList:
    job: str
    key_line: int  # index of the `        product:` line
    items_start: int  # index of the first `          - <slug>` line
    items_end: int  # exclusive — index of the first non-item line after the list
    slugs: list[str]


def _parse_matrix_lists(lines: list[str]) -> list[_MatrixList]:
    """Every `matrix: product:` list, scoped to job bodies (after `jobs:`) so
    a same-indent key elsewhere (`on: push:`, `permissions: contents:`) can
    never false-match as a job name."""
    jobs_idx = next((i for i, ln in enumerate(lines) if _JOBS_KEY_RE.match(ln)), None)
    if jobs_idx is None:
        return []

    job_starts = [
        (i, m.group(1))
        for i, ln in enumerate(lines)
        if i > jobs_idx and (m := _JOB_START_RE.match(ln))
    ]
    out: list[_MatrixList] = []
    for idx, (start, name) in enumerate(job_starts):
        end = job_starts[idx + 1][0] if idx + 1 < len(job_starts) else len(lines)
        if name not in _JOB_PREDICATES:
            continue
        key_line = next(
            (i for i in range(start, end) if _MATRIX_PRODUCT_KEY_RE.match(lines[i])), None
        )
        if key_line is None:
            continue
        slugs: list[str] = []
        i = key_line + 1
        while i < end and (m := _MATRIX_ITEM_RE.match(lines[i])):
            slugs.append(m.group(1))
            i += 1
        out.append(_MatrixList(job=name, key_line=key_line, items_start=key_line + 1, items_end=i, slugs=slugs))
    return out


def _on_disk_products(root: Path) -> list[str]:
    products = root / "products"
    if not products.exists():
        return []
    return [d.name for d in products.iterdir() if d.is_dir() and not d.name.startswith(".")]


def sync_ci_matrix_coverage(root: Path | None = None, write: bool = True) -> dict:
    """Repair `.github/workflows/test.yml`'s per-product matrices. Returns
    `{ok, status, path, changed, added, stale}`; `status` is
    `written` | `in-sync` | `would-write` | `error`. `added` / `stale` map
    `{job: [slugs]}`. Stale entries are reported, never removed — CI already
    fails loudly on them (unlike the dependabot silent-gap class), so removal
    is a lower-urgency human call, but the symmetry is worth surfacing.
    """
    root = root or REPO_ROOT
    path = root / TEST_WORKFLOW_REL
    if not path.is_file():
        return {"ok": False, "status": "error", "error": f"{TEST_WORKFLOW_REL} not found under {root}"}

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    matrix_lists = _parse_matrix_lists(lines)
    on_disk = _on_disk_products(root)

    added: dict[str, list[str]] = {}
    stale: dict[str, list[str]] = {}
    for ml in matrix_lists:
        predicate = _JOB_PREDICATES[ml.job]
        required = {s for s in on_disk if predicate(root, s)}
        covered = set(ml.slugs)
        missing = sorted(required - covered)
        gone = sorted(covered - required)
        if missing:
            added[ml.job] = missing
        if gone:
            stale[ml.job] = gone

    changed = bool(added)

    if not changed:
        return {
            "ok": True, "status": "in-sync", "path": str(path), "changed": False,
            "added": {}, "stale": stale,
        }

    if not write:
        return {
            "ok": True, "status": "would-write", "path": str(path), "changed": True,
            "added": added, "stale": stale,
        }

    inserts: list[tuple[int, list[str]]] = []
    for ml in matrix_lists:
        missing = added.get(ml.job)
        if not missing:
            continue
        new_lines = [f"          - {slug}\n" for slug in missing]
        inserts.append((ml.items_end, new_lines))

    for anchor, new_lines in sorted(inserts, key=lambda t: t[0], reverse=True):
        lines[anchor:anchor] = new_lines

    path.write_text("".join(lines), encoding="utf-8")
    return {
        "ok": True, "status": "written", "path": str(path), "changed": True,
        "added": added, "stale": stale,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_ci_matrix_coverage",
        description=(
            "Repair .github/workflows/test.yml's per-product `matrix: product:` "
            "lists (product-backend-tests, product-frontend-tests) so every "
            "product that QUALIFIES (has real test files for that suite) is in "
            "the matrix. Targeted — appends missing slugs only, every existing "
            "line/comment survives. Idempotent. Stale entries (matrix names a "
            "product whose tests are gone) are reported, never removed. "
            "write=False previews. Fixes the 2026-08-13 gap: igig/orbity/seed "
            "backend tests and orbity frontend tests were never running in CI. "
            "KB § PATTERNS/devops/product-lockfile-and-slug-drift.md."
        ),
    )
    def _refresh_ci_matrix_coverage(write: bool = True) -> dict:
        return sync_ci_matrix_coverage(write=write)


__all__ = [
    "TEST_WORKFLOW_REL",
    "sync_ci_matrix_coverage",
    "register",
]
