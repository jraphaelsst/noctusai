"""``noctus.seed.search_capabilities`` — unified discovery over seed lib + MCP tools.

Solves the un-discoverability problem: ``list_capabilities`` returns ~203 KB
(5230 entries) and the MCP surface is ~300 tools — both too large to consume
raw.  This tool makes both surfaces navigable via three bounded modes:

**Modes**  (controlled by the ``mode`` parameter):

``search``  (default)
    Keyword/substring ranking over name + import_path + summary/description.
    Returns compact rows (import_path / tool-name + one-line summary), ranked
    by match-score.  Always bounded by ``limit``.

``summary``
    Grouped counts (no payload rows).  For lib: counts by layer + kind.
    For MCP: counts by namespace.  Fast orientation in one call.

``detail``
    Full docstring + signature/params for ONE exact target (``query`` = the
    exact ``import_path`` for lib, or the exact ``tool_name`` for mcp).
    Returns full awareness on demand without the 203 KB dump.

**Surfaces**  (controlled by the ``surface`` parameter):

``lib``   — ``noctusai_seed.*`` + ``noctusai_lib.*`` (AST-extracted).
``mcp``   — all ``noctus.*`` tools under ``mcp/noctusai/tools/`` (AST-extracted).
``all``   — both surfaces merged (default).

**Filters** (all optional, combinable):

``layer``      — lib only; restrict to one of the 6 layers:
                 primitives / config / testing / integrations / domain / api.
``kind``       — lib only; restrict to: function / async function / class /
                 constant.
``namespace``  — mcp only; restrict by dot-prefix, e.g. ``noctus.dev``,
                 ``noctus.graph``, ``noctus.seed``, ``google``, ``llm``.
``limit``      — max rows returned in search mode (default 40; capped at 200).

**Token safety**:
    Every mode returns a bounded payload.  When ``search`` drops rows due
    to ``limit``, the return includes ``"dropped": N`` so callers see the
    true match count.  ``detail`` returns one item.  ``summary`` returns
    counts only.

**Extraction reuse**:
    Lib extraction reuses ``list_capabilities._walk_package`` + helpers (no
    duplication).  MCP extraction reuses ``scan_fusions._parse_tool_file`` +
    ``_walk_tool_files`` (static AST, no runtime server start-up required).

Usage examples::

    # What seed capabilities exist for "youtube"?
    noctus.seed.search_capabilities(query="youtube", surface="lib")

    # What MCP tools handle "graph" queries?
    noctus.seed.search_capabilities(query="graph", surface="mcp")

    # How many tools exist per MCP namespace?
    noctus.seed.search_capabilities(mode="summary", surface="mcp")

    # Full doc for a specific lib capability:
    noctus.seed.search_capabilities(
        mode="detail",
        query="noctusai_lib.integrations.meta.publish_instagram_reel",
        surface="lib",
    )

    # Full doc for a specific MCP tool:
    noctus.seed.search_capabilities(
        mode="detail",
        query="noctus.dev.task_branch",
        surface="mcp",
    )

    # All integrations capabilities:
    noctus.seed.search_capabilities(surface="lib", layer="integrations", limit=60)
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ─── constants ────────────────────────────────────────────────────────────────

_LIB_LAYERS: tuple[str, ...] = (
    "primitives",
    "config",
    "testing",
    "integrations",
    "domain",
    "api",
)

_SEED_FRAMEWORK_ROOT = REPO_ROOT / "seed" / "framework" / "backend" / "noctusai_seed"
_SEED_LIB_ROOT = REPO_ROOT / "seed" / "lib" / "backend" / "noctusai_lib"
_TOOLS_ROOT = REPO_ROOT / "mcp" / "noctusai" / "tools"

_DEFAULT_LIMIT = 40
_MAX_LIMIT = 200

# ─── lib extraction (reuse list_capabilities helpers) ────────────────────────


def _docstring_first_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node) or ""
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _full_docstring(node: ast.AST) -> str:
    return ast.get_docstring(node) or ""


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _import_path(file_path: Path, package_root: Path, package_name: str) -> str:
    rel = file_path.relative_to(package_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    if not parts:
        return package_name
    return ".".join([package_name, *parts])


def _func_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reconstruct a human-readable signature string from an AST node."""
    args = node.args
    parts: list[str] = []

    # positional args + defaults
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        default_idx = i - defaults_offset
        if default_idx >= 0:
            default = args.defaults[default_idx]
            try:
                default_str = ast.unparse(default)
            except Exception:
                default_str = "..."
            parts.append(f"{arg.arg}={default_str}")
        else:
            annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
            parts.append(f"{arg.arg}{annotation}")

    # *args
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    # keyword-only
    kw_defaults = args.kw_defaults
    for i, kwarg in enumerate(args.kwonlyargs):
        kd = kw_defaults[i] if i < len(kw_defaults) and kw_defaults[i] is not None else None
        if kd:
            try:
                kd_str = ast.unparse(kd)
            except Exception:
                kd_str = "..."
            parts.append(f"{kwarg.arg}={kd_str}")
        else:
            annotation = f": {ast.unparse(kwarg.annotation)}" if kwarg.annotation else ""
            parts.append(f"{kwarg.arg}{annotation}")

    # **kwargs
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({', '.join(parts)}){ret}"


def _scan_module_detail(file_path: Path) -> list[dict]:
    """Walk a .py file, return full detail per public top-level symbol."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    out: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(node.name):
            out.append({
                "name": node.name,
                "kind": "async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "summary": _docstring_first_line(node),
                "docstring": _full_docstring(node),
                "signature": _func_signature(node),
                "lineno": node.lineno,
            })
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            out.append({
                "name": node.name,
                "kind": "class",
                "summary": _docstring_first_line(node),
                "docstring": _full_docstring(node),
                "signature": f"class {node.name}",
                "lineno": node.lineno,
            })
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and _is_public(target.id):
                    out.append({
                        "name": target.id,
                        "kind": "constant",
                        "summary": "",
                        "docstring": "",
                        "signature": target.id,
                        "lineno": node.lineno,
                    })
    return out


def _collect_lib_entries(
    *,
    repo_root: Path,
    layer_filter: str | None = None,
) -> list[dict]:
    """Walk both noctusai_seed and noctusai_lib; return flat list of entries.

    Each entry: {import_path, module, name, kind, summary, docstring, signature,
                 lineno, source (framework|library), layer (for library)}.
    """
    base = repo_root
    framework_root = base / "seed" / "framework" / "backend" / "noctusai_seed"
    lib_root = base / "seed" / "lib" / "backend" / "noctusai_lib"

    out: list[dict] = []

    # Framework package (no layers)
    if layer_filter is None and framework_root.is_dir():
        for file_path in sorted(framework_root.rglob("*.py")):
            if "__pycache__" in file_path.parts:
                continue
            caps = _scan_module_detail(file_path)
            if not caps:
                continue
            mod = _import_path(file_path, framework_root, "noctusai_seed")
            for cap in caps:
                out.append({
                    "import_path": f"{mod}.{cap['name']}" if cap["name"] else mod,
                    "module": mod,
                    "source": "framework",
                    "layer": "framework",
                    **cap,
                })

    # Library package (6 layers)
    layers_to_walk = [layer_filter] if layer_filter else list(_LIB_LAYERS)
    for layer in layers_to_walk:
        walk_root = lib_root / layer
        if not walk_root.is_dir():
            continue
        for file_path in sorted(walk_root.rglob("*.py")):
            if "__pycache__" in file_path.parts:
                continue
            caps = _scan_module_detail(file_path)
            if not caps:
                continue
            mod = _import_path(file_path, lib_root, "noctusai_lib")
            for cap in caps:
                out.append({
                    "import_path": f"{mod}.{cap['name']}" if cap["name"] else mod,
                    "module": mod,
                    "source": "library",
                    "layer": layer,
                    **cap,
                })

    return out


# ─── mcp tool extraction (reuse scan_fusions AST walking) ────────────────────

# Import the parse helpers from scan_fusions rather than duplicating them.
from tools.noctus.seed.scan_fusions import _parse_tool_file, _walk_tool_files  # noqa: E402


def _collect_mcp_entries(*, tools_root: Path, namespace_filter: str | None = None) -> list[dict]:
    """Walk all tool .py files; return flat list of MCP tool entries.

    Each entry: {tool_name, namespace, description, params, source_file}.
    """
    tool_files = _walk_tool_files(tools_root)
    out: list[dict] = []
    for path in tool_files:
        for meta in _parse_tool_file(path):
            ns = meta.namespace
            # Apply namespace filter if set (prefix match)
            if namespace_filter and not ns.startswith(namespace_filter):
                continue
            out.append({
                "tool_name": meta.name,
                "namespace": ns,
                "description": meta.description,
                "params": sorted(meta.params),
                "source_file": meta.source_file,
                "is_read_only": meta.is_read_only,
            })
    return out


# ─── detail extraction ───────────────────────────────────────────────────────


def _detail_for_lib(query: str, *, repo_root: Path) -> dict | None:
    """Resolve exact import_path → full detail from the source file."""
    # We need to find which file contains this exact import_path.
    # Strategy: collect all entries until we find the match.
    all_entries = _collect_lib_entries(repo_root=repo_root)
    match = next((e for e in all_entries if e["import_path"] == query), None)
    if match:
        return {
            "surface": "lib",
            "import_path": match["import_path"],
            "module": match["module"],
            "kind": match["kind"],
            "layer": match["layer"],
            "signature": match["signature"],
            "docstring": match["docstring"],
            "summary": match["summary"],
        }
    return None


def _detail_for_mcp(query: str, *, tools_root: Path) -> dict | None:
    """Resolve exact tool_name → full detail: reads the source file for the
    implementation function's full docstring and reconstructs signature from AST.
    """
    tool_files = _walk_tool_files(tools_root)
    for path in tool_files:
        for meta in _parse_tool_file(path):
            if meta.name != query:
                continue
            # Re-read the source file to get full implementation docstring
            # and reconstruct the impl signature.
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, SyntaxError):
                full_doc = meta.description
                signature = f"{query}({', '.join(sorted(meta.params))})"
            else:
                # Find the impl function (the function the shim delegates to,
                # not the shim itself). It's usually the non-decorated function
                # whose name doesn't start with `_`.
                shim_names: set[str] = set()
                impl_doc = ""
                impl_sig = ""
                for node in ast.walk(tree):
                    if not isinstance(node, ast.FunctionDef):
                        continue
                    # Shims are decorated with @server.tool(...)
                    is_shim = any(
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Attribute)
                        and d.func.attr == "tool"
                        for d in node.decorator_list
                    )
                    if is_shim:
                        shim_names.add(node.name)
                # Find the first public non-shim, non-register function
                for node in tree.body:
                    if (
                        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and _is_public(node.name)
                        and node.name not in shim_names
                        and node.name != "register"
                    ):
                        impl_doc = _full_docstring(node)
                        impl_sig = _func_signature(node)
                        break
                full_doc = impl_doc or meta.description
                signature = impl_sig or f"{query}({', '.join(sorted(meta.params))})"

            return {
                "surface": "mcp",
                "tool_name": meta.name,
                "namespace": meta.namespace,
                "description": meta.description,
                "params": sorted(meta.params),
                "source_file": meta.source_file,
                "signature": signature,
                "docstring": full_doc,
            }
    return None


# ─── scoring / search ────────────────────────────────────────────────────────


def _score_lib_entry(entry: dict, query_lower: str) -> int:
    """Simple rank score: exact name > name contains > import_path contains >
    summary contains."""
    name = entry["name"].lower()
    import_path = entry["import_path"].lower()
    summary = (entry.get("summary") or "").lower()
    if name == query_lower:
        return 100
    if query_lower in name:
        return 80
    if query_lower in import_path:
        return 60
    if query_lower in summary:
        return 40
    return 0


def _score_mcp_entry(entry: dict, query_lower: str) -> int:
    """Rank by exact name > name contains > description contains."""
    tool_name = entry["tool_name"].lower()
    description = (entry.get("description") or "").lower()
    if tool_name == query_lower:
        return 100
    if query_lower in tool_name:
        return 80
    if query_lower in description:
        return 40
    return 0


# ─── main entry point ─────────────────────────────────────────────────────────


def search_capabilities(
    *,
    query: str = "",
    mode: str = "search",
    surface: str = "all",
    layer: str | None = None,
    kind: str | None = None,
    namespace: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    # Test seams
    repo_root: Path | None = None,
    tools_root: Path | None = None,
) -> dict:
    """Unified discovery tool over seed lib capabilities AND MCP tools.

    Parameters
    ----------
    query : str
        Keyword/substring to search (search mode), or exact target name
        (detail mode).  Case-insensitive.  Empty = return all (bounded by
        ``limit``).
    mode : str
        One of:
        - ``search``  — ranked rows matching ``query``; bounded by ``limit``.
        - ``summary`` — grouped counts by layer/namespace/kind; no rows.
        - ``detail``  — full docstring + signature for one exact target.
    surface : str
        One of ``lib`` | ``mcp`` | ``all`` (default).
    layer : str | None
        Lib-only filter.  One of: primitives / config / testing /
        integrations / domain / api.
    kind : str | None
        Lib-only filter.  One of: function / async function / class /
        constant.
    namespace : str | None
        MCP-only filter.  Dot-prefix match, e.g. ``noctus.dev``,
        ``noctus.graph``, ``google``.
    limit : int
        Max rows in search mode (default 40, capped at 200).  Ignored in
        summary + detail modes.

    Returns
    -------
    dict
        Search mode::

            {
              "mode": "search",
              "surface": "...",
              "query": "...",
              "total_matched": int,
              "returned": int,
              "dropped": int,          # 0 when limit wasn't hit
              "results": [
                {                       # lib entry
                  "surface": "lib",
                  "import_path": "...",
                  "kind": "...",
                  "layer": "...",
                  "summary": "...",
                  "score": int,
                },
                {                       # mcp entry
                  "surface": "mcp",
                  "tool_name": "...",
                  "namespace": "...",
                  "summary": "...",     # first sentence of description
                  "score": int,
                },
              ],
            }

        Summary mode::

            {
              "mode": "summary",
              "surface": "...",
              "lib": {
                "total": int,
                "by_layer": {"primitives": int, ...},
                "by_kind":  {"function": int, ...},
              },
              "mcp": {
                "total": int,
                "by_namespace": {"noctus.dev": int, ...},
              },
            }

        Detail mode::

            {
              "mode": "detail",
              "surface": "lib" | "mcp",
              "found": true | false,
              "item": {
                # lib: import_path, module, kind, layer, signature, docstring
                # mcp: tool_name, namespace, params, signature, docstring
              },
            }
    """
    _repo_root = repo_root if repo_root is not None else REPO_ROOT
    _tools_root = tools_root if tools_root is not None else _TOOLS_ROOT

    # Clamp limit
    limit = min(max(1, limit), _MAX_LIMIT)

    if mode == "detail":
        return _handle_detail(
            query=query,
            surface=surface,
            repo_root=_repo_root,
            tools_root=_tools_root,
        )

    if mode == "summary":
        return _handle_summary(
            surface=surface,
            layer=layer,
            namespace=namespace,
            repo_root=_repo_root,
            tools_root=_tools_root,
        )

    # Default: search
    return _handle_search(
        query=query,
        surface=surface,
        layer=layer,
        kind=kind,
        namespace=namespace,
        limit=limit,
        repo_root=_repo_root,
        tools_root=_tools_root,
    )


def _handle_detail(
    *,
    query: str,
    surface: str,
    repo_root: Path,
    tools_root: Path,
) -> dict:
    if not query:
        return {
            "mode": "detail",
            "surface": surface,
            "found": False,
            "error": "detail mode requires a non-empty query (exact import_path or tool_name)",
        }

    item = None
    resolved_surface = surface

    if surface in ("lib", "all"):
        item = _detail_for_lib(query, repo_root=repo_root)
        if item:
            resolved_surface = "lib"

    if item is None and surface in ("mcp", "all"):
        item = _detail_for_mcp(query, tools_root=tools_root)
        if item:
            resolved_surface = "mcp"

    return {
        "mode": "detail",
        "surface": resolved_surface,
        "found": item is not None,
        "item": item or None,
    }


def _handle_summary(
    *,
    surface: str,
    layer: str | None,
    namespace: str | None,
    repo_root: Path,
    tools_root: Path,
) -> dict:
    result: dict[str, Any] = {"mode": "summary", "surface": surface}

    if surface in ("lib", "all"):
        lib_entries = _collect_lib_entries(repo_root=repo_root, layer_filter=layer)
        by_layer: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for e in lib_entries:
            lyr = e.get("layer", "?")
            by_layer[lyr] = by_layer.get(lyr, 0) + 1
            knd = e.get("kind", "?")
            by_kind[knd] = by_kind.get(knd, 0) + 1
        result["lib"] = {
            "total": len(lib_entries),
            "by_layer": dict(sorted(by_layer.items())),
            "by_kind": dict(sorted(by_kind.items())),
        }

    if surface in ("mcp", "all"):
        mcp_entries = _collect_mcp_entries(tools_root=tools_root, namespace_filter=namespace)
        by_ns: dict[str, int] = {}
        for e in mcp_entries:
            ns = e.get("namespace", "?")
            by_ns[ns] = by_ns.get(ns, 0) + 1
        result["mcp"] = {
            "total": len(mcp_entries),
            "by_namespace": dict(sorted(by_ns.items())),
        }

    return result


def _handle_search(
    *,
    query: str,
    surface: str,
    layer: str | None,
    kind: str | None,
    namespace: str | None,
    limit: int,
    repo_root: Path,
    tools_root: Path,
) -> dict:
    query_lower = query.lower().strip()
    scored: list[tuple[int, dict]] = []

    if surface in ("lib", "all"):
        lib_entries = _collect_lib_entries(repo_root=repo_root, layer_filter=layer)
        for e in lib_entries:
            # kind filter
            if kind and e.get("kind") != kind:
                continue
            score = _score_lib_entry(e, query_lower) if query_lower else 1
            if score == 0:
                continue
            scored.append((score, {
                "surface": "lib",
                "import_path": e["import_path"],
                "kind": e["kind"],
                "layer": e["layer"],
                "summary": e["summary"],
                "score": score,
            }))

    if surface in ("mcp", "all"):
        mcp_entries = _collect_mcp_entries(tools_root=tools_root, namespace_filter=namespace)
        for e in mcp_entries:
            score = _score_mcp_entry(e, query_lower) if query_lower else 1
            if score == 0:
                continue
            # First sentence of description as summary
            desc = e.get("description") or ""
            first_sent = desc.split(".")[0].strip() if desc else ""
            scored.append((score, {
                "surface": "mcp",
                "tool_name": e["tool_name"],
                "namespace": e["namespace"],
                "summary": first_sent,
                "score": score,
            }))

    # Sort by score desc, then by name asc
    scored.sort(key=lambda x: (-x[0], x[1].get("import_path") or x[1].get("tool_name", "")))
    total = len(scored)
    rows = [row for _, row in scored[:limit]]
    dropped = total - len(rows)

    return {
        "mode": "search",
        "surface": surface,
        "query": query,
        "total_matched": total,
        "returned": len(rows),
        "dropped": dropped,
        "results": rows,
    }


# ─── registration ─────────────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.seed.search_capabilities",
        description=(
            "Unified discovery over seed lib (noctusai_seed.* + noctusai_lib.*) "
            "AND all MCP tools (~300 noctus.* tools). Three modes: "
            "``search`` (keyword/substring ranked rows, bounded by limit — never the 203KB dump); "
            "``summary`` (grouped counts by layer/namespace/kind — orient in one call); "
            "``detail`` (full docstring + signature for one exact target). "
            "Filters: ``surface`` (lib|mcp|all), ``layer`` (lib 6-layer), ``kind``, "
            "``namespace`` (mcp prefix e.g. noctus.dev). "
            "Use BEFORE inventing new helpers; use for 'what tools exist for X'."
        ),
    )
    def _shim(
        query: str = "",
        mode: str = "search",
        surface: str = "all",
        layer: str = "",
        kind: str = "",
        namespace: str = "",
        limit: int = _DEFAULT_LIMIT,
    ) -> dict:
        return search_capabilities(
            query=query,
            mode=mode,
            surface=surface,
            layer=layer or None,
            kind=kind or None,
            namespace=namespace or None,
            limit=limit,
        )
