"""`ImovelWebLead` → unified-lead payload.

The load-bearing assertions here are the three refusals: no invented date,
no invented broker, no CPF.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from noctusai_lib.integrations.imovelweb.normalizers import (
    IMOVELWEB_DEFAULT_SOURCE_SLUG,
    IMOVELWEB_PIPE,
    imovelweb_lead_to_lead_payload,
    imovelweb_timestamp_to_date,
    render_observacoes,
    resolve_source_slug,
)
from noctusai_lib.integrations.imovelweb.types import ImovelWebLead

_LOGGER = "noctusai_lib.integrations.imovelweb.normalizers"


def _lead(**overrides) -> ImovelWebLead:
    base = dict(
        event_id="evt-1",
        event_type="CONTACTO_MENSAJE",
        timestamp="2026-08-17T10:00:00.000-0300",
        name="Fulano",
        email="fulano@example.com",
        ddd="31",
        phone="+5531999998888",
        client_listing_id="AP-1024",
    )
    base.update(overrides)
    return ImovelWebLead(**base)


class TestResolveSourceSlug:
    def test_maps_known_portals(self):
        assert resolve_source_slug("Imovelweb") == "imovel-web"
        assert resolve_source_slug("CasaMineira") == "casa-mineira"

    def test_tolerates_surrounding_whitespace(self):
        assert resolve_source_slug("  Imovelweb  ") == "imovel-web"

    def test_absent_origin_falls_back_without_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert resolve_source_slug(None) == IMOVELWEB_DEFAULT_SOURCE_SLUG
        assert caplog.text == ""

    def test_wimoveis_folds_into_imovel_web_and_warns(self, caplog):
        # Deliberate: `wimoveis` has no lead_sources row and no observed BR
        # traffic. Minting a slug for an unseen value would record a guess
        # in Portal ROI as if it were data.
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert resolve_source_slug("Wimoveis") == IMOVELWEB_DEFAULT_SOURCE_SLUG
        assert "Wimoveis" in caplog.text

    def test_unknown_origin_falls_back_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert resolve_source_slug("PortalNovo") == IMOVELWEB_DEFAULT_SOURCE_SLUG
        assert "PortalNovo" in caplog.text


class TestPipeVsPortalSeparation:
    """`external_source` is the PIPE and never varies; `origem_id` is the
    portal. Conflating them turns a re-delivery into a duplicate row,
    because `external_source` is half of the unique index."""

    def test_external_source_is_constant_across_portals(self):
        for origin in ("Imovelweb", "CasaMineira", "Wimoveis", None, "Unknown"):
            payload = imovelweb_lead_to_lead_payload(
                _lead(lead_origin=origin), origem_source_id="src-1"
            )
            assert payload["external_source"] == IMOVELWEB_PIPE

    def test_origem_id_is_the_caller_resolved_portal_row(self):
        payload = imovelweb_lead_to_lead_payload(
            _lead(lead_origin="CasaMineira"), origem_source_id="src-casa"
        )
        assert payload["origem_id"] == "src-casa"

    def test_external_lead_id_is_the_event_not_the_contact(self):
        # One Navent contact fans out to several events; keying on the
        # contact would silently collapse distinct leads.
        payload = imovelweb_lead_to_lead_payload(
            _lead(event_id="evt-A", origin_lead_id="contact-1"),
            origem_source_id="src-1",
        )
        assert payload["external_lead_id"] == "evt-A"

    def test_origem_raw_preserves_the_true_portal_name(self):
        payload = imovelweb_lead_to_lead_payload(
            _lead(lead_origin="Wimoveis"), origem_source_id="src-1"
        )
        assert "Wimoveis" in payload["origem_raw"]


class TestRefusals:
    def test_raises_rather_than_inventing_a_date(self):
        with pytest.raises(ValueError, match="refusing to guess"):
            imovelweb_lead_to_lead_payload(
                _lead(timestamp=None), origem_source_id="src-1"
            )

    def test_raises_on_unparseable_timestamp(self):
        with pytest.raises(ValueError, match="refusing to guess"):
            imovelweb_lead_to_lead_payload(
                _lead(timestamp="not a date"), origem_source_id="src-1"
            )

    def test_never_assigns_a_corretor(self):
        payload = imovelweb_lead_to_lead_payload(_lead(), origem_source_id="src-1")
        assert "corretor_id" not in payload

    def test_cpf_never_reaches_the_projection(self):
        lead = _lead(identification_id="12345678901")
        payload = imovelweb_lead_to_lead_payload(lead, origem_source_id="src-1")
        assert "identification_id" not in payload
        assert "12345678901" not in str(payload)

    def test_cpf_never_reaches_observacoes(self):
        lead = _lead(identification_id="12345678901", message="oi")
        assert "12345678901" not in (render_observacoes(lead) or "")


class TestPayloadShape:
    def test_maps_the_expected_fields(self):
        payload = imovelweb_lead_to_lead_payload(_lead(), origem_source_id="src-1")
        assert payload["cliente_nome"] == "Fulano"
        assert payload["codigo_imovel"] == "AP-1024"
        assert payload["tipo_lead"] == "novo"
        assert payload["data_entrada"] == date(2026, 8, 17)

    def test_contato_prefers_phone_over_email(self):
        payload = imovelweb_lead_to_lead_payload(_lead(), origem_source_id="src-1")
        assert payload["contato"] == "+5531999998888"

    def test_ddd_is_not_prefixed_onto_an_international_number(self):
        # The vendor documents `phone` as international-with-+ AND
        # `phoneNumber` as "ddd + phone". Both cannot be true. Blind
        # concatenation yields `31+5531999998888`, which dials nowhere.
        lead = _lead(ddd="31", phone="+5531999998888", phone_number=None)
        assert lead.full_phone == "+5531999998888"

    def test_ddd_is_not_doubled_when_phone_already_carries_it(self):
        lead = _lead(ddd="31", phone="31999998888", phone_number=None)
        assert lead.full_phone == "31999998888"

    def test_ddd_is_prefixed_onto_a_bare_local_number(self):
        lead = _lead(ddd="31", phone="999998888", phone_number=None)
        assert lead.full_phone == "31999998888"

    def test_phone_number_wins_when_present(self):
        lead = _lead(ddd="31", phone="999998888", phone_number="31999997777")
        assert lead.full_phone == "31999997777"

    def test_ddd_alone_is_better_than_nothing(self):
        lead = _lead(ddd="31", phone=None, phone_number=None)
        assert lead.full_phone == "31"

    def test_no_phone_fields_at_all_yields_none(self):
        lead = _lead(ddd=None, phone=None, phone_number=None)
        assert lead.full_phone is None

    def test_contato_falls_back_to_email(self):
        payload = imovelweb_lead_to_lead_payload(
            _lead(phone=None, phone_number=None, ddd=None), origem_source_id="src-1"
        )
        assert payload["contato"] == "fulano@example.com"

    def test_missing_client_listing_id_is_not_an_error(self):
        # Unlike Grupo OLX, this vendor documents no requeue path for it.
        payload = imovelweb_lead_to_lead_payload(
            _lead(client_listing_id=None), origem_source_id="src-1"
        )
        assert payload["codigo_imovel"] is None


class TestTimestampToDate:
    @pytest.mark.parametrize(
        "stamp,expected",
        [
            ("2026-08-17T21:30:00.000-0300", date(2026, 8, 17)),
            ("2026-08-17T21:30:00.000-03:00", date(2026, 8, 17)),
            ("2026-08-17T21:30:00.000Z", date(2026, 8, 17)),
            ("2026-08-17T21:30:00.000+0000", date(2026, 8, 17)),
            ("2026-08-17T21:30:00.000", date(2026, 8, 17)),
            ("2026-08-17", date(2026, 8, 17)),
        ],
    )
    def test_parses_every_documented_shape(self, stamp, expected):
        assert imovelweb_timestamp_to_date(stamp) == expected

    def test_evening_lead_keeps_the_sellers_date_not_utcs(self):
        # 23:30 BRT is already the NEXT day in UTC. Normalising to UTC
        # before taking .date() would move this lead a day forward in
        # Portal ROI — the exact bug the function is written to avoid.
        assert imovelweb_timestamp_to_date(
            "2026-08-17T23:30:00.000-0300"
        ) == date(2026, 8, 17)

    def test_accepts_date_and_datetime_objects(self):
        from datetime import datetime

        assert imovelweb_timestamp_to_date(date(2026, 1, 2)) == date(2026, 1, 2)
        assert imovelweb_timestamp_to_date(
            datetime(2026, 1, 2, 3, 4)
        ) == date(2026, 1, 2)

    @pytest.mark.parametrize("bad", [None, "", "   ", "nope", 12345, {}])
    def test_returns_none_rather_than_guessing(self, bad):
        assert imovelweb_timestamp_to_date(bad) is None


class TestRenderObservacoes:
    def test_returns_none_when_there_is_nothing_to_show(self):
        assert render_observacoes(ImovelWebLead(event_id="e", event_type="CONTACTO")) is None

    def test_includes_message_and_context(self):
        text = render_observacoes(
            _lead(message="Tenho interesse", lead_origin="Imovelweb",
                  contact_type_id=1, internal_reference="IMOB-1")
        )
        assert "Tenho interesse" in text
        assert "CONSULTA" in text
        assert "Imovelweb" in text
        assert "IMOB-1" in text

    def test_uncatalogued_contact_type_is_shown_as_such(self):
        text = render_observacoes(_lead(contact_type_id=999))
        assert "999" in text
        assert "não catalogado" in text
