"""`noctus.dev.knowledge_bundle_export` — export a sibling repo's git
history of its knowledge-base + project-state files into the JSONL
bundle shape the ``academia-de-reciclagem`` importer consumes
(contract §B.6, ``app/importer/bundle.py``).

For every commit that touched a path matching ``include_globs`` (git
``--follow`` per matching path, so a later rename is still traced back),
emits one JSONL line ``{path, git_sha, git_author_raw, git_committed_at,
git_message, content}`` — the file's content AT that commit, via
``git show <sha>:<path>``.

**Refusals (never a silent write):**
- Any line's ``content`` trips the secret scan -> the WHOLE export is
  refused, and every offending path is reported in ``refused_paths``.
  Nothing is written to ``out_dir``.
- ``out_dir`` resolves inside ``repo_path`` OR inside this noc repo's
  own root -> refused outright (``{ok: false, error}``). The bundle
  must never land inside a git working tree — it is meant for an
  out-of-band admin upload, not a commit.

**Why the secret scan here is a small duplicate, not an import.** This
module lives in the shared MCP toolkit and cannot import
``products/academia-de-reciclagem/backend/app/importer/secrets.py`` —
that package isn't on this process's Python path, and reaching across
the product/toolkit boundary would be a real layering violation, not a
convenience. The scan logic (known-pattern + Shannon-entropy heuristic,
hyphen-excluded token class) is kept identical in *behaviour* to
``app/importer/secrets.py`` deliberately. See this module's
`scoped-improvement` footer in the A2 delivery note for the follow-up:
hoist both copies to one `noctusai_lib` helper once A1's
``app/knowledge/`` lands, so they can never drift apart.
"""
from __future__ import annotations

import json
import logging
import math
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

DEFAULT_INCLUDE_GLOBS: tuple[str, ...] = (
    "KNOWLEDGE-BASE/**/*.md",
    "projects/state/*.json",
    "docs/SPEC.md",
    "docs/OPEN-QUESTIONS.md",
)

_BUNDLE_FILENAME = "knowledge-bundle.jsonl"

# --- content secret scan (mirrors app/importer/secrets.py; see module
# docstring for why this is a deliberate small duplicate) -------------------

_KNOWN_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"pk_[A-Za-z0-9]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_SECRET_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=]{28,}")
_SECRET_ENTROPY_THRESHOLD = 3.5


def _shannon_entropy(token: str) -> float:
    if not token:
        return 0.0
    counts = Counter(token)
    length = len(token)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _content_has_secret(content: str) -> bool:
    for pattern in _KNOWN_SECRET_PATTERNS:
        if pattern.search(content):
            return True
    for token in _SECRET_TOKEN_RE.findall(content):
        if _shannon_entropy(token) >= _SECRET_ENTROPY_THRESHOLD:
            return True
    return False


# --- git plumbing ------------------------------------------------------


class GitCommandError(RuntimeError):
    """A git subprocess call failed."""


def _run_git(repo_path: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def _pathspec(glob: str) -> str:
    return f":(glob){glob}"


@dataclass(frozen=True, slots=True)
class _Commit:
    sha: str
    author: str
    committed_at: str
    message: str


def _list_matching_paths(repo_path: Path, include_globs: tuple[str, ...]) -> list[str]:
    """Every path that ever matched any glob at some commit (added,
    modified, renamed, or copied — never a pure deletion), across the
    full history of the current branch.
    """
    pathspecs = [_pathspec(g) for g in include_globs]
    out = _run_git(
        repo_path,
        ["log", "--format=", "--name-only", "--diff-filter=ACMR", "--", *pathspecs],
    )
    seen: dict[str, None] = {}
    for line in out.splitlines():
        line = line.strip()
        if line:
            seen[line] = None
    return list(seen.keys())


def _commits_for_path(repo_path: Path, path: str) -> list[_Commit]:
    """Every commit that added/modified this exact path (``--follow``
    across renames), oldest first, excluding pure deletions.
    """
    sep = "\x1f"
    fmt = f"%H{sep}%an{sep}%aI{sep}%s"
    out = _run_git(
        repo_path,
        [
            "log",
            "--follow",
            "--reverse",
            "--diff-filter=ACMR",
            f"--format={fmt}",
            "--",
            path,
        ],
    )
    commits: list[_Commit] = []
    for line in out.splitlines():
        if not line:
            continue
        sha, author, committed_at, message = line.split(sep, 3)
        commits.append(_Commit(sha=sha, author=author, committed_at=committed_at, message=message))
    return commits


def _show_content(repo_path: Path, sha: str, path: str) -> str:
    return _run_git(repo_path, ["show", f"{sha}:{path}"])


@dataclass
class ExportResult:
    ok: bool
    path: str | None = None
    lines: int = 0
    commits: int = 0
    paths: list[str] = field(default_factory=list)
    refused_paths: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "path": self.path,
            "lines": self.lines,
            "commits": self.commits,
            "paths": self.paths,
            "refused_paths": self.refused_paths,
            "error": self.error,
        }


def _resolve_or_none(p: Path) -> Path | None:
    try:
        return p.resolve()
    except OSError:
        return None


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def export_knowledge_bundle(
    repo_path: str,
    out_dir: str,
    include_globs: tuple[str, ...] | None = None,
) -> ExportResult:
    """Export ``repo_path``'s git history (paths matching
    ``include_globs``) to a JSONL bundle under ``out_dir``.
    """
    globs = include_globs or DEFAULT_INCLUDE_GLOBS

    repo = _resolve_or_none(Path(repo_path))
    out = _resolve_or_none(Path(out_dir))
    if repo is None or out is None:
        return ExportResult(ok=False, error="repo_path or out_dir is not a resolvable path")

    if not (repo / ".git").exists():
        return ExportResult(ok=False, error=f"{repo} is not a git repository (.git missing)")

    noc_root = REPO_ROOT.resolve()
    if _is_inside(out, repo) or out == repo:
        return ExportResult(
            ok=False,
            error=f"out_dir ({out}) resolves inside repo_path ({repo}) — refusing to write into a git tree",
        )
    if _is_inside(out, noc_root) or out == noc_root:
        return ExportResult(
            ok=False,
            error=f"out_dir ({out}) resolves inside the noc repo root ({noc_root}) — refusing to write into a git tree",
        )

    try:
        matching_paths = _list_matching_paths(repo, globs)
    except GitCommandError as exc:
        return ExportResult(ok=False, error=str(exc))

    rows: list[dict] = []
    refused_paths: list[str] = []
    commit_shas: set[str] = set()

    for path in matching_paths:
        try:
            commits = _commits_for_path(repo, path)
        except GitCommandError as exc:
            return ExportResult(ok=False, error=str(exc))

        for commit in commits:
            try:
                content = _show_content(repo, commit.sha, path)
            except GitCommandError as exc:
                logger.warning(
                    "knowledge_bundle_export: cannot show %s:%s (%s), skipping",
                    commit.sha, path, exc,
                )
                continue

            if _content_has_secret(content):
                refused_paths.append(path)
                continue

            commit_shas.add(commit.sha)
            rows.append(
                {
                    "path": path,
                    "git_sha": commit.sha,
                    "git_author_raw": commit.author,
                    "git_committed_at": commit.committed_at,
                    "git_message": commit.message,
                    "content": content,
                }
            )

    if refused_paths:
        return ExportResult(
            ok=False,
            error="secret(s) detected in bundle content — refusing to write",
            paths=sorted(set(matching_paths)),
            refused_paths=sorted(set(refused_paths)),
        )

    out.mkdir(parents=True, exist_ok=True)
    bundle_path = out / _BUNDLE_FILENAME
    with bundle_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")

    return ExportResult(
        ok=True,
        path=str(bundle_path),
        lines=len(rows),
        commits=len(commit_shas),
        paths=sorted({r["path"] for r in rows}),
        refused_paths=[],
    )


def register(server) -> None:
    @server.tool(
        name="noctus.dev.knowledge_bundle_export",
        description=(
            "Export a git repo's history of its knowledge-base + project-state files "
            "(default globs: KNOWLEDGE-BASE/**/*.md, projects/state/*.json, "
            "docs/SPEC.md, docs/OPEN-QUESTIONS.md) into the JSONL bundle shape the "
            "academia-de-reciclagem importer consumes. Runs a content secret scan "
            "first — any hit refuses the whole export. Refuses out_dir when it "
            "resolves inside repo_path or inside the noc repo root: the bundle must "
            "never land in a git tree."
        ),
    )
    def _knowledge_bundle_export(
        repo_path: str,
        out_dir: str,
        include_globs: list[str] | None = None,
    ) -> dict:
        globs = tuple(include_globs) if include_globs else DEFAULT_INCLUDE_GLOBS
        return export_knowledge_bundle(repo_path, out_dir, globs).to_dict()
