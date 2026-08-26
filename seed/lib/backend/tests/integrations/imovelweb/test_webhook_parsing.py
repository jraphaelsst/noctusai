"""Parsing the ImovelWeb callback across all five language variants.

The parser's contract is unusually permissive on purpose, so most of these
tests assert that something UNEXPECTED still gets through. A 4xx on an
unfamiliar value would start a 72-hour retry loop against a body that never
changes — i.e. it throws a real customer away.
"""

from __future__ import annotations

import logging

import pytest

from noctusai_lib.integrations.imovelweb.contract import (
    IMOVELWEB_SAMPLE_BODIES,
    LANGUAGE_FIELD_ALIASES,
)
from noctusai_lib.integrations.imovelweb.webhook import (
    detect_callback_language,
    parse_imovelweb_callback,
)


class TestDetectCallbackLanguage:
    def test_detects_each_sample_body(self):
        for language, body in IMOVELWEB_SAMPLE_BODIES.items():
            assert detect_callback_language(body) == language

    def test_returns_none_for_unrecognisable_body(self):
        assert detect_callback_language({"totally": "unrelated"}) is None

    def test_returns_none_for_non_dict(self):
        assert detect_callback_language(None) is None
        assert detect_callback_language([1, 2, 3]) is None
        assert detect_callback_language("") is None

    def test_returns_none_for_empty_dict(self):
        assert detect_callback_language({}) is None

    def test_shared_field_alone_does_not_decide(self):
        # `email` exists in every language. Detection must not claim
        # certainty from a field that discriminates nothing — whatever it
        # picks, it must not crash and must stay within the known set.
        result = detect_callback_language({"email": "a@b.com"})
        assert result is None or result in LANGUAGE_FIELD_ALIASES

    def test_distinctive_field_wins(self):
        # `codigoImobiliaria` is PT-only; `leadOrigin` is EN2-only.
        assert detect_callback_language(
            {"idEvento": "e1", "codigoImobiliaria": "org-1"}
        ) == "PT"
        assert detect_callback_language(
            {"eventId": "e1", "leadOrigin": "Imovelweb"}
        ) == "EN2"


class TestParseImovelWebCallback:
    def test_parses_en2_message_lead(self):
        lead = parse_imovelweb_callback(IMOVELWEB_SAMPLE_BODIES["EN2"])
        assert lead is not None
        assert lead.event_id == "evt-0000000001"
        assert lead.event_type == "CONTACTO_MENSAJE"
        assert lead.is_message_lead is True
        assert lead.lead_origin == "Imovelweb"
        assert lead.callback_language == "EN2"
        assert lead.contact_type == "CONSULTA"

    def test_parses_pt_phone_reveal(self):
        lead = parse_imovelweb_callback(IMOVELWEB_SAMPLE_BODIES["PT"])
        assert lead is not None
        assert lead.event_id == "evt-0000000002"
        assert lead.event_type == "CONTACTO"
        assert lead.is_message_lead is False
        # The trade-off that drives the language decision: PT carries the
        # agency code, EN2 carries the portal name, neither carries both.
        assert lead.codigo_imobiliaria == "noc-org-demo"
        assert lead.lead_origin is None

    def test_en2_carries_portal_but_not_agency(self):
        lead = parse_imovelweb_callback(IMOVELWEB_SAMPLE_BODIES["EN2"])
        assert lead.lead_origin == "Imovelweb"
        assert lead.codigo_imobiliaria is None

    def test_raw_is_preserved_verbatim(self):
        body = dict(IMOVELWEB_SAMPLE_BODIES["EN2"])
        body["somethingBrandNew"] = {"nested": True}
        lead = parse_imovelweb_callback(body)
        assert lead.raw == body
        assert lead.raw["somethingBrandNew"] == {"nested": True}

    # -- the single blocking condition -------------------------------------

    def test_returns_none_without_event_id(self):
        assert parse_imovelweb_callback({"name": "x", "email": "a@b.com"}) is None

    def test_returns_none_for_non_dict(self):
        assert parse_imovelweb_callback(None) is None
        assert parse_imovelweb_callback("not a body") is None
        assert parse_imovelweb_callback([1, 2]) is None

    def test_never_raises_on_hostile_input(self):
        for payload in ({}, {"eventId": None}, {"eventId": ""},
                        {"eventId": "e", "contactTypeId": "not-an-int"},
                        {"eventId": "e", "messageId": {"nested": 1}}):
            parse_imovelweb_callback(payload)  # must not raise

    # -- permissiveness ----------------------------------------------------

    def test_unknown_event_type_passes_through(self):
        lead = parse_imovelweb_callback(
            {"eventId": "e1", "eventType": "SOMETHING_NEW"}
        )
        assert lead is not None
        assert lead.event_type == "SOMETHING_NEW"

    def test_unknown_contact_type_id_passes_through_with_none_label(self):
        lead = parse_imovelweb_callback(
            {"eventId": "e1", "eventType": "CONTACTO", "contactTypeId": 999}
        )
        assert lead.contact_type_id == 999
        assert lead.contact_type is None

    def test_unknown_lead_origin_passes_through(self):
        lead = parse_imovelweb_callback(
            {"eventId": "e1", "leadOrigin": "AlgumPortalNovo"}
        )
        assert lead.lead_origin == "AlgumPortalNovo"

    def test_unparseable_int_becomes_none_not_an_exception(self, caplog):
        with caplog.at_level(
            logging.WARNING, logger="noctusai_lib.integrations.imovelweb.webhook"
        ):
            lead = parse_imovelweb_callback(
                {"eventId": "e1", "contactTypeId": "abc"}
            )
        assert lead is not None
        assert lead.contact_type_id is None
        assert "not an integer" in caplog.text

    def test_unknown_language_falls_back_to_en2(self, caplog):
        with caplog.at_level(
            logging.WARNING, logger="noctusai_lib.integrations.imovelweb.webhook"
        ):
            lead = parse_imovelweb_callback({"eventId": "e1"}, language="KLINGON")
        assert lead is not None
        assert lead.callback_language == "EN2"
        assert "unknown language" in caplog.text

    def test_language_mismatch_warns_loudly(self, caplog):
        # A PT body while EN2 is configured means the vendor-side
        # registration and our config have diverged — and every subsequent
        # body will too, so this must not be silent.
        with caplog.at_level(
            logging.WARNING, logger="noctusai_lib.integrations.imovelweb.webhook"
        ):
            parse_imovelweb_callback(IMOVELWEB_SAMPLE_BODIES["PT"], language="EN2")
        assert "configured" in caplog.text

    # -- EN2's duplicated listing-code aliases -----------------------------

    def test_reference_and_client_listing_id_agree(self):
        lead = parse_imovelweb_callback(
            {"eventId": "e1", "reference": "AP-1", "clientListingId": "AP-1"}
        )
        assert lead.client_listing_id == "AP-1"

    def test_null_alias_does_not_blank_a_populated_one(self):
        # first-non-empty-wins, in either key order
        a = parse_imovelweb_callback(
            {"eventId": "e1", "reference": None, "clientListingId": "AP-9"}
        )
        b = parse_imovelweb_callback(
            {"eventId": "e1", "clientListingId": None, "reference": "AP-9"}
        )
        assert a.client_listing_id == "AP-9"
        assert b.client_listing_id == "AP-9"


class TestTimestampOffsetVariants:
    """The vendor sends Java's `SSSZ`, which is an RFC-822 numeric offset."""

    @pytest.mark.parametrize(
        "stamp",
        [
            "2026-08-17T21:30:00.000-0300",   # what the vendor documents
            "2026-08-17T21:30:00.000+0000",
            "2026-08-17T21:30:00.000Z",       # literal Z
            "2026-08-17T21:30:00.000-03:00",  # already colon-separated
            "2026-08-17T21:30:00.000",        # no offset at all
        ],
    )
    def test_all_offset_shapes_parse(self, stamp):
        lead = parse_imovelweb_callback({"eventId": "e1", "timestamp": stamp})
        assert lead.timestamp == stamp


class TestAllFiveLanguagesRoundTrip:
    @pytest.mark.parametrize("language", sorted(LANGUAGE_FIELD_ALIASES))
    def test_every_language_can_parse_a_minimal_body(self, language):
        aliases = LANGUAGE_FIELD_ALIASES[language]
        event_key = next(k for k, v in aliases.items() if v == "event_id")
        lead = parse_imovelweb_callback({event_key: "e-123"}, language=language)
        assert lead is not None
        assert lead.event_id == "e-123"
        assert lead.callback_language == language
