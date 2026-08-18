"""Smoke + behaviour tests for the ImovelWeb connector MCP.

No network to the vendor: the client is swapped through the DI seam
(`imovelweb.client.configure_client`), and the two tools that legitimately
open a socket — `webhook.simulate` at OUR receiver and
`diagnostics.fetch_swagger` at a public spec endpoint — are exercised
against a patched `urlopen` at the EXTERNAL boundary, never against our
own code.

Pins, per the connector contract:

- the exact registered tool-name set (a silent addition fails here),
- 3-segment dotted naming under the `imovelweb.*` umbrella,
- the confirm gate on every write, proven by injecting a client that
  raises on ANY call — so "gated" means "no side effect", not "returned an
  error afterwards",
- gated-capability honesty: unconfigured ⇒ typed 424, never faked,
- the contract tools work with NO credentials and NO network at all,
- secrets never survive into a result, and a CPF is redacted by default,
- the integrator-wide write refuses an unreachable receiver URL and
  reports drift when the vendor stores something else,
- the sandbox guard refuses a production host.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from imovelweb import api, client, settings as settings_module
from imovelweb.tools import agencies, all_descriptors, all_handlers
from imovelweb.tools import callbacks, contract, diagnostics, leads, sandbox, webhook
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_PROD_BR,
    IMOVELWEB_SANDBOX_BR,
    CallbackConfig,
    FakeImovelWebClient,
    basic_credential,
)

EXPECTED_TOOLS = {
    "imovelweb.agencies.list",
    "imovelweb.callbacks.get_config",
    "imovelweb.callbacks.put_config",
    "imovelweb.callbacks.subscribe",
    "imovelweb.callbacks.unsubscribe",
    "imovelweb.contract.describe",
    "imovelweb.contract.diff_observed",
    "imovelweb.contract.validate_payload",
    "imovelweb.diagnostics.connection_status",
    "imovelweb.diagnostics.fetch_swagger",
    "imovelweb.diagnostics.list_known_endpoints",
    "imovelweb.diagnostics.probe",
    "imovelweb.leads.get_message",
    "imovelweb.leads.get_smartlead",
    "imovelweb.leads.list_contact_actions",
    "imovelweb.leads.list_messages",
    "imovelweb.sandbox.emit_event",
    "imovelweb.webhook.record_delivery",
    "imovelweb.webhook.simulate",
}

#: Every tool that can change something — vendor-side or on disk.
WRITE_TOOLS = {
    "imovelweb.callbacks.put_config": {},
    "imovelweb.callbacks.subscribe": {"event": "CONTACTO"},
    "imovelweb.callbacks.unsubscribe": {"event": "CONTACTO"},
    "imovelweb.sandbox.emit_event": {"codigo_imobiliaria": "noc-org-demo"},
    "imovelweb.webhook.record_delivery": {"payload": {"eventId": "e1"}},
    "imovelweb.webhook.simulate": {},
}

#: Tools that need vendor credentials, with minimal valid arguments.
CREDENTIALED_READS = {
    "imovelweb.callbacks.get_config": {},
    "imovelweb.agencies.list": {},
    "imovelweb.leads.get_message": {"id_mensaje": 1},
    "imovelweb.leads.list_messages": {"codigo_imobiliaria": "x", "from_date": "20260817"},
    "imovelweb.leads.get_smartlead": {"id_mensagem": 1},
    "imovelweb.leads.list_contact_actions": {},
}

RECEIVER_URL = "https://noc.example.com/api/portals/imovelweb/leads"
SECRET = "sup3r-secret-value"


def run(coro):
    return asyncio.run(coro)


class _ExplodingClient:
    """Any call is a test failure — proves the gate stops BEFORE effect."""

    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise AssertionError(f"gate did not stop the write; {name} was called")

        return _boom


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Never touch the real corpus, the real client, or a real .env.

    The dotenv loader is stubbed rather than merely clearing env vars: a
    developer with a populated `mcp/imovelweb/.env` would otherwise make
    the unconfigured-behaviour tests pass for the wrong reason, locally
    only, which is the worst kind of green.
    """
    monkeypatch.setattr("_kit.settings._load_dotenv", lambda path: {})
    client.configure_client(None)
    client.configure_http_client(None)
    client.configure_corpus_dir(tmp_path / "observed")
    for var in (
        "IMOVELWEB_CLIENT_ID", "IMOVELWEB_CLIENT_SECRET", "IMOVELWEB_WEBHOOK_SECRET",
        "IMOVELWEB_RECEIVER_URL", "IMOVELWEB_REGION", "IMOVELWEB_SANDBOX",
        "IMOVELWEB_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    settings_module.get_settings.cache_clear()
    yield
    client.configure_client(None)
    client.configure_http_client(None)
    client.configure_corpus_dir(None)
    settings_module.get_settings.cache_clear()


@pytest.fixture
def configured(monkeypatch):
    """Vendor credentials + our receiver, both present."""
    monkeypatch.setenv("IMOVELWEB_CLIENT_ID", "cid")
    monkeypatch.setenv("IMOVELWEB_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("IMOVELWEB_WEBHOOK_SECRET", "receiver-secret-value")
    monkeypatch.setenv("IMOVELWEB_RECEIVER_URL", RECEIVER_URL)
    monkeypatch.setenv("IMOVELWEB_SANDBOX", "true")
    settings_module.get_settings.cache_clear()
    return settings_module.get_settings()


def _fake(**kwargs) -> FakeImovelWebClient:
    kwargs.setdefault("base_url", IMOVELWEB_SANDBOX_BR)
    return FakeImovelWebClient(**kwargs)


# ── registry ──────────────────────────────────────────────────────────


class TestRegistry:
    def test_exact_tool_set(self):
        assert set(all_handlers()) == EXPECTED_TOOLS

    def test_every_handler_has_a_descriptor_and_vice_versa(self):
        assert {d.name for d in all_descriptors()} == set(all_handlers())

    def test_naming_is_three_dotted_segments_under_imovelweb(self):
        for name in all_handlers():
            head, _, rest = name.partition(".")
            assert head == "imovelweb"
            assert len(rest.split(".")) == 2, name

    def test_every_descriptor_carries_a_schema(self):
        for descriptor in all_descriptors():
            assert descriptor.inputSchema["type"] == "object"
            assert descriptor.description

    def test_write_tools_are_all_declared_here(self):
        # A new write tool that nobody added to WRITE_TOOLS would slip past
        # the confirm-gate test below, so the two lists are pinned to each
        # other rather than maintained independently.
        declared_writes = {
            d.name for d in all_descriptors() if "requires confirm=true" in d.description
        }
        assert declared_writes == set(WRITE_TOOLS)


# ── the confirm gate ──────────────────────────────────────────────────


class TestConfirmGate:
    @pytest.mark.parametrize("tool", sorted(WRITE_TOOLS))
    def test_refuses_without_confirm_and_makes_no_call(self, tool, configured):
        client.configure_client(_ExplodingClient())
        result = run(all_handlers()[tool](dict(WRITE_TOOLS[tool])))
        assert result["error"]["status"] == 412, tool
        assert "NO side-effect" in result["error"]["message"]

    def test_the_gate_precedes_configuration(self):
        # Unconfigured AND unconfirmed must report the gate, not 424:
        # otherwise an operator fixes credentials and then discovers the
        # write was going to happen all along.
        result = run(callbacks.put_config({}))
        assert result["error"]["status"] == 412

    def test_record_delivery_writes_nothing_when_gated(self):
        run(webhook.record_delivery({"payload": {"eventId": "e1"}}))
        assert list(client.corpus_dir().glob("*.json")) == []


# ── gated-capability honesty ──────────────────────────────────────────


class TestUnconfigured:
    @pytest.mark.parametrize("tool", sorted(CREDENTIALED_READS))
    def test_credentialed_reads_return_424_never_faked(self, tool):
        result = run(all_handlers()[tool](dict(CREDENTIALED_READS[tool])))
        assert result["error"]["status"] == 424, tool
        assert "integracao@imovelweb.com.br" in result["error"]["message"]

    def test_simulate_needs_the_receiver_half_not_the_api_half(self):
        result = run(webhook.simulate({"confirm": True}))
        assert result["error"]["status"] == 424
        assert "IMOVELWEB_RECEIVER_URL" in result["error"]["message"]

    def test_connection_status_makes_zero_api_calls(self):
        client.configure_client(_ExplodingClient())
        status = run(diagnostics.connection_status({}))
        assert status["ok"] is False
        assert status["api_configured"] is False
        assert status["contract_verified"] is False

    def test_connection_status_names_the_two_halves_separately(self, monkeypatch):
        monkeypatch.setenv("IMOVELWEB_CLIENT_ID", "cid")
        monkeypatch.setenv("IMOVELWEB_CLIENT_SECRET", SECRET)
        settings_module.get_settings.cache_clear()
        status = run(diagnostics.connection_status({}))
        assert status["api_configured"] is True
        assert status["receiver_configured"] is False
        assert "IMOVELWEB_RECEIVER_URL" in status["next_step"]

    def test_probe_reports_nothing_probed_without_a_host(self, monkeypatch):
        monkeypatch.setenv("IMOVELWEB_REGION", "atlantis")
        settings_module.get_settings.cache_clear()
        result = run(diagnostics.probe({}))
        assert result["probed"] is False
        assert result["results"] == []


# ── the zero-IO surface (works during an outage) ──────────────────────


class TestZeroIoContractTools:
    def test_describe_needs_no_credentials(self):
        result = run(contract.describe({}))
        assert result["contract"]["languages"]
        assert result["verified_against_live_traffic"] is False

    def test_describe_one_language_carries_a_json_schema(self):
        result = run(contract.describe({"language": "PT"}))
        assert result["json_schema"]["title"].endswith("(PT)")

    def test_an_unknown_language_is_the_callers_typo_not_an_empty_contract(self):
        result = run(contract.describe({"language": "KLINGON"}))
        assert "unknown language" in result["contract"]["error"]

    def test_validate_auto_detects_the_language(self):
        # A PT body read as EN2 would look like it has no fields at all.
        result = run(contract.validate_payload({"payload": {
            "idEvento": "evt-1", "tipoEvento": "CONTACTO",
            "codigoImobiliaria": "noc-org-demo", "email": "a@b.com",
        }}))
        assert result["detected_language"] == "PT"
        assert result["valid"] is True

    def test_no_event_id_is_the_only_blocking_violation(self):
        result = run(contract.validate_payload({"payload": {"eventType": "CONTACTO"}}))
        assert result["valid"] is False
        assert any("event id" in e for e in result["errors"])

    def test_a_missing_listing_code_is_a_warning_not_an_error(self):
        # A 4xx would requeue a real lead for 72 hours against a field that
        # will never arrive.
        result = run(contract.validate_payload({"payload": {
            "eventId": "e1", "eventType": "CONTACTO",
        }}))
        assert result["valid"] is True
        assert any("listing code" in w for w in result["warnings"])

    def test_the_parsed_projection_never_carries_the_cpf(self):
        result = run(contract.validate_payload({"payload": {
            "idEvento": "e1", "tipoEvento": "CONTACTO", "cpf": "12345678901",
        }}))
        assert "identification_id" not in result["parsed"]
        assert result["parsed"]["carries_national_id"] is True

    def test_an_empty_corpus_is_never_clean(self):
        result = run(contract.diff_observed({}))
        assert result["clean"] is False
        assert result["corpus_size"] == 0
        assert "proves nothing" in result["next_step"]

    def test_list_known_endpoints_exposes_the_unresolved_spellings(self):
        result = run(diagnostics.list_known_endpoints({}))
        assert "callback_config" in result["path_variants"]
        assert result["support_contacts"]["credentials_and_callbacks"]
        assert result["sandbox_window"]

    def test_no_baseline_row_claims_a_verified_expectation(self):
        # A guessed expectation makes the probe print `as_expected` for a
        # number we invented, and an operator who learns the report lies
        # stops reading it.
        result = run(diagnostics.list_known_endpoints({}))
        assert all(row["expected_http_status"] is None for row in result["endpoints"])


# ── redaction + PII ───────────────────────────────────────────────────


class TestRedaction:
    def test_a_secret_embedded_mid_string_is_stripped(self, configured):
        payload = {"detail": f"failed with client_secret={SECRET}"}
        redacted = api.redact(payload, configured)
        assert SECRET not in json.dumps(redacted)
        assert "REDACTED" in redacted["detail"]

    def test_an_unserializable_result_is_withheld_not_leaked(self, configured):
        class _Opaque:
            def __repr__(self):
                return f"<holds {SECRET}>"

        # `default=str` would stringify it THROUGH __repr__, so the guard
        # that matters is the one below: a value we cannot serialize is
        # never returned unredacted.
        assert SECRET not in json.dumps(api.redact({"x": _Opaque()}, configured))

    def test_the_vendor_secret_never_survives_a_tool_result(self, configured):
        fake = _fake()
        fake.inject_messages("ag-1", [{"idMensaje": 7, "texto": f"leaked {SECRET}"}])
        client.configure_client(fake)
        result = run(leads.get_message({"id_mensaje": 7}))
        assert SECRET not in json.dumps(result)

    def test_the_cpf_is_redacted_by_default(self, configured):
        fake = _fake()
        fake.inject_messages("ag-1", [{"idMensaje": 7, "identificationId": "12345678901"}])
        client.configure_client(fake)
        result = run(leads.get_message({"id_mensaje": 7}))
        assert result["message"]["identificationId"] == api.PII_PLACEHOLDER
        assert result["pii_redacted"] == 1

    def test_the_key_survives_so_the_finding_is_visible(self, configured):
        # Dropping the key would hide that the vendor sent a CPF at all,
        # which is itself the thing worth knowing.
        fake = _fake()
        fake.inject_messages("ag-1", [{"idMensaje": 7, "cpf": "12345678901"}])
        client.configure_client(fake)
        result = run(leads.get_message({"id_mensaje": 7}))
        assert "cpf" in result["message"]

    def test_include_pii_is_explicit_and_reported(self, configured):
        fake = _fake()
        fake.inject_messages("ag-1", [{"idMensaje": 7, "identificationId": "12345678901"}])
        client.configure_client(fake)
        result = run(leads.get_message({"id_mensaje": 7, "include_pii": True}))
        assert result["message"]["identificationId"] == "12345678901"
        assert result["pii_redacted"] == 0

    def test_nested_pii_is_reached(self):
        payload = {"contacto": {"cuestionarios": [{"dni": "X"}]}}
        stripped, count = api.strip_pii(payload)
        assert count == 1
        assert stripped["contacto"]["cuestionarios"][0]["dni"] == api.PII_PLACEHOLDER

    def test_smartlead_always_carries_its_lgpd_note(self, configured):
        client.configure_client(_fake())
        result = run(leads.get_smartlead({"id_mensagem": 1}))
        assert "Art. 20" in result["lgpd_note"]


# ── the integrator-wide write ─────────────────────────────────────────


class TestCallbackRegistration:
    def test_refuses_a_localhost_receiver_url(self, configured, monkeypatch):
        monkeypatch.setenv("IMOVELWEB_RECEIVER_URL", "http://localhost:8000/api")
        settings_module.get_settings.cache_clear()
        client.configure_client(_ExplodingClient())
        result = run(callbacks.put_config({"confirm": True}))
        assert result["error"]["status"] == 422
        assert "blackholes" in result["error"]["message"]

    def test_refuses_an_ephemeral_tunnel(self, configured, monkeypatch):
        monkeypatch.setenv("IMOVELWEB_RECEIVER_URL", "https://abc.ngrok-free.app/api")
        settings_module.get_settings.cache_clear()
        client.configure_client(_ExplodingClient())
        result = run(callbacks.put_config({"confirm": True}))
        assert result["error"]["status"] == 422

    def test_allow_local_url_registers_and_says_so(self, configured, monkeypatch):
        monkeypatch.setenv("IMOVELWEB_RECEIVER_URL", "http://localhost:8000/api")
        settings_module.get_settings.cache_clear()
        client.configure_client(_fake())
        result = run(callbacks.put_config({"confirm": True, "allow_local_url": True}))
        assert result["registered"] is True
        assert any("registered anyway" in w for w in result["warnings"])

    def test_registers_our_basic_credential(self, configured):
        fake = _fake()
        client.configure_client(fake)
        run(callbacks.put_config({"confirm": True}))
        assert fake.put_calls[0].authorization_header_value == basic_credential(
            "receiver-secret-value"
        )

    def test_the_credential_never_appears_in_the_result(self, configured):
        client.configure_client(_fake())
        result = run(callbacks.put_config({"confirm": True}))
        assert result["applied"]["authorizationHeaderValue"] == "***REDACTED***"

    def test_refuses_an_empty_subscription_list(self, configured):
        client.configure_client(_ExplodingClient())
        result = run(callbacks.put_config({"confirm": True, "subscriptions": []}))
        assert result["error"]["status"] == 422
        assert "delivers nothing" in result["error"]["message"]

    def test_warns_when_subscribing_to_a_write_scope_event(self, configured):
        client.configure_client(_fake())
        result = run(callbacks.put_config({
            "confirm": True, "subscriptions": ["CONTACTO", "AVISO_CALIDAD"],
        }))
        assert any("Read-and-Write" in w for w in result["warnings"])

    def test_reports_drift_when_the_vendor_drops_a_subscription(self, configured):
        class _DroppingClient(FakeImovelWebClient):
            """The real hazard: the PUT succeeds and the subscriptions are
            not stored. Invisible without a read-back."""

            async def put_callback_config(self, config):
                stripped = CallbackConfig(
                    url=config.url,
                    authorization_header_value=config.authorization_header_value,
                    authorization_header_key=config.authorization_header_key,
                    language=config.language,
                    subscriptions=("CONTACTO",),
                )
                await super().put_callback_config(stripped)
                return stripped

        client.configure_client(_DroppingClient(base_url=IMOVELWEB_SANDBOX_BR))
        result = run(callbacks.put_config({"confirm": True}))
        assert result["registered"] is True
        assert any("dropped" in d for d in result["drift"])

    def test_warns_loudly_when_nothing_is_subscribed_after_the_write(self, configured):
        class _SwallowingClient(FakeImovelWebClient):
            async def put_callback_config(self, config):
                return CallbackConfig(
                    url=config.url,
                    authorization_header_value=config.authorization_header_value,
                    subscriptions=(),
                )

        client.configure_client(_SwallowingClient(base_url=IMOVELWEB_SANDBOX_BR))
        result = run(callbacks.put_config({"confirm": True}))
        assert any("deliver nothing" in w for w in result["warnings"])

    def test_keeps_the_previous_config(self, configured):
        fake = _fake(callback_config=CallbackConfig(
            url="https://old.example.com/hook",
            authorization_header_value="Basic old",
        ))
        client.configure_client(fake)
        result = run(callbacks.put_config({"confirm": True}))
        assert result["previous"]["url"] == "https://old.example.com/hook"

    def test_says_so_when_the_previous_config_could_not_be_read(self, configured):
        class _NoReadClient(FakeImovelWebClient):
            async def get_callback_config(self):
                from noctusai_lib.integrations.imovelweb import ImovelWebUpstreamError

                raise ImovelWebUpstreamError("vendor down", status=503)

        client.configure_client(_NoReadClient(base_url=IMOVELWEB_SANDBOX_BR))
        result = run(callbacks.put_config({"confirm": True}))
        assert result["registered"] is True
        assert any("nothing to roll back to" in w for w in result["warnings"])

    def test_get_config_flags_the_silent_failure(self, configured):
        # Nothing registered reads as "no subscriptions", which is exactly
        # the state that reports perfect health and delivers nothing.
        client.configure_client(_fake())
        result = run(callbacks.get_config({}))
        assert result["delivers_nothing"] is True
        assert result["receiver_url_matches"] is False

    def test_get_config_confirms_a_matching_url(self, configured):
        client.configure_client(_fake(callback_config=CallbackConfig(
            url=RECEIVER_URL, authorization_header_value=basic_credential("x"),
        )))
        result = run(callbacks.get_config({}))
        assert result["receiver_url_matches"] is True
        assert result["delivers_nothing"] is False


class TestSubscriptions:
    def test_an_unknown_event_is_refused_not_passed_through(self, configured):
        client.configure_client(_fake())
        result = run(callbacks.subscribe({"event": "CONTACTOO", "confirm": True}))
        assert result["error"]["status"] == 422
        assert "never fires" in result["error"]["message"]

    def test_subscribe_reads_back_to_prove_it_stuck(self, configured):
        client.configure_client(_fake(callback_config=CallbackConfig(
            url=RECEIVER_URL,
            authorization_header_value=basic_credential("x"),
            subscriptions=("CONTACTO",),
        )))
        result = run(callbacks.subscribe({"event": "CONTACTO_MENSAJE", "confirm": True}))
        assert "CONTACTO_MENSAJE" in result["subscriptions"]

    def test_a_subscribe_that_did_not_stick_is_reported(self, configured):
        # The Fake only mutates a config that exists; with none registered
        # the subscribe succeeds and changes nothing — the exact silent
        # failure the read-back exists to catch.
        client.configure_client(_fake())
        result = run(callbacks.subscribe({"event": "CONTACTO", "confirm": True}))
        assert any("did not store it" in w for w in result["warnings"])

    def test_unsubscribing_the_last_event_warns(self, configured):
        client.configure_client(_fake(callback_config=CallbackConfig(
            url=RECEIVER_URL,
            authorization_header_value=basic_credential("x"),
            subscriptions=("CONTACTO",),
        )))
        result = run(callbacks.unsubscribe({"event": "CONTACTO", "confirm": True}))
        assert result["subscriptions"] == []
        assert any("delivers nothing" in w for w in result["warnings"])


# ── the sandbox guard ─────────────────────────────────────────────────


class TestSandboxGuard:
    def test_refuses_a_production_host(self, configured):
        client.configure_client(_fake(base_url=IMOVELWEB_PROD_BR))
        result = run(sandbox.emit_event({
            "codigo_imobiliaria": "ag-1", "event_type": "CONTACTO",
            "contact_email": "a@b.com", "confirm": True,
        }))
        assert result["emitted"] is False
        assert "indistinguishable from real customers" in result["error"]["message"]

    def test_emits_on_the_sandbox(self, configured):
        fake = _fake()
        client.configure_client(fake)
        result = run(sandbox.emit_event({
            "codigo_imobiliaria": "ag-1", "event_type": "CONTACTO",
            "contact_email": "a@b.com", "confirm": True,
        }))
        assert result["emitted"] is True
        assert fake.emitted[0]["codigoInmobiliaria"] == "ag-1"

    def test_a_partial_message_event_is_refused_before_any_call(self, configured):
        client.configure_client(_ExplodingClient())
        result = run(sandbox.emit_event({
            "codigo_imobiliaria": "ag-1", "contact_email": "a@b.com", "confirm": True,
        }))
        assert result["error"]["status"] == 422
        assert "proves the wrong thing" in result["error"]["message"]

    def test_an_unknown_event_type_is_refused(self, configured):
        client.configure_client(_ExplodingClient())
        result = run(sandbox.emit_event({
            "codigo_imobiliaria": "ag-1", "event_type": "NOPE", "confirm": True,
        }))
        assert result["error"]["status"] == 422

    def test_the_window_is_surfaced_rather_than_left_a_mystery(self, configured):
        class _TimingOut(FakeImovelWebClient):
            async def emit_event(self, payload):
                from noctusai_lib.integrations.imovelweb import ImovelWebUpstreamError

                raise ImovelWebUpstreamError("timed out")

        client.configure_client(_TimingOut(base_url=IMOVELWEB_SANDBOX_BR))
        result = run(sandbox.emit_event({
            "codigo_imobiliaria": "ag-1", "event_type": "CONTACTO",
            "contact_email": "a@b.com", "confirm": True,
        }))
        assert "07:00-21:00 UTC-3" in result["error"]["hint"]


# ── the corpus loop ───────────────────────────────────────────────────


class TestCorpusLoop:
    def test_record_then_diff(self, configured):
        run(webhook.record_delivery({
            "payload": {"eventId": "e1", "eventType": "CONTACTO"}, "confirm": True,
        }))
        result = run(contract.diff_observed({}))
        assert result["corpus_size"] == 1
        assert result["clean"] is True

    def test_an_undocumented_field_makes_the_corpus_unclean(self, configured):
        run(webhook.record_delivery({
            "payload": {"eventId": "e1", "surpriseField": 1}, "confirm": True,
        }))
        result = run(contract.diff_observed({}))
        assert result["clean"] is False
        assert "surpriseField" in result["report"]["undocumented_fields"]

    def test_an_unparseable_body_is_recorded_not_refused(self, configured):
        # It is the shape our receiver would drop, which makes it the most
        # valuable evidence in the corpus.
        result = run(webhook.record_delivery({"payload": {"junk": True}, "confirm": True}))
        assert result["recorded"] is True
        assert result["event_id"] is None
        assert "unparseable" in result["path"]

    def test_the_detected_language_is_recorded_with_the_body(self, configured):
        run(webhook.record_delivery({
            "payload": {"idEvento": "e1", "tipoEvento": "CONTACTO",
                        "codigoImobiliaria": "x"},
            "confirm": True,
        }))
        stored = json.loads(next(client.corpus_dir().glob("*.json")).read_text())
        assert stored["detected_language"] == "PT"


# ── the response budget ───────────────────────────────────────────────


class _Resp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"{}"


class TestSimulate:
    def test_posts_our_credential_and_reads_the_budget(self, configured):
        with patch("urllib.request.urlopen", return_value=_Resp(200)) as opened:
            result = run(webhook.simulate({"confirm": True}))
        request = opened.call_args[0][0]
        assert request.full_url == RECEIVER_URL
        assert request.get_header("Authorization") == basic_credential("receiver-secret-value")
        assert result["within_response_budget"] is True
        assert result["response_budget_ms"] == 1500.0

    def test_a_3xx_counts_as_delivered_for_this_vendor(self, configured):
        with patch("urllib.request.urlopen", return_value=_Resp(302)):
            result = run(webhook.simulate({"confirm": True}))
        assert "delivered" in result["interpretation"]

    def test_a_4xx_explains_the_72_hour_loop(self, configured):
        import urllib.error

        error = urllib.error.HTTPError(RECEIVER_URL, 401, "no", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            result = run(webhook.simulate({"confirm": True}))
        assert result["http_status"] == 401
        assert "VENCIDO" in result["interpretation"]

    def test_wrong_secret_sends_a_different_credential(self, configured):
        with patch("urllib.request.urlopen", return_value=_Resp(401)) as opened:
            run(webhook.simulate({"confirm": True, "wrong_secret": True}))
        sent = opened.call_args[0][0].get_header("Authorization")
        assert sent != basic_credential("receiver-secret-value")

    def test_a_language_with_no_transcribed_sample_is_refused(self, configured):
        # Inventing a body would prove the receiver handles a shape we made
        # up, which is worse than proving nothing.
        result = run(webhook.simulate({"confirm": True, "language": "EN_SF"}))
        assert result["error"]["status"] == 422
        assert "rather than inventing one" in result["error"]["message"]

    def test_the_event_id_override_uses_the_right_wire_name(self, configured):
        with patch("urllib.request.urlopen", return_value=_Resp(200)):
            result = run(webhook.simulate({
                "confirm": True, "language": "PT", "event_id": "evt-override",
            }))
        assert result["payload"]["idEvento"] == "evt-override"


# ── the public spec ───────────────────────────────────────────────────


class _SpecResp(_Resp):
    def __init__(self, spec):
        super().__init__(200)
        self._spec = spec

    def read(self):
        return json.dumps(self._spec).encode()


class TestFetchSwagger:
    def _spec(self, paths, version="1.0"):
        return {"info": {"version": version, "title": "t"},
                "paths": {p: {} for p in paths}}

    def test_diffs_both_hosts_against_the_baseline(self):
        prod = _SpecResp(self._spec(["/v1/imobiliarias", "/v1/brand/new"], "2.105"))
        sandbox_spec = _SpecResp(self._spec(
            ["/v1/imobiliarias", "/v1/callbacks/geracao/eventos"], "ON-10172"
        ))
        with patch("urllib.request.urlopen", side_effect=[prod, sandbox_spec]):
            result = run(diagnostics.fetch_swagger({}))
        assert result["hosts"]["prod_br"]["spec_version"] == "2.105"
        assert "/v1/brand/new" in result["in_spec_not_in_baseline"]
        assert "/v1/imobiliarias" in result["confirmed"]
        assert "/v1/callbacks/geracao/eventos" in result["sandbox_only"]

    def test_parameter_spelling_does_not_read_as_drift(self):
        # The vendor spells the same parameter three ways across its own
        # surfaces; a diff that called those different endpoints would
        # report drift on every row and be ignored within a day.
        spec = _SpecResp(self._spec(["/v2/imobiliarias/{cod}/mensagens"]))
        with patch("urllib.request.urlopen", side_effect=[spec, spec]):
            result = run(diagnostics.fetch_swagger({}))
        assert "/v2/imobiliarias/{}/mensagens" in result["confirmed"]

    def test_a_non_json_200_is_reported_not_swallowed(self):
        with patch("urllib.request.urlopen", return_value=_Resp(200)) as opened:
            opened.return_value.read = lambda: b"<html>captive portal</html>"
            result = run(diagnostics.fetch_swagger({}))
        assert "not JSON" in result["hosts"]["prod_br"]["error"]

    def test_sends_an_identifying_user_agent(self):
        # The vendor's edge 403s `Python-urllib/*` — urllib's default — while
        # serving the same public URL to curl. Observed 2026-08-18. Without
        # this header the tool reports a network fault for a WAF rejection.
        spec = _SpecResp(self._spec(["/v1/imobiliarias"]))
        with patch("urllib.request.urlopen", side_effect=[spec, spec]) as opened:
            run(diagnostics.fetch_swagger({}))
        sent = opened.call_args[0][0].get_header("User-agent")
        assert sent and "urllib" not in sent
        assert "noctusai" in sent

    def test_probe_sends_it_too(self, monkeypatch):
        monkeypatch.setenv("IMOVELWEB_CLIENT_ID", "cid")
        monkeypatch.setenv("IMOVELWEB_CLIENT_SECRET", SECRET)
        settings_module.get_settings.cache_clear()
        with patch("urllib.request.urlopen", return_value=_Resp(401)) as opened:
            run(diagnostics.probe({}))
        assert "noctusai" in opened.call_args[0][0].get_header("User-agent")

    def test_a_403_is_named_an_edge_rejection_not_a_missing_spec(self):
        import urllib.error

        error = urllib.error.HTTPError("u", 403, "forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            result = run(diagnostics.fetch_swagger({}))
        # The spec needs no credentials, so "not served" would send an
        # operator hunting for a key that was never required.
        assert "edge refused" in result["hosts"]["prod_br"]["error"]
        assert "User-Agent" in result["next_step"]

    def test_unreachable_hosts_say_it_is_our_network_not_authorization(self):
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("dns")):
            result = run(diagnostics.fetch_swagger({}))
        assert "network or DNS on our side" in result["next_step"]


# ── the outage rule ───────────────────────────────────────────────────


class TestOutageResilience:
    def test_no_tool_module_reaches_a_model_provider(self):
        import pathlib

        import imovelweb.tools as package

        root = pathlib.Path(package.__file__).parent.parent
        offenders = []
        for path in sorted(root.rglob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                for needle in ("integrations.llm", "openai", "anthropic", "litellm"):
                    if needle in stripped:
                        offenders.append(f"{path.name}: {stripped}")
        assert offenders == [], (
            "the lead path must not reach a model provider — the vendor "
            f"allows 1.5 seconds to answer: {offenders}"
        )

    def test_the_contract_surface_needs_no_transport_library(self, monkeypatch):
        # httpx is imported lazily inside the client factory precisely so a
        # broken transport cannot take down the tools an operator reaches
        # for DURING an incident.
        import builtins

        real_import = builtins.__import__

        def _no_httpx(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("httpx is unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_httpx)
        assert run(contract.describe({}))["contract"]["languages"]
        assert run(diagnostics.list_known_endpoints({}))["endpoints"]
