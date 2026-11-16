"""Shell STRUCTURE for the background-launch guard (stdlib-only; shared by the guard and the wrapper).

WHY (owner, 2026-11-14): the first guard judged a command by `do ... done` TEXT heuristics, so prose
inside `-m '...'` or a heredoc written to a file looked like a loop, and a loop inside a script
(`./poll.sh`) was invisible. This module reads the command as a shell does:

  * a hand-written lexer (quotes, `$(...)`, backticks, comments, heredocs, redirections; no new
    dependency - bashlex is not installed) turns the text into words and operators;
  * words remember whether they were quoted, so a quoted string is DATA unless something executes it
    (`bash -c STR`, `eval STR`, `$(...)`, a heredoc fed to a shell);
  * a heredoc body written to a file (`cat > f <<EOF`) is data, never judged;
  * a `while`/`until` is a loop only where a command STARTS and only when its `do ... done` closes;
  * `timeout N <cmd>` (also inside `-c` strings) and `bg_run.py ... --done-when` / `--long-lived` bound
    what they wrap;
  * the first path token of an invoked script (`./poll.sh`, `bash x.sh`, `python poll.py`) is opened
    (bounded: <= 128 KB, under the repo or the session scratchpad, <= 6 files) and scanned the same way
    (shell: this module; Python: `ast`, an infinite `while True` with no break/return).

A finding is `Finding(kind, bounded, ...)`; callers act on the UNBOUNDED open-ended ones.
KB § PATTERNS/common/background-agent-lifecycle.md
"""
from __future__ import annotations

import ast
import os
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SHELLS = frozenset({"zsh", "bash", "sh", "dash", "ksh"})
MAX_SCRIPT_BYTES = 128 * 1024
MAX_SCRIPT_READS = 6
MAX_DEPTH = 4
OPEN_ENDED = frozenset({"loop", "follow", "watch", "watch-flag", "script-loop", "poll"})  # kinds that never end by themselves
_PREFIX = frozenset({"nohup", "time", "command", "exec", "env", "nice", "setsid", "stdbuf", "sudo"})
_PEEL = frozenset({"while", "until", "do", "done", "then", "else", "elif", "fi", "if", "for", "select", "case", "esac", "{", "}", "!"})
_PURE_BODY = frozenset({"sleep", "echo", "printf", "date", ":", "true"})
_HEADER = frozenset({"for", "select", "case"})
_DURATION = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
_FOLLOW = re.compile(r"^-[a-zA-Z]*[fF]$|^--follow(?:=.*)?$")
_HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^']*)'|\"([^\"]*)\"|([\w.-]+))")
_SCRIPT_SUFFIX = (".sh", ".bash", ".zsh", ".py")
LOG_PATH_RE = re.compile(r"(?<![^\s'\"=(])([^\s'\"|;&<>()=]+\.(?:log|out|output|txt))(?![\w])")  # a log-ish file, absolute or relative
_WRAPPER_VALUE_OPTS = ("--purpose", "--done", "--done-when", "--command", "--producer-pid", "--learnings", "--interval")


# ---------------------------------------------------------------- lexer
@dataclass
class Word:
    text: str
    quoted: bool
    subs: list[str]
    start: int
    end: int = 0


@dataclass
class Op:
    text: str
    start: int


@dataclass
class Redir:
    op: str
    start: int
    target: Word | None = None
    body: str | None = None


def _skip_heredoc_bodies(s: str, j: int, pend: list[tuple[str, bool]]) -> int:
    for delim, strip in pend:
        while j < len(s):
            k = s.find("\n", j)
            k = len(s) if k < 0 else k
            line = s[j:k]
            j = min(k + 1, len(s))
            if (line.lstrip("\t") if strip else line) == delim:
                break
    return j


def _skip_dq(s: str, j: int) -> int:
    """Index just after the closing `"` of a double-quoted string that starts at j (after the opening quote)."""
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
        elif c == '"':
            return j + 1
        elif c == "$" and s[j + 1:j + 2] == "(":
            j = _scan_paren(s, j + 2) + 1
        elif c == "`":
            k = s.find("`", j + 1)
            j = n if k < 0 else k + 1
        else:
            j += 1
    return n


def _scan_paren(s: str, j: int) -> int:
    """Index of the `)` closing a `$(` whose body starts at j (quote-, comment- and heredoc-aware)."""
    n, depth, pend = len(s), 1, []
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            j = n if k < 0 else k + 1
            continue
        if c == '"':
            j = _skip_dq(s, j + 1)
            continue
        if c == "#" and (j == 0 or s[j - 1] in " \t\n;&|("):
            k = s.find("\n", j)
            j = n if k < 0 else k
            continue
        if c == "$" and s[j + 1:j + 2] == "(":
            depth += 1
            j += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        elif c == "<" and s[j:j + 2] == "<<" and s[j:j + 3] != "<<<":
            m = _HEREDOC.match(s, j)
            if m:
                pend.append((m.group(4) or m.group(2) or m.group(3) or "", bool(m.group(1))))
                j = m.end()
                continue
        elif c == "\n" and pend:
            j = _skip_heredoc_bodies(s, j + 1, pend)
            pend = []
            continue
        j += 1
    return n


class _Lexer:
    def __init__(self, s: str):
        self.s, self.i, self.items = s, 0, []
        self.cur: Word | None = None
        self.pending: list[tuple[Redir, str, bool]] = []
        self.want_delim: tuple[Redir, bool] | None = None
        self.want_target: Redir | None = None

    def _begin(self) -> Word:
        if self.cur is None:
            self.cur = Word("", False, [], self.i)
        return self.cur

    def _flush(self) -> None:
        w, self.cur = self.cur, None
        if w is None:
            return
        w.end = self.i
        if self.want_delim is not None:
            r, strip = self.want_delim
            self.want_delim = None
            r.target = w
            self.pending.append((r, w.text, strip))
        elif self.want_target is not None:
            self.want_target.target, self.want_target = w, None
        else:
            self.items.append(w)

    def _bodies(self) -> None:
        s = self.s
        for r, delim, strip in self.pending:
            lines: list[str] = []
            while self.i < len(s):
                k = s.find("\n", self.i)
                k = len(s) if k < 0 else k
                line = s[self.i:k]
                self.i = min(k + 1, len(s))
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                lines.append(line)
            r.body = "\n".join(lines)
        self.pending = []

    def _sub(self, start: int, end: int) -> None:
        w = self._begin()
        w.subs.append(self.s[start:end])
        w.text += self.s[start - 2:end + 1]

    def _redir(self) -> None:
        s, i = self.s, self.i
        if self.cur is not None and self.cur.text.isdigit() and not self.cur.quoted and self.cur.start + len(self.cur.text) == i:
            self.cur = None  # `2>` : the fd prefix is part of the operator
        else:
            self._flush()
        for op in ("<<<", "<<-", "<<", "&>>", "&>", ">>", ">&", ">|", "<&", "<>", ">", "<"):
            if s.startswith(op, i):
                break
        r = Redir(op, i)
        self.items.append(r)
        self.i += len(op)
        if op in ("<<", "<<-"):
            self.want_delim = (r, op == "<<-")
        else:
            self.want_target = r

    def run(self) -> list:
        s, n = self.s, len(self.s)
        while self.i < n:
            i, c = self.i, s[self.i]
            if c == "\\":
                if s[i + 1:i + 2] == "\n":
                    self.i += 2
                    continue
                w = self._begin()
                w.quoted, w.text = True, w.text + s[i + 1:i + 2]
                self.i += 2
            elif c == "'":
                w = self._begin()
                k = s.find("'", i + 1)
                k = n if k < 0 else k
                w.quoted, w.text = True, w.text + s[i + 1:k]
                self.i = k + 1
            elif c == '"':
                w, j = self._begin(), i + 1
                w.quoted = True
                while j < n and s[j] != '"':
                    if s[j] == "\\" and j + 1 < n:
                        w.text += s[j + 1]
                        j += 2
                    elif s[j] == "$" and s[j + 1:j + 2] == "(":
                        k = _scan_paren(s, j + 2)
                        self._sub(j + 2, k)
                        j = k + 1
                    elif s[j] == "`":
                        k = s.find("`", j + 1)
                        k = n if k < 0 else k
                        self._sub(j + 1, k)
                        j = k + 1
                    else:
                        w.text += s[j]
                        j += 1
                self.i = j + 1
            elif c == "$" and s[i + 1:i + 2] == "(":
                k = _scan_paren(s, i + 2)
                self._begin()
                self._sub(i + 2, k)
                self.i = k + 1
            elif c == "`":
                k = s.find("`", i + 1)
                k = n if k < 0 else k
                self._begin()
                self._sub(i + 1, k)
                self.i = k + 1
            elif c == "#" and self.cur is None:
                k = s.find("\n", i)
                self.i = n if k < 0 else k
            elif c in " \t":
                self._flush()
                self.i += 1
            elif c == "\n":
                self._flush()
                self.items.append(Op("\n", i))
                self.i += 1
                self._bodies()
            elif c in "<>" and s[i + 1:i + 2] == "(":  # process substitution: executed
                self._flush()
                k = _scan_paren(s, i + 2)
                w = self._begin()
                w.subs.append(s[i + 2:k])
                w.text = s[i:k + 1]
                self.i = k + 1
                self._flush()
            elif c in "<>" or (c == "&" and s[i + 1:i + 2] == ">"):
                self._redir()
            elif c in ";&|()":
                self._flush()
                two = s[i:i + 2]
                op = two if two in ("&&", "||", "|&", ";;") else c
                self.items.append(Op(op, i))
                self.i += len(op)
            else:
                self._begin().text += c
                self.i += 1
        self._flush()
        return self.items


def lex(src: str) -> list:
    return _Lexer(src).run()


# ---------------------------------------------------------------- structure
@dataclass
class Cmd:
    words: list[Word] = field(default_factory=list)   # after leading reserved words are peeled
    kws: list[Word] = field(default_factory=list)
    redirs: list[Redir] = field(default_factory=list)
    start: int = 0
    end: int = 0

    @property
    def header(self) -> bool:
        return any(k.text in _HEADER for k in self.kws)

    def heredoc(self) -> str | None:
        for r in self.redirs:
            if r.op in ("<<", "<<-") and r.body is not None:
                return r.body
        return None


@dataclass
class Loop:
    kind: str
    start: int
    cond_from: int
    cond_src: str = ""
    end: int = 0
    closed: bool = False
    top: bool = True
    in_body: bool = False
    cond: list[Cmd] = field(default_factory=list)
    body: list[Cmd] = field(default_factory=list)


@dataclass
class Parsed:
    src: str
    cmds: list[Cmd]
    loops: list[Loop]


def parse(src: str) -> Parsed:
    cmds: list[Cmd] = []
    cur = Cmd()

    def close():
        nonlocal cur
        if cur.words or cur.kws or cur.redirs:
            cmds.append(cur)
        cur = Cmd()

    for it in lex(src):
        if isinstance(it, Op):
            close()
        elif isinstance(it, Redir):
            cur.redirs.append(it)
        else:
            if not cur.words and not it.quoted and it.text in _PEEL and not cur.header:
                cur.kws.append(it)
            else:
                cur.words.append(it)
    close()
    for c in cmds:
        ws = c.kws + c.words
        if ws:
            c.start, c.end = ws[0].start, ws[-1].end
    loops: list[Loop] = []
    stack: list[Loop] = []
    for c in cmds:
        for kw in c.kws:
            t = kw.text
            if t in ("while", "until", "for", "select"):
                lp = Loop(t, kw.start, kw.end, top=not stack)
                stack.append(lp)
                loops.append(lp)
            elif t == "do":
                lp = next((x for x in reversed(stack) if not x.in_body), None)
                if lp:
                    lp.in_body = True
                    lp.cond_src = src[lp.cond_from:kw.start].strip(" \t\n;")
            elif t == "done" and stack:
                lp = stack.pop()
                lp.closed, lp.end = True, kw.end
        if c.words and not c.header:
            for lp in stack:
                (lp.body if lp.in_body else lp.cond).append(c)
    return Parsed(src, cmds, loops)


# ---------------------------------------------------------------- command analysis
@dataclass
class Finding:
    kind: str            # loop | follow | watch | watch-flag | poll-sleep | script-loop
    bounded: bool
    detail: str = ""
    loop: Loop | None = None


def core_words(words: list[Word]) -> tuple[list[Word], bool]:
    """The command proper (env assignments / nohup / time / ... stripped) and whether a `timeout N` bounds it."""
    ws, bounded = list(words), False
    while ws:
        t = ws[0].text
        if not ws[0].quoted and re.match(r"^[A-Za-z_]\w*=", t):
            ws.pop(0)
        elif os.path.basename(t) in _PREFIX:
            ws.pop(0)
            while ws and (ws[0].text.startswith("-") or re.match(r"^[A-Za-z_]\w*=", ws[0].text)):
                ws.pop(0)
        elif os.path.basename(t) in ("timeout", "gtimeout"):
            ws.pop(0)
            while ws and ws[0].text.startswith("-"):
                took = ws.pop(0).text
                if took in ("-s", "-k", "--signal", "--kill-after") and ws:
                    ws.pop(0)
            if ws and _DURATION.match(ws[0].text):
                ws.pop(0)
                bounded = True
        else:
            break
    return ws, bounded


def wrapper_of(words: list[Word]) -> dict | None:
    """Options of a `bg_run.py` invocation among `words` (None when this command is not the wrapper)."""
    idx = next((i for i, w in enumerate(words[:4]) if os.path.basename(w.text) == "bg_run.py"), None)
    if idx is None:
        return None
    opts: dict = {"flags": set(), "payload": None}
    rest, i = words[idx + 1:], 0
    while i < len(rest):
        t = rest[i].text
        if t == "--":
            tail = [w.text for w in rest[i + 1:]]
            opts["payload"] = tail[0] if len(tail) == 1 else shlex.join(tail) if tail else None
            break
        name, eq, val = t.partition("=")
        if name in _WRAPPER_VALUE_OPTS:
            if not eq and i + 1 < len(rest):
                i += 1
                val = rest[i].text
            opts[name.lstrip("-")] = val
            if name == "--command":
                opts["payload"] = val
        elif t.startswith("--"):
            opts["flags"].add(name.lstrip("-"))
        i += 1
    return opts


def shell_c_script(ws: list[Word]) -> str | None:
    """The script string of `bash -c STR` (words already core-stripped), else None."""
    if not ws or os.path.basename(ws[0].text).lstrip("-") not in SHELLS:
        return None
    for i, w in enumerate(ws[1:], 1):
        if re.match(r"^-[a-zA-Z]*c[a-zA-Z]*$", w.text) and i + 1 < len(ws):
            return ws[i + 1].text
    return None


_EXEMPT_COND = re.compile(r"^\s*(?:IFS=\S*\s+)?(?:read|getopts)\b|\$#")  # `while read` is stdin-bounded; `while [ $# ..]` is arg parsing


def default_read_file(path: Path, roots: list[Path]) -> str | None:
    try:
        rp = path.resolve()
        ok = any(rp == r or r in rp.parents for r in roots) or str(rp).startswith(("/private/tmp/claude-", "/tmp/claude-"))
        if not ok or not rp.is_file() or rp.stat().st_size > MAX_SCRIPT_BYTES:
            return None
        return rp.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def py_loops(text: str) -> list[int]:
    """Line numbers of `while True`/`while 1` loops with no break/return/raise of their own (Python `ast`)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value:
            stack, exits = list(node.body), False
            while stack and not exits:
                n = stack.pop()
                if isinstance(n, (ast.Break, ast.Return, ast.Raise)):
                    exits = True
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                elif isinstance(n, (ast.While, ast.For)):
                    stack.extend(x for x in ast.walk(n) if isinstance(x, (ast.Return, ast.Raise)))
                else:
                    stack.extend(ast.iter_child_nodes(n))
            if not exits:
                out.append(node.lineno)
    return out


def git_root(cwd: Path) -> Path | None:
    for p in (cwd, *cwd.parents):
        if (p / ".git").exists():
            return p
    return None


@dataclass
class Ctx:
    cwd: Path
    roots: list[Path]
    read_file: Callable[[Path], str | None]
    reads: int = 0


def make_ctx(cwd: str | None = None, read_file: Callable[[Path], str | None] | None = None,
             extra_roots: list[Path] | None = None) -> Ctx:
    c = Path(cwd or os.getcwd())
    roots = [r for r in (git_root(c), *(extra_roots or [])) if r]
    return Ctx(c, roots, read_file or (lambda p: default_read_file(p, roots)))


def _script_target(ws: list[Word]) -> Path | None:
    """The script file an invocation runs (`./x.sh`, `bash x.sh`, `python x.py`), else None."""
    base = os.path.basename(ws[0].text)
    if base.lstrip("-") in SHELLS or re.match(r"^python[\d.]*$", base):
        for w in ws[1:]:
            if w.text == "-m" or (w.text.startswith("-") and len(w.text) > 1):
                if w.text == "-m":
                    return None
                continue
            return Path(w.text) if w.text.endswith(_SCRIPT_SUFFIX) or "/" in w.text else None
        return None
    if base.endswith(_SCRIPT_SUFFIX) or ws[0].text.startswith(("./", "../", "/", "~")):
        return Path(ws[0].text)
    return None


def _scan_script(path: Path, ctx: Ctx, bounded: bool, depth: int) -> list[Finding]:
    if ctx.reads >= MAX_SCRIPT_READS or depth >= MAX_DEPTH:
        return []
    target = path if path.is_absolute() else ctx.cwd / path
    text = ctx.read_file(target)
    ctx.reads += 1
    if text is None:
        return []
    first = text.split("\n", 1)[0]
    is_py = target.suffix == ".py" or ("python" in first and first.startswith("#!"))
    if is_py:
        return [Finding("script-loop", bounded, f"{target}:{ln} infinite `while True` with no break/return")
                for ln in py_loops(text)]
    if not (target.suffix in (".sh", ".bash", ".zsh") or (first.startswith("#!") and re.search(r"\b(?:ba|z|da|k)?sh\b", first))):
        return []  # not a shell script (a node/binary launcher): not judged
    sub = Ctx(target.parent, ctx.roots, ctx.read_file, ctx.reads)
    found = analyze(text, ctx=sub, bounded=bounded, depth=depth + 1, from_script=True)
    ctx.reads = sub.reads
    return [Finding("script-loop", f.bounded, f"{target}: {f.kind} {f.detail}".strip()) for f in found if f.kind in OPEN_ENDED]


def analyze(src: str, *, ctx: Ctx | None = None, bounded: bool = False, depth: int = 0,
            from_script: bool = False) -> list[Finding]:
    """Every open-ended / poll shape that would EXECUTE when `src` runs. Quoted text and file-bound heredocs are data."""
    if depth > MAX_DEPTH:
        return []
    ctx = ctx or make_ctx()
    p = parse(src)
    out: list[Finding] = []
    for lp in p.loops:
        if lp.kind in ("while", "until") and lp.closed and not _EXEMPT_COND.search(lp.cond_src):
            body = [core_words(c.words)[0] for c in lp.body]
            if body and all(w and os.path.basename(w[0].text) in _PURE_BODY for w in body) and any(
                    os.path.basename(w[0].text) == "sleep" for w in body if w):
                # sleep + a readiness test only: a POLL. Never acceptable, bounded (`timeout N`) or not (owner 2026-11-14).
                out.append(Finding("poll", False, f"{lp.kind} {lp.cond_src[:60]}", lp))
            else:
                out.append(Finding("loop", bounded, f"{lp.kind} {lp.cond_src[:60]}", lp))
    cwd = ctx.cwd
    for c in p.cmds:
        for w in c.words:
            for sub in w.subs:
                out += analyze(sub, ctx=ctx, bounded=bounded, depth=depth + 1, from_script=from_script)
        if c.header or not c.words:
            continue
        ws, tb = core_words(c.words)
        b = bounded or tb
        if not ws:
            continue
        t = [w.text for w in ws]
        base = os.path.basename(t[0])
        if base == "cd" and len(t) > 1:
            nxt = Path(os.path.expanduser(t[1]))
            cwd = nxt if nxt.is_absolute() else cwd / nxt
            ctx = Ctx(cwd, ctx.roots, ctx.read_file, ctx.reads)
            continue
        wrap = wrapper_of(ws)
        if wrap is not None:
            if wrap["payload"]:
                inner_bounded = b or "done-when" in wrap or "long-lived" in wrap["flags"]
                out += analyze(wrap["payload"], ctx=ctx, bounded=inner_bounded, depth=depth + 1, from_script=from_script)
            continue
        script = shell_c_script(ws)
        if script is not None:
            out += analyze(script, ctx=ctx, bounded=b, depth=depth + 1, from_script=from_script)
            continue
        if base == "eval":
            out += analyze(" ".join(t[1:]), ctx=ctx, bounded=b, depth=depth + 1, from_script=from_script)
            continue
        if base.lstrip("-") in SHELLS and (body := c.heredoc()) is not None:
            out += analyze(body, ctx=ctx, bounded=b, depth=depth + 1, from_script=from_script)
        if base == "tail" and any(not w.quoted and _FOLLOW.match(w.text) for w in ws[1:]):
            out.append(Finding("follow", b, "tail -f"))
        elif base == "watch" and len(t) > 1:
            out.append(Finding("watch", b, "watch"))
        elif base == "sleep" and len(t) > 1 and re.match(r"^\d", t[1]):
            out.append(Finding("poll-sleep", b, f"sleep {t[1]}"))
        if any(not w.quoted and (w.text == "--watch" or w.text.startswith("--watch=")) for w in ws[1:]):
            out.append(Finding("watch-flag", b, "--watch"))
        target = _script_target(ws)
        if target is not None:
            out += _scan_script(target, ctx, b, depth)
    return out


def open_ended(command: str, *, ctx: Ctx | None = None) -> list[Finding]:
    """What the guard refuses: UNBOUNDED never-ending shapes, and every POLL (sleep + readiness test) bounded or not."""
    return [f for f in analyze(command, ctx=ctx) if f.kind in OPEN_ENDED and not f.bounded]
