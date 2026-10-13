"""Categories, products, offers, media: rules + the guarded lifecycle."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import CommerceError, catalog
from noctusai_lib.domain.commerce import media as media_svc
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import CFG, ORG_A, ORG_B, run, seed_product

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64


class TestCategories:
    def test_slug_defaults_from_name_and_is_unique_per_org(self, db):
        a = catalog.create_category(db, ORG_A, {"name": "Cursos Online"})
        assert a["slug"] == "cursos-online"
        with pytest.raises(CommerceError) as exc:
            catalog.create_category(db, ORG_A, {"name": "Cursos Online"})
        assert exc.value.status_code == 409
        # another org may reuse the slug
        assert catalog.create_category(db, ORG_B, {"name": "Cursos Online"})["slug"] == "cursos-online"

    def test_parent_must_exist_in_the_same_org(self, db):
        other = catalog.create_category(db, ORG_B, {"name": "Alheia"})
        with pytest.raises(CommerceError) as exc:
            catalog.create_category(db, ORG_A, {"name": "Filha", "parent_id": other["id"]})
        assert exc.value.status_code == 422

    def test_cycles_are_refused(self, db):
        root = catalog.create_category(db, ORG_A, {"name": "Raiz"})
        child = catalog.create_category(db, ORG_A, {"name": "Filha", "parent_id": root["id"]})
        with pytest.raises(CommerceError):
            catalog.update_category(db, ORG_A, root["id"], {"parent_id": child["id"]})
        with pytest.raises(CommerceError):
            catalog.update_category(db, ORG_A, root["id"], {"parent_id": root["id"]})

    def test_update_and_delete(self, db):
        c = catalog.create_category(db, ORG_A, {"name": "A"})
        assert catalog.update_category(db, ORG_A, c["id"], {"name": "B"})["name"] == "B"
        catalog.delete_category(db, ORG_A, c["id"])
        assert catalog.list_categories(db, ORG_A) == []
        with pytest.raises(NotFoundError):
            catalog.delete_category(db, ORG_A, c["id"])


class TestProducts:
    def test_create_defaults_to_draft_with_type_derived_fulfillment(self, db):
        for ptype, ful in [("digital", "digital_delivery"), ("physical", "shipping"), ("service", "none"), ("print_on_demand", "shipping")]:
            p = catalog.create_product(db, ORG_A, {"title": f"P {ptype}", "product_type": ptype})
            assert p["status"] == "draft" and p["fulfillment_type"] == ful

    def test_explicit_fulfillment_is_respected(self, db):
        p = catalog.create_product(db, ORG_A, {"title": "Retirada", "product_type": "physical", "fulfillment_type": "pickup"})
        assert p["fulfillment_type"] == "pickup"

    def test_auto_slug_collisions_get_a_suffix_but_an_explicit_slug_conflicts(self, db):
        a = catalog.create_product(db, ORG_A, {"title": "Foto", "product_type": "digital"})
        b = catalog.create_product(db, ORG_A, {"title": "Foto", "product_type": "digital"})
        assert (a["slug"], b["slug"]) == ("foto", "foto-2")
        with pytest.raises(CommerceError) as exc:
            catalog.create_product(db, ORG_A, {"title": "Outra", "slug": "foto", "product_type": "digital"})
        assert exc.value.code == "slug_em_uso"

    def test_patch_cannot_change_status(self, db):
        p = catalog.create_product(db, ORG_A, {"title": "X", "product_type": "digital"})
        out = catalog.update_product(db, ORG_A, p["id"], {"title": "Y", "status": "published"})
        assert out["title"] == "Y" and out["status"] == "draft"

    def test_publish_needs_an_active_offer(self, db):
        p = catalog.create_product(db, ORG_A, {"title": "X", "product_type": "digital"})
        with pytest.raises(CommerceError) as exc:
            catalog.set_product_status(db, ORG_A, p["id"], "published")
        assert exc.value.code == "sem_oferta_ativa"
        o = catalog.create_offer(db, ORG_A, p["id"], {"name": "N", "price_cents": 100, "active": False})
        with pytest.raises(CommerceError):
            catalog.set_product_status(db, ORG_A, p["id"], "published")
        catalog.update_offer(db, ORG_A, p["id"], o["id"], {"active": True})
        assert catalog.set_product_status(db, ORG_A, p["id"], "published")["status"] == "published"

    def test_other_lifecycle_moves_are_free(self, db):
        p, _ = seed_product(db, publish=False)
        for status in ("in_review", "unlisted", "retired", "draft"):
            assert catalog.set_product_status(db, ORG_A, p["id"], status)["status"] == status

    def test_listing_filters_by_status_and_search_and_pages(self, db):
        seed_product(db, title="Curso de Fotografia")
        seed_product(db, title="Preset Lightroom", publish=False)
        rows, total, page, size = catalog.list_products(db, ORG_A, status="published")
        assert [r["title"] for r in rows] == ["Curso de Fotografia"] and total == 1
        rows, total, *_ = catalog.list_products(db, ORG_A, q="lightroom")
        assert [r["title"] for r in rows] == ["Preset Lightroom"]
        rows, total, page, size = catalog.list_products(db, ORG_A, page=1, page_size=1)
        assert len(rows) == 1 and total == 2

    def test_delete_removes_offers_and_media_rows(self, db):
        p, o = seed_product(db)
        storage = FakeStorageBackend()
        run(media_svc.add_media(db, storage, CFG, ORG_A, p["id"], content_type="image/png", data=PNG))
        rows = catalog.delete_product_rows(db, ORG_A, p["id"])
        run(media_svc.delete_objects(storage, CFG, rows))
        assert db.table("commerce_offers").select("*").execute().data == []
        assert db.table("commerce_media").select("*").execute().data == []
        assert run(storage.list_keys(bucket=CFG.bucket)) == []


class TestOffers:
    def test_fee_estimate_rides_every_offer(self, db):
        p, o = seed_product(db, price_cents=4700)
        assert o["fee_estimate"] == {"pix_cents": 199, "boleto_cents": 199, "card_cents": 190}
        assert catalog.list_offers(db, ORG_A, p["id"])[0]["fee_estimate"]["pix_cents"] == 199

    def test_update_reestimates_and_delete_works(self, db):
        p, o = seed_product(db, price_cents=1000)
        out = catalog.update_offer(db, ORG_A, p["id"], o["id"], {"price_cents": 20000})
        assert out["price_cents"] == 20000 and out["fee_estimate"]["card_cents"] == 49 + 598
        catalog.delete_offer(db, ORG_A, p["id"], o["id"])
        assert catalog.list_offers(db, ORG_A, p["id"]) == []

    def test_an_offer_id_from_another_product_is_a_404(self, db):
        p1, o1 = seed_product(db, title="Um")
        p2, _ = seed_product(db, title="Dois")
        with pytest.raises(NotFoundError):
            catalog.update_offer(db, ORG_A, p2["id"], o1["id"], {"name": "x"})


class TestMedia:
    def test_upload_stores_privately_and_returns_a_signed_url(self, db):
        p, _ = seed_product(db)
        storage = FakeStorageBackend()
        m = run(media_svc.add_media(db, storage, CFG, ORG_A, p["id"], content_type="image/jpeg", data=JPEG, alt="capa"))
        assert m["kind"] == "image" and m["alt"] == "capa" and m["url"].startswith("fake://")
        assert "storage_path" not in m  # the raw key never leaves the service
        key = db.table("commerce_media").select("*").execute().data[0]["storage_path"]
        assert key.startswith(f"{ORG_A}/products/{p['id']}/")  # org-prefixed => bucket RLS agrees
        assert run(storage.exists(bucket=CFG.bucket, key=key))

    def test_video_is_accepted_and_positions_increment(self, db):
        p, _ = seed_product(db)
        storage = FakeStorageBackend()
        run(media_svc.add_media(db, storage, CFG, ORG_A, p["id"], content_type="image/png", data=PNG))
        v = run(media_svc.add_media(db, storage, CFG, ORG_A, p["id"], content_type="video/mp4", data=MP4))
        assert v["kind"] == "video" and v["position"] == 1

    @pytest.mark.parametrize(
        "ctype,data",
        [("application/pdf", b"%PDF-1.4"), ("image/png", JPEG), ("image/jpeg", b"not an image"), ("video/mp4", PNG)],
    )
    def test_declared_type_must_match_the_bytes(self, db, ctype, data):
        p, _ = seed_product(db)
        with pytest.raises(CommerceError) as exc:
            run(media_svc.add_media(db, FakeStorageBackend(), CFG, ORG_A, p["id"], content_type=ctype, data=data))
        assert exc.value.code == "midia_invalida"

    def test_size_limit_is_413(self, db):
        p, _ = seed_product(db)
        with pytest.raises(CommerceError) as exc:
            run(media_svc.add_media(db, FakeStorageBackend(), CFG, ORG_A, p["id"], content_type="image/png",
                                    data=PNG + b"0" * media_svc.MAX_IMAGE_BYTES))
        assert exc.value.status_code == 413

    def test_delete_removes_row_and_object(self, db):
        p, _ = seed_product(db)
        storage = FakeStorageBackend()
        m = run(media_svc.add_media(db, storage, CFG, ORG_A, p["id"], content_type="image/png", data=PNG))
        run(media_svc.delete_media(db, storage, CFG, ORG_A, p["id"], m["id"]))
        assert run(storage.list_keys(bucket=CFG.bucket)) == []
        with pytest.raises(NotFoundError):
            run(media_svc.delete_media(db, storage, CFG, ORG_A, p["id"], m["id"]))

    def test_cannot_attach_media_to_another_orgs_product(self, db):
        p, _ = seed_product(db, ORG_B)
        with pytest.raises(NotFoundError):
            run(media_svc.add_media(db, FakeStorageBackend(), CFG, ORG_A, p["id"], content_type="image/png", data=PNG))

    def test_upload_route_override_is_declared_for_the_host(self):
        assert media_svc.MEDIA_UPLOAD_PATH_PATTERN == "/api/commerce/products/*/media"
        assert media_svc.MEDIA_UPLOAD_MAX_BYTES > media_svc.MAX_VIDEO_BYTES
