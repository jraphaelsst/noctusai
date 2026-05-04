"""Recurrence-scan tool — wraps `noctus.dev.scan_*` Python functions.

Per design-reference.md §3 + KB § 06-AGENTS.md absorption-search sextet:
- ``scan_recurrence`` — repeated lines.
- ``scan_cross_product_helpers`` — duplicated helpers across products.
- ``scan_within_product_helpers`` — duplicated helpers within a product.
- ``scan_service_line_recurrence`` — service-line repetition.
- ``scan_block_patterns`` — try/except + control-flow repetition.

The wrap targets live at
``mcp/noctusai/tools/noctus/dev/recurrence.py``. We add ``mcp/noctusai/`` to
sys.path lazily so dev_team imports cleanly even when MCP is not on PATH.
"""

from __future__ import annotations

from typing import Any, Callable

from dev_team.tools._mcp_path import ensure_mcp_path


def _import_recurrence_module():
    """Lazy-import the recurrence module from mcp/noctusai/."""
    ensure_mcp_path()
    # noinspection PyUnresolvedReferences
    from tools.noctus.dev import recurrence as _r  # type: ignore[import-not-found]

    return _r


def recurrence_scan(
    mode: str = "recurrence",
    *,
    repo_root: str | None = None,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
    **kwargs: Any,
) -> dict:
    """Run an absorption-search scan.

    Args:
        mode: One of ``recurrence`` (default), ``cross_product_helpers``,
            ``within_product_helpers``, ``service_line``, ``block_patterns``.
        repo_root: Optional override (mostly for tests).
        min_count: Triage threshold — minimum N occurrences.
        must_formalize_threshold: At this count, severity escalates.
        **kwargs: Mode-specific extras forwarded to the underlying scanner.

    Returns:
        Whatever the wrapped scanner returns (typically
        ``{"findings": [...], "stats": {...}}``).
    """
    from pathlib import Path as _P

    rec = _import_recurrence_module()
    root = _P(repo_root) if repo_root else None

    if mode == "recurrence":
        return rec.scan_recurrence(
            repo_root=root,
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
            **kwargs,
        )
    if mode == "cross_product_helpers":
        return rec.scan_cross_product_helpers(repo_root=root, **kwargs)
    if mode == "within_product_helpers":
        return rec.scan_within_product_helpers(repo_root=root, **kwargs)
    if mode == "service_line":
        return rec.scan_service_line_recurrence(repo_root=root, **kwargs)
    if mode == "block_patterns":
        return rec.scan_block_patterns(repo_root=root, **kwargs)
    raise ValueError(
        f"unknown recurrence mode {mode!r}; expected recurrence / "
        "cross_product_helpers / within_product_helpers / service_line / "
        "block_patterns."
    )


def build_recurrence_scan_tool(**kwargs) -> Callable:
    return recurrence_scan


__all__ = ["recurrence_scan", "build_recurrence_scan_tool"]
