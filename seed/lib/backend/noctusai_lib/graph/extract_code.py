"""L1 code extractor — Python (stdlib ``ast``) + TypeScript (regex-anchored).

Python uses ``ast`` (same discipline as ``outline_python`` in the MCP
toolkit). TS uses anchored regex on top-level ``export``/``import``/``function``/
``class`` declarations — narrow enough to be sound (always-outline-able
invariant means files parse cleanly), and avoids a hard dep on a
TS-parsing subprocess at lib level (the MCP-side ``outline_typescript``
tool handles deeper parsing when needed).

Emits nodes + edges into a ``Graph`` passed in by the orchestrator. Pure
function over file paths; no I/O beyond reading the file.

Re-export attribution (``consumes_component`` edge)
----------------------------------------------------
When a product TS file imports ``{ LoginForm }`` from ``"@noctusai/lib/design-system"``,
the raw ``consumes_seed`` edge points at the barrel package path — not the
canonical component file. The ``BarrelResolver`` class walks the barrel
``index.ts`` files under ``seed/lib/frontend/src/`` and builds a
``symbol → canonical_path`` map at graph-build time.

For each named import from a known barrel path the extractor emits a second
``consumes_component`` edge: ``consumer-module → component-node``, where the
target is the canonical ``.tsx`` file that DEFINES the symbol (not the barrel
re-export shim). The ``consumes_seed`` edge is also kept for package-level
queries.

Edge direction decision: ``consumer-module → component`` (forward direction,
same polarity as ``IMPORTS``). Rationale: "who uses LoginForm?" is answered by
incoming edges on the component node — the natural query is
``graph.neighbors(component, incoming=True, edge_kinds=[CONSUMES_COMPONENT])``.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_PYTHON_SUFFIXES: frozenset[str] = frozenset({".py", ".pyi"})
_TS_SUFFIXES: frozenset[str] = frozenset({".ts", ".tsx"})

# FastAPI/Starlette route decorator shape: `<router-or-app>.<verb>` where
# <verb> is one of get/post/put/patch/delete/head/options/api_route.
_ROUTE_DECORATOR_RE = re.compile(
    r"^([A-Za-z_]\w*)\.(get|post|put|patch|delete|head|options|api_route)$"
)

# ── Barrel re-export resolution ────────────────────────────────────────────

# Package alias → barrel index.ts path relative to seed/lib/frontend/src/
# Order matters: more-specific paths first (so @noctusai/lib/design-system/components
# is checked before @noctusai/lib/design-system).
_BARREL_ALIASES: tuple[tuple[str, str], ...] = (
    ("@noctusai/lib/design-system/components", "design-system/components/index.ts"),
    ("@noctusai/lib/design-system/ai", "design-system/ai/index.ts"),
    ("@noctusai/lib/design-system", "design-system/index.ts"),
    ("@noctusai/lib/components", "components/index.ts"),
    ("@noctusai/lib", "index.ts"),
    ("noctusai-lib", "index.ts"),
)

# Regex to extract named exports FROM a barrel index.ts line:
# e.g.  export { Foo, Bar } from "./some/path";
# e.g.  export type { FooProps } from "./some/path";
_BARREL_EXPORT_RE = re.compile(
    r'^export\s+(?:type\s+)?\{([^}]+)\}\s+from\s+["\']([^"\']+)["\']',
    re.MULTILINE,
)

# Regex to extract named imports WITH their module path (full destructured form):
# e.g.  import { LoginForm, useTheme } from "@noctusai/lib/design-system";
_TS_NAMED_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+["\']([^"\']+)["\']',
    re.MULTILINE,
)


class BarrelResolver:
    """Resolves named symbols imported from @noctusai barrel paths to canonical component paths.

    Built once per graph-walk from the seed frontend barrel index.ts files.
    Maps ``(barrel_alias_prefix, symbol_name)`` → repo-relative canonical path.

    Skips ``export type { ... }`` entries (type-only re-exports don't produce
    runtime component nodes).

    Thread-safety: read-only after construction.
    """

    def __init__(self, seed_frontend_src: Path, repo_root: Path) -> None:
        # symbol_name → set[canonical_repo_relative_path]
        # Uses set because the same symbol could (rarely) be re-exported from
        # multiple barrel entries; we emit one edge per resolved canonical path.
        self._map: dict[str, set[str]] = {}
        # Resolve both paths to eliminate symlinks (e.g. macOS /var → /private/var)
        # so that relative_to() checks succeed across all platforms.
        self._repo_root = repo_root.resolve()
        self._seed_src = seed_frontend_src.resolve()
        self._build()

    def _build(self) -> None:
        """Walk each known barrel, resolve relative paths to repo-relative."""
        for _alias, barrel_rel in _BARREL_ALIASES:
            barrel_abs = self._seed_src / barrel_rel
            if not barrel_abs.exists():
                logger.debug("barrel_resolver: barrel not found: %s", barrel_abs)
                continue
            try:
                barrel_src = barrel_abs.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("barrel_resolver: cannot read barrel %s — %s", barrel_abs, exc)
                continue
            barrel_dir = barrel_abs.resolve().parent
            for m in _BARREL_EXPORT_RE.finditer(barrel_src):
                names_raw, rel_path = m.group(1), m.group(2)
                # Resolve relative path against barrel's directory
                if rel_path.startswith("."):
                    target = (barrel_dir / rel_path).resolve()
                else:
                    # Not a relative path (e.g. re-exporting from a sub-barrel "./ai")
                    target = (barrel_dir / rel_path).resolve()
                # If the path has no extension, try .tsx then .ts
                if not target.suffix:
                    for ext in (".tsx", ".ts"):
                        candidate = target.with_suffix(ext)
                        if candidate.exists():
                            target = candidate
                            break
                # Convert to repo-relative
                try:
                    canonical = target.relative_to(self._repo_root).as_posix()
                except ValueError:
                    logger.debug("barrel_resolver: cannot relativize %s", target)
                    continue
                # Parse symbol names from `{ Foo, Bar }` — strip type annotations
                for raw_name in names_raw.split(","):
                    sym = raw_name.strip().split(" as ")[0].strip()
                    if not sym or sym.startswith("//"):
                        continue
                    if sym not in self._map:
                        self._map[sym] = set()
                    self._map[sym].add(canonical)

        logger.debug("barrel_resolver: resolved %d symbols", len(self._map))

    def resolve(self, import_path: str, symbol: str) -> set[str]:
        """Return set of repo-relative canonical paths for ``symbol`` imported from ``import_path``.

        Returns empty set if the import_path is not a known barrel alias or the
        symbol is not found in any barrel.
        """
        if not any(import_path.startswith(alias) for alias, _ in _BARREL_ALIASES):
            return set()
        return self._map.get(symbol, set())

    def is_barrel_import(self, import_path: str) -> bool:
        return any(import_path.startswith(alias) for alias, _ in _BARREL_ALIASES)


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


def walk(
    graph: Graph,
    root: CodeRoot,
    *,
    repo_root: Path,
    only_paths: list[str] | None = None,
    barrel_resolver: BarrelResolver | None = None,
) -> None:
    """Walk a root and emit nodes + edges into ``graph``.

    Skips ``node_modules``, ``__pycache__``, ``.venv``, ``dist``, ``build``.
    If ``only_paths`` is provided, ONLY visit files whose repo-relative
    posix path is in that allow-list (incremental rebuild mode).

    ``barrel_resolver`` — if provided, resolves named imports from
    ``@noctusai/lib/...`` barrel paths to canonical component nodes and emits
    ``consumes_component`` edges. Pass ``None`` to skip re-export attribution
    (backward-compatible default).
    """
    skip_dirs = {"node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".git"}
    allow: set[str] | None = set(only_paths) if only_paths else None

    for path in _iter_source_files(root.path, skip_dirs):
        if allow is not None:
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            if rel not in allow:
                continue
        suffix = path.suffix.lower()
        if suffix in _PYTHON_SUFFIXES:
            _extract_python(graph, path, root, repo_root=repo_root)
        elif suffix in _TS_SUFFIXES:
            _extract_typescript(graph, path, root, repo_root=repo_root, barrel_resolver=barrel_resolver)


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

    # First pass: collect every server.tool-decorated function regardless of
    # nesting (MCP tools live inside `register(server)` closures, which is
    # NOT top-level — but they ARE the platform's user-facing surface).
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                dname = _name_of(d) or ""
                if "server.tool" not in dname and not dname.endswith(".tool"):
                    continue
                tool_name: str | None = None
                if isinstance(d, ast.Call):
                    for kw in d.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            tool_name = kw.value.value
                            break
                label = tool_name or node.name
                tool_id = code_id(path, f"tool::{label}", repo_root=repo_root)
                graph.add_node(Node(
                    id=tool_id,
                    label=label,
                    kind=NodeKind.MCP_TOOL,
                    path=str(path.relative_to(repo_root).as_posix()),
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    product=root.product,
                    confidence=Confidence.EXTRACTED.value,
                    meta=(("tool_name", label),),
                ))
                graph.add_edge(Edge(
                    source=module_id,
                    target=tool_id,
                    kind=EdgeKind.EXPOSES_TOOL,
                    confidence=Confidence.EXTRACTED.value,
                ))
                break  # one tool per function — collected; move on

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
            # Decorator-based kind detection (open taxonomy — extend per surface).
            decorators = [_name_of(d) for d in node.decorator_list]
            route_path = None
            route_method = None
            for d in node.decorator_list:
                dname = _name_of(d) or ""
                if "server.tool" in dname or dname.endswith(".tool"):
                    kind = NodeKind.MCP_TOOL
                # FastAPI route: @router.get(...) / @app.post(...) / etc.
                route_match = _ROUTE_DECORATOR_RE.match(dname)
                if route_match:
                    kind = NodeKind.ROUTE
                    route_method = route_match.group(2).upper()
                    if isinstance(d, ast.Call) and d.args:
                        first = d.args[0]
                        if isinstance(first, ast.Constant) and isinstance(first.value, str):
                            route_path = first.value
            meta_dict: dict[str, object] = {}
            if decorators:
                meta_dict["decorators"] = tuple(d for d in decorators if d)
            if route_path:
                meta_dict["route_path"] = route_path
            if route_method:
                meta_dict["route_method"] = route_method
            graph.add_node(Node(
                id=fn_id,
                label=node.name if not route_path else f"{route_method} {route_path}",
                kind=kind,
                path=str(path.relative_to(repo_root).as_posix()),
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                product=root.product,
                confidence=Confidence.EXTRACTED.value,
                meta=tuple(sorted(meta_dict.items())) if meta_dict else (),
            ))
            graph.add_edge(Edge(
                source=fn_id,
                target=module_id,
                kind=EdgeKind.DEFINED_IN,
                confidence=Confidence.EXTRACTED.value,
            ))
            if kind == NodeKind.MCP_TOOL:
                graph.add_edge(Edge(
                    source=module_id,
                    target=fn_id,
                    kind=EdgeKind.EXPOSES_TOOL,
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


def _emit_consumes_component_edges(
    graph: Graph,
    source: str,
    consumer_module_id: str,
    repo_root: Path,
    barrel_resolver: BarrelResolver,
) -> None:
    """Emit ``consumes_component`` edges for named imports resolved through barrels.

    For each ``import { Foo, Bar } from "@noctusai/lib/..."`` statement in
    ``source``, resolves each named symbol through the barrel registry and
    emits an edge ``consumer_module_id → code:<canonical_path>:SymbolName``.

    The target node id mirrors the ``code_id(path, symbol, repo_root=repo_root)``
    format so it joins with nodes already emitted by ``_extract_typescript``
    when it processes the canonical component file.

    Edge direction: consumer → component (same polarity as IMPORTS).
    Querying "who consumes LoginForm?" = incoming edges on the component node.
    """
    for match in _TS_NAMED_IMPORT_RE.finditer(source):
        names_raw, import_path = match.group(1), match.group(2)
        if not barrel_resolver.is_barrel_import(import_path):
            continue
        for raw_name in names_raw.split(","):
            # Strip inline type keyword, aliases (`Foo as LocalFoo`), whitespace
            raw_name = raw_name.strip()
            if not raw_name or raw_name.startswith("//"):
                continue
            # Strip leading `type ` keyword (some imports: { type FooProps, Bar })
            if raw_name.startswith("type "):
                continue
            sym = raw_name.split(" as ")[0].strip()
            if not sym:
                continue
            canonical_paths = barrel_resolver.resolve(import_path, sym)
            for canonical in canonical_paths:
                # Target = canonical module node (file level) + symbol suffix
                # We emit two targets:
                # 1. The symbol node (component:LoginForm) — most precise
                # 2. The module node (file) — fallback when symbol wasn't yet
                #    extracted (e.g. hooks or types defined in .ts not .tsx)
                # We always emit (1); if the canonical path ends in .tsx and
                # the symbol looks like a component, that node was likely
                # created by the TS extractor — the join will succeed.
                component_node_id = f"code:{canonical}:{sym}"
                graph.add_edge(Edge(
                    source=consumer_module_id,
                    target=component_node_id,
                    kind=EdgeKind.CONSUMES_COMPONENT,
                    confidence=Confidence.EXTRACTED_LOW.value,
                    meta=(
                        ("symbol", sym),
                        ("barrel", import_path),
                        ("canonical", canonical),
                    ),
                ))

_TS_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:(?:type\s+)?(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+)?["\']([^"\']+)["\']',
    re.MULTILINE,
)
_TS_TOP_LEVEL_RE = re.compile(
    r'^\s*export\s+(?:default\s+)?(?:async\s+)?(function|const|class|interface|type|enum)\s+([A-Za-z_]\w*)',
    re.MULTILINE,
)
_TS_REACT_HOOK_RE = re.compile(r'^use[A-Z]\w*$')


def _extract_typescript(
    graph: Graph,
    path: Path,
    root: CodeRoot,
    *,
    repo_root: Path,
    barrel_resolver: BarrelResolver | None = None,
) -> None:
    """Parse one TS/TSX file via anchored regex over top-level declarations.

    Sound because the always-outline-able invariant guarantees parse-clean
    files. Misses nested declarations — intentional (mirrors
    ``outline_python``'s top-level-plus-methods discipline).

    When ``barrel_resolver`` is provided and the file is NOT itself a barrel
    index (to prevent circular self-attribution), named imports from
    ``@noctusai/lib/...`` barrel paths are resolved to canonical component
    nodes and a ``consumes_component`` edge is emitted for each resolved symbol.
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

    # This file is itself a barrel shim if it's named index.ts and lives under
    # seed/lib/frontend/src/ — skip consumes_component attribution to avoid
    # circular barrel→component edges.
    is_barrel_shim = (
        path.name in ("index.ts", "index.tsx")
        and "seed/lib/frontend/src" in rel
    )

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

    # consumes_component edges: resolve named imports through barrel index.ts
    if barrel_resolver is not None and not is_barrel_shim:
        _emit_consumes_component_edges(graph, source, module_id, repo_root, barrel_resolver)

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
