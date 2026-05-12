"""Regression tests for canonical rate-limit policy constants.

These tests defend against three failure modes:

1. **Deletion** — a constant gets dropped during a refactor, breaking
   every product router that imports it.
2. **Shape drift** — someone tunes a value to a non-slowapi shape
   (e.g. ``"30 rpm"`` or ``"30"``) and ships before any product fails
   at startup.
3. **Silent zeroing** — a constant gets set to ``"0/minute"`` (which
   slowapi accepts but means "block everything"), bricking the
   endpoint.

If you add a new policy to ``rate_limit_policies.py``, add it to
``ALL_POLICIES`` below — the existence test will then cover it.
"""
from __future__ import annotations

import re

import pytest

from noctusai_lib.api import rate_limit_policies as rlp

# Canonical list of every policy constant exposed by the module.
# Keep in sync with `rate_limit_policies.__all__`.
ALL_POLICIES = [
    "DEFAULT_AI_RL",
    "DEFAULT_AUTH_RL",
    "DEFAULT_WEBHOOK_RL",
    "DEFAULT_PORTAL_RL",
]

# slowapi accepts "<int>/<window>" or "<int> per <window>"; we standardize
# on the slash form. Window must be one of the four canonical units.
_SLOWAPI_LIMIT = re.compile(r"^\d+/(second|minute|hour|day)$")


@pytest.mark.parametrize("name", ALL_POLICIES)
def test_policy_constant_exists(name: str) -> None:
    """Every canonical policy is exported from the module."""
    assert hasattr(rlp, name), f"missing policy constant: {name}"


@pytest.mark.parametrize("name", ALL_POLICIES)
def test_policy_constant_is_str(name: str) -> None:
    """Each policy value is a string (slowapi expects str at call time)."""
    value = getattr(rlp, name)
    assert isinstance(value, str), f"{name} must be str, got {type(value).__name__}"


@pytest.mark.parametrize("name", ALL_POLICIES)
def test_policy_constant_shape(name: str) -> None:
    """Each policy matches the slowapi ``"<int>/<window>"`` shape."""
    value = getattr(rlp, name)
    assert _SLOWAPI_LIMIT.match(
        value
    ), f"{name}={value!r} does not match slowapi shape '<int>/<window>'"


@pytest.mark.parametrize("name", ALL_POLICIES)
def test_policy_constant_is_positive(name: str) -> None:
    """Reject ``"0/window"`` — silent-zero would brick endpoints."""
    value = getattr(rlp, name)
    count = int(value.split("/", 1)[0])
    assert count > 0, f"{name} must have a positive count, got {value!r}"


def test_all_export_list_matches_documented_set() -> None:
    """``__all__`` and our ``ALL_POLICIES`` test list stay in sync."""
    assert set(rlp.__all__) == set(ALL_POLICIES), (
        "rate_limit_policies.__all__ drifted from ALL_POLICIES — "
        "update both lists when adding/removing a policy."
    )
