"""`olx_ingest_service` — ledger + projection onto the unified `leads`.

The mapping itself is tested in the seed
(`seed/lib/backend/tests/integrations/olx/`). What is tested HERE is the
product-side contract: idempotency on the generic external key, the
ledger being written before the projection, and the paged backfill.
"""
from __future__ import annotations

import copy
from uuid import UUID

import pytest

from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD, parse_olx_lead_webhook

from app.modules.leads.services import dimensions_service
from app.modules.portal_leads.services import olx_ingest_service

from tests.modules.portal_leads.conftest import ORG_A

ORG = UUID(ORG_A)


def _lead(**overrides):
    body = copy.deepcopy(OLX_SAMPLE_LEAD)
    body.update(overrides)
    lead = parse_olx_lead_webhook(body)
    assert lead is not None
    return lead


@pytest.fixture
def client(mock_db):
    scoped = mock_db.schema("social_wiring")
    dimensions_service.ensure_default_dimensions(scoped, ORG)
    return scoped


class TestCanonicalSource:
    def test_grupo_olx_source_is_provisioned_by_ensure_default_dimensions(self, client):
        source = olx_ingest_service.get_or_create_olx_source(client, ORG)

        assert source["slug"] == "grupo-olx"
        assert source["categoria"] == "portal"

    def test_does_not_reuse_the_spreadsheet_zap_slug(self, client):
        """`zap` is human-entered attribution from the spreadsheet import.
        Writing automated leads into it would silently merge a guess with
        data someone actually knew."""
        source = olx_ingest_service.get_or_create_olx_source(client, ORG)

        assert source["slug"] != "zap"


class TestIngest:
    def test_ingest_writes_the_ledger_and_the_unified_lead(self, client):
        result = olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        assert result["created"] is True
        ledger = client.table("olx_leads").select("*").execute().data
        assert len(ledger) == 1
        assert ledger[0]["id"] == "59ee0fc6e4b043e1b2a6d863"
        assert ledger[0]["raw"] == OLX_SAMPLE_LEAD

        leads = client.table("leads").select("*").execute().data
        assert len(leads) == 1
        assert leads[0]["external_source"] == "grupo-olx"
        assert leads[0]["external_lead_id"] == "59ee0fc6e4b043e1b2a6d863"
        assert leads[0]["cliente_nome"] == "Nome Consumidor"

    def test_redelivery_is_a_no_op(self, client):
        """OLX retries a non-2xx 3x and stores failures 14 days, so the
        same lead arriving twice is ordinary traffic, not an anomaly."""
        first = olx_ingest_service.ingest_olx_lead(client, ORG, _lead())
        second = olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        assert first["created"] is True
        assert second["created"] is False
        assert len(client.table("leads").select("*").execute().data) == 1
        assert len(client.table("olx_leads").select("*").execute().data) == 1

    def test_the_ledger_is_written_before_the_projection(self, client):
        """A mapping failure must not cost us the vendor's body — it is
        unrecoverable after 14 days, whereas a mapping bug is fixable and
        the event re-processable."""
        with pytest.raises(ValueError):
            olx_ingest_service.ingest_olx_lead(client, ORG, _lead(timestamp="???"))

        assert len(client.table("olx_leads").select("*").execute().data) == 1
        assert client.table("leads").select("*").execute().data == []

    def test_payload_without_origin_lead_id_is_refused(self, client):
        with pytest.raises(ValueError, match="deduplicated"):
            olx_ingest_service.ingest_olx_payload(client, ORG, {"name": "no id"})

    def test_mcmv_lead_ingests_without_a_listing_id(self, client):
        lead = _lead(leadOrigin="MCMV_OLX", clientListingId=None, originListingId=None)

        result = olx_ingest_service.ingest_olx_lead(client, ORG, lead)

        assert result["created"] is True
        assert result["lead"]["codigo_imovel"] is None

    def test_two_orgs_can_hold_the_same_vendor_lead_id(self, client):
        """The idempotency key is (org, source, external id) — org-scoped,
        so one tenant's dedup can never suppress another tenant's lead."""
        other = UUID("00000000-0000-4000-8000-0000000000b2")
        dimensions_service.ensure_default_dimensions(client, other)

        olx_ingest_service.ingest_olx_lead(client, ORG, _lead())
        result = olx_ingest_service.ingest_olx_lead(client, other, _lead())

        assert result["created"] is True
        assert len(client.table("leads").select("*").execute().data) == 2


class TestBackfill:
    def test_backfill_projects_stored_ledger_rows(self, client):
        for index in range(3):
            olx_ingest_service.store_olx_lead(
                client, ORG, _lead(originLeadId=f"lead-{index}")
            )

        result = olx_ingest_service.backfill_olx_leads(client, ORG)

        assert result["ingested"] == 3
        assert result["errors"] == []

    def test_backfill_is_idempotent(self, client):
        olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        result = olx_ingest_service.backfill_olx_leads(client, ORG)

        assert result["ingested"] == 0
        assert result["skipped_existing"] == 1

    def test_backfill_reports_unmappable_rows_instead_of_dropping_them(self, client):
        olx_ingest_service.store_olx_lead(client, ORG, _lead(timestamp="???"))

        result = olx_ingest_service.backfill_olx_leads(client, ORG)

        assert result["ingested"] == 0
        assert len(result["errors"]) == 1
        assert "timestamp" in result["errors"][0]["error"]

    def test_backfill_terminates_and_covers_everything_when_range_is_ignored(self, client):
        """`MockSupabaseClient.range()` is a documented no-op, so every
        page here returns the FULL set — which is precisely the condition
        that made an offset-only loop spin forever (it hung this test
        before the no-progress guard). A real backend that ignored the
        range header would hang production identically.

        So this asserts the two properties a mock CAN speak to: the loop
        terminates, and every row is covered exactly once. Whether
        PostgREST honours `range` is not testable here — that is the
        98377d26 bug class, and it stays a live-verification item."""
        for index in range(7):
            olx_ingest_service.store_olx_lead(
                client, ORG, _lead(originLeadId=f"page-{index}")
            )

        result = olx_ingest_service.backfill_olx_leads(client, ORG, page_size=2)

        assert result["ingested"] == 7
        assert result["skipped_existing"] == 0  # exactly once, not re-walked


class TestPortalAttribution:
    """The splitter is wired into the ingest path even though its rule
    table is empty — so Gate 1 is a data change, not a code change."""

    def test_todays_leads_all_land_on_the_umbrella_source(self, client):
        result = olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        assert result["source_slug"] == "grupo-olx"
        source = olx_ingest_service.get_or_create_olx_source(client, ORG)
        assert result["lead"]["origem_id"] == source["id"]

    def test_a_split_resolves_a_different_source_row(self, monkeypatch):
        """Proves the seam works end-to-end with a rule in place, without
        shipping one. `zap` already exists in CANONICAL_SOURCES, so this
        needs no migration — which is the property being asserted."""
        from functools import partial

        from noctusai_lib.integrations.olx import (
            PortalRule,
            resolve_portal_source_slug,
        )
        from noctusai_lib.testing import MockSupabaseClient

        rule = PortalRule(
            slug="zap", field="leadOrigin", contains="Grupo OLX",
            evidence="test-only — never shipped in OLX_PORTAL_RULES",
        )
        # Injecting the RULES, not replacing the resolver: the real
        # function still runs, so this exercises the shipped matching.
        monkeypatch.setattr(
            olx_ingest_service, "resolve_portal_source_slug",
            partial(resolve_portal_source_slug, rules=(rule,)),
        )

        db = MockSupabaseClient().schema("social_wiring")
        result = olx_ingest_service.ingest_olx_lead(db, ORG, _lead())

        assert result["source_slug"] == "zap"
        zap = olx_ingest_service.get_or_create_olx_source(db, ORG, "zap")
        assert result["lead"]["origem_id"] == zap["id"]
        # And it is a DIFFERENT row from the umbrella — not a rename.
        umbrella = olx_ingest_service.get_or_create_olx_source(db, ORG)
        assert zap["id"] != umbrella["id"]
