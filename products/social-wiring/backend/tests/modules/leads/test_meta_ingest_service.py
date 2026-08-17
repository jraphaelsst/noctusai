"""Tests for ``services.meta_ingest_service`` — the Meta Lead-Ads ->
unified-``leads`` mapping (migration 041, Slice 3 of
`meta-ads-console-2026-07`).

Two layers, mirroring the module's own split:
- pure mapping (``map_meta_lead_to_lead_payload`` /
  ``render_answers_pt_br`` / corretor resolution) — no DB.
- DB-facing entry points (``ingest_meta_lead`` / ``backfill_meta_ads_leads``)
  against ``noctusai_lib.testing.MockSupabaseClient``, same
  ``_scoped_mock()`` idiom as ``test_dimensions_service.py``.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.modules.leads.services import dimensions_service, meta_ingest_service
from app.modules.leads.services.meta_ingest_service import (
    _resolve_corretor_from_answers,
    map_meta_lead_to_lead_payload,
    render_answers_pt_br,
)

ORG = UUID("00000000-0000-4000-8000-0000000000a1")


def _scoped_mock():
    db = MockSupabaseClient()
    return db.schema("social_wiring")


def _meta_lead(**overrides) -> dict:
    row = {
        "id": "ml-1",
        "org_id": str(ORG),
        "form_id": "f1",
        "campaign_name": "C10023",
        "created_time": "2026-07-27T10:00:00+00:00",
        "full_name": "Ana Souza",
        "email": "ana@example.com",
        "phone": "+5511994573387",
        "answers": {
            "Nome completo": "Ana Souza",
            "Email": "ana@example.com",
            "Telefone": "+5511994573387",
            "Faixa": "Até R$700 Mil",
        },
        "raw": [],
    }
    row.update(overrides)
    return row


# ─── pure mapping ────────────────────────────────────────────────────────


class TestMapMetaLeadToLeadPayload:
    def test_meta_lead_id_origem_and_tipo_lead(self):
        payload = map_meta_lead_to_lead_payload(_meta_lead(), origem_source_id="SRC1")
        assert payload["meta_lead_id"] == "ml-1"
        assert payload["origem_id"] == "SRC1"
        assert payload["tipo_lead"] == "novo"
        assert payload["data_entrada"].isoformat() == "2026-07-27"

    def test_missing_full_name_leaves_cliente_nome_none(self):
        payload = map_meta_lead_to_lead_payload(
            _meta_lead(full_name=None), origem_source_id="SRC1"
        )
        assert payload["cliente_nome"] is None
        # phone is untouched by the missing name
        assert payload["contato"] == "+5511994573387"

    def test_missing_phone_leaves_contato_none(self):
        payload = map_meta_lead_to_lead_payload(
            _meta_lead(phone=None), origem_source_id="SRC1"
        )
        assert payload["contato"] is None
        assert payload["cliente_nome"] == "Ana Souza"

    def test_empty_answers_yields_no_observacoes(self):
        payload = map_meta_lead_to_lead_payload(
            _meta_lead(answers={}), origem_source_id="SRC1"
        )
        assert payload["observacoes"] is None

    def test_null_campaign_leaves_origem_raw_none(self):
        payload = map_meta_lead_to_lead_payload(
            _meta_lead(campaign_name=None), origem_source_id="SRC1"
        )
        assert payload["origem_raw"] is None

    def test_missing_created_time_raises_value_error(self):
        with pytest.raises(ValueError):
            map_meta_lead_to_lead_payload(
                _meta_lead(created_time=None), origem_source_id="SRC1"
            )

    def test_unparseable_created_time_raises_value_error(self):
        with pytest.raises(ValueError):
            map_meta_lead_to_lead_payload(
                _meta_lead(created_time="not-a-date"), origem_source_id="SRC1"
            )

    def test_missing_id_raises_value_error(self):
        with pytest.raises(ValueError):
            map_meta_lead_to_lead_payload(_meta_lead(id=None), origem_source_id="SRC1")


class TestRenderAnswersPtBr:
    def test_excludes_promoted_question_types(self):
        rendered = render_answers_pt_br(
            {"nome": "Ana", "faixa": "Até R$700 Mil"},
            question_types={"nome": "FULL_NAME", "faixa": "CUSTOM"},
            question_labels={"faixa": "Faixa de investimento"},
        )
        assert rendered == "Faixa de investimento: Até R$700 Mil"

    def test_falls_back_to_raw_key_when_no_label_or_type_map(self):
        rendered = render_answers_pt_br({"faixa": "Até R$700 Mil"})
        assert rendered == "faixa: Até R$700 Mil"

    def test_list_values_join_with_comma(self):
        rendered = render_answers_pt_br({"interesses": ["Apartamento", "Casa"]})
        assert rendered == "interesses: Apartamento, Casa"

    def test_empty_or_none_answers_return_none(self):
        assert render_answers_pt_br({}) is None
        assert render_answers_pt_br(None) is None

    def test_blank_values_are_skipped_not_rendered_as_empty_lines(self):
        rendered = render_answers_pt_br({"faixa": "  ", "regiao": "Zona Sul"})
        assert rendered == "regiao: Zona Sul"


class TestResolveCorretorFromAnswers:
    def test_matches_a_known_alias(self):
        corretor_id, corretor_raw = _resolve_corretor_from_answers(
            {"quem_atendeu": "Cindy"}, {"CINDY": "corretor-1"}
        )
        assert corretor_id == "corretor-1"
        assert corretor_raw == "Cindy"

    def test_no_match_leaves_both_none_rather_than_guessing(self):
        corretor_id, corretor_raw = _resolve_corretor_from_answers(
            {"quem_atendeu": "Alguém Desconhecido"}, {"CINDY": "corretor-1"}
        )
        assert corretor_id is None
        assert corretor_raw is None

    def test_empty_corretor_map_leaves_both_none(self):
        corretor_id, corretor_raw = _resolve_corretor_from_answers(
            {"x": "Cindy"}, {}
        )
        assert corretor_id is None
        assert corretor_raw is None


# ─── DB-facing entry points ──────────────────────────────────────────────


class TestEnsureDefaultDimensionsProvisionsMetaLeadAdsSource:
    def test_meta_lead_ads_slug_is_provisioned(self):
        client = _scoped_mock()
        dimensions_service.ensure_default_dimensions(client, ORG)
        sources = dimensions_service.list_sources(client, ORG)
        slugs = {s["slug"] for s in sources}
        assert "meta-lead-ads" in slugs
        source = next(s for s in sources if s["slug"] == "meta-lead-ads")
        assert source["categoria"] == "social"


class TestIngestMetaLead:
    def test_creates_a_leads_row_mapped_from_the_meta_lead(self):
        client = _scoped_mock()
        result = meta_ingest_service.ingest_meta_lead(client, ORG, _meta_lead())
        assert result["created"] is True
        lead = result["lead"]
        assert lead["meta_lead_id"] == "ml-1"
        assert lead["cliente_nome"] == "Ana Souza"
        assert lead["contato"] == "+5511994573387"
        # `_derive_contato_fields` (leads_service.create_lead) re-derives
        # contato_norm from contato — a no-op re-run of the same
        # canonicalization migration 037's trigger already applied to
        # `meta_ads_leads.phone`, not a second blind normalization.
        assert lead["contato_norm"] == "+5511994573387"
        assert lead["contato_tipo"] == "telefone"
        assert lead["origem_raw"] == "C10023"
        assert lead["tipo_lead"] == "novo"

    def test_ingesting_the_same_meta_lead_twice_produces_exactly_one_row(self):
        client = _scoped_mock()
        first = meta_ingest_service.ingest_meta_lead(client, ORG, _meta_lead())
        second = meta_ingest_service.ingest_meta_lead(client, ORG, _meta_lead())

        assert first["created"] is True
        assert second["created"] is False
        assert second["lead"]["id"] == first["lead"]["id"]

        resp = (
            client.table("leads")
            .select("*")
            .eq("org_id", str(ORG))
            .eq("meta_lead_id", "ml-1")
            .execute()
        )
        assert len(list(resp.data or [])) == 1

    def test_missing_id_raises_value_error(self):
        client = _scoped_mock()
        with pytest.raises(ValueError):
            meta_ingest_service.ingest_meta_lead(client, ORG, _meta_lead(id=None))


class TestBackfillMetaAdsLeads:
    def _seed_meta_ads_leads(self, client, *rows: dict) -> None:
        for row in rows:
            client.table("meta_ads_leads").insert(row).execute()

    def test_backfills_every_row_once_and_skips_on_rerun(self):
        client = _scoped_mock()
        self._seed_meta_ads_leads(
            client,
            _meta_lead(id="ml-1"),
            _meta_lead(id="ml-2", full_name="Beto Lima", phone=None, campaign_name=None),
        )

        first = meta_ingest_service.backfill_meta_ads_leads(client, ORG)
        assert first == {"ingested": 2, "skipped_existing": 0, "errors": []}

        second = meta_ingest_service.backfill_meta_ads_leads(client, ORG)
        assert second == {"ingested": 0, "skipped_existing": 2, "errors": []}

        resp = client.table("leads").select("*").eq("org_id", str(ORG)).execute()
        meta_lead_ids = sorted(r["meta_lead_id"] for r in (resp.data or []))
        assert meta_lead_ids == ["ml-1", "ml-2"]

    def test_a_row_with_unparseable_created_time_is_reported_not_raised(self):
        client = _scoped_mock()
        self._seed_meta_ads_leads(client, _meta_lead(id="ml-bad", created_time=None))

        result = meta_ingest_service.backfill_meta_ads_leads(client, ORG)
        assert result["ingested"] == 0
        assert result["skipped_existing"] == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["meta_lead_id"] == "ml-bad"

    def test_terminates_and_covers_everything_when_range_is_ignored(self):
        """`MockSupabaseClient.range()` is a documented no-op, so every
        page here returns the FULL set — the condition under which the
        offset-only `while True` this function used to run never ended.
        A real backend or proxy that dropped the Range header would hang
        production the same way, on the path that touches the most rows.

        Asserts the two properties a mock CAN speak to: the loop
        terminates, and every row is projected exactly once. Whether
        PostgREST honours `range` is the 98377d26 bug class and stays a
        live-verification item."""
        client = _scoped_mock()
        self._seed_meta_ads_leads(
            client, *[_meta_lead(id=f"ml-page-{index}") for index in range(7)]
        )

        result = meta_ingest_service.backfill_meta_ads_leads(client, ORG, page_size=2)

        assert result["ingested"] == 7
        assert result["skipped_existing"] == 0  # exactly once, not re-walked
        assert result["errors"] == []
