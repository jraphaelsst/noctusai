"""Tests for `noctus.dev.d4sign_contract_verify` — the MCP wrapper around
`noctusai_lib.testing.d4sign_harness.run_contract_harness`. Zero network:
`mode="sandbox"` drives the in-process `D4SignSandbox`; `mode="real"`
without credentials proves the honest `not_configured` contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

# This worktree's `seed/lib/backend` must resolve BEFORE any editable
# `noctusai-lib` install pointing at a different worktree (the primary), the
# same worktree-shadowing concern `noctus.dev.pytest`'s `worktree_path` param
# exists for — `d4sign_sandbox.py`/`d4sign_harness.py` are new modules this
# slice adds and won't exist anywhere else.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "seed" / "lib" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import d4sign_contract_verify as V  # noqa: E402


def test_sandbox_mode_returns_ok_true() -> None:
    result = V.d4sign_contract_verify(mode="sandbox")

    assert result["ok"] is True
    assert result["mode"] == "sandbox"
    assert result["all_verified_live"] is False
    assert len(result["markers"]) == 6
    assert all(
        m["status"] not in ("verified_live", "contradicted_live")
        for m in result["markers"]
    )


def test_real_mode_without_credentials_is_honestly_not_ok() -> None:
    # No env vars / org_settings configured in this test process — the
    # resolver falls straight through to "missing everything".
    import os

    for key in ("D4SIGN_API_TOKEN", "D4SIGN_CRYPT_KEY", "D4SIGN_SAFE_UUID"):
        os.environ.pop(key, None)

    result = V.d4sign_contract_verify(mode="real")

    assert result["ok"] is False
    assert result["mode"] == "real"
    assert len(result["not_configured"]) == 6
    assert result["all_verified_live"] is False


def test_invalid_mode_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        V.d4sign_contract_verify(mode="bogus")
