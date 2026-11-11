"""noctus.dev.access_tier_catalog -- the access-tier classifier, keepers and endpoint catalog.

Every route and every DB table declares who may touch it (``platform`` | ``service`` | ``org`` | ``public``);
undeclared is refused. KB § PATTERNS/security/access-tiers.md. The registry (dependency -> tier map, Platform-IP
routes / fields / tables) is ``seed/lib/backend/noctusai_lib/api/access_tiers.py`` -- loaded by path, so the
keeper and the product marker share ONE source.

Three outputs, one analysis:

* ``classify_routes``  -- AST over every ACTIVE product's backend (+ the seed routers): method, path, gates,
  resolved tier, whether it returns Platform IP, verdict ``ok | too-open | unclear``.
* ``check_routes`` / ``check_tables`` -- the keepers: violations not in the ratchet baseline fail.
* ``render_catalog``   -- the generated endpoint catalog (never hand-edited).

The ratchet is the living findings ledger (``access_tier_findings``): a violation without a live row is NEW and fails.
"""
from __future__ import annotations

import ast
import fnmatch
import importlib.util
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from settings import REPO_ROOT

REGISTRY_REL = Path("seed/lib/backend/noctusai_lib/api/access_tiers.py")
CATALOG_REL = Path("project-history/access-tiers/endpoint-catalog.md")
_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}
_SKIP_DIRS = {"tests", "test", "migrations", "node_modules", "__pycache__", "venv", ".venv", "scripts", "templates"}


def load_registry(root: Path | None = None):
    path = (root or REPO_ROOT) / REGISTRY_REL
    spec = importlib.util.spec_from_file_location("_access_tiers_registry", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _tail(expr: ast.AST) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


_GATE_NAME = re.compile(r"^_?(require|assert|ensure|authorize|authenticate|check_access)_|^get_current_|_editor$|_admin$|_context$|_caller$|_ctx$")


def _is_gate_name(name: str) -> bool:
    """Only gate-shaped helpers are followed from a handler body -- an arbitrary helper that happens to call
    a gate (a branch, a read) must not re-tier every route that calls it."""
    return bool(_GATE_NAME.search(name))


def _call_name(call: ast.Call) -> str | None:
    return _tail(call.func)


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    return None


# ---------------------------------------------------------------------------
# Per-product index
# ---------------------------------------------------------------------------
@dataclass
class _Index:
    funcs: dict[str, list[ast.AST]] = field(default_factory=lambda: defaultdict(list))
    assigns: dict[str, list[ast.Call]] = field(default_factory=lambda: defaultdict(list))
    classes: dict[str, ast.ClassDef] = field(default_factory=dict)
    files: dict[Path, ast.Module] = field(default_factory=dict)
    mounts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)


def _py_files(base: Path) -> list[Path]:
    out: list[Path] = []
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in p.relative_to(base).parts):
            continue
        if p.name.startswith("test_") or p.name == "conftest.py":
            continue
        out.append(p)
    return out


def _build_index(files: list[Path]) -> _Index:
    idx = _Index()
    for p in files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        idx.files[p] = tree
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                idx.funcs[n.name].append(n)
            elif isinstance(n, ast.ClassDef):
                idx.classes.setdefault(n.name, n)
            elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        idx.assigns[t.id].append(n.value)
        _collect_mounts(idx, p, tree)
    return idx


def _deps_of_kw(call: ast.Call) -> list[ast.AST]:
    for kw in call.keywords:
        if kw.arg == "dependencies" and isinstance(kw.value, (ast.List, ast.Tuple)):
            return [e.args[0] for e in kw.value.elts if isinstance(e, ast.Call) and _call_name(e) == "Depends" and e.args]
    return []


def _collect_mounts(idx: _Index, path: Path, tree: ast.Module) -> None:
    """``app.include_router(<mod>.router | alias, prefix=, dependencies=)`` -> keyed (module stem, var)."""
    alias: dict[str, tuple[str, str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mod_last = (n.module or "").split(".")[-1]
            for a in n.names:
                if a.name.endswith("router") or a.name == "router":
                    alias[a.asname or a.name] = (mod_last, a.name)
                else:
                    alias[a.asname or a.name] = (a.name, "router")
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "include_router" and n.args):
            continue
        a0 = n.args[0]
        key: tuple[str, str] | None = None
        if isinstance(a0, ast.Attribute) and isinstance(a0.value, ast.Name):
            key = (alias.get(a0.value.id, (a0.value.id, ""))[0], a0.attr)
        elif isinstance(a0, ast.Name) and a0.id in alias:
            key = alias[a0.id]
        elif isinstance(a0, ast.Name):
            key = (path.stem, a0.id)
        if key is None:
            continue
        prefix = ""
        for kw in n.keywords:
            if kw.arg == "prefix":
                prefix = _const_str(kw.value) or ""
        entry = idx.mounts.setdefault(key, {"prefix": prefix, "deps": []})
        entry["prefix"] = prefix or entry["prefix"]
        entry["deps"] += _deps_of_kw(n)


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------
class _Resolver:
    def __init__(self, idx: _Index, reg) -> None:
        self.idx, self.reg = idx, reg
        self._memo: dict[str, tuple[str | None, str]] = {}
        self._busy: set[str] = set()

    def _strongest(self, found: list[tuple[str, str]]) -> tuple[str | None, str]:
        if not found:
            return None, ""
        best = max(found, key=lambda t: self.reg.TIER_RANK[t[0]])
        return best

    def _factory_tier(self, call: ast.Call) -> tuple[str | None, str]:
        name = _call_name(call)
        if name is None:
            return None, ""
        if name == "require_scopes":
            restrict = next((_const_str(k.value) for k in call.keywords if k.arg == "restrict"), None)
            has_roles = any(k.arg == "user_roles" for k in call.keywords)
            if restrict == "product_only":
                return "service", "require_scopes(product_only)"
            if has_roles:
                return "org", "require_scopes(user_roles)"
            return ("service", "require_scopes(scopes)") if call.args else ("org", "require_scopes")
        if name in self.reg.DEP_TIERS:
            return self.reg.DEP_TIERS[name], name
        if name in self.idx.funcs:
            return self.func_tier(name)
        return None, ""

    def func_tier(self, name: str) -> tuple[str | None, str]:
        if name in self._memo:
            return self._memo[name]
        if name in self._busy:
            return None, ""
        self._busy.add(name)
        found: list[tuple[str, str]] = []
        for fn in self.idx.funcs.get(name, []):
            found += self._scan(fn, skip_decorators=True)
        res = self._strongest(found)
        self._busy.discard(name)
        self._memo[name] = res
        return res

    def _scan(self, fn: ast.AST, skip_decorators: bool = False) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                cn = _call_name(n)
                if cn == "Depends" and n.args:
                    t, why = self.dep_tier(n.args[0])
                    if t:
                        found.append((t, why))
                elif cn in self.reg.DEP_TIERS and cn != "require_scopes" and not cn.startswith(("make_", "select_")):
                    found.append((self.reg.DEP_TIERS[cn], f"{cn}()"))
                elif cn and isinstance(n.func, ast.Name) and cn in self.idx.assigns and cn != getattr(fn, "name", None) and self.dep_tier(n.func)[0]:
                    t, why = self.dep_tier(n.func)
                    found.append((t, f"{cn}()->{why}"))  # type: ignore[arg-type]
                elif cn and _is_gate_name(cn) and isinstance(n.func, ast.Name) and cn in self.idx.funcs and cn != getattr(fn, "name", None):
                    t, why = self.func_tier(cn)
                    if t:
                        found.append((t, f"{cn}()->{why}"))
                elif cn in self.reg.SIGNATURE_CALLS:
                    found.append(("public", f"signed ({cn})"))
        return found

    def dep_tier(self, expr: ast.AST) -> tuple[str | None, str]:
        if isinstance(expr, ast.Call):
            return self._factory_tier(expr)
        name = _tail(expr)
        if name is None:
            return None, ""
        if name in self.reg.DEP_TIERS:
            return self.reg.DEP_TIERS[name], name
        if name in self._memo:
            return self._memo[name]
        if name in self._busy:
            return None, ""
        found: list[tuple[str, str]] = []
        self._busy.add(name)
        for call in self.idx.assigns.get(name, []):
            t, why = self._factory_tier(call)
            if t:
                found.append((t, f"{name}={why}"))
        self._busy.discard(name)
        t, why = self.func_tier(name)
        if t:
            found.append((t, f"{name}->{why}" if why and why != name else name))
        res = self._strongest(found)
        self._memo[name] = res
        return res


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@dataclass
class Route:
    product: str
    file: str
    func: str
    line: int
    method: str
    path: str
    gates: list[str]
    tier: str | None
    why: str
    platform_ip: bool
    ip_reason: str
    verdict: str
    note: str
    category: str = ""
    in_schema: bool = True
    router: str = ""

    @property
    def key(self) -> str:
        return f"{self.product}|{self.method} {self.path}|{self.func}"


def _router_defs(tree: ast.Module) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and _call_name(n.value) in ("APIRouter", "FastAPI", "make_router"):
            prefix = next((_const_str(k.value) for k in n.value.keywords if k.arg == "prefix"), "") or ""
            rtier = next((_const_str(k.value) for k in n.value.keywords if k.arg == "tier"), None) if _call_name(n.value) == "make_router" else None
            rcat = next((_const_str(k.value) or "" for k in n.value.keywords if k.arg == "category"), "")
            for t in n.targets:
                if isinstance(t, ast.Name):
                    gdeps = [k.value for k in n.value.keywords if k.arg == "guard"]   # make_router(guard=<dep>) == Depends(<dep>)
                    explicit = next((k.value.value for k in n.value.keywords
                                     if k.arg == "include_in_schema" and isinstance(k.value, ast.Constant)), None)
                    # make_router(tier="platform") defaults include_in_schema=False (access_tiers.make_router) -- the
                    # form this keeper's own message prescribes must not read as exposed.
                    hidden = explicit is False or (explicit is None and rtier == "platform")
                    out[t.id] = {"prefix": prefix, "deps": _deps_of_kw(n.value) + gdeps, "tier": rtier, "category": rcat, "hidden": hidden}
    return out


def _decl_tier(fn: ast.AST, reg) -> tuple[str | None, str, str]:
    for d in getattr(fn, "decorator_list", []):
        if isinstance(d, ast.Call) and _call_name(d) == "access_tier" and d.args:
            t = _const_str(d.args[0])
            if t in reg.TIERS:
                cat = next((_const_str(k.value) or "" for k in d.keywords if k.arg == "category"), "")
                return t, "declared @access_tier", cat
    return None, "", ""


def _module_tier(tree: ast.Module, reg) -> str | None:
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ACCESS_TIER" for t in n.targets):
            v = _const_str(n.value)
            if v in reg.TIERS:
                return v
    return None


def _response_fields(idx: _Index, fn: ast.AST, deco: ast.Call) -> set[str]:
    names: list[str] = []
    for kw in deco.keywords:
        if kw.arg == "response_model":
            names += [n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)]
    ret = getattr(fn, "returns", None)
    if ret is not None:
        names += [n.id for n in ast.walk(ret) if isinstance(n, ast.Name)]
    fields: set[str] = set()
    seen: set[str] = set()
    stack = list(names)
    while stack:
        nm = stack.pop()
        if nm in seen or nm not in idx.classes:
            continue
        seen.add(nm)
        for st in idx.classes[nm].body:
            if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                fields.add(st.target.id)
                stack += [x.id for x in ast.walk(st.annotation) if isinstance(x, ast.Name)]
    return fields


def _route_decorators(fn: ast.AST) -> list[ast.Call]:
    return [
        d for d in getattr(fn, "decorator_list", [])
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _METHODS
        and isinstance(d.func.value, (ast.Name, ast.Attribute))
    ]


def _classify_set(product: str, files: list[Path], root: Path, reg) -> list[Route]:
    idx = _build_index(files)
    res = _Resolver(idx, reg)
    ip_re = [re.compile(p) for p in reg.PLATFORM_IP_ROUTES.get(product, ())]
    pub_re = [re.compile(p) for p in reg.PUBLIC_PATH_CONVENTION]
    routes: list[Route] = []
    for p, tree in idx.files.items():
        routers = _router_defs(tree)
        mod_tier = _module_tier(tree, reg)
        rel = p.relative_to(root).as_posix()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in _route_decorators(fn):
                var = _tail(deco.func.value)  # type: ignore[attr-defined]
                rd = routers.get(var or "", {"prefix": "", "deps": []})
                mount = idx.mounts.get((p.stem, var or ""), {"prefix": "", "deps": []})
                sub = ""
                if deco.args:
                    sub = _const_str(deco.args[0])
                    if sub is None:
                        sub = ast.unparse(deco.args[0])
                else:
                    sub = next((_const_str(k.value) or "" for k in deco.keywords if k.arg == "path"), "")
                path = (mount["prefix"] + rd["prefix"] + sub) or "/"
                dep_exprs: list[ast.AST] = list(rd["deps"]) + list(mount["deps"]) + _deps_of_kw(deco)
                for n in ast.walk(fn.args):
                    if isinstance(n, ast.Call) and _call_name(n) == "Depends" and n.args:
                        dep_exprs.append(n.args[0])
                found: list[tuple[str, str]] = []
                gates: list[str] = []
                for e in dep_exprs:
                    t, why = res.dep_tier(e)
                    if t:
                        found.append((t, why))
                        gates.append(why or (_tail(e) or "?"))
                # imperative gates / signature checks in the handler body (raising gates only: `resolve_*` is a read)
                for n in ast.walk(fn):
                    if not isinstance(n, ast.Call):
                        continue
                    cn = _call_name(n)
                    if cn in reg.SIGNATURE_CALLS:
                        found.append(("public", f"signed ({cn})")); gates.append(f"signed:{cn}")
                    elif cn in reg.DEP_TIERS and cn != "require_scopes" and not cn.startswith(("make_", "select_")) and (
                            not cn.startswith("resolve_") or any(isinstance(x, ast.Raise) for x in ast.walk(fn))):
                        found.append((reg.DEP_TIERS[cn], f"{cn}()")); gates.append(f"{cn}()")
                    elif cn and isinstance(n.func, ast.Name) and cn in idx.assigns and res.dep_tier(n.func)[0] not in (None, "public"):
                        t, why = res.dep_tier(n.func)
                        found.append((t, f"{cn}()->{why}")); gates.append(f"{cn}()")  # type: ignore[arg-type]
                    elif cn and _is_gate_name(cn) and isinstance(n.func, ast.Name) and cn != fn.name and cn in idx.funcs:
                        t, why = res.func_tier(cn)
                        if t and t != "public":
                            found.append((t, f"{cn}()->{why}")); gates.append(f"{cn}()")
                auth_found = [f for f in found if f[0] != "public"]
                signed = [f for f in found if f[0] == "public"]   # signature-verification calls = the signed/service tier
                decl, dwhy, dcat = _decl_tier(fn, reg)
                if not decl and rd.get("tier") in reg.TIERS:   # the router's typed declaration (make_router(tier=...))
                    decl, dwhy, dcat = rd["tier"], "declared make_router(tier=)", rd.get("category", "")
                category = dcat
                verdict_override = None
                if auth_found:
                    tier, why = max(auth_found, key=lambda t: reg.TIER_RANK[t[0]])
                    if decl and reg.TIER_RANK[decl] > reg.TIER_RANK[tier]:
                        verdict_override = ("too-open", f"declared tier {decl} but the gates ({', '.join(sorted(set(gates)))}) only enforce {tier}")
                    elif decl and decl != tier and decl == "public":
                        tier, why = None, f"declared public conflicts with resolved gate {tier}"
                elif decl:
                    tier, why = decl, dwhy
                elif signed:
                    tier, why, category = "service", signed[0][1], "signed:webhook"
                elif mod_tier:
                    tier, why = mod_tier, "module ACCESS_TIER"
                elif any(r.search(path) for r in pub_re):
                    tier, why, category = "service", "health convention", "signed:health"
                else:
                    tier, why = None, "no auth dependency, no @access_tier"
                body_src = ast.unparse(fn).lower()
                oauth_cb = bool(re.search(r"oauth.*callback|/callback\b|/authorize\b", path)) and tier != "platform"
                state_calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and _call_name(n) in reg.OAUTH_STATE_CALLS]
                oauth_bound = any(k.arg == reg.OAUTH_STATE_BINDING_KWARG for c in state_calls for k in c.keywords)
                if oauth_cb and any(c in body_src for c in reg.OAUTH_STATE_CALLS):
                    tier, category = ("service" if tier in (None, "public") else tier), "signed:oauth-callback"
                ip_hit = [r.pattern for r in ip_re if r.search(path)]
                fields = _response_fields(idx, fn, deco) & set(reg.PLATFORM_IP_FIELDS)
                platform_ip = bool(ip_hit or fields)
                ip_reason = ("path~" + ip_hit[0]) if ip_hit else (("fields:" + ",".join(sorted(fields))) if fields else "")
                verdict, note = "ok", ""
                if verdict_override:
                    verdict, note = verdict_override
                elif oauth_cb and category != "signed:oauth-callback":
                    verdict, note = "unclear", "OAuth callback without a state verification call (one of " + ", ".join(sorted(reg.OAUTH_STATE_CALLS)) + ")"
                elif oauth_cb and not oauth_bound and re.search(r"oauth.*callback|/callback\b", path):  # the CALLBACK is bound; /authorize is the start
                    verdict, note = "unclear", (
                        f"OAuth callback verifies state but does not bind it to the browser: pass `{reg.OAUTH_STATE_BINDING_KWARG}=<browser cookie>` "
                        "on the state call (login-CSRF / account-linking; KB § PATTERNS/security/access-tiers.md)")
                elif tier is None:
                    verdict, note = "unclear", why
                elif platform_ip and tier != "platform":
                    verdict, note = "too-open", f"Platform IP ({ip_reason}) behind tier {tier}"
                elif "/admin" in path and tier in ("org", "public") and not decl:
                    verdict, note = "unclear", f"admin-looking path behind tier {tier}; confirm it is customer-owned"
                elif tier == "public":
                    # the closed public allowlist: landing | auth | pricing-checkout | legal-consent | lead-capture
                    limited = any("limit" in ast.unparse(d).lower() or "rate" in ast.unparse(d).lower() for d in fn.decorator_list) \
                        or "limiter" in body_src or "rate_limit" in body_src or "ratelimit" in body_src
                    if category not in reg.PUBLIC_CATEGORIES:
                        verdict, note = "unclear", f"public route outside the closed allowlist {list(reg.PUBLIC_CATEGORIES)} (category={category or 'none'}): every other route is access-level"
                    elif not limited:
                        verdict, note = "unclear", "public route without a rate limit"
                    elif deco.func.attr.upper() != "GET" and not any(a in body_src for a in reg.ABUSE_PROTECTION_NAMES):
                        verdict, note = "unclear", f"public write without abuse protection (one of {sorted(reg.ABUSE_PROTECTION_NAMES)})"
                routes.append(Route(
                    product, rel, fn.name, fn.lineno, deco.func.attr.upper(), path,  # type: ignore[attr-defined]
                    sorted(set(gates)), tier, why, platform_ip, ip_reason, verdict, note, category,
                    in_schema=not (rd.get("hidden") or any(k.arg == "include_in_schema" and isinstance(k.value, ast.Constant) and k.value.value is False for k in deco.keywords)),
                    router=var or "",
                ))
    seen: set[str] = set()
    uniq: list[Route] = []
    for r in sorted(routes, key=lambda r: (r.file, r.line)):
        k = f"{r.key}|{r.file}"
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def analyze_schema_exposure(root: Path | None = None) -> list[dict]:
    """Platform-tier routes that appear in the PUBLIC OpenAPI schema (`/docs` stays public, so Platform IP must be left out by
    construction: the router sets `include_in_schema=False`). One finding per (file, router) -- AST-precise."""
    root = root or REPO_ROOT
    seen: dict[str, dict] = {}
    for r in classify_routes(root):
        if r.tier == "platform" and r.in_schema:
            k = f"schema:{r.product}:{r.file}:{r.router or '?'}"
            seen.setdefault(k, {"key": k, "product": r.product, "file": r.file, "n": 0, "line": r.line})
            seen[k]["n"] += 1
    return [{**v, "issue": f"[schema] router `{v['key'].rsplit(':', 1)[1]}` in {v['file']} has {v['n']} platform-tier route(s) listed in the "
             "PUBLIC OpenAPI schema: create it with `make_router(tier=\"platform\", guard=...)` (include_in_schema=False) or pass "
             "`include_in_schema=False`. Docs stay public; Platform IP never appears in them."} for v in seen.values()]


def active_products(root: Path) -> list[str]:
    """EVERY product that has backend code, active or asleep, plus `seed` (the owner directive: asleep code is still
    served the day it wakes; the access-tier gate has no product carve-out) and `core`."""
    names = sorted(p.name for p in (root / "products").iterdir() if p.is_dir())  # product-scope: all — an asleep product is still served when it wakes
    out = [n for n in names if (root / "products" / n / "backend").is_dir()]
    return [o for o in out if o != "seed"] + (["seed"] if (root / "seed").is_dir() else [])


def classify_routes(root: Path | None = None) -> list[Route]:
    root = root or REPO_ROOT
    reg = load_registry(root)
    routes: list[Route] = []
    for prod in active_products(root):
        if prod == "seed":  # the seed workspace routers + the products/seed template product
            files = (_py_files(root / "seed/framework/backend") + _py_files(root / "seed/lib/backend")
                     + _py_files(root / "products/seed/backend"))
        else:
            files = _py_files(root / "products" / prod / "backend")
        if files:
            routes += _classify_set(prod, files, root, reg)
    return routes


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
_ROLES = ("authenticated", "anon", "public")
#: Supabase's built-in `ALTER DEFAULT PRIVILEGES ... IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated`
#: (prod relacl: `anon=arwdDxtm,authenticated=arwdDxtm`). "" = an unqualified name resolved via search_path=public.
_SUPABASE_DEFAULT_SCHEMAS = ("public", "")
_SUPABASE_DEFAULT_ROLES = ("anon", "authenticated")
_Q = r'"?(?:(?P<schema>[\w-]+)"?\."?)?(?P<table>[\w-]+)"?'
_GRANT_ALL_SCHEMA = re.compile(r"(?:GRANT|REVOKE)\s+[^;]*?ON\s+ALL\s+TABLES\s+IN\s+SCHEMA\s+\"?(?P<s>[\w-]+)\"?", re.I)
_GRANT_RE = re.compile(r"^\s*(?P<verb>GRANT|REVOKE)\s+(?P<privs>.+?)\s+ON\s+(?:TABLE\s+)?(?P<tables>.+?)\s+(?P<dir>TO|FROM)\s+(?P<roles>.+?)\s*$", re.I | re.S)
_DEFPRIV_RE = re.compile(r"ALTER\s+DEFAULT\s+PRIVILEGES\s+(?:FOR\s+ROLE\s+\w+\s+)?IN\s+SCHEMA\s+\"?(?P<s>[\w-]+)\"?\s+(?P<verb>GRANT|REVOKE)\s+.+?\s+ON\s+TABLES\s+(?:TO|FROM)\s+(?P<roles>.+)", re.I | re.S)
_CREATE_TABLE_RE = re.compile(r"^\s*CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _Q, re.I)
_DROP_TABLE_RE = re.compile(r"^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?" + _Q, re.I)
_POLICY_CREATE_RE = re.compile(r"^\s*CREATE\s+POLICY\s+\"?(?P<name>[\w-]+)\"?\s+ON\s+" + _Q + r"(?P<rest>.*)$", re.I | re.S)
_POLICY_ALTER_RE = re.compile(r"^\s*ALTER\s+POLICY\s+\"?(?P<name>[\w-]+)\"?\s+ON\s+" + _Q + r"(?P<rest>.*)$", re.I | re.S)
_POLICY_DROP_RE = re.compile(r"^\s*DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?\"?(?P<name>[\w-]+)\"?\s+ON\s+" + _Q, re.I)
_COMMENT_RE = re.compile(r"^\s*COMMENT\s+ON\s+TABLE\s+" + _Q + r"\s+IS\s+'(?P<c>[^']*)'", re.I)


def _roles_in(text: str) -> set[str]:
    return {r.lower() for r in re.findall(r"[\w]+", text)} & set(_ROLES)


@dataclass
class _Tbl:
    schema: str | None
    name: str
    product: str
    file: str
    grants: dict[str, str] = field(default_factory=dict)   # role -> file:line that granted
    policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    declared: str | None = None
    cols: set[str] = field(default_factory=set)


_SENSITIVE_COL = re.compile(
    r"(?<!input_)(?<!output_)(?<!total_)(?<!prompt_)(?<!completion_)(?<!cache_)(?<!max_)token(?!s\b|_count|_limit|_usage|_cost)"
    r"|secret|credential|api[_-]?key|senha|password|passwd|private[_-]?key", re.I)
_PII_COL = re.compile(r"telefone|phone|whatsapp|e?mail|cpf|cnpj|endereco|address", re.I)
#: a policy whose text is bound to the caller / their org cannot be read by anon, whatever role it names
_SCOPED_RE = re.compile(r"auth\.uid|auth\.jwt|current_org|org_id|my_org|current_setting\(|auth\.role", re.I)
_ADD_COL_RE = re.compile(r"^\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?" + _Q + r"\s+.*?ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(?P<col>\w+)\"?", re.I | re.S)
_OPEN_USING_RE = re.compile(r"using\s*\(\s*true\s*\)", re.I)
_WRITE_ONLY_RE = re.compile(r"\bFOR\s+(?:INSERT|UPDATE|DELETE)\b", re.I)


def _cols_of(create_stmt: str) -> set[str]:
    body = create_stmt[create_stmt.find("(") + 1:] if "(" in create_stmt else ""
    return {m.group(1).lower() for m in re.finditer(r"(?:^|,)\s*\"?([a-zA-Z_]\w*)\"?\s+(?:[A-Za-z]+\b)", body, re.M)
            if m.group(1).upper() not in {"PRIMARY", "UNIQUE", "CONSTRAINT", "CHECK", "FOREIGN", "EXCLUDE", "LIKE"}}


_DO_ARRAY_RE = re.compile(r":=\s*ARRAY\s*\[(?P<items>[^\]]*)\]", re.I)
_DO_REVOKE_RE = re.compile(r"(?P<verb>REVOKE|GRANT)\s+(?P<privs>[\w, ]+?)\s+ON\s+\"?(?P<schema>[\w-]+)\"?\.%I\s+(?:FROM|TO)\s+(?P<roles>[\w, ]+)", re.I)
_DO_POLICY_ROLES_RE = re.compile(r"roles\s*&&\s*ARRAY\s*\[(?P<roles>[^\]]*)\]", re.I)


def _apply_do_block(stmt: str, tables: dict[str, "_Tbl"], pschema: str | None) -> None:
    """The `DO $$ ... FOREACH t IN ARRAY v_tables LOOP EXECUTE format('REVOKE ALL ON s.%I FROM ...', t) ... $$` lockdown
    shape (agents 036): apply the literal-list REVOKE/GRANT and the policy DROP to the named tables that exist so far."""
    names: list[str] = []
    for m in _DO_ARRAY_RE.finditer(stmt):
        names += [x.lower() for x in re.findall(r"'([\w-]+)'", m.group("items"))]
    if not names:
        return
    for m in _DO_REVOKE_RE.finditer(stmt):
        roles = _roles_in(m.group("roles"))
        privs = m.group("privs").upper()
        schema = m.group("schema").lower()
        for n in names:
            t = tables.get(f"{schema}.{n}")
            if t is None:
                continue
            for r in roles:
                if m.group("verb").upper() == "REVOKE" and ("ALL" in privs or "SELECT" in privs):
                    t.grants.pop(r, None)
                elif m.group("verb").upper() == "GRANT":
                    t.grants[r] = "do-block"
    pm = _DO_POLICY_ROLES_RE.search(stmt)
    if pm and re.search(r"DROP\s+POLICY", stmt, re.I):
        named = _roles_in(pm.group("roles"))
        for n in names:
            for k, t in tables.items():
                if k.endswith("." + n) or k == n:
                    for pn in [pn for pn, pol in t.policies.items() if pol["roles"] & named]:
                        t.policies.pop(pn)


def _tbl_key(schema: str | None, name: str, product_schema: str | None) -> str:
    return f"{(schema or product_schema or '').lower()}.{name.lower()}".lstrip(".")


def _is_platform_table(key: str, bare_ok: bool, reg, declared: str | None) -> bool:
    if declared == "platform":
        return True
    schema, _, name = key.rpartition(".")
    for pat in reg.PLATFORM_TABLES:
        ps, _, pn = pat.rpartition(".")
        if fnmatch.fnmatch(name, pn) and (not ps or not schema or fnmatch.fnmatch(schema, ps)):
            return True
    return False


def _migration_files(root: Path, prod: str) -> list[Path]:
    d = root / "products" / prod / "backend" / "migrations"
    return sorted(d.glob("*.sql")) if d.is_dir() else []


def analyze_tables(root: Path | None = None) -> dict[str, Any]:
    """Replay each active product's migration chain statically; return its Platform-IP tables with the grants
    and policies that expose them to ``authenticated`` / ``anon``."""
    from noctusai_lib.testing.migration_parser import _strip_block_comments, _strip_line_comments, _walk_statements

    root = root or REPO_ROOT
    reg = load_registry(root)
    findings: list[dict] = []
    platform_tables: set[str] = set()
    grant_findings: list[dict] = []
    all_tables = 0
    for prod in active_products(root):
        files = _migration_files(root, prod)
        if not files:
            continue
        pschema = prod.replace("-", "_") if prod == "agents" else None
        tables: dict[str, _Tbl] = {}
        # schema -> roles with default table grants. `public` (and the unqualified search_path form) starts with the
        # Supabase default privileges (anon + authenticated ALL): a table created with no REVOKE INHERITS them.
        defaults: dict[str, set[str]] = defaultdict(set)
        for _s in _SUPABASE_DEFAULT_SCHEMAS:
            defaults[_s] = set(_SUPABASE_DEFAULT_ROLES)
        for f in files:
            rel = f.relative_to(root).as_posix()
            try:
                cleaned = _strip_block_comments(_strip_line_comments(f.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
            for st in _walk_statements(cleaned):
                head = st.lstrip()
                line = cleaned[: cleaned.find(st)].count("\n") + 1 if st in cleaned else 1
                where = f"{rel}:{line}"
                if m := _CREATE_TABLE_RE.match(head):
                    k = _tbl_key(m.group("schema"), m.group("table"), pschema)
                    t = tables.setdefault(k, _Tbl(m.group("schema"), m.group("table"), prod, rel))
                    t.cols |= _cols_of(head)
                    for r in defaults.get(k.rpartition(".")[0], ()):  # default privileges
                        t.grants[r] = where + " (default privileges)"
                elif (m := _ADD_COL_RE.match(head)) and head[:11].upper().startswith("ALTER TABLE"):
                    k = _tbl_key(m.group("schema"), m.group("table"), pschema)
                    if k in tables:
                        tables[k].cols.add(m.group("col").lower())
                elif m := _DROP_TABLE_RE.match(head):
                    tables.pop(_tbl_key(m.group("schema"), m.group("table"), pschema), None)
                elif m := _COMMENT_RE.match(head):
                    k = _tbl_key(m.group("schema"), m.group("table"), pschema)
                    c = m.group("c").strip().lower()
                    if k in tables and c.startswith("tier:"):
                        tables[k].declared = c.split(":", 1)[1].strip()
                elif m := _DEFPRIV_RE.match(head):
                    s = m.group("s").lower()
                    roles = _roles_in(m.group("roles"))
                    if m.group("verb").upper() == "GRANT":
                        defaults[s] |= roles
                    else:
                        defaults[s] -= roles
                elif m := _POLICY_CREATE_RE.match(head):
                    k = _tbl_key(m.group("schema"), m.group("table"), pschema)
                    rest = m.group("rest")
                    tm = re.search(r"\bTO\s+(.+?)(?:\s+USING\b|\s+WITH\s+CHECK\b|$)", rest, re.I | re.S)
                    roles = _roles_in(tm.group(1)) if tm else {"public"}
                    if k in tables:
                        tables[k].policies[m.group("name").lower()] = {"roles": roles, "text": rest, "where": where}
                elif m := _POLICY_ALTER_RE.match(head):
                    k = _tbl_key(m.group("schema"), m.group("table"), pschema)
                    pol = tables.get(k, _Tbl(None, "", prod, rel)).policies.get(m.group("name").lower())
                    if pol:
                        pol["text"] = pol["text"] + " " + m.group("rest")
                elif m := _POLICY_DROP_RE.match(head):
                    k = _tbl_key(m.group("schema"), m.group("table"), pschema)
                    if k in tables:
                        tables[k].policies.pop(m.group("name").lower(), None)
                elif head[:2].upper() == "DO":
                    _apply_do_block(head, tables, pschema)
                elif head[:5].upper() in ("GRANT", "REVOK"):
                    sm = _GRANT_ALL_SCHEMA.match(head)
                    gm = _GRANT_RE.match(head)
                    if not gm:
                        continue
                    grant = gm.group("verb").upper() == "GRANT"
                    roles = _roles_in(gm.group("roles"))
                    if not roles:
                        continue
                    if sm:
                        s = sm.group("s").lower()
                        targets = [t for k, t in tables.items() if k.rpartition(".")[0] == s]
                    else:
                        targets = []
                        for part in gm.group("tables").split(","):
                            pm = re.match(r"\s*(?:TABLE\s+)?" + _Q + r"\s*$", part, re.I)
                            if pm:
                                k = _tbl_key(pm.group("schema"), pm.group("table"), pschema)
                                if k in tables:
                                    targets.append(tables[k])
                    privs = gm.group("privs").upper()
                    for t in targets:
                        for r in roles:
                            if grant:
                                if "USAGE" in privs and "SELECT" not in privs and "ALL" not in privs:
                                    continue
                                t.grants[r] = where
                            else:
                                full = "ALL" in privs or "SELECT" in privs
                                if full:
                                    t.grants.pop(r, None)
        all_tables += len(tables)
        for k, t in sorted(tables.items()):
            platform = _is_platform_table(k, pschema is not None, reg, t.declared)
            anon_grant = "anon" in t.grants
            for n, pol in sorted(t.policies.items()):
                open_roles = pol["roles"] & {"anon", "public"}
                if not open_roles or _WRITE_ONLY_RE.search(pol["text"]):
                    continue
                sens = sorted(c for c in t.cols if _SENSITIVE_COL.search(c))
                if sens and not _SCOPED_RE.search(pol["text"]):
                    findings.append({
                        "kind": "policy-secret", "key": f"table:{k}:policy-secret:{n}", "table": k, "product": prod, "severity": "critical",
                        "issue": f"CRITICAL: `{k}` policy `{n}` ({pol['where']}) lets {','.join(sorted(open_roles))} read a table with secret-like column(s) "
                                 f"{sens}. Resolve the token server-side (backend route or a SECURITY DEFINER RPC taking the token as an argument), never through a readable table.",
                    })
                pii = sorted(c for c in t.cols if _PII_COL.search(c))
                if pii and not sens and not _SCOPED_RE.search(pol["text"]):
                    findings.append({
                        "kind": "policy-pii", "key": f"table:{k}:policy-pii:{n}", "table": k, "product": prod, "severity": "high",
                        "issue": f"`{k}` policy `{n}` ({pol['where']}) lets {','.join(sorted(open_roles))} read contact/PII column(s) {pii} with no "
                                 "caller/org scoping. If the row is meant to be public, expose it through a view of the public columns or a backend route.",
                    })
                if _OPEN_USING_RE.search(pol["text"]) and anon_grant:
                    findings.append({
                        "kind": "policy-open", "key": f"table:{k}:policy-open:{n}", "table": k, "product": prod, "severity": "high",
                        "issue": f"`{k}` policy `{n}` ({pol['where']}) is `USING (true)` for {','.join(sorted(open_roles))} and anon holds the grant: "
                                 "anonymous callers read every row. Scope it to authenticated/org or drop the anon grant.",
                    })
            if not platform:
                if t.declared not in ("org", "public") and not any(fnmatch.fnmatch(t.name.lower(), g) for g in reg.BROWSER_GRANT_ALLOWED_TABLES):
                    for r in sorted(r for r in t.grants if r in ("authenticated", "anon")):
                        grant_findings.append({
                            "kind": "browser-grant", "key": f"grant:{k}:{r}", "table": k, "product": prod, "severity": "medium",
                            "issue": f"`{k}` ({prod}) holds a `{r}` grant and declares no `tier:org|public`: RLS is its only protection. "
                                     "Declare the tier and drop the grant the browser does not need (defence in depth).",
                        })
                continue
            platform_tables.add(k)
            exposed = {r: w for r, w in t.grants.items() if r in ("authenticated", "anon")}
            weak = {
                n: p for n, p in t.policies.items()
                if p["roles"] & set(_ROLES) and not any(mk in p["text"].lower() for mk in reg.PLATFORM_ADMIN_POLICY_MARKERS)
            }
            for r, w in sorted(exposed.items()):
                findings.append({
                    "kind": "grant", "key": f"table:{k}:grant:{r}", "table": k, "product": prod,
                    "issue": f"Platform-IP table `{k}` still has a `{r}` table grant (last set at {w}): "
                             f"PostgREST serves it to every {r} session. REVOKE ALL ... FROM {r} (service role only).",
                })
            for n, p in sorted(weak.items()):
                findings.append({
                    "kind": "policy", "key": f"table:{k}:policy:{n}", "table": k, "product": prod,
                    "issue": f"Platform-IP table `{k}` has policy `{n}` (TO {','.join(sorted(p['roles']))}) at {p['where']} with no "
                             "platform-admin check: any org member passes it. DROP it (service role only) or require noctus_users.role='admin'.",
                })
    return {"findings": findings, "tables_scanned": all_tables, "platform_tables": sorted(platform_tables), "grant_findings": grant_findings}


_NEW_TABLE_ALLOW = "noc-allow: access-tier-table"


def check_new_tables_declared(root: Path | None, paths: list[str]) -> list[dict]:
    """DELTA: a NEW migration's ``CREATE TABLE`` must declare its tier (``COMMENT ON TABLE ... IS 'tier:x'``) or
    match the Platform-IP registry. Undeclared = refused."""
    from noctusai_lib.testing.migration_parser import _strip_block_comments, _strip_line_comments, _walk_statements

    root = root or REPO_ROOT
    reg = load_registry(root)
    out: list[dict] = []
    for rel in paths:
        f = root / rel
        if f.suffix != ".sql" or not f.exists():
            continue
        raw = f.read_text(encoding="utf-8")
        if _NEW_TABLE_ALLOW in raw:
            continue
        cleaned = _strip_block_comments(_strip_line_comments(raw))
        sts = list(_walk_statements(cleaned))
        declared = {
            _tbl_key(m.group("schema"), m.group("table"), None): m.group("c").strip().lower()
            for st in sts if (m := _COMMENT_RE.match(st.lstrip()))
        }
        for st in sts:
            m = _CREATE_TABLE_RE.match(st.lstrip())
            if not m:
                continue
            k = _tbl_key(m.group("schema"), m.group("table"), None)
            if not re.search(r"\b(?:GRANT|REVOKE)\b[^;]*\bON\b[^;]*\b" + re.escape(m.group("table")) + r"\b", cleaned, re.I):
                out.append({
                    "file": rel, "severity": "high",
                    "issue": f"{rel}: new table `{k}` has no explicit GRANT/REVOKE in its migration: it would INHERIT the schema's "
                             "default privileges (often `authenticated` ALL). State the grants (Platform IP: `REVOKE ALL ON "
                             f"{k} FROM authenticated, anon;`). KB § PATTERNS/security/access-tiers.md.",
                })
            tier = declared.get(k) or next((v for dk, v in declared.items() if dk.rpartition(".")[2] == m.group("table").lower()), None)
            if tier and tier.startswith("tier:") and tier.split(":", 1)[1].strip() in reg.TIERS:
                continue
            if _is_platform_table(k, True, reg, None):
                continue
            out.append({
                "file": rel, "severity": "high",
                "issue": f"{rel}: new table `{k}` declares no access tier. Add `COMMENT ON TABLE {k} IS 'tier:platform|org|service|public';` "
                         "(Platform IP = service role only). KB § PATTERNS/security/access-tiers.md.",
            })
    return out


# ---------------------------------------------------------------------------
# Baseline (ratchet) + keepers
# ---------------------------------------------------------------------------
def _route_violations(root: Path) -> dict[str, dict]:
    return {
        r.key: {"verdict": r.verdict, "file": r.file, "line": r.line, "note": r.note}
        for r in classify_routes(root) if r.verdict != "ok"
    }


def _table_violations(root: Path) -> dict[str, dict]:
    return {f["key"]: {"issue": f["issue"], "product": f["product"]} for f in analyze_tables(root)["findings"]}


# --- LLM streaming: delta events reach a browser only through the leak filter ---------------------------------
def analyze_streams(root: Path | None = None) -> list[dict]:
    root = root or REPO_ROOT
    reg = load_registry(root)
    out: list[dict] = []
    for prod in active_products(root):
        files = (_py_files(root / "seed/framework/backend") + _py_files(root / "seed/lib/backend")
                 + _py_files(root / "products/seed/backend")) if prod == "seed" else _py_files(root / "products" / prod / "backend")
        for p in files:
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            rel = p.relative_to(root).as_posix()
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                own = [n for n in ast.walk(fn)]
                pubs = [
                    n for n in own if isinstance(n, ast.Call) and _call_name(n) in reg.STREAM_PUBLISH_CALLS and any(
                        isinstance(a, ast.Constant) and a.value in reg.STREAM_EVENT_MARKERS for a in n.args)
                ]
                if not pubs:
                    continue
                names = {_tail(n) for n in own if isinstance(n, (ast.Name, ast.Attribute))} | {_call_name(n) for n in own if isinstance(n, ast.Call)}
                if names & reg.LEAK_FILTER_NAMES:
                    continue
                out.append({
                    "key": f"stream:{rel}:{fn.name}", "file": rel, "line": pubs[0].lineno,
                    "issue": f"[stream] `{fn.name}` publishes a partial/delta LLM event to a browser without a leak filter "
                             f"(one of {sorted(reg.LEAK_FILTER_NAMES)}): a streamed delta can reproduce the prompt before the "
                             "whole-message guard runs. Wrap the delta in the filter whenever a guard is active.",
                })
    return out


# --- leak fingerprint: every prompt-derived source is registered at the one seam -------------------------------
def analyze_fingerprint(root: Path | None = None) -> list[dict]:
    root = root or REPO_ROOT
    reg = load_registry(root)
    if "agents" not in active_products(root):
        return []
    rel, seam = reg.LEAK_FINGERPRINT_SEAM
    out: list[dict] = []

    def _f(key: str, issue: str, file: str = rel) -> None:
        out.append({"key": f"fingerprint:{key}", "file": file, "line": 0, "issue": f"[fingerprint] {issue}"})

    seam_file = root / rel
    if not seam_file.exists():
        _f("seam-missing", f"the fingerprint seam {rel}::{seam} does not exist: coverage is UNMEASURABLE (never green).")
        return out
    tree = ast.parse(seam_file.read_text(encoding="utf-8"))
    tokens: set[str] = set()
    found = False
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and (fn.name == seam or fn.name.startswith(seam + "_")):
            found = True
            for n in ast.walk(fn):
                if isinstance(n, ast.Attribute):
                    tokens.add(n.attr)
                elif isinstance(n, ast.Name):
                    tokens.add(n.id)
                elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                    tokens.add(n.value)
    if not found:
        _f("seam-missing", f"function `{seam}` not found in {rel}: coverage is UNMEASURABLE (never green).")
        return out
    for key, aliases in sorted(reg.LEAK_FINGERPRINT_SOURCES.items()):
        if not set(aliases) & tokens:
            _f(f"source:{key}", f"`{seam}` never references the `{key}` source (accepted spellings {list(aliases)}): "
                                "content of that kind reaches the model but a reply reproducing it is not detected.")
    treg = root / reg.LEAK_TOOL_REGISTRY
    if treg.exists():
        names = [
            n.args[0].value for n in ast.walk(ast.parse(treg.read_text(encoding="utf-8")))
            if isinstance(n, ast.Call) and _call_name(n) == "ToolDef" and n.args
            and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
        ]
        for name in names:
            if name in reg.PROMPT_DERIVED_TOOLS:
                if reg.PROMPT_DERIVED_TOOLS[name] not in reg.LEAK_FINGERPRINT_SOURCES:
                    _f(f"tool:{name}", f"tool `{name}` returns prompt-derived content but its source "
                                       f"`{reg.PROMPT_DERIVED_TOOLS[name]}` is not a registered fingerprint source.", reg.LEAK_TOOL_REGISTRY)
            elif name not in reg.NOT_PROMPT_DERIVED_TOOLS:
                _f(f"tool-unclassified:{name}", f"tool `{name}` is not classified: say whether its result is prompt-derived "
                                                "(PROMPT_DERIVED_TOOLS -> fingerprint source) or not (NOT_PROMPT_DERIVED_TOOLS).",
                   reg.LEAK_TOOL_REGISTRY)
    else:
        _f("tool-registry-missing", f"{reg.LEAK_TOOL_REGISTRY} not found: tool coverage is UNMEASURABLE.", reg.LEAK_TOOL_REGISTRY)
    return out


SECTIONS = ("routes", "tables", "grants", "streams", "fingerprint", "schema")


def _all_violations(root: Path) -> dict[str, dict]:
    return {
        "routes": _route_violations(root),
        "tables": _table_violations(root),
        "grants": {f["key"]: {"issue": f["issue"], "product": f["product"]} for f in analyze_tables(root)["grant_findings"]},
        "streams": {f["key"]: {"file": f["file"], "issue": f["issue"]} for f in analyze_streams(root)},
        "fingerprint": {f["key"]: {"file": f["file"], "issue": f["issue"]} for f in analyze_fingerprint(root)},
    }


def _new_only(section: str, current: dict[str, dict], root: Path) -> list[tuple[str, dict]]:
    """Violations with no LIVE ledger row (open | in-progress | accepted): the ratchet IS the findings ledger."""
    from tools.noctus.dev import access_tier_findings as ledger

    live = ledger.known_live_keys(root)
    return [(k, v) for k, v in sorted(current.items()) if k not in live]


def check_routes(root: Path | None = None) -> list[dict]:
    """Every route in every active product resolves to a tier; Platform IP never sits behind a weaker gate.
    A violation is a failure unless the ratchet baseline already lists it."""
    root = root or REPO_ROOT
    return [{
        "file": v["file"], "line": v["line"], "severity": "high" if v["verdict"] == "too-open" else "medium",
        "issue": f"[{v['verdict']}] {k}: {v['note']}. Put it behind a platform-admin dependency, or declare "
                 "`@access_tier(...)` (noctusai_lib.api.access_tiers). KB § PATTERNS/security/access-tiers.md.",
    } for k, v in _new_only("routes", _route_violations(root), root)]


def check_tables(root: Path | None = None) -> list[dict]:
    """Table exposure: Platform-IP tables carry no `authenticated`/`anon` grant and no non-admin policy; no anon/PUBLIC
    policy on a table with a secret-like column; no anon `USING (true)`; no undeclared browser grant. Ratcheted."""
    root = root or REPO_ROOT
    out = []
    # BLOCKING only what is near-zero false-positive; PII-column detection (policy-pii) and the browser-grant defence-in-depth
    # class are heuristic => recorded in the ledger, warn-only until measured precise (SRE book ch.12).
    for sec in ("tables",):
        cur = {k: v for k, v in _table_violations(root).items() if ":policy-pii:" not in k}
        out += [{"file": k, "line": 0, "severity": "high", "issue": v["issue"] + " KB § PATTERNS/security/access-tiers.md."}
                for k, v in _new_only(sec, cur, root)]
    return out


def check_streams(root: Path | None = None) -> list[dict]:
    root = root or REPO_ROOT
    cur = {f["key"]: f for f in analyze_streams(root)}
    return [{"file": v["file"], "line": v["line"], "severity": "high", "issue": v["issue"] + " KB § PATTERNS/security/access-tiers.md."}
            for k, v in _new_only("streams", cur, root)]


def check_fingerprint(root: Path | None = None) -> list[dict]:
    root = root or REPO_ROOT
    cur = {f["key"]: f for f in analyze_fingerprint(root)}
    return [{"file": v["file"], "line": 0, "severity": "high", "issue": v["issue"] + " KB § PATTERNS/security/access-tiers.md."}
            for k, v in _new_only("fingerprint", cur, root)]


# --- effective state (prod) vs declared tiers -------------------------------------------------------------------
EXPOSURE_QUERIES: dict[str, str] = {
    "grants": "SELECT table_schema, table_name, grantee, privilege_type FROM information_schema.role_table_grants "
              "WHERE grantee IN ('authenticated','anon','PUBLIC') AND privilege_type IN ('SELECT','INSERT','UPDATE','DELETE') "
              "AND table_schema NOT IN ('pg_catalog','information_schema')",
    "policies": "SELECT schemaname, tablename, policyname, roles, cmd, qual, with_check FROM pg_policies "
                "WHERE roles && ARRAY['authenticated','anon','public']::name[]",
    "columns": "SELECT table_schema, table_name, column_name FROM information_schema.columns WHERE column_name ~* "
               "'(token|secret|credential|api_?key|senha|password|private_?key)' AND table_schema NOT IN ('pg_catalog','information_schema')",
    "db_schemas": "SELECT setting FROM (SELECT unnest(string_to_array(rolconfig::text,',')) AS setting FROM pg_roles "
                  "WHERE rolname='authenticator') s WHERE setting LIKE '%pgrst.db_schemas%'",
}


#: Supabase advisor lint name -> OUR finding kind it corroborates. Everything we find that is not here is a blind spot of the
#: advisor (reported as `advisor_blind_spots`): policy-secret / policy-pii (anon read of token/secret/PII columns), grant / policy
#: on Platform-IP tables (needs OUR tier declaration), inactive-schema-served, browser-grant.
ADVISOR_COVERS: dict[str, str] = {"rls_policy_always_true": "policy-open", "policy_exists_rls_disabled": "rls-off",
                                  "rls_disabled_in_public": "rls-off"}


def _inactive_schemas(root: Path) -> dict[str, str]:
    """schema -> inactive product slug (schemas the product's own migrations create, plus its slug normalised)."""
    active = set((root / "deploy/fleet/active-scope.txt").read_text(encoding="utf-8").split()) if (root / "deploy/fleet/active-scope.txt").exists() else set()
    out: dict[str, str] = {}
    for d in sorted((root / "products").iterdir()):  # product-scope: all — finding the schemas of ASLEEP products is the point
        if not d.is_dir() or d.name in active:
            continue
        out[d.name.replace("-", "_")] = d.name
        for f in sorted((d / "backend" / "migrations").glob("*.sql")) if (d / "backend" / "migrations").is_dir() else []:
            for m in re.finditer(r"CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?([\w-]+)", f.read_text(encoding="utf-8", errors="ignore"), re.I):
                out[m.group(1).lower()] = d.name
    return out


def diff_exposure(effective: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Diff the EFFECTIVE prod state (rows from `EXPOSURE_QUERIES`, run read-only through the supabase connector)
    against the declared tiers. `effective` = {grants, policies, db_schemas, columns?}. Classes: (a) anon/PUBLIC
    policy on a table with a secret-like column (critical, any row count); (b) PUBLIC/anon `USING (true)` where anon
    holds the grant; (c) a browser grant on a table not declared `tier:org|public`; (d) a schema of an INACTIVE product
    served by the data API; plus every declared Platform-IP table with a grant or a non-admin policy. Anything missing
    from `effective` is reported `unmeasured`, never green."""
    root = root or REPO_ROOT
    reg = load_registry(root)
    an = analyze_tables(root)
    declared = set(an["platform_tables"])
    findings: list[dict] = []
    unmeasured = [k for k in ("grants", "policies", "db_schemas", "columns") if effective.get(k) is None]  # advisors are optional
    grants = effective.get("grants") or []
    anon_tables = {f"{g.get('table_schema', '')}.{g.get('table_name', '')}".lower() for g in grants if str(g.get("grantee", "")).lower() in ("anon", "public")}
    secret_cols: dict[str, list[str]] = defaultdict(list)
    for c in effective.get("columns") or []:
        if _SENSITIVE_COL.search(str(c.get("column_name", ""))):
            secret_cols[f"{c.get('table_schema', '')}.{c.get('table_name', '')}".lower()].append(c["column_name"])
    undeclared_grants: Counter = Counter()
    for g in grants:
        k = f"{g.get('table_schema', '')}.{g.get('table_name', '')}".lower()
        who = str(g.get("grantee", "")).lower()
        if who not in ("authenticated", "anon", "public"):
            continue
        if k in declared:
            findings.append({"kind": "grant", "table": k, "severity": "critical", "issue": f"EFFECTIVE: `{g['grantee']}` holds {g.get('privilege_type')} on Platform-IP `{k}` in prod"})
        elif g.get("privilege_type") == "SELECT":
            undeclared_grants[g.get("table_schema", "")] += 1
    for p in effective.get("policies") or []:
        k = f"{p.get('schemaname', '')}.{p.get('tablename', '')}".lower()
        text = f"{p.get('qual') or ''} {p.get('with_check') or ''}".lower()
        roles = {r.strip().lower() for r in re.findall(r"[\w]+", str(p.get("roles") or ""))}
        open_roles = roles & {"anon", "public"}
        if k in declared and not any(m in text for m in reg.PLATFORM_ADMIN_POLICY_MARKERS):
            findings.append({"kind": "policy", "table": k, "severity": "critical", "issue": f"EFFECTIVE: policy `{p.get('policyname')}` TO {p.get('roles')} on Platform-IP `{k}` has no platform-admin check"})
        if open_roles and str(p.get("cmd", "")).upper() in ("SELECT", "ALL", "") and secret_cols.get(k) and not _SCOPED_RE.search(text):
            findings.append({"kind": "policy-secret", "table": k, "severity": "critical", "issue": f"EFFECTIVE CRITICAL: policy `{p.get('policyname')}` lets {sorted(open_roles)} read `{k}` with secret-like column(s) {secret_cols[k]}"})
        if open_roles and re.fullmatch(r"\(*\s*true\s*\)*", str(p.get("qual") or "").strip().lower()) and k in anon_tables:
            findings.append({"kind": "policy-open", "table": k, "severity": "high", "issue": f"EFFECTIVE: policy `{p.get('policyname')}` ({sorted(open_roles)}, qual true) and anon holds the grant on `{k}`: every row is anonymous-readable"})
    exposed = {x.strip().lower() for x in str(effective.get("db_schemas") or "").replace("pgrst.db_schemas=", "").replace('"', "").split(",") if x.strip()}
    inactive = _inactive_schemas(root)
    for sch in sorted(exposed & set(inactive)):
        findings.append({"kind": "inactive-schema-served", "table": sch, "severity": "high", "issue": f"schema `{sch}` belongs to INACTIVE product `{inactive[sch]}` yet the data API serves it (pgrst.db_schemas): drop it from the list while the product sleeps"})
    # Supabase's own security advisor (splinter, via get_advisors -> supabase_advisors filter) is the vendor-maintained lint
    # set: its ERROR/WARN rows join the findings; our own SQL stays only for what it misses (see ADVISOR_COVERS).
    advisor_hits = 0
    for a in effective.get("advisors") or []:
        lvl = str(a.get("level", "")).upper()
        if lvl not in ("ERROR", "WARN"):
            continue
        md = a.get("metadata") or {}
        tbl = f"{md.get('schema', '')}.{md.get('name', '')}".strip(".").lower() or str(a.get("cache_key", ""))
        findings.append({"kind": f"advisor:{a.get('name', '?')}", "table": tbl, "severity": "high" if lvl == "ERROR" else "medium",
                         "issue": f"SUPABASE ADVISOR {lvl} `{a.get('name')}` on `{tbl}`: {str(a.get('detail') or a.get('title') or '')[:200]}"})
        advisor_hits += 1
    ours = {f["kind"] for f in findings if not f["kind"].startswith("advisor:")}
    corroborated = {ADVISOR_COVERS[n] for n in {str(a.get("name")) for a in effective.get("advisors") or []} if n in ADVISOR_COVERS}
    return {"ok": not findings and not unmeasured, "findings": findings, "unmeasured": unmeasured,
            "advisor_rows": advisor_hits, "advisor_blind_spots": sorted(ours - corroborated),
            "exposed_schemas": sorted(exposed), "declared_platform_tables": len(declared),
            "select_grants_on_undeclared_tables_by_schema": dict(undeclared_grants)}


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
def summarize(routes: list[Route]) -> dict[str, Any]:
    return {
        "total": len(routes),
        "by_tier": dict(Counter(r.tier or "UNCLASSIFIED" for r in routes)),
        "by_verdict": dict(Counter(r.verdict for r in routes)),
        "by_product": {p: dict(Counter(r.tier or "UNCLASSIFIED" for r in routes if r.product == p))
                       for p in sorted({r.product for r in routes})},
    }


def render_catalog(root: Path | None = None) -> str:
    root = root or REPO_ROOT
    routes = classify_routes(root)
    tv = analyze_tables(root)
    s = summarize(routes)
    L = [
        "# Endpoint access-tier catalog",
        "",
        "> GENERATED by `python mcp/noctusai/cli.py --access-tier-catalog --write` (tool `noctus.dev.access_tier_catalog`). "
        "Never hand-edit. Method: `KB § PATTERNS/security/access-tiers.md`. Scope: EVERY product backend, active or asleep "
        "(+ the seed routers every product mounts). Paths are best-effort (router prefix + `include_router` prefix).",
        "",
        f"**{s['total']} endpoints.** Tier: " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_tier"].items())) +
        ". Verdict: " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_verdict"].items())) + ".",
        f"Table findings (Platform-IP exposure, anon/PUBLIC policies on secret/PII tables, open `USING (true)`): {len(tv['findings'])}; "
        f"browser grants on tables without `tier:org|public`: {len(tv['grant_findings'])} (per table in findings.ndjson); {tv['tables_scanned']} tables scanned.",
        "",
        "| product | endpoints | " + " | ".join(["platform", "service", "org", "public", "UNCLASSIFIED"]) + " |",
        "|---|---:|" + "---:|" * 5,
    ]
    for p, c in s["by_product"].items():
        L.append(f"| {p} | {sum(c.values())} | " + " | ".join(str(c.get(t, 0)) for t in ("platform", "service", "org", "public", "UNCLASSIFIED")) + " |")
    L += ["", "## Too-open and unclear (the work list; each row is one remediation marker)", ""]
    flagged = [r for r in routes if r.verdict != "ok"]
    from tools.noctus.dev import findings_ledger as _gl

    since = min((r["found_at"] for r in _gl.load(_gl.get("access-tier"), root).values()), default="2026-11-05")
    for r in sorted(flagged, key=lambda r: (r.verdict != "too-open", r.product, r.path)):
        L.append(
            f"- NOC-REMEDIATE[access-tier]: {r.product} `{r.method} {r.path}` is {r.verdict} (tier {r.tier or 'none'}; "
            f"gates {', '.join(r.gates) or 'none'}): {r.note} — {since}")
    if tv["findings"]:
        L += ["", "## Platform-IP tables exposed", ""]
        L += [f"- NOC-REMEDIATE[access-tier]: {f['issue']} — {since}" for f in tv["findings"]]
    docs = docs_exposure(root)
    L += ["", "## API docs exposure (owner decision: `/docs` + `/openapi.json` stay PUBLIC; every documented route is gated by its tier -- proven by the schema-driven 401/403 contract test -- and Platform IP is left out of the public schema)", ""]
    L += [f"- {p}: {state}" for p, state in docs.items()]
    pub = [r for r in routes if r.tier == "public"]
    L += ["", "## Public routes by category (closed allowlist: landing, auth, pricing-checkout, legal-consent, lead-capture)", ""]
    if not pub:
        L.append("_No route currently declares `@access_tier(\"public\", category=...)`; every anonymous-reachable route is in the baseline as unclear._")
    for cat in load_registry(root).PUBLIC_CATEGORIES:
        rows = [r for r in pub if r.category == cat]
        L += [f"### {cat} ({len(rows)})", ""] + [f"- {r.product} `{r.method} {r.path}`" for r in rows] + [""]
    signed = [r for r in routes if r.category.startswith("signed:")]
    L += ["## Signed / service routes reachable from the network (verification call required)", ""]
    L += [f"- {r.product} `{r.method} {r.path}` ({r.category})" for r in signed] or ["_none_"]
    extra = analyze_streams(root) + analyze_fingerprint(root)
    if extra:
        L += ["", "## LLM streaming + leak-fingerprint gaps", ""]
        L += [f"- NOC-REMEDIATE[access-tier]: {f['issue']} ({f['file']}) — {since}" for f in extra]
    L += ["", "## All endpoints", ""]
    for p in s["by_product"]:
        L += [f"### {p}", "", "| method path | tier | category | gates (resolved) | Platform IP | verdict |", "|---|---|---|---|---|---|"]
        for r in routes:
            if r.product == p:
                L.append(
                    f"| `{r.method} {r.path}` | {r.tier or '-'} | {r.category or '-'} | {', '.join(r.gates) or '-'} | "
                    f"{'yes (' + r.ip_reason + ')' if r.platform_ip else 'no'} | {r.verdict} |")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def docs_exposure(root: Path) -> dict[str, str]:
    """product -> whether its app disables the interactive docs / schema (`docs_url=None`, `openapi_url=None`) or leaves FastAPI's defaults."""
    out: dict[str, str] = {}
    for prod in active_products(root):
        files = (_py_files(root / "seed/framework/backend") + _py_files(root / "seed/lib/backend")) if prod == "seed" \
            else _py_files(root / "products" / prod / "backend")
        state = "default (docs + openapi.json served)"
        for p in files:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if ("FastAPI(" in txt or "create_product_app(" in txt or "create_app(" in txt) and re.search(r"(openapi_url|docs_url)\s*=\s*None", txt):
                state = "locked (openapi_url/docs_url=None)"
                break
            if "docs_enabled" in txt or "ENABLE_DOCS" in txt or "docs_url=" in txt:
                state = "configurable (docs_url/docs_enabled in app factory)"
        out[prod] = state
    return out


def access_tier_catalog(write: bool = False, worktree_path: str | None = None) -> dict:
    """Generate the endpoint catalog. ``write=False`` (default) returns the summary + the flagged rows only."""
    root = Path(worktree_path) if worktree_path else REPO_ROOT
    routes = classify_routes(root)
    out: dict[str, Any] = {"summary": summarize(routes), "flagged": [
        {"verdict": r.verdict, "product": r.product, "route": f"{r.method} {r.path}", "tier": r.tier, "gates": r.gates, "note": r.note}
        for r in routes if r.verdict != "ok"][:200]}
    if write:
        p = root / CATALOG_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_catalog(root), encoding="utf-8")
        out["written"] = [str(CATALOG_REL)]
    return out


def register(server) -> None:
    @server.tool(
        name="noctus.dev.access_tier_catalog",
        description=(
            "Classify EVERY HTTP endpoint of every product (active or asleep) into an access tier (platform | service | org | "
            "public | unclassified) from its auth dependencies, flag Platform IP behind a weaker gate (too-open) "
            "and undeclared routes (unclear). Default returns counts + the flagged rows; write=true regenerates "
            "project-history/access-tiers/endpoint-catalog.md. worktree_path = the tree to read."
        ),
    )
    def _catalog(write: bool = False, worktree_path: str | None = None) -> dict:
        return access_tier_catalog(write=write, worktree_path=worktree_path)

    @server.tool(
        name="noctus.dev.access_tier_exposure",
        description=(
            "Diff the EFFECTIVE prod exposure against the declared Platform-IP tables. With no args returns the three "
            "read-only SQL queries (role_table_grants for authenticated/anon, pg_policies TO authenticated, pgrst.db_schemas) "
            "to run through the supabase connector; pass their rows back as grants / policies / db_schemas to get the drift "
            "findings (unmeasured inputs are reported, never green); reconcile=true also records them in the findings ledger. Used by the security audit and the daily ops routine."
        ),
    )
    def _exposure(grants: list[dict] | None = None, policies: list[dict] | None = None, db_schemas: str | None = None,
                  columns: list[dict] | None = None, reconcile: bool = False, worktree_path: str | None = None) -> dict:
        if grants is None and policies is None and db_schemas is None and columns is None:
            return {"queries": EXPOSURE_QUERIES}
        root = Path(worktree_path) if worktree_path else REPO_ROOT
        out = diff_exposure({"grants": grants, "policies": policies, "db_schemas": db_schemas, "columns": columns}, root)
        if reconcile:  # opt-in write: new effective findings are opened, fully-measured clean ones closed in the ledger
            from tools.noctus.dev import access_tier_findings

            out["ledger"] = access_tier_findings.reconcile_effective(out, root)
        return out


__all__ = ["access_tier_catalog", "analyze_tables", "check_new_tables_declared", "check_routes", "check_tables",
           "classify_routes", "register", "render_catalog", "check_streams", "check_fingerprint", "diff_exposure", "EXPOSURE_QUERIES"]
