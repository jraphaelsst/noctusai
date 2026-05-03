"""
Catalog tool — auto-generated shared-library observation layer.

Purpose: keep a live view of every symbol exported by the shared-library
packages (the "seed spine") and who consumes them. Replaces drift in the
hand-maintained `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` with a
mechanically-derived artifact.

What it reports per run:
  1. Every public symbol in every lib root (module, kind, signature, doc).
  2. Which products import each symbol, and how many times.
  3. **Orphans** — lib symbols with zero importers (dead or unused code).
  4. **Duplication candidates** — names defined in 2+ products but NOT in lib
     (candidates for absorption into the shared library).

What it does NOT do:
  - Modify product code.
  - Rename things.
  - Auto-absorb duplicates — those require human judgment (false positives
    are normal for name-only matching).

Namespace note:
  The `LIB_ROOTS` map below is the single knob for the eventual rename from
  the current `noctusai_lib` / `noctusai_seed` to `noctusai.lib` /
  `noctusai.seed`. When the rename lands, update the dict keys — the rest of
  the tool adapts automatically. Output shows the *actual* import paths
  present in the code today (truth in observation).

Run:
  python mcp/noctusai/cli.py --catalog              # print + write markdown
  python mcp/noctusai/cli.py --catalog --json       # structured output
"""
from __future__ import annotations

# accept-with-rationale: "MCP detectors keep raw `import ast`" in
# KB § PATTERNS/accept-with-rationale.md — catalog needs node-level
# introspection (Call.keywords, Field defaults, ast.unparse for full
# signatures, ast.get_docstring) below outline_python's symbol-tree
# contract. Migration evaluated 2026-05-02 by ast-callers-consolidation
# Phase 0 → accept; outline_python is for narrow-read planning, not
# detector parsing.
import ast
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field as PydField

logger = logging.getLogger(__name__)


class CatalogInput(BaseModel):
    write: bool = PydField(
        True,
        description="Write the markdown artifact to mcp/noctusai/catalog.md. False returns markdown inline.",
    )


class CatalogOutput(BaseModel):
    output_path: str | None = PydField(
        None, description="Relative path to the written artifact. None when `write=False`."
    )
    markdown: str | None = PydField(
        None, description="Inline markdown when `write=False`. None when `write=True`."
    )
    summary: dict[str, Any] = PydField(
        default_factory=dict,
        description="Counts: total_symbols, products, orphans, single_consumer, duplicate_candidates.",
    )
    symbols: list[dict[str, Any]] = PydField(default_factory=list)
    orphans: list[dict[str, Any]] = PydField(default_factory=list)
    duplicate_candidates: list[dict[str, Any]] = PydField(default_factory=list)

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)

# Map of import-path prefix → filesystem root. Update when the namespace
# is renamed (e.g. "noctusai_lib" → "noctusai.lib"). Currently these are
# flat top-level packages; for dotted names (PEP 420 namespace packages)
# the key must be the full dotted prefix as it appears in import statements.
LIB_ROOTS: dict[str, Path] = {
    "noctusai_lib": REPO_ROOT / "seed" / "lib" / "backend" / "noctusai_lib",
    "noctusai_seed": REPO_ROOT / "seed" / "framework" / "backend" / "noctusai_seed",
}

CATALOG_OUTPUT = REPO_ROOT / "mcp" / "noctusai" / "catalog.md"


# ── Data model ────────────────────────────────────────────────────────

@dataclass
class Symbol:
    """A public top-level symbol exported by a lib module."""
    qualified_name: str        # e.g. "noctusai_lib.api.auth.resolve_sso_role"
    module: str                # e.g. "noctusai_lib.auth"
    name: str                  # e.g. "resolve_sso_role"
    kind: str                  # "def" | "async def" | "class" | "const"
    signature: str             # "(user: dict) -> Optional[str]"  or ""
    doc: str                   # first line of docstring or ""
    location: str              # "seed/lib/backend/noctusai_lib/auth.py:42"

    # Populated after product scan
    importers: list[str] = field(default_factory=list)   # product slugs
    import_count: int = 0                                  # total imports across all products


@dataclass
class DuplicateCandidate:
    name: str
    kind: str
    occurrences: list[dict]    # [{"product": str, "file": str, "line": int}]


@dataclass
class CatalogReport:
    lib_roots: dict[str, str]
    products_scanned: list[str]
    symbols: list[Symbol]
    orphans: list[Symbol]
    single_consumer: list[Symbol]
    duplicates: list[DuplicateCandidate]

    def to_dict(self) -> dict:
        return {
            "lib_roots": self.lib_roots,
            "products_scanned": self.products_scanned,
            "symbols": [asdict(s) for s in self.symbols],
            "orphans": [asdict(s) for s in self.orphans],
            "single_consumer": [asdict(s) for s in self.single_consumer],
            "duplicates": [asdict(d) for d in self.duplicates],
            "summary": {
                "total_symbols": len(self.symbols),
                "orphans": len(self.orphans),
                "single_consumer": len(self.single_consumer),
                "duplicate_candidates": len(self.duplicates),
                "products": len(self.products_scanned),
            },
        }


# ── AST helpers ───────────────────────────────────────────────────────

def _parse(path: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        logger.warning("catalog: cannot parse %s (%s), skipping", path, exc)
        return None


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _signature(node: ast.AST) -> str:
    """Render a compact signature for a FunctionDef or AsyncFunctionDef."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    try:
        return f"({ast.unparse(node.args)})" + (
            f" -> {ast.unparse(node.returns)}" if node.returns else ""
        )
    except Exception as exc:
        logger.warning("catalog: ast.unparse failed for %s: %s", getattr(node, 'name', '?'), exc)
        return "(...)"


def _docstring(node: ast.AST) -> str:
    try:
        doc = ast.get_docstring(node) or ""
    except Exception as exc:
        logger.warning("catalog: ast.get_docstring failed for %s: %s", getattr(node, 'name', '?'), exc)
        return ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def _module_name(pkg_prefix: str, pkg_root: Path, file_path: Path) -> str:
    """Turn a file path into a dotted module name under the package prefix."""
    rel = file_path.relative_to(pkg_root).with_suffix("")
    parts = [pkg_prefix] + [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


# ── Supply side: scan lib roots for public symbols ────────────────────

def scan_lib_symbols() -> list[Symbol]:
    """
    Collect only *source-defined* public symbols (def, async def, class,
    uppercase module-level const).

    Re-exports in __init__.py files are NOT emitted as separate Symbols —
    they're handled by the re-export resolution map instead, which threads
    import attribution back to the source definition. Emitting them as
    Symbols would double-count and pollute the orphan list.
    """
    symbols: list[Symbol] = []
    seen_source_defs: set[str] = set()

    for prefix, root in LIB_ROOTS.items():
        if not root.exists():
            continue
        for py in sorted(root.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            tree = _parse(py)
            if not tree:
                continue
            module = _module_name(prefix, root, py)
            location_rel = py.relative_to(REPO_ROOT)
            is_init = py.name == "__init__.py"

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public(node.name):
                    sym_module = prefix if is_init else module
                    qn = f"{sym_module}.{node.name}"
                    if qn in seen_source_defs:
                        continue
                    seen_source_defs.add(qn)
                    symbols.append(Symbol(
                        qualified_name=qn,
                        module=sym_module,
                        name=node.name,
                        kind="async def" if isinstance(node, ast.AsyncFunctionDef) else "def",
                        signature=_signature(node),
                        doc=_docstring(node),
                        location=f"{location_rel}:{node.lineno}",
                    ))

                elif isinstance(node, ast.ClassDef) and _is_public(node.name):
                    sym_module = prefix if is_init else module
                    qn = f"{sym_module}.{node.name}"
                    if qn in seen_source_defs:
                        continue
                    seen_source_defs.add(qn)
                    symbols.append(Symbol(
                        qualified_name=qn,
                        module=sym_module,
                        name=node.name,
                        kind="class",
                        signature="",
                        doc=_docstring(node),
                        location=f"{location_rel}:{node.lineno}",
                    ))

                elif isinstance(node, ast.Assign):
                    # module-level constants: NAME = ...
                    # Skip single-letter uppercase names (almost always TypeVars
                    # like `T = TypeVar("T")`) and assignments whose RHS is a
                    # TypeVar / NewType call.
                    rhs_is_typevar = (
                        isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name)
                        and node.value.func.id in ("TypeVar", "NewType")
                    )
                    if rhs_is_typevar:
                        continue
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and _is_public(target.id)
                            and target.id.isupper()
                            and len(target.id) > 1
                        ):
                            sym_module = prefix if is_init else module
                            qn = f"{sym_module}.{target.id}"
                            if qn in seen_source_defs:
                                continue
                            seen_source_defs.add(qn)
                            symbols.append(Symbol(
                                qualified_name=qn,
                                module=sym_module,
                                name=target.id,
                                kind="const",
                                signature="",
                                doc="",
                                location=f"{location_rel}:{node.lineno}",
                            ))

                # Re-exports in __init__.py are handled entirely by
                # build_reexport_map() — no Symbols emitted here.

    symbols.sort(key=lambda s: (s.module, s.name))
    return symbols


# ── Re-export resolution map ──────────────────────────────────────────

def build_reexport_map() -> dict[str, str]:
    """
    Map `{module}.{alias}` → `{source_module}.{source_name}` by parsing every
    `__init__.py` in each lib root.

    When a product writes `from noctusai_lib import AppException`, the catalog
    must credit `noctusai_lib.primitives.exceptions.AppException` — not orphan the source.
    """
    rmap: dict[str, str] = {}
    for prefix, root in LIB_ROOTS.items():
        if not root.exists():
            continue
        for init_py in root.rglob("__init__.py"):
            if "__pycache__" in init_py.parts:
                continue
            tree = _parse(init_py)
            if not tree:
                continue
            init_module = _module_name(prefix, root, init_py)
            for node in tree.body:
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                if node.module == "__future__":
                    continue
                if node.level:
                    src_module = f"{prefix}.{node.module}" if node.module else prefix
                elif node.module.startswith(prefix):
                    src_module = node.module
                else:
                    continue
                for alias in node.names:
                    exposed_as = alias.asname or alias.name
                    rmap[f"{init_module}.{exposed_as}"] = f"{src_module}.{alias.name}"
    return rmap


# ── Demand side: scan products + lib roots for lib-symbol imports ────

def _iter_products() -> Iterable[tuple[str, Path]]:
    if not PRODUCTS_DIR.exists():
        return
    for d in sorted(PRODUCTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            yield d.name, d


def _iter_consumers() -> Iterable[tuple[str, Path, Optional[str]]]:
    """
    Every code tree that may import from a lib root.

    Yields (label, scan_root, owning_lib_prefix). `owning_lib_prefix` is
    non-None when the consumer is itself a lib root (needed to resolve
    relative imports like `from .auth import ...`).
    """
    for slug, product_path in _iter_products():
        backend = product_path / "backend"
        if backend.exists():
            yield slug, backend, None
    for prefix, root in LIB_ROOTS.items():
        if root.exists():
            yield f"lib:{prefix}", root, prefix


def scan_importers(reexport_map: dict[str, str]) -> dict[str, dict[str, int]]:
    """
    Returns: {qualified_symbol_name: {consumer_label: import_count}}

    Re-exports are resolved to their source symbol so `from noctusai_lib import
    AppException` credits `noctusai_lib.primitives.exceptions.AppException`, not an orphan.
    Internal lib-to-lib imports show up as `lib:noctusai_seed` (etc.).
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    lib_prefixes = tuple(LIB_ROOTS.keys())

    for consumer_label, scan_root, owning_prefix in _iter_consumers():
        for py in scan_root.rglob("*.py"):
            if "__pycache__" in py.parts or ".backup" in py.parts:
                continue
            tree = _parse(py)
            if not tree:
                continue

            # Package path of the file being scanned — used to resolve `from .foo import ...`.
            file_pkg: Optional[str] = None
            if owning_prefix:
                rel = py.relative_to(LIB_ROOTS[owning_prefix]).with_suffix("")
                parts = [owning_prefix] + list(rel.parts)
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                # For `from .X import Y` issued from module foo.bar.baz, the
                # package is foo.bar — all but the last path segment.
                file_pkg = ".".join(parts[:-1]) if parts else owning_prefix

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level:
                        # Relative import — resolve against the file's package.
                        if not file_pkg:
                            continue
                        # level=1 means "current package"; level=2 means "parent", etc.
                        pkg_parts = file_pkg.split(".")
                        if node.level - 1 > len(pkg_parts):
                            continue
                        base_parts = pkg_parts[: len(pkg_parts) - (node.level - 1)] if node.level > 1 else pkg_parts
                        if node.module:
                            base_parts = base_parts + node.module.split(".")
                        base_module = ".".join(base_parts)
                    else:
                        base_module = node.module or ""
                    if not base_module:
                        continue
                    if not (base_module in lib_prefixes or base_module.split(".")[0] in lib_prefixes):
                        continue
                    for alias in node.names:
                        qn = f"{base_module}.{alias.name}"
                        resolved = reexport_map.get(qn, qn)
                        counts[resolved][consumer_label] += 1
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top in lib_prefixes:
                            counts[alias.name][consumer_label] += 1
    return {qn: dict(per_consumer) for qn, per_consumer in counts.items()}


def _attach_importers(symbols: list[Symbol], import_counts: dict[str, dict[str, int]]) -> None:
    for sym in symbols:
        # Exact match on qualified_name (e.g. noctusai_lib.api.auth.resolve_sso_role)
        direct = import_counts.get(sym.qualified_name, {})
        # Also credit imports of the parent module (`from noctusai_lib.api.auth import ...`
        # may resolve to any symbol in that module — we can't tell which without
        # deeper analysis, so we only credit when the import target name matches).
        total_products = set(direct.keys())
        total_count = sum(direct.values())
        sym.importers = sorted(total_products)
        sym.import_count = total_count


# ── Duplicate detection: same name in 2+ products, not in lib ─────────

_IGNORE_DUP_NAMES: set[str] = {
    # Names that are too generic to flag (every router has them).
    "router",
    "settings",
    "get_db",
    "configure",
    "main",
    "startup",
    "shutdown",
    "lifespan",
}


def scan_duplicate_candidates(lib_symbols: list[Symbol]) -> list[DuplicateCandidate]:
    """
    Walk every product's `backend/app/services/` and `backend/app/routers/`
    and collect top-level function/class names. If a name appears in 2+
    products AND is not exported by any lib root, it's a candidate for
    absorption into the shared library.
    """
    lib_names = {s.name for s in lib_symbols}

    # name → [(product, file, line, kind)]
    occurrences: dict[str, list[dict]] = defaultdict(list)
    for slug, product_path in _iter_products():
        for sub in ("services", "routers", "dependencies.py", "database.py"):
            target = product_path / "backend" / "app" / sub
            files = [target] if target.is_file() else (
                sorted(target.rglob("*.py")) if target.exists() else []
            )
            for py in files:
                tree = _parse(py)
                if not tree:
                    continue
                rel = py.relative_to(REPO_ROOT)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if not _is_public(node.name):
                            continue
                        if node.name in _IGNORE_DUP_NAMES:
                            continue
                        if node.name in lib_names:
                            continue
                        kind = (
                            "class" if isinstance(node, ast.ClassDef)
                            else "async def" if isinstance(node, ast.AsyncFunctionDef)
                            else "def"
                        )
                        occurrences[node.name].append({
                            "product": slug,
                            "file": str(rel),
                            "line": node.lineno,
                            "kind": kind,
                        })

    candidates: list[DuplicateCandidate] = []
    for name, occ in sorted(occurrences.items()):
        products = {o["product"] for o in occ}
        if len(products) >= 2:
            candidates.append(DuplicateCandidate(
                name=name,
                kind=occ[0]["kind"],
                occurrences=sorted(occ, key=lambda o: (o["product"], o["file"], o["line"])),
            ))
    return candidates


# ── Top-level builder ─────────────────────────────────────────────────

def build_catalog() -> CatalogReport:
    symbols = scan_lib_symbols()
    reexport_map = build_reexport_map()
    import_counts = scan_importers(reexport_map)
    _attach_importers(symbols, import_counts)

    products = [slug for slug, _ in _iter_products()]
    duplicates = scan_duplicate_candidates(symbols)

    orphans = [s for s in symbols if s.import_count == 0]
    single_consumer = [s for s in symbols if len(s.importers) == 1]

    return CatalogReport(
        lib_roots={k: str(v.relative_to(REPO_ROOT)) for k, v in LIB_ROOTS.items()},
        products_scanned=products,
        symbols=symbols,
        orphans=orphans,
        single_consumer=single_consumer,
        duplicates=duplicates,
    )


# ── Markdown renderer ─────────────────────────────────────────────────

def render_markdown(report: CatalogReport) -> str:
    lines: list[str] = []
    lines.append("# NoctusAI Shared Library Catalog")
    lines.append("")
    lines.append("> **Auto-generated** by `python mcp/noctusai/cli.py --catalog`. Do not edit by hand.")
    lines.append("> This artifact replaces the drift-prone handwritten catalog. It answers:")
    lines.append("> *what's in the lib, who uses it, and what's duplicated across products that probably shouldn't be.*")
    lines.append("")
    lines.append(f"- **Lib roots scanned**: " + ", ".join(f"`{k}` ({v})" for k, v in report.lib_roots.items()))
    lines.append(f"- **Products scanned**: " + ", ".join(f"`{p}`" for p in report.products_scanned))
    lines.append(f"- **Totals**: {len(report.symbols)} symbols · "
                 f"{len(report.orphans)} orphans · "
                 f"{len(report.single_consumer)} single-consumer · "
                 f"{len(report.duplicates)} duplicate candidates")
    lines.append("")

    # ── Symbols grouped by module ─────────────────
    lines.append("## Symbols")
    lines.append("")
    by_module: dict[str, list[Symbol]] = defaultdict(list)
    for s in report.symbols:
        by_module[s.module].append(s)

    for module in sorted(by_module):
        lines.append(f"### `{module}`")
        lines.append("")
        lines.append("| Symbol | Kind | Signature | Doc | Used by | Imports |")
        lines.append("|---|---|---|---|---|---|")
        for s in sorted(by_module[module], key=lambda x: x.name):
            used_by = ", ".join(s.importers) if s.importers else "—"
            doc = (s.doc[:80] + "…") if len(s.doc) > 80 else s.doc
            sig = (s.signature[:60] + "…") if len(s.signature) > 60 else s.signature
            lines.append(f"| `{s.name}` | {s.kind} | `{sig}` | {doc} | {used_by} | {s.import_count} |")
        lines.append("")

    # ── Orphans ───────────────────────────────────
    lines.append("## Orphans")
    lines.append("")
    lines.append("Symbols defined in the lib but with **zero importers** across all products.")
    lines.append("Candidates for deletion — but confirm first (may be staged for imminent use,")
    lines.append("or intentionally-public for future consumers).")
    lines.append("")
    if report.orphans:
        lines.append("| Symbol | Kind | Location |")
        lines.append("|---|---|---|")
        for s in report.orphans:
            lines.append(f"| `{s.qualified_name}` | {s.kind} | `{s.location}` |")
    else:
        lines.append("_None. Every public lib symbol is imported somewhere._")
    lines.append("")

    # ── Single-consumer (informational) ───────────
    lines.append("## Single-consumer symbols")
    lines.append("")
    lines.append("Lib symbols imported by exactly **one product**. Informational only —")
    lines.append("a symbol may legitimately live in lib because it encodes a platform-wide")
    lines.append("policy, even if currently only one product exercises it.")
    lines.append("")
    if report.single_consumer:
        lines.append("| Symbol | Used by | Imports |")
        lines.append("|---|---|---|")
        for s in report.single_consumer:
            lines.append(f"| `{s.qualified_name}` | {s.importers[0]} | {s.import_count} |")
    else:
        lines.append("_None._")
    lines.append("")

    # ── Duplication candidates ────────────────────
    lines.append("## Duplication candidates")
    lines.append("")
    lines.append("Public top-level functions/classes with the **same name** in 2+ products,")
    lines.append("and **not** already exported by the shared lib. Strong signal that they")
    lines.append("belong in `noctusai_lib`. Name-based matching has false positives —")
    lines.append("review occurrences before absorbing.")
    lines.append("")
    if report.duplicates:
        for d in report.duplicates:
            lines.append(f"### `{d.name}` ({d.kind})")
            lines.append("")
            for occ in d.occurrences:
                lines.append(f"- `{occ['product']}` — `{occ['file']}:{occ['line']}`")
            lines.append("")
    else:
        lines.append("_None detected by exact-name match._")
    lines.append("")

    return "\n".join(lines)


# ── Public entry points ───────────────────────────────────────────────

def generate_catalog(write: bool = True) -> dict:
    """
    Build the catalog, optionally write the markdown artifact, return a
    structured dict suitable for CLI/MCP output.
    """
    report = build_catalog()
    md = render_markdown(report)
    output_path = None
    if write:
        CATALOG_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_OUTPUT.write_text(md, encoding="utf-8")
        output_path = str(CATALOG_OUTPUT.relative_to(REPO_ROOT))
    return {
        "output_path": output_path,
        "markdown": md if not write else None,
        **report.to_dict(),
    }


def register(server) -> None:
    desc = (
        "Regenerate the shared-library catalog: every lib symbol, its importers, "
        "orphans (zero consumers), and duplication candidates (same name in 2+ "
        "products, not in lib). Writes mcp/noctusai/catalog.md."
    )

    def _catalog(write: bool = True) -> dict:
        return generate_catalog(write=write)

    server.tool(name="noctusai_catalog", description=desc)(_catalog)
    server.tool(
        name="noctus.dev.catalog",
        description="Dotted alias for noctusai_catalog.",
    )(_catalog)


if __name__ == "__main__":
    import sys
    result = generate_catalog(write=True)
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, default=str))
    else:
        summary = result["summary"]
        print(f"Wrote {result['output_path']}")
        print(f"  {summary['total_symbols']} symbols across {summary['products']} products")
        print(f"  {summary['orphans']} orphans · {summary['single_consumer']} single-consumer · "
              f"{summary['duplicate_candidates']} duplicate candidates")
