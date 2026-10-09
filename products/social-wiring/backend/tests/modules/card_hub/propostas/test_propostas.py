"""Propostas CRUD (CONTRACT §4) — every route, every 4xx code."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_agendamentos import atendimento_row
from tests.modules.card_hub.test_roteiros import _criar, imovel_row, registry_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, *, valor_venda=850000, imobiliarias=1, pct_default=None, pct_negociacao=None):
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("atendimentos", [atendimento_row(aid, cid)])
    scoped.set_table_data("imovel_registry", [registry_row("ONE9001"), registry_row("ONE9002")])
    scoped.set_table_data(
        "imoveis",
        [imovel_row("ONE9001", valor_venda=valor_venda), imovel_row("ONE9002")],
    )
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("roteiros", [])
    scoped.set_table_data("visitas", [])
    scoped.set_table_data("atendimento_propostas", [])
    scoped.set_table_data(
        "atendimento_negociacao",
        [{"org_id": ORG_ID, "atendimento_id": aid, "pct_comissao": pct_negociacao}]
        if pct_negociacao is not None
        else [],
    )
    scoped.set_table_data(
        "negociacao_defaults",
        [{"org_id": ORG_ID, "pct_comissao": pct_default}] if pct_default is not None else [],
    )
    scoped.set_table_data(
        "org_imobiliarias",
        [
            {"id": str(uuid4()), "org_id": ORG_ID, "razao_social": f"Imob {i}",
             "created_at": f"2026-01-0{i + 1}T00:00:00+00:00", "excluida_em": None}
            for i in range(imobiliarias)
        ],
    )
    scoped.set_table_data("org_testemunhas", [])
    return cid, aid


def _visita_realizada(client, cid) -> tuple[str, str]:
    roteiro = _criar(client, cid, ["ONE9001"])
    vid = roteiro["visitas"][0]["id"]
    resp = client.patch(
        f"/api/clientes/{cid}/roteiros/{roteiro['id']}/visitas/{vid}",
        json={"status": "realizada"}, headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return roteiro["id"], vid


def _nova(client, cid, **body) -> dict:
    resp = client.post(
        f"/api/clientes/{cid}/propostas", json=body or {"imovel_codigo": "ONE9001"}, headers=_auth()
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _url(cid, pid="", suffix="") -> str:
    return f"/api/clientes/{cid}/propostas" + (f"/{pid}" if pid else "") + suffix


def _err(resp) -> dict:
    return resp.json()["error"]


class TestCriar:
    def test_prefill_from_visita(self, client, scoped):
        cid, _ = _seed(scoped, pct_default=6)
        _, vid = _visita_realizada(client, cid)
        p = _nova(client, cid, visita_id=vid)
        assert p["status"] == "rascunho"
        assert p["imovel_codigo"] == "ONE9001"
        assert float(p["valor_proposto"]) == 850000
        assert float(p["pct_comissao"]) == 6
        assert p["imobiliaria"]["razao_social"] == "Imob 0"
        assert p["visita"]["id"] == vid
        assert p["imovel"]["titulo"] == "Apartamento ONE9001"
        assert p["imovel"]["endereco"].startswith("Rua das Palmeiras 320")
        assert p["parcelas"] == [] and p["testemunhas"] == []

    def test_visita_stamps_proposta_em(self, client, scoped):
        cid, _ = _seed(scoped)
        _, vid = _visita_realizada(client, cid)
        _nova(client, cid, visita_id=vid)
        visita = next(v for v in scoped.table("visitas").select("*").execute().data if v["id"] == vid)
        assert visita["proposta_em"] is not None

    def test_negociacao_pct_wins_over_org_default(self, client, scoped):
        cid, _ = _seed(scoped, pct_default=6, pct_negociacao=5)
        assert float(_nova(client, cid)["pct_comissao"]) == 5

    def test_no_pct_anywhere_is_null_and_reported(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        assert p["pct_comissao"] is None
        assert "Percentual de comissão" in p["completude"]

    def test_unknown_price_is_null(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid, imovel_codigo="ONE9002")
        assert p["valor_proposto"] is None and p["saldo_nao_alocado"] is None

    def test_imobiliaria_only_when_exactly_one_active(self, client, scoped):
        cid, _ = _seed(scoped, imobiliarias=2)
        assert _nova(client, cid)["imobiliaria"] is None

    def test_imovel_codigo_is_canonicalised(self, client, scoped):
        cid, _ = _seed(scoped)
        assert _nova(client, cid, imovel_codigo=" one9001 ")["imovel_codigo"] == "ONE9001"

    def test_visita_not_realizada_is_409(self, client, scoped):
        cid, _ = _seed(scoped)
        roteiro = _criar(client, cid, ["ONE9001"])
        resp = client.post(
            _url(cid), json={"visita_id": roteiro["visitas"][0]["id"]}, headers=_auth()
        )
        assert resp.status_code == 409
        assert _err(resp)["code"] == "visita_nao_realizada"

    def test_needs_visita_or_imovel_400(self, client, scoped):
        cid, _ = _seed(scoped)
        resp = client.post(_url(cid), json={}, headers=_auth())
        assert resp.status_code == 400

    def test_unknown_visita_404(self, client, scoped):
        cid, _ = _seed(scoped)
        resp = client.post(_url(cid), json={"visita_id": str(uuid4())}, headers=_auth())
        assert resp.status_code == 404

    def test_unregistered_imovel_404(self, client, scoped):
        cid, _ = _seed(scoped)
        resp = client.post(_url(cid), json={"imovel_codigo": "NOPE1"}, headers=_auth())
        assert resp.status_code == 404

    def test_visita_and_other_imovel_400(self, client, scoped):
        cid, _ = _seed(scoped)
        _, vid = _visita_realizada(client, cid)
        resp = client.post(
            _url(cid), json={"visita_id": vid, "imovel_codigo": "ONE9002"}, headers=_auth()
        )
        assert resp.status_code == 400

    def test_unknown_field_is_rejected(self, client, scoped):
        cid, _ = _seed(scoped)
        resp = client.post(_url(cid), json={"imovel_codigo": "ONE9001", "x": 1}, headers=_auth())
        assert resp.status_code == 422

    def test_funil_failure_never_fails_the_create(self, client, scoped):
        # `funil_eventos` may be absent or may refuse; the create succeeds either way.
        cid, _ = _seed(scoped)
        assert _nova(client, cid)["status"] == "rascunho"


class TestListarObter:
    def test_list_is_bare_and_newest_first(self, client, scoped):
        cid, _ = _seed(scoped)
        a = _nova(client, cid)
        b = _nova(client, cid, imovel_codigo="ONE9002")
        scoped.table("atendimento_propostas").update(
            {"created_at": "2026-01-01T00:00:00+00:00"}
        ).eq("id", a["id"]).execute()
        body = client.get(_url(cid), headers=_auth()).json()
        assert isinstance(body, list)  # bare JSON, no envelope
        assert [p["id"] for p in body] == [b["id"], a["id"]]
        assert body[0]["imovel"]["codigo"] == "ONE9002"

    def test_get_one_and_404(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        assert client.get(_url(cid, p["id"]), headers=_auth()).json()["id"] == p["id"]
        assert client.get(_url(cid, str(uuid4())), headers=_auth()).status_code == 404

    def test_other_org_proposta_is_404(self, client, scoped):
        cid, aid = _seed(scoped)
        pid = str(uuid4())
        scoped.set_table_data("atendimento_propostas", [{
            "id": pid, "org_id": str(uuid4()), "atendimento_id": aid, "cliente_id": cid,
            "imovel_codigo": "ONE9001", "status": "rascunho",
        }])
        assert client.get(_url(cid, pid), headers=_auth()).status_code == 404


PARCELAS = [
    {"tipo": "sinal", "valor": "100000", "favorecido_ref": "fav:0"},
    {"tipo": "saldo", "valor": "500000", "favorecido_ref": "fav:0"},
]
FAVORECIDOS = [{"nome": "Vendedor Silva"}]


class TestPatch:
    def test_patch_snapshots_and_saldo(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        resp = client.patch(
            _url(cid, p["id"]),
            json={"parcelas": PARCELAS, "favorecidos": FAVORECIDOS,
                  "termos": {"posse_marco": "assinatura", "posse_marco_parcela_ref": "parcela:1"},
                  "financiamento": True, "validade_ate": "2026-12-31"},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert float(out["saldo_nao_alocado"]) == 250000
        assert out["financiamento"] is True and out["validade_ate"] == "2026-12-31"
        assert out["termos"]["posse_marco_parcela_ref"] == "parcela:1"
        assert "Parcelas não cobrem o valor" in " ".join(out["completude"])
        assert client.get(_url(cid, p["id"]), headers=_auth()).json()["parcelas"][0]["tipo"] == "sinal"

    def test_absent_means_leave_alone_and_null_clears(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        client.patch(_url(cid, p["id"]), json={"observacoes": "oi"}, headers=_auth())
        out = client.patch(_url(cid, p["id"]), json={"fgts": True}, headers=_auth()).json()
        assert out["observacoes"] == "oi" and out["valor_proposto"] is not None
        out = client.patch(_url(cid, p["id"]), json={"valor_proposto": None}, headers=_auth()).json()
        assert out["valor_proposto"] is None

    @pytest.mark.parametrize(
        "body, campo",
        [
            ({"parcelas": [{"tipo": "sinal", "valor": "1", "favorecido_ref": "fav:3"}],
              "favorecidos": FAVORECIDOS}, "parcelas.0.favorecido_ref"),
            ({"parcelas": [{"tipo": "sinal", "valor": "1", "favorecido_ref": "xx"}]},
             "parcelas.0.favorecido_ref"),
            ({"intermediarios": [{"nome": "Corretor", "favorecido_ref": "fav:0"}]},
             "intermediarios.0.favorecido_ref"),
            ({"termos": {"posse_marco_parcela_ref": "parcela:0"}},
             "termos.posse_marco_parcela_ref"),
            ({"parcelas": [{"tipo": "direta", "valor": "1",
                            "favorecidos_divisao": [{"favorecido_ref": "fav:9", "valor": "1"}]}],
              "favorecidos": FAVORECIDOS},
             "parcelas.0.favorecidos_divisao.0.favorecido_ref"),
        ],
    )
    def test_bad_ref_is_400_with_field_path(self, client, scoped, body, campo):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        resp = client.patch(_url(cid, p["id"]), json=body, headers=_auth())
        assert resp.status_code == 400, resp.text
        erro = _err(resp)
        assert erro["code"] == "snapshot_invalido"
        assert campo in [c["path"] for c in erro["details"]["campos"]]
        assert all(c["mensagem"] for c in erro["details"]["campos"])

    def test_ref_validated_against_merged_state(self, client, scoped):
        """Shrinking the favorecidos while parcelas still point at them is a 400."""
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        client.patch(
            _url(cid, p["id"]), json={"parcelas": PARCELAS, "favorecidos": FAVORECIDOS},
            headers=_auth(),
        )
        resp = client.patch(_url(cid, p["id"]), json={"favorecidos": []}, headers=_auth())
        assert resp.status_code == 400
        assert _err(resp)["code"] == "snapshot_invalido"

    def test_real_favorecido_id_is_not_accepted_in_a_snapshot(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        resp = client.patch(
            _url(cid, p["id"]),
            json={"parcelas": [{"tipo": "sinal", "valor": "1", "favorecido_id": str(uuid4())}]},
            headers=_auth(),
        )
        assert resp.status_code == 400
        assert [c["path"] for c in _err(resp)["details"]["campos"]] == ["parcelas.0.favorecido_id"]

    def test_invalid_snapshot_shape_is_400_with_every_path(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        resp = client.patch(
            _url(cid, p["id"]),
            json={"parcelas": [{"tipo": "nope", "valor": "1"}, {"tipo": "sinal"}],
                  "favorecidos": [{"nome": ""}], "termos": {"posse_marco": "x"}},
            headers=_auth(),
        )
        assert resp.status_code == 400
        erro = _err(resp)
        assert erro["code"] == "snapshot_invalido"
        assert erro["message"].startswith("Os dados da proposta têm campos inválidos")
        assert {c["path"] for c in erro["details"]["campos"]} == {
            "parcelas.0.tipo", "parcelas.1.valor", "favorecidos.0.nome", "termos.posse_marco",
        }
        # nothing stored
        assert client.get(_url(cid, p["id"]), headers=_auth()).json()["parcelas"] == []

    def test_malformed_body_type_is_still_422(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        assert client.patch(_url(cid, p["id"]), json={"parcelas": "x"}, headers=_auth()).status_code == 422
        assert client.patch(_url(cid, p["id"]), json=[1], headers=_auth()).status_code == 422

    def test_nonpositive_valor_422(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        assert client.patch(
            _url(cid, p["id"]), json={"valor_proposto": 0}, headers=_auth()
        ).status_code == 422

    def test_unknown_imobiliaria_and_testemunha_404(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        assert client.patch(
            _url(cid, p["id"]), json={"imobiliaria_id": str(uuid4())}, headers=_auth()
        ).status_code == 404
        assert client.patch(
            _url(cid, p["id"]), json={"testemunha_ids": [str(uuid4())]}, headers=_auth()
        ).status_code == 404

    def test_testemunhas_resolved(self, client, scoped):
        cid, _ = _seed(scoped)
        tid = str(uuid4())
        scoped.set_table_data("org_testemunhas", [
            {"id": tid, "org_id": ORG_ID, "nome": "Tereza", "excluida_em": None}
        ])
        p = _nova(client, cid)
        out = client.patch(_url(cid, p["id"]), json={"testemunha_ids": [tid, tid]}, headers=_auth()).json()
        assert out["testemunhas"] == [{"id": tid, "nome": "Tereza"}]

    def test_removed_imobiliaria_cannot_be_newly_chosen(self, client, scoped):
        cid, _ = _seed(scoped)
        iid = str(uuid4())
        scoped.set_table_data("org_imobiliarias", [
            {"id": iid, "org_id": ORG_ID, "razao_social": "Velha", "created_at": "2026-01-01T00:00:00+00:00",
             "excluida_em": "2026-02-01T00:00:00+00:00"},
        ])
        p = _nova(client, cid)
        resp = client.patch(_url(cid, p["id"]), json={"imobiliaria_id": iid}, headers=_auth())
        assert resp.status_code == 400

    def test_change_imovel(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        out = client.patch(_url(cid, p["id"]), json={"imovel_codigo": "one9002"}, headers=_auth()).json()
        assert out["imovel_codigo"] == "ONE9002"
        assert client.patch(
            _url(cid, p["id"]), json={"imovel_codigo": "NOPE"}, headers=_auth()
        ).status_code == 404


class TestCicloDeVida:
    def test_enviar_then_edit_still_allowed(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        out = client.post(_url(cid, p["id"], "/enviar"), headers=_auth()).json()
        assert out["status"] == "enviada" and out["enviada_em"]
        again = client.post(_url(cid, p["id"], "/enviar"), headers=_auth())
        assert again.status_code == 200 and again.json()["enviada_em"] == out["enviada_em"]
        assert client.patch(_url(cid, p["id"]), json={"fgts": True}, headers=_auth()).status_code == 200

    def test_recusar_requires_motivo(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        for body in ({}, {"motivo": "   "}):
            resp = client.post(_url(cid, p["id"], "/recusar"), json=body, headers=_auth())
            assert resp.status_code == 400, resp.text
            assert _err(resp)["code"] == "motivo_obrigatorio"
        out = client.post(
            _url(cid, p["id"], "/recusar"), json={"motivo": "Valor alto"}, headers=_auth()
        ).json()
        assert out["status"] == "recusada" and out["motivo_recusa"] == "Valor alto"
        assert out["recusada_em"]

    @pytest.mark.parametrize("estado", ["aceita", "recusada", "cancelada"])
    def test_closed_proposta_is_409_proposta_fechada(self, client, scoped, estado):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        scoped.table("atendimento_propostas").update({"status": estado}).eq("id", p["id"]).execute()
        for resp in (
            client.patch(_url(cid, p["id"]), json={"fgts": True}, headers=_auth()),
            client.post(_url(cid, p["id"], "/enviar"), headers=_auth()),
            client.post(_url(cid, p["id"], "/recusar"), json={"motivo": "x"}, headers=_auth()),
        ):
            assert resp.status_code == 409
            assert resp.json() == {"error": {"code": "proposta_fechada", "message": (
                f"A proposta está {estado} e não pode mais ser alterada.")}}

    def test_delete_rascunho_only(self, client, scoped):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        q = _nova(client, cid)
        client.post(_url(cid, q["id"], "/enviar"), headers=_auth())
        resp = client.delete(_url(cid, q["id"]), headers=_auth())
        assert resp.status_code == 409 and _err(resp)["code"] == "proposta_nao_rascunho"
        assert client.delete(_url(cid, p["id"]), headers=_auth()).status_code == 204
        assert client.get(_url(cid, p["id"]), headers=_auth()).status_code == 404
        assert client.delete(_url(cid, p["id"]), headers=_auth()).status_code == 404


class TestAceiteSeam:
    """While `aceite.py` (another slice) is absent, the two routes are 503 —
    never a silent success."""

    @pytest.fixture(autouse=True)
    def _sem_aceite(self):
        import importlib.util

        if importlib.util.find_spec("app.modules.card_hub.propostas.aceite") is not None:
            pytest.skip("aceite.py has landed; the seam is covered by its own tests")

    @pytest.mark.parametrize("suffix", ["/aceitar", "/pos-aceite"])
    def test_503_aceite_indisponivel(self, client, scoped, suffix):
        cid, _ = _seed(scoped)
        p = _nova(client, cid)
        resp = client.post(_url(cid, p["id"], suffix), json={}, headers=_auth())
        assert resp.status_code == 503
        assert _err(resp)["code"] == "aceite_indisponivel"
        # nothing was written
        assert client.get(_url(cid, p["id"]), headers=_auth()).json()["status"] == "rascunho"
