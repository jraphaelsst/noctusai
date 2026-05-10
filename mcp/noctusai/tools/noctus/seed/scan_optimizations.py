"""``noctus.seed.scan_optimizations`` — intra-file optimization detector.

Third leg of the absorption + fusion + optimization trio. Operates at
a strictly **intra-file** scope: opportunities to delete, inline, or
collapse code WITHIN a single source file. Complements:

- ``scan_repetition`` / ``audit_drift`` / ``report`` — cross-product
  absorption (file-level scope; many copies of the same file across
  products → lift to seed).
- ``scan_fusions`` — cross-tool fusion (function-level scope; many
  similar tool registrations → collapse via mode/kind switch).
- ``scan_optimizations`` (this) — intra-file optimization (line-level
  scope; dead code, single-use helpers, wrappers, verbose docstrings).

Six detectors:

- **dead_function** — module-level ``def`` whose name appears nowhere
  else in the file (no caller, no export, no decorator-target). Likely
  vestigial from an earlier refactor. Action: delete.
- **single_call_helper** — private ``_func`` called from exactly one
  call site in the file. Action: inline, save indirection LoC.
- **wrapper_only** — function whose entire body is
  ``return other_fn(*args, **kwargs)`` (no logic added). Action:
  unwrap (rename calls to the inner fn directly).
- **verbose_tool_description** — ``@server.tool(description=...)``
  where the description string exceeds ``description_max_chars``
  (default 240) — agents rarely benefit from descriptions longer than
  this; the cost is real (every schema fetch loads it). Action: trim.
- **oversized_shim_docstring** — decorated FastMCP shim function whose
  docstring is more than ``shim_docstring_max_lines`` (default 2)
  lines. The impl function's docstring is the authoritative one;
  shim docstrings are duplication. Action: trim or remove.
- **lone_constant_only_used_locally** — UPPER_SNAKE module-level
  constant referenced from exactly one location in the file. Action:
  inline at the call site.

All detectors are read-only static analysis via stdlib ``ast``. Each
finding carries an ``estimated_savings_loc`` estimate; the summary
totals them with caveats about overlap (deleting a dead function
that calls a single-call helper would double-count).
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

logger = logging.getLogger(__name__)


# Names we don't treat as "dead" even if they have no in-file references —
# they're dispatched by external machinery (FastMCP register hooks, pytest,
# ABC contracts).
_FRAMEWORK_NAMES: frozenset[str] = frozenset({
    "register", "register_all", "main", "setup", "teardown",
    "pytest_configure", "pytest_collection_modifyitems",
    "configure", "create_app",
})


_DEFAULT_TOOLS_DIR = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus"


# ─── AST helpers ───────────────────────────────────────────────────────────


def _func_lines(node: ast.FunctionDef) -> int:
    if not node.end_lineno:
        return 1
    return max(node.end_lineno - node.lineno + 1, 1)


def _name_references(tree: ast.Module) -> dict[str, int]:
    """Count every ``Name`` / ``Attribute`` reference in the module.
    Returns a dict mapping referenced name → count.
    """
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            counts[node.id] = counts.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            counts[node.attr] = counts.get(node.attr, 0) + 1
    return counts


def _all_names_referenced(tree: ast.Module) -> set[str]:
    """Return EVERY name referenced anywhere in the module — Names,
    Attribute targets, ImportFrom aliases (incl. ``as`` rebindings),
    and decorator targets. Used to build a tree-wide reference set
    across all files so cross-file callers count toward "is this
    function dead?".
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # `import a.b.c` introduces refs to every segment.
                for seg in alias.name.split("."):
                    names.add(seg)
                if alias.asname:
                    names.add(alias.asname)
    return names


def _build_tree_wide_refs(files: list[Path]) -> set[str]:
    """First-pass scan: aggregate every referenced name across every .py
    in the tree. Used by ``dead_function`` to avoid false positives on
    public functions that are imported by sibling modules.
    """
    out: set[str] = set()
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        out |= _all_names_referenced(tree)
    return out


def _module_level_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Top-level FunctionDef nodes (not nested inside classes / functions)."""
    return [n for n in tree.body if isinstance(n, ast.FunctionDef)]


def _module_level_constants(tree: ast.Module) -> list[tuple[str, ast.Assign]]:
    """Top-level UPPER_SNAKE constants. Returns list of (name, assign_node)."""
    out: list[tuple[str, ast.Assign]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not target.id.isupper():
            continue
        out.append((target.id, node))
    return out


def _docstring_lines(node: ast.FunctionDef) -> int:
    """Number of lines in the function's docstring (0 if absent)."""
    doc = ast.get_docstring(node)
    if not doc:
        return 0
    return len(doc.splitlines())


def _is_decorated_tool_shim(node: ast.FunctionDef) -> bool:
    """A FastMCP shim is a function decorated with ``@server.tool(...)``."""
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        func = deco.func
        if isinstance(func, ast.Attribute) and func.attr == "tool":
            return True
    return False


def _wrapper_target(node: ast.FunctionDef) -> str | None:
    """If the function's entire body is a no-op forwarding call ``return
    other_fn(*params)`` (where the call's args / kwargs mirror the
    function's params 1:1), return the called name. Otherwise None.

    A genuine wrapper has parameters AND forwards them unchanged; a
    parameterless ``def f(): return X.method(...)`` is a NAMED operation,
    not a wrapper, even though its body is a single Return(Call(...)).
    Skip those.

    Receiver-of-attribute must itself be a ``Name`` — chained calls like
    ``datetime.now().isoformat(...)`` are NOT wrappers (they compose
    operations, not forward them).
    """
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if len(body) != 1:
        return None
    stmt = body[0]
    if not isinstance(stmt, ast.Return) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    param_names = [a.arg for a in node.args.args]
    # Zero-param "wrappers" are usually named-operation factories
    # (e.g. `_now_iso()` returning a constructed timestamp). Skip.
    if not param_names:
        return None
    # The call must pass through the function's params unchanged.
    if len(call.args) != len(param_names):
        if call.args:
            return None
        if [k.arg for k in call.keywords] != param_names:
            return None
    else:
        for arg, name in zip(call.args, param_names):
            if not (isinstance(arg, ast.Name) and arg.id == name):
                return None
    # Attribute receiver must be a Name — chained calls like
    # `obj.method().chain()` aren't wrappers (they compose operations).
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        if not isinstance(call.func.value, ast.Name):
            return None
        return call.func.attr
    return None


def _tool_description_chars(node: ast.FunctionDef) -> tuple[int, str | None] | None:
    """If the function carries an ``@server.tool(description=...)`` decorator,
    return ``(char_count, tool_name_or_none)``. Else None."""
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        func = deco.func
        if not (isinstance(func, ast.Attribute) and func.attr == "tool"):
            continue
        descr_chars = 0
        tool_name: str | None = None
        for kw in deco.keywords:
            if kw.arg == "description":
                value = _string_literal(kw.value)
                if value is not None:
                    descr_chars = len(value)
            elif kw.arg == "name":
                value = _string_literal(kw.value)
                if value is not None:
                    tool_name = value
        return descr_chars, tool_name
    return None


def _string_literal(node: ast.AST) -> str | None:
    """Resolve a Constant or implicitly-concatenated string-tuple."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_literal(node.left)
        right = _string_literal(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.Tuple):
        parts: list[str] = []
        for elt in node.elts:
            v = _string_literal(elt)
            if v is None:
                return None
            parts.append(v)
        return "".join(parts)
    return None


def _walk_python_files(root: Path) -> list[Path]:
    """Yield every ``.py`` file under ``root`` (skipping __pycache__,
    .venv, etc.)."""
    if not root.is_dir():
        return []
    skip_dirs = {"__pycache__", ".venv", "venv", "node_modules", ".git",
                 "dist", "build", ".mypy_cache", ".pytest_cache"}
    out: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        out.append(path)
    return sorted(out)


# ─── Detectors ─────────────────────────────────────────────────────────────


def _scan_one_file(
    path: Path, tree_wide_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Run every detector on a single file. Returns flat list of findings.

    ``tree_wide_refs`` (optional) is the union of every referenced name
    across the entire tools tree. ``dead_function`` uses it to avoid
    false-positives on public functions imported by sibling modules.
    Pass None for legacy single-file behaviour.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    references = _name_references(tree)
    if tree_wide_refs is None:
        tree_wide_refs = set()
    funcs = _module_level_functions(tree)
    rel_path = str(path)
    findings: list[dict[str, Any]] = []

    # ─── Detector 1: dead_function ─────────────────────────────────────
    # Module-level def whose name is never referenced anywhere in the file
    # (no caller, no decorator-target, no export). NOTE: FunctionDef.name
    # is a string attribute — NOT an ast.Name node — so the def itself
    # does NOT contribute to references[func.name]. Reference count of 0
    # means truly no in-file caller.
    func_names = {f.name for f in funcs}
    for func in funcs:
        if func.name in _FRAMEWORK_NAMES:
            continue
        if func.name.startswith("__"):
            continue  # dunders are framework-dispatched
        # Decorated functions are presumed used by their decorator
        # framework (e.g. @app.get('/foo')).
        if func.decorator_list:
            continue
        ref_count = references.get(func.name, 0)
        if ref_count > 0:
            continue
        # Cross-file check: skip if any sibling module references the
        # name (likely an exported helper). This is a strong signal —
        # public functions almost always survive this filter.
        if func.name in tree_wide_refs:
            continue
        loc = _func_lines(func)
        findings.append({
            "detector": "dead_function",
            "file": rel_path,
            "line": func.lineno,
            "name": func.name,
            "estimated_savings_loc": loc,
            "severity": "high" if loc >= 10 else "warning",
            "suggestion": (
                f"Function `{func.name}` ({loc} LoC) has no in-file "
                "references. Verify cross-module callers via grep, then delete."
            ),
        })

    # ─── Detector 2: single_call_helper ─────────────────────────────────
    # Private (leading-underscore) functions called from exactly one place
    # in the file AND small enough that inlining doesn't hurt readability.
    # Cap at 25 LoC — beyond that, the helper is doing real cognitive work
    # and the name carries value even if there's only one call site.
    # Realistic savings per inline: ~3 LoC (def line + signature + return),
    # NOT the full body (which moves to the caller, not deleted).
    SINGLE_CALL_MAX_LOC = 25
    SINGLE_CALL_SAVINGS = 3
    for func in funcs:
        if not func.name.startswith("_") or func.name.startswith("__"):
            continue
        if func.decorator_list:
            continue
        ref_count = references.get(func.name, 0)
        if ref_count != 1:
            continue
        loc = _func_lines(func)
        if loc < 3 or loc > SINGLE_CALL_MAX_LOC:
            # <3 LoC: barely worth inlining. >25 LoC: helper carries
            # cognitive value; inlining hurts readability.
            continue
        findings.append({
            "detector": "single_call_helper",
            "file": rel_path,
            "line": func.lineno,
            "name": func.name,
            "estimated_savings_loc": SINGLE_CALL_SAVINGS,
            "severity": "warning" if loc <= 10 else "info",
            "suggestion": (
                f"Helper `{func.name}` ({loc} LoC) is called from exactly "
                "one place. Inlining at the call site saves ~3 LoC of "
                "indirection (only beneficial below 10 LoC; judgment call "
                "between 11-25)."
            ),
        })

    # ─── Detector 3: wrapper_only ──────────────────────────────────────
    # Functions whose body is just `return other_fn(*params)` add no value.
    for func in funcs:
        if func.decorator_list:
            # Decorated wrappers (e.g. @server.tool shims) are intentional.
            continue
        target = _wrapper_target(func)
        if target is None:
            continue
        loc = _func_lines(func)
        findings.append({
            "detector": "wrapper_only",
            "file": rel_path,
            "line": func.lineno,
            "name": func.name,
            "estimated_savings_loc": loc,
            "severity": "warning",
            "suggestion": (
                f"`{func.name}` is a no-op wrapper around `{target}`. "
                "Rename callers to use the inner function directly, then delete."
            ),
        })

    # ─── Detector 4: verbose_tool_description ──────────────────────────
    # @server.tool(description=...) with a long string. Agents pay this
    # cost on every schema load.
    for func in funcs + [
        n for parent in funcs for n in ast.walk(parent)
        if isinstance(n, ast.FunctionDef) and n is not parent
    ]:
        meta = _tool_description_chars(func)
        if meta is None:
            continue
        chars, tool_name = meta
        DESCR_MAX = 240
        if chars <= DESCR_MAX:
            continue
        # Estimate savings: every 80 chars beyond the limit ≈ 1 LoC of
        # multi-line string.
        excess = chars - DESCR_MAX
        savings = max(excess // 80, 1)
        findings.append({
            "detector": "verbose_tool_description",
            "file": rel_path,
            "line": func.lineno,
            "name": tool_name or func.name,
            "estimated_savings_loc": savings,
            "severity": "info",
            "suggestion": (
                f"Tool `{tool_name or func.name}` description is {chars} "
                f"chars (limit {DESCR_MAX}). Trim — agents pay the cost on "
                "every schema load."
            ),
        })

    # ─── Detector 5: oversized_shim_docstring ──────────────────────────
    # FastMCP shim functions with their own multi-line docstring duplicate
    # the impl function's docstring.
    for parent in funcs:
        for inner in ast.walk(parent):
            if not isinstance(inner, ast.FunctionDef) or inner is parent:
                continue
            if not _is_decorated_tool_shim(inner):
                continue
            doc_lines = _docstring_lines(inner)
            if doc_lines <= 2:
                continue
            findings.append({
                "detector": "oversized_shim_docstring",
                "file": rel_path,
                "line": inner.lineno,
                "name": inner.name,
                "estimated_savings_loc": doc_lines,
                "severity": "info",
                "suggestion": (
                    f"Shim `{inner.name}` has a {doc_lines}-line docstring. "
                    "Trim to ≤2 lines or delete (the impl function's "
                    "docstring + the @server.tool description are the "
                    "authoritative surfaces)."
                ),
            })

    # ─── Detector 6: lone_constant ─────────────────────────────────────
    # UPPER_SNAKE module-level constant referenced from exactly one place
    # in the file. (Same as functions: the assign target's `Name(ctx=Store)`
    # is counted by ast.walk too, so the assign itself contributes 1 ref;
    # exactly one external use = ref_count == 2.)
    for name, assign in _module_level_constants(tree):
        ref_count = references.get(name, 0)
        if ref_count != 2:
            continue
        # Skip __all__, __version__, etc. — module-protocol constants.
        if name.startswith("__"):
            continue
        loc = (assign.end_lineno or assign.lineno) - assign.lineno + 1
        findings.append({
            "detector": "lone_constant",
            "file": rel_path,
            "line": assign.lineno,
            "name": name,
            "estimated_savings_loc": loc,
            "severity": "info",
            "suggestion": (
                f"Constant `{name}` ({loc} LoC) is referenced from exactly "
                "one place. Inline at the call site to remove indirection."
            ),
        })

    return findings


# ─── Public API ────────────────────────────────────────────────────────────


_SEVERITY_ORDER: dict[str, int] = {"high": 0, "warning": 1, "info": 2}

_VALID_DETECTORS: frozenset[str] = frozenset({
    "dead_function", "single_call_helper", "wrapper_only",
    "verbose_tool_description", "oversized_shim_docstring", "lone_constant",
})


def scan_optimizations(
    *,
    tools_dir: Path | None = None,
    max_findings: int | None = None,
    include_detectors: list[str] | None = None,
    min_severity: str = "info",
) -> dict:
    """Detect intra-file optimization opportunities across a tree of .py files.

    Args:
        tools_dir: Override (test seam). Defaults to ``REPO_ROOT/mcp/noctusai/tools/noctus``.
        max_findings: Optional cap on the returned findings list.
        include_detectors: Optional whitelist of detector names. Subset of
            ``["dead_function", "single_call_helper", "wrapper_only",
            "verbose_tool_description", "oversized_shim_docstring",
            "lone_constant"]``. None = run all.
        min_severity: Drop findings below this level. Default "info"
            keeps everything; "warning" drops info-only; "high" keeps
            only the highest-confidence opportunities.

    Returns:
        ``{
          "scanned_files": int,
          "findings": [
            {
              "detector": str,            # which detector surfaced this
              "file": str,
              "line": int,
              "name": str,                # function / constant / tool name
              "estimated_savings_loc": int,
              "severity": "high" | "warning" | "info",
              "suggestion": str,          # action text
            },
            ...
          ],
          "summary": {
            "total_findings": int,
            "by_detector": {detector: count},
            "by_severity": {severity: count},
            "estimated_savings_loc_total": int,   # UPPER BOUND — overlap possible
            "by_file": {file: count},
          },
        }``
    """
    base = tools_dir if tools_dir is not None else _DEFAULT_TOOLS_DIR
    if include_detectors is not None:
        unknown = [d for d in include_detectors if d not in _VALID_DETECTORS]
        if unknown:
            return {
                "scanned_files": 0,
                "findings": [],
                "summary": {
                    "total_findings": 0,
                    "by_detector": {},
                    "by_severity": {},
                    "estimated_savings_loc_total": 0,
                    "by_file": {},
                    "error": (
                        f"unknown detector(s): {unknown}. Valid: "
                        f"{sorted(_VALID_DETECTORS)}"
                    ),
                },
            }
    if min_severity not in _SEVERITY_ORDER:
        return {
            "scanned_files": 0,
            "findings": [],
            "summary": {
                "total_findings": 0,
                "by_detector": {},
                "by_severity": {},
                "estimated_savings_loc_total": 0,
                "by_file": {},
                "error": (
                    f"invalid min_severity {min_severity!r}; "
                    f"valid: {sorted(_SEVERITY_ORDER)}"
                ),
            },
        }

    files = _walk_python_files(base)
    severity_floor = _SEVERITY_ORDER[min_severity]
    detector_filter = (
        frozenset(include_detectors) if include_detectors is not None else None
    )

    # Pre-pass: build the tree-wide reference set so dead_function can
    # skip names imported by sibling modules.
    tree_wide_refs = _build_tree_wide_refs(files)

    all_findings: list[dict[str, Any]] = []
    for f in files:
        for finding in _scan_one_file(f, tree_wide_refs=tree_wide_refs):
            if detector_filter and finding["detector"] not in detector_filter:
                continue
            if _SEVERITY_ORDER.get(finding["severity"], 99) > severity_floor:
                continue
            all_findings.append(finding)

    # Sort: severity asc (high first), then savings desc, then file path,
    # then line number.
    all_findings.sort(
        key=lambda f: (
            _SEVERITY_ORDER.get(f["severity"], 99),
            -f["estimated_savings_loc"],
            f["file"],
            f["line"],
        )
    )

    by_detector: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_file: dict[str, int] = {}
    savings_total = 0
    for f in all_findings:
        by_detector[f["detector"]] = by_detector.get(f["detector"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
        rel = str(Path(f["file"]).relative_to(base)) if Path(f["file"]).is_relative_to(base) else f["file"]
        by_file[rel] = by_file.get(rel, 0) + 1
        savings_total += f["estimated_savings_loc"]

    summary = {
        "total_findings": len(all_findings),
        "by_detector": by_detector,
        "by_severity": by_severity,
        "estimated_savings_loc_total": savings_total,
        "by_file": by_file,
    }

    if max_findings is not None and max_findings >= 0:
        all_findings = all_findings[:max_findings]

    return {
        "scanned_files": len(files),
        "findings": all_findings,
        "summary": summary,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.scan_optimizations",
        description=(
            "Intra-file optimization detector — third leg of the absorption "
            "+ fusion + optimization trio. Scans every .py for dead "
            "functions, single-call helpers, no-op wrappers, verbose tool "
            "descriptions, oversized shim docstrings, and lone constants. "
            "min_severity 'high' / 'warning' / 'info' caps the queue. "
            "Read-only."
        ),
    )
    def _scan_optimizations(
        max_findings: int | None = None,
        include_detectors: list[str] | None = None,
        min_severity: str = "info",
    ) -> dict:
        return scan_optimizations(
            max_findings=max_findings,
            include_detectors=include_detectors,
            min_severity=min_severity,
        )
