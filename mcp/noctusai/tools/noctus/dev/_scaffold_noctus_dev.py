"""Toolkit-tool scaffolder core — the ``target='noctus.dev'`` leg of
``noctus.dev.scaffold_mcp_tool``.

WHY: skill ``noc-mcp-tool`` says "scaffold first", but the scaffolder only
knew the connector-MCP leaf shape (``mcp/<vendor>/tools``). A toolkit tool
(``noctus.dev.<name>``) was hand-copied from a sibling each time. This module
emits the REAL toolkit shape and wires it:

1. ``tools/noctus/dev/<name>.py`` — pure core fn (keyword-only, with a DI seam
   ``executor``), ``register(server)``; a writer is dry-run by default
   (``confirm=False`` returns the plan) and wrapped in
   ``toolkit_freshness.refuse_gate``.
2. ``tools/noctus/dev/__init__.py`` — import + ``register`` line (libcst).
3. ``cli.py`` — ``--<flag>`` (+ ``-confirm`` / ``-allow-stale-toolkit`` for a
   writer) in ``build_parser`` and an ``elif`` dispatch branch (libcst).
4. ``tests/test_<name>.py`` — exercises the core through the seam, no patching.
5. writer only: ``toolkit_freshness._MAPPED_PARAMS`` entry + ``_tool_cli_argv``
   branch (libcst) so the R4 fresh-subprocess hop carries every MCP param.

AST-first: every edit of an existing file is a libcst transform (formatting
and comments survive byte-for-byte). ``cli.py``'s ~250-deep ``elif`` chain
overflows the default recursion limit in libcst's visitor/codegen, so every
edit runs under ``_deep_recursion``. Nothing is written unless every target
file transforms cleanly and no target already exists (all-or-nothing).
"""
from __future__ import annotations

import ast
import contextlib
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

import libcst as cst

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,60}$")
_RECURSION_LIMIT = 50_000

DEV = Path("mcp/noctusai/tools/noctus/dev")
INIT_REL = DEV / "__init__.py"
CLI_REL = Path("mcp/noctusai/cli.py")
FRESH_REL = DEV / "toolkit_freshness.py"


@contextlib.contextmanager
def _deep_recursion():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, _RECURSION_LIMIT))
    try:
        yield
    finally:
        sys.setrecursionlimit(old)


def default_repo_root() -> Path:
    # .../mcp/noctusai/tools/noctus/dev/<this file> -> repo root
    return Path(__file__).resolve().parents[5]


# ── rendering ───────────────────────────────────────────────────────────────

def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def render_module(name: str, description: str, writes: bool, tree_dependent: bool) -> str:
    wt_param = "    worktree_path: str | None = None,\n" if tree_dependent else ""
    wt_pass = "worktree_path=worktree_path, " if tree_dependent else ""
    wt_exec = "worktree_path: str | None = None" if tree_dependent else ""
    wt_tool = "        worktree_path: str | None = None,\n" if tree_dependent else ""
    desc = description.replace('"', "'")
    if writes:
        imports = "from . import toolkit_freshness as _toolkit_freshness\n"
        deco = f'@_toolkit_freshness.refuse_gate("{name}")\n'
        confirm_param = "    confirm: bool = False,\n"
        tool_confirm = "        confirm: bool = False,\n        allow_stale_toolkit: bool = False,\n"
        call = f"{name}({wt_pass}confirm=confirm, allow_stale_toolkit=allow_stale_toolkit)"
        exec_sig = "*, confirm: bool" + (f", {wt_exec}" if wt_exec else "")
        exec_call = f"run({wt_pass}confirm=confirm)"
        status = '"applied" if confirm else "planned"'
        doc_gate = (
            "Dry-run by default: ``confirm=False`` returns the plan and mutates nothing; "
            "``confirm=True`` applies. "
        )
        desc_tail = " WRITE - confirm=False returns the plan (status 'planned'), confirm=True applies."
    else:
        imports = ""
        deco = ""
        confirm_param = ""
        tool_confirm = ""
        call = f"{name}({wt_pass.rstrip(', ')})"
        exec_sig = f"*, {wt_exec}" if wt_exec else ""
        exec_call = f"run({wt_pass.rstrip(', ')})"
        status = '"ok"'
        doc_gate = "Read-only. "
        desc_tail = " READ-ONLY."
    return f'''"""noctus.dev.{name} - {desc}

{doc_gate}The core is a pure function with a DI seam (``executor``) so tests drive it
without patching anything; ``register`` is a thin MCP wrapper.

KB § PATTERNS/architect/mcp-first-scripts.md
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

{imports}

def _default_executor({exec_sig}) -> dict[str, Any]:
    # TODO: the real work. A writer MUST do nothing but plan when confirm is False.
    return {{
        "ok": False,
        "status": "not_implemented",
        "error": "NOC-REMEDIATE[scaffold-todo]: {name} has no implementation yet - fill _default_executor.",
    }}


{deco}def {name}(
    *,
{wt_param}{confirm_param}    executor: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """{desc}"""
    run = executor or _default_executor
    outcome = {exec_call}
    if outcome.get("ok") is False:
        return outcome
    return {{"ok": True, "status": {status}, **outcome}}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.{name}",
        description=(
            "{desc}{desc_tail} Returns {{ok, status, ...}}. "
            "KB § PATTERNS/architect/mcp-first-scripts.md"
        ),
    )
    def _{name}(
{wt_tool}{tool_confirm}    ) -> dict:
        return {call}


__all__ = ["{name}", "register"]
'''


def render_test(name: str, writes: bool, tree_dependent: bool) -> str:
    wt = ", worktree_path=None" if tree_dependent else ""
    if writes:
        body = f'''
def test_dry_run_is_the_default_and_plans_only():
    calls = []

    def seam(*, confirm{", worktree_path=None" if tree_dependent else ""}):
        calls.append(confirm)
        return {{"changed": []}}

    out = mod.{name}(executor=seam)
    assert out["status"] == "planned" and calls == [False]


def test_confirm_applies_through_the_seam():
    calls = []

    def seam(*, confirm{", worktree_path=None" if tree_dependent else ""}):
        calls.append(confirm)
        return {{"changed": ["x"]}}

    out = mod.{name}(confirm=True, executor=seam)
    assert out["status"] == "applied" and out["changed"] == ["x"] and calls == [True]


def test_failing_executor_is_not_ok():
    def seam(*, confirm{", worktree_path=None" if tree_dependent else ""}):
        return {{"ok": False, "status": "error", "error": "boom"}}

    assert mod.{name}(confirm=True, executor=seam)["ok"] is False
'''
    else:
        body = f'''
def test_core_through_the_seam():
    def seam({"*, worktree_path=None" if tree_dependent else ""}):
        return {{"rows": [1]}}

    out = mod.{name}(executor=seam)
    assert out == {{"ok": True, "status": "ok", "rows": [1]}}


def test_failing_executor_is_not_ok():
    def seam({"*, worktree_path=None" if tree_dependent else ""}):
        return {{"ok": False, "status": "error", "error": "boom"}}

    assert mod.{name}(executor=seam)["ok"] is False
'''
    tail = f'''
def test_registered_under_the_dev_namespace():
    seen = {{}}

    class _Server:
        def tool(self, *, name, description):
            seen["name"], seen["description"] = name, description
            return lambda fn: fn

    mod.register(_Server())
    assert seen["name"] == "noctus.dev.{name}"
    assert seen["description"].strip()
'''
    cls = "".join(p.capitalize() for p in name.split("_"))
    inner = re.sub(r"^def (test_\w+)\(\):", r"def \1(self):", body + tail, flags=re.M)
    inner = textwrap.indent(inner.strip("\n"), "    ")
    return f'''"""Colocated tests for noctus.dev.{name} (scaffolded) - core driven through the
executor seam; nothing in this repo is monkeypatched."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import {name} as mod  # noqa: E402


class Test{cls}:
{inner}
'''


# ── libcst edits ────────────────────────────────────────────────────────────

def _stmt(src: str) -> cst.BaseStatement:
    return cst.parse_statement(src)


def _is_call_stmt(stmt: cst.CSTNode, attr: str) -> bool:
    """``<x>.<attr>(server)`` expression statement."""
    if not isinstance(stmt, cst.SimpleStatementLine) or len(stmt.body) != 1:
        return False
    e = stmt.body[0]
    return (isinstance(e, cst.Expr) and isinstance(e.value, cst.Call)
            and isinstance(e.value.func, cst.Attribute) and e.value.func.attr.value == attr)


class _InitEdit(cst.CSTTransformer):
    def __init__(self, name: str):
        self.name, self.done = name, False

    def leave_FunctionDef(self, orig, updated):
        if updated.name.value != "register_all" or not isinstance(updated.body, cst.IndentedBlock):
            return updated
        body = list(updated.body.body)
        last_imp = max((i for i, s in enumerate(body) if isinstance(s, cst.SimpleStatementLine)
                        and isinstance(s.body[0], cst.ImportFrom)), default=None)
        last_reg = max((i for i, s in enumerate(body) if _is_call_stmt(s, "register")), default=None)
        if last_imp is None or last_reg is None:
            return updated
        body.insert(last_reg + 1, _stmt(f"{self.name}.register(server)\n"))
        body.insert(last_imp + 1, _stmt(f"from . import {self.name}\n"))
        self.done = True
        return updated.with_changes(body=updated.body.with_changes(body=body))


def edit_init(src: str, name: str) -> str:
    if f"from . import {name}\n" in src or f"{name}.register(server)" in src:
        raise ValueError(f"{INIT_REL} already registers {name!r}")
    with _deep_recursion():
        ed = _InitEdit(name)
        out = cst.parse_module(src).visit(ed)
        if not ed.done:
            raise ValueError(f"{INIT_REL}: register_all() import/register block not found")
        return out.code


def _flags_in(src: str) -> set[str]:
    out: set[str] = set()
    with _deep_recursion():
        tree = ast.parse(src)
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "add_argument"):
            out.update(a.value for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
                       and a.value.startswith("--"))
    return out


class _CliEdit(cst.CSTTransformer):
    def __init__(self, parser_stmts: list[str], dispatch_src: str):
        self.parser_stmts, self.dispatch_src = parser_stmts, dispatch_src
        self.parser_done = self.dispatch_done = False

    def leave_FunctionDef(self, orig, updated):
        if not isinstance(updated.body, cst.IndentedBlock):
            return updated
        body = list(updated.body.body)
        if updated.name.value == "build_parser":
            ret = next((i for i, s in enumerate(body) if isinstance(s, cst.SimpleStatementLine)
                        and isinstance(s.body[0], cst.Return)), None)
            if ret is None:
                return updated
            for k, s in enumerate(self.parser_stmts):
                body.insert(ret + k, _stmt(s + "\n"))
            self.parser_done = True
            return updated.with_changes(body=updated.body.with_changes(body=body))
        if updated.name.value == "main" and not self.dispatch_done:
            for i, s in enumerate(body):
                if not isinstance(s, cst.If):
                    continue
                chain = [s]
                while isinstance(chain[-1].orelse, cst.If):
                    chain.append(chain[-1].orelse)
                if len(chain) < 20 or not isinstance(chain[-1].orelse, cst.Else):
                    continue  # not the dispatch chain, or it has no default `else`
                new_if = _stmt(self.dispatch_src).with_changes(
                    leading_lines=[cst.EmptyLine(indent=False)], orelse=chain[-1].orelse)
                rebuilt: cst.If = chain[-1].with_changes(orelse=new_if)
                for parent in reversed(chain[:-1]):
                    rebuilt = parent.with_changes(orelse=rebuilt)
                body[i] = rebuilt
                self.dispatch_done = True
                return updated.with_changes(body=updated.body.with_changes(body=body))
        return updated


def edit_cli(src: str, name: str, writes: bool, tree_dependent: bool) -> str:
    flag = _flag(name)
    have = _flags_in(src)
    wanted = [flag] + ([f"{flag}-confirm", f"{flag}-allow-stale-toolkit"] if writes else [])
    clash = [f for f in wanted if f in have]
    if clash:
        raise ValueError(f"{CLI_REL} already defines {clash}")
    attr = name
    parser = [f'parser.add_argument("{flag}", action="store_true", '
              f'help="TODO one line. MCP: noctus.dev.{name}.")']
    kw = []
    if writes:
        parser += [
            f'parser.add_argument("{flag}-confirm", action="store_true", '
            f'help="With {flag}: apply (a write). Without it, dry-run only.")',
            f'parser.add_argument("{flag}-allow-stale-toolkit", action="store_true", '
            f'help="With {flag}: bypass the toolkit-staleness fresh-subprocess hop (escape hatch).")',
        ]
        kw += [f'confirm=bool(getattr(args, "{attr}_confirm", False))',
               f'allow_stale_toolkit=bool(getattr(args, "{attr}_allow_stale_toolkit", False))']
    if tree_dependent:
        kw.append("worktree_path=args.worktree_path")
    dispatch = (
        f"if args.{attr}:\n"
        f"    from tools.noctus.dev.{name} import {name} as _{name}\n"
        f"    r = _{name}({', '.join(kw)})\n"
        f"    print(json.dumps(r, indent=2, default=str))\n"
        f"    sys.exit(0 if r.get(\"ok\") else 1)\n"
    )
    with _deep_recursion():
        ed = _CliEdit(parser, dispatch)
        out = cst.parse_module(src).visit(ed)
        if not (ed.parser_done and ed.dispatch_done):
            raise ValueError(f"{CLI_REL}: build_parser() return or main() dispatch chain not found")
        return out.code


class _FreshEdit(cst.CSTTransformer):
    def __init__(self, name: str, mapped: list[str], argv_src: str):
        self.name, self.mapped, self.argv_src = name, mapped, argv_src
        self.map_done = self.argv_done = False

    def leave_AnnAssign(self, orig, updated):
        t = updated.target
        if isinstance(t, cst.Name) and t.value == "_MAPPED_PARAMS" and isinstance(updated.value, cst.Dict):
            elems = list(updated.value.elements)
            vals = ", ".join(f'"{p}"' for p in self.mapped)
            new = cst.parse_expression(f'{{"{self.name}": frozenset({{{vals}}})}}').elements[0]
            prev = elems[-1]
            # Entries are one-per-line: the previous entry hands its (newline +
            # indent) comma to the new last entry and gets a fresh newline comma.
            elems[-1] = prev.with_changes(comma=cst.Comma(
                whitespace_after=cst.ParenthesizedWhitespace(
                    indent=True, last_line=cst.SimpleWhitespace("    "))))
            elems.append(new.with_changes(comma=prev.comma if isinstance(prev.comma, cst.Comma) else cst.Comma()))
            self.map_done = True
            return updated.with_changes(value=updated.value.with_changes(elements=elems))
        return updated

    def leave_FunctionDef(self, orig, updated):
        if updated.name.value != "_tool_cli_argv" or not isinstance(updated.body, cst.IndentedBlock):
            return updated
        body = list(updated.body.body)
        last = body[-1]
        if not (isinstance(last, cst.SimpleStatementLine) and isinstance(last.body[0], cst.Return)):
            return updated
        body.insert(len(body) - 1, _stmt(self.argv_src).with_changes(
            leading_lines=[cst.EmptyLine(indent=False)]))
        self.argv_done = True
        return updated.with_changes(body=updated.body.with_changes(body=body))


def edit_freshness(src: str, name: str, tree_dependent: bool) -> str:
    if re.search(rf'^\s+"{name}": frozenset\(', src, re.M) or f'tool_name == "{name}"' in src:
        raise ValueError(f"{FRESH_REL} already maps {name!r}")
    flag = _flag(name)
    mapped = ["confirm"] + (["worktree_path"] if tree_dependent else [])
    argv = (
        f'if tool_name == "{name}":\n'
        f'    argv = ["{flag}"]\n'
        f'    if kwargs.get("confirm"):\n'
        f'        argv.append("{flag}-confirm")\n'
        + (f'    if kwargs.get("worktree_path"):\n'
           f'        argv.append(f"--worktree-path={{kwargs[\'worktree_path\']}}")\n' if tree_dependent else "")
        + "    return argv\n"
    )
    with _deep_recursion():
        ed = _FreshEdit(name, mapped, argv)
        out = cst.parse_module(src).visit(ed)
        if not (ed.map_done and ed.argv_done):
            raise ValueError(f"{FRESH_REL}: _MAPPED_PARAMS / _tool_cli_argv anchors not found")
        return out.code


# ── orchestration ───────────────────────────────────────────────────────────

def scaffold_noctus_dev(
    name: str, description: str, kind: str, tree_dependent: bool,
    repo_root: Path, confirm: bool,
) -> dict[str, Any]:
    if not _NAME_RE.match(name or ""):
        return {"ok": False, "error": "name must be snake_case ([a-z][a-z0-9_]{2,60})"}
    if kind not in ("read", "write"):
        return {"ok": False, "error": "kind must be 'read' or 'write'"}
    writes = kind == "write"
    root = Path(repo_root)
    mod_p, test_p = root / DEV / f"{name}.py", root / "mcp/noctusai/tests" / f"test_{name}.py"
    init_p, cli_p, fresh_p = root / INIT_REL, root / CLI_REL, root / FRESH_REL
    for p in (init_p, cli_p) + ((fresh_p,) if writes else ()):
        if not p.is_file():
            return {"ok": False, "error": f"{p} not found - is repo_root a noc tree?"}
    exists = [str(p) for p in (mod_p, test_p) if p.exists()]
    if exists:
        return {"ok": False, "status": "refused_exists", "error": f"refusing to overwrite: {exists}"}
    desc = description.strip() or "TODO one-line purpose"
    try:
        edits = {
            init_p: edit_init(init_p.read_text(), name),
            cli_p: edit_cli(cli_p.read_text(), name, writes, tree_dependent),
        }
        if writes:
            edits[fresh_p] = edit_freshness(fresh_p.read_text(), name, tree_dependent)
        new_files = {
            mod_p: render_module(name, desc, writes, tree_dependent),
            test_p: render_test(name, writes, tree_dependent),
        }
        for p, code in new_files.items():
            ast.parse(code)
        for p, code in edits.items():
            ast.parse(code)
    except (ValueError, SyntaxError, cst.ParserSyntaxError) as exc:
        return {"ok": False, "status": "refused_exists" if "already" in str(exc) else "error",
                "error": str(exc)}
    rel = lambda p: str(p.relative_to(root))  # noqa: E731
    result: dict[str, Any] = {
        "ok": True,
        "status": "scaffolded" if confirm else "planned",
        "tool_name": f"noctus.dev.{name}",
        "cli_flag": _flag(name),
        "creates": [rel(p) for p in new_files],
        "edits": [rel(p) for p in edits],
        "note": "Fill _default_executor + the description/help TODOs, then /mcp reconnect.",
    }
    if not confirm:
        result["module_code"] = new_files[mod_p]
        result["test_code"] = new_files[test_p]
        result["note"] = "confirm=False: nothing written. Re-call with confirm=True to create/edit the files."
        return result
    for p, code in {**new_files, **edits}.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code)
    return result
