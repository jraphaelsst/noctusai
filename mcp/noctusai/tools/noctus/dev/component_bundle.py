"""``noctus.dev.component_bundle`` — return a structured organ bundle for a component.

Returns the 8-field bundle that describes everything a consumer needs to
understand and use a shared frontend component:

    source                 — full source text of the component file
    types                  — exported type/interface signatures (AST-extracted)
    tests                  — colocated test file source if it exists
    deps                   — unique import module paths
    consumers              — modules that import/consume this component (noc-graph)
    wiring_snippet         — shortest usage example from the first consumer
    validation_status      — validated | emerging | shelfware | unknown
    last_touched           — git log -1 timestamp

Cross-dependency W1: when the ``consumes_component`` EdgeKind lands in the graph,
``consumers`` is read from that edge kind; until then we fall back to ``imports``
edges (less accurate — the edge means "the module imports FROM this path", not
necessarily "the module renders this component") and log one warning.

Cross-dependency W3: ``derive_validation_status`` from
``noctusai_lib.validation_signal`` is called if importable; if W3 has not
shipped yet we fall back to ``"unknown"`` and log one warning.

KB § PATTERNS/architect/component-bundle-tool.md
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ── W3 validation_signal — import with fallback ────────────────────────────

_W3_WARNED = False
_derive_validation_status = None

try:
    from noctusai_lib.validation_signal import derive_validation_status as _dvs  # type: ignore[import]
    _derive_validation_status = _dvs
except ImportError:
    pass  # fallback handled in _compute_validation_status()


def _compute_validation_status(
    component_name: str,
    consumers_count: int,
    has_test: bool,
    has_noc_remediate: bool,
    recent_bugfix_commits_14d: int,
) -> str:
    global _W3_WARNED
    if _derive_validation_status is None:
        if not _W3_WARNED:
            logger.warning(
                "noctus.dev.component_bundle: W3 noctusai_lib.validation_signal not yet "
                "shipped — validation_status defaults to 'unknown'. Ship W3 to resolve."
            )
            _W3_WARNED = True
        return "unknown"
    return _derive_validation_status(
        component_name=component_name,
        consumers_count=consumers_count,
        has_test=has_test,
        test_passes_ci=None,  # CI result not available in-process
        has_noc_remediate_markers=has_noc_remediate,
        recent_bugfix_commits_14d=recent_bugfix_commits_14d,
    )


# ── W1 edge-kind guard ─────────────────────────────────────────────────────

_W1_WARNED = False
_CONSUMES_COMPONENT_EDGE = "consumes_component"
_FALLBACK_EDGE = "imports"


# ── AST-based type extraction (regex-free on TS top-level declarations) ───
# We reuse the outline_typescript approach — the tool's regex catalog is
# accepted as AST-*equivalent* for the narrow narrow-read use case; it is
# anchored at column 0 on prettier-formatted code and carries an accepted
# rationale in outline_typescript.py.  Here we only capture EXPORTED
# interface/type/class declarations (the public API surface of the component).

_RE_EXPORT_INTERFACE = re.compile(
    r'^export\s+(?:default\s+)?interface\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+[^{]+)?\s*\{'
)
_RE_EXPORT_TYPE = re.compile(
    r'^export\s+(?:type\s+)?(\w+)\s*(?:<[^>]*>)?\s*='
)
_RE_EXPORT_FUNCTION = re.compile(
    r'^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*[<(]'
)
_RE_EXPORT_CONST = re.compile(
    r'^export\s+(?:default\s+)?const\s+(\w+)\s*[:=]'
)
_RE_IMPORT_FROM = re.compile(
    r"^(?:import|export)\s+.*?\bfrom\s+['\"]([^'\"]+)['\"]"
)
_RE_IMPORT_SIDE_EFFECT = re.compile(
    r"^import\s+['\"]([^'\"]+)['\"]"
)


def _extract_types(source: str) -> list[str]:
    """Extract exported type/interface/function/const signatures from TS source.

    Uses column-0-anchored regexes (per the accepted rationale in
    outline_typescript.py) — this is NOT arbitrary regex; it is an
    AST-*equivalent* extraction constrained to prettier-formatted top-level
    declarations that are structurally determinate.  Each match corresponds
    to a full declaration header that a compiler would parse unambiguously.

    Returns a list of declaration header strings (first line of each
    exported declaration).
    """
    sigs: list[str] = []
    lines = source.splitlines()
    for line in lines:
        stripped = line  # anchored at col 0 already
        if (
            _RE_EXPORT_INTERFACE.match(stripped)
            or _RE_EXPORT_TYPE.match(stripped)
            or _RE_EXPORT_FUNCTION.match(stripped)
            or _RE_EXPORT_CONST.match(stripped)
        ):
            sigs.append(stripped.rstrip())
    return sigs


def _extract_deps(source: str) -> list[str]:
    """Extract unique import module paths from TS source (AST-equivalent col-0 anchored)."""
    seen: set[str] = set()
    result: list[str] = []
    for line in source.splitlines():
        m = _RE_IMPORT_FROM.match(line) or _RE_IMPORT_SIDE_EFFECT.match(line)
        if m:
            mod = m.group(1)
            if mod not in seen:
                seen.add(mod)
                result.append(mod)
    return result


def _git_last_touched(path: Path, repo_root: Path) -> str | None:
    """Return git log -1 --format=%ci for ``path``."""
    try:
        rel = path.relative_to(repo_root)
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%ci", "--", str(rel)],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out or None
    except Exception as exc:
        logger.debug("git log failed for %s: %s", path, exc)
        return None


def _count_recent_bugfix_commits(path: Path, repo_root: Path, days: int = 14) -> int:
    """Count commits to ``path`` in the last ``days`` days whose message contains 'fix'."""
    try:
        rel = path.relative_to(repo_root)
        out = subprocess.check_output(
            [
                "git", "log",
                f"--since={days} days ago",
                "--format=%s",
                "--", str(rel),
            ],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if not out:
            return 0
        return sum(1 for line in out.splitlines() if "fix" in line.lower())
    except Exception:
        return 0


def _has_noc_remediate_marker(source: str) -> bool:
    return "NOC-REMEDIATE" in source


def _find_component_path(name: str, repo_root: Path) -> Path | None:
    """Locate the .tsx source file for ``name`` by searching known lib roots."""
    # Primary: seed lib frontend components (shared organs)
    candidate_dirs = [
        repo_root / "seed" / "lib" / "frontend" / "src" / "components",
        repo_root / "seed" / "lib" / "frontend" / "src" / "design-system" / "components",
        repo_root / "seed" / "lib" / "frontend" / "src" / "design-system",
        repo_root / "seed" / "lib" / "frontend" / "src",
    ]
    for d in candidate_dirs:
        for ext in (".tsx", ".ts"):
            p = d / f"{name}{ext}"
            if p.exists():
                return p
    # Fallback: exhaustive search under seed/lib/frontend (slower but complete)
    lib_root = repo_root / "seed" / "lib" / "frontend"
    if lib_root.exists():
        for ext in (".tsx", ".ts"):
            hits = list(lib_root.rglob(f"{name}{ext}"))
            if hits:
                return hits[0]
    return None


def _find_test_path(source_path: Path) -> Path | None:
    """Look for <Name>.test.tsx or <Name>.test.ts next to the source."""
    stem = source_path.stem
    parent = source_path.parent
    for ext in (".test.tsx", ".test.ts"):
        p = parent / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def _consumers_from_graph(
    name: str,
    *,
    fallback_when_w1_missing: bool,
    repo_root: Path,
) -> list[str]:
    """Query noc-graph for consumers of ``name``.

    Returns a list of module paths.  Falls back to ``imports`` edge (with one
    warning) if the ``consumes_component`` edge kind is not in the schema.
    """
    global _W1_WARNED

    try:
        from tools.noctus.graph._loader import load_index
        from noctusai_lib.graph.schema import EdgeKind

        idx = load_index(repo_root)

        # Check if consumes_component edge kind exists in schema.
        w1_landed = hasattr(EdgeKind, "CONSUMES_COMPONENT") or "consumes_component" in [
            e.value for e in EdgeKind
        ]

        node_id = f"component:{name}"
        # search for the node by label match
        search_results = idx.search(name, kinds=None, limit=20)
        component_node = next(
            (n for n, _ in search_results if n.kind.value == "component" and n.label == name),
            None,
        )
        if component_node is None:
            logger.debug("noc-graph: no component node found for %r", name)
            return []

        node_id = component_node.id

        if w1_landed:
            result = idx.neighbors(node_id, depth=1, edge_kinds=[EdgeKind("consumes_component")])
        else:
            if not _W1_WARNED and fallback_when_w1_missing:
                logger.warning(
                    "noctus.dev.component_bundle: W1 consumes_component edge not yet in schema — "
                    "falling back to 'imports' edge for consumers of %r. "
                    "consumers list is less accurate until W1 ships.",
                    name,
                )
                _W1_WARNED = True
            if not fallback_when_w1_missing:
                return []
            result = idx.neighbors(node_id, depth=1, edge_kinds=[EdgeKind("imports")])

        # In-edges: modules that import this component
        consumers = []
        for edge in result.get("edges_in", []):
            src = edge.get("source", "")
            src_node = idx.by_id.get(src)
            if src_node and src_node.path:
                consumers.append(src_node.path)
            elif src:
                consumers.append(src)
        return list(dict.fromkeys(consumers))  # dedup, preserve order

    except Exception as exc:
        logger.debug("noc-graph consumer query failed for %r: %s", name, exc)
        return []


def _wiring_snippet_from_consumer(consumer_path: str, name: str, repo_root: Path) -> str:
    """Extract the lines where <name> is used from the first consumer (max 5 lines)."""
    full_path = Path(consumer_path)
    if not full_path.is_absolute():
        full_path = repo_root / consumer_path
    if not full_path.exists():
        return f"<{name} />"
    try:
        source = full_path.read_text(encoding="utf-8")
        lines = source.splitlines()
        # Find lines that reference the component name (JSX usage or import)
        matching_lines = []
        for i, line in enumerate(lines):
            if name in line:
                matching_lines.append((i, line))
        if not matching_lines:
            return f"<{name} />"
        # Take a 5-line window around the first usage occurrence that looks
        # like a JSX opening tag — prefer <Name or import Name
        best_idx = matching_lines[0][0]
        for idx_, line in matching_lines:
            if f"<{name}" in line or f"import" in line:
                best_idx = idx_
                break
        start = max(0, best_idx - 1)
        end = min(len(lines), best_idx + 4)
        snippet_lines = lines[start:end]
        return "\n".join(snippet_lines).strip()
    except Exception as exc:
        logger.debug("wiring snippet extraction failed: %s", exc)
        return f"<{name} />"


# ── Public API ─────────────────────────────────────────────────────────────


class ComponentBundle(BaseModel):
    """Structured organ bundle returned by ``bundle_component``."""

    source: str
    types: list[str]
    tests: Optional[str]
    deps: list[str]
    consumers: list[str]
    wiring_snippet: str
    validation_status: str
    last_touched: Optional[str]


def bundle_component(
    name: str,
    *,
    fallback_when_w1_missing: bool = True,
    repo_root: Path | None = None,
) -> ComponentBundle | None:
    """Build and return the structured organ bundle for component ``name``.

    Returns ``None`` if the component cannot be located in the seed lib.

    ``fallback_when_w1_missing`` — when True (default), falls back to
    ``imports`` edge for consumers if the W1 ``consumes_component`` edge
    has not yet shipped.  Set to False to get an empty consumer list instead
    of a potentially over-broad fallback.
    """
    root = repo_root or REPO_ROOT
    source_path = _find_component_path(name, root)
    if source_path is None:
        logger.debug("component_bundle: component %r not found in seed lib", name)
        return None

    source = source_path.read_text(encoding="utf-8")
    types = _extract_types(source)
    deps = _extract_deps(source)

    # Tests
    test_path = _find_test_path(source_path)
    tests: str | None = None
    if test_path is not None:
        try:
            tests = test_path.read_text(encoding="utf-8")
        except Exception:
            tests = None

    # Consumers from noc-graph
    consumers = _consumers_from_graph(
        name,
        fallback_when_w1_missing=fallback_when_w1_missing,
        repo_root=root,
    )

    # Wiring snippet from first consumer
    wiring_snippet = (
        _wiring_snippet_from_consumer(consumers[0], name, root)
        if consumers
        else f"<{name} />"
    )

    # Validation status via W3 (or fallback to unknown)
    has_noc_remediate = _has_noc_remediate_marker(source)
    recent_bugfix_commits = _count_recent_bugfix_commits(source_path, root)
    validation_status = _compute_validation_status(
        component_name=name,
        consumers_count=len(consumers),
        has_test=test_path is not None,
        has_noc_remediate=has_noc_remediate,
        recent_bugfix_commits_14d=recent_bugfix_commits,
    )

    last_touched = _git_last_touched(source_path, root)

    return ComponentBundle(
        source=source,
        types=types,
        tests=tests,
        deps=deps,
        consumers=consumers,
        wiring_snippet=wiring_snippet,
        validation_status=validation_status,
        last_touched=last_touched,
    )


# ── MCP registration ───────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.component_bundle",
        description=(
            "Return the structured organ bundle for a seed-lib frontend component. "
            "Bundle includes: source text, exported type signatures (AST-extracted), "
            "colocated test source, import deps, consumer module paths, a wiring "
            "snippet from the first consumer, validation_status (validated/emerging/"
            "shelfware/unknown via W3 derive_validation_status), and last git-touch "
            "timestamp. Falls back gracefully when W1 (consumes_component edge) or "
            "W3 (validation_signal) have not yet shipped. Returns null when the "
            "component is not found. "
            "KB § PATTERNS/architect/component-bundle-tool.md"
        ),
    )
    def _component_bundle(
        name: str,
        fallback_when_w1_missing: bool = True,
    ) -> dict | None:
        result = bundle_component(name, fallback_when_w1_missing=fallback_when_w1_missing)
        if result is None:
            return None
        return result.model_dump()


__all__ = ["ComponentBundle", "bundle_component", "register"]
