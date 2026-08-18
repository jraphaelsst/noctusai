"""`imovelweb_callback_service` — the integrator-wide registration.

`PUT /v1/configuracao/callbacks` takes no agency code, so one call
redirects every agency's leads at once and the vendor reports nothing when
the new URL is unreachable — it believes it delivered. These tests pin the
three guards that follow from that, and each one exists because the
failure it prevents is SILENT rather than loud.
"""
from __future__ import annotations

import json

import pytest

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_SANDBOX_BR,
    CallbackConfig,
    FakeImovelWebClient,
    basic_credential,
)

from app.modules.portal_leads.services import imovelweb_callback_service as svc

SECRET = "imovelweb-secret-value"
PUBLIC_BASE = "https://noc.example.com"


def _fake(**kwargs) -> FakeImovelWebClient:
    kwargs.setdefault("base_url", IMOVELWEB_SANDBOX_BR)
    return FakeImovelWebClient(**kwargs)


class _MemoryStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def put(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)


class TestUrlGuard:
    @pytest.mark.parametrize(
        "base",
        [
            "http://localhost:8000",
            "https://127.0.0.1",
            "https://10.0.0.4",
            "https://abc123.ngrok-free.app",
        ],
    )
    @pytest.mark.asyncio
    async def test_refuses_an_unreachable_receiver(self, base):
        """The failure this prevents is INVISIBLE: the vendor believes it
        delivered, we never see the lead, and every agency's leads stop
        arriving at once with no error anywhere."""
        adapter = _fake()

        with pytest.raises(svc.CallbackRegistrationError, match="blackholes"):
            await svc.register_callback(
                adapter, public_base_url=base, webhook_secret=SECRET
            )

        assert adapter.put_calls == []

    @pytest.mark.asyncio
    async def test_allow_local_url_registers_and_says_so(self):
        adapter = _fake()

        result = await svc.register_callback(
            adapter,
            public_base_url="http://localhost:8000",
            webhook_secret=SECRET,
            allow_local_url=True,
        )

        assert result["registered"] is True
        assert any("allow_local_url" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_no_secret_is_a_424_not_a_validation_error(self):
        """"We are not set up" and "you asked for something invalid" are
        different facts, and an operator acts on them differently."""
        with pytest.raises(svc.CallbackRegistrationError) as exc:
            await svc.register_callback(
                _fake(), public_base_url=PUBLIC_BASE, webhook_secret=""
            )

        assert exc.value.status == 424


class TestRegistration:
    @pytest.mark.asyncio
    async def test_registers_our_own_credential(self):
        adapter = _fake()

        await svc.register_callback(
            adapter, public_base_url=PUBLIC_BASE, webhook_secret=SECRET
        )

        assert adapter.put_calls[0].authorization_header_value == basic_credential(SECRET)

    @pytest.mark.asyncio
    async def test_registers_the_canonical_receiver_path(self):
        adapter = _fake()

        await svc.register_callback(
            adapter, public_base_url=PUBLIC_BASE + "/", webhook_secret=SECRET
        )

        assert adapter.put_calls[0].url == f"{PUBLIC_BASE}{svc.RECEIVER_PATH}"

    @pytest.mark.asyncio
    async def test_the_credential_never_appears_in_the_result(self):
        """There is no signature scheme — that header IS the entire inbound
        security boundary."""
        result = await svc.register_callback(
            _fake(), public_base_url=PUBLIC_BASE, webhook_secret=SECRET
        )

        assert SECRET not in json.dumps(result)
        assert result["applied"]["authorizationHeaderValue"] == "***REDACTED***"

    @pytest.mark.asyncio
    async def test_refuses_an_empty_subscription_list(self):
        """Legal to the vendor, useless to us, and invisible: a perfectly
        configured URL with no subscriptions delivers nothing and reports
        no error anywhere. The likeliest production incident here."""
        adapter = _fake()

        with pytest.raises(svc.CallbackRegistrationError, match="delivers nothing"):
            await svc.register_callback(
                adapter, public_base_url=PUBLIC_BASE, webhook_secret=SECRET, events=()
            )

        assert adapter.put_calls == []


class TestReadBackAndDrift:
    @pytest.mark.asyncio
    async def test_reports_a_dropped_subscription(self):
        class _Dropping(FakeImovelWebClient):
            """The real hazard: the PUT succeeds and the subscriptions are
            not stored. Invisible without a read-back."""

            async def put_callback_config(self, config):
                stripped = CallbackConfig(
                    url=config.url,
                    authorization_header_value=config.authorization_header_value,
                    language=config.language,
                    subscriptions=("CONTACTO",),
                )
                await super().put_callback_config(stripped)
                return stripped

        result = await svc.register_callback(
            _Dropping(base_url=IMOVELWEB_SANDBOX_BR),
            public_base_url=PUBLIC_BASE,
            webhook_secret=SECRET,
        )

        assert any("dropped" in d for d in result["drift"])

    @pytest.mark.asyncio
    async def test_a_reordering_is_not_reported_as_drift(self):
        """The vendor is free to reorder. Reporting that as drift would
        train the reader to skip the list — which is the list that matters."""
        class _Reordering(FakeImovelWebClient):
            async def put_callback_config(self, config):
                flipped = CallbackConfig(
                    url=config.url,
                    authorization_header_value=config.authorization_header_value,
                    language=config.language,
                    subscriptions=tuple(reversed(config.subscriptions)),
                )
                await super().put_callback_config(flipped)
                return flipped

        result = await svc.register_callback(
            _Reordering(base_url=IMOVELWEB_SANDBOX_BR),
            public_base_url=PUBLIC_BASE,
            webhook_secret=SECRET,
        )

        assert result["drift"] == []

    @pytest.mark.asyncio
    async def test_warns_when_nothing_is_subscribed_afterwards(self):
        class _Swallowing(FakeImovelWebClient):
            async def put_callback_config(self, config):
                return CallbackConfig(
                    url=config.url,
                    authorization_header_value=config.authorization_header_value,
                    subscriptions=(),
                )

        result = await svc.register_callback(
            _Swallowing(base_url=IMOVELWEB_SANDBOX_BR),
            public_base_url=PUBLIC_BASE,
            webhook_secret=SECRET,
        )

        assert any("deliver nothing" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_a_changed_language_is_named_for_what_it_breaks(self):
        class _Relanguaging(FakeImovelWebClient):
            async def put_callback_config(self, config):
                changed = CallbackConfig(
                    url=config.url,
                    authorization_header_value=config.authorization_header_value,
                    language="PT",
                    subscriptions=config.subscriptions,
                )
                await super().put_callback_config(changed)
                return changed

        result = await svc.register_callback(
            _Relanguaging(base_url=IMOVELWEB_SANDBOX_BR),
            public_base_url=PUBLIC_BASE,
            webhook_secret=SECRET,
            language="EN2",
        )

        assert any("FIELD NAMES" in d for d in result["drift"])


class TestRollbackCopy:
    @pytest.mark.asyncio
    async def test_keeps_the_previous_configuration(self):
        """After a bad PUT the VENDOR cannot tell you what you had, and the
        registration is integrator-wide — so this is the only copy."""
        store = _MemoryStore()
        adapter = _fake(callback_config=CallbackConfig(
            url="https://old.example.com/hook",
            authorization_header_value="Basic old",
        ))

        await svc.register_callback(
            adapter, public_base_url=PUBLIC_BASE, webhook_secret=SECRET, store=store
        )

        from app.services.app_config_store import (
            IMOVELWEB_CALLBACK_CONFIG_KEY,
            IMOVELWEB_CALLBACK_CONFIG_PREVIOUS_KEY,
        )

        previous = json.loads(store.values[IMOVELWEB_CALLBACK_CONFIG_PREVIOUS_KEY])
        applied = json.loads(store.values[IMOVELWEB_CALLBACK_CONFIG_KEY])
        assert previous["url"] == "https://old.example.com/hook"
        assert applied["url"].startswith(PUBLIC_BASE)

    @pytest.mark.asyncio
    async def test_the_stored_copy_carries_no_credential(self):
        store = _MemoryStore()

        await svc.register_callback(
            _fake(), public_base_url=PUBLIC_BASE, webhook_secret=SECRET, store=store
        )

        assert SECRET not in json.dumps(store.values)

    @pytest.mark.asyncio
    async def test_says_so_when_the_previous_config_could_not_be_read(self):
        class _NoRead(FakeImovelWebClient):
            async def get_callback_config(self):
                from noctusai_lib.integrations.imovelweb import ImovelWebUpstreamError

                raise ImovelWebUpstreamError("vendor down", status=503)

        result = await svc.register_callback(
            _NoRead(base_url=IMOVELWEB_SANDBOX_BR),
            public_base_url=PUBLIC_BASE,
            webhook_secret=SECRET,
        )

        assert result["registered"] is True
        assert any("nothing to roll back to" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_a_persistence_failure_does_not_report_the_write_as_failed(self):
        """The vendor write already happened. Raising here would send an
        operator to re-run a registration the vendor already has."""
        class _BrokenStore:
            def put(self, key, value):
                raise RuntimeError("store unavailable")

        result = await svc.register_callback(
            _fake(),
            public_base_url=PUBLIC_BASE,
            webhook_secret=SECRET,
            store=_BrokenStore(),
        )

        assert result["registered"] is True


class TestReadConfig:
    @pytest.mark.asyncio
    async def test_flags_the_silent_failure(self):
        """Nothing registered reads as "no subscriptions" — the state that
        reports perfect health and delivers nothing."""
        result = await svc.read_config(_fake())

        assert result["delivers_nothing"] is True

    @pytest.mark.asyncio
    async def test_a_healthy_config_is_not_flagged(self):
        adapter = _fake()
        await svc.register_callback(
            adapter, public_base_url=PUBLIC_BASE, webhook_secret=SECRET
        )

        result = await svc.read_config(adapter)

        assert result["delivers_nothing"] is False
        assert result["config"]["authorizationHeaderValue"] == "***REDACTED***"
