"""The roteiro lifecycle — CONTRACT products/social-wiring/projects/roteiro-ciclo-CONTRACT.md §3 (R1-R14), §4.

One test per row of the contract table, one per side effect, `permissoes` per role (owner, admin, supervisor,
member), the strict-401 boundary and the access-tier markers. The database rules the mock cannot show (the atomic
`roteiro_gerar`, the backfill, the CHECKs) are proven on a real Postgres by
`tests/test_migration_338_roteiro_ciclo.py`; here `roteiro_gerar` is mirrored (see `roteiro_rpc`).

The wire error shape of these routes is `{detail, code, message, details?}` (`roteiro_erros.RoteiroErro`).
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from noctusai_lib.testing import TEST_USER_ID

from tests.modules.card_hub import roteiro_rpc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_agendamentos import atendimento_row
from tests.modules.card_hub.test_roteiros import imovel_row, registry_row

OUTRO_USUARIO = str(uuid4())
URL = "/api/clientes/{cid}/roteiros"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, *, codigos=("ONE9001", "ONE9002", "ONE9003"), lead_id=None, meta_ads_lead_id=None):
    cid, aid = str(uuid4()), str(uuid4())
    atendimento = atendimento_row(aid, cid)
    atendimento["lead_id"], atendimento["meta_ads_lead_id"] = lead_id, meta_ads_lead_id
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("atendimentos", [atendimento])
    scoped.set_table_data("imovel_registry", [registry_row(c) for c in codigos])
    # No `foto_destaque`: the PDF must not reach for the network in a test.
    scoped.set_table_data("imoveis", [imovel_row(c, foto_destaque=None) for c in codigos])
    for tabela in ("imovel_dados", "roteiros", "visitas", "cliente_imovel_interesses", "pipeline_stages",
                   "usuario_papeis", "atendimento_negociacao", "negociacao_defaults", "cliente_membros",
                   "lead_corretores", "atendimento_propostas"):
        scoped.set_table_data(tabela, [])
    return cid, aid


def _papel(client, org_role):
    rows = [] if org_role is None else [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": org_role}]
    client.mock_supabase.set_table_data("noctus_users", rows)


def _supervisor(scoped):
    scoped.set_table_data(
        "usuario_papeis",
        [{"org_id": ORG_ID, "user_id": TEST_USER_ID, "papel": "supervisor"}],
    )


def _rascunho(client, cid, codigos=("ONE9001", "ONE9002"), **body) -> dict:
    resp = client.post(
        URL.format(cid=cid), json={"imoveis": list(codigos), "data_visita": "2026-10-10", **body}, headers=_auth()
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _gerar(client, cid, rid):
    return client.post(f"{URL.format(cid=cid)}/{rid}/gerar", headers=_auth())


def _gerado(client, cid, codigos=("ONE9001", "ONE9002"), **body) -> dict:
    r = _rascunho(client, cid, codigos, **body)
    resp = _gerar(client, cid, r["id"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _v(roteiro: dict, visita: dict) -> dict:
    """One visita out of the full Roteiro that R6/R7/R11 answer with."""
    return next(x for x in roteiro["visitas"] if x["id"] == visita["id"])


def _erro(resp) -> dict:
    """The typed error body of these routes: `{detail, code, message, details?}` (amendment v1.1 §4)."""
    return resp.json()


def _linha(scoped, tabela, **eq) -> list[dict]:
    q = scoped.table(tabela).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.execute().data or []


def _visita_url(cid, r, v, sufixo="") -> str:
    return f"{URL.format(cid=cid)}/{r['id']}/visitas/{v['id']}{sufixo}"


# ── R1 ──────────────────────────────────────────────────────────────────────

class TestR1Listar:
    def test_items_carry_drafts_and_the_whole_roteiro_shape(self, client, scoped):
        cid, _ = _seed(scoped)
        rascunho = _rascunho(client, cid)
        gerado = _gerado(client, cid, ("ONE9003",))
        body = client.get(URL.format(cid=cid), headers=_auth()).json()
        assert body["total"] == 2
        por_id = {r["id"]: r for r in body["items"]}
        assert por_id[rascunho["id"]]["status"] == "rascunho"
        assert por_id[gerado["id"]]["status"] == "gerado"
        chaves = {
            "id", "atendimento_id", "titulo", "data_visita", "hora_visita", "created_at", "updated_at", "status",
            "gerado_em", "gerado_por", "reaberto_em", "reaberto_por", "criado_por", "feedback_status", "feedback_em",
            "visitas", "contagem", "permissoes",
        }
        assert chaves <= set(por_id[rascunho["id"]])
        assert set(por_id[rascunho["id"]]["permissoes"]) == {
            "editar_imoveis", "gerar", "motivo_gerar", "baixar_pdf", "reabrir", "motivo_reabrir",
        }
        visita = por_id[rascunho["id"]]["visitas"][0]
        assert {"cancelada_por", "cancelada_motivo", "reagendada_para_visita_id", "resultado_em", "resultado_por"} <= set(visita)
        assert "nao_realizada_motivo" not in visita

    def test_unknown_cliente_is_404(self, client, scoped):
        _seed(scoped)
        assert client.get(URL.format(cid=uuid4()), headers=_auth()).status_code == 404


# ── R2 ──────────────────────────────────────────────────────────────────────

class TestR2Criar:
    def test_201_rascunho_with_no_funil_move_and_no_lead_link(self, client, scoped):
        cid, _ = _seed(scoped, lead_id=str(uuid4()))
        r = _rascunho(client, cid)
        assert r["status"] == "rascunho" and r["gerado_em"] is None
        assert "funil" not in r  # the funil moves on gerar
        assert r["criado_por"] == str(TEST_USER_ID)
        assert _linha(scoped, "cliente_imovel_interesses") == []  # nothing is linked to the lead yet

    def test_nothing_is_required_to_start_a_draft(self, client, scoped):
        cid, _ = _seed(scoped)
        resp = client.post(URL.format(cid=cid), json={}, headers=_auth())
        assert resp.status_code == 201 and resp.json()["visitas"] == [] and resp.json()["data_visita"] is None

    def test_409_ambiguous_atendimento(self, client, scoped):
        cid, _ = _seed(scoped)
        scoped.set_table_data(
            "atendimentos", [atendimento_row(str(uuid4()), cid), atendimento_row(str(uuid4()), cid)]
        )
        assert client.post(URL.format(cid=cid), json={"imoveis": ["ONE9001"]}, headers=_auth()).status_code == 409

    def test_404_unknown_codigo(self, client, scoped):
        cid, _ = _seed(scoped)
        assert client.post(URL.format(cid=cid), json={"imoveis": ["NOPE0001"]}, headers=_auth()).status_code == 404

    def test_422_shape(self, client, scoped):
        cid, _ = _seed(scoped)
        assert client.post(URL.format(cid=cid), json={"bogus": 1}, headers=_auth()).status_code == 422
        assert client.post(URL.format(cid=cid), json={"data_visita": "ontem"}, headers=_auth()).status_code == 422


# ── R3 ──────────────────────────────────────────────────────────────────────

class TestR3Patch:
    def test_allowed_in_both_statuses_and_returns_the_roteiro(self, client, scoped):
        cid, _ = _seed(scoped)
        for r in (_rascunho(client, cid), _gerado(client, cid, ("ONE9003",))):
            resp = client.patch(
                f"{URL.format(cid=cid)}/{r['id']}",
                json={"titulo": "Terça", "data_visita": "2026-12-01", "hora_visita": "09:30"},
                headers=_auth(),
            )
            assert resp.status_code == 200, resp.text
            assert (resp.json()["titulo"], resp.json()["data_visita"], resp.json()["hora_visita"]) == (
                "Terça", "2026-12-01", "09:30")
            assert resp.json()["status"] == r["status"]

    def test_422_null_date_on_a_gerado_but_not_on_a_draft(self, client, scoped):
        cid, _ = _seed(scoped)
        gerado = _gerado(client, cid)
        resp = client.patch(f"{URL.format(cid=cid)}/{gerado['id']}", json={"data_visita": None}, headers=_auth())
        assert resp.status_code == 422 and _erro(resp)["code"] == "roteiro_sem_data"
        assert _erro(resp)["message"] == "Informe a data da visita."
        rascunho = _rascunho(client, cid, ("ONE9003",))
        resp = client.patch(f"{URL.format(cid=cid)}/{rascunho['id']}", json={"data_visita": None}, headers=_auth())
        assert resp.status_code == 200 and resp.json()["data_visita"] is None

    def test_autosave_bumps_updated_at(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        scoped.table("roteiros").update({"updated_at": "2000-01-01T00:00:00+00:00"}).eq("id", r["id"]).execute()
        out = client.patch(f"{URL.format(cid=cid)}/{r['id']}", json={"titulo": "x"}, headers=_auth()).json()
        assert out["updated_at"] > "2000-01-01"


# ── R4 ──────────────────────────────────────────────────────────────────────

class TestR4Delete:
    def test_a_draft_and_a_gerado_without_outcomes_are_deletable(self, client, scoped):
        cid, _ = _seed(scoped)
        assert client.delete(f"{URL.format(cid=cid)}/{_rascunho(client, cid)['id']}", headers=_auth()).status_code == 204
        gerado = _gerado(client, cid, ("ONE9003",))
        assert client.delete(f"{URL.format(cid=cid)}/{gerado['id']}", headers=_auth()).status_code == 204
        assert client.get(URL.format(cid=cid), headers=_auth()).json()["total"] == 0

    def test_409_gerado_with_any_outcome(self, client, scoped):
        cid, _ = _seed(scoped)
        gerado = _gerado(client, cid)
        assert client.patch(
            _visita_url(cid, gerado, gerado["visitas"][0]), json={"status": "realizada"}, headers=_auth()
        ).status_code == 200
        resp = client.delete(f"{URL.format(cid=cid)}/{gerado['id']}", headers=_auth())
        assert resp.status_code == 409
        assert _erro(resp)["code"] == "roteiro_gerado_com_resultados"
        assert _erro(resp)["details"] == {"quantidade": 1}
        assert client.get(URL.format(cid=cid), headers=_auth()).json()["total"] == 1


# ── R5 / R6 / R7 ────────────────────────────────────────────────────────────

class TestR5R6R7ImoveisDoRascunho:
    def test_r5_reorder_a_draft_and_409_on_a_gerado(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid, ("ONE9001", "ONE9002", "ONE9003"))
        ids = [v["id"] for v in reversed(r["visitas"])]
        resp = client.put(f"{URL.format(cid=cid)}/{r['id']}/ordem", json={"visita_ids": ids}, headers=_auth())
        assert resp.status_code == 200
        assert [v["codigo"] for v in resp.json()["visitas"]] == ["ONE9003", "ONE9002", "ONE9001"]
        assert _gerar(client, cid, r["id"]).status_code == 200
        resp = client.put(f"{URL.format(cid=cid)}/{r['id']}/ordem", json={"visita_ids": ids}, headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_gerado"

    def test_r5_400_when_the_set_does_not_match(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = client.put(
            f"{URL.format(cid=cid)}/{r['id']}/ordem", json={"visita_ids": [r["visitas"][0]["id"]]}, headers=_auth()
        )
        assert resp.status_code == 400

    def test_r6_add_to_a_draft_and_409_on_a_gerado(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid, ("ONE9001",))
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/visitas", json={"codigo": "ONE9002"}, headers=_auth())
        assert resp.status_code == 201  # R6 answers with the full Roteiro
        assert resp.json()["id"] == r["id"] and [v["codigo"] for v in resp.json()["visitas"]] == ["ONE9001", "ONE9002"]
        assert _gerar(client, cid, r["id"]).status_code == 200
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/visitas", json={"codigo": "ONE9003"}, headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_gerado"

    def test_r7_remove_from_a_draft_and_409_on_a_gerado(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = client.delete(_visita_url(cid, r, r["visitas"][0]), headers=_auth())
        assert resp.status_code == 200  # R7 answers 200 with the full Roteiro
        assert resp.json()["id"] == r["id"] and [v["codigo"] for v in resp.json()["visitas"]] == ["ONE9002"]
        assert _gerar(client, cid, r["id"]).status_code == 200
        resp = client.delete(_visita_url(cid, r, r["visitas"][1]), headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_gerado"

    def test_each_autosave_returns_state_that_bumps_updated_at(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid, ("ONE9001",))
        scoped.table("roteiros").update({"updated_at": "2000-01-01T00:00:00+00:00"}).eq("id", r["id"]).execute()
        client.post(f"{URL.format(cid=cid)}/{r['id']}/visitas", json={"codigo": "ONE9002"}, headers=_auth())
        atual = client.get(URL.format(cid=cid), headers=_auth()).json()["items"][0]
        assert atual["updated_at"] > "2000-01-01"


# ── R8 ──────────────────────────────────────────────────────────────────────

class TestR8Gerar:
    def test_flips_the_roteiro_and_stamps_who_and_when(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = _gerar(client, cid, r["id"])
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["status"] == "gerado" and out["gerado_em"] and out["gerado_por"] == str(TEST_USER_ID)
        assert out["permissoes"]["baixar_pdf"] is True and out["permissoes"]["editar_imoveis"] is False

    def test_the_funil_outcome_rides_on_the_response(self, client, scoped):
        cid, _ = _seed(scoped)
        out = _gerado(client, cid)
        assert out["funil"]["moveu"] is False and out["funil"]["motivo"] == "etapa_inexistente"

    def test_links_the_lead_for_each_visita_codigo(self, client, scoped):
        lead = str(uuid4())
        cid, _ = _seed(scoped, lead_id=lead)
        _gerado(client, cid, ("ONE9001", "ONE9002"))
        linhas = {i["codigo"]: i for i in _linha(scoped, "cliente_imovel_interesses", cliente_id=cid)}
        assert set(linhas) == {"ONE9001", "ONE9002"}
        assert all(i["origem"] == "roteiro" and i["lead_id"] == lead for i in linhas.values())

    def test_fills_empty_only_and_never_changes_an_existing_origem(self, client, scoped):
        lead = str(uuid4())
        cid, _ = _seed(scoped, lead_id=lead)
        scoped.set_table_data("cliente_imovel_interesses", [
            {"id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "codigo": "ONE9001", "origem": "manual",
             "lead_id": None, "meta_ads_lead_id": None, "deleted_at": None, "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "codigo": "ONE9002", "origem": "lead",
             "lead_id": None, "meta_ads_lead_id": "meta-9", "deleted_at": None, "created_at": "2026-01-01T00:00:00+00:00"},
        ])
        _gerado(client, cid, ("ONE9001", "ONE9002", "ONE9003"))
        linhas = {i["codigo"]: i for i in _linha(scoped, "cliente_imovel_interesses", cliente_id=cid)}
        assert (linhas["ONE9001"]["origem"], linhas["ONE9001"]["lead_id"]) == ("manual", lead)
        assert (linhas["ONE9002"]["origem"], linhas["ONE9002"]["lead_id"], linhas["ONE9002"]["meta_ads_lead_id"]) == (
            "lead", None, "meta-9")
        assert linhas["ONE9003"]["origem"] == "roteiro"

    def test_enters_the_feedback_flow_only_now(self, client, scoped):
        from app.modules.card_hub import roteiros_feedback_service as fb

        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        agora = datetime(2026, 11, 1, 12, tzinfo=fb.TZ)
        from uuid import UUID
        assert fb.pendentes(scoped, UUID(ORG_ID), agora=agora) == []
        _gerar(client, cid, r["id"])
        assert [p["roteiro_id"] for p in fb.pendentes(scoped, UUID(ORG_ID), agora=agora)] == [r["id"]]

    def test_409_already_generated(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        resp = _gerar(client, cid, r["id"])
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_ja_gerado"

    def test_422_without_imoveis(self, client, scoped):
        cid, _ = _seed(scoped)
        r = client.post(URL.format(cid=cid), json={"data_visita": "2026-10-10"}, headers=_auth()).json()
        resp = _gerar(client, cid, r["id"])
        assert resp.status_code == 422 and _erro(resp)["code"] == "roteiro_sem_imoveis"
        assert _erro(resp)["message"] == "Adicione ao menos um imóvel."

    def test_422_without_a_date(self, client, scoped):
        cid, _ = _seed(scoped)
        r = client.post(URL.format(cid=cid), json={"imoveis": ["ONE9001"]}, headers=_auth()).json()
        resp = _gerar(client, cid, r["id"])
        assert resp.status_code == 422 and _erro(resp)["code"] == "roteiro_sem_data"
        assert _erro(resp)["message"] == "Informe a data da visita."
        assert client.get(URL.format(cid=cid), headers=_auth()).json()["items"][0]["status"] == "rascunho"

    def test_404_unknown_or_foreign_roteiro(self, client, scoped):
        cid, _ = _seed(scoped)
        assert _gerar(client, cid, uuid4()).status_code == 404

    def test_atomicity_a_failure_in_the_transaction_leaves_nothing_behind(self, client, scoped):
        """ALL the writes of "gerar" live inside the one RPC, so when it fails NOTHING was written by Python: the
        roteiro is still a draft, no lead link exists, the funil did not move. (That the RPC itself rolls its own
        status flip back with a failed lead link is proven on a real Postgres in `test_migration_338_*`.)"""
        cid, _ = _seed(scoped, lead_id=str(uuid4()))
        r = _rascunho(client, cid)

        def falha(name, params=None):
            raise RuntimeError("forced failure inside roteiro_gerar")

        scoped.rpc = falha
        scoped.set_table_data("pipeline_movimentos", [])
        from app.main import app
        from fastapi.testclient import TestClient

        # No `with`: this needs a 500 instead of a raised exception, not the app's lifespan (workers, schedulers).
        resp = TestClient(app, raise_server_exceptions=False).post(f"{URL.format(cid=cid)}/{r['id']}/gerar", headers=_auth())
        assert resp.status_code == 500
        roteiro = _linha(scoped, "roteiros", id=r["id"])[0]
        assert roteiro["status"] == "rascunho" and roteiro.get("gerado_em") is None
        assert _linha(scoped, "cliente_imovel_interesses") == []
        assert _linha(scoped, "pipeline_movimentos") == []


# ── R9 ──────────────────────────────────────────────────────────────────────

class TestR9Reabrir:
    def test_the_owner_reopens_and_the_lead_link_and_funil_stay(self, client, scoped):
        lead = str(uuid4())
        cid, aid = _seed(scoped, lead_id=lead)
        _papel(client, "owner")
        r = _gerado(client, cid)
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["status"] == "rascunho" and out["reaberto_em"] and out["reaberto_por"] == str(TEST_USER_ID)
        assert out["permissoes"]["editar_imoveis"] is True
        assert len(_linha(scoped, "cliente_imovel_interesses", cliente_id=cid)) == 2  # not undone
        assert _linha(scoped, "atendimentos", id=aid)[0]["etapa_id"] is None  # funil untouched

    @pytest.mark.parametrize("papel", ["owner", "admin"])
    def test_owner_and_admin_may(self, client, scoped, papel):
        cid, _ = _seed(scoped)
        _papel(client, papel)
        r = _gerado(client, cid)
        assert client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth()).status_code == 200

    def test_a_supervisor_may(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "member")
        _supervisor(scoped)
        r = _gerado(client, cid)
        assert client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth()).status_code == 200

    @pytest.mark.parametrize("papel", ["member", "viewer", "corretor"])
    def test_403_everybody_else(self, client, scoped, papel):
        cid, _ = _seed(scoped)
        _papel(client, papel)
        r = _gerado(client, cid)
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert resp.status_code == 403 and _erro(resp)["code"] == "sem_permissao_reabrir"
        assert client.get(URL.format(cid=cid), headers=_auth()).json()["items"][0]["status"] == "gerado"

    def test_a_supervisor_of_another_org_is_not_one_here(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "member")
        scoped.set_table_data(
            "usuario_papeis", [{"org_id": str(uuid4()), "user_id": TEST_USER_ID, "papel": "supervisor"}]
        )
        r = _gerado(client, cid)
        assert client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth()).status_code == 403

    def test_409_not_generated(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _rascunho(client, cid)
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_nao_gerado"

    def test_409_with_results_and_how_many(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)
        for v in r["visitas"]:
            client.patch(_visita_url(cid, r, v), json={"status": "realizada"}, headers=_auth())
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_com_resultados"
        assert _erro(resp)["details"] == {"quantidade": 2}

    def test_an_in_app_notice_goes_to_whoever_generated_it_when_that_is_somebody_else(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)
        scoped.table("roteiros").update({"gerado_por": OUTRO_USUARIO}).eq("id", r["id"]).execute()
        client.mock_supabase.set_table_data("notifications", [])
        assert client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth()).status_code == 200
        avisos = client.mock_supabase.table("notifications").select("*").execute().data
        assert [(a["user_id"], a["metadata"]["tipo"], a["org_id"]) for a in avisos] == [
            (OUTRO_USUARIO, "roteiro_reaberto", ORG_ID)]
        assert avisos[0]["type"] == "system"

    def test_no_notice_when_the_one_who_generated_it_reopens_it(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)  # gerado_por == the caller
        client.mock_supabase.set_table_data("notifications", [])
        client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert client.mock_supabase.table("notifications").select("*").execute().data == []


# ── R10 ─────────────────────────────────────────────────────────────────────

class TestR10Pdf:
    def test_a_draft_is_409_with_the_contract_message(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = client.get(f"{URL.format(cid=cid)}/{r['id']}/pdf", headers=_auth())
        assert resp.status_code == 409
        assert _erro(resp)["code"] == "roteiro_rascunho"
        assert _erro(resp)["message"] == "Este roteiro ainda é um rascunho. Gere o roteiro para baixar o PDF."

    def test_a_gerado_roteiro_is_a_pdf(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        resp = client.get(f"{URL.format(cid=cid)}/{r['id']}/pdf", headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf" and resp.content.startswith(b"%PDF")

    def test_a_reopened_roteiro_is_a_draft_again_for_the_pdf(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)
        client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert client.get(f"{URL.format(cid=cid)}/{r['id']}/pdf", headers=_auth()).status_code == 409

    def test_the_renderer_refuses_a_draft_too(self):
        from app.modules.card_hub import roteiro_pdf_service
        from app.modules.card_hub.roteiro_erros import RoteiroConflito

        with pytest.raises(RoteiroConflito) as exc:
            roteiro_pdf_service.gerar({"status": "rascunho", "visitas": [{"ordem": 0}]})
        assert exc.value.code == "roteiro_rascunho"


# ── R11 ─────────────────────────────────────────────────────────────────────

class TestR11VisitaPatch:
    def test_an_observation_is_allowed_on_a_draft(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = client.patch(_visita_url(cid, r, r["visitas"][0]), json={"observacao": "levar chave"}, headers=_auth())
        assert resp.status_code == 200 and resp.json()["id"] == r["id"]  # R11 answers with the full Roteiro
        assert _v(resp.json(), r["visitas"][0])["observacao"] == "levar chave"

    def test_the_visitas_own_time_is_editable_in_both_statuses(self, client, scoped):
        cid, _ = _seed(scoped)
        for r in (_rascunho(client, cid, ("ONE9001",)), _gerado(client, cid, ("ONE9002",))):
            url = _visita_url(cid, r, r["visitas"][0])
            out = client.patch(url, json={"horario": "10:15"}, headers=_auth())
            assert out.status_code == 200 and _v(out.json(), r["visitas"][0])["horario"] == "10:15"
            out = client.patch(url, json={"horario": None}, headers=_auth())
            assert _v(out.json(), r["visitas"][0])["horario"] is None
        assert client.patch(url, json={"horario": "25:99"}, headers=_auth()).status_code == 422

    def test_409_an_outcome_on_a_draft_but_pendente_is_fine(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        url = _visita_url(cid, r, r["visitas"][0])
        resp = client.patch(url, json={"status": "realizada"}, headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_rascunho"
        assert client.patch(url, json={"status": "pendente"}, headers=_auth()).status_code == 200

    def test_cancelada_needs_who_and_why(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        url = _visita_url(cid, r, r["visitas"][0])
        for corpo in ({"status": "cancelada"}, {"status": "cancelada", "cancelada_por": "cliente"},
                      {"status": "cancelada", "cancelada_motivo": "outro"}):
            resp = client.patch(url, json=corpo, headers=_auth())
            assert resp.status_code == 422 and _erro(resp)["code"] == "cancelada_incompleta", corpo
        ok = client.patch(
            url, json={"status": "cancelada", "cancelada_por": "proprietario", "cancelada_motivo": "imovel_indisponivel"},
            headers=_auth())
        assert ok.status_code == 200
        v = _v(ok.json(), r["visitas"][0])
        assert (v["cancelada_por"], v["cancelada_motivo"]) == ("proprietario", "imovel_indisponivel")

    def test_422_reagendada_is_not_set_here(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        resp = client.patch(_visita_url(cid, r, r["visitas"][0]), json={"status": "reagendada"}, headers=_auth())
        assert resp.status_code == 422 and _erro(resp)["code"] == "reagendada_use_reagendar"

    def test_the_vocabularies_are_closed(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        url = _visita_url(cid, r, r["visitas"][0])
        for corpo in ({"status": "nao_realizada"}, {"cancelada_por": "vizinho"}, {"cancelada_motivo": "preguica"},
                      {"bogus": 1}):
            assert client.patch(url, json=corpo, headers=_auth()).status_code == 422, corpo

    def test_an_outcome_stamps_who_and_when_and_pendente_clears_the_stamps(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        url = _visita_url(cid, r, r["visitas"][0])
        feita = _v(client.patch(url, json={"status": "realizada"}, headers=_auth()).json(), r["visitas"][0])
        assert feita["resultado_em"] and feita["resultado_por"] == str(TEST_USER_ID) and feita["realizada_em"]
        volta = _v(client.patch(url, json={"status": "pendente"}, headers=_auth()).json(), r["visitas"][0])
        assert (volta["resultado_em"], volta["resultado_por"], volta["realizada_em"]) == (None, None, None)

    def test_after_any_outcome_the_roteiro_cannot_be_reopened(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)
        url = _visita_url(cid, r, r["visitas"][0])
        client.patch(url, json={"status": "nao_compareceu"}, headers=_auth())
        resp = client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_com_resultados"
        client.patch(url, json={"status": "pendente"}, headers=_auth())
        assert client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth()).status_code == 200

    def test_a_legacy_cancelada_must_be_completed_by_the_edit_that_touches_it(self, client, scoped):
        """The NOT VALID CHECK stands for legacy rows but checks every updated one — so the API says so, as a 422,
        instead of letting the database answer with a 500."""
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        vid = r["visitas"][0]["id"]
        scoped.table("visitas").update({"status": "cancelada", "cancelada_motivo": "outro"}).eq("id", vid).execute()
        url = _visita_url(cid, r, r["visitas"][0])
        resp = client.patch(url, json={"observacao": "x"}, headers=_auth())
        assert resp.status_code == 422 and _erro(resp)["code"] == "cancelada_incompleta"
        assert client.patch(url, json={"observacao": "x", "cancelada_por": "cliente"}, headers=_auth()).status_code == 200


# ── R12 ─────────────────────────────────────────────────────────────────────

class TestR12Reagendar:
    def test_creates_a_new_draft_with_that_imovel_and_points_the_visita_at_it(self, client, scoped):
        cid, aid = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001", "ONE9002"))
        v = r["visitas"][1]
        resp = client.post(
            _visita_url(cid, r, v, "/reagendar"), json={"data_visita": "2026-12-05", "hora_visita": "14:00"},
            headers=_auth())
        assert resp.status_code == 201, resp.text
        visita, novo = resp.json()["visita"], resp.json()["novo_roteiro"]
        assert visita["status"] == "reagendada" and visita["resultado_em"]
        assert novo["status"] == "rascunho" and novo["atendimento_id"] == aid
        assert [x["codigo"] for x in novo["visitas"]] == ["ONE9002"]
        assert (novo["data_visita"], novo["hora_visita"]) == ("2026-12-05", "14:00")
        assert visita["reagendada_para_visita_id"] == novo["visitas"][0]["id"]
        assert novo["criado_por"] == str(TEST_USER_ID)

    def test_reagendada_is_neutral_in_the_count(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001", "ONE9002"))
        client.post(_visita_url(cid, r, r["visitas"][0], "/reagendar"), json={}, headers=_auth())
        antigo = next(x for x in client.get(URL.format(cid=cid), headers=_auth()).json()["items"] if x["id"] == r["id"])
        assert antigo["contagem"]["reagendadas"] == 1
        assert (antigo["contagem"]["consolidadas"], antigo["contagem"]["perdidas"], antigo["contagem"]["neutras"]) == (0, 0, 2)

    def test_409_on_a_draft_roteiro(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = client.post(_visita_url(cid, r, r["visitas"][0], "/reagendar"), json={}, headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_rascunho"

    def test_409_when_the_visita_already_has_an_outcome(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        url = _visita_url(cid, r, r["visitas"][0])
        client.patch(url, json={"status": "realizada"}, headers=_auth())
        resp = client.post(url + "/reagendar", json={}, headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "visita_ja_tem_resultado"
        assert len(client.get(URL.format(cid=cid), headers=_auth()).json()["items"]) == 1  # no orphan draft

    def test_422_unknown_field(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        assert client.post(
            _visita_url(cid, r, r["visitas"][0], "/reagendar"), json={"bogus": 1}, headers=_auth()
        ).status_code == 422


# ── R13 ─────────────────────────────────────────────────────────────────────

class TestR13Proposta:
    def test_409_on_a_draft_and_fine_on_a_gerado(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        url = _visita_url(cid, r, r["visitas"][0], "/proposta")
        resp = client.patch(url, json={"proposta": True}, headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_rascunho"
        _gerar(client, cid, r["id"])
        assert client.patch(url, json={"proposta": True}, headers=_auth()).status_code == 200


# ── R14 ─────────────────────────────────────────────────────────────────────

class TestR14Feedback:
    def test_409_on_a_draft(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        resp = client.post(
            f"{URL.format(cid=cid)}/{r['id']}/feedback",
            json={"aconteceu": True, "visitas": [{"visita_id": v["id"], "resultado": "realizada"} for v in r["visitas"]]},
            headers=_auth())
        assert resp.status_code == 409 and _erro(resp)["code"] == "roteiro_rascunho"

    def test_the_new_body_with_a_resultado_per_visita(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001", "ONE9002", "ONE9003"))
        resp = client.post(
            f"{URL.format(cid=cid)}/{r['id']}/feedback",
            json={"aconteceu": True, "visitas": [
                {"visita_id": r["visitas"][0]["id"], "resultado": "realizada"},
                {"visita_id": r["visitas"][1]["id"], "resultado": "cancelada", "cancelada_por": "corretor",
                 "cancelada_motivo": "outro"},
                {"visita_id": r["visitas"][2]["id"], "resultado": "nao_compareceu"}]},
            headers=_auth())
        assert resp.status_code == 200, resp.text
        assert [v["status"] for v in resp.json()["visitas"]] == ["realizada", "cancelada", "nao_compareceu"]
        assert resp.json()["feedback_status"] == "respondido"

    def test_the_legacy_body_is_still_accepted(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001", "ONE9002"))
        resp = client.post(
            f"{URL.format(cid=cid)}/{r['id']}/feedback",
            json={"aconteceu": True, "visitas": [
                {"visita_id": r["visitas"][0]["id"], "realizada": True},
                {"visita_id": r["visitas"][1]["id"], "realizada": False, "motivo": "cliente_nao_compareceu"}]},
            headers=_auth())
        assert resp.status_code == 200, resp.text
        assert [v["status"] for v in resp.json()["visitas"]] == ["realizada", "nao_compareceu"]

    def test_a_legacy_cancelada_without_who_is_422(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001",))
        resp = client.post(
            f"{URL.format(cid=cid)}/{r['id']}/feedback",
            json={"aconteceu": True, "visitas": [
                {"visita_id": r["visitas"][0]["id"], "realizada": False, "motivo": "cliente_desistiu"}]},
            headers=_auth())
        assert resp.status_code == 422 and _erro(resp)["code"] == "cancelada_incompleta"

    def test_422_an_entry_with_no_answer_and_unknown_fields(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001",))
        url = f"{URL.format(cid=cid)}/{r['id']}/feedback"
        vid = r["visitas"][0]["id"]
        assert client.post(url, json={"aconteceu": True, "visitas": [{"visita_id": vid}]}, headers=_auth()).status_code == 422
        assert client.post(
            url, json={"aconteceu": True, "visitas": [{"visita_id": vid, "resultado": "talvez"}]}, headers=_auth()
        ).status_code == 422
        assert client.post(url, json={"aconteceu": True, "visitas": [], "bogus": 1}, headers=_auth()).status_code == 422


# ── amendment v1.1 §3: who generated / reopened it, by name ────────────────

class TestNomesDeQuemGerouEReabriu:
    def test_the_names_are_joined_server_side(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        client.mock_supabase.set_table_data("noctus_users", [
            {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Cindy Kumagai"},
            {"id": OUTRO_USUARIO, "org_id": ORG_ID, "org_role": "member", "nome": "Bruno Souza"},
        ])
        r = _gerado(client, cid)
        assert (r["gerado_por_nome"], r["reaberto_por_nome"]) == ("Cindy Kumagai", None)
        scoped.table("roteiros").update({"gerado_por": OUTRO_USUARIO}).eq("id", r["id"]).execute()
        out = client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth()).json()
        assert (out["gerado_por_nome"], out["reaberto_por_nome"]) == ("Bruno Souza", "Cindy Kumagai")

    def test_a_draft_that_was_never_generated_has_null_names(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        assert (r["gerado_por_nome"], r["reaberto_por_nome"]) == (None, None)


# ── permissoes per role (CONTRACT §2) ───────────────────────────────────────

class TestPermissoes:
    def test_a_draft_says_why_it_cannot_be_generated(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        vazio = client.post(URL.format(cid=cid), json={"data_visita": "2026-10-10"}, headers=_auth()).json()
        assert vazio["permissoes"] == {
            "editar_imoveis": True, "gerar": False, "motivo_gerar": "Adicione ao menos um imóvel.",
            "baixar_pdf": False, "reabrir": False, "motivo_reabrir": None,
        }
        sem_data = client.post(URL.format(cid=cid), json={"imoveis": ["ONE9001"]}, headers=_auth()).json()
        assert sem_data["permissoes"]["gerar"] is False
        assert sem_data["permissoes"]["motivo_gerar"] == "Informe a data da visita."
        pronto = _rascunho(client, cid)
        assert pronto["permissoes"]["gerar"] is True and pronto["permissoes"]["motivo_gerar"] is None

    @pytest.mark.parametrize("papel,supervisor,pode", [
        ("owner", False, True), ("admin", False, True), ("member", True, True),
        ("member", False, False), ("viewer", False, False),
    ])
    def test_a_gerado_roteiro_reopen_permission_per_role(self, client, scoped, papel, supervisor, pode):
        cid, _ = _seed(scoped)
        _papel(client, papel)
        if supervisor:
            _supervisor(scoped)
        r = _gerado(client, cid)
        p = r["permissoes"]
        assert (p["editar_imoveis"], p["baixar_pdf"], p["gerar"]) == (False, True, False)
        assert p["reabrir"] is pode
        if pode:
            assert p["motivo_reabrir"] is None
        else:
            assert p["motivo_reabrir"] == "Só supervisores, administradores e o proprietário da conta podem reabrir."

    def test_results_block_the_reopen_and_say_how_many(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)
        for v in r["visitas"]:
            client.patch(_visita_url(cid, r, v), json={"status": "realizada"}, headers=_auth())
        p = client.get(URL.format(cid=cid), headers=_auth()).json()["items"][0]["permissoes"]
        assert p["reabrir"] is False and p["motivo_reabrir"] == "Já tem 2 resultados registrados."

    def test_the_role_comes_from_the_trusted_row_not_from_user_metadata(self, client, scoped):
        """`user_metadata.org_role` is user-writable (auth.updateUser): a member who writes "owner" there is still a
        member."""
        cid, _ = _seed(scoped)
        _papel(client, "member")
        client.mock_supabase.auth.get_user.return_value.user.user_metadata["org_role"] = "owner"
        r = _gerado(client, cid)
        assert r["permissoes"]["reabrir"] is False


# ── the contagem keys (CONTRACT §2) ─────────────────────────────────────────

class TestContagem:
    def test_the_contract_keys_and_the_one_derivation(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001", "ONE9002", "ONE9003"))
        v = r["visitas"]
        client.patch(_visita_url(cid, r, v[0]), json={"status": "realizada"}, headers=_auth())
        client.patch(_visita_url(cid, r, v[1]), json={"status": "nao_compareceu"}, headers=_auth())
        c = client.get(URL.format(cid=cid), headers=_auth()).json()["items"][0]["contagem"]
        assert c == {"total": 3, "pendentes": 1, "realizadas": 1, "canceladas": 0, "nao_compareceu": 1,
                     "reagendadas": 0, "consolidadas": 1, "perdidas": 1, "neutras": 1}


# ── v1.2: the event ledger's inputs ─────────────────────────────────────────

class TestEventosDeCadaRota:
    """`roteiro_eventos` is written by TRIGGERS on `roteiros` / `visitas` (migration 338), in the same transaction as the
    change — so the event cannot be skipped and a failed event write fails the request. What the API owes the triggers is
    the ACTOR on every write (`criado_por`, `gerado_por`, `reaberto_por`, `resultado_por`, else `atualizado_por`). The
    exact event each of those statements produces is asserted on a real Postgres in `test_migration_338_*`
    ("events: ..." scenarios); here, for every write route, the caller is on the rows the trigger reads."""

    ME = str(TEST_USER_ID)

    def _roteiro(self, scoped, rid):
        return _linha(scoped, "roteiros", id=rid)[0]

    def _visita(self, scoped, vid):
        return _linha(scoped, "visitas", id=vid)[0]

    def test_r2_criar(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        assert self._roteiro(scoped, r["id"])["criado_por"] == self.ME
        assert {self._visita(scoped, v["id"])["atualizado_por"] for v in r["visitas"]} == {self.ME}

    def test_r3_patch_r4_delete(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid)
        client.patch(f"{URL.format(cid=cid)}/{r['id']}", json={"data_visita": "2026-12-01"}, headers=_auth())
        assert self._roteiro(scoped, r["id"])["atualizado_por"] == self.ME
        scoped.table("roteiros").update({"atualizado_por": None}).eq("id", r["id"]).execute()
        client.delete(f"{URL.format(cid=cid)}/{r['id']}", headers=_auth())
        roteiro = self._roteiro(scoped, r["id"])
        assert roteiro["deleted_at"] and roteiro["atualizado_por"] == self.ME

    def test_r5_r6_r7_the_imoveis_of_a_draft(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _rascunho(client, cid, ("ONE9001", "ONE9002"))
        for v in r["visitas"]:
            scoped.table("visitas").update({"atualizado_por": None}).eq("id", v["id"]).execute()
        client.put(f"{URL.format(cid=cid)}/{r['id']}/ordem",
                   json={"visita_ids": [v["id"] for v in reversed(r["visitas"])]}, headers=_auth())
        assert {self._visita(scoped, v["id"])["atualizado_por"] for v in r["visitas"]} == {self.ME}
        nova = client.post(f"{URL.format(cid=cid)}/{r['id']}/visitas", json={"codigo": "ONE9003"}, headers=_auth()).json()
        adicionada = next(v for v in nova["visitas"] if v["codigo"] == "ONE9003")
        assert self._visita(scoped, adicionada["id"])["atualizado_por"] == self.ME
        scoped.table("visitas").update({"atualizado_por": None}).eq("id", adicionada["id"]).execute()
        client.delete(_visita_url(cid, r, adicionada), headers=_auth())
        removida = self._visita(scoped, adicionada["id"])
        assert removida["deleted_at"] and removida["atualizado_por"] == self.ME

    def test_r8_gerar_hands_the_actor_to_the_transaction(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        assert [p["p_user_id"] for n, p in scoped.rpc_calls if n == "roteiro_gerar"] == [self.ME]
        assert self._roteiro(scoped, r["id"])["gerado_por"] == self.ME

    def test_r9_reabrir(self, client, scoped):
        cid, _ = _seed(scoped)
        _papel(client, "owner")
        r = _gerado(client, cid)
        client.post(f"{URL.format(cid=cid)}/{r['id']}/reabrir", headers=_auth())
        roteiro = self._roteiro(scoped, r["id"])
        assert (roteiro["reaberto_por"], roteiro["atualizado_por"]) == (self.ME, self.ME)

    def test_r11_resultado_and_horario(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        v = r["visitas"][0]
        client.patch(_visita_url(cid, r, v), json={"status": "realizada", "horario": "10:00"}, headers=_auth())
        row = self._visita(scoped, v["id"])
        assert (row["resultado_por"], row["atualizado_por"], row["horario"]) == (self.ME, self.ME, "10:00:00")

    def test_r12_reagendar(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid)
        out = client.post(_visita_url(cid, r, r["visitas"][0], "/reagendar"), json={}, headers=_auth()).json()
        antiga = self._visita(scoped, r["visitas"][0]["id"])
        assert (antiga["status"], antiga["resultado_por"], antiga["atualizado_por"]) == ("reagendada", self.ME, self.ME)
        assert self._roteiro(scoped, out["novo_roteiro"]["id"])["criado_por"] == self.ME
        assert self._visita(scoped, out["novo_roteiro"]["visitas"][0]["id"])["atualizado_por"] == self.ME

    def test_r14_feedback(self, client, scoped):
        cid, _ = _seed(scoped)
        r = _gerado(client, cid, ("ONE9001",))
        client.post(f"{URL.format(cid=cid)}/{r['id']}/feedback", json={"aconteceu": True, "visitas": [
            {"visita_id": r["visitas"][0]["id"], "resultado": "realizada"}]}, headers=_auth())
        row = self._visita(scoped, r["visitas"][0]["id"])
        assert (row["resultado_por"], row["atualizado_por"]) == (self.ME, self.ME)
        assert self._roteiro(scoped, r["id"])["atualizado_por"] == self.ME


# ── the boundary ────────────────────────────────────────────────────────────

_ROTAS = [
    ("get", "", None), ("post", "", {}), ("patch", "/{r}", {"titulo": "x"}), ("delete", "/{r}", None),
    ("put", "/{r}/ordem", {"visita_ids": [str(uuid4())]}), ("post", "/{r}/visitas", {"codigo": "ONE9001"}),
    ("delete", "/{r}/visitas/{v}", None), ("post", "/{r}/gerar", None), ("post", "/{r}/reabrir", None),
    ("get", "/{r}/pdf", None), ("patch", "/{r}/visitas/{v}", {"observacao": "x"}),
    ("post", "/{r}/visitas/{v}/reagendar", {}), ("patch", "/{r}/visitas/{v}/proposta", {"proposta": True}),
    ("post", "/{r}/feedback", {"aconteceu": False, "visitas": []}),
]


class TestAuthBoundary:
    @pytest.mark.parametrize("metodo,sufixo,corpo", _ROTAS, ids=[f"{m} {s or '/'}" for m, s, _ in _ROTAS])
    def test_no_token_is_exactly_401(self, anon_client, metodo, sufixo, corpo):
        url = URL.format(cid=uuid4()) + sufixo.format(r=uuid4(), v=uuid4())
        kwargs = {"json": corpo} if corpo is not None else {}
        assert getattr(anon_client, metodo)(url, **kwargs).status_code == 401


class TestAccessTier:
    """Every route of the roteiro lifecycle is declared `org` (the keepers `check_access_tier_routes/_tables` read
    the same marker and the table comment)."""

    def test_every_roteiro_route_carries_an_org_marker(self):
        from app.modules.card_hub import roteiros_router
        from app.modules.card_hub.router import router

        rotas = [
            r for r in list(router.routes) + list(roteiros_router.router.routes) + list(roteiros_router.pendentes_router.routes)
            if "/roteiros" in r.path
        ]
        assert len(rotas) >= 15
        sem = [f"{sorted(r.methods)} {r.path}" for r in rotas if getattr(r.endpoint, "__access_tier__", None) != "org"]
        assert sem == []

    def test_the_new_table_declares_its_tier(self):
        from pathlib import Path

        from noctusai_lib.testing.migrations import migration_sql

        sql = migration_sql(Path(__file__).resolve().parents[3], "roteiro_ciclo_de_vida")
        assert "COMMENT ON TABLE social_wiring.usuario_papeis IS 'tier:org'" in sql
        assert "REVOKE ALL ON TABLE social_wiring.usuario_papeis FROM PUBLIC, anon, authenticated" in sql
        assert "COMMENT ON TABLE social_wiring.roteiro_eventos IS 'tier:org'" in sql
        assert "GRANT SELECT, INSERT ON TABLE social_wiring.roteiro_eventos TO service_role" in sql

    def test_the_routers_use_the_seed_marker(self):
        from noctusai_lib.api.access_tiers import access_tier as marcador
        from app.modules.card_hub import router as mod

        assert mod.access_tier is marcador and "access_tier" in inspect.getsource(mod)
