"""Assuntos Virais — backend contract tests (pesquisa-wave2-contract.md section 5)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import pytest

from app.modules.media_creation.services.assuntos_virais_service import (
    AssuntosViraisService,
)

BASE = "/api/media-creation/pesquisa/assuntos-virais"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_ORG_MARCA = str(uuid.uuid4())


@dataclass(frozen=True)
class Post:
    id: str
    plays: Optional[int] = None
    kind: str = "instagram_media"
    account_id: Optional[str] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    published_at: Optional[str] = None
    likes: Optional[int] = None
    comments: Optional[int] = None


@pytest.fixture
def vc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_ORG_MARCA, "org_id": "other-org", "name": "B"}).execute()
    return client


def _svc(vc) -> AssuntosViraisService:
    return AssuntosViraisService(vc.mock_supabase, ORG, "u1")


def _rows(vc):
    return vc.mock_supabase.from_("cs_viral_topics").select("*").execute().data


def _add(vc, topics, marca=MARCA):
    return vc.post(BASE, json={"marca_id": marca, "topics": topics})


def _topic(vc, name):
    return next(r for r in _rows(vc) if r["topic"] == name)


class TestCrud:
    def test_manual_add_is_approved_with_null_plays(self, vc):
        r = _add(vc, ["  Dólar  ", "Juros"])
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["saved"] == 2 and data["skipped"] == 0
        assert {i["status"] for i in data["items"]} == {"approved"}
        assert {i["origin"] for i in data["items"]} == {"manual"}
        assert all(i["total_plays"] is None and i["fontes_count"] == 0 for i in data["items"])
        assert {i["topic"] for i in data["items"]} == {"Dólar", "Juros"}

    def test_duplicate_is_skipped_case_insensitive(self, vc):
        _add(vc, ["Dólar"])
        data = _add(vc, ["dólar", "DÓLAR"]).json()["data"]
        assert data["saved"] == 0 and data["skipped"] == 2

    def test_too_long_or_blank_is_422(self, vc):
        assert _add(vc, ["x" * 256]).status_code == 422
        assert _add(vc, ["   "]).status_code == 422
        assert _add(vc, []).status_code == 422

    def test_manual_readd_of_rejected_flips_to_approved(self, vc):
        tid = _add(vc, ["Dólar"]).json()["data"]["items"][0]["id"]
        assert vc.post(f"{BASE}/{tid}/reject").status_code == 200
        data = _add(vc, ["dólar"]).json()["data"]
        assert data["saved"] == 1
        assert _topic(vc, "Dólar")["status"] == "approved"

    def test_approve_reject_and_hidden_after_reject(self, vc):
        _svc(vc).salvar_extraidos(MARCA, None, [("Tema", Post("p1", 10), None)])
        tid = _topic(vc, "Tema")["id"]
        assert _topic(vc, "Tema")["status"] == "pending"
        r = vc.post(f"{BASE}/{tid}/approve")
        assert r.status_code == 200 and r.json()["data"]["status"] == "approved"
        r = vc.post(f"{BASE}/{tid}/reject")
        assert r.json()["data"]["status"] == "rejected"
        assert vc.post(f"{BASE}/{tid}/approve").status_code == 404
        assert vc.get(f"{BASE}/{tid}/fontes").status_code == 404
        for st in ("approved", "pending"):
            r = vc.get(BASE, params={"marca_id": MARCA, "status": st})
            assert r.json()["data"]["items"] == []
        assert vc.get(f"{BASE}/counts", params={"marca_id": MARCA}).json()["data"] == {
            "approved": 0, "pending": 0,
        }

    def test_delete_204_then_404(self, vc):
        tid = _add(vc, ["Dólar"]).json()["data"]["items"][0]["id"]
        assert vc.delete(f"{BASE}/{tid}").status_code == 204
        assert vc.delete(f"{BASE}/{tid}").status_code == 404

    def test_counts_and_list_shape(self, vc):
        _add(vc, ["Manual"])
        s = _svc(vc)
        s.salvar_extraidos(MARCA, None, [
            ("Baixo", Post("a", 5), None), ("Alto", Post("b", 500), None),
        ])
        for name in ("Baixo", "Alto"):
            vc.post(f"{BASE}/{_topic(vc, name)['id']}/approve")
        assert vc.get(f"{BASE}/counts", params={"marca_id": MARCA}).json()["data"] == {
            "approved": 3, "pending": 0,
        }
        items = vc.get(BASE, params={"marca_id": MARCA}).json()["data"]["items"]
        # ORDER BY is applied by PostgREST; the mock client ignores it, so the
        # sort contract is asserted on the shape, not the order.
        assert {i["topic"] for i in items} == {"Manual", "Alto", "Baixo"}
        by = {i["topic"]: i for i in items}
        assert by["Alto"]["fontes_count"] == 1 and by["Manual"]["fontes_count"] == 0
        assert by["Alto"]["total_plays"] == 500 and by["Manual"]["total_plays"] is None
        assert vc.get(BASE, params={"marca_id": MARCA, "sort": "recent"}).status_code == 200
        assert vc.get(BASE, params={"marca_id": MARCA, "sort": "bogus"}).status_code == 422
        total = vc.get(BASE, params={"marca_id": MARCA, "limit": 1}).json()["data"]["total"]
        assert total == 3

    def test_bulk_actions(self, vc):
        ids = [i["id"] for i in _add(vc, ["A", "B", "C"]).json()["data"]["items"]]
        r = vc.post(f"{BASE}/bulk", json={"marca_id": MARCA, "action": "reject", "ids": ids[:2]})
        assert r.json()["data"]["affected"] == 2
        r = vc.post(f"{BASE}/bulk", json={"marca_id": MARCA, "action": "delete", "ids": ids})
        assert r.json()["data"]["affected"] == 3
        assert _rows(vc) == []

    def test_empty_only_removes_given_status(self, vc):
        _add(vc, ["Aprovado", "Rejeitado"])
        _svc(vc).salvar_extraidos(MARCA, None, [("Pendente", Post("p"), None)])
        vc.post(f"{BASE}/{_topic(vc, 'Rejeitado')['id']}/reject")
        r = vc.post(f"{BASE}/empty", json={"marca_id": MARCA, "status": "approved", "confirm": True})
        assert r.json()["data"] == {"deleted": 1}
        assert {x["topic"] for x in _rows(vc)} == {"Rejeitado", "Pendente"}
        assert vc.post(f"{BASE}/empty", json={"marca_id": MARCA, "status": "approved"}).status_code == 422


class TestSalvarExtraidos:
    def test_new_topic_is_pending_extraction_with_source_and_plays(self, vc):
        res = _svc(vc).salvar_extraidos(MARCA, str(uuid.uuid4()), [
            ("Tema novo", Post("p1", 120, url="https://x/1"), "frase de origem"),
        ])
        assert res == {"saved": 1, "skipped": 0}
        t = _topic(vc, "Tema novo")
        assert (t["status"], t["origin"], t["total_plays"]) == ("pending", "extraction", 120)
        src = vc.mock_supabase.from_("cs_viral_topic_sources").select("*").execute().data
        assert len(src) == 1 and src[0]["excerpt"] == "frase de origem" and src[0]["plays"] == 120

    def test_duplicate_topic_adds_source_and_recomputes_skipping_null(self, vc):
        s = _svc(vc)
        s.salvar_extraidos(MARCA, None, [("Tema", Post("p1", 100), None)])
        res = s.salvar_extraidos(MARCA, None, [
            ("tema", Post("p2", 50), None),
            ("TEMA", Post("p3", None), None),
            ("Tema", Post("p2", 50), None),  # same post again: no second source
        ])
        assert res == {"saved": 0, "skipped": 3}
        assert _topic(vc, "Tema")["total_plays"] == 150
        assert len(vc.mock_supabase.from_("cs_viral_topic_sources").select("*").execute().data) == 3

    def test_all_null_plays_stays_null_and_overlong_is_skipped(self, vc):
        res = _svc(vc).salvar_extraidos(MARCA, None, [
            ("Sem plays", Post("p1", None), None), ("x" * 300, Post("p2", 1), None),
        ])
        assert res == {"saved": 1, "skipped": 1}
        assert _topic(vc, "Sem plays")["total_plays"] is None

    def test_cross_org_marca_is_404(self, vc):
        from app.modules.media_creation.services.pesquisa_service import PesquisaError

        with pytest.raises(PesquisaError) as e:
            _svc(vc).salvar_extraidos(OTHER_ORG_MARCA, None, [("T", Post("p"), None)])
        assert e.value.status == 404


class TestFontes:
    def test_sorted_by_plays_desc_nulls_last(self, vc):
        _svc(vc).salvar_extraidos(MARCA, None, [
            ("Tema", Post("a", 10), None), ("Tema", Post("b", None), None),
            ("Tema", Post("c", 900), None),
        ])
        tid = _topic(vc, "Tema")["id"]
        data = vc.get(f"{BASE}/{tid}/fontes").json()["data"]
        assert [d["source_id"] for d in data] == ["c", "a", "b"]
        assert set(data[0]) == {
            "source_kind", "account_id", "source_id", "url", "thumbnail_url",
            "published_at", "plays", "likes", "comments", "excerpt",
        }

    def test_refresher_updates_urls_and_failure_falls_back_to_snapshot(self, vc):
        _svc(vc).salvar_extraidos(MARCA, None, [("Tema", Post("a", 10, url="old"), None)])
        tid = _topic(vc, "Tema")["id"]

        def ok(org, marca, rows):
            return [{**r, "url": "fresh"} for r in rows]

        def boom(org, marca, rows):
            raise RuntimeError("source gone")

        good = AssuntosViraisService(vc.mock_supabase, ORG, "u1", source_refresher=ok)
        assert good.list_sources(tid)[0]["url"] == "fresh"
        bad = AssuntosViraisService(vc.mock_supabase, ORG, "u1", source_refresher=boom)
        assert bad.list_sources(tid)[0]["url"] == "old"


class TestOwnership:
    def test_cross_org_marca_is_404_everywhere(self, vc):
        m = OTHER_ORG_MARCA
        assert vc.get(BASE, params={"marca_id": m}).status_code == 404
        assert vc.get(f"{BASE}/counts", params={"marca_id": m}).status_code == 404
        assert _add(vc, ["X"], marca=m).status_code == 404
        r = vc.post(f"{BASE}/bulk", json={"marca_id": m, "action": "delete", "ids": [str(uuid.uuid4())]})
        assert r.status_code == 404
        r = vc.post(f"{BASE}/empty", json={"marca_id": m, "status": "pending", "confirm": True})
        assert r.status_code == 404

    def test_other_orgs_topic_is_404(self, vc):
        other = str(uuid.uuid4())
        vc.mock_supabase.from_("cs_viral_topics").insert({
            "id": other, "org_id": "other-org", "marca_id": OTHER_ORG_MARCA, "topic": "T",
            "status": "approved", "origin": "manual",
        }).execute()
        assert vc.post(f"{BASE}/{other}/approve").status_code == 404
        assert vc.delete(f"{BASE}/{other}").status_code == 404
        assert vc.get(f"{BASE}/{other}/fontes").status_code == 404


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", [
        ("get", "", {"params": {"marca_id": MARCA}}),
        ("get", "/counts", {"params": {"marca_id": MARCA}}),
        ("post", "", {"json": {"marca_id": MARCA, "topics": ["x"]}}),
        ("post", f"/{uuid.uuid4()}/approve", {}),
        ("post", f"/{uuid.uuid4()}/reject", {}),
        ("delete", f"/{uuid.uuid4()}", {}),
        ("post", "/bulk", {"json": {"marca_id": MARCA, "action": "delete", "ids": [str(uuid.uuid4())]}}),
        ("post", "/empty", {"json": {"marca_id": MARCA, "status": "pending", "confirm": True}}),
        ("get", f"/{uuid.uuid4()}/fontes", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)
