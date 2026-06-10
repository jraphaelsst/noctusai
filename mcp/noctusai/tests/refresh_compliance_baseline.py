#!/usr/bin/env python3
"""Regenerate ``tests/compliance_baseline.json`` from the real ``check_all_products()``.

Colocated test-fixture regenerator (NOT a top-level automation script — it
regenerates the committed regression-baseline fixture that the 2 platform-health
gate tests in ``test_compliance.py`` consume; lives next to that fixture by
convention, same as other ``tests/`` helpers).

The baseline encodes Option A (locked 2026-05-18,
``projects/platform-compliance-baseline/PROJECT.md`` §7(A)): the gate is
**regression semantics** — *no NEW high/critical fingerprint vs this committed
baseline* — and the absolute score is informational only.

Run from the repo root::

    mcp/noctusai/.venv/bin/python mcp/noctusai/tests/refresh_compliance_baseline.py

``fingerprint`` / ``ENV_ARTIFACT_PREFIXES`` / ``is_env_artifact`` are imported by
``test_compliance.py`` so the regenerator and the gate compute the live set
identically (single source of truth — no drift between fixture and check).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
# Put `mcp/noctusai/` on the path so `tools.noctus.dev.compliance` resolves as
# a package. Do NOT add `mcp/noctusai/tools/` directly — that lets the in-repo
# `tools/google/` shadow the real `google` SDK for sibling llm tests
# (caught 2026-05-18).
_MCP_DIR = str(_TESTS_DIR.parent)
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

BASELINE_PATH = _TESTS_DIR / "compliance_baseline.json"

# Non-deterministic / environment-artifact issue classes — excluded from BOTH
# the committed baseline and the live comparison so the regression gate cannot
# flap on stamp-lag / wall-clock. Per PROJECT.md §3a P4.
#
# Prefix classes (matched in the issue text's leading ~40 chars):
#   "Seed drift:"  — seed-version stamp lag (pre-commit HEAD vs post-commit SHA)
#   "Archive entry" — archive-staleness (date-relative)
#   "Dispatcher"    — dispatcher-staleness (date-relative)
ENV_ARTIFACT_PREFIXES = (
    "Seed drift:",
    "Archive entry",
    "Dispatcher",
    # "Worktree " — per-worktree uncommitted-state issues depend entirely on which
    # worktrees exist on the current machine. check_drift_fix_compliance emits these
    # under the "Worktree `<path>`" prefix; they are machine-state artifacts, not
    # code regressions. Added 2026-06-02.
    "Worktree ",
)

# Substring classes (matched ANYWHERE in the issue text — the discriminating
# token does NOT lead the message). The seed-version stamp
# `noctusai_{seed,lib}/_version_static.py` is gitignored (written by the
# `stamp-seed-version` hook) and therefore ABSENT in a fresh worktree — a
# worktree-scoped compliance scan would then flag its absence as a false
# `critical` ("`noctusai_seed` has no `_version_static.py` stamp …"). That is
# an environment artifact of WHERE the scan ran, not a code regression, so it
# is excluded both sides of the gate (added 2026-05-25, sibling of the
# "Seed drift:" prefix which covers the stamp-LAG variant).
# "cache STALE" — every Tier-1 keeper-mirror cache (keeper-pattern / agent-context /
# noc-graph / corpus-/memory-/auto-improvement-embeddings) lives in the git-common-dir
# and is UNTRACKED; its source_sha-vs-live-source comparison is machine/timing state
# (the cache is rebuilt per-environment, and a hermetic CI run can observe a transient
# sha skew between the prime step and the check even after --refresh-*-cache). Cache
# freshness has its OWN dedicated `check_*_cache_freshness` keepers (each with a
# regression test, structural ones heal-on-contact), so it is gated there — NOT in the
# code-health regression baseline, where it only produces non-deterministic flap.
# (added 2026-06-02 — auto-improvement cache STALE flapped the CI gate.)
# "auto-loaded memory index" / "is bloated — trim to title" — check_memory_md_index
# fingerprints. MEMORY.md lives OUT-OF-REPO at `~/.claude/projects/<encoded-cwd>/
# memory/MEMORY.md` (Claude-Code per-project store), so these `<memory>` issues are
# machine-LOCAL state that CI never observes (the path is absent there). Leaving them
# un-excluded means `refresh_compliance_baseline.py`, run on any machine with a bloated
# local MEMORY.md, silently bakes machine-specific fingerprints into the committed
# baseline — the same "silent baseline absorption" the regression gate exists to prevent.
# Memory-index discipline has its OWN dedicated keeper (`check_memory_md_index`, gated at
# `validate` + `--check-memory-md-index` with test_memory_md_index.py), so excluding it
# here loses no coverage. (added 2026-06-10.)
ENV_ARTIFACT_SUBSTRINGS = (
    "_version_static.py",
    "cache STALE",
    "auto-loaded memory index must stay tight",
    "is bloated — trim to title",
)


def is_env_artifact(issue_text: str) -> bool:
    head = issue_text.lstrip()[:40]
    if any(p in head for p in ENV_ARTIFACT_PREFIXES):
        return True
    if any(s in issue_text for s in ENV_ARTIFACT_SUBSTRINGS):
        return True
    return False


def fingerprint(issue: dict) -> str:
    """Stable, line-churn-robust identity for one high/critical issue."""
    txt = issue.get("issue", "")
    m = re.search(r"patches our own symbol `([^`]+)`", txt)
    sym = m.group(1) if m else re.sub(r"\d+", "#", txt[:80])
    return (
        f"{issue.get('product', '')}|{issue.get('file', '')}"
        f"|{issue.get('severity', '')}|{sym}"
    )


def live_high_critical_fingerprints() -> tuple[int, list[str]]:
    """(absolute_score, sorted unique high/critical fingerprints minus env artifacts)."""
    from tools.noctus.dev.compliance import check_all_products

    score, issues = check_all_products()
    hc = [
        i
        for i in issues
        if i.get("severity") in ("high", "critical")
        and not is_env_artifact(i.get("issue", ""))
    ]
    return score, sorted({fingerprint(i) for i in hc})


def main() -> int:
    score, fps = live_high_critical_fingerprints()
    existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    payload = {
        "_README": existing["_README"],
        "generated": date.today().isoformat(),
        "generator": existing["generator"],
        "fingerprints": fps,
    }
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Refreshed {BASELINE_PATH.name}: {len(fps)} fingerprints "
          f"(informational absolute score: {score}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
