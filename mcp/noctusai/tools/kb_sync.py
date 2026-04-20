"""
kb_sync tool — verify that CLAUDE.md pointers resolve and KB/INDEX.md is complete.

Thin wrapper around scripts/verify-kb-sync.sh so the same check is callable from:
  - bash:  bash scripts/verify-kb-sync.sh
  - CLI:   python mcp/noctusai/cli.py --verify-kb-sync
  - heal:  automatically run as part of the heal loop (future wiring)
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TypedDict

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "verify-kb-sync.sh"


class KBSyncResult(TypedDict):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def verify_kb_sync() -> KBSyncResult:
    """Run the KB sync verifier. Returns structured result."""
    if not SCRIPT.exists():
        return {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": f"Script not found: {SCRIPT}",
        }

    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
