"""Proposal tool — `file_proposal`. Wraps `noctus.dev.file_proposal`."""

from __future__ import annotations

from typing import Callable, Optional

from dev_team.tools._mcp_path import ensure_mcp_path


def _import_proposals_module():
    ensure_mcp_path()
    # noinspection PyUnresolvedReferences
    from tools.noctus.dev import proposals as _p  # type: ignore[import-not-found]

    return _p


def file_proposal(
    *,
    title: str,
    body: str,
    agent: str = "keeper",
    project: Optional[str] = None,
    product: Optional[str] = None,
    subdir: Optional[str] = None,
) -> dict:
    """File a proposal markdown via the underlying noctus.dev tool.

    Args:
        title: Used to compute the filename slug + dedup key.
        body: Fully rendered markdown.
        agent: Origin tag — filename prefix.
        project: Project slug (mutually exclusive with ``product``).
        product: Product slug (e.g. for keeper / compliance proposals).
        subdir: Subdirectory under the product proposals dir.

    Returns:
        ``{"created": bool, "file": str, "path": str}``.
    """
    mod = _import_proposals_module()
    return mod.file_proposal(
        title=title,
        body=body,
        agent=agent,
        project=project,
        product=product,
        subdir=subdir,
    )


def build_file_proposal_tool(**kwargs) -> Callable:
    return file_proposal


__all__ = ["file_proposal", "build_file_proposal_tool"]
