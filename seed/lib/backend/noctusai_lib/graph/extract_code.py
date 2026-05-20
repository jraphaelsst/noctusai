"""L1 code extractor — Python (stdlib ``ast``) + TypeScript (regex-anchored).

Python uses ``ast`` (same discipline as ``outline_python`` in the MCP
toolkit). TS uses anchored regex on top-level ``export``/``import``/``function``/
``class`` declarations — narrow enough to be sound (always-outline-able
invariant means files parse cleanly), and avoids a hard dep on a
TS-parsing subprocess at lib level (the MCP-side ``outline_typescript``
tool handles deeper parsing when needed).

Emits nodes + edges into a ``Graph`` passed in by the orchestrator. Pure
function over file paths; no I/O beyond reading the file.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_PYTHON_SUFFIXES: frozenset[str] = frozenset({".py", ".pyi"})
_TS_SUFFIXES: frozenset[str] = frozenset({".ts", ".tsx"})


@dataclass(frozen=True)
class CodeRoot:
    """One root the walker scans. Used to label nodes by product/seed."""

    path: Path                # absolute root
    label: str                # "social-wiring", "seed", "core", "mcp", "noctusai_lib"
    product: str | None       # populated for products; None for seed/mcp
    kind_hint: NodeKind | None = None  # SEED for seed roots


def code_id(path: Path, symbol: str | None = None, *, repo_root: Path) -> str:
    """Stable id: ``code:<rel-path>[:symbol]``."""
    rel = path.relative_to(repo_root) if path.is_absolute() else path
    base = f"code:{rel.as_posix()}"
    return f"{base}:{symbol}" if symbol else base


def walk(graph: Graph, root: CodeRoot, *, repo_root: Path) -> None:
    """Walk a root and emit nodes + edges into ``graph``.

    Skips ``node_modules``, ``__pycache__``, ``.venv``, ``dist``, ``build``.
    """
    skip_dirs = {"node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".git"}

    for path in _iter_source_files(root.path, skip_dirs):
        suffix = path.suffix.lower()
        if suffix in _PYTHON_SUFFIXES:
            _extract_python(graph, path, root, repo_root=repo_root)
        elif suffix in _TS_SUFFIXES:
            _extract_typescript(graph, path, root, repo_root=repo_root)


def _iter_source_files(root: Path, skip_dirs: set[str]):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() in (_PYTHON_SUFFIXES | _TS_SUFFIXES):
            yield path


def _extract_python(graph: Graph, path: Path, root: CodeRoot, *, repo_root: Path) -> None:
    """Parse one Python file and add its symbols + import edges."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        logger.debug("graph.extract_code: skipping %s — %s", path, exc)
        return

    module_id = code_id(path, repo_root=repo_root)
    module_label = path.stem
    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.split("\n", 1)[0].strip() if docstring else ""

    graph.add_node(Node(
        id=module_id,
        label=module_label,
        kind=NodeKind.MODULE,
        path=str(path.relative_to(repo_root).as_posix()),
        line=1,
        end_line=len(source.splitlines()),
        product=root.product,
        confidence=Confidence.EXTRACTED.value,
        meta=(("docstring", first_line),) if first_line else (),
    ))

    # Product-membership edge (anchor → module).
    if root.product:
        graph.add_edge(Edge(
            source=f"product:{root.product}",
            target=module_id,
            kind=EdgeKind.CONTAINS,
            confidence=Confidence.EXTRACTED.value,
        ))
    elif root.kind_hint == NodeKind.SEED:
        graph.add_edge(Edge(
            source="seed:noctusai_lib",
            target=module_id,
            kind=EdgeKind.CONTAINS,
            confidence=Confidence.EXTRACTED.value,
        ))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _emit_import_edge(graph, node, module_id, repo_root=repo_root)
        elif isinstance(node, ast.ClassDef):
            cls_id = code_id(path, node.name, repo_root=repo_root)
            graph.add_node(Node(
                id=cls_id,
                label=node.name,
                kind=NodeKind.CLASS,
                path=str(path.relative_to(repo_root).as_posix()),
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                product=root.product,
                confidence=Confidence.EXTRACTED.value,
            ))
            graph.add_edge(Edge(
                source=cls_id,
                target=module_id,
                kind=EdgeKind.DEFINED_IN,
                confidence=Confidence.EXTRACTED.value,
            ))
            # Inheritance edges
            for base in node.bases:
                base_name = _name_of(base)
                if base_name:
                    graph.add_edge(Edge(
                        source=cls_id,
                        target=f"symbol:{base_name}",  # late-bound; may not resolve
                        kind=EdgeKind.INHERITS,
                        confidence=Confidence.EXTRACTED.value,
                        meta=(("base", base_name),),
                    ))
            # Methods
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    meth_id = code_id(path, f"{node.name}.{child.name}", repo_root=repo_root)
                    graph.add_node(Node(
                        id=meth_id,
                        label=f"{node.name}.{child.name}",
                        kind=NodeKind.METHOD,
                        path=str(path.relative_to(repo_root).as_posix()),
                        line=child.lineno,
                        end_line=getattr(child, "end_lineno", child.lineno),
                        product=root.product,
                        confidence=Confidence.EXTRACTED.value,
                    ))
                    graph.add_edge(Edge(
                        source=meth_id,
                        target=cls_id,
                        kind=EdgeKind.DEFINED_IN,
                        confidence=Confidence.EXTRACTED.value,
                    ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_top_level(tree, node):
            fn_id = code_id(path, node.name, repo_root=repo_root)
            kind = NodeKind.FUNCTION
            # MCP tool detection: decorator @server.tool(...)
            decorators = [_name_of(d) for d in node.decorator_list]
            if any(d and ("server.tool" in d or d.endswith(".tool")) for d in decorators):
                kind = NodeKind.MCP_TOOL
            graph.add_node(Node(
                id=fn_id,
                label=node.name,
                kind=kind,
                path=str(path.relative_to(repo_root).as_posix()),
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                product=root.product,
                confidence=Confidence.EXTRACTED.value,
                meta=(("decorators", tuple(d for d in decorators if d)),) if decorators else (),
            ))
            graph.add_edge(Edge(
                source=fn_id,
                target=module_id,
                kind=EdgeKind.DEFINED_IN,
                confidence=Confidence.EXTRACTED.value,
            ))


def _emit_import_edge(graph: Graph, node: ast.AST, module_id: str, *, repo_root: Path) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            graph.add_edge(Edge(
                source=module_id,
                target=f"pkg:{alias.name}",
                kind=EdgeKind.IMPORTS,
                confidence=Confidence.EXTRACTED.value,
                meta=(("name", alias.name),),
            ))
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if not module:
            return
        edge_kind = EdgeKind.CONSUMES_SEED if module.startswith("noctusai_lib") else EdgeKind.IMPORTS
        graph.add_edge(Edge(
            source=module_id,
            target=f"pkg:{module}",
            kind=edge_kind,
            confidence=Confidence.EXTRACTED.value,
            meta=(("names", tuple(a.name for a in node.names)),),
        ))


def _is_top_level(tree: ast.Module, node: ast.AST) -> bool:
    return any(child is node for child in tree.body)


def _name_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return None


# ── TypeScript ────────────────────────────────────────────────────────────────

_TS_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:(?:type\s+)?(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+)?["\']([^"\']+)["\']',
    re.MULTILINE,
)
_TS_TOP_LEVEL_RE = re.compile(
    r'^\s*export\s+(?:default\s+)?(?:async\s+)?(function|const|class|interface|type|enum)\s+([A-Za-z_]\w*)',
    re.MULTILINE,
)
_TS_REACT_HOOK_RE = re.compile(r'^use[A-Z]\w*$')


def _extract_typescript(graph: Graph, path: Path, root: CodeRoot, *, repo_root: Path) -> None:
    """Parse one TS/TSX file via anchored regex over top-level declarations.

    Sound because the always-outline-able invariant guarantees parse-clean
    files. Misses nested declarations — intentional (mirrors
    ``outline_python``'s top-level-plus-methods discipline).
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("graph.extract_code: skipping %s — %s", path, exc)
        return

    rel = path.relative_to(repo_root).as_posix()
    module_id = code_id(path, repo_root=repo_root)
    line_count = len(source.splitlines())

    graph.add_node(Node(
        id=module_id,
        label=path.stem,
        kind=NodeKind.MODULE,
        path=rel,
        line=1,
        end_line=line_count,
        product=root.product,
        confidence=Confidence.EXTRACTED.value,
    ))

    if root.product:
        graph.add_edge(Edge(
            source=f"product:{root.product}",
            target=module_id,
            kind=EdgeKind.CONTAINS,
            confidence=Confidence.EXTRACTED.value,
        ))
    elif root.kind_hint == NodeKind.SEED:
        graph.add_edge(Edge(
            source="seed:noctusai_lib",
            target=module_id,
            kind=EdgeKind.CONTAINS,
            confidence=Confidence.EXTRACTED.value,
        ))

    # Imports
    for match in _TS_IMPORT_RE.finditer(source):
        target_module = match.group(1)
        edge_kind = (
            EdgeKind.CONSUMES_SEED
            if target_module.startswith(("noctusai-lib", "@noctusai", "noctusai_lib"))
            else EdgeKind.IMPORTS
        )
        graph.add_edge(Edge(
            source=module_id,
            target=f"pkg:{target_module}",
            kind=edge_kind,
            confidence=Confidence.EXTRACTED.value,
        ))

    # Top-level exports
    lines = source.split("\n")
    for match in _TS_TOP_LEVEL_RE.finditer(source):
        decl_kind, name = match.group(1), match.group(2)
        line_no = source[: match.start()].count("\n") + 1
        # Heuristic kinds:
        # - capitalised function/const in .tsx → likely React component
        # - useX function → hook
        if _TS_REACT_HOOK_RE.match(name):
            node_kind = NodeKind.HOOK
        elif path.suffix == ".tsx" and name[:1].isupper() and decl_kind in ("function", "const"):
            node_kind = NodeKind.COMPONENT
        elif decl_kind == "class":
            node_kind = NodeKind.CLASS
        else:
            node_kind = NodeKind.FUNCTION
        sym_id = code_id(path, name, repo_root=repo_root)
        graph.add_node(Node(
            id=sym_id,
            label=name,
            kind=node_kind,
            path=rel,
            line=line_no,
            end_line=min(line_no + 5, line_count),  # placeholder; not used for edges
            product=root.product,
            confidence=Confidence.EXTRACTED.value,
            meta=(("declaration", decl_kind),),
        ))
        graph.add_edge(Edge(
            source=sym_id,
            target=module_id,
            kind=EdgeKind.DEFINED_IN,
            confidence=Confidence.EXTRACTED.value,
        ))
