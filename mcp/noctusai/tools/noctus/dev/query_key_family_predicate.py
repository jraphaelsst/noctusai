"""Query-key FAMILY predicates — the screen must not lie after a write or an async job.

Two keepers (`check_mutation_family_write`, `check_job_start_without_handoff` in
`compliance.py`) read through this module. Both answer a question the sibling keeper
`check_mutation_invalidate_only` cannot: that one asks "does this mutation put ANYTHING
into the cache?" (a `setQueryData` / `onMutate` token in the block). These ask "does it put
it into the RIGHT entries?" — which needs every query key of the product resolved to its
segments, so a key's family (its descendants) can be derived from the key convention
instead of from a hand list.

Escaped class (2026-10-24, social-wiring replay, fixed locally by 203b6a1b5):

* F88 — `useNegociacaoMutation` wrote `setQueryData(["sw","clientes",id,"negociacao"])`.
  The invalidate-only keeper was satisfied (a write token exists), but the product reads
  `[..."negociacao","estruturada"]` and `[..."negociacao","conflitos"]` — derived from the
  same row — and nothing refreshed them. `setQueryData` is EXACT; `invalidateQueries` is a
  PREFIX match. A raw write that never invalidates its own family leaves the children stale.
  → `family_write_hits`.
* F87 — `useSolicitarEmissao` carried `noc-allow: invalidate-only — queues emissions that
  finish asynchronously ... arrive via the polled partes read`. The allow was honest, but the
  polled read's `jobPolling(isActive)` predicate reads only `data`; the refetch the
  invalidate triggers landed BEFORE the async job created its rows, so `isActive` was false
  and polling never started. A mutation that reaches a job-polled read only by invalidating
  it cannot know the read will see the job → it must hand off (`handOffToPolling` from
  `@noctusai/lib`). → `job_handoff_hits`.

Lexical, not a TypeScript AST — the same register as `check_mutation_invalidate_only`
(brace/bracket balancing that is string-, template- and comment-aware). A key it cannot
resolve is SKIPPED, never guessed: the keeper under-reports, it does not invent families.
NOC-REMEDIATE[query-key-family-ts-morph]: port the resolver to the ts-morph scanner
(`mcp/noctusai/node/`) so cross-file aliases / key-factory objects resolve via the binder — 2026-10-24.

KB § PATTERNS/frontend/mutation-cache-writes.md (§ Write the family, § Async jobs hand off).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

WILD = "*"
Key = tuple[str, ...]

_ALLOW_FAMILY = "noc-allow: exact-write"
_ALLOW_HANDOFF = "noc-allow: no-job-handoff"
_JOB_POLLING = re.compile(r"\bjobPolling\s*(?:<[^()]*?>)?\(")
_RESPONSE_TYPE = re.compile(r"\b(?:api|apiClient|http|client)\.(?:post|put|patch|request)\s*<\s*([A-Z][\w$]*)")
_TYPE_DECL = re.compile(r"(?:^|\s)(?:export\s+)?(?:interface\s+([A-Z][\w$]*)[^{]*\{|type\s+([A-Z][\w$]*)\s*(?:<[^=]*>)?\s*=\s*\{)")
#: A response field that names server-side work still running: the write QUEUED something.
_JOB_FIELD = re.compile(r"(?<![\w$])(?:job_?id|jobId|consulta_?ids?|consultaIds?|run_?id|runId|execucao_?id|sync_?id|syncId|operation_?id)\s*\??\s*:")
#: An invalidate-only allow whose own reason says the write starts async work.
_ASYNC_REASON = re.compile(r"(?i)noc-allow:\s*invalidate-only\b.*(?:ass[ií]ncron|async|enfileir|\bfila\b|queue|background|segundo plano|\bjob|poll)")
_HANDOFF_CALL = re.compile(r"\bhandOffToPolling\s*\(")

_READ_CALL = re.compile(
    r"\b(?:useQuery|useSuspenseQuery|useInfiniteQuery|useSuspenseInfiniteQuery|queryOptions|"
    r"infiniteQueryOptions|prefetchQuery|fetchQuery|ensureQueryData)\s*(?:<[^()]*?>)?\(\s*\{"
)
_MUTATION_CALL = re.compile(r"\b(useMutation|useCacheWriteMutation)\s*(?:<[^()]*?>)?\(\s*\{")
_SET_CALL = re.compile(r"\bsetQueryData\s*(?:<[^()]*?>)?\(")
_SETS_CALL = re.compile(r"\bsetQueriesData\s*(?:<[^()]*?>)?\(")
_INV_CALL = re.compile(r"\b(?:invalidateQueries|refetchQueries|resetQueries|removeQueries)\s*\(")
_TOP_DECL = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*\w+|const\s+\w+|let\s+\w+)", re.M)
_CONST_DEF = re.compile(r"(?:^|[;\s])(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=;]+?)?=\s*", re.M)
_FUNC_DEF = re.compile(r"(?:^|\s)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^()]*?>)?\(")
_IMPORT = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")
_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
_CALL_NAME = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(")


# ─── lexing ──────────────────────────────────────────────────────────────────

def strip_comments(text: str) -> str:
    """Blank `//` and `/* */` comments (newlines kept, so line numbers survive); strings untouched."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            i = _skip_string(text, i)
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def _skip_string(text: str, i: int) -> int:
    """Index just past the string literal opening at ``i`` (template `${}` nesting aware)."""
    q = text[i]
    j, n = i + 1, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if q == "`" and text.startswith("${", j):
            j = _close(text, j + 1) + 1
            continue
        if c == q:
            return j + 1
        if c == "\n" and q != "`":
            return j
        j += 1
    return n


_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _close(text: str, i: int) -> int:
    """Index of the bracket closing the one at ``i`` (string-aware); ``len-1`` when unbalanced."""
    stack: list[str] = []
    j, n = i, len(text)
    while j < n:
        c = text[j]
        if c in "'\"`":
            j = _skip_string(text, j)
            continue
        if c in _PAIRS:
            stack.append(_PAIRS[c])
        elif c in ")]}":
            if stack and stack[-1] == c:
                stack.pop()
                if not stack:
                    return j
        j += 1
    return n - 1


def _split_top(text: str) -> list[str]:
    """Split on commas at bracket depth 0 (string-aware)."""
    parts: list[str] = []
    depth, start, j, n = 0, 0, 0, len(text)
    while j < n:
        c = text[j]
        if c in "'\"`":
            j = _skip_string(text, j)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:j])
            start = j + 1
        j += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _expr_end(text: str, i: int) -> int:
    """End (exclusive) of the expression starting at ``i``: stops at a depth-0 `,` `;` `)` `]` `}`
    or a blank-line / new top-level statement."""
    depth, j, n = 0, i, len(text)
    while j < n:
        c = text[j]
        if c in "'\"`":
            j = _skip_string(text, j)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif depth == 0 and c in ",;":
            return j
        elif depth == 0 and c == "\n" and _TOP_DECL.match(text, j + 1):
            return j
        j += 1
    return n


def _string_value(expr: str) -> str | None:
    e = expr.strip()
    if len(e) >= 2 and e[0] == e[-1] and e[0] in "'\"":
        return e[1:-1]
    if len(e) >= 2 and e[0] == e[-1] == "`" and "${" not in e:
        return e[1:-1]
    return None


def _strip_expr(expr: str) -> str:
    """Drop wrapping parens and a trailing `as …` / `satisfies …` type assertion."""
    e = expr.strip()
    while True:
        m = re.search(r"\s+(?:as|satisfies)\s+[\w.<>\[\], |]+$", e)
        if m:
            e = e[: m.start()].rstrip()
            continue
        if e.startswith("(") and _close(e, 0) == len(e) - 1:
            e = e[1:-1].strip()
            continue
        return e


def _prop(obj: str, name: str) -> str | None:
    """Value text of property ``name`` at the top level of the object literal ``obj`` (``{...}``)."""
    inner = obj.strip()
    if not inner.startswith("{"):
        return None
    for part in _split_top(inner[1:-1] if inner.endswith("}") else inner[1:]):
        m = re.match(rf"^{re.escape(name)}\s*:\s*", part)
        if m:
            return part[m.end():]
        if part == name:  # shorthand `{ queryKey }`
            return name
    return None


# ─── definitions index ───────────────────────────────────────────────────────

@dataclass
class Def:
    params: list[str]
    expr: str | None = None      # value expression (arrow expression body / const value)
    body: str | None = None      # function block body (helpers)


@dataclass
class FileInfo:
    path: Path
    text: str                    # comments stripped
    raw: str
    defs: dict[str, Def] = field(default_factory=dict)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)  # local → (spec, exported)
    types: dict[str, str] = field(default_factory=dict)  # interface / object-type name → body


def _params(sig: str) -> list[str]:
    out = []
    for p in _split_top(sig):
        p = p.lstrip(".")
        m = re.match(r"^([A-Za-z_$][\w$]*)", p)
        out.append(m.group(1) if m else "")
    return out


def _index_defs(text: str) -> dict[str, Def]:
    defs: dict[str, Def] = {}
    for m in _FUNC_DEF.finditer(text):
        po = m.end() - 1
        pc = _close(text, po)
        bo = text.find("{", pc)
        if bo == -1:
            continue
        defs.setdefault(m.group(1), Def(_params(text[po + 1 : pc]), body=text[bo + 1 : _close(text, bo)]))
    for m in _CONST_DEF.finditer(text):
        name, i = m.group(1), m.end()
        rest = text[i:]
        am = re.match(r"(?:async\s+)?(?:<[^()]*?>)?\(", rest)
        if am:  # arrow fn `(a, b) => ...` (or a call — rejected by the `=>` check)
            po = i + am.end() - 1
            pc = _close(text, po)
            after = re.match(r"\s*(?::\s*[^=]+?)?=>\s*", text[pc + 1 :])
            if not after:
                defs.setdefault(name, Def([], expr=text[i : _expr_end(text, i)]))
                continue
            bstart = pc + 1 + after.end()
            if text[bstart : bstart + 1] == "{":
                defs.setdefault(name, Def(_params(text[po + 1 : pc]), body=text[bstart + 1 : _close(text, bstart)]))
            else:
                defs.setdefault(name, Def(_params(text[po + 1 : pc]), expr=text[bstart : _expr_end(text, bstart)]))
            continue
        sm = re.match(r"([A-Za-z_$][\w$]*)\s*=>\s*", rest)
        if sm:
            bstart = i + sm.end()
            if text[bstart : bstart + 1] == "{":
                defs.setdefault(name, Def([sm.group(1)], body=text[bstart + 1 : _close(text, bstart)]))
            else:
                defs.setdefault(name, Def([sm.group(1)], expr=text[bstart : _expr_end(text, bstart)]))
            continue
        val = text[i : _expr_end(text, i)]
        defs.setdefault(name, Def([], expr=val))
        if val.lstrip().startswith("{"):  # key-factory object: `keys = { all: [...], detail: (id) => [...] }`
            for part in _split_top(val.strip()[1:-1]):
                pm = re.match(r"^([A-Za-z_$][\w$]*)\s*:\s*", part)
                if not pm:
                    continue
                sub = _index_defs(f"const {pm.group(1)} = {part[pm.end():]}")
                if pm.group(1) in sub:
                    defs.setdefault(f"{name}.{pm.group(1)}", sub[pm.group(1)])
    return defs


def _first_return(body: str) -> str | None:
    m = re.search(r"\breturn\s+", body)
    return body[m.end() : _expr_end(body, m.end())] if m else None


class Product:
    """Every TS/TSX source of one frontend `src/` tree, indexed for key resolution."""

    def __init__(self, src: Path, files: list[Path]) -> None:
        self.src = src
        self.files: dict[Path, FileInfo] = {}
        for f in files:
            try:
                raw = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            text = strip_comments(raw)
            info = FileInfo(f, text, raw, _index_defs(text))
            for tm in _TYPE_DECL.finditer(text):
                ob = tm.end() - 1
                info.types.setdefault(tm.group(1) or tm.group(2), text[ob : _close(text, ob) + 1])
            for im in _IMPORT.finditer(text):
                for part in im.group(1).split(","):
                    part = part.strip().removeprefix("type ").strip()
                    if not part:
                        continue
                    exported, _, local = part.partition(" as ")
                    info.imports[(local or exported).strip()] = (im.group(2), exported.strip())
            self.files[f] = info
        self._by_resolved = {p.resolve(): info for p, info in self.files.items()}

    def _module(self, spec: str, origin: Path) -> FileInfo | None:
        if spec.startswith("@/"):
            base = self.src / spec[2:]
        elif spec.startswith("."):
            base = (origin.parent / spec).resolve()
        else:
            return None
        base = base.resolve()
        for cand in (base, Path(f"{base}.ts"), Path(f"{base}.tsx"), base / "index.ts", base / "index.tsx"):
            hit = self._by_resolved.get(cand)
            if hit:
                return hit
        return None

    def type_body(self, name: str, info: FileInfo, _seen: int = 0) -> str | None:
        """Body of the interface / object type ``name`` as seen from ``info`` (same file or import)."""
        if _seen > 4:
            return None
        if name in info.types:
            return info.types[name]
        if name in info.imports:
            spec, exported = info.imports[name]
            mod = self._module(spec, info.path)
            if mod:
                return self.type_body(exported, mod, _seen + 1)
        return None

    def lookup(self, name: str, info: FileInfo, _seen: int = 0) -> tuple[Def, FileInfo] | None:
        """Definition of ``name`` (``a`` or ``a.b``) as seen from ``info``: same file, then its import."""
        if _seen > 4:
            return None
        if name in info.defs:
            return info.defs[name], info
        head, _, tail = name.partition(".")
        if head in info.imports:
            spec, exported = info.imports[head]
            mod = self._module(spec, info.path)
            if mod:
                return self.lookup(f"{exported}.{tail}" if tail else exported, mod, _seen + 1)
        return None

    # ── key resolution ──────────────────────────────────────────────────────

    def resolve_key(self, expr: str, info: FileInfo, env: dict[str, str] | None = None, depth: int = 0) -> Key | None:
        """Segments of a query-key expression (string literal → its value, anything else → ``*``)."""
        env = env or {}
        if depth > 6:
            return None
        e = _strip_expr(expr)
        if not e:
            return None
        if e.startswith("["):
            close = _close(e, 0)
            if close != len(e) - 1:
                return None
            segs: list[str] = []
            for el in _split_top(e[1:-1]):
                if el.startswith("..."):
                    sub = self.resolve_key(el[3:], info, env, depth + 1)
                    if sub is None:
                        return None
                    segs.extend(sub)
                    continue
                segs.append(self._segment(el, info, env))
            return tuple(segs)
        m = re.match(r"^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*(\(.*\))?$", e, re.S)
        if not m:
            return None
        name, call = m.group(1), m.group(2)
        found = self.lookup(name, info)
        if not found:
            return None
        d, where = found
        value = d.expr if d.expr is not None else (_first_return(d.body) if d.body else None)
        if value is None:
            return None
        sub_env: dict[str, str] = {}
        if call:
            args = _split_top(call[1:-1])
            for p, a in zip(d.params, args):
                if p:
                    sub_env[p] = self._segment(a, info, env)
        return self.resolve_key(value, where, sub_env, depth + 1)

    def _segment(self, el: str, info: FileInfo, env: dict[str, str]) -> str:
        e = _strip_expr(el)
        s = _string_value(e)
        if s is not None:
            return s
        if _IDENT.match(e):
            if e in env:
                return env[e]
            found = self.lookup(e, info)
            if found and found[0].expr is not None:
                s = _string_value(_strip_expr(found[0].expr))
                if s is not None:
                    return s
        return WILD


def key_prefix_of(a: Key, b: Key) -> bool:
    """``a`` is a (non-strict) prefix of ``b`` — segment-equal, ``*`` matches only ``*``."""
    return len(a) <= len(b) and all(x == y for x, y in zip(a, b))


# ─── scanning a product ──────────────────────────────────────────────────────

def _call_arg(text: str, open_paren: int) -> str:
    return _split_top(text[open_paren + 1 : _close(text, open_paren)])[0] if text[open_paren + 1 : _close(text, open_paren)].strip() else ""


def _keys_in(product: Product, info: FileInfo, scope: str) -> tuple[list[Key], list[Key]]:
    """(written, invalidated) keys mentioned directly in ``scope``. An argument-less
    ``invalidateQueries()`` invalidates everything (the empty key)."""
    written: list[Key] = []
    invalidated: list[Key] = []
    for m in _SET_CALL.finditer(scope):
        k = product.resolve_key(_call_arg(scope, m.end() - 1), info)
        if k is not None:
            written.append(k)
    for m in _SETS_CALL.finditer(scope):
        arg = _call_arg(scope, m.end() - 1)
        qk = _prop(arg, "queryKey") if arg.startswith("{") else arg
        k = product.resolve_key(qk, info) if qk else None
        if k is not None:
            written.append(k)
            invalidated.append(k)  # setQueriesData is already a prefix write
    for m in _INV_CALL.finditer(scope):
        arg = _call_arg(scope, m.end() - 1)
        if not arg:
            invalidated.append(())
            continue
        qk = _prop(arg, "queryKey") if arg.startswith("{") else arg
        if arg.startswith("{") and qk is None:
            invalidated.append(())  # `{ predicate }` / `{ type }` — treated as broad
            continue
        k = product.resolve_key(qk, info) if qk else None
        if k is not None:
            invalidated.append(k)
    return written, invalidated


@dataclass
class Mutation:
    info: FileInfo
    line: int
    kind: str                    # "useMutation" | "useCacheWriteMutation"
    allow_line: str
    written: list[Key]
    invalidated: list[Key]
    handoff: bool
    job_start: str | None = None  # why this write starts server-side async work (None = it does not)


@dataclass
class Read:
    info: FileInfo
    line: int
    key: Key
    polled: bool


_FN_DECL = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*\w+"
    r"|^[ \t]*(?:export\s+)?const\s+\w+\s*(?::[^=\n]+)?=\s*(?:async\s*)?(?:<[^()\n]*?>)?\([^()\n]*\)\s*(?::[^=\n]+)?=>",
    re.M,
)


def _enclosing_start(text: str, pos: int) -> int:
    """Start of the innermost function declaration (``function f`` / ``const f = (...) =>``) before ``pos``."""
    start = 0
    for m in _FN_DECL.finditer(text, 0, pos):
        start = m.start()
    return start


def _helper_keys(product: Product, info: FileInfo, scope: str, depth: int = 0) -> tuple[list[Key], list[Key], bool]:
    """Keys + hand-off reached through same-product helper calls named in ``scope`` (2 levels)."""
    w: list[Key] = []
    inv: list[Key] = []
    handoff = False
    if depth > 1:
        return w, inv, handoff
    for name in set(_CALL_NAME.findall(scope)):
        found = product.lookup(name, info)
        if not found or found[0].body is None and found[0].expr is None:
            continue
        d, where = found
        body = d.body if d.body is not None else d.expr or ""
        if not (_INV_CALL.search(body) or _SET_CALL.search(body) or _HANDOFF_CALL.search(body) or _CALL_NAME.search(body)):
            continue
        a, b = _keys_in(product, where, body)
        w += a
        inv += b
        handoff = handoff or bool(_HANDOFF_CALL.search(body))
        a, b, h = _helper_keys(product, where, body, depth + 1)
        w += a
        inv += b
        handoff = handoff or h
    return w, inv, handoff


def scan(product: Product) -> tuple[list[Mutation], list[Read]]:
    mutations: list[Mutation] = []
    reads: list[Read] = []
    for info in product.files.values():
        text = info.text
        raw_lines = info.raw.splitlines()
        for m in _READ_CALL.finditer(text):
            ob = m.end() - 1
            block = text[ob : _close(text, ob) + 1]
            qk = _prop(block, "queryKey")
            if qk is None:
                continue
            if qk == "queryKey":  # shorthand: the local `const queryKey = ...`
                local = list(re.finditer(r"\bconst\s+queryKey\s*(?::[^=]+?)?=\s*", text[: m.start()]))
                if not local:
                    continue
                qk = text[local[-1].end() : _expr_end(text, local[-1].end())]
            key = product.resolve_key(qk, info)
            if key is None:
                continue
            polled = bool(_JOB_POLLING.search(block)) or bool(re.search(r"\brefetchInterval\s*:\s*(?:\(|[A-Za-z_$][\w$]*\s*=>)", block))
            reads.append(Read(info, text.count("\n", 0, m.start()) + 1, key, polled))
        for m in _MUTATION_CALL.finditer(text):
            ob = m.end() - 1
            block = text[ob : _close(text, ob) + 1]
            line = text.count("\n", 0, m.start()) + 1
            pre = text[_enclosing_start(text, m.start()) : m.start()]
            w, inv = _keys_in(product, info, block)
            if m.group(1) == "useCacheWriteMutation":
                for part in re.finditer(r"\bqueryKey\s*:\s*", block):
                    k = product.resolve_key(block[part.end() : _expr_end(block, part.end())], info)
                    if k is not None:
                        w.append(k)
                        inv.append(k)  # settle invalidates every target (prefix)
                iv = _prop(block, "invalidate")
                if iv:
                    iv = _strip_expr(iv)
                    if iv.startswith("("):  # `(vars) => [...]`
                        iv = iv[iv.find("=>") + 2 :].strip() if "=>" in iv else iv
                    if iv.startswith("["):
                        for el in _split_top(iv[1:-1]):
                            k = product.resolve_key(el, info)
                            if k is not None:
                                inv.append(k)
                    else:
                        found = product.lookup(iv.split("(")[0].strip(), info)
                        if found:
                            d, where = found
                            val = d.expr if d.expr is not None else _first_return(d.body or "")
                            if val and _strip_expr(val).startswith("["):
                                for el in _split_top(_strip_expr(val)[1:-1]):
                                    k = product.resolve_key(el, where)
                                    if k is not None:
                                        inv.append(k)
            hw, hinv, hh = _helper_keys(product, info, block + "\n" + pre)
            allow_line = raw_lines[line - 1] if line - 1 < len(raw_lines) else ""
            job_start = None
            if _ASYNC_REASON.search(allow_line):
                job_start = "its invalidate-only allow says the write starts async work"
            elif re.search(r"(?<![\w.])202(?![\w.])", block):
                job_start = "it handles a 202 Accepted"
            else:
                for t in dict.fromkeys(_RESPONSE_TYPE.findall(block)):
                    body = product.type_body(t, info)
                    fm = _JOB_FIELD.search(body or "")
                    if fm:
                        job_start = f"its response `{t}` carries `{fm.group(0).rstrip(':?').strip()}`"
                        break
            mutations.append(Mutation(
                info=info, line=line, kind=m.group(1),
                allow_line=allow_line, job_start=job_start,
                written=w + hw, invalidated=inv + hinv,
                handoff=bool(_HANDOFF_CALL.search(block)) or hh,
            ))
    return mutations, reads


def family_write_hits(mutations: list[Mutation], reads: list[Read]) -> list[tuple[Mutation, Key, list[Key]]]:
    """Raw `useMutation` blocks that `setQueryData` a key whose family has read descendants
    the block never refreshes (no invalidation of the key, an ancestor, or each descendant).
    A descendant counts when its first extra segment is NAMED (a derived view of the written
    entry); an id-wildcard first (`[...list, *, ...]`) is a sub-resource of one element."""
    read_keys = {r.key for r in reads}
    out: list[tuple[Mutation, Key, list[Key]]] = []
    for mu in mutations:
        if mu.kind != "useMutation" or _ALLOW_FAMILY in mu.allow_line:
            continue
        for w in dict.fromkeys(mu.written):
            if any(key_prefix_of(i, w) for i in mu.invalidated):
                continue
            stale = sorted(
                d for d in read_keys
                if len(d) > len(w) and key_prefix_of(w, d)
                # `[...chats]` → `[...chats, <id>, "messages"]` is a sub-resource of ONE element of the
                # written collection, not a view derived from it: only a NAMED child (`"estruturada"`) is.
                and d[len(w)] != WILD
                and not any(key_prefix_of(i, d) for i in mu.invalidated)
            )
            if stale:
                out.append((mu, w, stale))
    return out


def job_handoff_hits(mutations: list[Mutation], reads: list[Read]) -> list[tuple[Mutation, list[Key]]]:
    """Mutations that START server-side async work (response carries a job / consulta id, a 202,
    or their own invalidate-only allow says so) and neither hand off to polling
    (`handOffToPolling`) nor write a job-polled read's entry with the server's answer. The
    invalidate-triggered refetch can land BEFORE the job is visible, so the polled read's
    `isActive(data)` is false and the poll never starts (F87). Returns the job-polled reads
    the write reaches (empty list ⇒ no read polls this job at all — also a hit)."""
    polled = {r.key for r in reads if r.polled}
    out: list[tuple[Mutation, list[Key]]] = []
    for mu in mutations:
        if not mu.job_start or mu.handoff or _ALLOW_HANDOFF in mu.allow_line:
            continue
        if any(key_prefix_of(w, p) for w in mu.written for p in polled):
            continue  # its entry was WRITTEN: the predicate sees the server's answer
        reached = sorted(p for p in polled if any(i and key_prefix_of(i, p) for i in mu.invalidated))
        out.append((mu, reached))
    return out


def fmt_key(k: Key) -> str:
    return "[" + ", ".join(s if s == WILD else repr(s) for s in k) + "]"
