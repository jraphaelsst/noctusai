"""Smoke + behaviour tests for the OLX connector MCP.

No network to OLX: the outbound client is swapped through the DI seam
(`olx.client.configure_client`), and the receiver-facing simulator is
exercised against a patched `urlopen` at the EXTERNAL boundary — never
against our own code.

Pins, per the connector contract:
- the exact registered tool-name set (a silent addition fails here),
- 3-segment dotted naming under the `olx.*` umbrella,
- the confirm gate on every write, proven by injecting a client that
  raises on ANY call — so "gated" means "no side effect", not "returned
  an error afterwards",
- gated-capability honesty: unconfigured ⇒ typed 424, never faked,
- the contract tools work with NO credentials at all,
- the probe reports `unverified` rather than inventing an expectation.
"""
from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from olx import api, client, settings as settings_module
from olx.tools import all_descriptors, all_handlers
from olx.tools import diagnostics, leads, webhook

EXPECTED_TOOLS = {
    "olx.contract.diff_observed",
    "olx.diagnostics.connection_status",
    "olx.diagnostics.list_known_endpoints",
    "olx.diagnostics.probe",
    "olx.leads.push",
    "olx.webhook.describe_contract",
    "olx.webhook.record_delivery",
    "olx.webhook.simulate",
    "olx.webhook.validate_payload",
}

WRITE_TOOLS = {
    "olx.leads.push",
    "olx.webhook.record_delivery",
    "olx.webhook.simulate",
}


def run(coro):
    return asyncio.run(coro)


class _ExplodingClient:
    """Any call is a test failure — proves the gate stops BEFORE effect."""

    async def push_lead(self, **kwargs):
        raise AssertionError("confirm gate did not stop the write")

    async def connection_status(self):
        raise AssertionError("confirm gate did not stop the write")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Never touch the real corpus, the real client, or a real .env."""
    client.configure_client(None)
    client.configure_corpus_dir(tmp_path / "observed")
    for var in ("OLX_API_KEY", "OLX_AGENT_NAME", "OLX_WEBHOOK_SECRET",
                "OLX_RECEIVER_URL"):
        monkeypatch.delenv(var, raising=False)
    settings_module.get_settings.cache_clear()
    yield
    client.configure_client(None)
    client.configure_corpus_dir(None)
    settings_module.get_settings.cache_clear()


def _configured(**overrides):
    """A settings object with credentials, for patching get_settings."""
    base = settings_module.OlxConnectorSettings(
        api_key="test-key",
        agent_name="test-agent",
        webhook_secret="test-secret",
        receiver_url="https://receiver.test/api/portals/olx/leads",
    )
    return replace(base, **overrides) if overrides else base


# -- registry ---------------------------------------------------------------


def test_registry_exposes_exactly_the_expected_tools():
    assert set(all_handlers().keys()) == EXPECTED_TOOLS


def test_descriptors_and_handlers_agree():
    assert {d.name for d in all_descriptors()} == set(all_handlers().keys())


def test_every_tool_name_is_three_dotted_segments_under_olx():
    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, name
        assert parts[0] == "olx", name


def test_every_descriptor_carries_an_input_schema():
    for descriptor in all_descriptors():
        assert descriptor.inputSchema.get("type") == "object", descriptor.name


# -- the contract tools need no credentials ---------------------------------


def test_describe_contract_works_unconfigured():
    result = run(webhook.describe_contract({}))

    assert result["contract"]["auth"]["scheme"] == "http_basic"
    assert result["contract"]["retry_policy"]["max_attempts"] == 3
    assert any(f["name"] == "originLeadId" for f in result["contract"]["fields"])


def test_describe_contract_admits_it_is_unverified():
    """The connector exists BECAUSE the contract is unverified. Reporting
    it as fact would defeat the purpose."""
    result = run(webhook.describe_contract({}))

    assert result["verified_against_live_traffic"] is False


def test_validate_payload_accepts_the_vendor_sample():
    from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

    result = run(webhook.validate_payload({"payload": OLX_SAMPLE_LEAD}))

    assert result["valid"] is True
    assert result["would_return_4xx"] is False
    assert result["parsed"]["origin_lead_id"] == "59ee0fc6e4b043e1b2a6d863"


def test_validate_payload_flags_the_one_documented_4xx_case():
    from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

    body = dict(OLX_SAMPLE_LEAD)
    body.pop("clientListingId")

    result = run(webhook.validate_payload({"payload": body}))

    assert result["would_return_4xx"] is True


def test_validate_payload_does_not_demand_a_4xx_for_a_mere_warning():
    """An unknown enum value must stay a 2xx — a 4xx costs the lead."""
    from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

    body = dict(OLX_SAMPLE_LEAD, temperature="Escaldante")

    result = run(webhook.validate_payload({"payload": body}))

    assert result["would_return_4xx"] is False
    assert result["valid"] is True
    assert result["violations"]


# -- confirm gate -----------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(WRITE_TOOLS))
def test_every_write_tool_refuses_without_confirm(tool_name):
    client.configure_client(_ExplodingClient())
    handler = all_handlers()[tool_name]
    args = {
        "olx.leads.push": {"lead_name": "Fulana"},
        "olx.webhook.record_delivery": {"payload": {"originLeadId": "x"}},
        "olx.webhook.simulate": {},
    }[tool_name]

    result = run(handler(args))

    assert result["error"]["status"] == 412
    assert result["error"]["error_class"] == "ConfirmationRequiredError"


def test_record_delivery_writes_nothing_without_confirm():
    run(webhook.record_delivery({"payload": {"originLeadId": "abc"}}))

    assert list(client.corpus_dir().glob("*.json")) == [] if client.corpus_dir().exists() else True


# -- gated-capability honesty -----------------------------------------------


def test_push_unconfigured_returns_424_not_a_fake_success():
    result = run(leads.push({"lead_name": "Fulana", "confirm": True}))

    assert result["pushed"] is False
    assert result["error"]["status"] == 424


def test_simulate_unconfigured_returns_424():
    result = run(webhook.simulate({"confirm": True}))

    assert result["sent"] is False
    assert result["error"]["status"] == 424


def test_connection_status_makes_no_call_and_names_what_is_missing():
    result = run(diagnostics.connection_status({}))

    assert result["ok"] is False
    assert result["lead_manager_configured"] is False
    assert result["receiver_configured"] is False
    assert "OLX_API_KEY" in result["next_step"]
    assert "OLX_WEBHOOK_SECRET" in result["next_step"]


def test_connection_status_reports_configured_when_credentials_exist():
    with patch.object(diagnostics, "get_settings", lambda: _configured()):
        result = run(diagnostics.connection_status({}))

    assert result["ok"] is True
    assert result["has_api_key"] is True
    assert result["contract_verified"] is False


# -- outbound push ----------------------------------------------------------


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def push_lead(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "OK"}


def test_push_forwards_every_documented_field():
    recorder = _RecordingClient()
    client.configure_client(recorder)

    result = run(leads.push({
        "lead_name": "Fulana", "lead_email": "f@example.com",
        "lead_telephone": "11999999999", "message": "oi",
        "external_id": "noc-1", "business_type": "SALE",
        "broker_email": "b@example.com", "lead_origin": "NoctusAI",
        "confirm": True,
    }))

    assert result["pushed"] is True
    assert recorder.calls[0]["lead_name"] == "Fulana"
    assert recorder.calls[0]["business_type"] == "SALE"


def test_push_surfaces_the_vocabulary_mistake_as_a_typed_error():
    """SELL is the INBOUND webhook's word; addLeads wants SALE. This is a
    genuinely easy mistake given both live in this connector."""
    from noctusai_lib.integrations.olx import FakeOlxLeadManagerClient

    client.configure_client(FakeOlxLeadManagerClient())

    result = run(leads.push({
        "lead_name": "Fulana", "business_type": "SELL", "confirm": True,
    }))

    assert result["pushed"] is False
    assert "SALE" in result["error"]["message"]


# -- record + diff (the doc-vs-reality loop) --------------------------------


def test_record_delivery_then_diff_reports_clean_for_a_conforming_body():
    from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

    recorded = run(webhook.record_delivery({
        "payload": OLX_SAMPLE_LEAD, "label": "vendor sample", "confirm": True,
    }))
    assert recorded["recorded"] is True
    assert recorded["corpus_size"] == 1

    report = run(webhook.contract_diff_observed({}))

    assert report["clean"] is True
    assert report["corpus_size"] == 1


def test_diff_on_an_empty_corpus_says_it_proves_nothing():
    """`clean: true` on zero evidence would be the most dangerous output
    this connector could produce."""
    report = run(webhook.contract_diff_observed({}))

    assert report["corpus_size"] == 0
    assert report["clean"] is False
    assert "proves nothing" in report["next_step"]


def test_diff_surfaces_a_divergent_live_body():
    from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD

    body = dict(OLX_SAMPLE_LEAD, vendorAddedThis="surprise")
    run(webhook.record_delivery({"payload": body, "confirm": True}))

    report = run(webhook.contract_diff_observed({}))

    assert report["clean"] is False
    assert "vendorAddedThis" in report["report"]["undocumented_fields"]
    assert "contract.py FIRST" in report["next_step"]


def test_record_delivery_keeps_an_unparseable_body():
    """The bodies our receiver would DROP are the most valuable evidence,
    so they must not be the ones the recorder refuses."""
    result = run(webhook.record_delivery({"payload": {"no": "id"}, "confirm": True}))

    assert result["recorded"] is True
    assert result["origin_lead_id"] is None
    assert Path(result["path"]).exists()


# -- simulate ---------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_simulate_posts_a_basic_authenticated_lead_and_interprets_the_status():
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        return _FakeHttpResponse(200)

    with patch.object(webhook, "get_settings", lambda: _configured()), \
            patch.object(webhook.urllib.request, "urlopen", _fake_urlopen):
        result = run(webhook.simulate({"confirm": True}))

    assert result["sent"] is True
    assert result["http_status"] == 200
    assert "delivered" in result["interpretation"]

    authorization = captured["headers"]["Authorization"]
    decoded = base64.b64decode(authorization.split(" ", 1)[1]).decode()
    assert decoded == "vivareal:test-secret"
    assert captured["body"]["originLeadId"]


def test_simulate_can_rehearse_the_wrong_secret_path():
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        return _FakeHttpResponse(401)

    with patch.object(webhook, "get_settings", lambda: _configured()), \
            patch.object(webhook.urllib.request, "urlopen", _fake_urlopen):
        result = run(webhook.simulate({"confirm": True, "wrong_secret": True}))

    decoded = base64.b64decode(
        captured["headers"]["Authorization"].split(" ", 1)[1]
    ).decode()
    assert decoded != "vivareal:test-secret"
    assert result["http_status"] == 401
    assert "FAILURE" in result["interpretation"]
    assert "discards it permanently" in result["interpretation"]


def test_simulate_can_build_an_mcmv_lead_without_listing_ids():
    def _fake_urlopen(request, timeout=None):
        _fake_urlopen.body = json.loads(request.data.decode())
        return _FakeHttpResponse(200)

    with patch.object(webhook, "get_settings", lambda: _configured()), \
            patch.object(webhook.urllib.request, "urlopen", _fake_urlopen):
        run(webhook.simulate({"confirm": True, "mcmv": True}))

    assert "clientListingId" not in _fake_urlopen.body
    assert _fake_urlopen.body["leadOrigin"] == "MCMV_OLX"


def test_simulate_reports_an_http_error_status_as_a_result_not_an_error():
    """A 4xx from our receiver is the ANSWER the operator asked for."""
    import urllib.error

    def _fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 422, "nope", {}, None)

    with patch.object(webhook, "get_settings", lambda: _configured()), \
            patch.object(webhook.urllib.request, "urlopen", _fake_urlopen):
        result = run(webhook.simulate({"confirm": True}))

    assert result["sent"] is True
    assert result["http_status"] == 422
    assert result["error"] is None


def test_simulate_reports_an_unreachable_receiver_as_an_error():
    import urllib.error

    def _fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    with patch.object(webhook, "get_settings", lambda: _configured()), \
            patch.object(webhook.urllib.request, "urlopen", _fake_urlopen):
        result = run(webhook.simulate({"confirm": True}))

    assert result["sent"] is False
    assert result["error"]["status"] == 502


# -- diagnostics: probe + catalog -------------------------------------------


def test_probe_classifies_unrecorded_expectations_as_unverified():
    """Not `as_expected: true` against a number we invented."""
    def _fake_urlopen(request, timeout=None):
        return _FakeHttpResponse(405)

    with patch.object(diagnostics, "get_settings", lambda: _configured()), \
            patch.object(diagnostics.urllib.request, "urlopen", _fake_urlopen):
        result = run(diagnostics.probe({}))

    assert result["probed"] is True
    assert result["unexpected"] == []
    assert result["unverified"]
    row = result["unverified"][0]
    assert row["observed_http_status"] == 405
    assert row["as_expected"] is None
    assert "No expectation recorded yet" in row["action"]


def test_probe_skips_the_inbound_row_rather_than_calling_ourselves():
    def _fake_urlopen(request, timeout=None):
        return _FakeHttpResponse(405)

    with patch.object(diagnostics, "get_settings", lambda: _configured()), \
            patch.object(diagnostics.urllib.request, "urlopen", _fake_urlopen):
        result = run(diagnostics.probe({}))

    inbound = [r for r in result["results"] if r["probe_status"] == "inbound"]
    assert inbound
    assert inbound[0]["skipped"]
    assert inbound[0]["observed_http_status"] is None


def test_list_known_endpoints_matches_the_probe_baseline():
    """Catalog and probe read the same tuple, so they cannot disagree."""
    catalog = run(diagnostics.list_known_endpoints({}))

    from noctusai_lib.integrations.olx import OLX_ENDPOINT_BASELINE

    assert len(catalog["endpoints"]) == len(OLX_ENDPOINT_BASELINE)
    assert catalog["endpoints"][0]["tool"] == "olx.leads.push"


def test_list_known_endpoints_carries_the_unblocking_contacts():
    """An agent told to unblock the integration should not have to go
    hunting for the email address."""
    catalog = run(diagnostics.list_known_endpoints({}))

    assert "integracaoleads@grupozap.com" in catalog["support_contacts"].values()
    assert "atendimento@imovelweb.com.br" in catalog["support_contacts"].values()
    assert "endpoint_validator" in catalog["reference_urls"]


# -- input strictness -------------------------------------------------------


def test_unknown_argument_is_rejected_loudly():
    """extra='forbid' — a typo'd argument must not be silently ignored."""
    with pytest.raises(Exception):
        run(webhook.validate_payload({"payload": {}, "paylod": {}}))
