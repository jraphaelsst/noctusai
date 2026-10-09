"""Minha Pesquisa (CoreStudio rebuild) — backend contract tests.

The classifier LLM is faked through the real DI seam
(``get_pesquisa_llm`` dependency override) — no patching of our own code.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.modules.media_creation.pesquisa_variables import (
    CLASSIFIABLE,
    VARIABLES,
    seed_sql,
)
from app.modules.media_creation.prompts.pesquisa_classifier import (
    PESQUISA_CLASSIFIER_SYSTEM_PROMPT,
    parse_classifier_output,
)
from app.modules.media_creation.routers.pesquisa import get_pesquisa_llm

BASE = "/api/media-creation/pesquisa"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_ORG_MARCA = str(uuid.uuid4())
_MIG = Path(__file__).resolve().parents[3] / "migrations" / "217_cs_research.sql"


@pytest.fixture
def pc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert(
        {"id": OTHER_ORG_MARCA, "org_id": "other-org", "name": "Marca B"}
    ).execute()
    client.llm_reply = ""
    client.llm_error = None

    async def fake_llm(system, user, org_id):
        client.llm_calls = getattr(client, "llm_calls", []) + [(system, user, org_id)]
        if client.llm_error:
            raise client.llm_error
        return client.llm_reply

    client._tc.app.dependency_overrides[get_pesquisa_llm] = lambda: fake_llm
    return client


def _items(pc):
    return pc.mock_supabase.from_("cs_research_items").select("*").execute().data


def _add(pc, lines, slug="DORES-TANGIVEIS-DO-AVATAR", marca=MARCA):
    return pc.post(f"{BASE}/items", json={"marca_id": marca, "variable_slug": slug, "lines": lines})


class TestVariablesSeed:
    def test_exactly_40_with_four_groups(self):
        assert len(VARIABLES) == 40
        assert len({v.slug for v in VARIABLES}) == 40
        assert {v.grupo for v in VARIABLES} == {"publico", "especialista", "produto", "global"}
        assert len(CLASSIFIABLE) == 36
        assert sum(v.corestudio_id is not None for v in VARIABLES) == 33

    def test_migration_carries_the_generated_seed_verbatim(self):
        sql = _MIG.read_text()
        assert seed_sql() in sql
        assert sql.count("\n    ('") == 40

    def test_prompt_lists_all_36_and_no_global(self):
        for v in CLASSIFIABLE:
            assert "{{" + v.slug + "}} | " + v.description in PESQUISA_CLASSIFIER_SYSTEM_PROMPT
        assert "VERBOS-PODEROSOS" not in PESQUISA_CLASSIFIER_SYSTEM_PROMPT

    def test_endpoint_lists_variables(self, pc):
        for i, v in enumerate(VARIABLES, 1):
            pc.mock_supabase.from_("cs_research_variables").insert({
                "slug": v.slug, "label": v.label, "grupo": v.grupo,
                "description": v.description, "corestudio_id": v.corestudio_id,
                "sort_order": i, "classifiable": v.classifiable,
            }).execute()
        r = pc.get(f"{BASE}/variables")
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]) == 40


class TestItemsCrud:
    def test_manual_add_is_approved_and_duplicate_skipped(self, pc):
        r = _add(pc, ["dor um", "Dor Um", "dor dois"])
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert (d["saved"], d["skipped"]) == (2, 1)
        assert {i["status"] for i in d["items"]} == {"approved"}
        assert {i["origin"] for i in d["items"]} == {"manual"}
        d2 = _add(pc, ["DOR UM"]).json()["data"]
        assert (d2["saved"], d2["skipped"]) == (0, 1)

    def test_list_counts_and_filters(self, pc):
        _add(pc, ["a", "b"])
        _add(pc, ["c"], slug="MEDOS-DO-AVATAR")
        r = pc.get(f"{BASE}/items", params={"marca_id": MARCA})
        assert r.status_code == 200, r.text
        assert len(r.json()["data"]["items"]) == 3
        r = pc.get(f"{BASE}/items", params={"marca_id": MARCA, "variable_slug": "MEDOS-DO-AVATAR"})
        assert [i["content"] for i in r.json()["data"]["items"]] == ["c"]
        c = pc.get(f"{BASE}/items/counts", params={"marca_id": MARCA}).json()["data"]
        assert c["approved"] == 3 and c["pending"] == 0
        assert c["by_variable"]["DORES-TANGIVEIS-DO-AVATAR"] == {"approved": 2, "pending": 0}

    def test_approve_reject_delete_transitions(self, pc):
        pc.llm_reply = "{{DORES-TANGIVEIS-DO-AVATAR}}\n[insônia]\n\n{{MEDOS-DO-AVATAR}}\n[perder o emprego]"
        pc.post(f"{BASE}/items/classify", json={"marca_id": MARCA, "text": "insônia\nperder o emprego"})
        pend = pc.get(f"{BASE}/items", params={"marca_id": MARCA, "status": "pending"}).json()["data"]
        assert pend["total"] == 2
        a, b = pend["items"][0]["id"], pend["items"][1]["id"]
        r = pc.post(f"{BASE}/items/{a}/approve")
        assert r.status_code == 200 and r.json()["data"]["status"] == "approved"
        r = pc.post(f"{BASE}/items/{b}/reject")
        assert r.status_code == 200
        # rejected is hidden everywhere and cannot be approved again
        listed = pc.get(f"{BASE}/items", params={"marca_id": MARCA, "status": "pending"}).json()["data"]
        assert listed["items"] == []
        assert pc.post(f"{BASE}/items/{b}/approve").status_code == 404
        counts = pc.get(f"{BASE}/items/counts", params={"marca_id": MARCA}).json()["data"]
        assert counts["approved"] == 1 and counts["pending"] == 0
        assert pc.delete(f"{BASE}/items/{a}").status_code == 204
        assert pc.delete(f"{BASE}/items/{a}").status_code == 404

    def test_manual_readd_of_rejected_flips_to_approved_but_ai_does_not(self, pc):
        _add(pc, ["x"])
        item = _items(pc)[0]
        pc.post(f"{BASE}/items/{item['id']}/reject")
        pc.llm_reply = "{{DORES-TANGIVEIS-DO-AVATAR}}\n[x]"
        d = pc.post(f"{BASE}/items/classify", json={"marca_id": MARCA, "text": "x"}).json()["data"]
        assert d["saved"] == 0 and d["skipped"] == 1
        assert _items(pc)[0]["status"] == "rejected"
        d = _add(pc, ["x"]).json()["data"]
        assert d["saved"] == 1
        assert _items(pc)[0]["status"] == "approved"

    def test_bulk_and_empty(self, pc):
        _add(pc, ["a", "b", "c"])
        ids = [i["id"] for i in _items(pc)]
        r = pc.post(f"{BASE}/items/bulk", json={"marca_id": MARCA, "action": "reject", "ids": ids[:2]})
        assert r.json()["data"]["affected"] == 2
        r = pc.post(f"{BASE}/items/bulk", json={"marca_id": MARCA, "action": "delete", "ids": ids[:1]})
        assert r.json()["data"]["affected"] == 1
        assert pc.post(f"{BASE}/items/empty", json={"marca_id": MARCA, "confirm": False}).status_code == 422
        r = pc.post(f"{BASE}/items/empty", json={"marca_id": MARCA, "confirm": True})
        assert r.json()["data"]["deleted"] == 2
        assert _items(pc) == []

    def test_validation(self, pc):
        assert _add(pc, ["   "]).status_code == 422
        assert _add(pc, ["x" * 501]).status_code == 422
        assert _add(pc, ["ok"], slug="NAO-EXISTE").status_code == 422


class TestOwnership:
    def test_cross_org_marca_is_404_everywhere(self, pc):
        m = OTHER_ORG_MARCA
        assert pc.get(f"{BASE}/items", params={"marca_id": m}).status_code == 404
        assert pc.get(f"{BASE}/items/counts", params={"marca_id": m}).status_code == 404
        assert _add(pc, ["x"], marca=m).status_code == 404
        assert pc.post(f"{BASE}/items/classify", json={"marca_id": m, "text": "x"}).status_code == 404
        assert pc.post(f"{BASE}/items/bulk", json={"marca_id": m, "action": "delete", "ids": [str(uuid.uuid4())]}).status_code == 404
        assert pc.post(f"{BASE}/items/empty", json={"marca_id": m, "confirm": True}).status_code == 404

    def test_other_orgs_item_is_404(self, pc):
        pc.mock_supabase.from_("cs_research_items").insert({
            "id": str(uuid.uuid4()), "org_id": "other-org", "marca_id": OTHER_ORG_MARCA,
            "variable_slug": "MEDOS-DO-AVATAR", "content": "z", "status": "pending", "origin": "manual",
        }).execute()
        iid = _items(pc)[0]["id"]
        assert pc.post(f"{BASE}/items/{iid}/approve").status_code == 404
        assert pc.delete(f"{BASE}/items/{iid}").status_code == 404


class TestClassify:
    def test_saves_pending_ai_classified(self, pc):
        pc.llm_reply = (
            "{{DORES-TANGIVEIS-DO-AVATAR}}\n[insônia]\n\n"
            "{{FRUSTRACOES-DO-AVATAR}}\n[já tentei várias dietas]"
        )
        r = pc.post(f"{BASE}/items/classify", json={"marca_id": MARCA, "text": "1. insônia\njá tentei várias dietas"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["saved"] == 2 and d["unclassified"] == []
        assert d["classified"]["FRUSTRACOES-DO-AVATAR"] == ["já tentei várias dietas"]
        assert {(i["status"], i["origin"]) for i in _items(pc)} == {("pending", "ai_classified")}
        system, user, org = pc.llm_calls[0]
        assert user == "1. insônia\njá tentei várias dietas" and org == ORG

    def test_llm_error_is_502_and_saves_nothing(self, pc):
        pc.llm_error = RuntimeError("provider down")
        r = pc.post(f"{BASE}/items/classify", json={"marca_id": MARCA, "text": "insônia"})
        assert r.status_code == 502
        assert r.json()["error"]["message"] == "Falha ao classificar com IA"
        assert _items(pc) == []

    def test_unknown_slug_and_missing_line_go_to_unclassified(self, pc):
        pc.llm_reply = "{{GPT}}\n[verbo]\n\n{{INVENTADO}}\n[foo]\n\n{{MEDOS-DO-AVATAR}}\n[perder tudo]"
        r = pc.post(f"{BASE}/items/classify", json={"marca_id": MARCA, "text": "verbo\nfoo\nperder tudo\nlinha esquecida"})
        d = r.json()["data"]
        assert d["saved"] == 1 and list(d["classified"]) == ["MEDOS-DO-AVATAR"]
        assert sorted(d["unclassified"]) == ["foo", "linha esquecida", "verbo"]


class TestParser:
    def test_valid_pairs_and_chatter(self):
        reply = (
            "Claro! Aqui está:\n\n{{ DORES-TANGIVEIS-DO-AVATAR }}\n\n[insônia]\n\n"
            "{{MEDOS-DO-AVATAR}}\nperder o emprego\nEspero ter ajudado."
        )
        res = parse_classifier_output(reply, ["insônia", "perder o emprego"])
        assert res.classified == {
            "DORES-TANGIVEIS-DO-AVATAR": ["insônia"],
            "MEDOS-DO-AVATAR": ["perder o emprego"],
        }
        assert res.unclassified == []

    def test_slug_without_content_and_empty_reply(self):
        res = parse_classifier_output("{{MEDOS-DO-AVATAR}}\n{{DORES-TANGIVEIS-DO-AVATAR}}\n[a]", ["a", "b"])
        assert res.classified == {"DORES-TANGIVEIS-DO-AVATAR": ["a"]}
        assert res.unclassified == ["b"]
        assert parse_classifier_output("", ["x"]).unclassified == ["x"]


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", [
        ("get", "/variables", {}),
        ("get", f"/items?marca_id={MARCA}", {}),
        ("get", f"/items/counts?marca_id={MARCA}", {}),
        ("post", "/items", {"json": {"marca_id": MARCA, "variable_slug": "GPT", "lines": ["x"]}}),
        ("post", "/items/classify", {"json": {"marca_id": MARCA, "text": "x"}}),
        ("post", f"/items/{uuid.uuid4()}/approve", {}),
        ("post", f"/items/{uuid.uuid4()}/reject", {}),
        ("delete", f"/items/{uuid.uuid4()}", {}),
        ("post", "/items/bulk", {"json": {"marca_id": MARCA, "action": "delete", "ids": [str(uuid.uuid4())]}}),
        ("post", "/items/empty", {"json": {"marca_id": MARCA, "confirm": True}}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)
