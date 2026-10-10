"""Symbol-level test scoping for big toolkit modules (gate_sweep's mcp gate).

WHY (2026-10-10, merged-tip budget measurement). `gate_sweep` scopes the
toolkit gate by IMPORT: every test file importing a changed module runs.
That is right for a small module and useless for `compliance.py` (150
detectors, ~1.1 MB): any keeper slice selected 90 of 295 test files and the
gate ran past 600 s, so every keeper integrate (14 of the last 100 dev
commits) came back `incomplete` against a 90 s merged-tip budget.

WHAT. For a module that many tests import, attribute the diff to the
module's TOP-LEVEL SYMBOLS (defs, classes, named assignments), close over
the module's own internal references (a changed helper pulls in every
symbol that transitively uses it), and select only the test nodes — a
top-level test class/function, or the whole file when a fixture/helper or
module-level statement is involved — that NAME a symbol in that closure.

FALSE-GREEN GUARDS. Symbol scoping can only narrow what runs, so every
uncertainty returns ``None`` = "fall back to import scoping for this module"
(never "select zero"):
  * an edit outside an attributable symbol (imports, `if`/`try` blocks,
    bare expressions) or on a decorator line;
  * a file that does not parse on either side of the diff;
  * a changed symbol no test names, directly or through a non-registry
    caller in the closure;
  * an empty selection.
Tests that reach detectors by REGISTRY or dispatch rather than by name are
ALWAYS selected: the registry is DERIVED (a top-level def that references
at least `REGISTRY_MIN_FANOUT` of the module's own PUBLIC functions, e.g.
`check_all_products`), extended ONE hop to the toolkit defs that call it
(`refresh_compliance_baseline.live_high_critical_fingerprints` is how
`test_all_products_compliant` gets there; a name defined in several modules,
like `main` or `register`, is too ambiguous to count). A test fixture or
helper naming a target selects the tests that request or call it; any other
module-level statement naming one takes the whole file, and so does a test
that reflects over the module object (`getattr`/`vars`/`dir`/
`inspect.getmembers` on it). CLI dispatch tests name the detector as a
`--kebab-flag`, which matches its snake_case symbol. Inside string
constants only code-shaped words (containing `_`) count, and docstrings
not at all: prose is not a reference.

Historical replay (2026-10-10, 14 compliance.py commits): 12 narrowed from
83-90 importing test files to 5-7, 2 fell back (an import edit; a changed
helper no test names).

CI still runs the full suite; this narrows only the merged-tip time-box.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Callable, Mapping

#: A module with at least this many importing test files is "big": below it,
#: import scoping is already cheap and symbol scoping only adds risk.
MIN_IMPORTING_TESTS = 10
#: A top-level def referencing this many of the module's own public functions
#: is a registry/dispatcher (`check_all_products` references 114 detectors).
REGISTRY_MIN_FANOUT = 5

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FLAG_RE = re.compile(r"--([a-z0-9][a-z0-9-]*)")
_REFLECTORS = frozenset({"getattr", "vars", "dir", "getmembers", "hasattr"})


@dataclass(frozen=True)
class _Symbols:
    spans: dict[str, tuple[int, int]]  # name -> (first line, last line)
    decorators: list[tuple[int, int]]  # decorator line ranges
    refs: dict[str, set[str]]  # name -> identifiers it references
    functions: frozenset[str]


def _node_names(node: ast.stmt) -> list[str] | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
        return [t.id for t in node.targets]  # type: ignore[union-attr]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return None


def _identifiers(node: ast.AST) -> set[str]:
    """Names, attribute names, and identifiers/`--flags` inside string
    constants (dispatch tables and CLI flags name symbols as text).
    Docstrings are prose, not references: skipped, or every detector whose
    docstring cites another would join its closure."""
    out: set[str] = set()
    docstrings = {
        id(n.body[0].value) for n in ast.walk(node)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module))
        and n.body and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str)
    }
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.alias):
            out.add(n.asname or n.name.split(".")[-1])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            # only code-shaped words: "keeper" in a message is prose,
            # "check_all_products" is a reference
            out.update(w for w in _IDENT_RE.findall(n.value) if "_" in w.strip("_"))
            out.update(f.replace("-", "_") for f in _FLAG_RE.findall(n.value))
    return out


def _symbols(source: str) -> _Symbols | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    spans: dict[str, tuple[int, int]] = {}
    decorators: list[tuple[int, int]] = []
    refs: dict[str, set[str]] = {}
    functions: set[str] = set()
    for node in tree.body:
        names = _node_names(node)
        if names is None:
            continue
        deco = getattr(node, "decorator_list", None) or []
        if deco:
            decorators.append((min(d.lineno for d in deco), node.lineno - 1))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        ids = _identifiers(node)
        for name in names:
            spans[name] = (node.lineno, node.end_lineno or node.lineno)
            refs[name] = ids - {name}
    return _Symbols(spans, decorators, refs, frozenset(functions))


def _changed_lines(diff: str) -> tuple[list[int], list[int]]:
    """(old-side, new-side) line numbers of a `-U0` diff, skipping lines whose
    content is blank or a comment — those change no behaviour."""
    old: list[int] = []
    new: list[int] = []
    o = n = 0
    for line in diff.splitlines():
        m = _HUNK_RE.match(line)
        if m:
            o, n = int(m.group(1)), int(m.group(3))
            continue
        if line.startswith(("---", "+++")) or not line[:1] in ("-", "+"):
            continue
        body = line[1:].strip()
        meaningful = body and not body.startswith("#")
        if line[0] == "-":
            if meaningful:
                old.append(o)
            o += 1
        else:
            if meaningful:
                new.append(n)
            n += 1
    return old, new


def _attribute(lines: list[int], syms: _Symbols) -> set[str] | None:
    """Changed symbol names, or None when any line is unattributable."""
    changed: set[str] = set()
    for ln in lines:
        if any(a <= ln <= b for a, b in syms.decorators):
            return None
        owner = next((s for s, (a, b) in syms.spans.items() if a <= ln <= b), None)
        if owner is None:
            return None
        changed.add(owner)
    return changed


def changed_symbols(old_source: str | None, new_source: str, diff: str) -> set[str] | None:
    """Top-level symbols a `-U0` diff touches, or None when it can't tell."""
    new_syms = _symbols(new_source)
    old_syms = _symbols(old_source) if old_source is not None else None
    if new_syms is None or (old_source is not None and old_syms is None):
        return None
    old_lines, new_lines = _changed_lines(diff)
    if old_lines and old_syms is None:
        return None
    from_new = _attribute(new_lines, new_syms)
    from_old = _attribute(old_lines, old_syms) if old_lines else set()
    if from_new is None or from_old is None:
        return None
    return from_new | from_old


def registry(syms: _Symbols) -> set[str]:
    """Dispatchers: defs fanning out to >= REGISTRY_MIN_FANOUT of the module's
    PUBLIC functions. Private helpers don't count — a detector calling five
    of its own `_helpers` is a detector, not a registry."""
    public = {f for f in syms.functions if not f.startswith("_")}
    return {
        name for name in syms.functions
        if len(syms.refs[name] & public) >= REGISTRY_MIN_FANOUT
    }


def registry_reach(sources: Mapping[str, str], reg: set[str]) -> set[str]:
    """`reg` plus every top-level def in `sources` (other toolkit modules,
    test helpers) that names a registry symbol — ONE hop. That is how a test
    reaches the detectors without naming them: `test_all_products_compliant`
    goes through `refresh_compliance_baseline.live_high_critical_fingerprints`,
    CLI dispatch through `cli.main`. A fixpoint would not stay bounded: the
    second hop already reaches `release`, `task_branch` and the graph build."""
    defined: dict[str, int] = {}
    reaching: set[str] = set()
    for text in sources.values():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        mentions = any(name in text for name in reg)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            defined[node.name] = defined.get(node.name, 0) + 1
            if mentions and not isinstance(node, ast.ClassDef) and _identifiers(node) & reg:
                reaching.add(node.name)
    # A name defined in several modules (`main`, every tool's `register`)
    # can't be told apart in a test by name: it would select by accident.
    return set(reg) | {n for n in reaching if defined.get(n, 0) == 1}


def closure(changed: set[str], syms: _Symbols) -> set[str]:
    """`changed` plus every symbol that transitively references one."""
    users: dict[str, set[str]] = {}
    for name, ids in syms.refs.items():
        for ref in ids & syms.spans.keys():
            users.setdefault(ref, set()).add(name)
    out, todo = set(changed), list(changed)
    while todo:
        for user in users.get(todo.pop(), ()):
            if user not in out:
                out.add(user)
                todo.append(user)
    return out


def _module_aliases(tree: ast.AST, module: str) -> set[str]:
    """Local names a test binds the module object to."""
    pkg, _, leaf = module.rpartition(".")
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.asname for a in n.names if a.name == module and a.asname)
        elif isinstance(n, ast.ImportFrom) and n.module == pkg:
            out.update(a.asname or a.name for a in n.names if a.name == leaf)
    return out


def _reflects(tree: ast.AST, aliases: set[str]) -> bool:
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and n.args):
            continue
        fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
        first = n.args[0]
        if fn in _REFLECTORS and isinstance(first, ast.Name) and first.id in aliases:
            return True
    return False


def _is_test_node(node: ast.stmt) -> bool:
    if isinstance(node, ast.ClassDef):
        return node.name.startswith("Test")
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")


def select_in_test(
    rel_test: str, source: str, module: str, targets: set[str], always: set[str]
) -> tuple[list[str], set[str]] | None:
    """(selectors, target symbols this file names) for one importing test
    file. A selector is the file itself or `file::Node`. None = can't parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if _reflects(tree, _module_aliases(tree, module)):
        return [rel_test], set(targets)
    body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    ids = {id(n): _identifiers(n) for n in body}
    wanted = targets | always
    named: set[str] = set()
    # A module-level helper or fixture that names a target becomes a target
    # itself, so the tests that call it (or request it by parameter) are
    # selected; repeat until no new helper joins.
    grew = True
    while grew:
        grew = False
        for node in body:
            if _is_test_node(node) or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in wanted and ids[id(node)] & wanted:
                named |= ids[id(node)] & wanted
                wanted.add(node.name)
                grew = True
    nodes: list[str] = []
    for node in body:
        hit = ids[id(node)] & wanted
        if not hit:
            continue
        named |= hit
        if _is_test_node(node):
            nodes.append(f"{rel_test}::{node.name}")  # type: ignore[attr-defined]
        elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return [rel_test], named  # a module-level statement uses it: whole file
    return nodes, named


def scope_module(
    read_test: Callable[[str], str], module: str, importing_tests: list[str],
    old_source: str | None, new_source: str, diff: str,
    toolkit_sources: Mapping[str, str] | None = None,
) -> list[str] | None:
    """Selectors for one big changed module, or None = import scoping.
    `read_test(rel_path)` returns a test file's source (the tree under test,
    or a historical commit when replaying)."""
    if len(importing_tests) < MIN_IMPORTING_TESTS:
        return None
    changed = changed_symbols(old_source, new_source, diff)
    syms = _symbols(new_source)
    if not changed or syms is None:
        return None
    reg = registry(syms)
    always = registry_reach(toolkit_sources or {}, reg)
    targets = closure(changed & syms.spans.keys(), syms) | (changed - syms.spans.keys())
    selectors: list[str] = []
    named: set[str] = set()
    for rel_test in importing_tests:
        picked = select_in_test(
            rel_test, read_test(rel_test), module, targets, always,
        )
        if picked is None:
            return None
        sel, hit = picked
        selectors.extend(sel)
        named |= hit
    # Every changed symbol must be NAMED by a test, directly or through a
    # non-registry symbol that uses it — reaching it only via the registry's
    # fleet run is not coverage of this change. A deleted symbol has no
    # behaviour left to test (its callers changed too and are checked here).
    covering = named - always
    for sym in changed & syms.spans.keys():
        if not (closure({sym}, syms) - always) & covering:
            return None
    return selectors or None
