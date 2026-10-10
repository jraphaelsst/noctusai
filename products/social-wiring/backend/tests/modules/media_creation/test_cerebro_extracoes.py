"""Segundo Cérebro — Minhas extrações (endpoints 19-24), pasted-text source only
(``url`` is phase 2 -> 422). Contract §4/§10."""
from __future__ import annotations

import uuid

import pytest

from app.modules.media_creation.deps import get_cerebro_storage
from app.modules.media_creation.services import cerebro_fontes_service as fontes
from noctusai_lib.integrations.storage import FakeStorageBackend

BASE = "/api/media-creation/cerebro"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_MARCA = str(uuid.uuid4())


@pytest.fixture
def cc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_MARCA, "org_id": "other-org", "name": "Marca B"}).execute()
    client._tc.app.dependency_overrides[get_cerebro_storage] = lambda: FakeStorageBackend()
    return client


def _brain(cc, *, org=ORG, marca=MARCA, content="", name=None):
    bid = str(uuid.uuid4())
    cc.mock_supabase.from_("cs_brains").insert({
        "id": bid, "org_id": org, "marca_id": marca, "kind": "custom", "template_slug": None,
        "name": name or f"B{bid[:4]}", "content": content, "content_version": 0,
        "synthesis_status": "idle",
    }).execute()
    return bid


def _content(cc, bid):
    return next(
        r for r in cc.mock_supabase.from_("cs_brains").select("*").execute().data if r["id"] == bid
    )["content"]


def _create(cc, brains, *, name="Aula 1", text="Texto da aula", **extra):
    body = {"marca_id": MARCA, "name": name, "brain_ids": brains, "text": text, **extra}
    return cc.post(f"{BASE}/extracoes", json=body)


class TestCreateAndRead:
    def test_text_extraction_is_201_ready_with_targets(self, cc):
        b1, b2 = _brain(cc, name="Um"), _brain(cc, name="Dois")
        r = _create(cc, [b1, b2])
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert d["status"] == "ready" and d["source_kind"] == "text" and d["transcript"] == "Texto da aula"
        assert {t["brain_name"] for t in d["targets"]} == {"Um", "Dois"}
        assert all(t["applied_at"] is None for t in d["targets"])
        got = cc.get(f"{BASE}/extracoes/{d['id']}").json()["data"]
        assert got["transcript"] == "Texto da aula"

    def test_url_is_422_not_available_and_creates_nothing(self, cc):
        r = cc.post(f"{BASE}/extracoes", json={
            "marca_id": MARCA, "name": "x", "brain_ids": [_brain(cc)], "url": "https://youtu.be/x",
        })
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "Extração por link ainda não disponível"
        assert cc.get(f"{BASE}/extracoes", params={"marca_id": MARCA}).json()["data"]["total"] == 0

    def test_exactly_one_source_and_bounds_are_422(self, cc):
        b = _brain(cc)
        both = {"marca_id": MARCA, "name": "x", "brain_ids": [b], "text": "t", "url": "u"}
        neither = {"marca_id": MARCA, "name": "x", "brain_ids": [b]}
        assert cc.post(f"{BASE}/extracoes", json=both).status_code == 422
        assert cc.post(f"{BASE}/extracoes", json=neither).status_code == 422
        assert _create(cc, []).status_code == 422
        assert _create(cc, [b], name="").status_code == 422
        assert _create(cc, [b], text="   ").status_code == 422
        assert _create(cc, [b], text="x" * 200_001).status_code == 422
        assert cc.post(f"{BASE}/extracoes", json={**neither, "text": "t", "extra": 1}).status_code == 422

    def test_foreign_marca_target_is_422_and_foreign_marca_is_404(self, cc):
        foreign_brain = _brain(cc, org="other-org", marca=OTHER_MARCA)
        other_marca_brain = _brain(cc, marca=str(uuid.uuid4()))  # same org, another marca
        assert _create(cc, [foreign_brain]).status_code == 422
        assert _create(cc, [other_marca_brain]).status_code == 422
        r = cc.post(f"{BASE}/extracoes", json={
            "marca_id": OTHER_MARCA, "name": "x", "brain_ids": [foreign_brain], "text": "t",
        })
        assert r.status_code == 404

    def test_list_filters_pages_and_scopes_by_marca(self, cc):
        b = _brain(cc)
        for n in ("Alpha", "Beta", "Gamma"):
            assert _create(cc, [b], name=n).status_code == 201
        listing = lambda **p: cc.get(f"{BASE}/extracoes", params={"marca_id": MARCA, **p}).json()["data"]
        assert listing()["total"] == 3
        assert [i["name"] for i in listing(q="bet")["items"]] == ["Beta"]
        page = listing(limit=2, offset=2)
        assert page["total"] == 3 and len(page["items"]) == 1
        assert "transcript" not in page["items"][0]
        assert cc.get(f"{BASE}/extracoes", params={"marca_id": OTHER_MARCA}).status_code == 404


class TestApply:
    def test_apply_appends_with_header_is_idempotent_and_marks_applied(self, cc):
        b1, b2 = _brain(cc), _brain(cc, content="antes")
        eid = _create(cc, [b1, b2]).json()["data"]["id"]
        r = cc.post(f"{BASE}/extracoes/{eid}/apply", json={})
        assert r.status_code == 200 and r.json()["data"] == {"applied": 2, "skipped": 0}
        assert _content(cc, b1).startswith("### Extração: «Aula 1» (") and "Texto da aula" in _content(cc, b1)
        assert _content(cc, b2).startswith("antes") and _content(cc, b2).count("### Extração") == 1
        again = cc.post(f"{BASE}/extracoes/{eid}/apply", json={})
        assert again.json()["data"] == {"applied": 0, "skipped": 0}
        # explicit re-apply of an applied target is skipped, never duplicated
        explicit = cc.post(f"{BASE}/extracoes/{eid}/apply", json={"brain_ids": [b1]})
        assert explicit.json()["data"] == {"applied": 0, "skipped": 1}
        assert _content(cc, b1).count("### Extração") == 1
        d = cc.get(f"{BASE}/extracoes/{eid}").json()["data"]
        assert d["status"] == "applied" and all(t["applied_at"] for t in d["targets"])

    def test_partial_apply_stays_ready_then_completes(self, cc):
        b1, b2 = _brain(cc), _brain(cc)
        eid = _create(cc, [b1, b2]).json()["data"]["id"]
        assert cc.post(f"{BASE}/extracoes/{eid}/apply", json={"brain_ids": [b1]}).json()["data"] == {
            "applied": 1, "skipped": 0,
        }
        assert cc.get(f"{BASE}/extracoes/{eid}").json()["data"]["status"] == "ready"
        assert cc.post(f"{BASE}/extracoes/{eid}/apply", json={}).json()["data"] == {"applied": 1, "skipped": 0}
        assert cc.get(f"{BASE}/extracoes/{eid}").json()["data"]["status"] == "applied"

    def test_non_target_brain_is_422_and_not_ready_is_409(self, cc):
        b, stranger = _brain(cc), _brain(cc)
        eid = _create(cc, [b]).json()["data"]["id"]
        assert cc.post(f"{BASE}/extracoes/{eid}/apply", json={"brain_ids": [stranger]}).status_code == 422
        cc.mock_supabase.from_("cs_extractions").update({"status": "transcribing"}).eq("id", eid).execute()
        assert cc.post(f"{BASE}/extracoes/{eid}/apply", json={}).status_code == 409

    def test_over_limit_releases_the_claim_so_a_retry_is_possible(self, cc):
        b = _brain(cc, content="x" * 199_990)
        eid = _create(cc, [b], text="y" * 100).json()["data"]["id"]
        r = cc.post(f"{BASE}/extracoes/{eid}/apply", json={})
        assert r.status_code == 422 and "200.000" in r.json()["error"]["message"], r.text
        d = cc.get(f"{BASE}/extracoes/{eid}").json()["data"]
        assert d["status"] == "ready" and d["targets"][0]["applied_at"] is None
        assert _content(cc, b) == "x" * 199_990


class TestPatchDelete:
    def test_patch_name_transcript_and_targets(self, cc):
        b1, b2, b3 = _brain(cc), _brain(cc), _brain(cc)
        eid = _create(cc, [b1, b2]).json()["data"]["id"]
        r = cc.patch(f"{BASE}/extracoes/{eid}", json={"name": "Novo", "transcript": "Editado", "brain_ids": [b2, b3]})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["name"] == "Novo" and d["transcript"] == "Editado"
        assert {t["brain_id"] for t in d["targets"]} == {b2, b3}
        cc.post(f"{BASE}/extracoes/{eid}/apply", json={})
        assert "Editado" in _content(cc, b2) and "### Extração: «Novo»" in _content(cc, b3)

    def test_applied_target_survives_removal_and_new_target_reopens(self, cc):
        b1, b2 = _brain(cc), _brain(cc)
        eid = _create(cc, [b1]).json()["data"]["id"]
        cc.post(f"{BASE}/extracoes/{eid}/apply", json={})
        d = cc.patch(f"{BASE}/extracoes/{eid}", json={"brain_ids": [b2]}).json()["data"]
        assert {t["brain_id"] for t in d["targets"]} == {b1, b2} and d["status"] == "ready"

    def test_patch_validations(self, cc):
        b = _brain(cc)
        eid = _create(cc, [b]).json()["data"]["id"]
        assert cc.patch(f"{BASE}/extracoes/{eid}", json={"transcript": "  "}).status_code == 422
        assert cc.patch(f"{BASE}/extracoes/{eid}", json={"brain_ids": [_brain(cc, org="other-org", marca=OTHER_MARCA)]}).status_code == 422
        assert cc.patch(f"{BASE}/extracoes/{eid}", json={"name": ""}).status_code == 422
        assert cc.patch(f"{BASE}/extracoes/{eid}", json={"nope": 1}).status_code == 422
        cc.mock_supabase.from_("cs_extractions").update({"status": "error"}).eq("id", eid).execute()
        assert cc.patch(f"{BASE}/extracoes/{eid}", json={"transcript": "x"}).status_code == 409

    def test_delete_keeps_appended_text_and_removes_targets(self, cc):
        b = _brain(cc)
        eid = _create(cc, [b]).json()["data"]["id"]
        cc.post(f"{BASE}/extracoes/{eid}/apply", json={})
        assert cc.delete(f"{BASE}/extracoes/{eid}").status_code == 204
        assert cc.get(f"{BASE}/extracoes/{eid}").status_code == 404
        assert "Texto da aula" in _content(cc, b)


class TestIsolationAndAuth:
    def _foreign_extraction(self, cc):
        eid = str(uuid.uuid4())
        cc.mock_supabase.from_("cs_extractions").insert({
            "id": eid, "org_id": "other-org", "marca_id": OTHER_MARCA, "name": "Alheia",
            "source_kind": "text", "transcript": "segredo", "status": "ready",
        }).execute()
        return eid

    def test_other_orgs_extraction_is_404_everywhere(self, cc):
        eid = self._foreign_extraction(cc)
        assert cc.get(f"{BASE}/extracoes/{eid}").status_code == 404
        assert cc.patch(f"{BASE}/extracoes/{eid}", json={"name": "x"}).status_code == 404
        assert cc.post(f"{BASE}/extracoes/{eid}/apply", json={}).status_code == 404
        assert cc.delete(f"{BASE}/extracoes/{eid}").status_code == 404

    @pytest.mark.parametrize("method,path,kw", [
        ("get", f"/extracoes?marca_id={MARCA}", {}),
        ("post", "/extracoes", {"json": {"marca_id": MARCA, "name": "x", "brain_ids": [str(uuid.uuid4())], "text": "t"}}),
        ("get", f"/extracoes/{uuid.uuid4()}", {}),
        ("patch", f"/extracoes/{uuid.uuid4()}", {"json": {"name": "x"}}),
        ("post", f"/extracoes/{uuid.uuid4()}/apply", {"json": {}}),
        ("delete", f"/extracoes/{uuid.uuid4()}", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)
