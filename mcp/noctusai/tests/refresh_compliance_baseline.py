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
ENV_ARTIFACT_PREFIXES = ("Seed drift:", "Archive entry", "Dispatcher")


def is_env_artifact(issue_text: str) -> bool:
    head = issue_text.lstrip()[:40]
    return any(p in head for p in ENV_ARTIFACT_PREFIXES)


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
