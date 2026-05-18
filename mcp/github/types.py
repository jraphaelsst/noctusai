"""Pydantic In/Out schemas for the GitHub connector MCP tools.

One In + one Out model per tool (vista/meta `types.py` shape). Out
models are JSON-friendly mirrors of the `gh` JSON surface — the tool
normalizes `gh`'s nested objects (e.g. `author.login`) into flat fields
so the host LLM gets a stable contract independent of `gh` versioning.

`github` is imported as a top-level package (no flat-`sys.path[0]`
collision — see `mcp/_kit/README.md`), so `types.py` is a safe module
name here (it never shadows the stdlib for the process).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# ─── Shared write-gate field (mirrors meta/types.py `_CONFIRM`) ──────────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False/omitted returns a "
        "typed error (status 412) and performs NO side-effect. This is "
        "the confirm-then-execute gate for an outward-facing action."
    ),
)

_REPO = Field(
    default=None,
    description="Target 'OWNER/REPO'. Omit to use GITHUB_DEFAULT_REPO or "
    "let `gh` infer it from the current git remote.",
)


# ─── github.pr.list ──────────────────────────────────────────────────────


class PrSummary(BaseModel):
    number: int
    title: str
    state: str
    author: Optional[str] = None
    headRefName: Optional[str] = None
    baseRefName: Optional[str] = None
    isDraft: bool = False
    url: Optional[str] = None


class PrListInput(BaseModel):
    """List pull requests. PURE read — no side-effect, no confirm gate."""

    state: str = Field(
        "open",
        description="Filter: 'open' | 'closed' | 'merged' | 'all'.",
    )
    limit: int = Field(20, ge=1, le=100, description="Max PRs to return.")
    repo: Optional[str] = _REPO


class PrListOutput(BaseModel):
    pulls: List[PrSummary] = Field(default_factory=list)
    error: Optional[dict] = None


# ─── github.pr.view ──────────────────────────────────────────────────────


class PrDetail(PrSummary):
    body: Optional[str] = None
    mergeable: Optional[str] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    changedFiles: Optional[int] = None


class PrViewInput(BaseModel):
    """View one pull request. PURE read."""

    number: int = Field(..., description="The PR number.")
    repo: Optional[str] = _REPO


class PrViewOutput(BaseModel):
    pull: Optional[PrDetail] = None
    error: Optional[dict] = None


# ─── github.pr.diff ──────────────────────────────────────────────────────


class PrDiffInput(BaseModel):
    """Fetch the unified diff of a pull request. PURE read."""

    number: int = Field(..., description="The PR number.")
    repo: Optional[str] = _REPO


class PrDiffOutput(BaseModel):
    diff: Optional[str] = None
    error: Optional[dict] = None


# ─── github.pr.checks ────────────────────────────────────────────────────


class CheckRun(BaseModel):
    name: str
    state: Optional[str] = None
    bucket: Optional[str] = None
    link: Optional[str] = None
    workflow: Optional[str] = None


class PrChecksInput(BaseModel):
    """CI check-run status for a PR. PURE read — the merge-readiness signal."""

    number: int = Field(..., description="The PR number.")
    repo: Optional[str] = _REPO


class PrChecksOutput(BaseModel):
    checks: List[CheckRun] = Field(default_factory=list)
    all_passing: Optional[bool] = Field(
        None,
        description="True iff every check is terminal-success; None when "
        "there are no checks (cannot assert pass on an empty set).",
    )
    error: Optional[dict] = None


# ─── github.pr.create ────────────────────────────────────────────────────


class PrCreateInput(BaseModel):
    """Open a pull request. WRITE / outward-facing — confirm-gated.

    Body is sent verbatim to GitHub (human-read) — author it as prose,
    NOT symbol-first (doc-symbology §3 NOT-list: PR bodies stay readable).
    """

    title: str = Field(..., min_length=1, description="PR title.")
    body: str = Field("", description="PR body (Markdown, prose).")
    base: Optional[str] = Field(
        None, description="Base branch. Omit ⇒ repo default branch."
    )
    head: Optional[str] = Field(
        None, description="Head branch. Omit ⇒ current branch."
    )
    draft: bool = Field(False, description="Open as a draft PR.")
    repo: Optional[str] = _REPO
    confirm: bool = _CONFIRM


class PrCreateOutput(BaseModel):
    created: bool = False
    url: Optional[str] = None
    number: Optional[int] = None
    error: Optional[dict] = None


# ─── github.pr.ready ─────────────────────────────────────────────────────


class PrReadyInput(BaseModel):
    """Mark a draft PR ready for review. WRITE — confirm-gated."""

    number: int = Field(..., description="The draft PR number.")
    repo: Optional[str] = _REPO
    confirm: bool = _CONFIRM


class PrReadyOutput(BaseModel):
    ready: bool = False
    error: Optional[dict] = None


# ─── github.repo.view ────────────────────────────────────────────────────


class RepoViewInput(BaseModel):
    """Repo metadata — default branch, visibility, description. PURE read."""

    repo: Optional[str] = _REPO


class RepoViewOutput(BaseModel):
    nameWithOwner: Optional[str] = None
    defaultBranch: Optional[str] = None
    description: Optional[str] = None
    isPrivate: Optional[bool] = None
    url: Optional[str] = None
    error: Optional[dict] = None


# ─── github.diagnostics.connection_status ────────────────────────────────


class ConnectionStatusInput(BaseModel):
    """Introspect the `gh` dependency. PURE read.

    The gated-capability honesty signal: surfaces whether the `gh` binary
    is present AND authenticated, so a query that 'succeeds empty' because
    `gh` is logged out is never silently misread as 'no data'.
    """


class ConnectionStatusOutput(BaseModel):
    gh_available: bool = False
    gh_version: Optional[str] = None
    authenticated: Optional[bool] = None
    account: Optional[str] = None
    default_repo: Optional[str] = None
    error: Optional[dict] = None


__all__ = [
    "PrSummary",
    "PrListInput",
    "PrListOutput",
    "PrDetail",
    "PrViewInput",
    "PrViewOutput",
    "PrDiffInput",
    "PrDiffOutput",
    "CheckRun",
    "PrChecksInput",
    "PrChecksOutput",
    "PrCreateInput",
    "PrCreateOutput",
    "PrReadyInput",
    "PrReadyOutput",
    "RepoViewInput",
    "RepoViewOutput",
    "ConnectionStatusInput",
    "ConnectionStatusOutput",
]
