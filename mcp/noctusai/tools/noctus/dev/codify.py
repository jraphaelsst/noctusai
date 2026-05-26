"""codify_log — the s-stage-enforcing wrapper around auto_improvement.log_entry.

The codification pipeline (`s1 emergent → s2 memory → s3 codified → s4 keeper`)
is methodology infrastructure. Direct ndjson writes have repeatedly slipped past
the stage discipline (5× backfill on 2026-05-26 alone — agents ship s4 keepers
without logging the s3 codification event). This helper enforces the
progression so the meta-keeper `check_codification_pipeline_health` stays fed.

Invariants enforced:

- `s4-keeper` event for `target T` REQUIRES a preceding `s3-codified` event
  for the same target (in the ledger, within an optional lookback window).
- `s3-codified` event for `target T` REQUIRES a preceding `s1-emergent` OR
  `s2-memory` event for the same target.
- `s2-memory` and `s1-emergent` are entry points — no prerequisite check.

The `force=True` escape hatch bypasses the prerequisite check for legitimate
out-of-order writes (backfill, retroactive codification, methodology re-baseline).
The force flag is captured in the entry's `source_ref` for audit.

KB § PATTERNS/common/dispatch-with-project-and-notes.md §Tooling.
KB § PATTERNS/common/methodology-codification-pipeline.md (the s-stage contract).
KB § PATTERNS/common/scoped-auto-improvement.md (the ledger sibling).
"""
from __future__ import annotations

import json
from pathlib import Path

from .auto_improvement import (
    LEDGER_PATH,
    STATUSES,
    log_entry,
)


# Canonical s-stage names. The set is ordered for clarity.
S1_EMERGENT = "s1-emergent"
S2_MEMORY = "s2-memory"
S3_CODIFIED = "s3-codified"
S3_KB_LEGACY = "s3-kb"  # legacy alias accepted on reads, never emitted by codify_log
S4_KEEPER = "s4-keeper"

# Stages that count as "s3 satisfied" for s4 prerequisite check (both canonical
# + legacy alias). Treats them as equivalent — the historical drift is invisible
# to downstream consumers.
_S3_SATISFIED = frozenset({S3_CODIFIED, S3_KB_LEGACY})

# Stages that count as prerequisite for s3.
_S3_PREREQUISITES = frozenset({S1_EMERGENT, S2_MEMORY})

# Stages valid for codify_log emission. `s3-kb` is INTENTIONALLY excluded —
# new writes use canonical `s3-codified`. Pre-existing `s3-kb` entries in the
# ledger remain valid (read-side compatibility).
VALID_STAGES = frozenset({S1_EMERGENT, S2_MEMORY, S3_CODIFIED, S4_KEEPER})


def _ledger_entries_for_target(
    target: str, ledger_path: Path = LEDGER_PATH,
) -> list[dict]:
    """Read every ledger entry for ``target`` (in chronological order)."""
    if not ledger_path.exists():
        return []
    entries: list[dict] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("target") == target:
            entries.append(entry)
    return entries


def _has_prereq_status(
    target: str,
    required_statuses: frozenset[str],
    ledger_path: Path = LEDGER_PATH,
) -> bool:
    """Return True if any ledger entry for ``target`` has status in
    ``required_statuses``."""
    for entry in _ledger_entries_for_target(target, ledger_path=ledger_path):
        if entry.get("status") in required_statuses:
            return True
    return False


def codify_log(
    *,
    stage: str,
    target: str,
    description: str,
    agent: str = "tech-lead",
    scope: str = "broad",
    kind: str = "improvement",
    source_ref: str | None = None,
    force: bool = False,
    ledger_path: Path = LEDGER_PATH,
) -> dict:
    """Log a codification event with s-stage progression enforcement.

    Args:
        stage: One of ``s1-emergent`` · ``s2-memory`` · ``s3-codified`` · ``s4-keeper``.
            ``s3-kb`` (legacy alias) is NOT accepted on emit — write
            ``s3-codified`` and let read-side normalize.
        target: What got codified (KB path / CLAUDE.md / agent / keeper name /
            file path). Used as the prerequisite-lookup key.
        description: What + why + sibling refs. Min 20 chars (enforced).
        agent: Who logged this (default ``tech-lead``).
        scope: ``scoped`` (engineer-slice) | ``broad`` (cross-cutting). Default ``broad``.
        kind: ``improvement`` | ``drift``. Default ``improvement``.
        source_ref: Provenance — commit SHA / session ID / project slug.
            When ``force=True`` and source_ref is None, the entry is tagged
            ``force:<original>`` for audit.
        force: Bypass the prerequisite check. Use for backfill, retroactive
            codification, methodology re-baseline. The force flag is recorded
            in source_ref.
        ledger_path: Override for tests.

    Returns:
        ``{ok, entry, ledger_path}`` on success (mirrors auto_improvement.log_entry).
        ``{ok: False, error, ...}`` on validation failure (invalid stage, empty
        target, short description, prerequisite missing without force).

    Raises:
        Nothing — errors return a structured dict for caller dispatch.

    Examples:
        # s3 with preceding s2
        >>> codify_log(stage="s3-codified", target="KB § PATTERNS/x.md",
        ...            description="Codified the X pattern after s2 memory landed.")
        {"ok": True, ...}

        # s4 without s3 → blocked
        >>> codify_log(stage="s4-keeper", target="never-codified.py",
        ...            description="...")
        {"ok": False, "error": "s4-keeper for target 'never-codified.py' has no preceding s3-codified entry; pass force=True with rationale to override."}

        # backfill via force
        >>> codify_log(stage="s3-codified", target="prior-ship.md",
        ...            description="Backfill — s4 shipped earlier without explicit s3.",
        ...            force=True, source_ref="session:backfill-2026-05-26")
        {"ok": True, ...}
    """
    # Stage validation (emit-side).
    if stage not in VALID_STAGES:
        return {
            "ok": False,
            "error": (
                f"invalid stage {stage!r}; valid: {sorted(VALID_STAGES)}. "
                f"(Note: 's3-kb' is a legacy alias accepted on READ but not "
                "emitted by codify_log — write 's3-codified' for new entries.)"
            ),
        }

    # Target + description validation.
    if not target or not target.strip():
        return {"ok": False, "error": "target cannot be empty"}
    if not description or len(description.strip()) < 20:
        return {
            "ok": False,
            "error": (
                "description must be >= 20 chars (capture what + why + sibling refs); "
                f"got {len(description.strip())} chars"
            ),
        }

    # s-stage progression check (skip-able via force=True).
    if not force:
        if stage == S4_KEEPER:
            if not _has_prereq_status(target, _S3_SATISFIED, ledger_path=ledger_path):
                return {
                    "ok": False,
                    "error": (
                        f"s4-keeper for target {target!r} has no preceding "
                        "s3-codified entry; pass force=True with rationale to "
                        "override (backfill / retroactive codification). "
                        "KB § PATTERNS/common/methodology-codification-pipeline.md."
                    ),
                    "missing_prereq": "s3-codified",
                }
        elif stage == S3_CODIFIED:
            if not _has_prereq_status(target, _S3_PREREQUISITES, ledger_path=ledger_path):
                return {
                    "ok": False,
                    "error": (
                        f"s3-codified for target {target!r} has no preceding "
                        "s1-emergent OR s2-memory entry; pass force=True with "
                        "rationale to override (the same-commit s2→s3→s4 "
                        "compression pattern is common in this codebase — when "
                        "you legitimately compress, use force=True). "
                        "KB § PATTERNS/common/methodology-codification-pipeline.md."
                    ),
                    "missing_prereq": "s1-emergent | s2-memory",
                }

    # Tag force in source_ref for audit.
    if force:
        force_tag = "force:" + (source_ref or "no-source-ref")
        effective_source_ref = force_tag
    else:
        effective_source_ref = source_ref

    # Override the ledger path for testing (auto_improvement.log_entry uses
    # module-level LEDGER_PATH directly).
    if ledger_path != LEDGER_PATH:
        # Monkeypatch the import-time constant for this call.
        import tools.noctus.dev.auto_improvement as ai_mod  # noqa: PLC0415
        original = ai_mod.LEDGER_PATH
        ai_mod.LEDGER_PATH = ledger_path
        try:
            result = log_entry(
                scope=scope,
                kind=kind,
                target=target,
                description=description,
                agent=agent,
                status=stage,
                source_ref=effective_source_ref,
            )
        finally:
            ai_mod.LEDGER_PATH = original
        return result

    return log_entry(
        scope=scope,
        kind=kind,
        target=target,
        description=description,
        agent=agent,
        status=stage,
        source_ref=effective_source_ref,
    )


def register(server) -> None:
    """Register the noctus.dev.codify_log MCP tool."""

    @server.tool(
        name="noctus.dev.codify_log",
        description=(
            "Log a codification event with s-stage progression enforcement. "
            "stage = 's1-emergent' | 's2-memory' | 's3-codified' | 's4-keeper'. "
            "Enforces invariants: s4 requires preceding s3 for same target; "
            "s3 requires preceding s1 OR s2. Pass force=True with rationale "
            "(captured in source_ref) for backfill / retroactive codification "
            "/ legitimate s2→s3→s4 same-commit compression. Solves the bypass-"
            "the-stages slip that needed 5× manual backfill on 2026-05-26. "
            "KB § PATTERNS/common/methodology-codification-pipeline.md."
        ),
    )
    def _codify_log(
        stage: str,
        target: str,
        description: str,
        agent: str = "tech-lead",
        scope: str = "broad",
        kind: str = "improvement",
        source_ref: str | None = None,
        force: bool = False,
    ) -> dict:
        return codify_log(
            stage=stage,
            target=target,
            description=description,
            agent=agent,
            scope=scope,
            kind=kind,
            source_ref=source_ref,
            force=force,
        )
