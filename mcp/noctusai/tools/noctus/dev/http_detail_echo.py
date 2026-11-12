"""Keeper logic: an HTTP error body never carries exception text ("no-leaking", owner rule 2026-11-11).

``HTTPException(..., detail=<expr>)`` / ``JSONResponse`` error bodies whose expression references the caught exception
(``str(exc)``, ``f"... {exc}"``, ``repr(exc)``, ``exc.args``) echo internal hostnames, env-var names and driver text to
the caller. Construction: ``noctusai_lib.api.integration_errors.integration_error`` (fixed pt-BR message + stable code).

Scope: ``seed/**`` (ZERO tolerance, never baselined) and ``products/*/backend/app/**`` (ratchet baseline
``deploy/security/http-detail-echo-baseline.json`` -- only shrinks; a NEW echo is refused while the backlog drains).
Escape for a domain-authored message that cannot carry infrastructure text: ``# detail-safe: <reason>`` on the call.

KB § PATTERNS/security/appsec-craft-canon.md
"""
from __future__ import annotations

# NOC-REMEDIATE[http-detail-echo]: ~209 product HTTP error bodies still echo exception text; destination = the ratchet baseline
# deploy/security/http-detail-echo-baseline.json (drain each to integration_error(); the file only shrinks) — 2026-11-11

import ast
import json
from pathlib import Path
from typing import Any, Iterator

BASELINE_REL = "deploy/security/http-detail-echo-baseline.json"
ESCAPE = "# detail-safe:"
_SKIP_PARTS = {"tests", "test", "__pycache__", "node_modules", ".venv", "venv"}


def _py_files(root: Path) -> Iterator[Path]:
    for base, pat in (("seed", "**/*.py"), ("products", "*/backend/app/**/*.py")):
        d = root / base
        if not d.is_dir():
            continue
        for p in sorted(d.glob(pat)):
            rel = p.relative_to(root).parts
            if _SKIP_PARTS & set(rel) or p.name.startswith("test_") or p.name == "conftest.py":
                continue
            yield p


def _refs(expr: ast.AST, names: set[str]) -> bool:
    """True when ``expr`` references an exception name, other than through ``type(exc).__name__``."""
    for node in ast.walk(expr):
        if isinstance(node, ast.Name) and node.id in names and not _only_type_name(expr, node):
            return True
    return False


def _only_type_name(expr: ast.AST, target: ast.Name) -> bool:
    """``type(exc).__name__`` / ``exc.__class__.__name__`` name the CLASS only: safe."""
    for node in ast.walk(expr):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "type"
                and node.args and node.args[0] is target):
            return True
        if isinstance(node, ast.Attribute) and node.attr == "__class__" and node.value is target:
            return True
    return False


def _is_error_status(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "status_code":
            v = kw.value
            if isinstance(v, ast.Constant) and isinstance(v.value, int):
                return v.value >= 400
            return "HTTP_4" in ast.unparse(v) or "HTTP_5" in ast.unparse(v)
    return False


def _body_exprs(call: ast.Call) -> list[ast.AST]:
    fn = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
    if fn == "HTTPException":
        out = [kw.value for kw in call.keywords if kw.arg == "detail"]
        if len(call.args) >= 2:
            out.append(call.args[1])
        return out
    if fn == "JSONResponse" and _is_error_status(call):
        out = [kw.value for kw in call.keywords if kw.arg == "content"]
        if call.args:
            out.append(call.args[0])
        return out
    return []


def _owner_func(tree: ast.AST) -> dict[int, str]:
    """id(node) -> name of the innermost enclosing function (for stable baseline keys)."""
    owner: dict[int, str] = {}

    def visit(node: ast.AST, fn: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            owner[id(child)] = name
            visit(child, name)

    visit(tree, "<module>")
    return owner


def _regions(tree: ast.AST) -> Iterator[tuple[ast.AST, set[str]]]:
    """(subtree, exception names live in it): an except-handler body, or a function body whose parameter is
    annotated ``Exception`` / ``BaseException``. Names never leak into sibling or nested-def scopes."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.name:
            yield node, {node.name}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = {a.arg for a in node.args.args + node.args.kwonlyargs
                     if a.annotation is not None and ast.unparse(a.annotation) in {"Exception", "BaseException"}}
            if names:
                yield node, names


def scan_source(src: str, rel: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()
    owner = _owner_func(tree)
    flagged: dict[tuple[int, int], dict[str, Any]] = {}
    for region, names in _regions(tree):
        for node in ast.walk(region):
            if not isinstance(node, ast.Call):
                continue
            for expr in _body_exprs(node):
                if not _refs(expr, names):
                    continue
                span = lines[node.lineno - 1: (node.end_lineno or node.lineno)]
                if any(ESCAPE in ln for ln in span):
                    continue
                flagged[(node.lineno, node.col_offset)] = {
                    "func": owner.get(id(node), "<module>"), "line": node.lineno, "expr": ast.unparse(expr)}
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for (_l, _c), f in sorted(flagged.items()):
        base = f"{rel}::{f['func']}::{f['expr']}"
        seen[base] = seen.get(base, 0) + 1
        out.append({
            "key": f"{base}#{seen[base]}", "file": rel, "line": f["line"],
            "issue": f"HTTP error body echoes exception text (`{f['expr']}`): leaks internal hosts / env names / driver "
                     "messages. Return a fixed message + stable code via noctusai_lib.api.integration_errors."
                     "integration_error(code, exc=exc) and log the exception server-side.",
        })
    return out


def scan(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in _py_files(root):
        rel = p.relative_to(root).as_posix()
        out += scan_source(p.read_text(encoding="utf-8", errors="replace"), rel)
    return out


def load_baseline(root: Path) -> dict[str, dict]:
    p = root / BASELINE_REL
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("findings", {})


def is_seed(rel: str) -> bool:
    return rel.startswith("seed/")


def check(root: Path) -> list[dict[str, Any]]:
    """Seed: every echo is a failure. Products: a failure unless the ratchet baseline already lists it."""
    base = load_baseline(root)
    return [
        {"file": f["file"], "line": f["line"], "severity": "high", "issue": f["issue"] + " KB § PATTERNS/security/appsec-craft-canon.md."}
        for f in scan(root) if is_seed(f["file"]) or f["key"] not in base
    ]


def stale_entries(root: Path) -> list[str]:
    """Baseline keys no longer present (fixed): the baseline must shrink to match."""
    cur = {f["key"] for f in scan(root)}
    return sorted(k for k in load_baseline(root) if k not in cur)


def per_product(findings: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        parts = f["file"].split("/")
        k = parts[1] if parts[0] == "products" else parts[0]
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def write_baseline(root: Path, *, grow: bool = False) -> dict[str, int]:
    """Rewrite the baseline to the products' CURRENT echoes. Shrink-only unless ``grow`` (first seeding)."""
    cur = {f["key"]: {"file": f["file"], "line": f["line"]} for f in scan(root) if not is_seed(f["file"])}
    old = load_baseline(root)
    if not grow:
        cur = {k: v for k, v in cur.items() if k in old}
    p = root / BASELINE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "_": "NOC-REMEDIATE[http-detail-echo]: product backlog of HTTP error bodies that echo exception text. Destination: "
             "drain each to noctusai_lib.api.integration_errors.integration_error; this file only shrinks "
             "(cli --update-http-detail-echo-baseline). KB § PATTERNS/security/appsec-craft-canon.md",
        "version": 1,
        "findings": dict(sorted(cur.items())),
    }
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return per_product([{"file": v["file"]} for v in cur.values()])
