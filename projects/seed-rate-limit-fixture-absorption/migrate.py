"""libcst codemod: remove inline _reset_rate_limiter autouse fixture,
add `from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401`
import.

Targets the 5 product conftests:
- products/core/backend/tests/conftest.py
- products/daily-life/backend/tests/conftest.py
- products/mailing/backend/tests/conftest.py
- products/media-scheduling/backend/tests/conftest.py
- products/therapy-platform/backend/tests/conftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import libcst as cst
import libcst.matchers as m


class RemoveResetRateLimiterAndImport(cst.CSTTransformer):
    """Remove the inline `_reset_rate_limiter` fixture definition.

    The new import is added separately by ``add_seed_fixture_import`` —
    keeps removal and insertion as separate, auditable steps.
    """

    def __init__(self) -> None:
        super().__init__()
        self.removed = False

    def leave_FunctionDef(  # noqa: D401
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ):
        if original_node.name.value != "_reset_rate_limiter":
            return updated_node
        # Confirm decorated with @pytest.fixture(autouse=True).
        is_autouse = False
        for dec in original_node.decorators:
            if m.matches(
                dec.decorator,
                m.Call(
                    func=m.Attribute(
                        value=m.Name("pytest"), attr=m.Name("fixture")
                    )
                ),
            ):
                call = dec.decorator
                assert isinstance(call, cst.Call)
                for arg in call.args:
                    if (
                        isinstance(arg.keyword, cst.Name)
                        and arg.keyword.value == "autouse"
                        and m.matches(arg.value, m.Name("True"))
                    ):
                        is_autouse = True
        if not is_autouse:
            return updated_node
        self.removed = True
        return cst.RemovalSentinel.REMOVE


def add_seed_fixture_import(module: cst.Module) -> cst.Module:
    """Insert the noqa-suppressed import after existing noctusai_lib imports.

    Strategy: find the LAST top-level ``from noctusai_lib...`` import in
    the module, and insert the new import directly after it. If no such
    import exists, insert at the top of the module body (after any
    docstring).
    """
    new_import = cst.parse_statement(
        "from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401\n"
    )

    body = list(module.body)
    last_noctusai_idx = -1
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine):
            for small in stmt.body:
                if isinstance(small, cst.ImportFrom):
                    mod_name = _import_from_module_name(small)
                    if mod_name and mod_name.startswith("noctusai_lib"):
                        last_noctusai_idx = i

    if last_noctusai_idx >= 0:
        body.insert(last_noctusai_idx + 1, new_import)
    else:
        # Fallback: insert after module-level docstring (if any).
        insert_at = 0
        if body and _is_module_docstring(body[0]):
            insert_at = 1
        body.insert(insert_at, new_import)

    return module.with_changes(body=tuple(body))


def _import_from_module_name(node: cst.ImportFrom) -> str | None:
    """Return the dotted module name being imported from."""
    if node.module is None:
        return None
    parts: list[str] = []
    cur: cst.CSTNode = node.module
    while isinstance(cur, cst.Attribute):
        parts.insert(0, cur.attr.value)
        cur = cur.value
    if isinstance(cur, cst.Name):
        parts.insert(0, cur.value)
        return ".".join(parts)
    return None


def _is_module_docstring(stmt: cst.BaseStatement) -> bool:
    return (
        isinstance(stmt, cst.SimpleStatementLine)
        and len(stmt.body) == 1
        and isinstance(stmt.body[0], cst.Expr)
        and isinstance(stmt.body[0].value, (cst.SimpleString, cst.ConcatenatedString))
    )


def migrate(path: Path) -> tuple[bool, bool]:
    """Migrate a single conftest. Returns (removed, imported)."""
    src = path.read_text()
    module = cst.parse_module(src)

    transformer = RemoveResetRateLimiterAndImport()
    module = module.visit(transformer)

    if not transformer.removed:
        print(f"  [skip] {path}: no _reset_rate_limiter fixture found")
        return (False, False)

    module = add_seed_fixture_import(module)
    path.write_text(module.code)
    return (True, True)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: migrate_rate_limit_fixture.py <conftest.py> [...]", file=sys.stderr)
        return 2

    total = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"  [error] {path}: not found", file=sys.stderr)
            continue
        removed, imported = migrate(path)
        if removed and imported:
            print(f"  [ok]   {path}: fixture removed + import added")
            total += 1
        elif removed:
            print(f"  [warn] {path}: fixture removed but import not added")
        else:
            print(f"  [skip] {path}")
    print(f"\nMigrated {total} conftests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
