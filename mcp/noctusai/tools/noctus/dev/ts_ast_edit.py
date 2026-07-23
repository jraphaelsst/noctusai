"""`noctus.dev.ts_ast_rename_symbol` — a REAL ts-morph AST edit for TypeScript.

WHY this tool exists
---------------------
Finding #7 (2026-07-23 session, memory `feedback_ast_first_rule_was_unenforced`):
the platform's AST-first rule ("if a compiler/type-checker parses the file,
edit it via libcst / ts-morph, never regex" — `KB § PATTERNS/common/ast.md`)
was **unenforceable for TypeScript** because no ts-morph tooling was
installed anywhere in the repo. `outline_typescript.py` deliberately stays
regex-based (read-only structural outline, no Node spawn — see its own
module docstring), so it never exercised the gap; every actual TS *edit*
in this repo has, until now, happened via `Edit`/string-replace, which
worked only because the diffs stayed small and safe by luck, not by
construction. This module is the first `noctus.dev.*` tool that performs
a genuine AST-driven TypeScript *write*.

WHERE ts-morph lives
---------------------
`mcp/noctusai/node/` — a **dedicated Node helper directory**, its own
`package.json` (`ts-morph` as the only dependency) + `node_modules/`
(gitignored, matches the existing global `node_modules` ignore rule).
Deliberately NOT:
  - a product's `frontend/` — that's product-runtime FE code, not
    dev-tooling; ts-morph is a devDependency of the *tooling*, not the
    shipped app.
  - `templates/product-seed/` — same reasoning; this isn't something a
    scaffolded product should inherit.
  - the MCP server's own `pyproject.toml`/`requirements.txt` — Node deps
    don't belong in a Python dependency manifest.
`outline_typescript.py`'s docstring already anticipated this shape
("Node spawn" as the thing it explicitly avoids for the *read-only* path)
— `mcp/noctusai/node/` is that spawn target for the *write* path.

HOW the edit happens
---------------------
`ts_ast_rename_symbol()` shells out to `node mcp/noctusai/node/ts_ast_edit.mjs`
(one JSON payload on stdin, one JSON result on stdout — see that file's
docstring for the op contract). The Node script loads the target file into
a real ts-morph `Project`, resolves the top-level declaration by name,
computes `findReferencesAsNodes()` BEFORE renaming (an honest count of what
actually changed — a regex `s/old/new/g` cannot report this truthfully:
it "succeeds" against 0 real references or over-matches unrelated
same-spelled text in strings/comments/JSX attrs), calls `.rename()`
(scope-aware — respects the real binder, not text matching), and writes
back via `SourceFile#saveSync()` (formatting-preserving).

Honest-error contract (no silent errors, `KB § 01-PHILOSOPHY.md`):
  - `node` not on PATH → `status="node_unavailable"`, `ok=False`. The
    caller (or a test) degrades explicitly; nothing silently no-ops.
  - Node script exits non-zero (a genuine crash, not a typed failure) →
    `status="node_crashed"`, stderr surfaced in `error`.
  - Node script's own typed failures (`parse_error`, `symbol_not_found`,
    `bad_request`, `unknown_op`, `rename_failed`, ...) pass through
    verbatim — the Python side does not re-interpret them.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from settings import REPO_ROOT  # noqa: E402  (path constant)
from workspace import resolve_caller_root  # noqa: E402

# Per `feedback_mcp_path_constants_from_settings.md` — resolve off the
# `REPO_ROOT` settings constant, never `Path(__file__).parents[N]` (that
# broke 18 modules the last time the MCP toolkit's directory depth shifted).
_NODE_HELPER_DIR = REPO_ROOT / "mcp" / "noctusai" / "node"
_TS_AST_EDIT_SCRIPT = _NODE_HELPER_DIR / "ts_ast_edit.mjs"

_SUBPROCESS_TIMEOUT_SECONDS = 30


@dataclass
class TsAstEditResult:
    ok: bool
    status: str
    path: str
    old_name: Optional[str] = None
    new_name: Optional[str] = None
    references_updated: Optional[int] = None
    declaration_kind: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "path": self.path,
            "old_name": self.old_name,
            "new_name": self.new_name,
            "references_updated": self.references_updated,
            "declaration_kind": self.declaration_kind,
            "error": self.error,
        }


def _resolve_target_path(path: str, worktree_path: Optional[str]) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    root = resolve_caller_root(worktree_path)
    return root / p


def _run_node_op(payload: dict) -> tuple[bool, dict, str]:
    """Run `ts_ast_edit.mjs` with `payload` on stdin.

    Returns ``(process_ok, result_dict, stderr)``. ``process_ok`` is False
    only for a genuine crash (non-zero exit / unparseable stdout) — a
    *typed* failure from the Node script (``ok: false`` in its own JSON)
    still returns ``process_ok=True`` with that JSON as ``result_dict``,
    since the subprocess itself ran fine and reported honestly.
    """
    proc = subprocess.run(
        ["node", str(_TS_AST_EDIT_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        return False, {}, stderr
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return False, {}, f"non-JSON stdout from ts_ast_edit.mjs: {exc}; stdout={proc.stdout!r}"
    return True, result, stderr


def ts_ast_rename_symbol(
    path: str,
    old_name: str,
    new_name: str,
    worktree_path: Optional[str] = None,
) -> TsAstEditResult:
    """Rename a top-level TS/TSX symbol AND every reference to it, via ts-morph.

    Covers function / class / interface / type-alias / const|let|var
    top-level declarations (the same set `outline_typescript.py` treats as
    "top-level structural declarations"). Scope-aware: a string literal,
    JSX attribute value, or comment that happens to contain the same text
    as ``old_name`` is left untouched — the case a `sed`/regex rename gets
    wrong (`KB § PATTERNS/common/ast.md § Anti-patterns`).
    """
    target = _resolve_target_path(path, worktree_path)

    if shutil.which("node") is None:
        msg = (
            "`node` not found on PATH — ts-morph AST edits require Node.js. "
            "This is a typed degrade, not a silent no-op: no file was touched."
        )
        logger.warning(msg)
        return TsAstEditResult(
            ok=False,
            status="node_unavailable",
            path=str(target),
            old_name=old_name,
            new_name=new_name,
            error=msg,
        )

    if not _TS_AST_EDIT_SCRIPT.exists():
        msg = f"ts_ast_edit.mjs missing at {_TS_AST_EDIT_SCRIPT} — node helper dir not installed correctly"
        logger.error(msg)
        return TsAstEditResult(
            ok=False,
            status="helper_script_missing",
            path=str(target),
            old_name=old_name,
            new_name=new_name,
            error=msg,
        )

    payload = {
        "op": "rename_symbol",
        "path": str(target),
        "oldName": old_name,
        "newName": new_name,
    }

    try:
        process_ok, result, stderr = _run_node_op(payload)
    except subprocess.TimeoutExpired:
        msg = f"ts_ast_edit.mjs timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s on {target}"
        logger.error(msg)
        return TsAstEditResult(
            ok=False,
            status="timeout",
            path=str(target),
            old_name=old_name,
            new_name=new_name,
            error=msg,
        )

    if not process_ok:
        msg = f"ts_ast_edit.mjs crashed (non-JSON output or non-zero exit): {stderr.strip() or 'no stderr'}"
        logger.error(msg)
        return TsAstEditResult(
            ok=False,
            status="node_crashed",
            path=str(target),
            old_name=old_name,
            new_name=new_name,
            error=msg,
        )

    if not result.get("ok"):
        error = result.get("error", "unknown ts_ast_edit.mjs failure")
        logger.warning("ts_ast_rename_symbol failed: %s", error)
        return TsAstEditResult(
            ok=False,
            status=result.get("status", "unknown_error"),
            path=str(target),
            old_name=old_name,
            new_name=new_name,
            error=error,
        )

    return TsAstEditResult(
        ok=True,
        status=result.get("status", "renamed"),
        path=result.get("path", str(target)),
        old_name=result.get("oldName", old_name),
        new_name=result.get("newName", new_name),
        references_updated=result.get("referencesUpdated"),
        declaration_kind=result.get("declarationKind"),
    )


def register(server) -> None:
    @server.tool(
        name="noctus.dev.ts_ast_rename_symbol",
        description=(
            "Rename a top-level TS/TSX symbol (function/class/interface/type/"
            "const|let|var) AND every real reference to it, via a genuine "
            "ts-morph AST edit (scope-aware — resolves the TypeScript binder, "
            "not text matching). Leaves same-spelled string literals, JSX "
            "attribute values, and comments untouched — the case a regex/sed "
            "rename gets wrong. Honest typed error on missing node / parse "
            "failure / symbol-not-found (no silent no-op). "
            "KB § PATTERNS/common/ast.md."
        ),
    )
    def _ts_ast_rename_symbol(
        path: str,
        old_name: str,
        new_name: str,
        worktree_path: Optional[str] = None,
    ) -> dict:
        return ts_ast_rename_symbol(
            path=path,
            old_name=old_name,
            new_name=new_name,
            worktree_path=worktree_path,
        ).to_dict()
