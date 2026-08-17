"""Normalizer + Protocol/Fake/Real/factory tests for the OLX integration."""

from __future__ import annotations

import copy
from datetime import date

import pytest

from noctusai_lib.integrations.olx import (
    OLX_SAMPLE_LEAD,
    OLX_SOURCE_SLUG,
    FakeOlxLeadManagerClient,
    OlxConfigError,
    OlxLeadManagerClient,
    OlxUpstreamError,
    make_olx_lead_manager_client,
    olx_lead_to_lead_payload,
    olx_timestamp_to_date,
    parse_olx_lead_webhook,
    redact_secret,
    render_observacoes,
)

SOURCE_ID = "11111111-2222-3333-4444-555555555555"


def _lead(**overrides):
    body = copy.deepcopy(OLX_SAMPLE_LEAD)
    body.update(overrides)
    lead = parse_olx_lead_webhook(body)
    assert lead is not None
    return lead


# -- timestamps ------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("2017-10-23T15:50:30.619Z", date(2017, 10, 23)),
    ("2017-10-23T15:50:30.619+00:00", date(2017, 10, 23)),
    ("2017-10-23T15:50:30", date(2017, 10, 23)),
    ("2017-10-23", date(2017, 10, 23)),
])
def test_parses_the_timestamp_shapes_the_vendor_sends(raw, expected):
    assert olx_timestamp_to_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "not-a-date", None, 12345])
def test_returns_none_for_an_unparseable_timestamp(raw):
    assert olx_timestamp_to_date(raw) is None


# -- mapping ---------------------------------------------------------------


def test_maps_a_lead_onto_the_unified_lead_payload():
    payload = olx_lead_to_lead_payload(_lead(), origem_source_id=SOURCE_ID)

    assert payload["external_source"] == OLX_SOURCE_SLUG
    assert payload["external_lead_id"] == "59ee0fc6e4b043e1b2a6d863"
    assert payload["origem_id"] == SOURCE_ID
    assert payload["data_entrada"] == date(2017, 10, 23)
    assert payload["tipo_lead"] == "novo"
    assert payload["cliente_nome"] == "Nome Consumidor"
    assert payload["contato"] == "11999999999"
    assert payload["codigo_imovel"] == "a40171"


def test_refuses_to_invent_a_data_entrada():
    """`data_entrada` is NOT NULL on `leads`. Stamping today() would put a
    wrong date on a real lead and nobody would ever notice."""
    with pytest.raises(ValueError, match="refusing to guess"):
        olx_lead_to_lead_payload(_lead(timestamp="???"), origem_source_id=SOURCE_ID)


def test_origem_raw_keeps_the_provenance_the_slug_flattens():
    """One `grupo-olx` slug is the honest attribution, but the pipe and
    channel still have to survive the join — that is what lets us build
    the portal splitter later, once Gate 1 says what distinguishes them."""
    payload = olx_lead_to_lead_payload(_lead(), origem_source_id=SOURCE_ID)

    assert payload["origem_raw"] == "Grupo OLX / CONTACT_CHAT"


def test_falls_back_to_email_when_there_is_no_phone():
    lead = _lead(phoneNumber=None, ddd=None, phone=None)

    payload = olx_lead_to_lead_payload(lead, origem_source_id=SOURCE_ID)

    assert payload["contato"] == "nome.consumidor@email.com"


def test_never_assigns_a_corretor():
    """The OLX payload carries no broker field. Guessing one would hand a
    real customer to the wrong person; an unassigned lead is honest."""
    payload = olx_lead_to_lead_payload(_lead(), origem_source_id=SOURCE_ID)

    assert "corretor_id" not in payload


def test_observacoes_renders_the_signals_a_broker_acts_on():
    text = render_observacoes(_lead())

    assert "Mensagem: Olá, tenho interesse neste imóvel..." in text
    assert "Canal: CONTACT_CHAT" in text
    assert "Temperatura: Alta" in text
    assert "Lead Certo: sim" in text


def test_observacoes_is_none_when_there_is_nothing_to_show():
    lead = _lead(message=None, temperature=None, transactionType=None,
                 originListingId=None, extraData={})

    assert render_observacoes(lead) is None


# -- adapter: Fake ---------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_records_pushes_instead_of_sending():
    client = FakeOlxLeadManagerClient()

    result = await client.push_lead(
        lead_name="Fulana", lead_email="f@example.com", business_type="SALE"
    )

    assert result == {"status": "OK"}
    assert client.pushed[0]["LeadName"] == "Fulana"
    assert client.pushed[0]["BusinessType"] == "SALE"


@pytest.mark.asyncio
async def test_fake_unconfigured_raises_the_same_error_as_real():
    client = FakeOlxLeadManagerClient(configured=False)

    with pytest.raises(OlxConfigError):
        await client.push_lead(lead_name="Fulana")


@pytest.mark.asyncio
async def test_fake_rejects_the_inbound_vocabulary_exactly_like_real():
    """SELL/RENT is the INBOUND webhook's vocabulary; addLeads wants
    SALE/RENTAL. If the Fake accepted SELL, a test would pass against a
    call production rejects — the exact false-green a Fake exists to
    avoid."""
    client = FakeOlxLeadManagerClient()

    with pytest.raises(ValueError, match="SALE"):
        await client.push_lead(lead_name="Fulana", business_type="SELL")


@pytest.mark.asyncio
async def test_fake_connection_status_needs_no_network():
    status = await FakeOlxLeadManagerClient().connection_status()

    assert status["ok"] is True
    assert status["fake"] is True


# -- adapter: Real ---------------------------------------------------------


@pytest.mark.asyncio
async def test_real_client_construction_is_lenient():
    """Building an unconfigured client must not raise — a tenant that has
    not set OLX up cannot be allowed to stop the host app booting."""
    client = OlxLeadManagerClient()

    assert client.configured is False
    with pytest.raises(OlxConfigError):
        await client.push_lead(lead_name="Fulana")


@pytest.mark.asyncio
async def test_real_client_connection_status_makes_no_call():
    status = await OlxLeadManagerClient("key", "agent").connection_status()

    assert status["configured"] is True
    assert status["next_step"] is None


class _StubResponse:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _StubHttp:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._response


@pytest.mark.asyncio
async def test_real_client_sends_the_documented_headers_and_body():
    http = _StubHttp(_StubResponse(200, '{"ok":true}', {"ok": True}))
    client = OlxLeadManagerClient("the-key", "the-agent", http_client=http)

    result = await client.push_lead(
        lead_name="Fulana", lead_email="f@example.com", business_type="RENTAL"
    )

    assert result == {"ok": True}
    call = http.calls[0]
    assert call["url"].endswith("/v1/addLeads")
    assert call["headers"]["X-API-KEY"] == "the-key"
    assert call["headers"]["X-Agent-Name"] == "the-agent"
    assert call["json"] == {
        "LeadName": "Fulana", "LeadEmail": "f@example.com", "BusinessType": "RENTAL"
    }


@pytest.mark.asyncio
async def test_real_client_treats_an_empty_2xx_body_as_success():
    http = _StubHttp(_StubResponse(204, ""))
    client = OlxLeadManagerClient("k", "a", http_client=http)

    assert await client.push_lead(lead_name="Fulana") == {}


@pytest.mark.asyncio
async def test_real_client_does_not_retry_a_4xx():
    """A 4xx means the request is wrong; retrying sends the same wrong
    request three more times."""
    http = _StubHttp(_StubResponse(400, "bad request"))
    client = OlxLeadManagerClient("k", "a", http_client=http)

    with pytest.raises(OlxUpstreamError) as excinfo:
        await client.push_lead(lead_name="Fulana")

    assert excinfo.value.status == 400
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_real_client_redacts_the_api_key_out_of_an_error_body():
    """Vendors echo credentials in error bodies, and an MCP tool result
    goes straight into a model's context."""
    http = _StubHttp(_StubResponse(400, "invalid key: super-secret-key"))
    client = OlxLeadManagerClient("super-secret-key", "a", http_client=http)

    with pytest.raises(OlxUpstreamError) as excinfo:
        await client.push_lead(lead_name="Fulana")

    assert "super-secret-key" not in str(excinfo.value)
    assert "***redacted***" in str(excinfo.value)


@pytest.mark.asyncio
async def test_real_client_rejects_a_non_json_2xx_body():
    http = _StubHttp(_StubResponse(200, "<html>maintenance</html>"))
    client = OlxLeadManagerClient("k", "a", http_client=http)

    with pytest.raises(OlxUpstreamError) as excinfo:
        await client.push_lead(lead_name="Fulana")

    assert excinfo.value.status == 502


def test_redact_secret_leaves_short_or_absent_secrets_alone():
    assert redact_secret("nothing here", None) == "nothing here"
    assert redact_secret("abc", "ab") == "abc"


# -- factory ---------------------------------------------------------------


def test_factory_selects_fake_or_real():
    assert isinstance(
        make_olx_lead_manager_client(use_fake=True), FakeOlxLeadManagerClient
    )
    assert isinstance(
        make_olx_lead_manager_client(api_key="k", agent_name="a"), OlxLeadManagerClient
    )


def test_factory_real_branch_without_credentials_does_not_raise():
    client = make_olx_lead_manager_client()

    assert isinstance(client, OlxLeadManagerClient)
    assert client.configured is False
