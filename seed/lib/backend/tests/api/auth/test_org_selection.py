"""Org picker building blocks: session-claims reader, selection store (Real over a Mock
client + Fake), the resolver's non-staff/ineligible paths, audit tagging, SQL canon."""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from noctusai_lib.api.audit.sink import _to_row
from noctusai_lib.api.audit.types import AuditActor, AuditEntry
from noctusai_lib.api.auth.effective_org import resolve_effective_org
from noctusai_lib.api.auth.mfa.aal import read_session_claims
from noctusai_lib.api.auth.org_selection import (
    FakeOrgSelectionStore,
    OrgSelectionError,
    RealOrgSelectionStore,
    make_org_selection_store,
)
from noctusai_lib.domain.licensing import FakeLicenseChecker
from noctusai_lib.domain.sql_templates import ORG_PICKER_FUNCTION_NAMES, org_identity_function_sql
from noctusai_lib.testing import MockSupabaseClient

HOME = "00000000-0000-0000-0000-00000000000a"
TARGET = "00000000-0000-0000-0000-00000000000b"
STAFF = "aaaaaaaa-0000-0000-0000-000000000001"
SID = "11111111-1111-1111-1111-111111111111"
PID = "99999999-0000-0000-0000-000000000009"


def _tok(sub, **claims):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, **claims})}.s"


class TestReadSessionClaims:
    def test_bound_token_yields_session_and_aal(self):
        assert read_session_claims(_tok(STAFF, session_id=SID, aal="aal2"), user_id=STAFF) == (SID, "aal2")

    def test_sub_mismatch_is_unbound(self):
        assert read_session_claims(_tok("other", session_id=SID, aal="aal2"), user_id=STAFF) == (None, "aal1")

    def test_garbage_or_cookie_session_id_is_unbound(self):
        assert read_session_claims("not-a-jwt", user_id=STAFF) == (None, "aal1")
        assert read_session_claims(None, user_id=STAFF) == (None, "aal1")
        assert read_session_claims(_tok(STAFF, session_id=SID), user_id=None) == (None, "aal1")

    def test_missing_aal_is_never_aal2(self):
        assert read_session_claims(_tok(STAFF, session_id=SID), user_id=STAFF) == (SID, "aal1")


class _RpcClient:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class _Q:
            def execute(self_inner):
                if outer.error:
                    raise outer.error
                return SimpleNamespace(data=outer.result)

        return _Q()


class TestRealStore:
    def test_set_maps_rpc_errors_to_codes(self):
        for code in ("not_platform_staff", "target_not_licensed", "product_not_ready"):
            store = RealOrgSelectionStore(lambda c=code: _RpcClient(error=RuntimeError(f"platform_org_selection:{c}")))
            with pytest.raises(OrgSelectionError) as exc:
                store.set(STAFF, "igig", TARGET, SID)
            assert exc.value.code == code

    def test_set_unknown_error_propagates(self):
        store = RealOrgSelectionStore(lambda: _RpcClient(error=RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            store.set(STAFF, "igig", TARGET, SID)

    def test_set_and_end_call_the_rpcs_with_named_params(self):
        client = _RpcClient(result="sel-1")
        store = RealOrgSelectionStore(lambda: client)
        assert store.set(STAFF, "igig", TARGET, SID) == "sel-1"
        assert client.calls[0] == ("platform_org_selection_set", {
            "p_user_id": STAFF, "p_product_slug": "igig",
            "p_target_org_id": TARGET, "p_auth_session_id": SID})
        client.result = 2
        assert store.end(STAFF, None, "logout") == 2
        assert client.calls[1] == ("platform_org_selection_end", {"p_user_id": STAFF, "p_reason": "logout"})

    def test_requires_mfa_reads_the_product_flag_and_fails_closed(self):
        core = MockSupabaseClient()
        core.set_table_data("products", [
            {"id": "p1", "slug": "off", "org_picker_ready": True, "db_schema": "off", "org_picker_requires_mfa": False},
            {"id": "p2", "slug": "on", "org_picker_ready": True, "db_schema": "on", "org_picker_requires_mfa": True},
            {"id": "p3", "slug": "pre073", "org_picker_ready": True, "db_schema": "pre073"},
            {"id": "p4", "slug": "nulled", "org_picker_ready": True, "db_schema": "nulled", "org_picker_requires_mfa": None},
        ])
        store = RealOrgSelectionStore(lambda: core)
        assert store.requires_mfa("off") is False
        assert store.requires_mfa("on") is True
        assert store.requires_mfa("pre073") is True  # column absent: the 2026-10-08 rule
        assert store.requires_mfa("nulled") is True
        assert store.requires_mfa("missing") is True

    def test_product_ready_and_live_and_licensed_orgs(self):
        core = MockSupabaseClient()
        core.set_table_data("products", [{"id": PID, "slug": "igig", "org_picker_ready": True, "db_schema": "igig"}])
        core.set_table_data("platform_org_selections", [
            {"id": "s1", "user_id": STAFF, "product_id": PID, "target_org_id": TARGET,
             "home_org_id": HOME, "auth_session_id": SID, "ended_at": None},
            {"id": "s0", "user_id": STAFF, "product_id": PID, "target_org_id": HOME,
             "home_org_id": HOME, "auth_session_id": SID, "ended_at": "2026-01-01T00:00:00+00:00"},
        ])
        core.set_table_data("licenses", [
            {"id": "l1", "org_id": TARGET, "product_id": PID, "status": "active", "fim": None},
            {"id": "l2", "org_id": HOME, "product_id": PID, "status": "active", "fim": "2001-01-01T00:00:00+00:00"},
        ])
        core.set_table_data("organizations", [{"id": TARGET, "nome": "Cliente"}, {"id": HOME, "nome": "Casa"}])
        store = RealOrgSelectionStore(lambda: core)
        assert store.product_ready("igig") is True
        assert store.product_ready("nope") is False
        live = store.live(STAFF, "igig")
        assert (live.id, live.target_org_id, live.auth_session_id) == ("s1", TARGET, SID)
        assert store.licensed_orgs("igig") == [{"id": TARGET, "nome": "Cliente"}]


class TestFakeStoreMirrorsTheRpcErrors:
    def test_errors_and_replacement_tags(self):
        s = FakeOrgSelectionStore(ready={"igig"}, staff={STAFF}, licensed={(TARGET, "igig")})
        with pytest.raises(OrgSelectionError) as e1:
            s.set("someone", "igig", TARGET, SID)
        assert e1.value.code == "not_platform_staff"
        with pytest.raises(OrgSelectionError) as e2:
            s.set(STAFF, "other", TARGET, SID)
        assert e2.value.code == "product_not_ready"
        with pytest.raises(OrgSelectionError) as e3:
            s.set(STAFF, "igig", HOME, SID)
        assert e3.value.code == "target_not_licensed"
        s.set(STAFF, "igig", TARGET, SID)
        s.set(STAFF, "igig", TARGET, "other-session")
        assert [r["ended_by"] for r in s.rows] == ["new_session", None]

    def test_factory_is_fake_under_pytest_real_when_forced(self):
        assert isinstance(make_org_selection_store(lambda: None), FakeOrgSelectionStore)
        assert isinstance(make_org_selection_store(lambda: None, force_real=True), RealOrgSelectionStore)


class TestResolverIneligiblePaths:
    def _core(self, row):
        c = MockSupabaseClient()
        c.set_table_data("noctus_users", [row])
        c.set_table_data("organizations", [{"id": HOME, "nome": "Casa", "is_platform": True}])
        return c

    def _store(self):
        return FakeOrgSelectionStore(ready={"igig"}, staff={STAFF}, licensed={(TARGET, "igig")},
                                     home_orgs={STAFF: HOME})

    def test_core_and_no_token_and_no_store_resolve_home(self):
        row = {"id": STAFF, "org_id": HOME, "org_role": "owner", "role": "admin"}
        store = self._store()
        store.set(STAFF, "igig", TARGET, SID)
        tok = _tok(STAFF, session_id=SID, aal="aal2")
        for slug, token, st in (("core", tok, store), ("igig", None, store), ("igig", tok, None)):
            eff = resolve_effective_org(self._core(row), STAFF, product_slug=slug, token=token, selection_store=st)
            assert eff.org_id == HOME and eff.selection_id is None

    def test_staff_with_selection_acts(self):
        row = {"id": STAFF, "org_id": HOME, "org_role": "owner", "role": "admin"}
        store = self._store()
        store.set(STAFF, "igig", TARGET, SID)
        eff = resolve_effective_org(
            self._core(row), STAFF, product_slug="igig", token=_tok(STAFF, session_id=SID, aal="aal2"),
            selection_store=store, license_checker=FakeLicenseChecker(allow_all=False, licensed={(TARGET, "igig")}))
        assert (eff.org_id, eff.org_role, eff.home_org_id, eff.acting) == (TARGET, "owner", HOME, True)

    def test_customer_role_is_never_staff(self):
        row = {"id": STAFF, "org_id": HOME, "org_role": "membro", "role": "admin"}
        store = self._store()
        store.set(STAFF, "igig", TARGET, SID)
        eff = resolve_effective_org(
            self._core(row), STAFF, product_slug="igig", token=_tok(STAFF, session_id=SID, aal="aal2"),
            selection_store=store)
        assert eff.org_id == HOME and eff.is_staff is False

    def test_intent_pin_only_enforced_for_staff(self):
        row = {"id": STAFF, "org_id": HOME, "org_role": "owner", "role": "admin"}
        with pytest.raises(HTTPException) as exc:
            resolve_effective_org(
                self._core(row), STAFF, product_slug="igig",
                token=_tok(STAFF, session_id=SID, aal="aal2"), acting_header=TARGET,
                selection_store=self._store())
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "org_selection_changed"
        plain = {"id": STAFF, "org_id": HOME, "org_role": "owner", "role": "user"}
        eff = resolve_effective_org(
            self._core(plain), STAFF, product_slug="igig", token=_tok(STAFF, session_id=SID, aal="aal2"),
            acting_header=TARGET, selection_store=self._store())
        assert eff.org_id == HOME


class TestStaffEligibilityAndActorHelper:
    def test_platform_admin_with_a_lesser_org_role_never_acts(self):
        row = {"id": STAFF, "org_id": HOME, "org_role": "manager", "role": "admin"}
        c = MockSupabaseClient()
        c.set_table_data("noctus_users", [row])
        c.set_table_data("organizations", [{"id": HOME, "nome": "Casa", "is_platform": True}])
        store = FakeOrgSelectionStore(ready={"igig"}, staff={STAFF}, licensed={(TARGET, "igig")},
                                      home_orgs={STAFF: HOME})
        store.set(STAFF, "igig", TARGET, SID)
        eff = resolve_effective_org(c, STAFF, product_slug="igig",
                                    token=_tok(STAFF, session_id=SID, aal="aal2"), selection_store=store)
        assert eff.org_id == HOME and eff.is_staff is False

    def test_acting_actor_is_client_visible_and_tagged(self):
        from noctusai_lib.api.auth.effective_org import EffectiveOrg, acting_audit_actor

        eff = EffectiveOrg(org_id=TARGET, org_role="owner", home_org_id=HOME, selection_id="sel-1", is_staff=True)
        actor = acting_audit_actor(STAFF, eff)
        assert (actor.org_id, actor.role, actor.acting_org_id, actor.act_as_session_id) == (
            TARGET, "platform_support", HOME, "sel-1")
        home = EffectiveOrg(org_id=HOME, org_role="owner", home_org_id=HOME, selection_id="sel-2", is_staff=True)
        assert acting_audit_actor(STAFF, home) is None
        assert acting_audit_actor(STAFF, None) is None


class TestAuditTagging:
    def _row(self, actor):
        return _to_row(AuditEntry(product_slug="igig", method="POST", route_template="/api/x",
                                  path_params={}, status=200, actor_kind="user", client_hint="web", actor=actor))

    def test_acting_row_carries_target_org_and_tags(self):
        row = self._row(AuditActor(user_id=STAFF, org_id=TARGET, role="platform_support",
                                   acting_org_id=HOME, act_as_session_id="sel-1"))
        assert (row["org_id"], row["acting_org_id"], row["act_as_session_id"]) == (TARGET, HOME, "sel-1")

    def test_selection_endpoints_actor_has_no_org(self):
        row = self._row(AuditActor(user_id=STAFF))
        assert row["org_id"] is None and "act_as_session_id" not in row


class TestSqlCanon:
    def test_helper_is_in_the_picker_tuple_and_renders(self):
        assert ORG_PICKER_FUNCTION_NAMES == ("current_org_id_for",)
        sql = org_identity_function_sql("current_org_id_for")
        assert "x-noctus-acting-org" in sql and "aal2" in sql and "session_id" in sql
        assert "ARRAY['membro']" in sql

    def test_unknown_name_still_raises(self):
        with pytest.raises(ValueError):
            org_identity_function_sql("nope")
