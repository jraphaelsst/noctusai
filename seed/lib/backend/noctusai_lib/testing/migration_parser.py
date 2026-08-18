"""
Regex-based parser for migration DDL files.

Phase 0 discovery (`projects/mock-supabase-schema-validation` §5.1) showed
the migration corpus is uniform enough for a hand-rolled parser: 269
column-defining DDL statements across 48 files, all fitting one of three
shapes (CREATE TABLE, ALTER TABLE ADD COLUMN, ALTER TABLE DROP COLUMN).
No quoted identifiers, no weird dialect. 120 CREATE
FUNCTION bodies and 11 DO blocks must be handled — function bodies are
skipped wholesale, DO blocks are walked (they can wrap conditional
ADD COLUMN guards).

Shape of the output:

    {
        "therapy.session_records": {"id", "appointment_id", ...},
        "therapy.session_summary_versions": {"id", "session_record_id", ...},
        "public.notifications": {"id", "user_id", "org_id", ...},
        ...
    }

Bare-tablename CREATE TABLE (22 cases in the repo, all platform tables)
coerce to `public.<table>`.

Graceful degradation (per project §7 Q4): tables that can't be parsed log
a WARNING and are omitted from the schema map; the blind spot reopens
per-table but loudly, not silently.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex building blocks
# ---------------------------------------------------------------------------

_IDENT = r"[a-zA-Z_][a-zA-Z_0-9]*"

_CREATE_TABLE_HEAD_RE = re.compile(
    rf"\bCREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
    rf"(?:(?P<schema>{_IDENT})\.)?(?P<table>{_IDENT})\s*\(",
    re.IGNORECASE,
)

# One `ALTER TABLE [IF EXISTS] [ONLY] [schema.]table` head. The clauses
# that follow are matched SEPARATELY (below) rather than folded into this
# pattern, because a single ALTER may carry many of them:
#
#     ALTER TABLE social_wiring.leads
#         ADD COLUMN IF NOT EXISTS external_source  TEXT,
#         ADD COLUMN IF NOT EXISTS external_lead_id TEXT;
#
# A combined `ALTER…[\s\S]*?ADD COLUMN (\w+)` pattern captures only the
# FIRST clause: `finditer` resumes after the match, and the next attempt
# needs another `ALTER TABLE` head that is not there. Every column after
# the first was silently missing from the mock schema registry — across
# ~20 fleet migrations — so a test touching one failed with "table has no
# column X" naming a column the migration plainly adds.
_ALTER_TABLE_HEAD_RE = re.compile(
    rf"\bALTER\s+TABLE(?:\s+IF\s+EXISTS)?\s+"
    rf"(?:ONLY\s+)?"
    rf"(?:(?P<schema>{_IDENT})\.)?(?P<table>{_IDENT})\b",
    re.IGNORECASE,
)

_ADD_COLUMN_CLAUSE_RE = re.compile(
    rf"\bADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+(?P<column>{_IDENT})\b",
    re.IGNORECASE,
)

_DROP_COLUMN_CLAUSE_RE = re.compile(
    rf"\bDROP\s+COLUMN(?:\s+IF\s+EXISTS)?\s+(?P<column>{_IDENT})\b",
    re.IGNORECASE,
)

# RENAME. The module docstring above used to assert the corpus contained
# "no RENAME COLUMN" — true when it was written, false from migration
# `060` (social-wiring's `negociacoes_venda` -> `atendimentos`).
#
# Leaving it unhandled is not a neutral gap. Renaming a table made the new
# name unknown to the schema map, so the mock stopped validating it
# entirely (graceful degradation — the blind spot reopens silently for
# that table), while the OLD column name survived on the *other* side of
# the rename and every honest query against the new name failed with
# "table has no column X" naming a column the migration plainly creates.
# One rename produced both a false failure and a silent hole at once.
_RENAME_TABLE_CLAUSE_RE = re.compile(
    rf"\bRENAME\s+TO\s+(?P<new_table>{_IDENT})\b",
    re.IGNORECASE,
)

_RENAME_COLUMN_CLAUSE_RE = re.compile(
    rf"\bRENAME\s+COLUMN\s+(?P<old>{_IDENT})\s+TO\s+(?P<new>{_IDENT})\b",
    re.IGNORECASE,
)


def _alter_table_segments(stmt: str):
    """Yield `(schema, table, body)` per ALTER TABLE head in `stmt`.

    `body` runs to the next ALTER head (or the end), so each head owns
    exactly its own clauses — several ALTERs inside one DO block stay
    correctly attributed instead of bleeding into each other.
    """
    heads = list(_ALTER_TABLE_HEAD_RE.finditer(stmt))
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(stmt)
        yield head.group("schema"), head.group("table"), stmt[head.end():end]

# Table-level constraints inside a CREATE TABLE body that must NOT be
# parsed as columns. Matched at line start (after optional whitespace).
_CONSTRAINT_KEYWORDS = (
    "PRIMARY",
    "FOREIGN",
    "CONSTRAINT",
    "UNIQUE",
    "CHECK",
    "EXCLUDE",
    "LIKE",  # CREATE TABLE foo (LIKE other INCLUDING ALL) — not a column
)

# ---------------------------------------------------------------------------
# Comment stripping + dollar-quote-aware statement splitting
# ---------------------------------------------------------------------------


# `$$` or `$tag$` — Postgres' dollar-quote openers. `pg_get_functiondef`
# emits `$function$`, so a migration written by copying a live definition
# out of the database uses the tagged form.
_DOLLAR_TAG_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def _strip_line_comments(sql: str) -> str:
    """Strip `-- ...` comments. Preserves line structure."""
    # Remove -- comments to end of line, keep the newline.
    return re.sub(r"--[^\n]*", "", sql)


def _strip_block_comments(sql: str) -> str:
    """Strip `/* ... */` comments. Handles nested blocks defensively."""
    # Simple non-nested (no migration in this repo uses nested /* */).
    return re.sub(r"/\*[\s\S]*?\*/", "", sql)


def _walk_statements(sql: str) -> Iterable[str]:
    """Yield top-level SQL statements, one at a time.

    Handles:
      - semicolon-separated statements at paren-depth 0
      - $$ ... $$ AND $tag$ ... $tag$ dollar-quoted blocks (function bodies,
        DO blocks) treated atomically
      - nested parens in types/defaults/constraints

    Tag variants used to be unhandled ("none exist in our corpus"), which
    stopped being true the moment a migration was written by copying a
    function definition out of the database: `pg_get_functiondef` emits
    `AS $function$ ... $function$`, not `$$`. The failure was silent and
    total — an unrecognised opener left the walker treating the function
    BODY as ordinary SQL, so every `;` inside it split a statement, and the
    whole file parsed to nothing. social-wiring's migration `060` produced
    exactly that: an empty schema map, which downstream reads as "this table
    has no columns" rather than as a parse failure.
    """
    i = 0
    n = len(sql)
    start = 0
    paren_depth = 0
    dollar_tag: str | None = None   # the exact opener, e.g. "$$" or "$function$"

    while i < n:
        ch = sql[i]

        if dollar_tag is not None:
            # Only the MATCHING tag closes the block — `$$` must not close a
            # `$function$`, or the tail of the body leaks back into the SQL.
            if ch == "$" and sql.startswith(dollar_tag, i):
                i += len(dollar_tag)
                dollar_tag = None
                continue
            i += 1
            continue

        if ch == "$":
            m = _DOLLAR_TAG_RE.match(sql, i)
            if m:
                dollar_tag = m.group(0)
                i += len(dollar_tag)
                continue

        # Handle string literals (single-quoted) — skip contents to avoid
        # interpreting `;` or `(` inside strings.
        if ch == "'":
            i += 1
            while i < n:
                if sql[i] == "'":
                    # Handle doubled '' as escape
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            if paren_depth > 0:
                paren_depth -= 1
        elif ch == ";" and paren_depth == 0:
            stmt = sql[start : i + 1].strip()
            if stmt:
                yield stmt
            start = i + 1

        i += 1

    # Trailing statement without a closing semicolon (rare but possible).
    tail = sql[start:].strip()
    if tail:
        yield tail


# ---------------------------------------------------------------------------
# Body extraction + column parsing
# ---------------------------------------------------------------------------


def _extract_table_body(stmt: str, body_start: int) -> str | None:
    """Given a statement starting with `CREATE TABLE ... (`, extract the
    body between matched parens. Returns None if parens don't balance."""
    depth = 0
    i = body_start - 1  # body_start points AFTER the opening `(`
    # Walk forward from the `(` we already matched.
    # body_start is the position of `(`; we want contents after it.
    # Actually caller passes position of the opening paren itself.
    i = body_start
    assert stmt[i] == "(", f"expected '(' at {i}, got {stmt[i]!r}"
    content_start = i + 1
    depth = 1
    i = content_start
    while i < len(stmt):
        ch = stmt[i]
        if ch == "'":
            i += 1
            while i < len(stmt):
                if stmt[i] == "'":
                    if i + 1 < len(stmt) and stmt[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return stmt[content_start:i]
        i += 1
    return None


def _split_top_level_commas(body: str) -> list[str]:
    """Split a CREATE TABLE body on top-level commas (paren-depth 0, not inside strings)."""
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'":
            buf.append(ch)
            i += 1
            while i < len(body):
                buf.append(body[i])
                if body[i] == "'":
                    if i + 1 < len(body) and body[i + 1] == "'":
                        buf.append(body[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


_COLUMN_HEAD_RE = re.compile(rf"^\s*(?P<name>{_IDENT})\b", re.IGNORECASE)


def _is_constraint_line(line: str) -> bool:
    stripped = line.lstrip()
    head = stripped.split(maxsplit=1)
    if not head:
        return True  # empty → treat as skip
    first = head[0].upper()
    return first in _CONSTRAINT_KEYWORDS


def _parse_column_names(body: str) -> list[str]:
    """Extract column names from a CREATE TABLE body."""
    cols: list[str] = []
    for part in _split_top_level_commas(body):
        if _is_constraint_line(part):
            continue
        m = _COLUMN_HEAD_RE.match(part)
        if m:
            cols.append(m.group("name"))
    return cols


# ---------------------------------------------------------------------------
# Top-level parse entry points
# ---------------------------------------------------------------------------


def _qualify(schema: str | None, table: str) -> str:
    return f"{(schema or 'public').lower()}.{table.lower()}"


def parse_sql(
    sql: str,
    *,
    source_label: str = "<unknown>",
    into: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    """Parse a blob of SQL into a `{qualified_table: {columns}}` map.

    WARN + skip per-table on any shape that doesn't parse.

    `into` accumulates across calls. Migrations apply SEQUENTIALLY against
    one evolving schema, so anything that mutates an existing table — a
    rename, a `DROP COLUMN` — is only meaningful when the parse can see
    what earlier files built. Passing a shared map is how `parse_files`
    models that; omitting it parses one blob in isolation.
    """
    sql_clean = _strip_block_comments(_strip_line_comments(sql))

    schema_map: dict[str, set[str]] = {} if into is None else into

    for stmt in _walk_statements(sql_clean):
        # Quick-reject statements that can't define a column.
        upper = stmt.upper()

        # CREATE FUNCTION / CREATE OR REPLACE FUNCTION — function bodies
        # arrive as single statements because the $$ ... $$ is atomic.
        # Just skip wholesale; they don't define tables.
        if re.search(r"\bCREATE(\s+OR\s+REPLACE)?\s+FUNCTION\b", upper):
            continue
        # DO $$ ... $$ blocks: may contain ALTER TABLE ADD COLUMN guards.
        # Run the ALTER regex regardless — it'll find matches inside DO
        # body when the whole statement is concatenated.
        if "CREATE TABLE" in upper:
            m = _CREATE_TABLE_HEAD_RE.search(stmt)
            if m:
                body_start = stmt.find("(", m.end() - 1)
                if body_start >= 0:
                    body = _extract_table_body(stmt, body_start)
                    if body is not None:
                        qualified = _qualify(m.group("schema"), m.group("table"))
                        cols = _parse_column_names(body)
                        if cols:
                            existing = schema_map.setdefault(qualified, set())
                            existing.update(cols)
                            continue
                logger.warning(
                    "mock-schema: unparseable CREATE TABLE in %s — skipping table %s.%s",
                    source_label,
                    m.group("schema") or "public",
                    m.group("table"),
                )

        # ALTER TABLE ADD COLUMN — may appear standalone OR inside DO block
        # body. Our statement walker treats DO as atomic, so scan for
        # ALTER ... ADD COLUMN matches inside the whole stmt.
        if "ADD COLUMN" in upper or "DROP COLUMN" in upper:
            for schema, table, body in _alter_table_segments(stmt):
                qualified = _qualify(schema, table)
                for m in _ADD_COLUMN_CLAUSE_RE.finditer(body):
                    schema_map.setdefault(qualified, set()).add(m.group("column"))
                for m in _DROP_COLUMN_CLAUSE_RE.finditer(body):
                    existing = schema_map.get(qualified)
                    if existing:
                        existing.discard(m.group("column"))

        # RENAME — same DO-block-tolerant scan as ADD/DROP above. Applied
        # AFTER them so a single migration that adds a column and then
        # renames the table still lands the column on the new name.
        if "RENAME" in upper:
            for schema, table, body in _alter_table_segments(stmt):
                qualified = _qualify(schema, table)

                for m in _RENAME_COLUMN_CLAUSE_RE.finditer(body):
                    existing = schema_map.get(qualified)
                    if existing and m.group("old") in existing:
                        existing.discard(m.group("old"))
                        existing.add(m.group("new"))
                    elif existing is not None:
                        # The column was never recorded — the rename is real
                        # in Postgres but our map cannot represent it. Add the
                        # new name anyway (a query against it is legitimate)
                        # rather than leave a hole that reads as "no such
                        # column".
                        existing.add(m.group("new"))

                for m in _RENAME_TABLE_CLAUSE_RE.finditer(body):
                    new_qualified = _qualify(schema, m.group("new_table"))
                    cols = schema_map.pop(qualified, None)
                    if cols is not None:
                        # Carry the columns across; a later migration's
                        # ADD COLUMN on the new name merges into the same set.
                        schema_map.setdefault(new_qualified, set()).update(cols)

    return schema_map


def parse_files(paths: Iterable[Path]) -> dict[str, set[str]]:
    """Parse multiple migration files in order, merging into one schema map."""
    # ONE accumulating map, threaded through every file in order — not a
    # per-file parse merged at the end. The old shape could only ever ADD:
    # each file was parsed against an empty map, so a later migration's
    # `DROP COLUMN` or `RENAME` had nothing to act on and was silently
    # discarded by the union merge. That made the map a record of every
    # column that ever existed rather than the schema as it now stands.
    merged: dict[str, set[str]] = {}
    for path in paths:
        try:
            sql = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("mock-schema: could not read %s: %s — skipping", path, exc)
            continue
        parse_sql(sql, source_label=str(path), into=merged)
    return merged


__all__ = ["parse_sql", "parse_files"]
