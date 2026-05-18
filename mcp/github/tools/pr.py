"""github.pr.* tools — pull-request lifecycle + CI visibility.

Reads (no confirm gate): list / view / diff / checks.
Writes (confirm-gated, outward-facing): create / ready.

Every tool routes through the single `gh.run_gh` seam (tests patch
`github.gh.run_gh`). `gh` failure ⇒ a typed-error envelope
(`_kit.errors.typed_error`), never a fabricated success.

`gh` is invoked via the module (`gh.run_gh`), NOT `from ..gh import
run_gh`, so a test `patch("github.gh.run_gh")` is actually observed by
these handlers.
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import gh
from ..settings import get_settings
from ..types import (
    CheckRun,
    PrChecksInput,
    PrChecksOutput,
    PrCreateInput,
    PrCreateOutput,
    PrDetail,
    PrDiffInput,
    PrDiffOutput,
    PrListInput,
    PrListOutput,
    PrReadyInput,
    PrReadyOutput,
    PrSummary,
    PrViewInput,
    PrViewOutput,
)

logger = logging.getLogger(__name__)

_SUMMARY_FIELDS = "number,title,state,author,headRefName,baseRefName,isDraft,url"
_DETAIL_FIELDS = _SUMMARY_FIELDS + ",body,mergeable,additions,deletions,changedFiles"
_CHECK_FIELDS = "name,state,bucket,link,workflow"
_TERMINAL_OK = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def _author_login(raw: object) -> Optional[str]:
    """`gh` returns `author` as an object `{login, ...}` (or null)."""
    if isinstance(raw, dict):
        return raw.get("login")
    return raw if isinstance(raw, str) else None


def _summary_kwargs(d: dict) -> dict:
    return {
        "number": d.get("number"),
        "title": d.get("title", ""),
        "state": d.get("state", ""),
        "author": _author_login(d.get("author")),
        "headRefName": d.get("headRefName"),
        "baseRefName": d.get("baseRefName"),
        "isDraft": bool(d.get("isDraft", False)),
        "url": d.get("url"),
    }


def _number_from_pr_url(url: str) -> Optional[int]:
    """`gh pr create` prints the PR URL (…/pull/<n>) on stdout."""
    tail = (url or "").rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _ctx(inp) -> dict:
    """Shared gh-invocation context from settings + the tool's repo arg."""
    s = get_settings()
    return {
        "gh_path": s.effective_gh_path,
        "repo": getattr(inp, "repo", None) or s.default_repo,
        "timeout": s.timeout_seconds,
    }


# ─── Reads ───────────────────────────────────────────────────────────────


async def pr_list(args: dict) -> dict:
    inp = PrListInput(**args)
    try:
        data = gh.run_gh(
            ["pr", "list", "--state", inp.state, "--limit", str(inp.limit),
             "--json", _SUMMARY_FIELDS],
            **_ctx(inp),
        )
    except gh.GitHubCliError as e:
        return PrListOutput(error=typed_error(e)).model_dump()
    pulls = [PrSummary(**_summary_kwargs(d)) for d in (data or [])]
    return PrListOutput(pulls=pulls).model_dump()


async def pr_view(args: dict) -> dict:
    inp = PrViewInput(**args)
    try:
        d = gh.run_gh(
            ["pr", "view", str(inp.number), "--json", _DETAIL_FIELDS],
            **_ctx(inp),
        )
    except gh.GitHubCliError as e:
        return PrViewOutput(error=typed_error(e)).model_dump()
    detail = PrDetail(
        **_summary_kwargs(d),
        body=d.get("body"),
        mergeable=d.get("mergeable"),
        additions=d.get("additions"),
        deletions=d.get("deletions"),
        changedFiles=d.get("changedFiles"),
    )
    return PrViewOutput(pull=detail).model_dump()


async def pr_diff(args: dict) -> dict:
    inp = PrDiffInput(**args)
    try:
        diff = gh.run_gh(
            ["pr", "diff", str(inp.number)], parse_json=False, **_ctx(inp)
        )
    except gh.GitHubCliError as e:
        return PrDiffOutput(error=typed_error(e)).model_dump()
    return PrDiffOutput(diff=diff or "").model_dump()


async def pr_checks(args: dict) -> dict:
    inp = PrChecksInput(**args)
    try:
        # exit 8 = pending / exit 1 = failing — both ship valid JSON.
        data = gh.run_gh(
            ["pr", "checks", str(inp.number), "--json", _CHECK_FIELDS],
            allow_nonzero=True,
            **_ctx(inp),
        )
    except gh.GitHubCliError as e:
        return PrChecksOutput(error=typed_error(e)).model_dump()
    runs = [CheckRun(**{k: c.get(k) for k in CheckRun.model_fields})
            for c in (data or [])]
    all_passing = (
        all((r.state or "").upper() in _TERMINAL_OK for r in runs)
        if runs else None
    )
    return PrChecksOutput(checks=runs, all_passing=all_passing).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def pr_create(args: dict) -> dict:
    inp = PrCreateInput(**args)
    if not inp.confirm:
        return PrCreateOutput(
            error=typed_error(gh.ConfirmationRequiredError("github.pr.create"))
        ).model_dump()
    cmd = ["pr", "create", "--title", inp.title, "--body", inp.body]
    if inp.base:
        cmd += ["--base", inp.base]
    if inp.head:
        cmd += ["--head", inp.head]
    if inp.draft:
        cmd.append("--draft")
    try:
        url = gh.run_gh(cmd, parse_json=False, **_ctx(inp))
    except gh.GitHubCliError as e:
        return PrCreateOutput(error=typed_error(e)).model_dump()
    return PrCreateOutput(
        created=True, url=url or None, number=_number_from_pr_url(url)
    ).model_dump()


async def pr_ready(args: dict) -> dict:
    inp = PrReadyInput(**args)
    if not inp.confirm:
        return PrReadyOutput(
            error=typed_error(gh.ConfirmationRequiredError("github.pr.ready"))
        ).model_dump()
    try:
        gh.run_gh(
            ["pr", "ready", str(inp.number)], parse_json=False, **_ctx(inp)
        )
    except gh.GitHubCliError as e:
        return PrReadyOutput(error=typed_error(e)).model_dump()
    return PrReadyOutput(ready=True).model_dump()


# ─── Registration (the _kit leaf-module contract) ────────────────────────


HANDLERS = {
    "github.pr.list": pr_list,
    "github.pr.view": pr_view,
    "github.pr.diff": pr_diff,
    "github.pr.checks": pr_checks,
    "github.pr.create": pr_create,
    "github.pr.ready": pr_ready,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="github.pr.list",
            description="List pull requests (state-filtered). READ-ONLY.",
            inputSchema=PrListInput.model_json_schema(),
        ),
        Tool(
            name="github.pr.view",
            description="View one pull request (title/body/refs/diffstat). "
            "READ-ONLY.",
            inputSchema=PrViewInput.model_json_schema(),
        ),
        Tool(
            name="github.pr.diff",
            description="Unified diff of a pull request. READ-ONLY.",
            inputSchema=PrDiffInput.model_json_schema(),
        ),
        Tool(
            name="github.pr.checks",
            description="CI check-run status for a PR — the merge-readiness "
            "signal. READ-ONLY. `all_passing` is None when there are no "
            "checks (cannot assert pass on an empty set).",
            inputSchema=PrChecksInput.model_json_schema(),
        ),
        Tool(
            name="github.pr.create",
            description="Open a pull request. WRITE / outward-facing — "
            "confirm-gated (status 412 without confirm=true, no side-effect).",
            inputSchema=PrCreateInput.model_json_schema(),
        ),
        Tool(
            name="github.pr.ready",
            description="Mark a draft PR ready for review. WRITE — "
            "confirm-gated.",
            inputSchema=PrReadyInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
