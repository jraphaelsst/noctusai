"""``noctus.seed.list_capabilities`` — enumerate seed-provided exports.

Walks ``seed/framework/backend/noctusai_seed/`` and ``seed/lib/backend/
noctusai_lib/`` via AST (no imports → no side effects, no LLM/Supabase init
required). Reports public top-level functions, classes, and module-level
constants with their first-line docstring summaries.

Why: future scaffolds + engineers should know what's already provided
before reinventing. The ``noctusai_lib`` six-layer layout
(primitives / config / testing / integrations / domain / api) is preserved
in the output so callers see "what kind of thing" each capability is.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)


_SEED_FRAMEWORK_ROOT = REPO_ROOT / "seed" / "framework" / "backend" / "noctusai_seed"
_SEED_LIB_ROOT = REPO_ROOT / "seed" / "lib" / "backend" / "noctusai_lib"

# noctusai_lib's 6-layer layout — top-level subpackages map to these layers.
_LIB_LAYERS: tuple[str, ...] = (
    "primitives",
    "config",
    "testing",
    "integrations",
    "domain",
    "api",
)


def _docstring_first_line(node: ast.AST) -> str:
    """First sentence/line of the docstring, or empty string."""
    doc = ast.get_docstring(node) or ""
    if not doc:
        return ""
    first_line = doc.strip().splitlines()[0].strip()
    return first_line


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _scan_module(file_path: Path) -> list[dict]:
    """AST-walk a Python file; yield public top-level capabilities."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    capabilities: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(node.name):
            capabilities.append({
                "name": node.name,
                "kind": "async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "summary": _docstring_first_line(node),
                "lineno": node.lineno,
            })
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            capabilities.append({
                "name": node.name,
                "kind": "class",
                "summary": _docstring_first_line(node),
                "lineno": node.lineno,
            })
        elif isinstance(node, ast.Assign):
            # Module-level constants (NAME = ...). Filter to UPPER_SNAKE_CASE
            # — that's the platform convention for public exported constants.
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and _is_public(target.id):
                    capabilities.append({
                        "name": target.id,
                        "kind": "constant",
                        "summary": "",
                        "lineno": node.lineno,
                    })
    return capabilities


def _import_path(file_path: Path, package_root: Path, package_name: str) -> str:
    """Convert ``<root>/foo/bar.py`` into ``<package>.foo.bar`` (or
    ``<package>.foo`` if the file is ``__init__.py``)."""
    rel = file_path.relative_to(package_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # strip .py
    if not parts:
        return package_name
    return ".".join([package_name, *parts])


def _walk_package(
    package_root: Path,
    package_name: str,
    *,
    layer_filter: str | None = None,
) -> list[dict]:
    """Walk all .py files under a package root; collect capabilities.

    ``layer_filter`` (when set) restricts to files under
    ``<package_root>/<layer_filter>/``.
    """
    if not package_root.is_dir():
        return []
    out: list[dict] = []
    walk_root = package_root / layer_filter if layer_filter else package_root
    if not walk_root.is_dir():
        return []
    for file_path in sorted(walk_root.rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        capabilities = _scan_module(file_path)
        if not capabilities:
            continue
        import_path = _import_path(file_path, package_root, package_name)
        for cap in capabilities:
            out.append({
                "import_path": f"{import_path}.{cap['name']}" if cap['name'] else import_path,
                "module": import_path,
                **cap,
            })
    return out


def list_capabilities(
    *,
    repo_root: Path | None = None,
) -> dict:
    """Enumerate seed-provided public capabilities.

    Returns:
        ``{
          "framework": [{import_path, module, name, kind, summary, lineno}, ...],
          "library": {
            "primitives": [...],
            "config": [...],
            "testing": [...],
            "integrations": [...],
            "domain": [...],
            "api": [...],
          },
          "summary": {
            "framework_count": int,
            "library_counts": {layer: int, ...},
            "total": int,
          },
        }``
    """
    base_root = repo_root if repo_root is not None else REPO_ROOT
    framework_root = base_root / "seed" / "framework" / "backend" / "noctusai_seed"
    lib_root = base_root / "seed" / "lib" / "backend" / "noctusai_lib"

    framework = _walk_package(framework_root, "noctusai_seed")

    library: dict[str, list[dict]] = {}
    for layer in _LIB_LAYERS:
        library[layer] = _walk_package(lib_root, "noctusai_lib", layer_filter=layer)

    summary = {
        "framework_count": len(framework),
        "library_counts": {layer: len(library[layer]) for layer in _LIB_LAYERS},
        "total": len(framework) + sum(len(v) for v in library.values()),
    }

    return {
        "framework": framework,
        "library": library,
        "summary": summary,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.list_capabilities",
        description=(
            "Enumerate every public capability the seed currently provides — "
            "framework factories (`noctusai_seed.*`) and library exports "
            "(`noctusai_lib.*` grouped by 6-layer layout). Each entry: "
            "import path + kind (function/class/constant) + first-line "
            "docstring. Use BEFORE inventing a new helper to confirm the "
            "seed doesn't already ship it."
        ),
    )
    def _list() -> dict:
        return list_capabilities()
