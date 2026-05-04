"""AST tools — `ast_python` (libcst) + `ast_typescript` (ts-morph stub).

Per design-reference.md §3 + KB § PATTERNS/ast.md:
- Code edits go through an AST tool. Regex on source files is forbidden.
- libcst for Python, ts-morph for TypeScript.

This module exposes ``ast_python`` actions: ``rename`` (rename a name
across a file), ``find_callers`` (locate callsites of a function),
``find_pattern`` (return matches of a node-class pattern).

``ast_typescript`` is stubbed with NotImplementedError because ts-morph is
a Node subprocess — wiring that across the dev_team requires the
TypeScript engineer's setup. The stub raises a clear error message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from dev_team.tools._mcp_path import repo_root


# ---------------------------------------------------------------------------
# Python — libcst-backed
# ---------------------------------------------------------------------------


def _resolve_path(path: str) -> Path:
    """Resolve a repo-relative or absolute path under the repo root."""
    root = repo_root().resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"path {path!r} escapes the repo root {root}")
    return target


class _RenameTransformer:
    """libcst transformer that renames a Name node from old → new."""

    def __init__(self, old: str, new: str) -> None:
        import libcst as cst

        self._cst = cst
        self.old = old
        self.new = new
        self.count = 0

    def __call__(self, source: str) -> tuple[str, int]:
        cst = self._cst
        module = cst.parse_module(source)
        old, new = self.old, self.new

        outer = self

        class _T(cst.CSTTransformer):
            def leave_Name(self, original_node, updated_node):
                if original_node.value == old:
                    outer.count += 1
                    return updated_node.with_changes(value=new)
                return updated_node

        new_tree = module.visit(_T())
        return new_tree.code, self.count


def ast_python(
    action: str,
    path: str,
    *,
    old: str | None = None,
    new: str | None = None,
    function_name: str | None = None,
    pattern_kind: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """libcst-backed Python AST operations.

    Args:
        action: One of ``rename``, ``find_callers``, ``find_pattern``.
        path: Path to the .py file (under the repo root).
        old: Required for ``rename`` — the existing identifier.
        new: Required for ``rename`` — the replacement identifier.
        function_name: Required for ``find_callers``.
        pattern_kind: Required for ``find_pattern`` — libcst node class
            name (``ImportFrom``, ``ClassDef``, ``FunctionDef``, ``Try``,
            ``Call``, …).
        write: If True and ``action == 'rename'``, persist the rewrite.

    Returns:
        Action-specific result dict.

    Raises:
        ValueError: missing required kwargs for the action.
    """
    import libcst as cst

    target = _resolve_path(path)
    if not target.exists():
        raise FileNotFoundError(f"AST target not found: {path}")
    source = target.read_text(encoding="utf-8")

    if action == "rename":
        if not old or not new:
            raise ValueError("ast_python(rename) requires `old=` and `new=`")
        transformer = _RenameTransformer(old, new)
        new_source, count = transformer(source)
        if write:
            target.write_text(new_source, encoding="utf-8")
        return {"action": "rename", "path": path, "renames": count, "wrote": write}

    if action == "find_callers":
        if not function_name:
            raise ValueError("ast_python(find_callers) requires `function_name=`")
        module = cst.parse_module(source)
        wrapper = cst.metadata.MetadataWrapper(module)
        positions = wrapper.resolve(cst.metadata.PositionProvider)
        results: list[dict[str, Any]] = []
        # walk for Call nodes whose func.value matches function_name
        for node, parent in _walk(module):
            if isinstance(node, cst.Call):
                func = node.func
                name: str | None = None
                if isinstance(func, cst.Name):
                    name = func.value
                elif isinstance(func, cst.Attribute):
                    name = func.attr.value
                if name == function_name:
                    pos = positions.get(node)
                    line = pos.start.line if pos else None
                    results.append({"line": line, "snippet": _short(node, cst)})
        return {"action": "find_callers", "path": path, "matches": results}

    if action == "find_pattern":
        if not pattern_kind:
            raise ValueError("ast_python(find_pattern) requires `pattern_kind=`")
        node_cls = getattr(cst, pattern_kind, None)
        if node_cls is None:
            raise ValueError(f"unknown libcst node class: {pattern_kind!r}")
        module = cst.parse_module(source)
        wrapper = cst.metadata.MetadataWrapper(module)
        positions = wrapper.resolve(cst.metadata.PositionProvider)
        results = []
        for node, parent in _walk(module):
            if isinstance(node, node_cls):
                pos = positions.get(node)
                line = pos.start.line if pos else None
                results.append({"line": line, "snippet": _short(node, cst)})
        return {"action": "find_pattern", "path": path, "matches": results}

    raise ValueError(
        f"unknown ast_python action {action!r}; expected one of "
        "rename / find_callers / find_pattern."
    )


def _walk(node):
    """Generator yielding (node, parent) for every libcst node."""
    import libcst as cst

    stack: list[tuple[Any, Any]] = [(node, None)]
    while stack:
        current, parent = stack.pop()
        yield current, parent
        for child in getattr(current, "children", ()):  # type: ignore[arg-type]
            stack.append((child, current))


def _short(node, cst_module) -> str:
    """Return a short textual snippet for a libcst node — for find result lines."""
    try:
        snippet = cst_module.Module(body=[]).code_for_node(node)
    except Exception:
        snippet = repr(node)[:80]
    return snippet[:120].replace("\n", " ")


# ---------------------------------------------------------------------------
# TypeScript — stub (ts-morph subprocess infeasible without Node bridge)
# ---------------------------------------------------------------------------


def ast_typescript(action: str, path: str, **kwargs) -> dict[str, Any]:
    """ts-morph-backed TypeScript AST operations. **Stubbed.**

    Raises NotImplementedError until the ts-morph Node subprocess bridge
    is wired (deferred — engineer scope was infeasible without a TS
    runtime in the dev_team venv).
    """
    raise NotImplementedError(
        f"ast_typescript({action!r}) not implemented yet — ts-morph runs in "
        "Node, not Python. The dev_team subprocess bridge is a follow-up "
        "(see PROJECT.md §6 follow-ups). Use ast_python for Python; for "
        "TypeScript call ts-morph directly via shell when the wrapper "
        "ships."
    )


def apply_edit(edit: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch a single ``edit_files`` entry to the appropriate AST tool.

    Edit shape::

        {"path": "x.py", "language": "python", "action": "rename", "old": "a", "new": "b"}

    The ``language`` key selects ``ast_python`` (default — inferred from
    .py extension) or ``ast_typescript``.
    """
    path = edit.get("path")
    if not path:
        raise ValueError("edit must include `path`")
    language = edit.get("language") or _infer_language(str(path))
    action = edit.get("action")
    if not action:
        raise ValueError("edit must include `action`")
    kwargs = {k: v for k, v in edit.items() if k not in ("path", "language", "action")}
    kwargs.setdefault("write", True)  # edit_files writes by default
    if language == "python":
        return ast_python(action, str(path), **kwargs)
    if language == "typescript":
        return ast_typescript(action, str(path), **kwargs)
    raise ValueError(f"unknown language {language!r}; expected python / typescript")


def _infer_language(path: str) -> str:
    if path.endswith((".py", ".pyi")):
        return "python"
    if path.endswith((".ts", ".tsx", ".js", ".jsx")):
        return "typescript"
    raise ValueError(f"cannot infer AST language for {path!r}; pass language= explicitly")


def build_ast_python_tool(**kwargs) -> Callable:
    return ast_python


def build_ast_typescript_tool(**kwargs) -> Callable:
    return ast_typescript


__all__ = [
    "ast_python",
    "ast_typescript",
    "apply_edit",
    "build_ast_python_tool",
    "build_ast_typescript_tool",
]
