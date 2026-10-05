"""HTTP-boundary tests for the Branding endpoints (the richer brand-kit model).

Auth boundary: every route asserts a STRICT ``== 401`` unauthenticated.
"""
from __future__ import annotations

import asyncio

import pytest

from app.modules.media_creation.deps import BRANDING_BUCKET
from app.modules.media_creation.design.tokens import resolve_tokens

from ._branding_fixtures import (
    PNG,
    TOKENS,
    WOFF2,
    b64,
    folder_files,
    mini_files,
    payload_files,
)

BASE = "/api/media-creation/branding"
ORG = "test-org-123"


def _marca(client, mid="marca-1", name="Nós no Limiar", kind="empresa", slug="nos-no-limiar"):
    client.mock_supabase.from_("marcas").insert(
        {"id": mid, "org_id": ORG, "slug": slug, "name": name, "kind": kind}
    ).execute()
    return mid


def _import(client, marca_id="marca-1", files=None, **extra):
    return client.post(
        f"{BASE}/import",
        json={"marca_id": marca_id, "files": payload_files(files or mini_files()), **extra},
    )


def _blobs(client):
    return asyncio.run(client.branding_storage.list_keys(bucket=BRANDING_BUCKET, limit=1000))


class TestAuthBoundary:
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("get", BASE, None),
            ("post", BASE, {"name": "x"}),
            ("post", f"{BASE}/import", {"files": []}),
            ("get", f"{BASE}/k1", None),
            ("patch", f"{BASE}/k1", {"name": "x"}),
            ("delete", f"{BASE}/k1", None),
            ("put", f"{BASE}/k1/components", {"name": "Button"}),
            ("delete", f"{BASE}/components/c1", None),
            ("post", f"{BASE}/k1/assets", {"kind": "logo", "label": "a", "content_base64": "AA=="}),
            ("delete", "/api/media-creation/references/r1", None),
        ],
    )
    def test_unauthenticated_is_401(self, client, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client.raw(), method)(path, **kwargs)
        assert resp.status_code == 401, (method, path, resp.status_code, resp.text)


class TestCatalogRemoved:
    def test_no_seed_catalog_or_owners_routes(self, client):
        assert client.post(f"{BASE}/seed-catalog", json={}).status_code in (404, 405)
        # "owners" is now just an unknown branding id
        assert client.get(f"{BASE}/owners").status_code == 404

    def test_repo_catalog_is_gone(self):
        import app.modules.media_creation.branding as pkg
        from pathlib import Path

        assert not (Path(pkg.__file__).parent / "catalog").exists()
        assert not hasattr(pkg, "load_catalog") and not hasattr(pkg, "seed_catalog")
        assert not (Path(pkg.__file__).parent / "loader.py").exists()


class TestOverview:
    def test_groups_by_marca_and_lists_empty_marcas(self, client):
        _marca(client, "m1", "One Consultoria", "empresa", "one")
        _marca(client, "m2", "Gilson", "pessoa_fisica", "gilson")
        client.mock_supabase.from_("mc_brand_kits").insert(
            {"id": "k1", "org_id": ORG, "name": "One Design", "marca_id": "m1", "slug": "one-design", "is_template": False}
        ).execute()
        client.mock_supabase.from_("mc_brand_kits").insert(
            {"id": "k2", "org_id": ORG, "name": "Loose kit", "marca_id": None, "is_template": False}
        ).execute()
        client.mock_supabase.from_("mc_brand_kits").insert(
            {"id": "kt", "org_id": ORG, "name": "Branding Template", "marca_id": None, "is_template": True}
        ).execute()
        data = client.get(BASE).json()["data"]
        by_name = {m["name"]: m for m in data["marcas"]}
        assert [b["id"] for b in by_name["One Consultoria"]["brandings"]] == ["k1"]
        assert by_name["Gilson"]["brandings"] == []
        assert [k["id"] for k in data["unassigned"]] == ["k2"]
        assert data["template"]["id"] == "kt"
        # summaries stay light: no tokens / brand book on the list
        assert "tokens" not in data["template"]

    def test_empty_org(self, client):
        data = client.get(BASE).json()["data"]
        assert data == {"template": None, "marcas": [], "unassigned": []}


class TestImport:
    def test_creates_then_updates_without_duplicating(self, client):
        _marca(client)
        first = _import(client)
        assert first.status_code == 201, first.text
        r1 = first.json()["data"]
        assert r1["action"] == "created"
        assert (r1["components"], r1["assets"], r1["sections"]) == (1, 2, 2)
        assert r1["ignored"] == ["source/dump.html"]
        assert len(_blobs(client)) == 2

        second = _import(client)
        assert second.status_code == 201, second.text
        r2 = second.json()["data"]
        assert r2["action"] == "updated" and r2["id"] == r1["id"]
        kits = client.mock_supabase.from_("mc_brand_kits").select("*").eq("org_id", ORG).execute().data
        assert len(kits) == 1
        refs = client.mock_supabase.from_("mc_brand_references").select("*").execute().data
        assert len(refs) == 2  # replaced, not duplicated
        assert len(_blobs(client)) == 2  # the superseded blobs were removed
        comps = client.mock_supabase.from_("mc_brand_components").select("*").execute().data
        assert len(comps) == 1

    def test_stores_rich_model_and_links_marca(self, client):
        _marca(client)
        kit_id = _import(client).json()["data"]["id"]
        d = client.get(f"{BASE}/{kit_id}").json()["data"]
        assert d["marca"]["name"] == "Nós no Limiar"
        assert d["is_template"] is False and d["marca_id"] == "marca-1"
        assert d["tokens"]["color"]["tokens"][0]["name"] == "ground"
        assert d["brand_book"].startswith("# Mini")
        assert {s["title"] for s in d["sections"]} == {"Voz", "Assets: Logos"}
        assert [c["name"] for c in d["components"]] == ["Button"]
        kinds = {(a["kind"], a["label"]) for a in d["assets"]}
        assert kinds == {("logo", "logo.png"), ("font", "mini.woff2")}
        assert all(a["signed_url"] for a in d["assets"])  # signed per read

    def test_limiar_folder_end_to_end(self, client):
        _marca(client)
        resp = _import(client, files=folder_files("nos-no-limiar-monica"))
        assert resp.status_code == 201, resp.text
        r = resp.json()["data"]
        assert r["name"] == "Nós no Limiar" and r["assets"] == 3 and r["components"] >= 8

    def test_import_as_template(self, client):
        resp = client.post(
            f"{BASE}/import",
            json={"is_template": True, "files": payload_files(mini_files())},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["is_template"] is True
        data = client.get(BASE).json()["data"]
        assert data["template"]["name"] == "Mini DS"
        # re-import updates the single template row
        again = client.post(
            f"{BASE}/import", json={"is_template": True, "files": payload_files(mini_files())}
        )
        assert again.json()["data"]["action"] == "updated"

    @pytest.mark.parametrize(
        "body",
        [
            {"is_template": True, "marca_id": "marca-1"},
            {"is_template": False},
        ],
    )
    def test_marca_rules(self, client, body):
        _marca(client)
        resp = client.post(f"{BASE}/import", json={**body, "files": payload_files(mini_files())})
        assert resp.status_code == 422, resp.text

    def test_unknown_marca_is_404(self, client):
        assert _import(client, marca_id="nope").status_code == 404

    def test_other_orgs_marca_is_404(self, client):
        client.mock_supabase.from_("marcas").insert(
            {"id": "alien", "org_id": "other-org", "slug": "a", "name": "A", "kind": "empresa"}
        ).execute()
        assert _import(client, marca_id="alien").status_code == 404

    def test_validation_errors_are_reported_and_nothing_is_written(self, client):
        _marca(client)
        files = mini_files() + [
            ("components/Evil/preview.html", b"<script>alert(1)</script>"),
            ("assets/Logos/fake.png", b"not an image"),
        ]
        resp = _import(client, files=files)
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "branding_invalid"
        detail = " ".join(resp.json()["errors"])
        assert "components/Evil/preview.html" in detail and "fake.png" in detail
        assert client.mock_supabase.from_("mc_brand_kits").select("*").execute().data == []
        assert _blobs(client) == []

    def test_invalid_tokens_rejected(self, client):
        _marca(client)
        files = [(p, d) for p, d in mini_files() if p != "tokens.json"]
        files.append(("tokens.json", b'{"name": "x"}'))
        resp = _import(client, files=files)
        assert resp.status_code == 422 and "tokens.json" in str(resp.json())

    def test_bad_base64_is_400(self, client):
        _marca(client)
        resp = client.post(
            f"{BASE}/import",
            json={"marca_id": "marca-1", "files": [{"path": "tokens.json", "content_base64": "***"}]},
        )
        assert resp.status_code == 400

    def test_unknown_field_rejected(self, client):
        _marca(client)
        resp = client.post(f"{BASE}/import", json={"marca_id": "marca-1", "files": payload_files(mini_files()), "x": 1})
        assert resp.status_code == 422


class TestCreateFromTemplate:
    def test_requires_a_template(self, client):
        _marca(client)
        resp = client.post(BASE, json={"name": "Novo", "marca_id": "marca-1", "from_template": True})
        assert resp.status_code == 409, resp.text

    def test_copies_tokens_book_components_and_blobs(self, client):
        _marca(client)
        client.post(f"{BASE}/import", json={"is_template": True, "files": payload_files(mini_files())})
        before = len(_blobs(client))
        resp = client.post(BASE, json={"name": "Cliente X", "marca_id": "marca-1", "from_template": True})
        assert resp.status_code == 201, resp.text
        d = resp.json()["data"]
        assert d["is_template"] is False and d["marca_id"] == "marca-1" and d["slug"] == "cliente-x"
        assert d["tokens"]["name"] == "Mini" and d["brand_book"].startswith("# Mini")
        assert [c["name"] for c in d["components"]] == ["Button"]
        assert {a["kind"] for a in d["assets"]} == {"logo", "font"}
        assert len(_blobs(client)) == before * 2  # blobs copied, not shared
        # the template itself is untouched
        assert client.get(BASE).json()["data"]["template"]["name"] == "Mini DS"

    def test_plain_create_and_slug_uniqueness(self, client):
        _marca(client)
        a = client.post(BASE, json={"name": "Dup", "marca_id": "marca-1"}).json()["data"]
        b = client.post(BASE, json={"name": "Dup", "marca_id": "marca-1"}).json()["data"]
        assert (a["slug"], b["slug"]) == ("dup", "dup-2")
        assert a["tokens"] is None and a["components"] == [] and a["assets"] == []

    def test_unknown_marca(self, client):
        assert client.post(BASE, json={"name": "x", "marca_id": "nope"}).status_code == 404


class TestUpdateDelete:
    def _kit(self, client):
        _marca(client)
        return _import(client).json()["data"]["id"]

    def test_patch_edits_book_sections_tokens_and_marca(self, client):
        kit = self._kit(client)
        _marca(client, "marca-2", "Outra", "empresa", "outra")
        t = {**TOKENS, "name": "Edited"}
        resp = client.patch(
            f"{BASE}/{kit}",
            json={
                "brand_book": "# novo",
                "sections": [{"title": "S", "markdown": "m"}],
                "tokens": t,
                "marca_id": "marca-2",
                "persona": "p",
            },
        )
        assert resp.status_code == 200, resp.text
        d = resp.json()["data"]
        assert d["brand_book"] == "# novo" and d["tokens"]["name"] == "Edited"
        assert d["sections"] == [{"title": "S", "markdown": "m"}]
        assert d["marca"]["name"] == "Outra" and d["persona"] == "p"

    def test_patch_rejects_invalid_tokens(self, client):
        kit = self._kit(client)
        resp = client.patch(f"{BASE}/{kit}", json={"tokens": {"name": "x"}})
        assert resp.status_code == 422, resp.text

    def test_patch_unknown_is_404(self, client):
        assert client.patch(f"{BASE}/nope", json={"name": "x"}).status_code == 404

    def test_template_cannot_get_a_marca_nor_be_deleted(self, client):
        _marca(client)
        tid = client.post(
            f"{BASE}/import", json={"is_template": True, "files": payload_files(mini_files())}
        ).json()["data"]["id"]
        assert client.patch(f"{BASE}/{tid}", json={"marca_id": "marca-1"}).status_code == 400
        assert client.delete(f"{BASE}/{tid}").status_code == 409

    def test_delete_removes_blobs_and_children(self, client):
        kit = self._kit(client)
        assert len(_blobs(client)) == 2
        resp = client.delete(f"{BASE}/{kit}")
        assert resp.status_code == 200 and resp.json()["orphaned_assets"] == 0
        assert _blobs(client) == []
        assert client.get(f"{BASE}/{kit}").status_code == 404

    def test_delete_refused_when_a_post_uses_it(self, client):
        kit = self._kit(client)
        client.mock_supabase.from_("mc_posts").insert(
            {"id": "p1", "org_id": ORG, "brand_kit_id": kit, "title": "t", "idea": "i"}
        ).execute()
        assert client.delete(f"{BASE}/{kit}").status_code == 400
        assert len(_blobs(client)) == 2  # nothing was touched

    def test_legacy_brand_kits_delete_also_cleans_blobs(self, client):
        kit = self._kit(client)
        assert client.delete(f"/api/media-creation/brand-kits/{kit}").status_code == 200
        assert _blobs(client) == []


class TestComponents:
    def _kit(self, client):
        _marca(client)
        return client.post(BASE, json={"name": "K", "marca_id": "marca-1"}).json()["data"]["id"]

    def test_upsert_creates_then_updates_by_name(self, client):
        kit = self._kit(client)
        body = {"name": "Chip", "guideline_md": "# Chip", "preview_html": "<div>a</div>"}
        assert client.put(f"{BASE}/{kit}/components", json=body).status_code == 200
        assert client.put(f"{BASE}/{kit}/components", json={**body, "guideline_md": "v2"}).status_code == 200
        comps = client.get(f"{BASE}/{kit}").json()["data"]["components"]
        assert [(c["name"], c["guideline_md"]) for c in comps] == [("Chip", "v2")]

    @pytest.mark.parametrize("html", ["<script>1</script>", "<div onclick='x()'>a</div>", "<iframe></iframe>"])
    def test_unsafe_preview_rejected(self, client, html):
        kit = self._kit(client)
        resp = client.put(f"{BASE}/{kit}/components", json={"name": "Evil", "preview_html": html})
        assert resp.status_code == 422, resp.text

    def test_invalid_name_rejected(self, client):
        kit = self._kit(client)
        assert client.put(f"{BASE}/{kit}/components", json={"name": "../x"}).status_code == 422

    def test_delete_component(self, client):
        kit = self._kit(client)
        cid = client.put(f"{BASE}/{kit}/components", json={"name": "Chip"}).json()["data"]["id"]
        assert client.delete(f"{BASE}/components/{cid}").status_code == 200
        assert client.delete(f"{BASE}/components/{cid}").status_code == 404


class TestAssets:
    def _kit(self, client):
        _marca(client)
        return client.post(BASE, json={"name": "K", "marca_id": "marca-1"}).json()["data"]["id"]

    def test_upload_list_replace_delete(self, client):
        kit = self._kit(client)
        up = client.post(f"{BASE}/{kit}/assets", json={"kind": "logo", "label": "l.png", "content_base64": b64(PNG)})
        assert up.status_code == 201, up.text
        row = up.json()["data"]
        assert row["content_type"] == "image/png" and row["size_bytes"] == len(PNG) and row["signed_url"]
        assert row["storage_path"].startswith(f"{ORG}/branding/{kit}/logo/")
        assert len(_blobs(client)) == 1
        # same (kind,label) replaces the blob, never duplicates
        client.post(f"{BASE}/{kit}/assets", json={"kind": "logo", "label": "l.png", "content_base64": b64(PNG)})
        assert len(_blobs(client)) == 1
        d = client.get(f"{BASE}/{kit}").json()["data"]
        assert len(d["assets"]) == 1
        # delete through the existing references route removes the blob too
        assert client.delete(f"/api/media-creation/references/{d['assets'][0]['id']}").status_code == 200
        assert _blobs(client) == []

    def test_type_is_decided_by_bytes(self, client):
        kit = self._kit(client)
        bad = client.post(f"{BASE}/{kit}/assets", json={"kind": "logo", "label": "x.png", "content_base64": b64(b"MZ not an image")})
        assert bad.status_code == 415
        wrong_family = client.post(f"{BASE}/{kit}/assets", json={"kind": "logo", "label": "f.woff2", "content_base64": b64(WOFF2)})
        assert wrong_family.status_code == 422
        ok_font = client.post(f"{BASE}/{kit}/assets", json={"kind": "font", "label": "f.woff2", "content_base64": b64(WOFF2)})
        assert ok_font.status_code == 201

    def test_oversize_rejected(self, client):
        kit = self._kit(client)
        big = PNG + b"\x00" * (5 * 1024 * 1024)
        resp = client.post(f"{BASE}/{kit}/assets", json={"kind": "logo", "label": "big.png", "content_base64": b64(big)})
        assert resp.status_code == 413

    def test_unknown_kit_404(self, client):
        resp = client.post(f"{BASE}/nope/assets", json={"kind": "logo", "label": "a.png", "content_base64": b64(PNG)})
        assert resp.status_code == 404

    def test_signing_failure_is_surfaced_on_the_row(self, client):
        kit = self._kit(client)
        client.post(f"{BASE}/{kit}/assets", json={"kind": "logo", "label": "l.png", "content_base64": b64(PNG)})

        async def boom(**_kw):
            raise RuntimeError("storage down")

        client.branding_storage.signed_url = boom  # real seam: the backend's own method
        a = client.get(f"{BASE}/{kit}").json()["data"]["assets"][0]
        assert a["signed_url"] is None and "storage down" in a["signed_url_error"]


class TestSvgRenderStaysCompatible:
    def test_design_tokens_override_still_wins_and_tokens_column_is_ignored(self):
        kit = {"design_tokens": {"accent_gold": "#123456", "handle": "@x"}, "tokens": TOKENS}
        t = resolve_tokens(kit, "premium")
        assert t.accent_gold == "#123456" and t.handle == "@x"
        # a kit with only the rich `tokens` falls back to the generic preset
        assert resolve_tokens({"tokens": TOKENS, "design_tokens": None}, "premium").accent_gold == "#B8924E"
