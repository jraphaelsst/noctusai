"""engineer_output_linter — mechanize the dispatched-engineer two-leg footer rule.

Why this exists
    Per `KB § CONTEXT/PATTERNS/common/scoped-auto-improvement.md`, every
    dispatched engineer's return text MUST carry the two-leg footer:

      drift-found:
        - <leftover OUTSIDE the slice brief, surfaced not resolved>
        - ...

      scoped-improvement:
        - <slip / improvement IN-slice, applied if cheap, surfaced if expanded scope>
        - ...

    Today the rule is enforced by SOCIAL contract — architect eyeballs the
    return + complains if the footer is missing. This module makes it
    MECHANICAL: pass the engineer's return text to `lint_return(text)`;
    it surfaces missing sections + heuristically-empty sections + format drift.

How it composes
    `engineer_brief_compose` (W1-E2) auto-authors the brief that mentions
    the two-leg footer requirement. This linter is the receive-side: when
    the architect pastes an engineer return into a scratchpad (or pipes it
    through CI), this module flags compliance gaps before the architect
    integrates.

Public API
    lint_return(text: str) -> dict
        Returns `{ok, missing: [...], empty: [...], warnings: [...]}`.
        ok=True ⇔ both legs present AND non-empty AND format-clean.

MCP tools
    noctus.dev.engineer_output_lint — surface compliance check.

KB § CONTEXT/PATTERNS/common/engineer-output-linter.md.
"""
from __future__ import annotations

import re
from typing import Any


# Pattern that captures a section header — case-insensitive at start of line.
# Tolerates `drift-found:` / `Drift-found:` / `DRIFT-FOUND:` / surrounding bold.
_HEADER_PATTERN = re.compile(
    r"^\**\s*(drift-found|scoped-improvement)\s*:\s*\**\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Bullet/list markers we treat as "this section has content." Tolerant of
# `-`, `*`, `1.`, and minor indentation.
_BULLET_PATTERN = re.compile(r"^\s*([-*]|[0-9]+\.)\s+\S+", re.MULTILINE)

# Sentinel phrases that mean "this section is intentionally empty." These
# count as content (a deliberate "nothing to surface") rather than a gap.
_EMPTY_SENTINELS = (
    "none",
    "n/a",
    "(none)",
    "no drift",
    "no drift found",
    "no improvements",
    "nothing",
)


def _extract_section(text: str, header_name: str) -> str | None:
    """Return the body of `<header_name>:` section, or None if header missing.

    Body = everything from after the header line up to the NEXT recognized
    section header OR end of text. Empty body returns ''.
    """
    headers = list(_HEADER_PATTERN.finditer(text))
    target_idx = None
    for i, match in enumerate(headers):
        if match.group(1).lower() == header_name.lower():
            target_idx = i
            break
    if target_idx is None:
        return None
    start = headers[target_idx].end()
    end = headers[target_idx + 1].start() if target_idx + 1 < len(headers) else len(text)
    return text[start:end].strip()


def _looks_empty(body: str) -> bool:
    """True if section body is empty OR matches a sentinel ('none', 'n/a', ...).

    Bullets / structured content ⇒ False (not empty). Free-text shorter than
    a sentinel + no bullets ⇒ might be empty; we check the sentinels.
    """
    if not body:
        return True
    if _BULLET_PATTERN.search(body):
        return False
    # No bullets — check sentinel match.
    normalized = body.lower().strip().strip(".").strip()
    return normalized in _EMPTY_SENTINELS or len(normalized) < 4


def lint_return(text: str) -> dict[str, Any]:
    """Inspect a dispatched-engineer return text for the two-leg footer.

    Returns:
        {
          "ok": bool,                  # True iff both legs present + non-empty
          "missing": list[str],        # section headers absent entirely
          "empty": list[str],          # present but empty / sentinel-only
          "warnings": list[str],       # format drift (not blocking)
        }

    Empty `text` ⇒ `ok=False`, both legs missing.
    """
    if not text or not text.strip():
        return {
            "ok": False,
            "missing": ["drift-found", "scoped-improvement"],
            "empty": [],
            "warnings": ["empty input text"],
        }

    missing: list[str] = []
    empty: list[str] = []
    warnings: list[str] = []

    for header in ("drift-found", "scoped-improvement"):
        body = _extract_section(text, header)
        if body is None:
            missing.append(header)
            continue
        if _looks_empty(body):
            # Intent-empty (sentinel) is OK; force-empty (no bullets, no sentinel)
            # also lands here. We surface it as a warning when literally empty,
            # and as compliant when sentinel-acknowledged.
            normalized = body.lower().strip().strip(".").strip()
            if normalized in _EMPTY_SENTINELS:
                continue  # sentinel — acceptable empty
            empty.append(header)

    # Format-drift warnings (advisory, not blocking).
    if "Co-Authored-By" in text and "drift-found:" not in text.lower():
        warnings.append(
            "return text contains a Co-Authored-By trailer but no "
            "drift-found section — likely a commit message instead of an "
            "engineer return"
        )

    ok = not missing and not empty
    return {
        "ok": ok,
        "missing": missing,
        "empty": empty,
        "warnings": warnings,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.engineer_output_lint",
        description=(
            "Check a dispatched-engineer return text for the mandatory "
            "two-leg footer (drift-found + scoped-improvement). Surfaces "
            "missing sections, empty sections, and format-drift warnings. "
            "Use BEFORE integrating an engineer's work — catches "
            "compliance-gap returns mechanically instead of via social "
            "contract. Returns "
            "{ok, missing: [...], empty: [...], warnings: [...]}. "
            "KB § CONTEXT/PATTERNS/common/engineer-output-linter.md."
        ),
    )
    def _lint(text: str) -> dict:
        return lint_return(text)


__all__ = ["lint_return", "register"]
