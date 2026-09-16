"""`CredentialService` — status, writes, renewal ordering, §D ring, alerts."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import timedelta

import pytest

from noctusai_lib.security.key_ring import KeyRing

from app.credentials.prober import ProbeResult
from app.credentials.registry import ACADEMIA_API_TOKEN, APPROVAL_RING, SOCIAL_WIRING_API_TOKEN
from app.credentials.service import CredentialError
from tests.credentials.conftest import (
    ANTHROPIC,
    JULIA_ID,
    NOW,
    OLD_ACADEMIA,
    ORG_ID,
    assert_no_secret,
    build_kit,
    seed_academia_token,
)


@pytest.fixture(autouse=True)
def _capture_everything(caplog):
    caplog.set_level(logging.DEBUG)
    yield
    assert_no_secret(caplog.text)


class TestStatus:
    def test_env_values_are_reported_with_prefix_only(self, kit):
        seed_academia_token(kit)
        statuses = {s.name: s for s in kit.service.list_status()}
        academia = statuses["academia_api_token"]
        assert academia.source == "env"
        assert academia.prefix == OLD_ACADEMIA[:11]
        assert academia.days_left == 60
        assert academia.severity == "info"
        anthropic = statuses["anthropic_api_key"]
        assert anthropic.prefix == "sk-ant-api03"
        assert_no_secret(repr([asdict(s) for s in statuses.values()]))

    def test_expiring_token_warns(self, kit):
        seed_academia_token(kit, days_left=10)
        status = kit.service.status("academia_api_token")
        assert status.severity == "warning"
        assert "10" in status.warnings[0]

    def test_principal_mismatch_is_critical(self, kit):
        seed_academia_token(kit, principal=ORG_ID)
        assert kit.service.status("academia_api_token").severity == "critical"

    def test_token_missing_in_target_is_critical(self, kit):
        status = kit.service.status("academia_api_token")
        assert status.configured is True
        assert status.severity == "critical"

    def test_unconfigured(self):
        status = build_kit().service.status("anthropic_api_key")
        assert status.configured is False
        assert status.source is None

    def test_db_value_wins_over_env(self, kit):
        kit.store.put("anthropic_api_key", "sk-ant-api04-" + "Y" * 40)
        status = kit.service.status("anthropic_api_key")
        assert (status.source, status.prefix) == ("db", "sk-ant-api04")

    def test_env_ring_status(self, kit):
        status = kit.service.status("approval_assertion_secrets")
        assert status.configured is True
        assert status.source == "env"
        assert [k.signing for k in status.ring] == [True, False]
        assert status.fingerprint and status.fingerprint not in "ring-secret-one"

    def test_unknown_credential_404(self, kit):
        with pytest.raises(CredentialError) as exc:
            kit.service.status("nope")
        assert exc.value.http_status == 404


class TestWrites:
    def test_set_anthropic_key(self, kit):
        new = "sk-ant-api03-" + "N" * 60
        status = kit.service.set_value("anthropic_api_key", new)
        assert kit.store.get("anthropic_api_key") == new
        assert status.source == "db"
        assert new not in repr(asdict(status))

    @pytest.mark.parametrize(
        "name,value",
        [
            ("anthropic_api_key", "not-a-key"),
            ("academia_api_token", "tok_wrong"),
            ("julia_agent_id", "not-a-uuid"),
            ("anthropic_api_key", "   "),
        ],
    )
    def test_invalid_values_422(self, kit, name, value):
        with pytest.raises(CredentialError) as exc:
            kit.service.set_value(name, value)
        assert exc.value.http_status == 422

    def test_ring_is_not_directly_settable(self, kit):
        with pytest.raises(CredentialError) as exc:
            kit.service.set_value("approval_assertion_secrets", "x")
        assert exc.value.http_status == 409

    def test_import_env_copies_server_side(self, kit):
        kit.service.import_env("academia_api_token")
        assert kit.store.get("academia_api_token") == OLD_ACADEMIA

    def test_import_env_ring_stores_the_json_form(self, kit):
        kit.service.import_env("approval_assertion_secrets")
        ring = KeyRing.from_value(kit.store.get(APPROVAL_RING.store_key))
        assert ring.accepted(NOW) == ["ring-secret-one", "ring-secret-two"]

    def test_import_env_refuses_empty_env(self):
        with pytest.raises(CredentialError) as exc:
            build_kit().service.import_env("anthropic_api_key")
        assert exc.value.code == "env_empty"

    def test_writes_refused_without_a_durable_store_in_deploy(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")  # external deploy signal, not our code
        kit = build_kit(persistent=False, anthropic_api_key=ANTHROPIC)
        with pytest.raises(CredentialError) as exc:
            kit.service.set_value("anthropic_api_key", "sk-ant-api03-" + "Q" * 30)
        assert exc.value.http_status == 503


class TestRenew:
    @pytest.mark.asyncio
    async def test_mint_verify_store_then_revoke_old(self, kit):
        old = seed_academia_token(kit, days_left=5)
        outcome = await kit.service.renew(
            "academia_api_token", actor_user_id=JULIA_ID, fallback_org_id=ORG_ID
        )
        new_secret = kit.store.get("academia_api_token")
        assert new_secret and new_secret != OLD_ACADEMIA
        # the probe ran against the NEW token
        assert kit.prober.calls == [("academia_api_token", new_secret)]
        rows = kit.admin.rows["academia_de_reciclagem"]
        new_row = next(r for r in rows if r["id"] != str(old.id))
        assert new_row["scopes"] == list(ACADEMIA_API_TOKEN.scopes)
        assert new_row["principal_agent_id"] == str(JULIA_ID)
        assert new_row["issuer"] == "agents"
        assert new_row["org_id"] == str(ORG_ID)
        old_row = next(r for r in rows if r["id"] == str(old.id))
        assert old_row["revoked_at"] is not None
        assert outcome.warnings == ()
        assert outcome.status.days_left >= 89
        assert new_secret not in repr(asdict(outcome.status))

    @pytest.mark.asyncio
    async def test_failed_verification_keeps_the_old_token(self, kit):
        old = seed_academia_token(kit)
        kit.prober.results["academia_api_token"] = ProbeResult.of("forbidden", 403)
        with pytest.raises(CredentialError) as exc:
            await kit.service.renew("academia_api_token", actor_user_id=None, fallback_org_id=ORG_ID)
        assert exc.value.code == "verification_failed"
        assert kit.store.get("academia_api_token") is None  # env value still in use
        rows = kit.admin.rows["academia_de_reciclagem"]
        assert next(r for r in rows if r["id"] == str(old.id))["revoked_at"] is None
        minted = next(r for r in rows if r["id"] != str(old.id))
        assert minted["revoked_at"] is not None  # the unverified token is revoked

    @pytest.mark.asyncio
    async def test_revoke_failure_is_a_warning_not_silence(self, kit):
        seed_academia_token(kit)
        kit.admin.fail_revoke = True
        outcome = await kit.service.renew("academia_api_token", actor_user_id=None, fallback_org_id=ORG_ID)
        assert kit.store.get("academia_api_token")
        assert outcome.warnings and "revog" in outcome.warnings[0]

    @pytest.mark.asyncio
    async def test_mint_failure_502(self, kit):
        seed_academia_token(kit)
        kit.admin.fail_mint = True
        with pytest.raises(CredentialError) as exc:
            await kit.service.renew("academia_api_token", actor_user_id=None, fallback_org_id=ORG_ID)
        assert exc.value.http_status == 502
        assert kit.store.get("academia_api_token") is None

    @pytest.mark.asyncio
    async def test_first_provision_uses_the_caller_org_and_no_principal(self):
        kit = build_kit()
        await kit.service.renew("social_wiring_api_token", actor_user_id=None, fallback_org_id=ORG_ID)
        row = kit.admin.rows["social_wiring"][0]
        assert row["org_id"] == str(ORG_ID)
        assert row["principal_agent_id"] is None
        assert row["scopes"] == list(SOCIAL_WIRING_API_TOKEN.scopes)

    @pytest.mark.asyncio
    async def test_academia_renew_needs_julia_agent_id(self):
        kit = build_kit()
        with pytest.raises(CredentialError) as exc:
            await kit.service.renew("academia_api_token", actor_user_id=None, fallback_org_id=ORG_ID)
        assert exc.value.code == "principal_missing"

    @pytest.mark.asyncio
    async def test_only_product_tokens_renew(self, kit):
        with pytest.raises(CredentialError) as exc:
            await kit.service.renew("anthropic_api_key", actor_user_id=None, fallback_org_id=ORG_ID)
        assert exc.value.http_status == 409

    @pytest.mark.asyncio
    async def test_probe_uses_the_resolved_value(self, kit):
        result = await kit.service.probe("anthropic_api_key")
        assert result.ok
        assert kit.prober.calls == [("anthropic_api_key", ANTHROPIC)]

    @pytest.mark.asyncio
    async def test_ring_is_not_probeable(self, kit):
        with pytest.raises(CredentialError) as exc:
            await kit.service.probe("approval_assertion_secrets")
        assert exc.value.http_status == 409


class TestRing:
    def test_rotation_requires_the_ring_in_the_db(self, kit):
        with pytest.raises(CredentialError) as exc:
            kit.service.rotate_ring()
        assert exc.value.code == "ring_not_in_db"

    def test_rotate_stages_then_switches_then_retires(self, kit):
        kit.service.import_env("approval_assertion_secrets")
        status = kit.service.rotate_ring()
        states = [k.state for k in status.ring]
        assert states == ["staged", "retiring", "retiring"]
        assert kit.service.resolver.approval_signing_secret(NOW) == "ring-secret-one"

        switched = NOW + timedelta(seconds=121)
        new_secret = kit.service.resolver.approval_signing_secret(switched)
        assert new_secret not in ("ring-secret-one", "ring-secret-two")

        kit.clock[0] = switched + timedelta(days=2)
        pruned = kit.service.prune_ring()
        assert [k.state for k in pruned.ring] == ["active"]
        assert kit.service.resolver.approval_signing_secret(kit.clock[0]) == new_secret


class TestExpiryAlerts:
    def test_alerts_for_expiring_expired_and_revoked(self):
        kit = build_kit(academia_api_token=OLD_ACADEMIA, social_wiring_api_token="pk_" + "c" * 64,
                        julia_agent_id=str(JULIA_ID))
        seed_academia_token(kit, days_left=3)
        kit.admin.seed(
            "social_wiring", "pk_" + "c" * 64, org_id=ORG_ID,
            expires_at=NOW + timedelta(days=200), revoked_at=NOW,
        )
        alerts = {a.name: a.reason for a in kit.service.expiry_alerts()}
        assert alerts == {"academia_api_token": "expiring", "social_wiring_api_token": "revoked"}

    def test_healthy_tokens_raise_nothing(self, kit):
        seed_academia_token(kit, days_left=80)
        assert [a.name for a in kit.service.expiry_alerts()] == []
