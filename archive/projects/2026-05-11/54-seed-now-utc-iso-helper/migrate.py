"""AST-driven migration: replace local `_now_iso` with seed `now_utc_iso`.

For each target file:
  1. Remove the `def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()`
     FunctionDef node.
  2. Add `from noctusai_lib.primitives.timeutil import now_utc_iso` at the
     same insertion point as other `from noctusai_lib...` imports (or after
     the existing `from datetime import ...` if none).
  3. Rename every `_now_iso()` call to `now_utc_iso()`.

Run from worktree root:
    python projects/seed-now-utc-iso-helper/migrate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import libcst as cst

WORKTREE_ROOT = Path(__file__).resolve().parents[2]

TARGETS = [
    "products/adconnect/backend/app/services/sellout_service.py",
    "products/adconnect/backend/app/services/orders_service.py",
    "products/adconnect/backend/app/services/financial_service.py",
    "products/core/backend/app/services/webhook_retention_service.py",
]


class NowIsoMigrator(cst.CSTTransformer):
    """Rewrites a single service file."""

    def __init__(self) -> None:
        super().__init__()
        self.removed_def = False
        self.renamed_calls = 0
        self.import_added = False
        self._has_existing_seed_import = False

    # --- import detection -------------------------------------------------
    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        module = _module_name(node)
        if module == "noctusai_lib.primitives.timeutil":
            # File already imports from this module; we'll append `now_utc_iso`
            self._has_existing_seed_import = True

    # --- remove local def -------------------------------------------------
    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.BaseStatement | cst.FlattenSentinel | cst.RemovalSentinel:
        if updated_node.name.value == "_now_iso":
            self.removed_def = True
            return cst.RemoveFromParent()
        return updated_node

    # --- rename callsites -------------------------------------------------
    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.BaseExpression:
        func = updated_node.func
        if isinstance(func, cst.Name) and func.value == "_now_iso":
            self.renamed_calls += 1
            return updated_node.with_changes(func=cst.Name("now_utc_iso"))
        return updated_node

    # --- inject import ----------------------------------------------------
    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        if not self.removed_def:
            return updated_node

        # Build the new import.
        new_import = cst.SimpleStatementLine(
            body=[
                cst.ImportFrom(
                    module=cst.Attribute(
                        value=cst.Attribute(
                            value=cst.Name("noctusai_lib"),
                            attr=cst.Name("primitives"),
                        ),
                        attr=cst.Name("timeutil"),
                    ),
                    names=[cst.ImportAlias(name=cst.Name("now_utc_iso"))],
                )
            ]
        )

        # Find the LAST `from X import Y` statement at module top level and
        # insert after it. This keeps import grouping intact.
        new_body: list = list(updated_node.body)
        last_import_idx = -1
        for idx, stmt in enumerate(new_body):
            if isinstance(stmt, cst.SimpleStatementLine):
                for small in stmt.body:
                    if isinstance(small, (cst.Import, cst.ImportFrom)):
                        last_import_idx = idx
                        break

        if last_import_idx == -1:
            # No imports at all — prepend (very unusual for a service file).
            new_body.insert(0, new_import)
        else:
            new_body.insert(last_import_idx + 1, new_import)
        self.import_added = True

        return updated_node.with_changes(body=new_body)


def _module_name(node: cst.ImportFrom) -> str:
    """Render an ImportFrom's module qualifier as a dotted string."""
    if node.module is None:
        return ""
    parts: list[str] = []
    cur: cst.BaseExpression = node.module
    while isinstance(cur, cst.Attribute):
        parts.append(cur.attr.value)
        cur = cur.value
    if isinstance(cur, cst.Name):
        parts.append(cur.value)
    return ".".join(reversed(parts))


def migrate(path: Path) -> dict:
    src = path.read_text()
    tree = cst.parse_module(src)
    migrator = NowIsoMigrator()
    new_tree = tree.visit(migrator)
    path.write_text(new_tree.code)
    return {
        "path": str(path.relative_to(WORKTREE_ROOT)),
        "removed_def": migrator.removed_def,
        "renamed_calls": migrator.renamed_calls,
        "import_added": migrator.import_added,
    }


def main() -> int:
    results = []
    for rel in TARGETS:
        path = WORKTREE_ROOT / rel
        if not path.exists():
            print(f"MISSING: {rel}", file=sys.stderr)
            return 1
        results.append(migrate(path))

    for r in results:
        marker = "OK" if r["removed_def"] and r["renamed_calls"] > 0 else "WARN"
        print(
            f"[{marker}] {r['path']}: removed_def={r['removed_def']} "
            f"renamed_calls={r['renamed_calls']} import_added={r['import_added']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
