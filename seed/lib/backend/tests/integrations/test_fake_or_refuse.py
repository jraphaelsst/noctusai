"""Tests for `noctusai_lib.integrations.fake_or_refuse.resolve_fake_or_refuse`.

The contract: configured → Real (Fake never built); unconfigured → the
caller's declared state; the Fake ONLY under an explicit `allow_fake=True`.
Builders are plain recording callables — no patching.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse


class _Recorder:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


class _Refused(Exception):
    pass


def _refuse():
    raise _Refused("not configured")


def test_configured_yields_real_and_never_builds_fake():
    real, fake = _Recorder("real"), _Recorder("fake")
    out = resolve_fake_or_refuse(
        configured=True, build_real=real, build_fake=fake, allow_fake=True, unconfigured=_refuse,
    )
    assert out == "real"
    assert (real.calls, fake.calls) == (1, 0)


def test_unconfigured_without_opt_in_returns_declared_state_not_fake():
    real, fake, state = _Recorder("real"), _Recorder("fake"), _Recorder(None)
    out = resolve_fake_or_refuse(
        configured=False, build_real=real, build_fake=fake, unconfigured=state,
    )
    assert out is None
    assert (real.calls, fake.calls, state.calls) == (0, 0, 1)


def test_unconfigured_without_opt_in_can_refuse():
    fake = _Recorder("fake")
    with pytest.raises(_Refused):
        resolve_fake_or_refuse(
            configured=False, build_real=_Recorder("real"), build_fake=fake,
            allow_fake=False, unconfigured=_refuse,
        )
    assert fake.calls == 0


def test_unconfigured_with_explicit_opt_in_yields_fake():
    fake, state = _Recorder("fake"), _Recorder(None)
    out = resolve_fake_or_refuse(
        configured=False, build_real=_Recorder("real"), build_fake=fake,
        allow_fake=True, unconfigured=state,
    )
    assert out == "fake"
    assert state.calls == 0


def test_opt_in_without_fake_builder_is_loud():
    with pytest.raises(ValueError, match="build_fake"):
        resolve_fake_or_refuse(
            configured=False, build_real=_Recorder("real"), allow_fake=True,
            unconfigured=_Recorder(None),
        )
