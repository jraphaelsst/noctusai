"""Regression test for the D1 boot-crash: a plain comma-separated
`APPROVAL_ASSERTION_SECRETS` env value used to raise `SettingsError` at
import time because `approval_assertion_secrets` was declared `list[str]`
with a `mode="before"` `field_validator` — `pydantic-settings` 2.5.2 (this
repo's installed version) JSON-decodes any complex-typed env-sourced field
BEFORE any validator runs, so the plain CSV string was never valid JSON.

Sets the REAL env var via `monkeypatch.setenv` (never monkeypatches our own
`app.config` module) and re-imports `app.config` fresh each time, since the
crash happens at CLASS-INSTANTIATION time (`settings = SeedSettings()` at
module scope) — a cached import would hide the bug entirely.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType

import pytest


@pytest.fixture(autouse=True)
def _restore_app_config_module() -> Iterator[None]:
    """Put the ORIGINAL `app.config` module back after each test.

    Every other module in this suite imported `settings` from the module
    object that was in `sys.modules` at collection time. Leaving a freshly
    re-imported copy there (or no entry at all, after the import-failure
    case) would let later tests read a different `settings` object than the
    code under test holds — an order-dependent result."""
    original = sys.modules.get("app.config")
    yield
    if original is None:
        sys.modules.pop("app.config", None)
    else:
        sys.modules["app.config"] = original


def _fresh_import_app_config() -> ModuleType:
    """Re-import `app.config` from scratch so the module-level
    `settings = SeedSettings()` line re-runs against the current env —
    a plain `import app.config` after a prior test run would return the
    already-imported (and already-instantiated) module from
    `sys.modules`, silently skipping the exact statement this test needs
    to exercise."""
    sys.modules.pop("app.config", None)
    return importlib.import_module("app.config")


class TestApprovalAssertionSecretsCsvBoot:
    def test_plain_csv_value_boots_and_resolves_to_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Module-level `settings = SeedSettings()` (app/config.py) runs
        # DURING this import — the exact statement that crashed at boot
        # pre-fix, so a successful import IS the regression assertion for
        # the "does it boot" half.
        monkeypatch.setenv("APPROVAL_ASSERTION_SECRETS", "k1,k2")
        config = _fresh_import_app_config()
        assert config.settings.approval_assertion_secrets_list == ["k1", "k2"]

    def test_empty_value_resolves_to_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APPROVAL_ASSERTION_SECRETS", "")
        config = _fresh_import_app_config()
        assert config.settings.approval_assertion_secrets_list == []

    def test_json_array_shaped_value_raises_clear_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The validator's ValueError surfaces as pydantic's ValidationError
        # (a ValueError subclass) during the module-level `SeedSettings()`
        # call, i.e. DURING import — so the import itself must be inside the
        # `pytest.raises` block, not a later explicit call.
        monkeypatch.setenv("APPROVAL_ASSERTION_SECRETS", '["k1","k2"]')
        with pytest.raises(ValueError, match="APPROVAL_ASSERTION_SECRETS"):
            _fresh_import_app_config()


class TestTurnDeadlineAndLockTtlSettings:
    """Contract §E.11 "Route order": `_TURN_LOCK_TTL_SECONDS` (now
    `settings.turn_lock_ttl_seconds`) must stay greater than
    `settings.turn_timeout_seconds`. Also pins the user decision
    (2026-09-15) dropping `approval_timeout_seconds` from 900 to 300."""

    def test_defaults(self) -> None:
        from app.config import SeedSettings

        s = SeedSettings()
        assert s.approval_timeout_seconds == 300
        assert s.turn_timeout_seconds == 600
        assert s.turn_lock_ttl_seconds == 900

    def test_lock_ttl_equal_to_turn_timeout_fails_loud(self) -> None:
        from app.config import SeedSettings

        with pytest.raises(ValueError, match="turn_lock_ttl_seconds"):
            SeedSettings(turn_lock_ttl_seconds=600, turn_timeout_seconds=600)

    def test_lock_ttl_below_turn_timeout_fails_loud(self) -> None:
        from app.config import SeedSettings

        with pytest.raises(ValueError, match="turn_lock_ttl_seconds"):
            SeedSettings(turn_lock_ttl_seconds=100, turn_timeout_seconds=600)

    def test_lock_ttl_above_turn_timeout_boots(self) -> None:
        from app.config import SeedSettings

        s = SeedSettings(turn_lock_ttl_seconds=601, turn_timeout_seconds=600)
        assert s.turn_lock_ttl_seconds == 601
