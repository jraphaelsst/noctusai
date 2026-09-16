"""`HttpCredentialProber` (over `httpx.MockTransport`), the expiry
notification sink logic, and resolver-level guards."""
from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

import httpx
import pytest

from noctusai_lib.config.deploy_config import MissingProdConfigError
from noctusai_lib.security.app_config import FakeAppConfigStore

from app.credentials.alerts import (
    FakeNotificationSink,
    dedup_key,
    notify_expiry_alerts,
    run_credential_maintenance,
)
from app.credentials.prober import HttpCredentialProber
from app.credentials.registry import (
    ACADEMIA_API_TOKEN,
    ANTHROPIC_API_KEY,
    APPROVAL_RING,
    JULIA_AGENT_ID,
    SOCIAL_WIRING_API_TOKEN,
)
from app.credentials.resolver import CredentialResolver, require_resolved_prod_config
from app.credentials.service import ExpiryAlert
from tests.credentials.conftest import (
    ANTHROPIC,
    ENV_SOCIAL,
    NOW,
    OLD_ACADEMIA,
    assert_no_secret,
    build_kit,
    make_settings,
    seed_academia_token,
)


def _prober(handler, seen):
    def _record(request: httpx.Request):
        seen.append(request)
        return handler(request)

    return HttpCredentialProber(
        base_url_for=lambda slug: f"https://{slug}.example.com",
        transport=httpx.MockTransport(_record),
    )


class TestHttpProber:
    @pytest.mark.asyncio
    async def test_academia_ok(self, caplog):
        caplog.set_level(logging.DEBUG)
        seen: list = []
        prober = _prober(lambda r: httpx.Response(200, json={"items": []}), seen)
        result = await prober.probe(ACADEMIA_API_TOKEN, OLD_ACADEMIA)
        assert result.ok and result.http_status == 200
        assert str(seen[0].url) == "https://academia-de-reciclagem.example.com/api/decisions"
        assert seen[0].headers["authorization"] == f"Bearer {OLD_ACADEMIA}"
        assert_no_secret(caplog.text + repr(result))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code,status", [(401, "unauthorized"), (403, "forbidden"), (503, "unreachable"), (418, "error")])
    async def test_status_mapping(self, code, status):
        prober = _prober(lambda r: httpx.Response(code), [])
        assert (await prober.probe(ACADEMIA_API_TOKEN, OLD_ACADEMIA)).status == status

    @pytest.mark.asyncio
    async def test_social_wiring_404_means_auth_passed(self):
        seen: list = []
        prober = _prober(lambda r: httpx.Response(404), seen)
        result = await prober.probe(SOCIAL_WIRING_API_TOKEN, ENV_SOCIAL)
        assert result.ok
        assert seen[0].url.path.endswith("/00000000-0000-0000-0000-000000000000")

    @pytest.mark.asyncio
    async def test_social_wiring_uses_the_configured_connection(self):
        seen: list = []
        conn = UUID("33333333-3333-3333-3333-333333333333")
        prober = _prober(lambda r: httpx.Response(200, json={}), seen)
        await prober.probe(SOCIAL_WIRING_API_TOKEN, ENV_SOCIAL, connection_id=conn)
        assert seen[0].url.path == f"/api/agents-bridge/one-chat/{conn}"

    @pytest.mark.asyncio
    async def test_anthropic_uses_x_api_key(self):
        seen: list = []
        prober = HttpCredentialProber(
            base_url_for=lambda slug: "unused",
            transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={})),
            anthropic_models_url="https://anthropic.example.com/v1/models",
        )
        assert (await prober.probe(ANTHROPIC_API_KEY, ANTHROPIC)).ok
        assert seen[0].headers["x-api-key"] == ANTHROPIC
        assert "authorization" not in seen[0].headers

    @pytest.mark.asyncio
    async def test_network_error_is_unreachable_and_leak_free(self, caplog):
        caplog.set_level(logging.DEBUG)

        def boom(request):
            raise httpx.ConnectError("down", request=request)

        result = await _prober(boom, []).probe(ACADEMIA_API_TOKEN, OLD_ACADEMIA)
        assert result.status == "unreachable"
        assert_no_secret(caplog.text + repr(result))

    @pytest.mark.asyncio
    async def test_non_probeable_spec(self):
        result = await _prober(lambda r: httpx.Response(200), []).probe(JULIA_AGENT_ID, "x")
        assert result.status == "error"


class TestAlerts:
    def _alert(self, days_left, reason="expiring"):
        # One token → one fixed expiry; only `days_left` moves day to day.
        return ExpiryAlert("academia_api_token", "Academia", NOW + timedelta(days=30), days_left, reason)

    def test_dedup_buckets(self):
        assert dedup_key(self._alert(25)).endswith(":30")
        assert dedup_key(self._alert(6)).endswith(":7")
        assert dedup_key(self._alert(0, "expired")).endswith(":expired")

    def test_one_notification_per_admin_per_bucket(self):
        sink = FakeNotificationSink(["u1", "u2"])
        assert notify_expiry_alerts([self._alert(20)], sink) == 2
        assert notify_expiry_alerts([self._alert(19)], sink) == 0  # same bucket
        assert notify_expiry_alerts([self._alert(6)], sink) == 2  # next bucket
        assert sink.sent[0]["metadata"]["link"] == "/credenciais"

    def test_no_platform_admin_is_logged_not_silent(self, caplog):
        assert notify_expiry_alerts([self._alert(3)], FakeNotificationSink([])) == 0
        assert "no_platform_admin" in caplog.text

    def test_maintenance_runs_both_legs(self, caplog):
        caplog.set_level(logging.DEBUG)
        kit = build_kit(academia_api_token=OLD_ACADEMIA, julia_agent_id="22222222-2222-2222-2222-222222222222")
        seed_academia_token(kit, days_left=2)
        sink = FakeNotificationSink(["admin-1"])
        result = run_credential_maintenance(kit.service, sink)
        assert result == {"alerts": 1, "notified": 1, "ring": "ring_not_in_db"}
        assert_no_secret(caplog.text + repr(sink.sent))


class TestResolver:
    def test_db_first_env_fallback_per_key(self):
        store = FakeAppConfigStore()
        resolver = CredentialResolver(store, make_settings(anthropic_api_key=ANTHROPIC, academia_api_token=OLD_ACADEMIA))
        store.put(ACADEMIA_API_TOKEN.store_key, "pk_db")
        assert resolver.academia_api_token() == "pk_db"
        assert resolver.anthropic_api_key() == ANTHROPIC
        assert resolver.social_wiring_api_token() is None

    def test_ring_storage_key_is_audience_scoped(self):
        assert APPROVAL_RING.store_key == "approval_assertion_secrets:academia-de-reciclagem"

    def test_malformed_agent_id_is_none(self):
        resolver = CredentialResolver(FakeAppConfigStore(), make_settings(julia_agent_id="nope"))
        assert resolver.julia_agent_id() is None

    def test_prod_guard_lists_every_gap(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")  # external deploy signal
        resolver = CredentialResolver(FakeAppConfigStore(), make_settings(anthropic_api_key=ANTHROPIC))
        with pytest.raises(MissingProdConfigError) as exc:
            require_resolved_prod_config(resolver)
        assert exc.value.missing_keys == ["APPROVAL_ASSERTION_SECRETS", "ACADEMIA_API_TOKEN", "JULIA_AGENT_ID"]

    def test_prod_guard_accepts_db_only_values(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        store = FakeAppConfigStore()
        for spec, value in (
            (ANTHROPIC_API_KEY, ANTHROPIC),
            (ACADEMIA_API_TOKEN, OLD_ACADEMIA),
            (JULIA_AGENT_ID, "22222222-2222-2222-2222-222222222222"),
            (APPROVAL_RING, "k1"),
        ):
            store.put(spec.store_key, value)
        require_resolved_prod_config(CredentialResolver(store, make_settings()))
