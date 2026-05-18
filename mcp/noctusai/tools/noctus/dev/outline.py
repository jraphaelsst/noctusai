"""``noctus.dev.outline`` — language-agnostic outline dispatch.

Rollup that auto-dispatches between ``outline_python`` and
``outline_typescript`` based on file extension. Eliminates the
caller-side language switch — agents that need *"read structure of
this file"* don't have to know which underlying parser to call.

Surfaced as a fusion candidate by ``noctus.seed.scan_fusions`` (score
0.65 — both tools take ``path``, both return outline results with
shared keys ``imports``, ``classes``, ``functions``, ``constants``).

Read-only; trivial composition over the two upstream parsers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_PYTHON_SUFFIXES: frozenset[str] = frozenset({".py", ".pyi"})
_TYPESCRIPT_SUFFIXES: frozenset[str] = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})


def outline(path: str | Path) -> dict[str, Any]:
    """Return the symbol tree of ``path`` regardless of language.

    Dispatches by file extension:
    - ``.py`` / ``.pyi`` → ``outline_python``
    - ``.ts`` / ``.tsx`` / ``.js`` / ``.jsx`` / ``.mjs`` / ``.cjs`` → ``outline_typescript``
    - other → ``{"error": "...", "language": null}``

    Args:
        path: File to outline. Resolved against repo root if relative.

    Returns:
        ``{
          "language": "python" | "typescript" | None,
          "result": <OutlineResult.to_dict()>,    # only when language is detected
          "error": str | None,                     # populated on dispatch failure
          "path": str,
        }``
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in _PYTHON_SUFFIXES:
        from .outline_python import outline_python
        result = outline_python(path)
        # OutlineResult is a dataclass — marshal to dict for MCP transport.
        return {
            "language": "python",
            "result": _result_to_dict(result),
            "error": None,
            "path": str(path),
        }
    if suffix in _TYPESCRIPT_SUFFIXES:
        from .outline_typescript import outline_typescript
        result = outline_typescript(path)
        return {
            "language": "typescript",
            "result": _result_to_dict(result),
            "error": None,
            "path": str(path),
        }
    return {
        "language": None,
        "result": None,
        "error": (
            f"unsupported extension {suffix!r}. Supported: "
            f"{sorted(_PYTHON_SUFFIXES | _TYPESCRIPT_SUFFIXES)}"
        ),
        "path": str(path),
    }


def _result_to_dict(result: Any) -> dict:
    """Marshal an OutlineResult dataclass to a plain dict. Handles both
    `to_dict` callables and bare dataclasses uniformly."""
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if hasattr(result, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(result)
    if isinstance(result, dict):
        return result
    return {"raw": repr(result)}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.outline",
        description=(
            "Language-agnostic outline. Dispatches to outline_python "
            "(.py/.pyi) or outline_typescript (.ts/.tsx/.js/.jsx) by "
            "file extension. One call instead of caller-side language "
            "switch. Read-only."
        ),
    )
    def _outline(path: str) -> dict:
        return outline(path)

    @server.tool(
        name="noctus.dev.scan_outlined",
        description=(
            "Audit the WHOLE platform (products/seed/mcp/scripts/"
            "noctusai_lib) for files the AST/outline tooling CANNOT read "
            "(SyntaxError / parse failure). Read-only. Returns the list "
            "of un-outline-able files so the pattern can be found + "
            "fixed — platform-wide companion to the pre-commit "
            "`--check-outlined` staged gate. Keeps AST-first / "
            "narrow-read tooling always functional."
        ),
    )
    def _scan_outlined() -> dict:
        from .compliance import check_files_outlined

        issues = check_files_outlined()
        return {
            "outlineable": not issues,
            "un_outlineable_count": len(issues),
            "files": issues,
        }
