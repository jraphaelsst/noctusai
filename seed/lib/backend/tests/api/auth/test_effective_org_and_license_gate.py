"""Round 2 — effective-org resolver + license gate.

The load-bearing guarantee (no ``role == 'admin'`` license bypass anywhere): the
effective org is ALWAYS the caller's home org (act-as-org was removed
2026-10-07), and the license is checked against it via ``public.licenses`` — the
platform org reaches every product only because it holds every license (core 068).
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


def _core(*, users):
    sb = MockSupabaseClient()
    sb.set_table_data("noctus_users", list(users))
    return sb


ADMIN_ROW = {"id": ADMIN, "org_id": HOME, "org_role": "admin", "role": "admin"}
USER_ROW = {"id": USER, "org_id": HOME, "org_role": "member", "role": "user"}


class TestEffectiveOrg:
    def test_plain_user_resolves_to_home(self):
        eff = resolve_effective_org(_core(users=[USER_ROW]), USER, product_slug=None)
        assert (eff.org_id, eff.org_role) == (HOME, "member")

    def test_superadmin_resolves_to_home_like_anyone(self):
        # noctus_users.role == 'admin' changes nothing: no staff override exists.
        eff = resolve_effective_org(_core(users=[ADMIN_ROW]), ADMIN, product_slug=None)
        assert (eff.org_id, eff.org_role) == (HOME, "admin")

    def test_no_row_is_none(self):
        assert resolve_effective_org(_core(users=[]), USER, product_slug=None) is None


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
    async def test_no_admin_license_bypass(self):
        # A superadmin whose HOME org is unlicensed is blocked like anyone else —
        # holding a license for some OTHER org changes nothing.
        _gate(FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}))
        dep = _dep(_core(users=[ADMIN_ROW]))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer x")
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "org_sem_licenca"

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


class TestAuditActor:
    @pytest.mark.asyncio
    async def test_request_actor_carries_the_home_org(self):
        request = SimpleNamespace(state=SimpleNamespace())
        dep = _dep(_core(users=[ADMIN_ROW]))
        await dep(authorization="Bearer x", request=request)
        actor = request.state.audit_actor
        assert (actor.user_id, actor.org_id) == (ADMIN, HOME)

    def test_sink_row_never_writes_the_historical_act_as_columns(self):
        from noctusai_lib.api.audit.sink import _to_row
        from noctusai_lib.api.audit.types import AuditActor, AuditEntry

        row = _to_row(AuditEntry(product_slug="igig", method="POST", route_template="/api/x",
                                 path_params={}, status=200, actor_kind="user", client_hint="web",
                                 actor=AuditActor(user_id=USER, org_id=HOME)))
        assert row["org_id"] == HOME
        assert "act_as_session_id" not in row and "acting_org_id" not in row


class TestLegacyBridgeGate:
    @pytest.mark.asyncio
    async def test_bridge_resolves_effective_org_and_enforces_license(self):
        user = SimpleNamespace(id=ADMIN, user_metadata={})

        async def get_current_user(authorization=None):
            return user, "tok"

        core = _core(users=[ADMIN_ROW])
        resolver = make_trusted_legacy_jwt_resolver(get_current_user, lambda: core)
        _gate(FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}))
        ctx = await resolver("jwt")
        assert str(ctx.org_id) == HOME
        _gate(FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}))
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


# ---------------------------------------------------------------------------
# Base authenticated dependency — gated by construction (no org lookup route)
# ---------------------------------------------------------------------------

from noctusai_lib.api.auth import make_get_current_user, make_get_current_user_ungated  # noqa: E402


class _AuthClient:
    def __init__(self, uid):
        self.auth = SimpleNamespace(get_user=lambda token: SimpleNamespace(user=SimpleNamespace(id=uid, user_metadata={})))


class CountingCore(MockSupabaseClient):
    lookups = 0

    def table(self, name):
        CountingCore.lookups += 1
        return super().table(name)


def _gated_dep(core, checker, *, uid=USER, slug="igig"):
    configure_license_gate(slug, checker, get_core_client=lambda: core)
    return make_get_current_user(lambda: _AuthClient(uid))


class TestBaseDepGatedByConstruction:
    @pytest.mark.asyncio
    async def test_auth_only_route_is_403_for_unlicensed_org(self):
        dep = _gated_dep(_core(users=[USER_ROW]), FakeLicenseChecker(allow_all=False))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer t")
        assert exc.value.status_code == 403 and exc.value.detail["code"] == "org_sem_licenca"

    @pytest.mark.asyncio
    async def test_licensed_org_passes(self):
        dep = _gated_dep(_core(users=[USER_ROW]), FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}))
        user, token = await dep(authorization="Bearer t")
        assert token == "t" and user.id == USER

    @pytest.mark.asyncio
    async def test_superadmin_is_checked_against_the_home_org_only(self):
        core = _core(users=[ADMIN_ROW])
        dep = _gated_dep(core, FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")}), uid=ADMIN)
        assert (await dep(authorization="Bearer t"))[1] == "t"
        dep = _gated_dep(core, FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}), uid=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer t")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_ungated_variant_is_explicitly_exempt(self):
        configure_license_gate("igig", FakeLicenseChecker(allow_all=False),
                               get_core_client=lambda: _core(users=[USER_ROW]))
        dep = make_get_current_user_ungated(lambda: _AuthClient(USER))
        assert (await dep(authorization="Bearer t"))[1] == "t"

    @pytest.mark.asyncio
    async def test_no_token_is_401_before_any_gate(self):
        dep = _gated_dep(_core(users=[USER_ROW]), FakeLicenseChecker(allow_all=False))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_orgless_user_has_nothing_to_license_and_passes(self):
        dep = _gated_dep(_core(users=[]), FakeLicenseChecker(allow_all=False))
        assert (await dep(authorization="Bearer t"))[1] == "t"

    @pytest.mark.asyncio
    async def test_outage_fails_closed_503(self):
        class Boom:
            def table(self, n):
                raise RuntimeError("db down")

        configure_license_gate("igig", FakeLicenseChecker(allow_all=False), get_core_client=lambda: Boom())
        dep = make_get_current_user(lambda: _AuthClient(USER))
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer t")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_core_and_permissive_fake_do_zero_lookups(self):
        CountingCore.lookups = 0
        core = CountingCore()
        for checker, slug in ((FakeLicenseChecker(allow_all=False), "core"), (FakeLicenseChecker(), "igig")):
            dep = _gated_dep(core, checker, slug=slug)
            await dep(authorization="Bearer t")
        assert CountingCore.lookups == 0

    @pytest.mark.asyncio
    async def test_org_factory_unwraps_so_the_license_is_checked_once(self):
        checker = FakeLicenseChecker(allow_all=False, licensed={(HOME, "igig")})
        core = _core(users=[{**USER_ROW, "id": USER}])
        gated = _gated_dep(core, checker)
        assert gated.ungated is not gated
        dep = make_get_current_user_org(gated, lambda u: None, get_admin_client_fn=lambda: core)
        await dep(authorization="Bearer t")
        assert checker.calls == [(HOME, "igig")]
