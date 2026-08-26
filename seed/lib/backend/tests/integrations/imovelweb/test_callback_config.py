"""`CallbackConfig` validation and the register-then-read-back loop.

`PUT /v1/configuracao/callbacks` takes no agency code, so it is
integrator-wide: one bad write redirects every agency's leads. Validation
is the cheap half of the guard; the read-back diff is the other half.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.imovelweb.errors import ImovelWebConfigError
from noctusai_lib.integrations.imovelweb.factory import make_imovelweb_client
from noctusai_lib.integrations.imovelweb.types import (
    IMOVELWEB_LEAD_EVENT_TYPES,
    CallbackConfig,
)


def _config(**overrides) -> CallbackConfig:
    base = dict(
        url="https://noc.example.com/api/portals/imovelweb/leads",
        authorization_header_value="Basic bm9jdHVzYWk6c2VjcmV0",
    )
    base.update(overrides)
    return CallbackConfig(**base)


class TestValidate:
    def test_a_good_config_has_no_problems(self):
        assert _config().validate() == ()

    @pytest.mark.parametrize("url", ["", "ftp://x", "noc.example.com", "//x"])
    def test_url_must_be_http_or_https(self, url):
        problems = _config(url=url).validate()
        assert any("http://" in p for p in problems)

    def test_empty_header_value_is_refused(self):
        problems = _config(authorization_header_value="").validate()
        assert any("unauthenticated receiver" in p for p in problems)

    def test_basic_credential_must_carry_the_literal_word(self):
        # The vendor forwards this string verbatim, so a malformed one
        # fails at our OWN verifier — and looks like a vendor problem.
        problems = _config(authorization_header_value="basicbm9j").validate()
        assert any("literal 'Basic <token>'" in p for p in problems)

    def test_a_non_basic_token_is_allowed(self):
        assert _config(authorization_header_value="Bearer abc123").validate() == ()

    def test_empty_header_key_is_refused(self):
        assert _config(authorization_header_key="").validate()

    def test_language_must_be_known(self):
        problems = _config(language="KLINGON").validate()
        assert any("not one of" in p for p in problems)

    def test_empty_subscriptions_is_refused_with_the_reason(self):
        # Legal to the vendor, useless to us, and INVISIBLE: a perfectly
        # configured URL with no subscriptions delivers nothing and
        # reports no error anywhere. The likeliest production incident.
        problems = _config(subscriptions=()).validate()
        assert any("delivers nothing, silently" in p for p in problems)

    def test_unknown_events_are_refused(self):
        problems = _config(subscriptions=("CONTACTO", "NOT_A_REAL_EVENT")).validate()
        assert any("NOT_A_REAL_EVENT" in p for p in problems)

    def test_defaults_subscribe_to_both_lead_events(self):
        assert _config().subscriptions == IMOVELWEB_LEAD_EVENT_TYPES


class TestWireRoundTrip:
    def test_to_wire_uses_the_vendor_field_names(self):
        wire = _config().to_wire()
        assert set(wire) == {
            "url", "authorizationHeaderKey", "authorizationHeaderValue",
            "lenguajeCallbackBody", "subscriptions",
        }

    def test_round_trips(self):
        original = _config(language="PT", subscriptions=("CONTACTO",))
        assert CallbackConfig.from_wire(original.to_wire()) == original

    def test_from_wire_tolerates_an_empty_response(self):
        # The read-back half of register-then-diff: a config we cannot
        # parse IS the drift the diff exists to surface, so this must not
        # explode.
        parsed = CallbackConfig.from_wire({})
        assert parsed.url == ""
        assert parsed.subscriptions == ()

    def test_from_wire_defaults_the_header_key(self):
        assert CallbackConfig.from_wire({"url": "https://x"}).authorization_header_key == "Authorization"


class TestFakeMirrorsRealRefusals:
    """A Fake more permissive than production makes tests lie."""

    @pytest.mark.asyncio
    async def test_fake_refuses_an_invalid_config(self):
        client = make_imovelweb_client(use_fake=True)
        with pytest.raises(ImovelWebConfigError, match="refusing to register"):
            await client.put_callback_config(_config(url="ftp://nope"))

    @pytest.mark.asyncio
    async def test_fake_refuses_empty_subscriptions(self):
        client = make_imovelweb_client(use_fake=True)
        with pytest.raises(ImovelWebConfigError):
            await client.put_callback_config(_config(subscriptions=()))

    @pytest.mark.asyncio
    async def test_unregistered_state_is_the_dangerous_one(self):
        # Nothing registered reads as "no subscriptions", which is exactly
        # the silent-failure shape the health card must show in red.
        client = make_imovelweb_client(use_fake=True)
        current = await client.get_callback_config()
        assert current.subscriptions == ()
        assert current.url == ""

    @pytest.mark.asyncio
    async def test_put_then_get_round_trips(self):
        client = make_imovelweb_client(use_fake=True)
        await client.put_callback_config(_config())
        assert (await client.get_callback_config()).url == _config().url

    @pytest.mark.asyncio
    async def test_subscribe_and_unsubscribe_are_recorded(self):
        client = make_imovelweb_client(use_fake=True)
        await client.put_callback_config(_config(subscriptions=("CONTACTO",)))
        await client.subscribe_event("CONTACTO_MENSAJE")
        assert "CONTACTO_MENSAJE" in (await client.get_callback_config()).subscriptions
        await client.unsubscribe_event("CONTACTO_MENSAJE")
        assert "CONTACTO_MENSAJE" not in (await client.get_callback_config()).subscriptions
        assert client.subscribed == ["CONTACTO_MENSAJE"]
        assert client.unsubscribed == ["CONTACTO_MENSAJE"]
