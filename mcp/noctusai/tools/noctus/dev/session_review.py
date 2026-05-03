"""`noctusai_review_session` — session-axis review.

Walks one Claude Code JSONL transcript and emits keeper-shaped issues
for any agent-discipline rule we have a detector for. The harness is
the cousin of `tools/review.py` (static-axis, walks repo files); this
one is dynamic-axis (walks the event stream).

**Detectors live here, side-by-side, sharing the `Event` contract:**

- `detect_ast_first` — `Bash(mutating sed/awk/...)` followed by
  `Edit/Write` on the same `.py|.ts|.tsx` path violates CLAUDE.md § 1
  AST-first. Phase 2 of `projects/session-review-baseline/`.
- `detect_narrow_read` — whole-file `Read` of a >200-line repo file
  with no preceding `outline_*` violates CLAUDE.md § 1 Narrow-read
  first. Phase 3 of `projects/session-review-baseline/`.

**Body-free output by construction (PROJECT.md § 3 principle 5).**
The `SessionIssue` shape carries paths, tool names, line numbers and
synthesized messages. It does NOT carry user/assistant message text or
the bodies of `tool_use.input` beyond what was needed to detect.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from session_loader import (
    DEFAULT_JSONL_DIR,
    Event,
    ToolResult,
    ToolUse,
    latest_session_path,
    load_session,
)

logger = logging.getLogger(__name__)

from settings import REPO_ROOT  # noqa: E402  (path constant)

Severity = Literal["INFO", "WARNING", "ERROR"]


@dataclass(frozen=True)
class SessionIssue:
    rule: str
    severity: Severity
    message: str
    suggestion: str
    jsonl_line: int
    tool_name: str
    target_path: Optional[str] = None


class ReviewSessionInput(BaseModel):
    path: Optional[str] = Field(
        None,
        description=(
            "Absolute path to a Claude Code JSONL transcript. Required on "
            "non-macOS hosts. When omitted, latest_session_path() resolves "
            "the newest *.jsonl in the macOS default project dir."
        ),
    )
    latest: bool = Field(
        False,
        description="When True (and `path` is None), resolve the newest *.jsonl in the default dir.",
    )


_AST_SOURCE_EXTS = (".py", ".ts", ".tsx")

# Mutation-marker regexes. Phase 0 calibration showed `\b(sed|awk)\b`
# alone over-flags read-only `sed -n '90,170p' file.py` patterns. The
# predicate below is `True` iff the command both mentions a known
# mutation-capable tool AND carries an explicit mutation marker. Tune
# this list as new tools surface in calibration runs.
_MUTATING_TOOL_RE = re.compile(r"\b(sed|awk|tr|perl)\b")
_MUTATION_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsed\s+-\w*i\w*\b"),               # sed -i / -Ei
    re.compile(r"\bsed\s+--in-place\b"),
    re.compile(r"\bperl\s+-\w*i\w*\b"),              # perl -i / -pi
    re.compile(r"\bperl\s+--in-place\b"),
    re.compile(r"\bs(/|\|)[^/|\s]+(/|\|)[^/|]*(/|\|)"),  # s/x/y/ substitution body
    re.compile(r">>?\s*\S+\.(?:py|ts|tsx)\b"),       # > foo.py / >> foo.ts
)


def detect_ast_first(events: list[Event]) -> list[SessionIssue]:
    """Flag `Bash(mutating sed/awk/...)` immediately preceding an
    `Edit/Write` on the same `.py|.ts|.tsx` file.

    Walks events forward; for every `Edit/Write` on a parser-readable
    source file, scans backward for the most recent `Bash` whose command
    both mentions a mutation-capable tool AND carries a mutation marker
    AND references the same target path. If the prior touch on
    `target_path` was an Edit/Write (not a Bash mutation), we treat the
    AST-first principle as already satisfied for the earlier mutation.
    """
    issues: list[SessionIssue] = []
    for idx, ev in enumerate(events):
        if not isinstance(ev, ToolUse):
            continue
        if ev.name not in ("Edit", "Write"):
            continue
        target = (ev.input or {}).get("file_path") or ""
        if not target.endswith(_AST_SOURCE_EXTS):
            continue
        offending = _scan_backward_for_mutating_bash(events, idx, target)
        if offending is None:
            continue
        issues.append(
            SessionIssue(
                rule="ast-first",
                severity="WARNING",
                message=(
                    f"Bash mutation on {Path(target).name} at line {offending.line_no} "
                    f"was followed by {ev.name} on the same path at line {ev.line_no}. "
                    f"AST-first rule (CLAUDE.md § 1) requires libcst / ts-morph / "
                    f"tree-sitter for parser-readable source files."
                ),
                suggestion=(
                    f"Replace the `Bash` regex/sed step with an AST tool. For "
                    f"`.py` use `libcst`; for `.ts`/`.tsx` use `ts-morph`. See "
                    f"`KB § PATTERNS/ast.md` for the canonical recipes."
                ),
                jsonl_line=offending.line_no,
                tool_name="Bash",
                target_path=target,
            )
        )
    return issues


def _scan_backward_for_mutating_bash(
    events: list[Event], end_idx: int, target_path: str
) -> ToolUse | None:
    """Walk events[0:end_idx] in reverse. Return the closest Bash
    `ToolUse` whose command mutates `target_path`, OR None if a prior
    Edit/Write on `target_path` was hit first (in which case AST-first
    is already satisfied for any earlier mutation)."""
    for j in range(end_idx - 1, -1, -1):
        prev = events[j]
        if not isinstance(prev, ToolUse):
            continue
        if prev.name in ("Edit", "Write"):
            prev_path = (prev.input or {}).get("file_path") or ""
            if prev_path == target_path:
                return None  # earlier Edit/Write satisfies the cursor
            continue
        if prev.name != "Bash":
            continue
        cmd = (prev.input or {}).get("command") or ""
        if _is_mutating(cmd, target_path):
            return prev
    return None


def _is_mutating(command: str, target_path: str) -> bool:
    """Mutation predicate: command mentions a mutation-capable tool AND
    carries a mutation marker AND references `target_path`. Phase 0
    calibration finding (PROJECT.md § 5.4)."""
    if not _MUTATING_TOOL_RE.search(command):
        return False
    if not any(m.search(command) for m in _MUTATION_MARKERS):
        return False
    # Path reference can be absolute or basename — agents do both. Match
    # either form to avoid false-negatives.
    target = Path(target_path)
    if target_path in command or target.name in command:
        return True
    return False


def detect_narrow_read(
    events: list[Event],
    *,
    repo_root: Path | None = None,
) -> list[SessionIssue]:
    """Flag whole-file `Read` (no `offset` and no `limit`) of a >200-line
    repo file when no `outline_*` precedes it for that path.

    Severity starts at INFO per PROJECT.md § 3 principle 4 — calibration
    in Phase 3 tunes from there. We only stat files that resolve under
    `repo_root` (default `REPO_ROOT`); reads outside the repo (system
    docs, /tmp scratch, referenced output paths) are skipped.

    The `repo_root` kwarg is the dependency-injection seam tests use
    instead of monkey-patching the module global.
    """
    root = repo_root or REPO_ROOT
    issues: list[SessionIssue] = []
    outlined_paths: set[str] = set()  # paths that had a prior outline_*

    for ev in events:
        if not isinstance(ev, ToolUse):
            continue
        # Track outline_* calls so subsequent reads on those paths are
        # exempt. Match both flat (`outline_python`) and prefixed
        # (`noctusai_outline_python`, `mcp__noctusai__noctusai_outline_python`)
        # tool names — the agent surface ships under multiple aliases.
        lname = ev.name.lower()
        if "outline_python" in lname or "outline_typescript" in lname:
            p = (ev.input or {}).get("path") or (ev.input or {}).get("file_path") or ""
            if p:
                outlined_paths.add(_norm_path(p))
            continue
        if ev.name != "Read":
            continue
        inp = ev.input or {}
        if "offset" in inp or "limit" in inp:
            continue  # narrow read — compliant by construction
        target = inp.get("file_path") or ""
        if not target:
            continue
        norm = _norm_path(target)
        if norm in outlined_paths:
            continue
        line_count = _line_count_if_in_repo(norm, root)
        if line_count is None or line_count <= 200:
            continue
        issues.append(
            SessionIssue(
                rule="narrow-read",
                severity="INFO",
                message=(
                    f"Whole-file Read on {Path(target).name} ({line_count} lines) "
                    f"with no prior outline_* call. Narrow-read rule (CLAUDE.md § 1) "
                    f"says: structure before bodies for files >200 lines."
                ),
                suggestion=(
                    f"Outline first: `noctusai_outline_python` (or "
                    f"`outline_typescript` for `.ts`/`.tsx`); then `Read` with "
                    f"`offset`/`limit` for the symbol you actually need. "
                    f"See `KB § PATTERNS/agent-reading-discipline.md`."
                ),
                jsonl_line=ev.line_no,
                tool_name="Read",
                target_path=target,
            )
        )
    return issues


def _norm_path(path_str: str) -> str:
    try:
        return str(Path(path_str).resolve())
    except (OSError, RuntimeError):
        return path_str


def _line_count_if_in_repo(norm_path: str, repo_root: Path) -> Optional[int]:
    """Stat-and-count if `norm_path` lives under `repo_root` and exists.
    Returns None for outside-repo paths or missing files (we don't want
    to flag a Read against a file the user has since deleted/renamed)."""
    try:
        p = Path(norm_path)
        if not p.is_file():
            return None
        if repo_root not in p.parents and p != repo_root:
            return None
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


# Detector registry — the orchestrator iterates this list, in this
# order. Adding a Phase 5+ detector is a one-line append.
_DETECTORS = (
    ("ast-first", detect_ast_first),
    ("narrow-read", detect_narrow_read),
)


def _call_detector(fn, events, *, repo_root):
    """Pass `repo_root` to detectors that accept it; call others bare.
    Lets the registry mix repo-aware and repo-independent detectors."""
    import inspect
    sig = inspect.signature(fn)
    if "repo_root" in sig.parameters:
        return fn(events, repo_root=repo_root)
    return fn(events)


def review_session(
    path: Path | str | None = None,
    *,
    latest: bool = False,
    repo_root: Path | None = None,
) -> dict:
    """Resolve a JSONL path, load events, run all detectors, return a
    keeper-shaped result dict.

    Args:
        path: Absolute path to a Claude Code JSONL transcript. Required
            on non-macOS hosts. When None and `latest=True`, resolves the
            newest *.jsonl in the macOS default dir.
        latest: When True and `path is None`, resolve the latest local
            session.

    Returns:
        dict with keys: `session_path`, `event_count`, `issues_found`,
        `issues` (list of dicts), `detectors_run` (list of rule names).
    """
    if path is None:
        if not latest:
            raise ValueError(
                "review_session requires either `path=<jsonl>` or `latest=True`. "
                "On non-macOS hosts always pass an explicit path."
            )
        resolved = latest_session_path()
    else:
        resolved = Path(path)

    events = load_session(resolved)
    all_issues: list[SessionIssue] = []
    for _, fn in _DETECTORS:
        all_issues.extend(_call_detector(fn, events, repo_root=repo_root))

    # Stable sort: jsonl_line ascending, then rule name (PROJECT.md § 7 Q6).
    all_issues.sort(key=lambda i: (i.jsonl_line, i.rule))

    return {
        "session_path": str(resolved),
        "default_jsonl_dir": str(DEFAULT_JSONL_DIR),
        "event_count": len(events),
        "issues_found": len(all_issues),
        "issues": [asdict(i) for i in all_issues],
        "detectors_run": [name for name, _ in _DETECTORS],
    }


def register(server) -> None:
    desc = (
        "OBSERVATION-ONLY session-axis review. Walks one Claude Code JSONL transcript "
        "and emits keeper-shaped issues for agent-discipline rules (AST-first, "
        "narrow-read). Body-free output by construction. Pass `path=<jsonl>` or "
        "`latest=true` (latest = newest *.jsonl in the macOS default project dir)."
    )

    def _review_session(
        path: str | None = None,
        latest: bool = False,
    ) -> dict:
        return review_session(path=path, latest=latest)

    server.tool(name="noctusai_review_session", description=desc)(_review_session)
    server.tool(
        name="noctus.dev.review_session",
        description="Dotted alias for noctusai_review_session.",
    )(_review_session)
