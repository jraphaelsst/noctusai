"""A portal lead gives its listing a REGISTRY IDENTITY (`origem_descoberta='lead'`).

WHAT WAS BROKEN
---------------
Exactly two things ever created `imovel_registry` rows: the nightly Vista sync
and migration 063's one-off backfill. Neither runs when a lead arrives.

So an OLX or ImovelWeb lead for a listing the catalog has never shown us landed
a `leads.codigo_imovel` that no FK in this schema would accept. The lead saved
(that column is free text) and then every registry-keyed feature — matrícula,
roteiro, negociação — 404'd the imóvel the lead was literally about.

Not a rare shape: 063 measured 1019 distinct well-formed códigos on leads that
resolve against nothing in the mirror, and a portal lead names the listing it
came from by definition.

NO MIGRATION WAS NEEDED, and that is worth an assertion rather than a comment —
`test_the_origem_value_is_already_in_migration_063s_vocabulary` reads the CHECK
out of the migration file itself, so the day someone narrows that vocabulary
this suite says so instead of production doing it.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from uuid import UUID

import pytest

from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD, parse_olx_lead_webhook

from app.modules.imovel_hub.dados_service import registrar_imovel
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
    scoped.set_table_data("imovel_registry", [])
    return scoped


def registry(client) -> list[dict]:
    return list(
        client.table("imovel_registry").select("*").eq("org_id", str(ORG)).execute().data
        or []
    )


class TestPortalLeadCreatesTheRegistryRow:
    def test_an_unknown_listing_gets_an_identity_on_arrival(self, client):
        olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        rows = registry(client)
        assert [r["codigo_canonical"] for r in rows] == ["A40171"]
        assert rows[0]["origem_descoberta"] == "lead"

    def test_the_codigo_is_stored_canonical_and_the_spelling_is_kept(self, client):
        """`clientListingId` arrives lowercase from OLX. The registry's join key
        is `upper(btrim(...))` (062), and 076 verified prod holds nothing else —
        so a lowercase row would be invisible to every consumer."""
        olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        row = registry(client)[0]
        assert row["codigo_canonical"] == "A40171"
        assert row["codigo_display"] == "a40171"

    def test_ativo_no_vista_is_false_because_the_catalog_never_showed_it(
        self, client
    ):
        """063's default is FALSE for exactly this case. Claiming TRUE would
        make the delist sweep "delist" something it never listed."""
        olx_ingest_service.ingest_olx_lead(client, ORG, _lead())

        assert registry(client)[0]["ativo_no_vista"] is False

    def test_a_lead_with_no_listing_code_creates_nothing(self, client):
        """An MCMV lead carries no `clientListingId`. Inventing a registry row
        for it would put a códigoless identity in an append-only table."""
        olx_ingest_service.ingest_olx_lead(
            client, ORG, _lead(clientListingId=None, leadOrigin="MCMV")
        )

        assert registry(client) == []

    def test_a_second_lead_for_the_same_listing_does_not_duplicate(self, client):
        """🔴 Read-then-insert, never `upsert()`: `MockRequestBuilder.upsert()`
        is a documented no-op, so an upsert-based path tests green and
        duplicates live. This is the assertion that would catch that."""
        olx_ingest_service.ingest_olx_lead(client, ORG, _lead())
        olx_ingest_service.ingest_olx_lead(
            client, ORG, _lead(originLeadId="a-second-lead")
        )

        assert len(registry(client)) == 1


class TestRegistrarImovelDirectly:
    def test_an_existing_row_is_left_exactly_as_it_was(self, client):
        """A código first discovered by the Vista sync must not be rewritten as
        `lead` when a portal lead later names it — how we LEARNED a código
        exists does not change because something else met it second."""
        client.set_table_data(
            "imovel_registry",
            [
                {
                    "org_id": str(ORG),
                    "codigo_canonical": "ONE9001",
                    "codigo_display": "ONE9001",
                    "ativo_no_vista": True,
                    "origem_descoberta": "vista_sync",
                }
            ],
        )

        assert registrar_imovel(client, ORG, "one9001", origem="lead") == "ONE9001"

        rows = registry(client)
        assert len(rows) == 1
        assert rows[0]["origem_descoberta"] == "vista_sync"
        assert rows[0]["ativo_no_vista"] is True

    def test_a_blank_codigo_is_none_and_writes_nothing(self, client):
        assert registrar_imovel(client, ORG, "   ", origem="lead") is None
        assert registrar_imovel(client, ORG, "", origem="lead") is None
        assert registry(client) == []


class TestNoMigrationWasNeeded:
    def test_the_origem_value_is_already_in_migration_063s_vocabulary(self):
        """The slot was reserved when `imovel_registry` was designed and never
        filled. Read out of the migration rather than restated here, so a future
        narrowing of the CHECK fails this instead of production."""
        sql = (
            Path(__file__).resolve().parents[3]
            / "migrations"
            / "063_imovel_registry.sql"
        ).read_text()
        check = re.search(
            r"origem_descoberta IN \(([^)]*)\)", sql, re.S
        )
        assert check, "063 no longer declares an origem_descoberta CHECK"
        assert "'lead'" in check.group(1)
