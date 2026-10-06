"""Round 2 — effective-org resolver, license gate, act-as audit tagging.

The load-bearing guarantee (no ``role == 'admin'`` license bypass anywhere): a
superadmin reaches a product he has no home license for ONLY through a LIVE
``act_as_sessions`` row, and the license is then checked against the TARGET org.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth import make_get_current_user_org
from noctusai_lib.api.auth.effective_org import resolve_effective_org
from noctusai_lib.api.auth.session.legacy_bridge import make_trusted_legacy_jwt_resolver
from noctusai_lib.domain import licensing
from noctusai_lib.domain.licensing import (
    FakeLicenseChecker,
    LicenseCheckUnavailable,
    clear_license_cache,
    configure_license_gate,
    org_has_product_license,
)
from noctusai_lib.testing import MockSupabaseClient

HOME = "00000000-0000-0000-0000-00000000000a"
TARGET = "00000000-0000-0000-0000-00000000000b"
ADMIN = "aaaaaaaa-0000-0000-0000-000000000001"
USER = "uuuuuuuu-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _reset_gate():
    configure_license_gate(None)
    clear_license_cache()
    yield
    configure_license_gate(None)
    clear_license_cache()


def _core(*, users, sessions=()):
    sb = MockSupabaseClient()
    sb.set_table_data("noctus_users", list(users))
    sb.set_table_data("act_as_sessions", list(sessions))
    return sb


def _live(superadmin=ADMIN, target=TARGET, sid="s-1"):
    return {"id": sid, "superadmin_id": superadmin, "target_org_id": target,
            "entry_product_slug": "igig", "started_at": "2026-10-06T10:00:00+00:00", "ended_at": None}


ADMIN_ROW = {"id": ADMIN, "org_id": HOME, "org_role": "admin", "role": "admin"}
USER_ROW = {"id": USER, "org_id": HOME, "org_role": "member", "role": "user"}


class TestEffectiveOrg:
    def test_plain_user_resolves_to_home(self):
        eff = resolve_effective_org(_core(users=[USER_ROW]), USER)
        assert (eff.org_id, eff.org_role, eff.acting_session_id) == (HOME, "member", None)

    def test_superadmin_without_session_resolves_to_home(self):
        eff = resolve_effective_org(_core(users=[ADMIN_ROW]), ADMIN)
        assert eff.org_id == HOME and not eff.acting

    def test_superadmin_with_live_session_acts_as_target_owner(self):
        eff = resolve_effective_org(_core(users=[ADMIN_ROW], sessions=[_live()]), ADMIN)
        assert (eff.org_id, eff.org_role, eff.home_org_id) == (TARGET, "owner", HOME)
        assert eff.acting_session_id == "s-1"

    def test_ended_session_does_not_act(self):
        ended = {**_live(), "ended_at": "2026-10-06T11:00:00+00:00"}
        eff = resolve_effective_org(_core(users=[ADMIN_ROW], sessions=[ended]), ADMIN)
        assert eff.org_id == HOME and not eff.acting

    def test_non_superadmin_with_a_session_row_never_acts(self):
        sess = _live(superadmin=USER)
        eff = resolve_effective_org(_core(users=[USER_ROW], sessions=[sess]), USER)
        assert eff.org_id == HOME and not eff.acting

    def test_no_row_is_none(self):
        assert resolve_effective_org(_core(users=[]), USER) is None


def _dep(core, **kw):
    user = SimpleNamespace(id=ADMIN, user_metadata={})

    async def get_current_user(authorization=None):
        return user, "tok"

    return make_get_current_user_org(
        get_current_user, lambda u: None, get_admin_client_fn=lambda: core, **kw
    )


def _gate(checker, slug="igig"):
    configure_license_gate(slug, checker)


class TestLicenseGateInTrustedDep:
    @pytest.mark.asyncio
    async def test_unlicensed_org_is_403_org_sem_licenca(self):
        _gate(FakeLicenseChecker(allow_all=False))
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer x")
        assert exc.value.status_code == 403
        assert exc.value.detail == {
            "detail": "Sua organização não tem acesso a este produto.",
            "code": "org_sem_licenca",
        }

    @pytest.mark.asyncio
    async def test_licensed_org_passes(self):
        _gate(FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}))
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]))
        _u, _t, org_id = await dep(authorization="Bearer x")
        assert org_id == HOME

    @pytest.mark.asyncio
    async def test_core_is_exempt(self):
        _gate(FakeLicenseChecker(allow_all=False), slug="core")
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]))
        assert (await dep(authorization="Bearer x"))[2] == HOME

    @pytest.mark.asyncio
    async def test_no_gate_configured_enforces_nothing(self):
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]))
        assert (await dep(authorization="Bearer x"))[2] == HOME

    @pytest.mark.asyncio
    async def test_enforce_license_false_skips_the_gate(self):
        _gate(FakeLicenseChecker(allow_all=False))
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]), enforce_license=False)
        assert (await dep(authorization="Bearer x"))[2] == HOME

    @pytest.mark.asyncio
    async def test_no_admin_license_bypass_without_act_as(self):
        # A superadmin whose HOME org is unlicensed is blocked like anyone else.
        _gate(FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}))
        dep = _dep(_core(users=[ADMIN_ROW]))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer x")
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "org_sem_licenca"

    @pytest.mark.asyncio
    async def test_act_as_switches_org_and_checks_target_license(self):
        checker = FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")})
        _gate(checker)
        dep = _dep(_core(users=[ADMIN_ROW], sessions=[_live()]))
        _u, _t, org_id = await dep(authorization="Bearer x")
        assert org_id == TARGET
        assert checker.calls == [(TARGET, "igig")]

    @pytest.mark.asyncio
    async def test_act_as_target_without_license_is_403(self):
        _gate(FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}))
        dep = _dep(_core(users=[ADMIN_ROW], sessions=[_live()]))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer x")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_lookup_outage_fails_closed_503(self):
        _gate(FakeLicenseChecker(unavailable=True))
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer x")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_customer_allowed_needs_aceita_clientes(self):
        row = {"id": ADMIN, "org_id": HOME, "org_role": "membro", "role": "user"}
        _gate(FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}))
        dep = _dep(_core(users=[row]), allow_customer=True)
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer x")
        assert exc.value.detail["code"] == "org_sem_licenca"
        _gate(FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}, customer_slugs={"igig"}))
        assert (await dep(authorization="Bearer x"))[2] == HOME


class TestAuditTagging:
    @pytest.mark.asyncio
    async def test_acting_request_is_tagged_and_has_no_org_id(self):
        request = SimpleNamespace(state=SimpleNamespace())
        dep = _dep(_core(users=[ADMIN_ROW], sessions=[_live()]))
        await dep(authorization="Bearer x", request=request)
        actor = request.state.audit_actor
        assert actor.user_id == ADMIN
        assert actor.org_id is None  # the customer's org-scoped audit read never sees it
        assert actor.acting_org_id == TARGET
        assert actor.act_as_session_id == "s-1"

    @pytest.mark.asyncio
    async def test_normal_request_is_not_tagged(self):
        request = SimpleNamespace(state=SimpleNamespace())
        dep = _dep(_core(users=[{**USER_ROW, "id": ADMIN}]))
        await dep(authorization="Bearer x", request=request)
        actor = request.state.audit_actor
        assert actor.org_id == HOME and actor.acting_org_id is None and actor.act_as_session_id is None

    def test_sink_row_carries_act_as_columns_only_when_acting(self):
        from noctusai_lib.api.audit.sink import _to_row
        from noctusai_lib.api.audit.types import AuditActor, AuditEntry

        def entry(actor):
            return AuditEntry(product_slug="igig", method="POST", route_template="/api/x",
                              path_params={}, status=200, actor_kind="user", client_hint="web",
                              actor=actor)

        acting = _to_row(entry(AuditActor(user_id=ADMIN, acting_org_id=TARGET, act_as_session_id="s-1")))
        assert acting["acting_org_id"] == TARGET and acting["act_as_session_id"] == "s-1"
        assert acting["org_id"] is None
        plain = _to_row(entry(AuditActor(user_id=USER, org_id=HOME)))
        assert "act_as_session_id" not in plain and "acting_org_id" not in plain


class TestLegacyBridgeGate:
    @pytest.mark.asyncio
    async def test_bridge_resolves_effective_org_and_enforces_license(self):
        user = SimpleNamespace(id=ADMIN, user_metadata={})

        async def get_current_user(authorization=None):
            return user, "tok"

        core = _core(users=[ADMIN_ROW], sessions=[_live()])
        resolver = make_trusted_legacy_jwt_resolver(get_current_user, lambda: core)
        _gate(FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}))
        ctx = await resolver("jwt")
        assert str(ctx.org_id) == TARGET
        _gate(FakeLicenseChecker(allow_all=False))
        with pytest.raises(HTTPException) as exc:
            await resolver("jwt")
        assert exc.value.status_code == 403


class TestRealLicenseCheck:
    def _client(self, licenses, *, products=({"id": "p1", "slug": "igig", "aceita_clientes": False},)):
        sb = MockSupabaseClient()
        sb.set_table_data("products", list(products))
        sb.set_table_data("licenses", list(licenses))
        return sb

    def test_active_permanent_license(self):
        c = self._client([{"id": "l", "org_id": HOME, "product_id": "p1", "status": "active", "fim": None}])
        assert org_has_product_license(c, HOME, "igig") is True

    def test_expired_license_is_false(self):
        c = self._client([{"id": "l", "org_id": HOME, "product_id": "p1", "status": "active",
                           "fim": "2020-01-01T00:00:00+00:00"}])
        assert org_has_product_license(c, HOME, "igig") is False

    def test_unknown_product_is_false(self):
        assert org_has_product_license(self._client([], products=[]), HOME, "nope") is False

    def test_negative_is_not_cached_positive_is_(self):
        c = self._client([])
        assert org_has_product_license(c, HOME, "igig") is False
        c.set_table_data("licenses", [{"id": "l", "org_id": HOME, "product_id": "p1", "status": "active", "fim": None}])
        assert org_has_product_license(c, HOME, "igig") is True  # a fresh grant works at once
        c.set_table_data("licenses", [])
        assert org_has_product_license(c, HOME, "igig") is True  # positive cached (TTL)
        clear_license_cache()
        assert org_has_product_license(c, HOME, "igig") is False

    def test_db_error_fails_closed(self):
        class Boom:
            def table(self, name):
                raise RuntimeError("db down")

        with pytest.raises(LicenseCheckUnavailable):
            org_has_product_license(Boom(), HOME, "igig")

    def test_factory_is_fake_under_pytest_real_when_forced(self):
        assert isinstance(licensing.make_license_checker(lambda: None), FakeLicenseChecker)
        assert isinstance(
            licensing.make_license_checker(lambda: None, force_real=True), licensing.RealLicenseChecker
        )
