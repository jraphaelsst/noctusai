"""Wall time of the effective-org resolve: the reads that need only (user_id, product_slug) are
issued WITH the ``noctus_users`` row read, not after it (2026-10-23 live walk: each Supabase call
~40 ms from the VPS, the shell endpoints spent their time on serial hops, not on queueing).

Pins: the reads overlap (one round trip of wall time, not two / four); a read the branch that
runs does not consume can never fail the request; a read it does consume still fails closed with
its own error; the answers are unchanged (the semantic suites in this directory cover those).
"""
from __future__ import annotations

import base64
import json
import threading
import time

import pytest

from noctusai_lib.api.auth._blocking import run_parallel
from noctusai_lib.api.auth.effective_org import platform_staff_role, resolve_effective_org, staff_role_of
from noctusai_lib.api.auth.org_selection import FakeOrgSelectionStore
from noctusai_lib.domain.licensing import FakeLicenseChecker
from noctusai_lib.testing import MockSupabaseClient
from noctusai_lib.testing._schema_cache import get_foreign_key_map, get_schema_map

ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"
USER = "bbbbbbbb-0000-0000-0000-000000000001"
SID = "11111111-1111-1111-1111-111111111111"
SLUG = "igig"
HOP = 0.15


@pytest.fixture(autouse=True, scope="module")
def _mock_caches_built():
    """The mock parses the migrations (columns, foreign keys) on first use; build both up front
    so that one-off cost never lands inside a timed request."""
    get_schema_map()
    get_foreign_key_map()


def _tok(sub, **claims):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, **claims})}.s"


class _SlowCore:
    """A core client whose every ``.table()`` costs one simulated round trip."""

    def __init__(self, inner):
        self._inner = inner

    def table(self, name):
        time.sleep(HOP)
        return self._inner.table(name)


class _SlowStore(FakeOrgSelectionStore):
    """Each per-request read costs one round trip; ``fail`` names a read that raises."""

    fail: str = ""

    def _hop(self, name):
        time.sleep(HOP)
        if self.fail == name:
            raise RuntimeError(f"{name} down")

    def memberships(self, user_id):
        self._hop("memberships")
        return super().memberships(user_id)

    def blocked_orgs(self, user_id, product_slug):
        self._hop("blocked_orgs")
        return super().blocked_orgs(user_id, product_slug)

    def live(self, user_id, product_slug):
        self._hop("live")
        return super().live(user_id, product_slug)


def _core(*, role="user", org_role="owner", platform=False):
    c = MockSupabaseClient()
    c.set_table_data("noctus_users", [{"id": USER, "org_id": ORG_A, "org_role": org_role, "role": role}])
    c.set_table_data("organizations", [
        {"id": ORG_A, "nome": "A", "is_platform": platform},
        {"id": ORG_B, "nome": "B", "is_platform": False},
    ])
    return _SlowCore(c)


def _store(*, ready=True, fail=""):
    s = _SlowStore(
        ready={SLUG} if ready else set(), mfa_optional={SLUG},
        licensed={(ORG_A, SLUG), (ORG_B, SLUG)}, members={USER: {ORG_A: "owner"}},
    )
    s.fail = fail
    return s


def _resolve(core, store, **kw):
    return resolve_effective_org(
        core, USER, product_slug=SLUG, token=_tok(USER, session_id=SID, aal="aal1"),
        selection_store=store, license_checker=FakeLicenseChecker(allow_all=True), **kw,
    )


def _timed(fn):
    t0 = time.monotonic()
    out = fn()
    return out, time.monotonic() - t0


class TestReadsOverlapTheProfileRead:
    def test_not_ready_product_reads_blocks_with_the_profile(self):
        eff, elapsed = _timed(lambda: _resolve(_core(), _store(ready=False)))
        assert eff.org_id == ORG_A
        assert elapsed < 1.8 * HOP  # serial: profile then blocks = 2 hops

    def test_member_on_ready_product_is_one_round_trip_not_two(self):
        eff, elapsed = _timed(lambda: _resolve(_core(), _store()))
        assert eff.org_id == ORG_A and eff.org_role == "owner"
        assert elapsed < 1.8 * HOP  # serial: profile, then memberships || blocks || live = 2 hops


class TestAPrefetchedReadFailsOnlyTheBranchThatUsesIt:
    def test_staff_never_reads_memberships_so_its_outage_cannot_fail_staff(self):
        core = _core(role="admin", org_role="owner", platform=True)
        eff = _resolve(core, _store(fail="memberships"), require_selection=False)
        assert eff.is_staff and eff.org_id == ORG_A

    def test_member_needs_blocks_so_their_outage_fails_closed_with_its_own_error(self):
        with pytest.raises(RuntimeError, match="blocked_orgs down"):
            _resolve(_core(), _store(fail="blocked_orgs"))

    def test_not_ready_product_still_fails_closed_on_a_blocks_outage(self):
        with pytest.raises(RuntimeError, match="blocked_orgs down"):
            _resolve(_core(), _store(ready=False, fail="blocked_orgs"))

    def test_no_profile_row_is_still_no_org(self):
        c = MockSupabaseClient()
        c.set_table_data("noctus_users", [])
        assert _resolve(_SlowCore(c), _store(fail="memberships")) is None


class TestStaffRuleReadsTheHomeOrgWithTheProfile:
    def test_platform_staff_role_is_one_round_trip(self):
        role, elapsed = _timed(lambda: platform_staff_role(_core(role="admin", platform=True), USER))
        assert role == "owner"
        assert elapsed < 1.8 * HOP  # serial: profile then the home org's is_platform = 2 hops

    def test_staff_resolve_on_ready_product_is_one_round_trip(self):
        core = _core(role="admin", platform=True)
        eff, elapsed = _timed(lambda: _resolve(core, _store(), require_selection=False))
        assert eff.is_staff and eff.org_id == ORG_A
        assert elapsed < 1.8 * HOP

    def test_admin_profile_in_a_non_platform_home_is_not_staff(self):
        assert platform_staff_role(_core(role="admin", platform=False), USER) is None

    def test_a_row_without_the_home_org_embed_is_never_staff(self):
        row = {"org_id": ORG_A, "org_role": "owner", "role": "admin"}
        assert staff_role_of(row) is None
        assert staff_role_of({**row, "organizations": None}) is None
        assert staff_role_of({**row, "organizations": {"is_platform": True}}) == "owner"


class TestRunParallelRunsTheFirstThunkOnTheCaller:
    def test_first_thunk_runs_on_the_calling_thread_the_rest_in_the_pool(self):
        me = threading.get_ident()
        first, second = run_parallel(threading.get_ident, threading.get_ident)
        assert first == me and second != me

    def test_nested_fan_out_from_many_callers_does_not_starve_the_pool(self):
        # 40 callers (> the 24-worker pool), each fanning out a thunk that fans out again.
        def inner():
            return sum(run_parallel(lambda: 1, lambda: 1, lambda: 1))

        def outer():
            return run_parallel(inner, lambda: 0)[0]

        results: list[int] = []
        threads = [threading.Thread(target=lambda: results.append(outer())) for _ in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert results == [3] * 40
