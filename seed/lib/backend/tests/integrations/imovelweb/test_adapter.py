"""Protocol conformance, factory selection, leniency, XML errors, retryability.

Also pins the outage rule: nothing on the lead path imports an LLM client.
A model provider going down must never cost a customer enquiry.
"""

from __future__ import annotations

import inspect

import pytest

from noctusai_lib.integrations.imovelweb.endpoints import (
    IMOVELWEB_PROD_BR,
    IMOVELWEB_SANDBOX_BR,
)
from noctusai_lib.integrations.imovelweb.errors import (
    ImovelWebConfigError,
    ImovelWebError,
    ImovelWebUpstreamError,
)
from noctusai_lib.integrations.imovelweb.factory import make_imovelweb_client
from noctusai_lib.integrations.imovelweb.fake import FakeImovelWebClient
from noctusai_lib.integrations.imovelweb.protocol import ImovelWebAdapter
from noctusai_lib.integrations.imovelweb.real import (
    ImovelWebClient,
    _is_retryable,
    describe_error_body,
)


class _Response:
    def __init__(self, *, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class TestFactory:
    def test_use_fake_returns_the_fake(self):
        assert isinstance(make_imovelweb_client(use_fake=True), FakeImovelWebClient)

    def test_default_returns_the_real_client(self):
        assert isinstance(make_imovelweb_client(), ImovelWebClient)

    def test_construction_without_credentials_never_raises(self):
        # The seed's leniency contract: an unconfigured tenant must not
        # stop the host app from starting.
        client = make_imovelweb_client(client_id=None, client_secret=None)
        assert client.configured is False

    def test_unknown_region_is_also_lenient(self):
        client = make_imovelweb_client(region="atlantis")
        assert client.configured is False


class TestProtocolConformance:
    @pytest.mark.parametrize(
        "client",
        [make_imovelweb_client(use_fake=True), make_imovelweb_client()],
        ids=["fake", "real"],
    )
    def test_satisfies_the_protocol(self, client):
        assert isinstance(client, ImovelWebAdapter)

    def test_fake_and_real_expose_the_same_surface(self):
        # A Fake missing a method is a test that passes here and fails in
        # production — the exact failure the quartet exists to prevent.
        def public_methods(obj):
            return {
                name
                for name, _ in inspect.getmembers(obj, callable)
                if not name.startswith("_")
            }

        real = public_methods(ImovelWebClient)
        fake = public_methods(FakeImovelWebClient)
        missing = real - fake - {"redact"}
        assert missing == set(), f"Fake is missing: {sorted(missing)}"


class TestLeniencyAndGating:
    @pytest.mark.asyncio
    async def test_unconfigured_real_client_raises_424_on_first_call(self):
        client = make_imovelweb_client(client_id=None, client_secret=None)
        with pytest.raises(ImovelWebConfigError) as exc:
            await client.get_callback_config()
        assert exc.value.status == 424

    @pytest.mark.asyncio
    async def test_unconfigured_fake_raises_the_same_way(self):
        client = make_imovelweb_client(use_fake=True, fake_configured=False)
        with pytest.raises(ImovelWebConfigError):
            await client.list_agencies()

    def test_connection_status_makes_no_api_call(self):
        # No http_client at all: if this touched the network it would fail.
        client = make_imovelweb_client(client_id="a", client_secret="b")
        status = client.connection_status()
        assert status["configured"] is True
        assert status["verified_against_live_traffic"] is False

    def test_connection_status_names_what_is_missing(self):
        client = make_imovelweb_client(client_id="a", client_secret=None)
        assert "client_secret" in client.connection_status()["missing"]

    def test_config_error_is_424_and_upstream_defaults_to_502(self):
        assert ImovelWebConfigError("x").status == 424
        assert ImovelWebUpstreamError("x").status == 502
        assert ImovelWebUpstreamError("x", status=429).status == 429

    def test_both_subclass_the_base(self):
        assert issubclass(ImovelWebConfigError, ImovelWebError)
        assert issubclass(ImovelWebUpstreamError, ImovelWebError)


class TestRetryability:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_retryable(self, status):
        assert _is_retryable(status) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 412, 422, 200, 204])
    def test_not_retryable(self, status):
        # Never a 4xx: it will be identical on every retry.
        assert _is_retryable(status) is False

    def test_transport_failure_gets_one_more_try(self):
        assert _is_retryable(None) is True


class TestXmlErrorParsing:
    """Gate 0 observed that this vendor answers errors in XML, despite its
    spec declaring `produces: */*`. Assuming JSON would bury the message."""

    def test_parses_the_observed_401_body(self):
        body = (
            "<UnauthorizedException><error>unauthorized</error>"
            "<error_description>An Authentication object was not found in the "
            "SecurityContext</error_description></UnauthorizedException>"
        )
        described = describe_error_body(_Response(status_code=401, text=body))
        assert "401" in described
        assert "An Authentication object was not found" in described

    def test_falls_back_to_the_tag_when_there_are_no_known_fields(self):
        described = describe_error_body(
            _Response(status_code=500, text="<SomeOtherFault/>")
        )
        assert "SomeOtherFault" in described

    def test_still_handles_json(self):
        described = describe_error_body(
            _Response(status_code=400, payload={"error_description": "bad request"})
        )
        assert "bad request" in described

    def test_falls_back_to_raw_text(self):
        assert "plain failure" in describe_error_body(
            _Response(status_code=500, text="plain failure")
        )

    def test_never_raises_on_malformed_xml(self):
        assert describe_error_body(_Response(status_code=500, text="<broken"))

    def test_handles_a_response_with_nothing_useful(self):
        assert "500" in describe_error_body(_Response(status_code=500))


class TestOutageResilience:
    """The lead path must survive a provider outage — including ours."""

    def test_no_llm_import_anywhere_in_the_package(self):
        # The vendor allows 1.5 seconds to answer. A model call cannot fit
        # inside that, and a model OUTAGE inside it would convert someone
        # else's incident into lost customer enquiries.
        import pathlib

        import noctusai_lib.integrations.imovelweb as package

        root = pathlib.Path(package.__file__).parent
        offenders = []
        for path in sorted(root.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for needle in ("integrations.llm", "import openai", "from openai",
                           "anthropic", "litellm"):
                # Skip prose: only flag it if it reads like real code.
                for line in source.splitlines():
                    stripped = line.strip()
                    if needle in stripped and (
                        stripped.startswith("import ") or stripped.startswith("from ")
                    ):
                        offenders.append(f"{path.name}: {stripped}")
        assert offenders == [], (
            "the ImovelWeb package must not reach a model provider on the lead "
            f"path: {offenders}"
        )

    def test_contract_tools_work_with_no_credentials_and_no_network(self):
        # What makes the connector usable for diagnosis DURING an outage
        # rather than another thing that is down.
        from noctusai_lib.integrations.imovelweb.contract import contract_summary
        from noctusai_lib.integrations.imovelweb.webhook import (
            parse_imovelweb_callback,
        )

        assert contract_summary()["languages"]
        assert parse_imovelweb_callback({"eventId": "e1"}) is not None
