"""`ProductDependencies.get_current_user_and_fetch` -- a read-only handler's query runs alongside
the license gate instead of after it (the bell's two endpoints, polled on every page).

Pins: the gate's verdict wins (403 raised, the fetched data never returned to a refused caller);
a licensed caller gets the data; the two overlap (one round trip of wall time, not two).
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate
from noctusai_lib.testing import MockSupabaseClient
from noctusai_seed.dependencies import ProductDependencies

USER = "bbbbbbbb-0000-0000-0000-000000000001"
ORG = "00000000-0000-0000-0000-00000000000a"
SLUG = "igig"
HOP = 0.15


@pytest.fixture(autouse=True)
def _no_gate():
    configure_license_gate(None)
    yield
    configure_license_gate(None)


class _SlowCore:
    def __init__(self):
        self._inner = MockSupabaseClient()
        self._inner.set_table_data("noctus_users", [{"id": USER, "org_id": ORG, "org_role": "owner", "role": "user"}])

    def table(self, name):
        time.sleep(HOP)
        return self._inner.table(name)


class _Db:
    def __init__(self, core):
        self._core = core

    def get_client(self):
        return SimpleNamespace(auth=SimpleNamespace(get_user=lambda _t: SimpleNamespace(user=SimpleNamespace(id=USER))))

    def get_core_client(self):
        return self._core


def _deps(*, licensed: bool):
    core = _SlowCore()
    checker = FakeLicenseChecker(allow_all=False, licensed={(ORG, SLUG)} if licensed else set())
    configure_license_gate(SLUG, checker, get_core_client=lambda: core)
    return ProductDependencies(_Db(core))


def _slow_fetch(user):
    time.sleep(HOP)
    return {"for": user.id}


@pytest.mark.asyncio
async def test_licensed_caller_gets_the_data_in_one_round_trip_of_wall_time():
    deps = _deps(licensed=True)
    t0 = time.monotonic()
    user, token, data = await deps.get_current_user_and_fetch("Bearer t", _slow_fetch)
    elapsed = time.monotonic() - t0
    assert user.id == USER and token == "t" and data == {"for": USER}
    assert elapsed < 1.8 * HOP  # gate (profile read) then fetch would be 2 hops


@pytest.mark.asyncio
async def test_refused_caller_gets_the_403_never_the_data():
    deps = _deps(licensed=False)
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user_and_fetch("Bearer t", _slow_fetch)
    assert exc.value.status_code == 403 and exc.value.detail["code"] == "org_sem_licenca"


@pytest.mark.asyncio
async def test_gate_verdict_wins_over_a_failing_fetch():
    deps = _deps(licensed=False)

    def boom(_user):
        raise RuntimeError("fetch down")

    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user_and_fetch("Bearer t", boom)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_token_is_401_before_anything_runs():
    deps = _deps(licensed=True)
    ran = []
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user_and_fetch(None, lambda u: ran.append(u))
    assert exc.value.status_code == 401 and ran == []
