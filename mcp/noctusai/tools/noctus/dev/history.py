"""History-record tool — append a structured entry to the project ledger.

Implements the ``noctus.dev.history_record`` MCP tool per
``projects/project-history-ledger/PROJECT.md § 6 Phase 1``.

Public surface:

    history_record(
        project_path,
        status_at_close,
        summary_md,
        review_md,
        outcome_signals=None,
        scope=None,
        dates_created=None,
        dates_closed=None,
        repo_root=None,
        ledger_path=None,
    ) -> dict

Behavior:

- Reads ``PROJECT.md`` + ``improvements.md`` + ``proposals/*.md`` from
  ``project_path``; static-tokenizes each via the shared cascade
  (``tools._tokens.count_tokens_in_text`` — tiktoken cl100k_base when
  available, chars/4 fallback otherwise).
- Walks ``git log`` for the project's commits (best-effort: matches the
  project's slug in commit messages) → sums ``--shortstat`` lines
  inserted across changed files. ``code_delta_tokens`` is reported as
  ``approximate_lines * 8`` (rough words-to-tokens fit) when commit
  history is available; ``0`` and a warning if not.
- Writes ONE NDJSON line to ``project-history/ledger.ndjson`` (per Q2=c
  in PROJECT.md §7 — append-only).

NDJSON discipline:

- **Append-only.** Re-stamping the same project appends a new line —
  the ledger is the history of stampings, not a unique-key keyed store.
  Each entry carries ``dates.closed`` (when the stamping happened) and
  ``status_at_close``; readers de-dupe at render time if they want a
  single row per slug.
- **One JSON object per line.** No pretty-printing. Every line is
  independently parseable.
- **UTC date in `dates.closed`.** Caller may override with an explicit
  ISO date; otherwise today (local TZ matching ``archive.py``) is used.

MCP tool registration at module bottom via ``register(server)``.

References:
- ``projects/project-history-ledger/PROJECT.md``
- ``KB § PATTERNS/mcp-tool-conventions.md``
- ``feedback_mcp_path_constants_from_settings.md`` (REPO_ROOT import)
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ConfigDict

# REPO_ROOT comes from settings per the centralization rule
# (`feedback_mcp_path_constants_from_settings.md`).
from settings import REPO_ROOT
from workspace import resolve_caller_root

# Shared tokenizer cascade — N=2 absorption with cost_evaluation.
from tools._tokens import (
    count_tokens_in_text,
    get_default_encoder,
)

logger = logging.getLogger(__name__)

_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

_VALID_STATUSES = {"shipped", "abandoned", "split", "deferred", "historical"}
_VALID_SCOPES = {"cross-product", "single-product", "core-control", "platform-infra"}

# ``code_delta_tokens`` heuristic: ``--shortstat`` reports insertions in
# lines; convert to a rough token estimate by multiplying. 8 tokens/line
# is the rule-of-thumb for code (denser than English markdown, hence
# higher than the chars/4 estimate). This is intentionally approximate;
# precise per-commit tokenization would require checking out every
# touched file at every revision (expensive). Document the approximation
# alongside the record so future readers don't over-trust the number.
_CODE_TOKEN_PER_LINE_HEURISTIC = 8

_SHORTSTAT_RE = re.compile(
    r"(\d+)\s+files?\s+changed"
    r"(?:,\s+(\d+)\s+insertions?\(\+\))?"
    r"(?:,\s+(\d+)\s+deletions?\(-\))?"
)


def _today_str() -> str:
    """Return today's date in local TZ as YYYY-MM-DD."""
    return datetime.now(tz=_LOCAL_TZ).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Pydantic schema — mirrors archive.py shape for sibling consistency.
# ---------------------------------------------------------------------------


class HistoryDates(BaseModel):
    """Created / closed dates. ISO YYYY-MM-DD."""

    model_config = ConfigDict(extra="forbid")

    created: str | None = None
    closed: str


class HistoryPhase(BaseModel):
    """One phase entry inside a project's record."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    tokens: int | None = None


class HistoryTokenCount(BaseModel):
    """Token-count breakdown. ``total`` is the sum the renderer surfaces."""

    model_config = ConfigDict(extra="forbid")

    project_doc_tokens: int = 0
    improvements_tokens: int = 0
    proposals_tokens: int = 0
    code_delta_tokens: int = 0
    total: int = 0
    tokenizer_used: str = ""


class HistoryRecord(BaseModel):
    """One ledger row — written as a single NDJSON line.

    Field set matches PROJECT.md §7 Q4 standard fields:
    ``slug``, ``scope``, ``status_at_close``, ``dates {created, closed}``,
    ``phases [...]``, ``short_summary``, ``short_review``,
    ``token_count {...}``, ``outcome_signals``.
    """

    model_config = ConfigDict(extra="forbid")

    slug: str
    scope: str
    status_at_close: str
    dates: HistoryDates
    phases: list[HistoryPhase] = Field(default_factory=list)
    short_summary: str
    short_review: str
    token_count: HistoryTokenCount
    outcome_signals: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _CountedFile:
    """Per-file tokenizer result inside the helper."""

    path: Path
    tokens: int
    label: str


def _safe_read_text(path: Path) -> str | None:
    """Read ``path`` as text, returning ``None`` on missing / unreadable.

    Errors are logged (no silent ``except: pass`` — per the no-silent-
    errors rule). Missing files are common (improvements.md is optional;
    proposals/ may be empty) so we return ``None`` rather than raising;
    the caller treats ``None`` as "0 tokens for this slot".
    """
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("history_record: failed to read %s: %s", path, e)
        return None


def _count_file(path: Path, encoder: Any | None) -> _CountedFile:
    """Tokenize ``path`` content; ``tokens=0`` on missing/unreadable."""
    text = _safe_read_text(path)
    if text is None:
        return _CountedFile(path=path, tokens=0, label="(missing)")
    tokens, label = count_tokens_in_text(text, encoder=encoder)
    return _CountedFile(path=path, tokens=tokens, label=label)


def _git_short_stat_for_slug(slug: str, repo_root: Path) -> tuple[int, int]:
    """Return ``(insertions, deletions)`` summed across the slug's commits.

    Best-effort: matches commits whose message contains the slug. Misses
    commits that mentioned the project differently — that's by design
    (the ledger documents this approximation; precision isn't the goal).

    Returns ``(0, 0)`` if ``git log`` fails, no commits match, or the
    project hasn't started shipping yet.
    """
    try:
        # `git log --all` so the search covers branches, not just HEAD.
        # `--grep` filters by commit message; we anchor on the slug.
        # `--shortstat` adds the insertions/deletions line per commit.
        result = subprocess.run(
            [
                "git",
                "log",
                "--all",
                "--grep",
                slug,
                "--shortstat",
                "--no-merges",
                "--format=%H",
            ],
            check=True,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(
            "history_record: git log failed for slug=%r in %s: %s",
            slug, repo_root, e,
        )
        return (0, 0)

    insertions = 0
    deletions = 0
    for line in result.stdout.splitlines():
        m = _SHORTSTAT_RE.search(line)
        if m:
            ins = int(m.group(2) or 0)
            dele = int(m.group(3) or 0)
            insertions += ins
            deletions += dele
    return (insertions, deletions)


def _approximate_code_tokens(insertions: int, deletions: int) -> int:
    """Convert git --shortstat counts to a rough token estimate.

    ``(insertions + deletions) * _CODE_TOKEN_PER_LINE_HEURISTIC``.
    Documented as approximate alongside the record (see module docstring).
    """
    return (insertions + deletions) * _CODE_TOKEN_PER_LINE_HEURISTIC


def _resolve_project_path(project_path: str, repo_root: Path) -> Path:
    """Resolve ``project_path`` (relative or absolute) to a folder.

    Accepts:
      - a path to a folder containing PROJECT.md (typical)
      - a path to PROJECT.md itself (we use its parent)
    """
    p = Path(project_path)
    if not p.is_absolute():
        p = (repo_root / project_path).resolve()
    else:
        p = p.resolve()
    if not p.exists():
        raise ValueError(f"project path does not exist: {p}")
    if p.name == "PROJECT.md":
        p = p.parent
    if not p.is_dir():
        raise ValueError(f"project path is not a directory: {p}")
    if not (p / "PROJECT.md").exists():
        raise ValueError(f"no PROJECT.md found at: {p / 'PROJECT.md'}")
    return p


def _derive_slug(project_dir: Path) -> str:
    """Slug = folder name. Matches archive.py convention."""
    return project_dir.name


def _gather_phases(short_review_md: str) -> list[HistoryPhase]:
    """Best-effort phase extraction from a short review.

    Looks for lines that start with ``Phase <N>`` or ``### Phase <N>``.
    Returns an empty list if none found — caller can pass a richer
    structure via an explicit ``phases=`` once the schema stabilizes.
    """
    phases: list[HistoryPhase] = []
    # Match `Phase N`, optionally preceded by markdown bullet (`- `,
    # `* `), heading marker (`###`), or whitespace.
    phase_re = re.compile(
        r"^\s*(?:[-*]\s+|#+\s*)?Phase\s+(\d+)[\s—:-]*(.*?)(?:\s*✅|\s*$)",
        re.IGNORECASE,
    )
    for line in short_review_md.splitlines():
        m = phase_re.match(line)
        if m:
            phases.append(
                HistoryPhase(
                    name=f"Phase {m.group(1)} — {m.group(2).strip()}" if m.group(2).strip() else f"Phase {m.group(1)}",
                    status="shipped",
                )
            )
    return phases


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def history_record(
    project_path: str,
    status_at_close: str,
    summary_md: str,
    review_md: str,
    outcome_signals: list[str] | None = None,
    scope: str | None = None,
    dates_created: str | None = None,
    dates_closed: str | None = None,
    phases: list[dict] | None = None,
    repo_root: Path | None = None,
    ledger_path: Path | None = None,
    worktree_path: str | Path | None = None,
    slug_override: str | None = None,
) -> dict:
    """Append a single NDJSON line to ``project-history/ledger.ndjson``.

    Args:
        project_path: project folder (or path to PROJECT.md). Relative
            paths resolve against ``repo_root``.
        status_at_close: one of ``shipped``, ``abandoned``, ``split``,
            ``deferred``, ``historical`` (backfill marker).
        summary_md: 1-3 sentence short summary (becomes
            ``short_summary``).
        review_md: 5-10 bullet short review (becomes ``short_review``).
            Phases are best-effort extracted from this text if ``phases``
            is not provided.
        outcome_signals: e.g. ``["pytest 1816/1816 green"]``.
        scope: one of ``cross-product``, ``single-product``,
            ``core-control``, ``platform-infra``. Inferred from the
            project path if absent (best-effort; defaults to
            ``cross-product``).
        dates_created: ISO YYYY-MM-DD; defaults to ``None`` (caller may
            supply from PROJECT.md ``Created`` line).
        dates_closed: ISO YYYY-MM-DD; defaults to today (local TZ).
        phases: explicit phase list; overrides the regex extraction.
        repo_root: override (tests).
        ledger_path: override (tests) — defaults to
            ``<repo_root>/project-history/ledger.ndjson``.
        worktree_path: **Caller-aware path resolution.** When set, the
            ledger lands at ``<worktree>/project-history/ledger.ndjson``
            instead of the MCP server's startup workspace. Engineers in a
            git worktree pass their worktree root; architects on main noc
            omit. Mutually-priority: explicit ``repo_root`` wins, else
            ``worktree_path``, else module-level ``REPO_ROOT``. See
            ``resolve_caller_root``.
        slug_override: **Backfill / migration use only.** When set, the
            ledger row uses this slug instead of deriving from the folder
            name. Use case: archived projects live at
            ``archive/projects/<date>/NN-<slug>/`` — passing the bare
            ``<slug>`` strips the ``NN-`` prefix so backfilled rows match
            the canonical convention used by live close-stamping (which
            sees ``projects/<slug>/`` BEFORE the git mv). Default ``None``
            preserves the original folder-name derivation. Do not use for
            normal close-stamping — the archive caller does the right
            thing without override.

    Returns:
        ``{"ledger_path": str, "line_count": int, "record": <dict>}``
        where ``record`` is the JSON-serialized form of the appended
        ``HistoryRecord`` (same shape as the NDJSON line).

    Raises:
        ValueError: invalid status_at_close, missing PROJECT.md, etc.
    """
    if status_at_close not in _VALID_STATUSES:
        raise ValueError(
            f"invalid status_at_close: {status_at_close!r}, "
            f"must be one of {sorted(_VALID_STATUSES)}"
        )
    if scope is not None and scope not in _VALID_SCOPES:
        raise ValueError(
            f"invalid scope: {scope!r}, must be one of {sorted(_VALID_SCOPES)}"
        )

    # Resolution order: explicit `repo_root` test seam wins; otherwise
    # `worktree_path` (caller-aware); otherwise module-level REPO_ROOT.
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT
    project_dir = _resolve_project_path(project_path, root)
    slug = slug_override.strip() if slug_override else _derive_slug(project_dir)
    if not slug:
        raise ValueError("slug_override resolved to empty string")

    # Scope inference — best effort: products/*/projects/* → single-product;
    # core/projects/* → core-control; projects/* at root → cross-product.
    resolved_scope = scope
    if resolved_scope is None:
        try:
            rel = project_dir.relative_to(root)
            parts = rel.parts
            if len(parts) >= 3 and parts[0] == "products" and parts[2] == "projects":
                resolved_scope = "single-product"
            elif len(parts) >= 2 and parts[0] == "core" and parts[1] == "projects":
                resolved_scope = "core-control"
            else:
                resolved_scope = "cross-product"
        except ValueError:
            resolved_scope = "cross-product"

    # Load + tokenize the three artifacts. Single shared encoder for
    # batch reuse (avoid re-loading the encoding tables per file).
    encoder = get_default_encoder()
    project_md = _count_file(project_dir / "PROJECT.md", encoder)
    improvements_md = _count_file(project_dir / "improvements.md", encoder)

    proposals_total = 0
    proposals_label = ""
    proposals_dir = project_dir / "proposals"
    if proposals_dir.is_dir():
        for prop_path in sorted(proposals_dir.glob("*.md")):
            cf = _count_file(prop_path, encoder)
            proposals_total += cf.tokens
            if cf.label and cf.label != "(missing)":
                proposals_label = cf.label

    # Code-delta tokens — best-effort from git log.
    insertions, deletions = _git_short_stat_for_slug(slug, root)
    code_delta_tokens = _approximate_code_tokens(insertions, deletions)
    if insertions == 0 and deletions == 0:
        logger.info(
            "history_record: no git commits matched slug=%r — "
            "code_delta_tokens=0. Re-run after the project's commits "
            "land (or supply a different slug via folder rename).",
            slug,
        )

    # Tokenizer label — use the most-recent non-missing label found;
    # they should all match in practice (same encoder).
    tokenizer_used = (
        project_md.label
        if project_md.label != "(missing)"
        else improvements_md.label
        if improvements_md.label != "(missing)"
        else proposals_label
        or "(no input)"
    )

    total_tokens = (
        project_md.tokens
        + improvements_md.tokens
        + proposals_total
        + code_delta_tokens
    )

    # Phase extraction.
    if phases is not None:
        phase_objs = [HistoryPhase(**p) for p in phases]
    else:
        phase_objs = _gather_phases(review_md)

    record = HistoryRecord(
        slug=slug,
        scope=resolved_scope,
        status_at_close=status_at_close,
        dates=HistoryDates(
            created=dates_created,
            closed=dates_closed or _today_str(),
        ),
        phases=phase_objs,
        short_summary=summary_md.strip(),
        short_review=review_md.strip(),
        token_count=HistoryTokenCount(
            project_doc_tokens=project_md.tokens,
            improvements_tokens=improvements_md.tokens,
            proposals_tokens=proposals_total,
            code_delta_tokens=code_delta_tokens,
            total=total_tokens,
            tokenizer_used=tokenizer_used,
        ),
        outcome_signals=outcome_signals or [],
    )

    # Append to NDJSON ledger. One JSON object per line. UTF-8.
    target = ledger_path or (root / "project-history" / "ledger.ndjson")
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.model_dump(), ensure_ascii=False, separators=(",", ":"))
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    # Count lines for caller convenience (idempotency / append verification).
    with target.open("r", encoding="utf-8") as fh:
        line_count = sum(1 for _ in fh)

    logger.info(
        "history_record: appended slug=%s tokens=%d to %s (now %d lines)",
        slug, total_tokens, target, line_count,
    )

    return {
        "ledger_path": str(target.relative_to(root)) if root in target.parents else str(target),
        "line_count": line_count,
        "record": record.model_dump(),
    }


# ---------------------------------------------------------------------------
# Ledger → PROJECT-HISTORY.md renderer.
#
# Absorbed from the former ``scripts/render-project-history.py`` (behaviour-
# preserving — byte-identical output). Reads ``project-history/ledger.ndjson``
# and emits the human-readable view at ``project-history/PROJECT-HISTORY.md``.
# The renderer dedupes-by-slug-keep-latest by ``dates.closed`` and sorts
# DESC by ``dates.closed`` (slug ASC tiebreak) so the rendered table is
# idempotent. Invalid NDJSON raises ``ValueError`` with the line number —
# no silent swallow per the no-silent-errors rule.
# ---------------------------------------------------------------------------

# The placeholder banner sits above the table in PROJECT-HISTORY.md. Its
# wording warns hand-editors away — the table below is generated.
_HISTORY_HEADER = (
    "# Project History\n"
    "\n"
    "_Auto-generated by scripts/render-project-history.py — do not edit by hand._\n"
    "_Source of truth: `project-history/ledger.ndjson` (see "
    "`projects/project-history-ledger/PROJECT.md`)._\n"
    "\n"
)

# Empty-ledger marker — the human-readable view still needs to render
# stably when the ledger has zero rows (fresh repo / pre-Phase-2 state).
_HISTORY_EMPTY_FOOTER = "_No project records yet — the ledger is empty._\n"

# Table column headers + alignment. Order matches the §6 Phase 3 spec.
_HISTORY_COLUMNS = [
    ("Date", ":---"),
    ("Slug", ":---"),
    ("Scope", ":---"),
    ("Status", ":---"),
    ("Total Tokens", "---:"),
    ("Short Summary", ":---"),
]


def _history_parse_ledger(ledger_path: Path) -> list[dict[str, Any]]:
    """Parse the NDJSON ledger, raising on any malformed line.

    Returns the list of records in file order (caller dedupes/sorts).

    Raises:
        ValueError: malformed JSON, with the line number quoted.
        FileNotFoundError: ledger does not exist (caller may treat as empty).
    """
    if not ledger_path.exists():
        raise FileNotFoundError(f"ledger not found: {ledger_path}")
    records: list[dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                # Blank lines are tolerated (trailing newline at EOF; no
                # silent error — the line carries no data, so there's
                # nothing to swallow).
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"invalid NDJSON at {ledger_path}:{lineno}: {e.msg} "
                    f"(line content: {stripped[:120]!r})"
                ) from e
            if not isinstance(rec, dict):
                raise ValueError(
                    f"NDJSON record at {ledger_path}:{lineno} is not a JSON "
                    f"object: {type(rec).__name__}"
                )
            records.append(rec)
    return records


def _history_dedupe_latest_by_slug(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse multi-stamping per slug → keep latest by ``dates.closed``.

    Ties on ``dates.closed`` resolve to file order (later line wins) —
    the ledger is append-only so a later line is the more recent event.

    Records lacking a ``dates.closed`` are kept under the empty-string key
    so they still surface in the rendered table (sorted last). They never
    silently disappear.
    """
    by_slug: dict[str, dict[str, Any]] = {}
    for rec in records:
        slug = rec.get("slug", "")
        if not slug:
            # No slug → use a synthetic key per-record so the row still
            # appears. Empty-slug rows are an upstream bug; we surface
            # them rather than swallow.
            slug = f"__no_slug__{id(rec)}"
        closed = (rec.get("dates") or {}).get("closed", "")
        prior = by_slug.get(slug)
        if prior is None:
            by_slug[slug] = rec
            continue
        prior_closed = (prior.get("dates") or {}).get("closed", "")
        # Lexicographic comparison on ISO YYYY-MM-DD is correct DESC sort
        # ordering; on tie, latest line (this `rec`) wins per append-only
        # convention (later = newer).
        if closed >= prior_closed:
            by_slug[slug] = rec
    return list(by_slug.values())


def _history_row_sort_key(rec: dict[str, Any]) -> tuple:
    """Sort key: closed-date DESC, then slug ASC (for stable idempotency)."""
    closed = (rec.get("dates") or {}).get("closed") or ""
    return closed


def _history_sort_rows(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort DESC by ``dates.closed``, ASC by ``slug`` on tie. Stable."""
    # First pass: ASC slug. Second pass: DESC closed. Python's `sorted`
    # is stable so the slug order survives the second sort within each
    # closed-date group.
    by_slug = sorted(records, key=lambda r: r.get("slug", ""))
    return sorted(by_slug, key=_history_row_sort_key, reverse=True)


def _history_escape_cell(text: str) -> str:
    """Make a string safe for a Markdown table cell.

    Replaces newlines (would break the row) and escapes pipe characters
    (would break the column). Keep the original content; just neutralize
    the table-breaking chars.
    """
    if not text:
        return ""
    # Newlines → spaces; tabs → spaces; pipe → escaped pipe.
    cleaned = text.replace("\r\n", " ").replace("\n", " ").replace("\t", " ")
    cleaned = cleaned.replace("|", "\\|")
    # Collapse runs of spaces so the column stays tight.
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip()


def _history_format_tokens(rec: dict[str, Any]) -> str:
    """Return the total-tokens cell as a stable string."""
    tc = rec.get("token_count") or {}
    total = tc.get("total", 0)
    if not isinstance(total, (int, float)):
        return str(total)
    # Plain int formatting — no thousands-separators (locale-stable).
    return str(int(total))


def _history_render_table(records: list[dict[str, Any]]) -> str:
    """Render the list of records into the Markdown table body.

    Returns the table text (header row + separator + data rows), no
    leading/trailing blank lines beyond the trailing newline.
    """
    if not records:
        return ""
    header = "| " + " | ".join(name for name, _ in _HISTORY_COLUMNS) + " |"
    sep = "| " + " | ".join(align for _, align in _HISTORY_COLUMNS) + " |"
    lines = [header, sep]
    for rec in records:
        closed = _history_escape_cell((rec.get("dates") or {}).get("closed") or "")
        slug = _history_escape_cell(rec.get("slug", ""))
        scope = _history_escape_cell(rec.get("scope", ""))
        status = _history_escape_cell(rec.get("status_at_close", ""))
        tokens = _history_format_tokens(rec)
        summary = _history_escape_cell(rec.get("short_summary", ""))
        lines.append(
            f"| {closed} | {slug} | {scope} | {status} | {tokens} | {summary} |"
        )
    return "\n".join(lines) + "\n"


def _history_render_body(ledger_path: Path) -> str:
    """Compose the full PROJECT-HISTORY.md body from the ledger.

    Returns the string to write. Trailing newline included.
    """
    try:
        records = _history_parse_ledger(ledger_path)
    except FileNotFoundError:
        # An absent ledger is the "empty" case (fresh repo / scaffold).
        # Phase 0 creates an empty marker file; absent file shouldn't
        # crash the renderer or block commits.
        records = []
    deduped = _history_dedupe_latest_by_slug(records)
    rows = _history_sort_rows(deduped)
    if not rows:
        return _HISTORY_HEADER + _HISTORY_EMPTY_FOOTER
    return _HISTORY_HEADER + _history_render_table(rows)


def render_project_history(
    repo_root: Path | None = None,
    *,
    ledger_path: Path | None = None,
    output_path: Path | None = None,
    check: bool = False,
    worktree_path: str | Path | None = None,
) -> dict:
    """Render ``project-history/ledger.ndjson`` → ``PROJECT-HISTORY.md``.

    Behaviour-preserving absorption of ``scripts/render-project-history.py``
    (byte-identical output). The renderer dedupes-by-slug-keep-latest by
    ``dates.closed``, sorts DESC by ``dates.closed`` (slug ASC tiebreak),
    and is idempotent (re-running on an unchanged ledger produces
    byte-identical output).

    Args:
        repo_root: override (tests); else ``worktree_path`` else
            ``REPO_ROOT``.
        ledger_path: override (tests) — defaults to
            ``<repo_root>/project-history/ledger.ndjson``.
        output_path: override (tests) — defaults to
            ``<repo_root>/project-history/PROJECT-HISTORY.md``.
        check: if True, do NOT write; report whether the rendered output
            differs from disk (``drift`` key in the result).
        worktree_path: **Caller-aware path resolution.** When set AND
            ``repo_root`` is None, paths resolve against the caller's
            worktree root instead of the MCP server's startup workspace.

    Returns:
        ``{"ledger_path": str, "output_path": str, "changed": bool,
        "drift": bool, "rows": int, "check": bool}`` — ``changed`` is the
        write-side flag (False in check-mode or on no-op); ``drift`` is
        True when the on-disk output differs from the freshly-rendered
        content (the signal the pre-commit hook keys on).

    Raises:
        ValueError: malformed NDJSON line (line number quoted).
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT
    ledger = ledger_path or (root / "project-history" / "ledger.ndjson")
    output = output_path or (root / "project-history" / "PROJECT-HISTORY.md")

    rendered = _history_render_body(ledger)
    existing = output.read_text(encoding="utf-8") if output.exists() else ""
    drift = rendered != existing

    changed = False
    if not check and drift:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        changed = True

    deduped = _history_dedupe_latest_by_slug(
        _history_parse_ledger(ledger) if ledger.exists() else []
    )
    return {
        "ledger_path": (
            str(ledger.relative_to(root)) if root in ledger.parents else str(ledger)
        ),
        "output_path": (
            str(output.relative_to(root)) if root in output.parents else str(output)
        ),
        "changed": changed,
        "drift": drift,
        "rows": len(deduped),
        "check": check,
    }


# ---------------------------------------------------------------------------
# Historical-archive backfill.
#
# Absorbed from the former ``scripts/backfill-project-history.py`` (behaviour-
# preserving). Walks ``archive/projects/<date>/NN-<slug>/PROJECT.md`` and
# appends one ledger row per archived project with
# ``status_at_close="historical"``. Idempotent — re-running does NOT
# duplicate ledger entries (idempotency key = ``(slug, dates.closed)`` over
# historical rows only). Fail-loud — a missing PROJECT.md / malformed
# archive folder name / malformed existing-ledger line raises
# ``BackfillError`` with the path (no silent-skip).
# ---------------------------------------------------------------------------


class BackfillError(RuntimeError):
    """Raised when an archive folder violates expected backfill structure.

    Per the no-silent-errors rule: methodology slips at the data layer
    surface here instead of silently truncating the historical ledger.
    """


# Pattern for archive folder names: ``NN-<slug>`` (e.g. ``01-archive-system``).
_BACKFILL_NN_PREFIX_RE = re.compile(r"^(\d{2})-(.+)$")

# Pattern for ``- **Created:** YYYY-MM-DD`` line in PROJECT.md.
_BACKFILL_CREATED_RE = re.compile(
    r"^\s*[-*]\s+\*\*Created:\*\*\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)


def _backfill_strip_nn_prefix(folder_name: str) -> str:
    """Return the bare slug from a ``NN-<slug>`` archive folder name.

    Raises ``BackfillError`` if the folder doesn't match the expected
    shape (callers should never reach this from a well-formed archive).
    """
    m = _BACKFILL_NN_PREFIX_RE.match(folder_name)
    if not m:
        raise BackfillError(
            f"archive folder name doesn't match 'NN-<slug>' shape: {folder_name!r}"
        )
    return m.group(2)


def _backfill_extract_created_date(project_md_text: str) -> str | None:
    """Extract the ISO ``Created:`` date from a PROJECT.md body.

    Returns ``None`` when no Created line is present (older historical
    projects predate the convention; logged but not error).
    """
    m = _BACKFILL_CREATED_RE.search(project_md_text)
    return m.group(1) if m else None


def _backfill_derive_short_summary(project_md_text: str) -> str:
    """Best-effort short summary from PROJECT.md.

    Two-tier extraction:

    1. **Primary:** first prose paragraph under ``## 1. Context & Purpose``
       (skipping its own heading, sub-headings, blockquotes, and
       metadata bullet lines).
    2. **Fallback:** first non-heading/non-blockquote/non-bullet line
       (matches ``archive._derive_default_summary`` shape).

    Metadata bullet lines (``- **Created:** ...``, etc.) are explicitly
    skipped — they are not project descriptions.
    """
    lines = project_md_text.splitlines()

    # Tier 1: locate ``## 1. Context & Purpose`` heading; collect first
    # prose paragraph after it.
    context_heading = re.compile(r"^##\s+1\.\s+Context.*$", re.IGNORECASE)
    next_section = re.compile(r"^##\s+\d+\.\s+")
    in_section = False
    for raw in lines:
        if not in_section:
            if context_heading.match(raw.strip()):
                in_section = True
            continue
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            # Heading inside §1 — bail only on a next major section.
            if next_section.match(line):
                break
            continue
        if line.startswith(">"):
            continue
        if line.startswith("- ") or line.startswith("* "):
            continue  # metadata bullets, never the summary
        return line

    # Tier 2 fallback: archive.py-style derivation with metadata-skip.
    metadata_bullet = re.compile(
        r"^[-*]\s+\*\*(?:Created|Last updated|Status|Owner|Related|Project slug|Branch)"
    )
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith(">"):
            continue
        if metadata_bullet.match(line):
            continue
        if line.startswith("- ") or line.startswith("* "):
            stripped = re.sub(r"^[-*]\s+", "", line)
            if stripped:
                return stripped
            continue
        return line
    return "(no summary available)"


def _backfill_scope_from_archive_path(
    archive_project_dir: Path, repo: Path
) -> str:
    """Best-effort scope from the archive path.

    Historical archives all live under ``archive/projects/<date>/NN-<slug>``
    — we can't reliably tell from archive-only data whether a project
    originated cross-product or single-product. Default to
    ``cross-product`` (accurate for the majority shape).
    """
    return "cross-product"


def _backfill_load_existing_keys(ledger_path: Path) -> set[tuple[str, str]]:
    """Return ``{(slug, closed_date)}`` for existing historical rows.

    Live close-stamps (status_at_close != 'historical') are excluded
    from the idempotency key — historical backfill and live close-stamps
    are orthogonal events that legitimately co-exist for the same slug.
    """
    keys: set[tuple[str, str]] = set()
    if not ledger_path.exists():
        return keys
    with ledger_path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise BackfillError(
                    f"existing ledger {ledger_path}:{lineno} is malformed: "
                    f"{e.msg} — fix or remove this row before backfilling"
                ) from e
            if rec.get("status_at_close") != "historical":
                continue
            slug = rec.get("slug", "")
            closed = (rec.get("dates") or {}).get("closed", "")
            keys.add((slug, closed))
    return keys


def _backfill_discover_archives(archive_root: Path) -> list[Path]:
    """Return sorted list of ``archive/projects/<date>/NN-<slug>/`` paths.

    Each returned path is a project directory containing PROJECT.md.
    Folders without PROJECT.md raise ``BackfillError`` (the archive
    system guarantees PROJECT.md presence; absence is a data-integrity
    issue, not a backfill skip).
    """
    projects_root = archive_root / "projects"
    if not projects_root.is_dir():
        return []
    found: list[Path] = []
    for date_dir in sorted(projects_root.iterdir()):
        if not date_dir.is_dir():
            continue
        # Skip files (e.g. README.md) directly under projects/.
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_dir.name):
            logger.debug(
                "skipping non-date entry under archive/projects/: %s",
                date_dir.name,
            )
            continue
        for proj_dir in sorted(date_dir.iterdir()):
            if not proj_dir.is_dir():
                continue
            project_md = proj_dir / "PROJECT.md"
            if not project_md.exists():
                raise BackfillError(
                    f"archive folder missing PROJECT.md: {proj_dir} — "
                    f"data-integrity issue, not a backfill skip"
                )
            found.append(proj_dir)
    return found


def _backfill_stamp_one(
    archive_project_dir: Path,
    repo: Path,
    existing_keys: set[tuple[str, str]],
    *,
    dry_run: bool = False,
) -> tuple[str, dict | None]:
    """Stamp one archive's ledger row.

    Returns a ``(outcome, result)`` tuple where outcome is one of
    ``"stamped"`` / ``"skipped_existing"`` / ``"would_stamp"``.
    """
    date_dir_name = archive_project_dir.parent.name  # e.g. ``2026-05-10``
    folder_name = archive_project_dir.name
    canonical_slug = _backfill_strip_nn_prefix(folder_name)

    # Idempotency check: this slug+close-date already historically stamped?
    key = (canonical_slug, date_dir_name)
    if key in existing_keys:
        logger.info(
            "skip (already-stamped): slug=%s closed=%s",
            canonical_slug, date_dir_name,
        )
        return ("skipped_existing", None)

    # Read PROJECT.md once; use for created-date extraction + summary
    # derivation + review body. ``errors="replace"`` mirrors archive.py.
    project_md_text = (archive_project_dir / "PROJECT.md").read_text(
        encoding="utf-8", errors="replace"
    )
    created = _backfill_extract_created_date(project_md_text)
    summary = _backfill_derive_short_summary(project_md_text)
    # Review body — pass the full PROJECT.md so phase regex extraction
    # in history_record gets material to work with.
    review = project_md_text

    scope = _backfill_scope_from_archive_path(archive_project_dir, repo)

    if dry_run:
        logger.info(
            "[dry-run] would stamp: slug=%s closed=%s created=%s scope=%s "
            "(summary[:60]=%r)",
            canonical_slug, date_dir_name, created, scope, summary[:60],
        )
        return ("would_stamp", None)

    # Mirror live close-stamp shape: pass archive_project_dir as
    # ``project_path``; ``slug_override`` strips the NN- prefix so the
    # ledger row matches canonical slug convention. ``repo_root``
    # ensures the ledger lands in THIS repo's project-history dir.
    result = history_record(
        project_path=str(archive_project_dir),
        status_at_close="historical",
        summary_md=summary,
        review_md=review,
        scope=scope,
        dates_created=created,
        dates_closed=date_dir_name,
        slug_override=canonical_slug,
        repo_root=repo,
    )
    existing_keys.add(key)
    logger.info(
        "stamped: slug=%s closed=%s tokens=%d (line %d)",
        canonical_slug,
        date_dir_name,
        result["record"]["token_count"]["total"],
        result["line_count"],
    )
    return ("stamped", result)


def backfill_project_history(
    repo_root: Path | None = None,
    *,
    dry_run: bool = False,
    worktree_path: str | Path | None = None,
) -> dict:
    """Walk ``archive/projects/`` and stamp every project's ledger row.

    Behaviour-preserving absorption of ``scripts/backfill-project-history.py``.
    Idempotent — re-running does NOT duplicate ledger entries (idempotency
    key = ``(slug, dates.closed)`` over historical rows only). Fail-loud —
    a missing PROJECT.md / malformed archive folder name / malformed
    existing-ledger line raises ``BackfillError`` with the path.

    Args:
        repo_root: repo root (tests); else ``worktree_path`` else
            ``REPO_ROOT``.
        dry_run: walk + log what would be stamped, but don't write.
        worktree_path: **Caller-aware path resolution.** When set AND
            ``repo_root`` is None, paths resolve against the caller's
            worktree root.

    Returns the same summary dict the former script printed:
        ``{"archives_seen", "stamped", "skipped_already_present",
        "ledger_lines_before", "ledger_lines_after", "ledger_path",
        "dry_run"[, "would_stamp"]}``.

    Raises:
        BackfillError: malformed archive folder / ledger line.
    """
    if repo_root is not None:
        repo = repo_root
    elif worktree_path is not None:
        repo = resolve_caller_root(worktree_path)
    else:
        repo = REPO_ROOT

    ledger_path = repo / "project-history" / "ledger.ndjson"
    existing_keys = _backfill_load_existing_keys(ledger_path)
    initial_count = (
        sum(1 for _ in ledger_path.open("r", encoding="utf-8"))
        if ledger_path.exists()
        else 0
    )

    archive_root = repo / "archive"
    archives = _backfill_discover_archives(archive_root)

    stamped = 0
    skipped = 0
    would_stamp = 0
    for proj_dir in archives:
        outcome, _ = _backfill_stamp_one(
            proj_dir, repo, existing_keys, dry_run=dry_run
        )
        if outcome == "stamped":
            stamped += 1
        elif outcome == "would_stamp":
            would_stamp += 1
        else:  # skipped_existing
            skipped += 1

    final_count = (
        sum(1 for _ in ledger_path.open("r", encoding="utf-8"))
        if ledger_path.exists()
        else 0
    )
    summary = {
        "archives_seen": len(archives),
        "stamped": stamped,
        "skipped_already_present": skipped,
        "ledger_lines_before": initial_count,
        "ledger_lines_after": final_count,
        "ledger_path": (
            str(ledger_path.relative_to(repo))
            if repo in ledger_path.parents
            else str(ledger_path)
        ),
        "dry_run": dry_run,
    }
    if dry_run:
        summary["would_stamp"] = would_stamp
    return summary


# ---------------------------------------------------------------------------
# FastMCP tool registration — see KB § PATTERNS/mcp-tool-conventions.md.
# ---------------------------------------------------------------------------


def register(server) -> None:
    """Register the history-record MCP tool.

    Per ``KB § PATTERNS/mcp-tool-conventions.md`` — 3-segment dotted
    naming (``<vendor>.<service>.<action>``), direct function args
    matching the existing dev-umbrella convention.
    """
    @server.tool(
        name="noctus.dev.history_record",
        description=(
            "Append one NDJSON record to project-history/ledger.ndjson. Reads "
            "PROJECT.md + improvements.md + proposals/*.md from `project_path`, "
            "tokenizes via the shared cascade (tiktoken cl100k_base when "
            "available; chars/4 fallback), walks `git log --grep <slug>` for a "
            "best-effort code-delta count, and writes one structured row. "
            "Append-only — re-stamping the same project appends a new line. "
            "status_at_close ∈ {shipped, abandoned, split, deferred, historical}. "
            "Used by the project-close protocol (`noctus.dev.archive` Phase 2). "
            "See projects/project-history-ledger/PROJECT.md."
        ),
    )
    def _history_record(
        project_path: str,
        status_at_close: str,
        summary_md: str,
        review_md: str,
        outcome_signals: list[str] | None = None,
        scope: str | None = None,
        dates_created: str | None = None,
        dates_closed: str | None = None,
        phases: list[dict] | None = None,
        worktree_path: str | None = None,
        slug_override: str | None = None,
    ) -> dict:
        return history_record(
            project_path=project_path,
            status_at_close=status_at_close,
            summary_md=summary_md,
            review_md=review_md,
            outcome_signals=outcome_signals,
            scope=scope,
            dates_created=dates_created,
            dates_closed=dates_closed,
            phases=phases,
            worktree_path=worktree_path,
            slug_override=slug_override,
        )

    @server.tool(
        name="noctus.dev.render_project_history",
        description=(
            "Render project-history/ledger.ndjson → project-history/PROJECT-HISTORY.md "
            "(the human-readable view). Dedupes-by-slug-keep-latest by dates.closed, "
            "sorts DESC by dates.closed (slug ASC tiebreak), idempotent (re-render on "
            "an unchanged ledger is byte-identical). Pass check=True to detect drift "
            "without writing. Invalid NDJSON raises ValueError with the line number. "
            "Run by the pre-commit hook when the ledger is staged/modified. Pass "
            "worktree_path when called from inside a git worktree. See "
            "projects/project-history-ledger/PROJECT.md § 6 Phase 3."
        ),
    )
    def _render_project_history(
        check: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return render_project_history(
            check=check,
            worktree_path=worktree_path,
        )

    @server.tool(
        name="noctus.dev.backfill_project_history",
        description=(
            "Walk archive/projects/<date>/NN-<slug>/PROJECT.md and append one ledger "
            "row per archived project with status_at_close='historical'. Idempotent "
            "— re-running does NOT duplicate entries (idempotency key = (slug, "
            "dates.closed) over historical rows only). Fail-loud — a missing "
            "PROJECT.md / malformed archive folder / malformed existing-ledger line "
            "raises BackfillError with the path (no silent-skip). Pass dry_run=True "
            "to preview. Pass worktree_path when called from inside a git worktree. "
            "See projects/project-history-ledger/PROJECT.md § 6 Phase 4."
        ),
    )
    def _backfill_project_history(
        dry_run: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return backfill_project_history(
            dry_run=dry_run,
            worktree_path=worktree_path,
        )


__all__ = [
    "history_record",
    "render_project_history",
    "backfill_project_history",
    "BackfillError",
    "register",
    "HistoryRecord",
    "HistoryDates",
    "HistoryPhase",
    "HistoryTokenCount",
]
