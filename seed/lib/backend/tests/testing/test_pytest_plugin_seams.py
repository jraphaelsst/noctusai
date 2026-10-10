"""The seed pytest plugin declares the hermetic seams BEFORE initial conftests
load (2026-10-10: module conftests importing app.* at import time built the
rate limiter on a shared Redis before pytest_configure ran)."""
from __future__ import annotations

from noctusai_lib.api.rate_limit import MEMORY_ONLY_VAR
from noctusai_lib.config.settings import NO_ENV_FILE_VAR
from noctusai_lib.testing import pytest_plugin


def test_declare_hermetic_seams_sets_both(monkeypatch):
    monkeypatch.delenv(NO_ENV_FILE_VAR, raising=False)
    monkeypatch.delenv(MEMORY_ONLY_VAR, raising=False)
    pytest_plugin.declare_hermetic_seams()
    import os

    assert os.environ[NO_ENV_FILE_VAR] == "1" and os.environ[MEMORY_ONLY_VAR] == "1"


def test_the_early_hook_runs_first():
    assert pytest_plugin.pytest_load_initial_conftests.pytest_impl["tryfirst"] is True
