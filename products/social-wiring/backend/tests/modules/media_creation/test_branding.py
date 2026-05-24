"""Branding system — catalog loader, idempotent seed, and HTTP endpoints.

Agency model: one org → many agents (mc_brand_owners) → many brandings
(mc_brand_kits). The repo catalog (catalog/<owner>/brand.json) is the
source of truth; seed_catalog upserts it into one org idempotently.
"""
from __future__ import annotations

from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation.branding import (
    BrandOwnerDef,
    load_catalog,
    seed_catalog,
)


# ── Catalog parsing ───────────────────────────────────────────────────────


class TestCatalogLoader:
    def test_wilson_present_with_two_brandings(self):
        owners = {o.slug: o for o in load_catalog()}
        assert "wilson" in owners, list(owners)
        wilson = owners["wilson"]
        assert wilson.kind == "real_estate_agent"
        slugs = {b.slug for b in wilson.brandings}
        assert slugs == {"premium", "educational"}  # >1 branding per agent

    def test_premium_design_tokens_match_wilson_brand(self):
        wilson = {o.slug: o for o in load_catalog()}["wilson"]
        premium = next(b for b in wilson.brandings if b.slug == "premium")
        t = premium.design_tokens
        assert t["bg_primary"] == "#2A2620"
        assert t["accent_gold"] == "#C5A55E"
        assert t["handle"] == "@wilson_one2022"
        assert t["location_pin"] == "GRANJA VIANA"
        assert premium.references  # has reference rows


# ── Idempotent seed ───────────────────────────────────────────────────────


class TestSeedCatalog:
    def _count(self, sb, table, org="org-1"):
        return len(sb.table(table).select("*").eq("org_id", org).execute().data or [])

    def test_seed_then_reseed_is_idempotent(self):
        sb = MockSupabaseClient()
        owners = load_catalog()

        first = seed_catalog(sb, "org-1", owners)
        assert first["owners_created"] == len(owners)
        assert first["brandings_created"] >= 2

        owners_after_1 = self._count(sb, "mc_brand_owners")
        kits_after_1 = self._count(sb, "mc_brand_kits")

        second = seed_catalog(sb, "org-1", owners)
        assert second["owners_created"] == 0
        assert second["owners_updated"] == len(owners)
        assert second["brandings_created"] == 0

        # No duplicates on re-seed.
        assert self._count(sb, "mc_brand_owners") == owners_after_1
        assert self._count(sb, "mc_brand_kits") == kits_after_1

    def test_seed_links_brandings_to_owner_and_org(self):
        sb = MockSupabaseClient()
        wilson = next(o for o in load_catalog() if o.slug == "wilson")
        seed_catalog(sb, "org-1", [wilson])

        owner_rows = sb.table("mc_brand_owners").select("*").eq("org_id", "org-1").execute().data
        assert len(owner_rows) == 1
        owner_id = owner_rows[0]["id"]

        kits = sb.table("mc_brand_kits").select("*").eq("org_id", "org-1").execute().data
        assert {k["slug"] for k in kits} == {"premium", "educational"}
        for k in kits:
            assert k["brand_owner_id"] == owner_id
            assert k["org_id"] == "org-1"
        # design_tokens round-trips as a dict
        premium = next(k for k in kits if k["slug"] == "premium")
        assert premium["design_tokens"]["accent_gold"] == "#C5A55E"

    def test_custom_owner_defs_seed_cleanly(self):
        sb = MockSupabaseClient()
        owners = [BrandOwnerDef(slug="acme", name="Acme Realty")]
        summary = seed_catalog(sb, "org-2", owners)
        assert summary["owners_created"] == 1
        assert summary["brandings_created"] == 0


# ── HTTP endpoints ────────────────────────────────────────────────────────


class TestBrandingEndpoints:
    def test_seed_then_list_owners(self, client):
        resp = client.post("/api/media-creation/branding/seed-catalog")
        assert resp.status_code == 200, resp.text
        summary = resp.json()["data"]
        assert summary["owners_created"] >= 1

        owners = client.get("/api/media-creation/branding/owners").json()["data"]
        wilson = next((o for o in owners if o["slug"] == "wilson"), None)
        assert wilson is not None
        assert len(wilson["brandings"]) == 2

    def test_get_owner_detail(self, client):
        client.post("/api/media-creation/branding/seed-catalog")
        owners = client.get("/api/media-creation/branding/owners").json()["data"]
        owner_id = next(o["id"] for o in owners if o["slug"] == "wilson")
        detail = client.get(f"/api/media-creation/branding/owners/{owner_id}").json()["data"]
        assert detail["slug"] == "wilson"
        assert {b["slug"] for b in detail["brandings"]} == {"premium", "educational"}

    def test_get_owner_404(self, client):
        resp = client.get("/api/media-creation/branding/owners/ghost-id")
        assert resp.status_code == 404, resp.text

    def test_seed_is_idempotent_over_http(self, client):
        client.post("/api/media-creation/branding/seed-catalog")
        second = client.post("/api/media-creation/branding/seed-catalog").json()["data"]
        assert second["owners_created"] == 0
        assert second["owners_updated"] >= 1
        owners = client.get("/api/media-creation/branding/owners").json()["data"]
        assert len([o for o in owners if o["slug"] == "wilson"]) == 1
