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


__all__ = [
    "history_record",
    "register",
    "HistoryRecord",
    "HistoryDates",
    "HistoryPhase",
    "HistoryTokenCount",
]
