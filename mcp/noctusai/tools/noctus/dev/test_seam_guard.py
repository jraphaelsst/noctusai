"""Deny a test-file write that patches our own code, BEFORE it lands.

WHY THIS EXISTS
===============
`check_no_self_monkeypatch` has existed for a long time and works. It is a
COMMIT/CI-time gate, which means the loop it produces is:

    engineer writes the whole test suite with self-patches
      -> hundreds of green tests
        -> commit or CI goes red
          -> rewrite the suite onto real seams

We paid exactly that this session: 16 patched symbols across two certidões
test files, 197 green tests, and a full rework AFTER the work looked done.
The owner's framing was blunt and correct — "we always monkeypatch, then fix
the monkeypatching afterwards" — and the cost is not the gate, it is that the
gate fires at the END of a slice instead of at the first line of it.

CLAUDE.md §1 already names this shape and its remedy, for a different rule:
self-branching is "gated at BOTH ends — the WRITE is denied before it lands
(`primary_write_guard`, PreToolUse hook), the COMMIT is the backstop", with
the explicit reasoning that "a gate at the first expensive consequence lets
work land in the wrong tree anyway". Self-monkeypatching had the backstop and
not the construction half. This is that half.

ONE PREDICATE, TWO ENFORCEMENT POINTS
=====================================
This module deliberately owns NO detection logic. It imports
`_extract_patch_target` / `_resolve_target_via_imports` /
`_classify_patch_target` / `_build_import_map` / `_SELF_PATCH_OK_COMMENT_RE`
from that module and runs them over the content the agent is about to
write. A second, hand-rolled predicate here would drift from the keeper, and
the two ends disagreeing is worse than having only one: an agent blocked by a
guard for something the keeper permits (or vice versa) learns to distrust
both. If the keeper's notion of "ours" changes, this changes with it, for
free.

DELIBERATE LIMITS (stated, not hidden)
======================================
* Covers `Write` / `Edit` / `MultiEdit` on test files. A test file authored
  through a Bash heredoc is NOT caught here; `check_no_self_monkeypatch`
  remains the backstop for that path, which is the point of keeping both.
* Fails OPEN on any internal error. A guard that crashes must never become a
  guard that blocks all work — the keeper still catches what leaks through.
* Honours the same `# self-patch-ok: <reason>` inline escape the keeper
  honours, so a genuinely legitimate patch is written once and accepted at
  both ends. `NOCTUS_ALLOW_SELF_PATCH=1` disables the write-time half
  wholesale for a deliberate bulk operation; the keeper is unaffected by it.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

ALLOW_ENV = "NOCTUS_ALLOW_SELF_PATCH"

#: Tools whose payload carries file content we can evaluate.
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _load_compliance():
    """Import the module that owns the predicate.

    Points at `self_patch_predicate.py`, NOT `compliance.py`. That is
    load-bearing: this runs inside a PreToolUse hook under whatever `python3`
    is on PATH, and `compliance.py` imports pydantic at module scope. Loading
    it here raised `No module named 'pydantic'`, the hook failed OPEN as
    designed, and the guard silently never fired — every unit test still
    passed, because those run under the venv. The leaf module is stdlib-only
    so this import cannot fail that way.
    """
    import importlib.util
    import sys

    here = Path(__file__).resolve()
    spec = importlib.util.spec_from_file_location(
        "noc_self_patch_predicate", here.parent / "self_patch_predicate.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError("cannot load self_patch_predicate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def is_test_file(path: str) -> bool:
    """Does this path look like one of OUR test files?

    Mirrors `_walk_test_files`'s shape (a `tests/` segment under products /
    seed / mcp, excluding vendored trees) without importing it, because that
    helper walks a tree and we have a single path.
    """
    if not path:
        return False
    p = Path(path).as_posix()
    if not p.endswith(".py"):
        return False
    parts = set(Path(p).parts)
    if parts & {"__pycache__", "node_modules", ".venv", "venv", "dist", "build"}:
        return False
    if "/tests/" not in f"/{p}" and not Path(p).name.startswith("test_"):
        return False
    return ("/products/" in f"/{p}") or ("/seed/" in f"/{p}") or ("/mcp/" in f"/{p}")


def _resulting_content(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """The file content as it WOULD be after this tool call, or None.

    For an Edit we reconstruct the whole file rather than parsing the
    fragment: `new_string` on its own is usually not valid Python, and a
    fragment parse would silently see nothing — a false green in the guard
    itself.
    """
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None

    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return None
    try:
        current = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if tool_name == "Edit":
        edits = [tool_input]
    else:  # MultiEdit
        raw = tool_input.get("edits")
        edits = raw if isinstance(raw, list) else []

    for edit in edits:
        if not isinstance(edit, dict):
            continue
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            continue
        if edit.get("replace_all"):
            current = current.replace(old, new)
        else:
            current = current.replace(old, new, 1)
    return current


def find_self_patches(content: str, path: str, repo_root: Path | None = None) -> list[str]:
    """Self-patched dotted targets in `content`, using the KEEPER's predicate.

    Returns [] when the content does not parse — a half-typed file is not a
    violation, and the keeper will see the finished article anyway.
    """
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError:
        return []

    comp = _load_compliance()
    root = repo_root or getattr(comp, "REPO_ROOT", None)
    try:
        connector_prefixes = comp._discover_connector_module_prefixes(root) if root else ()
    except Exception:
        connector_prefixes = ()

    import_map = comp._build_import_map(tree)
    lines = content.splitlines()
    found: list[str] = []

    for node in ast.walk(tree):
        raw_target = comp._extract_patch_target(node)
        if raw_target is None:
            continue
        target = comp._resolve_target_via_imports(raw_target, import_map)
        if comp._classify_patch_target(target, connector_prefixes) != "ours":
            continue
        line_no = getattr(node, "lineno", 0) or 0
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if comp._SELF_PATCH_OK_COMMENT_RE.search(line_text):
            continue
        found.append(f"{target} (line {line_no})")
    return found


def decide(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = None,
    allow_override: bool | None = None,
) -> dict[str, Any] | None:
    """None to allow; a dict with `reason` to deny.

    The reason names the offending symbols AND the remedy — a refusal that
    does not say what to do instead just gets retried a different way.
    """
    if allow_override is None:
        allow_override = os.environ.get(ALLOW_ENV, "") == "1"
    if allow_override:
        return None

    if tool_name not in _WRITE_TOOLS:
        return None
    tool_input = tool_input or {}
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not is_test_file(path):
        return None

    content = _resulting_content(tool_name, tool_input)
    if content is None:
        return None

    targets = find_self_patches(content, path)
    if not targets:
        return None

    listed = "\n".join(f"    - {t}" for t in targets[:8])
    more = "" if len(targets) <= 8 else f"\n    ... and {len(targets) - 8} more"
    return {
        "reason": (
            "REFUSED — this test patches our own code, which means it stops "
            "exercising it (CLAUDE.md §1: no monkey-patching, in production OR "
            "tests).\n\n"
            f"Self-patched symbol(s) in {path}:\n{listed}{more}\n\n"
            "Write it against a real seam instead:\n"
            "  1. Inject the collaborator — an explicit `x=None` parameter the "
            "test passes a fake to (see KB § PATTERNS/backend/di-test-seam.md; "
            "`matricula_service.processar_extracao(transcriber=...)` is the "
            "house example).\n"
            "  2. For a router, override the FastAPI dependency: "
            "`app.dependency_overrides[get_x] = ...`.\n"
            "  3. Patch only EXTERNAL boundaries — an SDK, the network. Those "
            "are not 'ours' and this guard already allows them.\n\n"
            "If this one is genuinely legitimate, say so at the call site with "
            "`# self-patch-ok: <reason>` on the patching line — the commit-time "
            "keeper honours the same escape.\n\n"
            "Do NOT route around this by writing the file through Bash; "
            "`check_no_self_monkeypatch` is the backstop and will fail the "
            "commit."
        ),
        "targets": targets,
        "path": path,
    }
