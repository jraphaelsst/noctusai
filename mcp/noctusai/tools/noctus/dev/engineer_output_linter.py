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


# ── outcome tags (owner rule 2026-11-05: errors are FIXED on contact) ─────────
# Every `drift-found:` bullet carries exactly one tag, at its END or at its START
# (2026-11-11: a leading `[fixed <sha>] text` was refused three times while the
# error only showed the tag shape, never where it goes - both ends now count):
#   [fixed <sha>] | [fixing → feat/<slug>] | [deferred → <destination> because <reason>]
# destination ∈ NOC-REMEDIATE[<class>] marker path · roadmap path
# (project-history/roadmaps/…) · owner reminder (MEMORY-reminders) · owner-decision ask.
_TAG_TAIL = re.compile(r"\[((?:fixed|fixing|deferred)\b(?:[^\[\]]|\[[^\[\]]*\])*)\]\s*$", re.IGNORECASE)
_TAG_HEAD = re.compile(r"^\[((?:fixed|fixing|deferred)\b(?:[^\[\]]|\[[^\[\]]*\])*)\]", re.IGNORECASE)
_FIXED_RE = re.compile(r"^fixed\s+([0-9a-f]{7,40})$", re.IGNORECASE)
_FIXING_RE = re.compile(r"^fixing\s*(?:→|->)\s*(feat/[\w./-]+)$")
_DEFERRED_RE = re.compile(r"^deferred\s*(?:→|->)\s*(.+?)\s+because\s+(.+)$", re.IGNORECASE | re.DOTALL)
_DEST_RES = (
    re.compile(r"NOC-REMEDIATE\[[\w.-]+\]"),
    re.compile(r"project-history/roadmaps/\S+"),
    re.compile(r"MEMORY-reminders", re.IGNORECASE),
    re.compile(r"owner[- ]decision", re.IGNORECASE),
)
MIN_DEFER_REASON = 10
TAG_SHAPE = (
    "one tag at the END (or start) of the bullet: [fixed <sha>] | [fixing → feat/<slug>] | "
    "[deferred → <NOC-REMEDIATE[class] | project-history/roadmaps/… | "
    "MEMORY-reminders | owner-decision> because <reason ≥10 chars>]"
)


def parse_outcome_tag(bullet: str) -> dict[str, Any] | None:
    """Parse the outcome tag of a footer bullet (trailing, else leading).

    Returns {outcome: fixed|fixing|deferred, ref, reason?} or None when the
    bullet carries no valid tag (bare, garbled, destination-less deferral,
    reason < MIN_DEFER_REASON chars).
    """
    text = bullet.strip()
    m = _TAG_TAIL.search(text) or _TAG_HEAD.match(text)
    if not m:
        return None
    body = m.group(1).strip()
    if (f := _FIXED_RE.match(body)):
        return {"outcome": "fixed", "ref": f.group(1)}
    if (f := _FIXING_RE.match(body)):
        return {"outcome": "fixing", "ref": f.group(1)}
    if (f := _DEFERRED_RE.match(body)):
        dest, reason = f.group(1).strip(), f.group(2).strip()
        if len(reason) < MIN_DEFER_REASON or not any(r.search(dest) for r in _DEST_RES):
            return None
        return {"outcome": "deferred", "ref": dest, "reason": reason}
    return None


def untagged_drift_bullets(body: str) -> list[str]:
    """Bullets of a drift-found body lacking a valid outcome tag (sentinels skipped)."""
    bad: list[str] = []
    for ln in body.splitlines():
        m = re.match(r"^\s*(?:[-*]|[0-9]+\.)\s+(.*\S)\s*$", ln)
        if not m:
            continue
        t = m.group(1).strip()
        if t.lower().strip(".").strip("()") in _EMPTY_SENTINELS or t.lower() in _EMPTY_SENTINELS:
            continue
        if parse_outcome_tag(t) is None:
            bad.append(t)
    return bad


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
            "untagged": [],
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

    untagged: list[str] = []
    drift_body = _extract_section(text, "drift-found")
    if drift_body:
        untagged = untagged_drift_bullets(drift_body)

    ok = not missing and not empty and not untagged
    result: dict[str, Any] = {
        "ok": ok,
        "missing": missing,
        "empty": empty,
        "untagged": untagged,
        "warnings": warnings,
    }
    if untagged:
        result["expected_tag_shape"] = TAG_SHAPE
    return result


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.engineer_output_lint",
        description=(
            "Check a dispatched-engineer return text for the mandatory "
            "two-leg footer (drift-found + scoped-improvement). Surfaces "
            "missing sections, empty sections, drift bullets lacking the outcome "
            "tag ([fixed <sha>] | [fixing → feat/<slug>] | [deferred → "
            "<destination> because <reason>]) and format-drift warnings. "
            "Use BEFORE integrating an engineer's work — catches "
            "compliance-gap returns mechanically instead of via social "
            "contract. Returns "
            "{ok, missing, empty, untagged, warnings}. "
            "KB § CONTEXT/PATTERNS/common/engineer-output-linter.md."
        ),
    )
    def _lint(text: str) -> dict:
        return lint_return(text)


__all__ = ["lint_return", "register"]
