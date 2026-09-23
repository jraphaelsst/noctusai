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

A GATE IS A SAFETY NET, NOT A WALL
===================================
Two holes shipped with the first version, both because the guard judged more
than the agent had just written:

* It scanned the WHOLE resulting file, so a PRE-EXISTING violation anywhere
  in a test file blocked EVERY subsequent edit to that file — including a
  fix, including something unrelated. That pushes an engineer to park new
  tests in a sibling file rather than touch the debt (2026-09-14 auto-
  improvement, seed/lib/backend/tests/integrations/documents/test_extractor.py).
* It only fired on `Write`/`Edit`/`MultiEdit`, so a test file authored
  through a Bash heredoc (`cat > tests/test_x.py <<'EOF' ... EOF`) bypassed it
  entirely. Three self-monkeypatch violations reached CI that way on
  2026-09-07 and were only caught by the commit-time keeper — the exact
  "gated at both ends" claim this guard exists to make true.

The fix for both is the same shape: judge only what THIS call actually
introduces — the lines an `Edit`/`Write` adds relative to what was already on
disk, or the body of a heredoc a `Bash` call writes into a test path — never
a violation that was already sitting in the file untouched. A safety net that
also catches things nobody threw stops being trusted as a net.

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
free. `find_self_patches` is that one predicate for BOTH the Edit/Write path
and the Bash-heredoc path below — the second does not re-derive it.

DELIBERATE LIMITS (stated, not hidden)
======================================
* Covers `Write` / `Edit` / `MultiEdit` diff-scoped, and `Bash` heredoc/
  redirect writes into a test path. A test file produced by some OTHER shell
  construct (`printf`, `python3 -c "open(...).write(...)"`, `sed -i`) is NOT
  caught here; `check_no_self_monkeypatch` remains the backstop for that path
  and for anything the heuristics below miss — the Bash leg can only ever be
  a good parser of an arbitrary shell command, never a proof.
* The Bash leg handles ONE heredoc per opening line (`cmd > target <<TAG`).
  Two heredocs stacked on the same line are not resolved; the commit-time
  keeper is the backstop.
* Fails OPEN on any internal error. A guard that crashes must never become a
  guard that blocks all work — the keeper still catches what leaks through.
* Honours the same `# self-patch-ok: <reason>` inline escape the keeper
  honours, so a genuinely legitimate patch is written once and accepted at
  both ends. `NOCTUS_ALLOW_SELF_PATCH=1` disables the write-time half
  wholesale for a deliberate bulk operation; the keeper is unaffected by it.
"""
from __future__ import annotations

import ast
import difflib
import os
from pathlib import Path
from typing import Any

ALLOW_ENV = "NOCTUS_ALLOW_SELF_PATCH"

#: Tools whose payload carries file content we can evaluate.
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _load_module(filename: str, module_name: str):
    """Load a sibling stdlib-only module by file path, not package import.

    This file runs inside a PreToolUse hook under whatever `python3` is on
    PATH, loaded standalone via `spec_from_file_location` — it has no package
    context, so `from . import X` is not available. Shared by
    `_load_compliance` and `_load_primary_write_guard` so there is exactly
    one loading strategy, not two that could drift.
    """
    import importlib.util
    import sys

    here = Path(__file__).resolve()
    spec = importlib.util.spec_from_file_location(module_name, here.parent / filename)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_compliance():
    """Import the module that owns the self-patch predicate.

    Points at `self_patch_predicate.py`, NOT `compliance.py`. That is
    load-bearing: `compliance.py` imports pydantic at module scope. Loading
    it here raised `No module named 'pydantic'`, the hook failed OPEN as
    designed, and the guard silently never fired — every unit test still
    passed, because those run under the venv. The leaf module is stdlib-only
    so this import cannot fail that way.
    """
    return _load_module("self_patch_predicate.py", "noc_self_patch_predicate")


def _load_primary_write_guard():
    """Import `primary_write_guard.py` for its heredoc/redirect parsing.

    Reuses `_HEREDOC_RE` and `_redirect_targets` instead of re-deriving a
    second shell parser — two parsers that quietly disagree on what a
    heredoc's write target is would be worse than one used twice. That
    module is documented stdlib-only and fast to import for the same reason
    this one is.
    """
    return _load_module("primary_write_guard.py", "noc_primary_write_guard_for_seam")


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


def _read_current(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _old_and_new_content(tool_name: str, tool_input: dict[str, Any]) -> tuple[str | None, str | None]:
    """(old_content, new_content) as they stand BEFORE / AFTER this call.

    `old_content` is `None` when there is nothing on disk to diff against — a
    brand-new `Write` — in which case the whole new file counts as added and
    `decide` skips line-scoping entirely (everything IS new).

    For an Edit/MultiEdit we reconstruct the whole file rather than parsing
    `new_string` alone: a fragment is usually not valid Python on its own,
    and a fragment parse would silently see nothing — a false green in the
    guard itself.
    """
    if tool_name == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str):
            return None, None
        path = tool_input.get("file_path")
        old = _read_current(path) if isinstance(path, str) else None
        return old, content

    path = tool_input.get("file_path")
    if not isinstance(path, str):
        return None, None
    current = _read_current(path)
    if current is None:
        return None, None

    if tool_name == "Edit":
        edits = [tool_input]
    else:  # MultiEdit
        raw = tool_input.get("edits")
        edits = raw if isinstance(raw, list) else []

    new_content = current
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            continue
        if edit.get("replace_all"):
            new_content = new_content.replace(old, new)
        else:
            new_content = new_content.replace(old, new, 1)
    return current, new_content


def _added_lines(old_content: str, new_content: str) -> set[str]:
    """Line texts in `new_content` that are an insert or a replace vs
    `old_content` — never a line simply carried over untouched.

    A LINE-level diff on purpose: "a simple line-set difference is fine" is
    the whole point of diff-scoped judgement (KB §
    PATTERNS/compliance/testing.md) — a pre-existing violation elsewhere in
    the file must never block an unrelated edit, and `SequenceMatcher`'s
    opcodes are the cheapest correct way to tell "already there" from "just
    introduced" without a real AST diff. `autojunk=False` because a test file
    with many blank/boilerplate lines must not get its diff heuristically
    degraded.
    """
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    added: set[str] = set()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            added.update(new_lines[j1:j2])
    return added


def find_self_patches(
    content: str,
    path: str,
    repo_root: Path | None = None,
    only_lines: set[str] | None = None,
) -> list[str]:
    """Self-patched dotted targets in `content`, using the KEEPER's predicate.

    Returns [] when the content does not parse — a half-typed file is not a
    violation, and the keeper will see the finished article anyway.

    `only_lines`, when given, restricts the result to violations whose
    statement (its full `lineno..end_lineno` span, so a multi-line
    `monkeypatch.setattr(...)` call is judged as one unit) touches at least
    one line in that set. `None` means "judge everything" — the shape every
    existing caller relies on (a brand-new file, or the Bash-heredoc path,
    where the whole body IS what this call introduces).
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
        end_line_no = getattr(node, "end_lineno", line_no) or line_no
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if comp._SELF_PATCH_OK_COMMENT_RE.search(line_text):
            continue
        if only_lines is not None:
            span = lines[max(line_no - 1, 0):max(end_line_no, line_no)]
            if not any(text in only_lines for text in span):
                continue
        found.append(f"{target} (line {line_no})")
    return found


def _bash_test_file_writes(command: str, pwg: Any) -> list[tuple[str, str]]:
    """(target_path, heredoc_body) for every heredoc in `command` that writes
    at a path `is_test_file()` recognises — the bypass that reaches a test
    file without ever going through Write/Edit/MultiEdit.

    Walks lines like `pwg._strip_heredocs` does (same terminator regex, same
    `<<-` handling), but KEEPS the body instead of dropping it, and resolves
    the write target from the portion of the opening line before `<<` via
    `pwg._redirect_targets` — the same quote-aware scanner the primary-write
    guard uses, so a quoted target (`cat > "tests/x.py" <<EOF`) resolves
    identically in both guards.
    """
    lines = command.split("\n")
    out: list[tuple[str, str]] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        match = pwg._HEREDOC_RE.search(line)
        if match is None:
            i += 1
            continue
        tag = match.group(2)
        head = line[: match.start()]
        targets = pwg._redirect_targets(head)
        target_path = targets[-1] if targets else None

        i += 1
        body_lines: list[str] = []
        while i < n and lines[i].strip() != tag:
            body_lines.append(lines[i])
            i += 1
        i += 1  # consume the terminator line itself

        if target_path and is_test_file(target_path):
            out.append((target_path, "\n".join(body_lines)))
    return out


def _decide_bash(command: str) -> dict[str, Any] | None:
    pwg = _load_primary_write_guard()
    for target_path, body in _bash_test_file_writes(command, pwg):
        targets = find_self_patches(body, target_path)
        if targets:
            return _refusal(target_path, targets)
    return None


def _refusal(path: str, targets: list[str]) -> dict[str, Any]:
    """The reason names the offending symbols AND the remedy — a refusal that
    does not say what to do instead just gets retried a different way."""
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


def decide(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = None,
    allow_override: bool | None = None,
) -> dict[str, Any] | None:
    """None to allow; a dict with `reason` to deny.

    For `Write`/`Edit`/`MultiEdit` this judges only what THIS call adds —
    diff-scoped against whatever is already on disk — so a pre-existing
    violation elsewhere in the file never blocks an unrelated edit, and an
    edit that removes the only violation is allowed. For `Bash`, a heredoc
    or redirect that writes a test file is resolved and its body is judged
    in full through the same predicate.
    """
    if allow_override is None:
        allow_override = os.environ.get(ALLOW_ENV, "") == "1"
    if allow_override:
        return None

    tool_input = tool_input or {}

    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command:
            return None
        return _decide_bash(command)

    if tool_name not in _WRITE_TOOLS:
        return None
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not is_test_file(path):
        return None

    old_content, new_content = _old_and_new_content(tool_name, tool_input)
    if new_content is None:
        return None

    only_lines = _added_lines(old_content, new_content) if old_content is not None else None
    targets = find_self_patches(new_content, path, only_lines=only_lines)
    if not targets:
        return None

    return _refusal(path, targets)
