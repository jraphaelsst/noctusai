"""The server never rotates nor signs out a GoTrue session it does not own.

Prod 2026-10-23: users were logged out mid-session. GoTrue refresh tokens rotate
on every use and a superseded token presented outside the reuse window revokes
the chain; ``sign_out`` defaults to scope ``global`` (every product, every
device). So the server-side rules are structural, pinned here by AST over the
seed and every product backend:

* ``refresh_session(`` runs ONLY on chains the server itself owns: the cookie
  sessions it minted at ``/api/auth/login`` (exchange + logout revoke) and
  core's stateless ``/api/auth/refresh`` proxy for the core SPA's own chain
  (the core SPA is that chain's single owner; the proxy keeps no copy). A
  browser supabase-js session (SSO / product login) is never refreshed
  server-side.
* every ``sign_out(`` names its scope explicitly and never the literal
  ``"global"`` -- the SDK default is global, so an implicit call is a silent
  fleet-wide logout. Core's explicit logout passes a validated ``scope``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]

ROOTS = [
    REPO / "seed" / "lib" / "backend" / "noctusai_lib",
    REPO / "seed" / "framework" / "backend" / "noctusai_seed",
    *sorted((REPO / "products").glob("*/backend/app")),
]

# file (repo-relative) -> why the server owns the chain it refreshes there
REFRESH_OWNERS = {
    "seed/lib/backend/noctusai_lib/api/auth/session/token_exchange.py":
        "cookie session minted server-side by /api/auth/login",
    "seed/lib/backend/noctusai_lib/api/auth/session/session_revoke.py":
        "cookie session logout revoke (server-minted chain)",
    "products/core/backend/app/routers/auth.py":
        "stateless proxy for the core SPA's own chain; no server copy",
}


def _calls(attr: str):
    for root in ROOTS:
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr
                ):
                    yield path.relative_to(REPO).as_posix(), node


def test_scan_roots_exist():
    assert ROOTS[0].is_dir() and ROOTS[1].is_dir()
    assert (REPO / "products" / "core" / "backend" / "app").is_dir()


def test_refresh_session_only_on_server_owned_chains():
    offenders = sorted({f"{p}:{n.lineno}" for p, n in _calls("refresh_session") if p not in REFRESH_OWNERS})
    assert offenders == [], (
        "server-side refresh of a GoTrue chain the server does not own (rotating the "
        f"browser's refresh token revokes its session): {offenders}"
    )


def _scope_of(call: ast.Call) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "scope":
            return kw.value
    for arg in call.args:
        if isinstance(arg, ast.Call) and getattr(arg.func, "id", getattr(arg.func, "attr", None)) == "SignOutOptions":
            return _scope_of(arg)
    return None


def test_every_server_sign_out_names_a_non_global_scope():
    implicit, global_literal = [], []
    for path, call in _calls("sign_out"):
        scope = _scope_of(call)
        where = f"{path}:{call.lineno}"
        if scope is None:
            implicit.append(where)
        elif isinstance(scope, ast.Constant) and scope.value == "global":
            global_literal.append(where)
    assert implicit == [], f"sign_out without an explicit scope (SDK default = global): {implicit}"
    assert global_literal == [], f"hard-coded global sign_out (every product, every device): {global_literal}"
