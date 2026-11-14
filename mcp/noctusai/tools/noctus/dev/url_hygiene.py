"""URL-hygiene keepers (security standard S1 + S4): long-lived signed URLs and PII in query strings.

Two AST detectors, delegated to from ``compliance.py`` (shim functions of the same name):

* ``check_signed_url_ttl`` -- a signed-URL creation (seed seam ``StorageBackend.signed_url``, raw
  ``create_signed_url(s)``) whose TTL resolves (int literal, simple int arithmetic, module-level int
  constant) to more than ``MAX_TTL_SECONDS`` and carries no reason kwarg. A signed URL is a bearer
  credential that lands in logs, history and referers; lifetime is the blast radius.
* ``check_pii_query_params`` -- a FastAPI route/dependency parameter that becomes a URL query param
  (explicit ``Query(...)`` default, or a plain scalar on a GET/DELETE handler) whose name is PII-like.
  Query strings are logged by every proxy and CDN; PII belongs in a POST body.

Both RATCHET against per-file baselines in ``mcp/noctusai/tests/`` (a file may carry fewer, never more;
``--lower-*-baseline`` lowers). Escapes carry a reason: ``ttl_reason=``/``reason=`` kwarg on the call;
``# pii-query-ok: <reason>`` on the parameter line; ``# signed-url-ttl-ok: <reason>`` for TTL.

KB § PATTERNS/security/url-hygiene.md
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

MAX_TTL_SECONDS = 600
_BASELINES = {
    "ttl": ("mcp", "noctusai", "tests", "signed_url_ttl_baseline.json"),
    "pii": ("mcp", "noctusai", "tests", "pii_query_params_baseline.json"),
}
_SKIP_PARTS = frozenset({"tests", "migrations", "node_modules", ".venv", "venv", "__pycache__", "e2e", "fixtures"})

# ── scanning scope ───────────────────────────────────────────────────────────
def _scan_roots(root: Path) -> list[Path]:
    from tools.noctus.dev.compliance import _postgrest_scan_roots  # same ACTIVE-product choke point

    return _postgrest_scan_roots(root)


def _py_files(root: Path):
    for scan_root in _scan_roots(root):
        for path in sorted(scan_root.rglob("*.py")):
            if any(p in _SKIP_PARTS for p in path.parts):
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            yield path


def _parse(text: str):
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


# ── signed-url TTL ───────────────────────────────────────────────────────────
_SIGN_FUNCS = frozenset({"signed_url", "create_signed_url", "create_signed_urls"})
_TTL_KWARGS = ("expires_in_seconds", "expires_in", "ttl_seconds", "ttl", "expiry", "expires")
_REASON_KWARGS = frozenset({"ttl_reason", "reason"})  # NOC-REMEDIATE[signed-url-reason-kwarg-name]: the seam's final kwarg name is being set on feat/sec-signed-url-ttl-clamp; both accepted until confirmed — 2026-11-14


def _module_int_consts(tree: ast.Module) -> dict[str, int]:
    consts: dict[str, int] = {}
    for node in tree.body:
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target, value = node.target.id, node.value
        if target is not None:
            n = _int_value(value, consts)
            if n is not None:
                consts[target] = n
    return consts


def _int_value(node: ast.AST, consts: dict[str, int]) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Add, ast.Sub)):
        a, b = _int_value(node.left, consts), _int_value(node.right, consts)
        if a is None or b is None:
            return None
        return a * b if isinstance(node.op, ast.Mult) else a + b if isinstance(node.op, ast.Add) else a - b
    return None


_TTL_CONST_NAME = re.compile(r"(SIGNED_URL.*(TTL|SECONDS|EXPIR)|URL_TTL)", re.I)
_TTL_OK = re.compile(r"#\s*signed-url-ttl-ok:\s*\S")


def signed_url_ttl_hits(text: str) -> list[tuple[int, int]]:
    """``[(line, ttl_seconds)]`` above the cap with no reason: signed-URL calls, a ``signed_url``
    definition whose TTL parameter defaults above it, and module-level ``*SIGNED_URL*TTL*`` constants."""
    if "signed_url" not in text.lower():
        return []
    tree = _parse(text)
    if tree is None:
        return []
    lines = text.splitlines()
    consts = _module_int_consts(tree)
    hits: list[tuple[int, int]] = []

    def ok(line: int) -> bool:
        return 0 < line <= len(lines) and bool(_TTL_OK.search(lines[line - 1]))

    for node in tree.body:  # module-level TTL constants
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(tgt, ast.Name) and _TTL_CONST_NAME.search(tgt.id) and tgt.id in consts \
                    and consts[tgt.id] > MAX_TTL_SECONDS and not ok(node.lineno):
                hits.append((node.lineno, consts[tgt.id]))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _SIGN_FUNCS:
            a = node.args
            pairs = list(zip(a.kwonlyargs, a.kw_defaults)) + list(
                zip((a.posonlyargs + a.args)[len(a.posonlyargs + a.args) - len(a.defaults):], a.defaults))
            for arg, default in pairs:
                if arg.arg in _TTL_KWARGS and default is not None and not ok(arg.lineno):
                    ttl = _int_value(default, consts)
                    if ttl is not None and ttl > MAX_TTL_SECONDS:
                        hits.append((arg.lineno, ttl))
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name not in _SIGN_FUNCS:
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        if any(r in kw for r in _REASON_KWARGS) or any(k.arg is None for k in node.keywords) or ok(node.lineno):
            continue
        ttl_node = next((kw[k] for k in _TTL_KWARGS if k in kw), None)
        if ttl_node is None and name in ("create_signed_url", "create_signed_urls") and len(node.args) >= 2:
            ttl_node = node.args[1]  # storage3: create_signed_url(path, expires_in)
        if ttl_node is None:
            continue
        ttl = _int_value(ttl_node, consts)
        if ttl is not None and ttl > MAX_TTL_SECONDS:
            hits.append((node.lineno, ttl))
    return sorted(set(hits))


# ── PII in query params ──────────────────────────────────────────────────────
# Decision (researched on the real tree 2026-11-14): flagged = names that identify a person on their
# own. NOT flagged: bare `nome`/`name` (overwhelmingly a resource-search filter), `cep` (area-level,
# not identifying). `nome_completo`/`full_name` ARE flagged. Matching is on name TOKENS so
# `cliente_email`, `email_contato`, `telefone_lead` match while `emailed_at`/`phonebook` do not.
_PII_TOKENS = frozenset({
    "email", "cpf", "cnpj", "rg", "telefone", "phone", "celular", "whatsapp", "fone", "endereco",
})
_PII_EXACT = frozenset({"documento"})  # bare `documento` = a CPF/CNPJ lookup key; `tipo_documento` is not
_PII_PHRASES = ("e_mail", "full_name", "nome_completo", "cpf_cnpj", "numero_documento")
_ROUTE_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "api_route"})
_BODYISH = frozenset({"Body", "Depends", "Header", "Cookie", "Path", "Form", "File", "Security"})
_SCALARS = frozenset({"str", "int", "float", "bool", "UUID", "date", "datetime", "Optional", "Annotated"})
_PII_OK = re.compile(r"#\s*pii-query-ok:\s*\S")


def is_pii_name(name: str) -> bool:
    low = name.lower()
    if low in _PII_EXACT:
        return True
    if any(p in low for p in _PII_PHRASES):
        return True
    return any(tok in _PII_TOKENS for tok in re.split(r"[_\W]+", low))


def _default_kind(default: ast.AST | None) -> str:
    if isinstance(default, ast.Call):
        f = default.func
        fname = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        if fname == "Query":
            return "query"
        if fname in _BODYISH:
            return "other"
    return "plain" if default is None or isinstance(default, ast.Constant) else "other"


def _annotation_is_scalar(ann: ast.AST | None) -> bool:
    if ann is None:
        return True
    names = {n.id for n in ast.walk(ann) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(ann) if isinstance(n, ast.Attribute)
    }
    if any(n in _BODYISH for n in names):
        # Annotated[str, Query()] still counts: look for Query below
        return any(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "Query"
                   for n in ast.walk(ann))
    return bool(names) and names <= (_SCALARS | {"None"})


def _route_info(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, set[str], str]:
    """``(is_route, path_params, verb)``."""
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute) and target.attr in _ROUTE_VERBS:
            path = ""
            if isinstance(dec, ast.Call) and dec.args and isinstance(dec.args[0], ast.Constant):
                path = str(dec.args[0].value)
            return True, set(re.findall(r"{([^}:]+)", path)), target.attr
    return False, set(), ""


def pii_query_param_hits(text: str) -> list[tuple[int, str, str]]:
    """``[(line, function, param)]`` PII-named params that are URL query params, minus escapes."""
    if "Query" not in text and "@" not in text:
        return []
    tree = _parse(text)
    if tree is None:
        return []
    lines = text.splitlines()
    hits: list[tuple[int, str, str]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_route, path_params, verb = _route_info(fn)
        a = fn.args
        pos = a.posonlyargs + a.args
        pairs = list(zip(pos, [None] * (len(pos) - len(a.defaults)) + list(a.defaults)))
        pairs += list(zip(a.kwonlyargs, a.kw_defaults))
        for arg, default in pairs:
            if not is_pii_name(arg.arg) or arg.arg in path_params:
                continue
            kind = _default_kind(default)
            explicit = kind == "query" or (
                isinstance(arg.annotation, ast.Subscript) and any(
                    isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "Query"
                    for n in ast.walk(arg.annotation)
                )
            )
            implicit = is_route and verb in ("get", "delete") and kind == "plain" and _annotation_is_scalar(arg.annotation)
            if not (explicit or implicit):
                continue
            span = range(arg.lineno, (getattr(default, "end_lineno", None) or arg.lineno) + 1)
            if any(_PII_OK.search(lines[i - 1]) for i in span if i <= len(lines)):
                continue
            hits.append((arg.lineno, fn.name, arg.arg))
    return sorted(set(hits))


# ── counts / baselines / keepers ─────────────────────────────────────────────
def _counts(root: Path, fn, needle: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for path in _py_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        n = len(fn(text))
        if n:
            out[path.relative_to(root).as_posix()] = n
    return out


def signed_url_ttl_counts(root: Path) -> dict[str, int]:
    return _counts(root, signed_url_ttl_hits, "signed_url")


def pii_query_param_counts(root: Path) -> dict[str, int]:
    return _counts(root, pii_query_param_hits, "Query")


def _load_baseline(root: Path, key: str) -> dict[str, int]:
    try:
        return dict(json.loads(root.joinpath(*_BASELINES[key]).read_text(encoding="utf-8")).get("arquivos", {}))
    except (OSError, ValueError):
        return {}


def _ratchet(root: Path, key: str, current: dict[str, int], describe, doc: str, fix: str, flag: str) -> list[dict]:
    baseline = _load_baseline(root, key)
    baseline_rel = "/".join(_BASELINES[key])
    issues: list[dict] = []
    for rel in sorted(set(current) | set(baseline)):
        have, allowed = current.get(rel, 0), int(baseline.get(rel, 0))
        product = rel.split("/")[1] if rel.startswith("products/") else "seed"
        if have > allowed:
            issues.append({
                "product": product, "file": rel, "severity": "high",
                "issue": f"{have} {describe(rel)}; baseline allows {allowed}. {fix} KB § PATTERNS/security/url-hygiene.md",
            })
        elif have < allowed:
            issues.append({
                "product": product, "file": rel, "severity": "high",
                "issue": f"{have} left but the baseline still allows {allowed}: lower `{rel}` in {baseline_rel} "
                         f"(`{flag}`; the ratchet only shrinks).",
            })
    return issues


def check_signed_url_ttl(repo_root: Path | None = None) -> list[dict]:
    from settings import REPO_ROOT

    root = repo_root or REPO_ROOT

    def describe(rel: str) -> str:
        hits = signed_url_ttl_hits((root / rel).read_text(encoding="utf-8")) if (root / rel).is_file() else []
        where = ", ".join(f"line {ln} ({ttl}s)" for ln, ttl in hits)
        return f"signed-URL call(s) with a TTL above {MAX_TTL_SECONDS}s and no reason ({where})"

    return _ratchet(
        root, "ttl", signed_url_ttl_counts(root), describe, "",
        f"Use a TTL <= {MAX_TTL_SECONDS}s, or pass `ttl_reason=\"<why this must live longer>\"`.",
        "--lower-signed-url-ttl-baseline",
    )


def check_pii_query_params(repo_root: Path | None = None) -> list[dict]:
    from settings import REPO_ROOT

    root = repo_root or REPO_ROOT

    def describe(rel: str) -> str:
        hits = pii_query_param_hits((root / rel).read_text(encoding="utf-8")) if (root / rel).is_file() else []
        where = ", ".join(f"{fn}({p})@{ln}" for ln, fn, p in hits)
        return f"PII-named URL query param(s) ({where})"

    return _ratchet(
        root, "pii", pii_query_param_counts(root), describe, "",
        "Query strings are logged by every proxy/CDN: move it to a POST body, or justify with "
        "`# pii-query-ok: <reason>` on the parameter line.",
        "--lower-pii-query-params-baseline",
    )


def _lower(root: Path, key: str, current: dict[str, int], doc: str, init: bool) -> dict[str, int]:
    old = _load_baseline(root, key)
    new = dict(current) if init else {rel: min(n, old[rel]) for rel, n in current.items() if rel in old}
    path = root.joinpath(*_BASELINES[key])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_doc": doc + " Ratchet: may only go down. KB § PATTERNS/security/url-hygiene.md",
                    "arquivos": dict(sorted(new.items()))}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return new


def lower_signed_url_ttl_baseline(repo_root: Path | None = None, *, init: bool = False) -> dict[str, int]:
    from settings import REPO_ROOT

    root = repo_root or REPO_ROOT
    return _lower(root, "ttl", signed_url_ttl_counts(root),
                  f"Per-file count of signed-URL calls with TTL > {MAX_TTL_SECONDS}s and no reason (check_signed_url_ttl).", init)


def lower_pii_query_params_baseline(repo_root: Path | None = None, *, init: bool = False) -> dict[str, int]:
    from settings import REPO_ROOT

    root = repo_root or REPO_ROOT
    return _lower(root, "pii", pii_query_param_counts(root),
                  "Per-file count of PII-named URL query params (check_pii_query_params).", init)
