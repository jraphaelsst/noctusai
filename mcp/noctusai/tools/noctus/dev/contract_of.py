"""Declared cross-product test dependencies (`CONTRACT_OF`) — derived, never listed.

WHY (recurrence N=2, 2026-10): `task_branch integrate` picks merged-tip gates
from the changed paths, so an agents-only diff ran only agents gates while
social-wiring tests that READ agents' contract (`channels.v2.json`) and tool
registry went red on dev, found by hand, twice.

MECHANISM: a test file that reads another product's files declares, as a
module-level literal, the provider paths it reads::

    CONTRACT_OF = ("products/agents/backend/contracts/**",
                   "products/agents/backend/app/channels/tool_registry.py")

`gate_sweep` scans the tracked test trees (cheap: only files containing the
token are parsed), and when a changed path matches a declared glob it adds a
scoped gate running exactly those consumer files. The keeper
`check_every_test_file_is_gated` fails a test that references another
product's `products/<x>/` tree without declaring `CONTRACT_OF`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

TOKEN = "CONTRACT_OF"
_TEST_ROOT_RE = re.compile(r"^products/([^/]+)/(?:backend|frontend)/")
_SKIP_DIRS = frozenset({".venv", "venv", "node_modules", "__pycache__", ".git", "dist"})
_TEST_GLOBS = ("test_*.py",)
_FS_READ_RE = re.compile(r"\b(?:Path|open|read_text|read_bytes|glob|rglob|os\.path)\b")
_PRODUCT_PATH_RES = (
    re.compile(r"products/([a-z0-9][a-z0-9_-]*)/(?:backend|frontend|contracts)\b"),
)


def _glob_re(pat: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile("^" + out + "$")


def matches_any(path: str, globs: tuple[str, ...]) -> bool:
    return any(_glob_re(g).match(path) for g in globs)


def parse_contract_of(text: str) -> tuple[str, ...] | None:
    """The module-level `CONTRACT_OF` literal (tuple/list of str), or None."""
    if TOKEN not in text:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == TOKEN for t in targets):
            try:
                val = ast.literal_eval(value)
            except ValueError:
                return None
            if isinstance(val, (tuple, list)) and all(isinstance(v, str) for v in val):
                return tuple(val)
    return None


def _test_files(root: Path):
    base = root / "products"
    if not base.is_dir():
        return
    for prod in sorted(p for p in base.iterdir() if p.is_dir()):
        tests = prod / "backend" / "tests"
        if not tests.is_dir():
            continue
        for p in sorted(tests.rglob("test_*.py")):
            if _SKIP_DIRS.intersection(p.relative_to(tests).parts):
                continue
            yield p


def declared_contracts(root: Path) -> dict[str, tuple[str, ...]]:
    """{consumer test rel path: provider globs} for every declaring test."""
    found: dict[str, tuple[str, ...]] = {}
    for p in _test_files(root):
        try:
            globs = parse_contract_of(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if globs:
            found[p.relative_to(root).as_posix()] = globs
    return found


def contract_consumers(root: Path, changed_files: list[str]) -> dict[str, list[str]]:
    """{consumer product slug: [consumer test paths relative to its backend]}
    for every declaring test whose globs match a changed path. A test that
    declares globs inside the changed product itself is excluded upstream by
    the caller (its full suite already runs)."""
    out: dict[str, list[str]] = {}
    for rel, globs in declared_contracts(root).items():
        if any(matches_any(f, globs) for f in changed_files):
            m = _TEST_ROOT_RE.match(rel)
            if m:
                slug = m.group(1)
                out.setdefault(slug, []).append(rel[len(f"products/{slug}/backend/"):])
    return {k: sorted(v) for k, v in out.items()}


def _flatten_div(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _flatten_div(node.left) + _flatten_div(node.right)
    return [node]


def foreign_product_refs(rel: str, text: str) -> set[str]:
    """Other products' slugs whose tree this test file reads by path literal.

    AST-based: docstrings/comments are prose, not reads; only real string
    constants (`"products/x/backend/..."`) and `/ "products" / "x"` chains
    count, and only in a file that does filesystem work at all."""
    m = _TEST_ROOT_RE.match(rel)
    own = m.group(1) if m else None
    refs: set[str] = set()
    if not _FS_READ_RE.search(text):
        return refs  # a slug in a URL/string is not a filesystem read
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return refs
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            refs.update(_PRODUCT_PATH_RES[0].findall(node.value))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = _flatten_div(node)
            vals = [p.value if isinstance(p, ast.Constant) and isinstance(p.value, str) else None for p in parts]
            for i in range(len(vals) - 1):
                if vals[i] == "products" and vals[i + 1]:
                    refs.add(vals[i + 1])
    refs.discard(own)
    refs.discard("seed")  # seed is covered by seed fan-out, not a sibling product
    return refs


def undeclared_cross_product_tests(root: Path) -> list[tuple[str, set[str]]]:
    """Tests naming another product's tree without a CONTRACT_OF declaration."""
    bad = []
    for p in _test_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        refs = foreign_product_refs(rel, text)
        if refs and not parse_contract_of(text):
            bad.append((rel, refs))
    return bad
