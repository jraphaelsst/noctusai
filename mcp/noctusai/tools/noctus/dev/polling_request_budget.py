"""Keeper: every loop that runs forever declares what it costs per day (polling request budget).

Born from the 2026-11-09 Supabase incident: the project was cut off (HTTP 402 on every call) after our own
backends made ~620k REST calls/day polling an EMPTY queue (a fixed 1 s idle poll, a stats read of
``select=*&limit=5000`` inside a per-tick ``claim_gate``, uncached flag reads). Tests use a fake client, so none of
it was visible. The rule + the incident: ``KB § PATTERNS/backend/polling-request-budget.md``.

The author writes the multiplication down, next to the construct (the construct's line or up to 3 lines above):

* Python: ``# poll-budget: <cadence>; <k> calls/tick; worst <N>/day; idle=<backoff|event|fixed>``
* TypeScript: ``// poll-budget: <cadence>; <k> calls/tick; worst <N>/day per open tab; hidden=<paused|runs>``

A declaration is valid only when it carries a number followed by ``/day`` (so it was multiplied out); an empty or
numberless declaration is itself a finding.

Rules (AST only -- ``ast`` for Python, ts-morph via ``mcp/noctusai/node/polling_budget_scan.mjs`` for TypeScript):

* ``py_while_sleep`` (R1) -- a ``while`` loop whose body calls a sleep or a timed wait (``asyncio.sleep``,
  ``time.sleep``, ``wait_for(..., timeout)``, ``asyncio.wait(..., timeout=)``, ``Event.wait(<timeout>)``).
* ``py_periodic_registration`` (R2) -- a periodic registration: the seed scheduler's
  ``register(name, fn, hours|minutes|seconds=...)``, an APScheduler ``add_job`` with an interval trigger, or any call
  passing ``poll_interval_seconds`` / ``max_idle_interval_seconds`` (the seed ``Worker`` and its wrappers).
* ``py_unbounded_tick_read`` (R3) -- inside a function that contains an R1 loop, or whose name says tick / poll /
  gate / stats / run_once, a ``.select("*")`` (or ``.select()``) or a ``.limit(<int literal or module constant> > 1000)``.
  It must count (``count="exact"`` / ``limit(0)``) or name columns, so it is a finding EVEN WHEN DECLARED. Reads that
  are bounded by construction (``.single()`` / ``.maybe_single()`` / ``.limit(<=1)``) are not flagged. Escape, with a
  reason of 10+ chars on the call's line or up to 3 lines above: ``# poll-budget-ok: <why>``.
* ``ts_refetch_interval`` / ``ts_set_interval`` / ``ts_background_poll`` (R4) -- a ``refetchInterval`` whose value is
  not literal ``false`` / ``undefined`` / ``0``, any ``setInterval(`` call, and ``refetchIntervalInBackground: true``
  without ``hidden=runs`` in its declaration.

Scope: ACTIVE products' ``backend/app`` + ``seed/lib/backend/noctusai_lib`` (Python) and ACTIVE products'
``frontend/src`` + ``seed/lib/frontend/src`` (TypeScript); tests, fixtures, ``testing/`` and ``_archive`` excluded.
Severity ``high``, blocking (no baseline: the owner's guarantee is zero undeclared, 2026-11-10). ``paths`` (repo
relative, the staged delta) scopes the scan; omitted = the whole tree. A TS scan that cannot run is ONE explicit
finding, never a silent pass.
"""
from __future__ import annotations

import ast
import io
import json
import re
import shutil
import subprocess
import tokenize
from pathlib import Path

SCRIPT_REL = ("mcp", "noctusai", "node", "polling_budget_scan.mjs")
_TS_TIMEOUT_SECONDS = 300
KB_REF = "KB § PATTERNS/backend/polling-request-budget.md"
SEVERITY = "high"

_PY_SEED_ROOT = "seed/lib/backend/noctusai_lib"
_TS_SEED_ROOT = "seed/lib/frontend/src"
_SKIP_DIRS = frozenset({
    "tests", "test", "__tests__", "fixtures", "_fixtures", "testing", "_archive", "node_modules", "__pycache__", "dist",
})
_WINDOW = 3
_DECL_RE = re.compile(r"poll-budget:")
_DAY_RE = re.compile(r"\d[\d.,]*\s*[kKmM]?\s*/day")
_OK_RE = re.compile(r"poll-budget-ok\s*:\s*\S.{9,}")
_PERIODIC_KWARGS = frozenset({"hours", "minutes", "seconds"})
_POLL_KWARGS = frozenset({"poll_interval_seconds", "max_idle_interval_seconds"})
_TICK_TOKENS = frozenset({"tick", "ticks", "ticker", "gate", "stats"})
_BIG_LIMIT = 1000

_FIX = {
    "py_while_sleep": "declare its cost on the `while` line (or up to 3 lines above) and give it an idle backoff / event wake",
    "py_periodic_registration": "declare its cost on the registration (or up to 3 lines above): cadence x calls per tick x 86400 s = worst N/day",
    "py_unbounded_tick_read": (
        "count with `count=\"exact\"` + `limit(0)` or an RPC, or name the columns and bound the rows; a per-tick read must be "
        "O(1) and cached. Escape, only for a genuinely tiny table: `# poll-budget-ok: <reason of 10+ chars>`"
    ),
    "ts_refetch_interval": "declare it, or drop the interval: prefer an event / invalidation over a timer",
    "ts_set_interval": "declare it (a request per open tab per interval, forever), or drive it from an event",
    "ts_background_poll": "a poll that keeps running in a hidden tab multiplies by every forgotten tab: declare `hidden=runs` with the worst-case number, or drop it",
}
_FORMAT = {
    "py": "`# poll-budget: <cadence>; <k> calls/tick; worst <N>/day; idle=<backoff|event|fixed>`",
    "ts": "`// poll-budget: <cadence>; <k> calls/tick; worst <N>/day per open tab; hidden=<paused|runs>`",
}


def _repo_root(repo_root: Path | None) -> Path:
    if repo_root is not None:
        return repo_root
    from tools.noctus.dev.compliance import REPO_ROOT

    return REPO_ROOT


def _excluded(rel_parts: tuple[str, ...], name: str) -> bool:
    if set(rel_parts[:-1]) & _SKIP_DIRS:
        return True
    return (
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
        or ".test." in name or ".spec." in name or name.endswith(".d.ts")
    )


def _source_roots(root: Path, sub: str, seed_rel: str) -> list[Path]:
    from tools.noctus.dev.compliance import _active_product_dirs

    roots: list[Path] = []
    products = root / "products"
    if products.is_dir():
        roots += [d / sub for d in _active_product_dirs(products) if (d / sub).is_dir()]
    seed = root / seed_rel
    if seed.is_dir():
        roots.append(seed)
    return roots


def _candidates(root: Path, suffixes: tuple[str, ...], sub: str, seed_rel: str, paths: set[str] | None) -> list[Path]:
    out: list[Path] = []
    for src in _source_roots(root, sub, seed_rel):
        for f in sorted(src.rglob("*")):
            if f.suffix not in suffixes or not f.is_file():
                continue
            rel = f.relative_to(root)
            if _excluded(rel.parts, f.name):
                continue
            if paths is not None and rel.as_posix() not in paths:
                continue
            out.append(f)
    return out


def _message(rule: str, detail: str, lang: str) -> str:
    return (
        f"[{rule}] {detail}. Fix: {_FIX[rule]}. Declare the cost, multiplied out per day (a number followed by `/day`): "
        f"{_FORMAT[lang]} -- a loop that runs forever pays per tick, and a fake client hides it (2026-11-09 Supabase 402). {KB_REF}"
    )


# --- Python ------------------------------------------------------------------------------------------------


def _comments(text: str) -> dict[int, str]:
    """line -> comment text, via tokenize (a ``poll-budget:`` inside a string is not a declaration)."""
    if "poll-budget" not in text:
        return {}
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


def _call_name(call: ast.Call) -> str:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _kw(call: ast.Call, name: str) -> ast.keyword | None:
    return next((k for k in call.keywords if k.arg == name), None)


def _is_timed_call(call: ast.Call) -> bool:
    name = _call_name(call)
    if name == "sleep":
        return True
    if name == "wait_for":
        return _kw(call, "timeout") is not None or len(call.args) >= 2
    if name == "wait":
        if _kw(call, "timeout") is not None:
            return True
        f = call.func
        on_asyncio = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "asyncio"
        return isinstance(f, ast.Attribute) and not on_asyncio and len(call.args) >= 1
    return False


def _walk_same_scope(node: ast.AST):
    """Descendants without entering a nested function/lambda/class (their loops are theirs)."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(n))


def _is_r1_loop(node: ast.AST) -> bool:
    return isinstance(node, ast.While) and any(
        isinstance(n, ast.Call) and _is_timed_call(n) for b in node.body for n in [b, *_walk_same_scope(b)]
    )


def _is_tick_name(name: str) -> bool:
    toks = [t for t in name.lower().split("_") if t]
    if not toks:
        return False
    if any(t in _TICK_TOKENS for t in toks) or any(t.startswith("poll") and t != "pollution" for t in toks):
        return True
    return any(a == "run" and b == "once" for a, b in zip(toks, toks[1:]))


def _chain_up(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[ast.Call]:
    """Calls ABOVE `node` in its fluent chain (``x.select(..).eq(..).limit(..)`` -> [eq, limit])."""
    out: list[ast.Call] = []
    cur = node
    while True:
        attr = parents.get(cur)
        if not isinstance(attr, ast.Attribute) or attr.value is not cur:
            break
        call = parents.get(attr)
        if not isinstance(call, ast.Call) or call.func is not attr:
            break
        out.append(call)
        cur = call
    return out


def _int_value(node: ast.AST | None, consts: dict[str, int]) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


class _PyScan:
    def __init__(self, text: str, rel: str):
        self.rel = rel
        self.tree = ast.parse(text)
        self.comments = _comments(text)
        self.parents = {c: p for p in ast.walk(self.tree) for c in ast.iter_child_nodes(p)}
        self.consts = {
            t.id: n.value.value
            for n in self.tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, int) and not isinstance(n.value.value, bool)
            for t in n.targets if isinstance(t, ast.Name)
        }
        self.found: dict[tuple[str, int], dict] = {}

    def _window(self, lines: list[int]):
        for ln in lines:
            for l in range(max(1, ln - _WINDOW), ln + 1):
                c = self.comments.get(l)
                if c is not None:
                    yield c

    def declared(self, *lines: int) -> bool:
        return any(_DECL_RE.search(c) and _DAY_RE.search(c) for c in self._window(list(lines)))

    def _has_numberless(self, *lines: int) -> bool:
        return any(_DECL_RE.search(c) and not _DAY_RE.search(c) for c in self._window(list(lines)))

    def escaped(self, *lines: int) -> bool:
        return any(_OK_RE.search(c) for c in self._window(list(lines)))

    def add(self, rule: str, line: int, detail: str) -> None:
        self.found.setdefault((rule, line), {
            "rule": rule, "line": line, "detail": detail,
        })

    def add_if_undeclared(self, rule: str, line: int, detail: str, *lines: int) -> None:
        if self.declared(line, *lines):
            return
        extra = " (a `poll-budget:` declaration is present but carries no `<N>/day` figure)" if self._has_numberless(line, *lines) else ""
        self.add(rule, line, detail + extra)

    def run(self) -> list[dict]:
        for node in ast.walk(self.tree):
            if _is_r1_loop(node):
                self.add_if_undeclared("py_while_sleep", node.lineno, "`while` loop that sleeps / waits on a timeout has no cost declaration")
            elif isinstance(node, ast.Call):
                self._registration(node)
        for fn in (n for n in ast.walk(self.tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            if _is_tick_name(fn.name) or any(_is_r1_loop(n) for n in ast.walk(fn)):
                self._tick_reads(fn)
        return sorted(self.found.values(), key=lambda f: (f["line"], f["rule"]))

    def _registration(self, call: ast.Call) -> None:
        name = _call_name(call)
        kws = {k.arg for k in call.keywords if k.arg}
        what = None
        if kws & _POLL_KWARGS:
            what = f"`{name or 'call'}(... {sorted(kws & _POLL_KWARGS)[0]}=...)` sets a poll cadence"
        elif name == "register" and kws & _PERIODIC_KWARGS and len(call.args) >= 2:
            what = f"`register(..., {sorted(kws & _PERIODIC_KWARGS)[0]}=...)` registers a periodic job"
        elif name == "add_job":
            interval = bool(kws & (_PERIODIC_KWARGS | {"weeks", "days"})) or any(
                isinstance(a, ast.Constant) and a.value == "interval" for a in call.args[1:2]
            ) or (_kw(call, "trigger") is not None and (
                (isinstance(_kw(call, "trigger").value, ast.Constant) and _kw(call, "trigger").value.value == "interval")
                or (isinstance(_kw(call, "trigger").value, ast.Call) and _call_name(_kw(call, "trigger").value) == "IntervalTrigger")
            ))
            if interval:
                what = "`add_job` with an interval trigger registers a periodic job"
        if what:
            self.add_if_undeclared("py_periodic_registration", call.lineno, what + " and has no cost declaration", *[k.value.lineno for k in call.keywords])

    def _tick_reads(self, fn: ast.AST) -> None:
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            name = _call_name(call)
            if name not in ("select", "limit"):
                continue
            above = _chain_up(call, self.parents)
            # `Call.lineno` is the START of the whole fluent chain; the method's own line is where its receiver ends.
            at = getattr(getattr(call.func, "value", None), "end_lineno", None) or call.lineno
            root_line = call.lineno
            cur: ast.AST = call
            while isinstance(cur, (ast.Call, ast.Attribute)):
                cur = cur.func if isinstance(cur, ast.Call) else cur.value
            root_line = min(root_line, getattr(cur, "lineno", root_line))
            chain_names = [_call_name(c) for c in above]
            if name == "select":
                star = not call.args or (isinstance(call.args[0], ast.Constant) and call.args[0].value == "*")
                counted = _kw(call, "count") is not None or any(
                    _call_name(c) == "limit" and c.args and _int_value(c.args[0], self.consts) == 0 for c in above
                )
                bounded = bool({"single", "maybe_single"} & set(chain_names)) or any(
                    _call_name(c) == "limit" and c.args and (_int_value(c.args[0], self.consts) or 99) <= 1 for c in above
                )
                if star and not counted and not bounded and not self.escaped(at, call.lineno, root_line):
                    self.add("py_unbounded_tick_read", at,
                             f'`.select("*")` inside `{fn.name}` (a tick / gate / loop) fetches whole rows on every tick')
            else:
                n = _int_value(call.args[0], self.consts) if call.args else None
                if n is not None and n > _BIG_LIMIT and not self.escaped(at, call.lineno, root_line):
                    self.add("py_unbounded_tick_read", at,
                             f"`.limit({n})` inside `{fn.name}` (a tick / gate / loop) reads up to {n} rows on every tick")


def _scan_python(root: Path, files: list[Path]) -> list[dict]:
    issues: list[dict] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # cheap pre-filter: skip the parse unless some rule's anchor appears
        if not (
            ("while" in text and ("sleep" in text or "wait" in text))
            or "register(" in text or "add_job" in text or "poll_interval_seconds" in text
            or "max_idle_interval_seconds" in text or "select(" in text
        ):
            continue
        rel = f.relative_to(root).as_posix()
        try:
            found = _PyScan(text, rel).run()
        except SyntaxError as exc:
            issues.append({"product": _owner(rel), "file": rel, "severity": SEVERITY, "rule": "py_unparsed",
                           "issue": f"polling-budget scan could not parse this file ({exc.msg}, line {exc.lineno}) -- a skipped file is not a clean one. {KB_REF}"})
            continue
        for x in found:
            issues.append({"product": _owner(rel), "file": rel, "line": x["line"], "rule": x["rule"], "severity": SEVERITY,
                           "construct": x["detail"], "issue": _message(x["rule"], f"line {x['line']}: {x['detail']}", "py")})
    return issues


# --- TypeScript ----------------------------------------------------------------------------------------------


def _owner(rel: str) -> str:
    parts = rel.split("/")
    return parts[1] if parts[0] == "products" and len(parts) > 1 else "seed"


def _scan_typescript(root: Path, files: list[Path]) -> list[dict]:
    cand = []
    for f in files:
        try:
            t = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "refetchInterval" in t or "setInterval" in t:
            cand.append(f)
    if not cand:
        return []
    script = root.joinpath(*SCRIPT_REL)
    if not script.exists():
        script = _repo_root(None).joinpath(*SCRIPT_REL)

    def boot(msg: str) -> list[dict]:
        return [{"product": "*", "file": "/".join(SCRIPT_REL), "severity": SEVERITY, "rule": "ts_scan_failed",
                 "issue": f"polling-budget TypeScript scan could not run -- {msg}. {KB_REF}"}]

    if shutil.which("node") is None:
        return boot("`node` not on PATH")
    if not script.exists():
        return boot(f"script_missing: {script}")
    try:
        proc = subprocess.run(["node", str(script)], input=json.dumps({"files": [str(f) for f in cand]}),
                              capture_output=True, text=True, timeout=_TS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return boot(f"timeout after {_TS_TIMEOUT_SECONDS}s ({len(cand)} files)")
    except OSError as exc:
        return boot(f"spawn_failed: {exc}")
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-400:]
        hint = "run `cd mcp/noctusai/node && npm ci`; " if "Cannot find module" in tail or "ERR_MODULE_NOT_FOUND" in tail else ""
        return boot(f"node_crashed (exit {proc.returncode}): {hint}{tail.strip()}")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return boot(f"non_json_stdout: {exc}")
    issues: list[dict] = []
    for path, message in sorted(parsed.get("errors", {}).items()):
        rel = Path(path).relative_to(root).as_posix() if path.startswith(str(root)) else path
        issues.append({"product": _owner(rel), "file": rel, "severity": SEVERITY, "rule": "ts_unparsed",
                       "issue": f"polling-budget scan could not read this file ({message[:200]}) -- a skipped file is not a clean one. {KB_REF}"})
    for path, findings in sorted(parsed.get("results", {}).items()):
        rel = Path(path).relative_to(root).as_posix() if path.startswith(str(root)) else path
        for x in findings:
            issues.append({"product": _owner(rel), "file": rel, "line": x["line"], "rule": x["rule"], "severity": SEVERITY,
                           "construct": x["construct"],
                           "issue": _message(x["rule"], f"line {x['line']}: `{x['construct']}` has no cost declaration", "ts")})
    return issues


def check_polling_request_budget(repo_root: Path | None = None, paths: list[str] | None = None) -> list[dict]:
    """Every forever-loop / periodic registration / browser poll declares its per-day cost (R1-R4, module docstring).
    ``paths`` (repo-relative) scopes the scan to those files. Severity ``high``; blocking."""
    root = _repo_root(repo_root)
    scope = {p.replace("\\", "/") for p in paths} if paths is not None else None
    issues = _scan_python(root, _candidates(root, (".py",), "backend/app", _PY_SEED_ROOT, scope))
    issues += _scan_typescript(root, _candidates(root, (".ts", ".tsx"), "frontend/src", _TS_SEED_ROOT, scope))
    return sorted(issues, key=lambda i: (i.get("file", ""), i.get("line", 0)))
