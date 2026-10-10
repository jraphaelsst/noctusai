"""
Regex-based parser for migration DDL files.

Phase 0 discovery (`projects/mock-supabase-schema-validation` §5.1) showed
the migration corpus is uniform enough for a hand-rolled parser: 269
column-defining DDL statements across 48 files, all fitting one of three
shapes (CREATE TABLE, DROP TABLE, ALTER TABLE ADD COLUMN, ALTER TABLE DROP COLUMN).
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

# `DROP TABLE [IF EXISTS] [schema.]t [, [schema.]t ...] [CASCADE|RESTRICT]`.
# The name list is captured whole and split on commas below.
_DROP_TABLE_RE = re.compile(
    rf"\bDROP\s+TABLE(?:\s+IF\s+EXISTS)?\s+"
    rf"(?P<names>(?:{_IDENT}\.)?{_IDENT}(?:\s*,\s*(?:{_IDENT}\.)?{_IDENT})*)",
    re.IGNORECASE,
)
_QUALIFIED_NAME_RE = re.compile(rf"^(?:(?P<schema>{_IDENT})\.)?(?P<table>{_IDENT})$")

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
#
# `(?!\.)` at the end is load-bearing, found while building the dynamic-DDL
# blind-spot detector (2026-09-18). `ALTER TABLE erp.%I ADD COLUMN x TEXT`
# (schema literal, table a runtime `%I` placeholder — `_dynamic_ddl_blind_
# spots` handles THAT case as a declared unknown) does not fail to match
# here; it MISmatches. `_IDENT` cannot consume `%I`, so the optional
# `schema.` group backtracks away and the engine instead binds `table` to
# `erp` alone — the SCHEMA name, reinterpreted as a bare table. The
# static ADD/DROP-COLUMN scan below then runs against that bogus head and
# fabricates a phantom table named after the schema (`public.erp`) holding
# whatever column the dynamic clause names. A schema is never itself
# immediately followed by `.` unless it WAS a `schema.table` qualifier that
# failed to resolve — a genuine bare table name never is — so refusing to
# match in that shape turns a silent corruption into the same clean "no
# match, nothing fabricated" the dynamic-DDL detector already expects.
_ALTER_TABLE_HEAD_RE = re.compile(
    rf"\bALTER\s+TABLE(?:\s+IF\s+EXISTS)?\s+"
    rf"(?:ONLY\s+)?"
    rf"(?:(?P<schema>{_IDENT})\.)?(?P<table>{_IDENT})(?!\.)\b",
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

# ---------------------------------------------------------------------------
# Dynamic DDL — genuinely unresolvable, and that fact must be SAID, not
# silently missed.
#
# `EXECUTE format('ALTER TABLE %s.%I RENAME COLUMN old TO new', schema, t)`
# builds its DDL at runtime from a loop variable (`social-wiring`'s
# migration 046: a `FOREACH t IN ARRAY [...]` over six literal table names,
# rename applied via `%I`). No regex over the migration file can know what
# `t` resolves to on any given loop iteration — that is not a gap in this
# parser's cleverness, it is what "dynamic" means. Pretending otherwise
# (resolving the FOREACH/ARRAY literal to special-case this migration's
# shape) would be a fork wearing a parser's clothes; the file's own
# docstring is explicit that a hand-rolled REGEX parser, not a PL/pgSQL
# interpreter, is the deliberate scope.
#
# What CAN be said truthfully: the format() TEMPLATE's other arguments —
# the column names in a RENAME COLUMN/ADD COLUMN/DROP COLUMN clause — are
# ordinary literal text in every migration seen so far (only the table/
# object identifier is parameterized via %I/%s), so those are reported.
# The table itself is not, and is never guessed. Before this, the whole
# statement was invisible: `_ALTER_TABLE_HEAD_RE` requires a real
# identifier, `%I` isn't one, so no `_alter_table_segments` entry was ever
# produced for it — not a false answer, just a total silence. This makes
# that silence a NAMED blind spot instead.
_DYNAMIC_EXEC_QUOTED_RE = re.compile(
    r"\bEXECUTE\s+(?:format\s*\(\s*)?'((?:[^']|'')*)'",
    re.IGNORECASE,
)

# The `$tag$ ... $tag$` sibling of the quoted form above — same idiom, a
# dollar-quoted string instead of `'...'` (used elsewhere in the corpus for
# EXECUTE format() bodies that themselves contain single quotes). No known
# migration puts column DDL inside one today, but the RLS/policy EXECUTEs
# that DO use this form make it cheap insurance rather than a gap that
# reopens the moment a future migration does.
_DYNAMIC_EXEC_DOLLAR_RE = re.compile(
    r"\bEXECUTE\s+format\s*\(\s*\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*|)\$"
    r"(?P<body>[\s\S]*?)\$(?P=tag)\$",
    re.IGNORECASE,
)


def _classify_dynamic_ddl(body: str) -> list[dict[str, str | None]]:
    """Given the literal SQL text passed to `EXECUTE [format(]...`, return
    the column/table-shape DDL classes it carries. Empty when the dynamic
    statement doesn't touch a table's columns at all — RLS/policy/index/
    trigger/constraint-NAME-only EXECUTEs are the overwhelming majority of
    the corpus's dynamic SQL and are out of this parser's scope already
    (see module docstring); flagging those as blind spots would be noise
    that trains people to ignore the real ones.
    """
    upper = body.upper()
    if "ALTER TABLE" not in upper:
        return []
    found: list[dict[str, str | None]] = []
    for m in _RENAME_COLUMN_CLAUSE_RE.finditer(body):
        found.append({
            "class": "rename_column",
            "old_column": m.group("old"),
            "new_column": m.group("new"),
            "column": None,
        })
    for m in _ADD_COLUMN_CLAUSE_RE.finditer(body):
        found.append({
            "class": "add_column",
            "old_column": None,
            "new_column": None,
            "column": m.group("column"),
        })
    for m in _DROP_COLUMN_CLAUSE_RE.finditer(body):
        found.append({
            "class": "drop_column",
            "old_column": None,
            "new_column": None,
            "column": m.group("column"),
        })
    for m in _RENAME_TABLE_CLAUSE_RE.finditer(body):
        found.append({
            "class": "rename_table",
            "old_column": None,
            "new_column": None,
            "column": None,
            "new_table": m.group("new_table"),
        })
    return found


def _dynamic_ddl_blind_spots(stmt: str, source_label: str) -> list[dict[str, str | None]]:
    """Scan one already-split statement for `EXECUTE`-wrapped DDL this
    parser cannot resolve; tag every hit with `source_label` (the migration
    file) so a caller can name exactly where the unknown lives."""
    bodies: list[str] = [m.group(1) for m in _DYNAMIC_EXEC_QUOTED_RE.finditer(stmt)]
    bodies += [m.group("body") for m in _DYNAMIC_EXEC_DOLLAR_RE.finditer(stmt)]
    spots: list[dict[str, str | None]] = []
    for body in bodies:
        for entry in _classify_dynamic_ddl(body):
            entry["file"] = source_label
            spots.append(entry)
    return spots


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

# Word-boundary-aware, NOT whitespace-split. `_is_constraint_line` used to
# tokenize via `line.split(maxsplit=1)` and compare `head[0].upper()` against
# `_CONSTRAINT_KEYWORDS` — correct for `UNIQUE (org_id, slug)` (the keyword
# is its own whitespace-delimited token) but wrong for `UNIQUE(org_id, email)`
# (no space before the paren): `split()` yields `"UNIQUE(org_id,"` as the
# first token, which matches NO keyword, so the line fell through to
# `_COLUMN_HEAD_RE` and was parsed as a column literally named `UNIQUE`.
# Five real tables in the fleet corpus hit this exact shape (2026-09-18).
# `\b` matches on either side of `(` (a non-word char) exactly as it does
# before whitespace, so switching to a regex match built FROM the same
# `_CONSTRAINT_KEYWORDS` tuple closes the gap for every entry at once — not
# just the one spelling that happened to fire — and any future addition to
# the tuple inherits the fix automatically.
_CONSTRAINT_HEAD_RE = re.compile(
    r"^\s*(?:" + "|".join(_CONSTRAINT_KEYWORDS) + r")\b",
    re.IGNORECASE,
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
    if not stripped:
        return True  # empty → treat as skip
    return bool(_CONSTRAINT_HEAD_RE.match(stripped))


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
    blind_spots: list[dict[str, str | None]] | None = None,
) -> dict[str, set[str]]:
    """Parse a blob of SQL into a `{qualified_table: {columns}}` map.

    WARN + skip per-table on any shape that doesn't parse.

    `into` accumulates across calls. Migrations apply SEQUENTIALLY against
    one evolving schema, so anything that mutates an existing table — a
    rename, a `DROP COLUMN` — is only meaningful when the parse can see
    what earlier files built. Passing a shared map is how `parse_files`
    models that; omitting it parses one blob in isolation.

    `blind_spots`, when passed, is APPENDED to (never replaced) with one
    dict per genuinely-unresolvable dynamic-DDL statement encountered (see
    `_dynamic_ddl_blind_spots`) — `EXECUTE format(...)`/`EXECUTE '...'`
    carrying `ALTER TABLE`/`RENAME`/`ADD COLUMN`/`DROP COLUMN` whose target
    table is a runtime placeholder (`%I`). Omitting it (the default) is a
    pure no-op for every existing caller — `MockSupabaseClient` doesn't
    need the list, only `noctus.dev.schema_drift` does.
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

        # Dynamic DDL — `EXECUTE format(...)`/`EXECUTE '...'` whose target
        # table is a runtime placeholder. Checked BEFORE (not instead of)
        # the static ADD/DROP/RENAME scans below: those still run over the
        # same `stmt` text and stay harmless no-ops against a dynamic
        # `%I` target (no static identifier to attribute the mutation to),
        # so nothing here changes what the static passes already do — this
        # only adds the declared-unknown the caller was missing.
        if blind_spots is not None and "EXECUTE" in upper:
            blind_spots.extend(_dynamic_ddl_blind_spots(stmt, source_label))

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

        # DROP TABLE — the table no longer exists from this point in the
        # chain. Without this, a later migration's drop (igig 030 dropping
        # the scaffold `examples` table) left the table in the declared map
        # forever, so schema_drift reported `missing_table` against a DB
        # that was correct, and the mock kept accepting writes to it.
        if "DROP TABLE" in upper:
            for m in _DROP_TABLE_RE.finditer(stmt):
                for name in m.group("names").split(","):
                    qm = _QUALIFIED_NAME_RE.match(name.strip())
                    if qm:
                        schema_map.pop(_qualify(qm.group("schema"), qm.group("table")), None)

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


def parse_files(
    paths: Iterable[Path],
    *,
    blind_spots: list[dict[str, str | None]] | None = None,
) -> dict[str, set[str]]:
    """Parse multiple migration files in order, merging into one schema map.

    `blind_spots`, when passed, is appended to across every file — see
    `parse_sql`'s docstring for the shape.
    """
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
        parse_sql(sql, source_label=str(path), into=merged, blind_spots=blind_spots)
    return merged


# ---------------------------------------------------------------------------
# CHECK constraints (2026-10-10) — the same ordered walk, a second map.
#
# `{qualified_table: {constraint_name: check_body}}`, the CHECKs as they
# stand after every migration applied in order: an `ADD CONSTRAINT` adds,
# `DROP CONSTRAINT` removes (the drop-then-re-add idiom replaces), `DROP
# TABLE` / `DROP COLUMN` take their CHECKs with them (Postgres drops a
# constraint whose column goes), `RENAME COLUMN` rewrites the bodies that
# name it, `RENAME TO` moves the table's CHECKs. `noctusai_lib.testing.
# sql_check` compiles the bodies; `MockSupabaseClient` enforces them.
# Unnamed CHECKs get Postgres' default name shape (`<table>_<col>_check`,
# `<table>_check`) so a message can be read against the real error.
# ---------------------------------------------------------------------------

_CHECK_OPEN_RE = re.compile(r"\bCHECK\s*\(", re.IGNORECASE)
_CONSTRAINT_NAME_BEFORE_RE = re.compile(rf"\bCONSTRAINT\s+(?P<name>{_IDENT})\s*$", re.IGNORECASE)
_ALTER_CHECK_EVENT_RE = re.compile(
    rf"\bADD\s+(?:CONSTRAINT\s+(?P<add_name>{_IDENT})\s+)?CHECK\s*\("
    rf"|\bDROP\s+CONSTRAINT(?:\s+IF\s+EXISTS)?\s+(?P<drop_name>{_IDENT})\b"
    rf"|\bDROP\s+COLUMN(?:\s+IF\s+EXISTS)?\s+(?P<drop_col>{_IDENT})\b"
    rf"|\bRENAME\s+COLUMN\s+(?P<old>{_IDENT})\s+TO\s+(?P<new>{_IDENT})\b"
    rf"|\bRENAME\s+TO\s+(?P<new_table>{_IDENT})\b",
    re.IGNORECASE,
)


def _mentions(body: str, column: str) -> bool:
    return re.search(rf"\b{re.escape(column)}\b", body, re.IGNORECASE) is not None


def _unique_name(existing: dict[str, str], base: str) -> str:
    name, n = base, 0
    while name in existing:
        n += 1
        name = f"{base}{n}"
    return name


def _create_table_checks(table: str, body: str) -> list[tuple[str, str]]:
    """`[(name, check_body)]` for every CHECK in a CREATE TABLE body —
    table-level (`[CONSTRAINT x] CHECK (...)`) and inline on a column."""
    found: list[tuple[str, str]] = []
    taken: dict[str, str] = {}
    for part in _split_top_level_commas(body):
        head = _COLUMN_HEAD_RE.match(part)
        column = head.group("name") if head and not _is_constraint_line(part) else None
        for m in _CHECK_OPEN_RE.finditer(part):
            inner = _extract_table_body(part, m.end() - 1)
            if inner is None:
                continue
            named = _CONSTRAINT_NAME_BEFORE_RE.search(part[:m.start()])
            if named:
                name = named.group("name")
            else:
                name = _unique_name(taken, f"{table}_{column}_check" if column else f"{table}_check")
            taken[name] = inner
            found.append((name, inner.strip()))
    return found


def parse_check_sql(
    sql: str,
    *,
    into: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Parse a blob of SQL into `{qualified_table: {constraint_name: body}}`,
    applying it on top of `into` (migrations apply in order — see the
    section comment above)."""
    sql_clean = _strip_block_comments(_strip_line_comments(sql))
    checks: dict[str, dict[str, str]] = {} if into is None else into
    for stmt in _walk_statements(sql_clean):
        upper = stmt.upper()
        if re.search(r"\bCREATE(\s+OR\s+REPLACE)?\s+FUNCTION\b", upper):
            continue
        if "CREATE TABLE" in upper:
            m = _CREATE_TABLE_HEAD_RE.search(stmt)
            if m:
                body = _extract_table_body(stmt, stmt.find("(", m.end() - 1))
                if body is not None:
                    qualified = _qualify(m.group("schema"), m.group("table"))
                    table_checks = checks.setdefault(qualified, {})
                    for name, check_body in _create_table_checks(m.group("table").lower(), body):
                        table_checks[name] = check_body
        if "DROP TABLE" in upper:
            for m in _DROP_TABLE_RE.finditer(stmt):
                for name in m.group("names").split(","):
                    qm = _QUALIFIED_NAME_RE.match(name.strip())
                    if qm:
                        checks.pop(_qualify(qm.group("schema"), qm.group("table")), None)
        if "ALTER TABLE" not in upper:
            continue
        for schema, table, body in _alter_table_segments(stmt):
            qualified = _qualify(schema, table)
            for ev in _ALTER_CHECK_EVENT_RE.finditer(body):
                table_checks = checks.setdefault(qualified, {})
                if ev.group(0).upper().startswith("ADD"):
                    inner = _extract_table_body(body, ev.end() - 1)
                    if inner is not None:
                        name = ev.group("add_name") or _unique_name(table_checks, f"{table.lower()}_check")
                        table_checks[name] = inner.strip()
                elif ev.group("drop_name"):
                    table_checks.pop(ev.group("drop_name"), None)
                elif ev.group("drop_col"):
                    for name in [n for n, b in table_checks.items() if _mentions(b, ev.group("drop_col"))]:
                        del table_checks[name]
                elif ev.group("old"):
                    old, new = ev.group("old"), ev.group("new")
                    for name, b in list(table_checks.items()):
                        table_checks[name] = re.sub(rf"\b{re.escape(old)}\b", new, b, flags=re.IGNORECASE)
                elif ev.group("new_table"):
                    moved = checks.pop(qualified, {})
                    qualified = _qualify(schema, ev.group("new_table"))
                    checks.setdefault(qualified, {}).update(moved)
    return checks


def parse_check_files(paths: Iterable[Path]) -> dict[str, dict[str, str]]:
    """`parse_check_sql` over migration files in order, one accumulating map."""
    merged: dict[str, dict[str, str]] = {}
    for path in paths:
        try:
            sql = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("mock-checks: could not read %s: %s — skipping", path, exc)
            continue
        parse_check_sql(sql, into=merged)
    return {table: named for table, named in merged.items() if named}

# ---------------------------------------------------------------------------
# Column DEFAULTs (2026-10-10) — which columns an INSERT may omit and still
# get a value. A cross-column CHECK judges an omitted column as NULL, exactly
# like Postgres does, UNLESS the column has a DEFAULT (or is serial /
# generated): then the mock can't know the value and doesn't guess.
# `{qualified_table: {columns_with_a_default}}`.
# ---------------------------------------------------------------------------

_HAS_DEFAULT_RE = re.compile(r"\b(?:DEFAULT|GENERATED|SMALLSERIAL|BIGSERIAL|SERIAL)\b", re.IGNORECASE)
_ALTER_DEFAULT_EVENT_RE = re.compile(
    rf"\bADD\s+COLUMN(?:\s+IF\s+NOT\s+EXISTS)?\s+(?P<add>{_IDENT})\b"
    rf"|\bALTER\s+(?:COLUMN\s+)?(?P<alter>{_IDENT})\s+(?P<verb>SET|DROP)\s+DEFAULT\b"
    rf"|\bDROP\s+COLUMN(?:\s+IF\s+EXISTS)?\s+(?P<drop>{_IDENT})\b"
    rf"|\bRENAME\s+COLUMN\s+(?P<old>{_IDENT})\s+TO\s+(?P<new>{_IDENT})\b"
    rf"|\bRENAME\s+TO\s+(?P<new_table>{_IDENT})\b",
    re.IGNORECASE,
)


def parse_default_sql(
    sql: str,
    *,
    into: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    """`{qualified_table: {columns with a DEFAULT}}` after `sql` applies on
    top of `into` (same ordered-walk semantics as `parse_check_sql`)."""
    sql_clean = _strip_block_comments(_strip_line_comments(sql))
    defaults: dict[str, set[str]] = {} if into is None else into
    for stmt in _walk_statements(sql_clean):
        upper = stmt.upper()
        if re.search(r"\bCREATE(\s+OR\s+REPLACE)?\s+FUNCTION\b", upper):
            continue
        if "CREATE TABLE" in upper:
            m = _CREATE_TABLE_HEAD_RE.search(stmt)
            if m:
                body = _extract_table_body(stmt, stmt.find("(", m.end() - 1))
                if body is not None:
                    cols = defaults.setdefault(_qualify(m.group("schema"), m.group("table")), set())
                    for part in _split_top_level_commas(body):
                        head = _COLUMN_HEAD_RE.match(part)
                        if head and not _is_constraint_line(part) and _HAS_DEFAULT_RE.search(part):
                            cols.add(head.group("name"))
        if "DROP TABLE" in upper:
            for m in _DROP_TABLE_RE.finditer(stmt):
                for name in m.group("names").split(","):
                    qm = _QUALIFIED_NAME_RE.match(name.strip())
                    if qm:
                        defaults.pop(_qualify(qm.group("schema"), qm.group("table")), None)
        if "ALTER TABLE" not in upper:
            continue
        for schema, table, body in _alter_table_segments(stmt):
            qualified = _qualify(schema, table)
            clauses = _split_top_level_commas(body)
            for clause in clauses:
                for ev in _ALTER_DEFAULT_EVENT_RE.finditer(clause):
                    cols = defaults.setdefault(qualified, set())
                    if ev.group("add"):
                        if _HAS_DEFAULT_RE.search(clause[ev.end():]):
                            cols.add(ev.group("add"))
                    elif ev.group("alter"):
                        (cols.add if ev.group("verb").upper() == "SET" else cols.discard)(ev.group("alter"))
                    elif ev.group("drop"):
                        cols.discard(ev.group("drop"))
                    elif ev.group("old"):
                        if ev.group("old") in cols:
                            cols.discard(ev.group("old"))
                            cols.add(ev.group("new"))
                    elif ev.group("new_table"):
                        moved = defaults.pop(qualified, set())
                        qualified = _qualify(schema, ev.group("new_table"))
                        defaults.setdefault(qualified, set()).update(moved)
                    break  # one event per clause
    return defaults


def parse_default_files(paths: Iterable[Path]) -> dict[str, set[str]]:
    """`parse_default_sql` over migration files in order."""
    merged: dict[str, set[str]] = {}
    for path in paths:
        try:
            sql = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("mock-defaults: could not read %s: %s — skipping", path, exc)
            continue
        parse_default_sql(sql, into=merged)
    return merged


__all__ = [
    "parse_sql", "parse_files", "parse_check_sql", "parse_check_files",
    "parse_default_sql", "parse_default_files",
]
