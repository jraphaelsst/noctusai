"""File directives + statement splitting for ``noctus.dev.migrate_product``.

A migration file may carry runner directives as ``-- noc:<name> [value]`` comment
lines in its LEADING comment block (blank / ``--`` lines before the first
statement):

``-- noc:no-transaction``
    Run the file outside the runner's implicit transaction, statement by
    statement (needed for ``CREATE INDEX CONCURRENTLY`` / ``DROP INDEX
    CONCURRENTLY``, which Postgres refuses inside a transaction block).
``-- noc:lock-timeout <value>``
    Override the runner's default ``lock_timeout`` for this file. ``0`` turns it
    off; otherwise ``<int><unit>`` with unit in ``ms|s|min|h|d`` (e.g. ``30s``).

Parsing is STRICT: an unknown directive, a bad / missing value, a duplicate, a
directive placed after the header block, or transaction control inside a
``no-transaction`` file is a ``DirectiveError`` (the runner refuses before any
DDL) -- never silently ignored. KB § PATTERNS/backend/postgres-craft.md § 6.3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_LOCK_TIMEOUT = "5s"

_DIRECTIVE_LINE = re.compile(r"^\s*--\s*noc:(\S*)(?:[ \t]+(.*?))?\s*$")
_LOCK_VALUE = re.compile(r"^(?:0|[1-9][0-9]{0,8}(?:ms|s|min|h|d))$")
_KNOWN = {"no-transaction", "lock-timeout"}
_TX_CONTROL = {"BEGIN", "START", "COMMIT", "END", "ROLLBACK", "ABORT", "SAVEPOINT", "RELEASE"}


class DirectiveError(ValueError):
    """A malformed / misplaced ``-- noc:`` directive (refuse, never ignore)."""


@dataclass(frozen=True)
class Directives:
    no_transaction: bool = False
    lock_timeout: str = DEFAULT_LOCK_TIMEOUT  # "0" = off


def validate_lock_timeout(value: str) -> str:
    if not _LOCK_VALUE.match(value or ""):
        raise DirectiveError(
            f"invalid lock-timeout {value!r}: expected 0 (off) or <integer><unit> with unit "
            "ms|s|min|h|d (e.g. 30s)"
        )
    return value


def parse_directives(sql: str) -> Directives:
    no_tx = False
    lock: str | None = None
    in_header = True
    for lineno, line in enumerate(sql.splitlines(), start=1):
        stripped = line.strip()
        m = _DIRECTIVE_LINE.match(line)
        if m:
            name, arg = m.group(1), (m.group(2) or "").strip()
            if not in_header:
                raise DirectiveError(
                    f"line {lineno}: '-- noc:{name}' must be in the leading comment block, "
                    "before the first statement"
                )
            if name not in _KNOWN:
                raise DirectiveError(f"line {lineno}: unknown directive 'noc:{name}' (known: {sorted(_KNOWN)})")
            if name == "no-transaction":
                if arg:
                    raise DirectiveError(f"line {lineno}: noc:no-transaction takes no value (got {arg!r})")
                if no_tx:
                    raise DirectiveError(f"line {lineno}: duplicate noc:no-transaction")
                no_tx = True
            else:
                if lock is not None:
                    raise DirectiveError(f"line {lineno}: duplicate noc:lock-timeout")
                try:
                    lock = validate_lock_timeout(arg)
                except DirectiveError as exc:
                    raise DirectiveError(f"line {lineno}: {exc}") from None
        elif stripped and not stripped.startswith("--"):
            in_header = False
    return Directives(no_transaction=no_tx, lock_timeout=lock if lock is not None else DEFAULT_LOCK_TIMEOUT)


def lock_timeout_literal(value: str) -> str:
    """``'5s'`` / ``0`` as a SQL literal for ``SET [LOCAL] lock_timeout``."""
    return "0" if value == "0" else f"'{value}'"


_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _strip_leading_comments(stmt: str) -> str:
    s = stmt
    while True:
        s = s.lstrip()
        if s.startswith("--"):
            nl = s.find("\n"); s = "" if nl < 0 else s[nl + 1:]
        elif s.startswith("/*"):
            e = s.find("*/"); s = "" if e < 0 else s[e + 2:]
        else:
            return s


def split_statements(sql: str) -> list[str]:
    """Split on top-level ``;`` (quotes, E'' escapes, $tag$ bodies, comments respected).

    Returns non-empty statements WITHOUT the trailing ``;``; comment-only chunks dropped.
    """
    out: list[str] = []
    cur: list[str] = []
    has_code = False
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        two = sql[i:i + 2]
        if two == "--":
            j = sql.find("\n", i)
            j = n if j < 0 else j
            cur.append(sql[i:j]); i = j; continue
        if two == "/*":
            depth, j = 1, i + 2
            while j < n and depth:
                if sql[j:j + 2] == "/*": depth += 1; j += 2
                elif sql[j:j + 2] == "*/": depth -= 1; j += 2
                else: j += 1
            cur.append(sql[i:j]); i = j; continue
        if c in ("'", '"'):
            escape = c == "'" and i > 0 and sql[i - 1] in "eE" and (i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] == "_"))
            j = i + 1
            while j < n:
                if escape and sql[j] == "\\":
                    j += 2; continue
                if sql[j] == c:
                    if sql[j + 1:j + 2] == c:
                        j += 2; continue
                    break
                j += 1
            cur.append(sql[i:j + 1]); i = j + 1; has_code = True; continue
        if c == "$":
            m = _DOLLAR_TAG.match(sql, i)
            if m:
                j = sql.find(m.group(0), m.end())
                end = n if j < 0 else j + len(m.group(0))
                cur.append(sql[i:end]); i = end; has_code = True; continue
        if c == ";":
            if has_code:
                out.append(_strip_leading_comments("".join(cur)))
            cur, has_code = [], False
            i += 1; continue
        if not c.isspace():
            has_code = True
        cur.append(c); i += 1
    if has_code:
        out.append(_strip_leading_comments("".join(cur)))
    return out


def first_keyword(stmt: str) -> str:
    """First SQL word of a statement, skipping leading comments."""
    m = re.match(r"[A-Za-z]+", _strip_leading_comments(stmt))
    return m.group(0).upper() if m else ""


def check_no_transaction_statements(stmts: list[str]) -> None:
    """A no-transaction file must not carry its own transaction control."""
    for s in stmts:
        if first_keyword(s) in _TX_CONTROL:
            raise DirectiveError(
                f"noc:no-transaction file contains transaction control ({first_keyword(s)}); "
                "remove it -- every statement runs on its own"
            )


_BARE_HEADS = (
    # PreventInTransactionBlock statements (PostgreSQL docs, each command's page): cannot share a
    # request with a SET LOCAL (a multi-statement request is a transaction block, live 25001).
    r"VACUUM\b", r"CLUSTER\b", r"DISCARD\b", r"ALTER\s+SYSTEM\b",
    r"(?:CREATE|DROP)\s+(?:DATABASE|TABLESPACE)\b",
    r"REINDEX\s+(?:\(.*?\)\s*)?(?:DATABASE|SCHEMA|SYSTEM)\b",
    r"(?:CREATE|DROP)\s+SUBSCRIPTION\b",
)
_BARE_HEAD_RE = re.compile(r"^(?:" + "|".join(_BARE_HEADS) + ")", re.I | re.S)
_CONCURRENTLY_RE = re.compile(r"\bCONCURRENTLY\b", re.I)


def needs_bare_request(stmt: str) -> bool:
    """True when ``stmt`` cannot run in a transaction block, so it is sent as its own request
    WITHOUT a lock_timeout guard: any ``CONCURRENTLY`` (CREATE/DROP INDEX, REINDEX, REFRESH
    MATERIALIZED VIEW) or one of ``_BARE_HEADS``. Explicit list, not inference."""
    body = _strip_leading_comments(stmt)
    return bool(_CONCURRENTLY_RE.search(body) or _BARE_HEAD_RE.match(body))
