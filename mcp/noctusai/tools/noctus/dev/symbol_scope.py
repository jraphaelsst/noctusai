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
ALWAYS selected when the change reaches the registry: it is DERIVED (a top-level def that references
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
    dynamic: bool  # the module looks its own names up at runtime


def _dynamic_lookup(tree: ast.AST) -> bool:
    """`globals()` / `vars()` / `sys.modules[__name__]`: a module that reads
    its own names by string at runtime defeats any static reference graph."""
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in ("globals", "vars") and not n.args):
            return True
        if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "modules" and isinstance(n.slice, ast.Name)
                and n.slice.id == "__name__"):
            return True
    return False


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
    return _Symbols(spans, decorators, refs, frozenset(functions), _dynamic_lookup(tree))


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
    if new_syms.dynamic:
        return None
    old_lines, new_lines = _changed_lines(diff)
    if old_lines and old_syms is None:
        return None
    from_new = _attribute(new_lines, new_syms)
    from_old = _attribute(old_lines, old_syms) if old_lines else set()
    if from_new is None or from_old is None:
        return None
    return from_new | from_old


def changed_by_ast(base_source: str, head_source: str) -> set[str] | None:
    """Top-level symbols whose AST differs between two whole sources (new,
    edited or removed), or None when it can't tell: a side that doesn't
    parse, a differing statement that binds no name (an import, an `if`
    block, a bare call), or a module that looks its names up dynamically.
    Line moves and comments don't count — `ast.dump` carries neither."""
    def dumps(src: str):
        tree = ast.parse(src)
        named: dict[str, str] = {}
        unnamed: list[str] = []
        for node in tree.body:
            names = _node_names(node)
            dumped = ast.dump(node)
            if names is None:
                if not _is_prose(node):
                    unnamed.append(dumped)
                continue
            for name in names:
                named[name] = dumped
        return named, sorted(unnamed), _dynamic_lookup(tree)

    try:
        base, base_unnamed, base_dyn = dumps(base_source)
        head, head_unnamed, head_dyn = dumps(head_source)
    except SyntaxError:
        return None
    if base_unnamed != head_unnamed:
        return None
    changed = {n for n in head if base.get(n) != head[n]} | (base.keys() - head.keys())
    if changed and (base_dyn or head_dyn):
        return None
    return changed


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


def closure(changed: set[str], syms: _Symbols, stop: frozenset[str] = frozenset()) -> set[str]:
    """`changed` plus every symbol that transitively references one. A
    symbol in `stop` (a registry) joins the result but its own users are not
    followed, unless it is itself in `changed`."""
    users: dict[str, set[str]] = {}
    for name, ids in syms.refs.items():
        for ref in ids:  # a removed name's former users are users too
            users.setdefault(ref, set()).add(name)
    out, todo = set(changed), list(changed)
    while todo:
        name = todo.pop()
        if name in stop and name not in changed:
            continue
        for user in users.get(name, ()):
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


def _is_prose(node: ast.stmt) -> bool:
    """A bare string statement (the module docstring, a section note)."""
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def _is_test_node(node: ast.stmt) -> bool:
    if isinstance(node, ast.ClassDef):
        return node.name.startswith("Test")
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")


@dataclass(frozen=True)
class Scoped:
    """`run`: selectors the gate runs. `delegated`: selectors that reach the
    change ONLY through the registry — handed to the stand-in gate that
    judges the registry run (`keeper_delta` for `compliance.py`), named in
    the result, and still run whole by CI."""
    run: list[str]
    delegated: list[str]


def select_in_test(
    rel_test: str, source: str, module: str, targets: set[str], always: set[str],
    delegate: bool = False,
) -> tuple[list[str], list[str], set[str]] | None:
    """(run selectors, delegated selectors, target symbols the file names)
    for one importing test file. A selector is the file itself or
    `file::Node`. Nodes reaching only `always` (registry) names are delegated
    when `delegate`, else run. None = can't parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if _reflects(tree, _module_aliases(tree, module)):
        return [rel_test], [], set(targets)
    body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom)) and not _is_prose(n)]
    # What each statement REFERENCES — minus the names it binds itself, so
    # `x = _mod.x` (a module-level re-export) is a helper, not a use.
    ids = {id(n): _identifiers(n) - set(_node_names(n) or ()) for n in body}
    want_run, want_reg = set(targets), set(always)
    named: set[str] = set()
    # A module-level helper, fixture or re-export that names a target becomes
    # a target itself (of the same tier), so the tests that call it or
    # request it by parameter are selected; repeat until nothing joins.
    grew = True
    while grew:
        grew = False
        for node in body:
            bound = _node_names(node)
            if _is_test_node(node) or bound is None:
                continue
            refs = ids[id(node)]
            if refs & want_run and not set(bound) <= want_run:
                named |= refs & want_run
                want_run.update(bound)
                grew = True
            elif refs & want_reg and not set(bound) <= want_reg | want_run:
                want_reg.update(bound)
                grew = True
    run: list[str] = []
    delegated: list[str] = []
    for node in body:
        refs = ids[id(node)]
        hit_run, hit_reg = refs & want_run, refs & want_reg
        if not (hit_run or hit_reg):
            continue
        named |= hit_run
        to_delegate = delegate and not hit_run
        if _is_test_node(node):
            (delegated if to_delegate else run).append(f"{rel_test}::{node.name}")  # type: ignore[attr-defined]
        elif _node_names(node) is None:  # any other module-level statement: whole file
            return ([], [rel_test], named) if to_delegate else ([rel_test], [], named)
    return run, delegated, named


def scope_module(
    read_test: Callable[[str], str], module: str, importing_tests: list[str],
    old_source: str | None, new_source: str, diff: str,
    toolkit_sources: Mapping[str, str] | None = None,
    delegate_registry: bool = False,
) -> Scoped | None:
    """Selectors for one big changed module, or None = import scoping.
    `read_test(rel_path)` returns a test file's source (the tree under test,
    or a historical commit when replaying). `delegate_registry` only when a
    stand-in gate judges the registry run for this module."""
    if len(importing_tests) < MIN_IMPORTING_TESTS:
        return None
    changed = changed_symbols(old_source, new_source, diff)
    syms = _symbols(new_source)
    if not changed or syms is None:
        return None
    reg = frozenset(registry(syms) - changed)  # a CHANGED registry is a plain target
    reached_all = closure(changed, syms, stop=reg)
    # Only the registries that actually dispatch to the change: a cache-
    # freshness aggregator has nothing to say about a detector's allowlist.
    reached = reached_all & reg
    targets = reached_all - reached
    always: set[str] = set()
    if reached:
        always = closure(set(reached), syms) | registry_reach(toolkit_sources or {}, set(reached))
    run: list[str] = []
    delegated: list[str] = []
    named: set[str] = set()
    for rel_test in importing_tests:
        picked = select_in_test(
            rel_test, read_test(rel_test), module, targets, always, delegate_registry,
        )
        if picked is None:
            return None
        r, d, hit = picked
        run.extend(r)
        delegated.extend(d)
        named |= hit
    # Every changed symbol must be NAMED by a test, directly or through a
    # non-registry symbol that uses it — reaching it only via the registry's
    # fleet run is not coverage of this change. A deleted symbol has no
    # behaviour left to test (its callers changed too and are checked here).
    for sym in changed & syms.spans.keys():
        if not closure({sym}, syms, stop=reg) - reg & named:
            return None
    if not run:
        return None
    return Scoped(run, delegated)
