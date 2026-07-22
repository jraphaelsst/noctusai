"""Service-level coverage for behavior not reachable through the public
HTTP surface — the alias-create re-link sweep (``origem_raw`` isn't
settable via ``LeadCreate``, only by the importer), and
``ensure_default_dimensions`` idempotency.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.modules.leads.services import dimensions_service, leads_service

ORG = UUID("00000000-0000-4000-8000-0000000000a1")


def _scoped_mock():
    db = MockSupabaseClient()
    return db.schema("social_wiring")


class TestCreateSourceAliasRelink:
    def test_relinks_leads_with_matching_origem_raw(self):
        client = _scoped_mock()
        source = dimensions_service.create_source(
            client, ORG, slug="viva-real", label="Viva Real", categoria="portal"
        )
        lead = leads_service.create_lead(
            client, ORG, {"data_entrada": "2026-07-01"}
        )
        # Simulate an imported row whose origem never got resolved yet.
        client.table("leads").update(
            {"origem_raw": "VIVAVREAL", "needs_review": True}
        ).eq("id", lead["id"]).execute()

        dimensions_service.create_source_alias(
            client, ORG, alias="VIVAVREAL", source_id=source["id"]
        )

        refreshed = leads_service.get_lead(client, ORG, UUID(lead["id"]))
        assert refreshed["origem_id"] == source["id"]
        assert refreshed["needs_review"] is False

    def test_relink_sets_needs_review_true_for_outro_source(self):
        client = _scoped_mock()
        outro = dimensions_service.create_source(
            client, ORG, slug="outro", label="Outro", categoria="outro"
        )
        lead = leads_service.create_lead(client, ORG, {"data_entrada": "2026-07-01"})
        client.table("leads").update({"origem_raw": "ALGO ESQUISITO"}).eq(
            "id", lead["id"]
        ).execute()

        dimensions_service.create_source_alias(
            client, ORG, alias="ALGO ESQUISITO", source_id=outro["id"]
        )

        refreshed = leads_service.get_lead(client, ORG, UUID(lead["id"]))
        assert refreshed["needs_review"] is True


class TestUnmappedOrigensBlankBucket:
    def test_blank_origem_raw_surfaces_as_a_distinct_bucket(self):
        """Previously a lead with NO `origem_raw` at all was silently
        skipped by this queue forever (~79 such leads in the real
        dataset) — now folded into `_BLANK_ORIGEM_BUCKET`."""
        client = _scoped_mock()
        leads_service.create_lead(client, ORG, {"data_entrada": "2026-07-01"})
        leads_service.create_lead(client, ORG, {"data_entrada": "2026-07-02"})

        unmapped = dimensions_service.list_unmapped_origens(client, ORG)
        blank = next(u for u in unmapped if u["alias"] == dimensions_service._BLANK_ORIGEM_BUCKET)
        assert blank["count"] == 2

    def test_no_blank_bucket_when_every_lead_has_an_origem_raw(self):
        client = _scoped_mock()
        client.table("leads").insert(
            {
                "id": "00000000-0000-4000-8000-00000000e001",
                "org_id": str(ORG),
                "data_entrada": "2026-07-01",
                "origem_raw": "ZAP",
            }
        ).execute()
        unmapped = dimensions_service.list_unmapped_origens(client, ORG)
        assert all(u["alias"] != dimensions_service._BLANK_ORIGEM_BUCKET for u in unmapped)


class TestEnsureDefaultDimensions:
    def test_idempotent_second_call_does_not_duplicate(self):
        client = _scoped_mock()
        dimensions_service.ensure_default_dimensions(client, ORG)
        first_count = len(dimensions_service.list_sources(client, ORG))
        dimensions_service.ensure_default_dimensions(client, ORG)
        second_count = len(dimensions_service.list_sources(client, ORG))
        assert first_count == second_count > 0

    def test_seeds_canonical_source_slugs(self):
        client = _scoped_mock()
        dimensions_service.ensure_default_dimensions(client, ORG)
        slugs = {s["slug"] for s in dimensions_service.list_sources(client, ORG)}
        assert {"senseys", "zap", "viva-real", "outro"} <= slugs

    def test_seeds_alias_map_resolves(self):
        client = _scoped_mock()
        dimensions_service.ensure_default_dimensions(client, ORG)
        source_map, _ = dimensions_service.build_resolution_maps(client, ORG)
        from app.modules.leads.seed_data import normalize_alias

        source_id, needs_review = source_map[normalize_alias("VIVAREAL")]
        assert needs_review is False
        source_id2, needs_review2 = source_map[normalize_alias("ONE8137 - JARDIM COLIBRI - KM 26")]
        assert needs_review2 is True
