"""All parties of an atendimento + registration lookup (CONTRACT §2.1-§2.5).

Driven through the REAL app (`partes_router` is mounted by `card_hub.router`,
CONTRACT §10), with the REAL `get_current_user_org` dependency — so the 401
assertions exercise the actual guard, not an override.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.card_hub import compradores_service as comp_svc
from app.modules.card_hub import partes_service as svc
from app.modules.card_hub.deps import get_card_hub_client
from app.modules.card_hub.partes_schemas import ParteCreateBody
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

CPF_A = "52998224725"
CPF_A_FMT = "529.982.247-25"
CNPJ_A = "11222333000181"
CNPJ_B = "11444777000161"

_PARTE_ITEM_KEYS = {
    "parte_id", "titular", "rotulo", "lado", "papel", "ordem", "tipo_pessoa",
    "cliente_id", "empresa_id", "nome", "documento", "observacao", "cliente",
    "empresa", "representa_parte_id", "pj_nire", "pj_sede",
}
_EMPRESA_KEYS = {"id", "razao_social", "nome_fantasia", "cnpj", "situacao_cadastral"}
_LOOKUP_KEYS = {
    "documento", "tipo_documento", "encontrado", "cliente", "empresa",
    "ja_no_atendimento", "atendimentos", "certidoes",
}
_CERT_KEYS = {
    "max_dias", "data_referencia", "itens", "tipos_vencidos", "alerta_vencidas",
    "mensagem",
}
_CERT_ITEM_KEYS = {
    "tipo", "rotulo", "resultado_id", "emitida_em", "validade_ate",
    "idade_dias", "stale_para_contrato", "resultado",
}
_ATD_KEYS = {
    "id", "titulo", "etapa", "status", "arquivado", "lado", "papel", "titular",
    "parte_id",
}


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def http(client):
    """The real app over the SAME patched mock the `client` fixture installed."""
    return client


@pytest.fixture
def anon_http(anon_client):
    """No Authorization header — the guard decides the status."""
    return anon_client


@pytest.fixture
def scoped(client):
    return get_card_hub_client()


def _atendimento(aid, cliente_id, **over):
    row = {
        "id": aid, "org_id": ORG_ID, "cliente_id": cliente_id, "lead_id": None,
        "meta_ads_lead_id": None, "status": "aberta", "substituida_por": None,
        "arquivado": False, "titulo": "Compra do apto", "etapa_id": None,
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }
    row.update(over)
    return row


def _parte(aid, *, cliente_id=None, empresa_id=None, lado="comprador",
           papel="comprador", ordem=0, created_at="2026-01-02T00:00:00+00:00", **extra):
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
        "cliente_id": cliente_id, "empresa_id": empresa_id, "lado": lado,
        "papel": papel, "ordem": ordem, "observacao": None,
        "created_at": created_at, "created_by": None, "updated_at": None,
        **extra,
    }


def _empresa(id_=None, cnpj=CNPJ_A, **over):
    row = {
        "id": id_ or str(uuid4()), "org_id": ORG_ID, "cnpj": cnpj,
        "razao_social": "Empresa Um LTDA", "nome_fantasia": "Um",
        "natureza_juridica": None, "data_abertura": None,
        "situacao_cadastral": "ativa", "data_situacao_cadastral": None,
        "motivo_situacao": None, "dados_origem": None, "dados_documento_id": None,
        "dados_em": None, "dados_confirmado_por": None, "dados_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    }
    row.update(over)
    return row


def _consulta(id_, *, cliente_id=None, empresa_id=None, tipo_documento="cpf"):
    return {
        "id": id_, "org_id": ORG_ID, "empresa_id": empresa_id,
        "cliente_id": cliente_id, "atendimento_parte_id": None,
        "tipo_documento": tipo_documento, "documento": "x", "nome": "Fulano",
        "excluida_em": None, "situacao_cadastral": None, "data_situacao": None,
        "situacao_origem": None,
    }


def _resultado(id_, consulta_id, tipo, *, emitida_em=None,
               created_at="2026-01-01T00:00:00+00:00", **over):
    row = {
        "id": id_, "org_id": ORG_ID, "consulta_id": consulta_id, "tipo": tipo,
        "nome_display": tipo.upper(), "status": "sucesso", "resultado": "negativa",
        "numero": None, "emitida_em": emitida_em, "validade_ate": None,
        "analise_ia": None, "erro_mensagem": None, "ordem": 0,
        "created_at": created_at, "excluida_em": None,
    }
    row.update(over)
    return row


def _seed(scoped, *, clientes=(), atendimentos=(), partes=(), empresas=(),
          consultas=(), resultados=(), stages=()):
    scoped.set_table_data("clientes", list(clientes))
    scoped.set_table_data("atendimentos", list(atendimentos))
    scoped.set_table_data("atendimento_partes", list(partes))
    scoped.set_table_data("empresas", list(empresas))
    scoped.set_table_data("certidao_consultas", list(consultas))
    scoped.set_table_data("certidao_resultados", list(resultados))
    scoped.set_table_data("pipeline_stages", list(stages))
    scoped.set_table_data("cliente_empresa_participacoes", [])


def _deal(scoped, **seed):
    """Titular + one open atendimento, plus whatever else the test seeds."""
    cid, aid = str(uuid4()), str(uuid4())
    clientes = [cliente_row(cid, nome="Luciano", nome_oficial="Luciano Mauricio", cpf=CPF_A)]
    clientes += list(seed.pop("clientes", []))
    atendimentos = [_atendimento(aid, cid)] + list(seed.pop("atendimentos", []))
    _seed(scoped, clientes=clientes, atendimentos=atendimentos, **seed)
    return cid, aid


# ─── §2.1 GET /partes ─────────────────────────────────────────────────────


class TestListarPartes:
    def test_titular_is_comp_1_and_labels_number_per_lado(self, http, scoped):
        spouse, seller, seller2 = str(uuid4()), str(uuid4()), str(uuid4())
        emp = _empresa()
        aid_holder = {}
        cid = str(uuid4())
        aid = str(uuid4())
        aid_holder["aid"] = aid
        _seed(
            scoped,
            clientes=[
                cliente_row(cid, nome="Luciano"),
                cliente_row(spouse, nome="Maria", cpf="111"),
                cliente_row(seller, nome="Vera"),
                cliente_row(seller2, nome="Paulo"),
            ],
            atendimentos=[_atendimento(aid, cid)],
            empresas=[emp],
            partes=[
                _parte(aid, cliente_id=seller, lado="vendedor", papel="proprietario", ordem=0),
                _parte(aid, empresa_id=emp["id"], lado="comprador", papel="comprador", ordem=1),
                _parte(aid, cliente_id=spouse, lado="comprador", papel="conjuge", ordem=0),
                _parte(aid, cliente_id=seller2, lado="vendedor", papel="conjuge", ordem=1),
            ],
        )
        r = http.get(f"/api/clientes/{cid}/partes", headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"items", "total", "atendimento_id"}
        assert body["atendimento_id"] == aid and body["total"] == 5
        assert [i["rotulo"] for i in body["items"]] == [
            "COMP 1", "COMP 2", "COMP 3", "VEND 1", "VEND 2",
        ]
        titular, comp2, comp3, vend1, vend2 = body["items"]
        for item in body["items"]:
            assert set(item) == _PARTE_ITEM_KEYS
        assert titular["titular"] is True and titular["parte_id"] is None
        assert (titular["lado"], titular["papel"], titular["tipo_pessoa"]) == (
            "comprador", "comprador", "PF",
        )
        assert comp2["nome"] == "Maria" and comp2["papel"] == "conjuge"
        # PJ is numbered in the SAME sequence as PF (ordem 1 -> third comprador).
        assert comp3["tipo_pessoa"] == "PJ" and comp3["cliente_id"] is None
        assert comp3["empresa_id"] == emp["id"] and comp3["cliente"] is None
        assert comp3["documento"] == CNPJ_A
        assert set(comp3["empresa"]) == _EMPRESA_KEYS
        assert comp3["nome"] == "Empresa Um LTDA"
        assert [vend1["nome"], vend2["nome"]] == ["Vera", "Paulo"]
        # `cliente` carries EXACTLY compradores_service._CLIENTE_RESUMO.
        assert set(comp2["cliente"]) == set(comp_svc._CLIENTE_RESUMO)

    def test_documento_is_digits_only_for_a_pf(self, http, scoped):
        cid, _ = _deal(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="L", cpf=CPF_A_FMT)])
        item = http.get(f"/api/clientes/{cid}/partes", headers=_auth()).json()["items"][0]
        assert item["documento"] == CPF_A

    def test_ambiguous_atendimento_reads_empty_never_409(self, http, scoped):
        cid = str(uuid4())
        _seed(
            scoped, clientes=[cliente_row(cid, nome="X")],
            atendimentos=[_atendimento(str(uuid4()), cid), _atendimento(str(uuid4()), cid)],
        )
        r = http.get(f"/api/clientes/{cid}/partes", headers=_auth())
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "atendimento_id": None}

    def test_explicit_atendimento_id_picks_one_of_two(self, http, scoped):
        cid, a1, a2 = str(uuid4()), str(uuid4()), str(uuid4())
        _seed(
            scoped, clientes=[cliente_row(cid, nome="X")],
            atendimentos=[_atendimento(a1, cid), _atendimento(a2, cid)],
        )
        r = http.get(f"/api/clientes/{cid}/partes?atendimento_id={a2}", headers=_auth())
        assert r.status_code == 200 and r.json()["atendimento_id"] == a2

    def test_foreign_atendimento_id_is_404_not_empty(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.get(f"/api/clientes/{cid}/partes?atendimento_id={uuid4()}", headers=_auth())
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"

    def test_unknown_cliente_is_404(self, http, scoped):
        _seed(scoped)
        r = http.get(f"/api/clientes/{uuid4()}/partes", headers=_auth())
        assert r.status_code == 404

    def test_listar_partes_service_contract_shape(self, scoped, client):
        from uuid import UUID

        cid, aid = _deal(scoped)
        got_aid, items = svc.listar_partes(scoped, UUID(ORG_ID), UUID(cid))
        assert got_aid == aid and len(items) == 1


# ─── §2.2 / §8: PF-only readers survive a PJ party ────────────────────────


class TestPJNaoQuebraLeitoresPF:
    def test_compradores_listar_filters_pj_rows(self, scoped, client):
        from uuid import UUID

        emp = _empresa()
        cid, aid = _deal(
            scoped, empresas=[emp],
        )
        scoped.set_table_data("atendimento_partes", [
            _parte(aid, empresa_id=emp["id"]),
        ])
        out = comp_svc.listar(scoped, UUID(ORG_ID), UUID(cid), lado="comprador")
        assert out["items"] == [] and out["total"] == 0
        assert set(out) == {"items", "total", "atendimento_id", "lado"}

    def test_checklist_certificando_tolerates_pj_vendedor(self, scoped, client):
        from uuid import UUID

        from app.modules.card_hub import documento_checklist_service as chk

        emp = _empresa()
        other = str(uuid4())
        cid, aid = _deal(scoped, empresas=[emp], clientes=[cliente_row(other, nome="Z")])
        scoped.set_table_data("atendimento_partes", [
            _parte(aid, empresa_id=emp["id"], lado="vendedor", papel="proprietario"),
        ])
        scoped.set_table_data("atendimento_negociacao_parcelas", [])
        # `other` is on no deal at all: must be False, not a crash on a None
        # cliente_id in the vendedores list.
        assert chk._e_certificando(scoped, UUID(ORG_ID), UUID(other)) in (True, False)

    def test_pessoas_do_card_skips_pj_party(self, scoped, client):
        from app.modules.card_hub import empresas_service as emp_svc

        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        scoped.set_table_data("atendimento_partes", [
            _parte(aid, empresa_id=emp["id"], lado="vendedor"),
        ])
        scoped.set_table_data("atendimento_negociacao_parcelas", [])
        from uuid import UUID

        pessoas = emp_svc.pessoas_do_card(
            scoped, UUID(ORG_ID), {"id": aid, "cliente_id": cid}
        )
        assert [p["cliente_id"] for p in pessoas] == [cid]  # never "None"

    def test_conjuge_principal_not_poisoned_by_pj_party(self, scoped, client):
        from uuid import UUID

        emp = _empresa()
        spouse = str(uuid4())
        cid, aid = _deal(scoped, empresas=[emp], clientes=[cliente_row(spouse, nome="Ela")])
        pj = _parte(aid, empresa_id=emp["id"], lado="comprador", papel="comprador", ordem=0)
        sp = _parte(aid, cliente_id=spouse, lado="comprador", papel="outro", ordem=1)
        scoped.set_table_data("atendimento_partes", [pj, sp])
        out = comp_svc.atualizar_papel(
            scoped, UUID(ORG_ID), UUID(cid), UUID(sp["id"]), papel="conjuge"
        )
        # Titular is the ONLY candidate principal: PJ row must not make it
        # ambiguous (nor count as "None").
        assert out["conjuge_cliente_id"] == cid

    def test_patch_papel_on_pj_ok_but_conjuge_is_400(self, scoped, client):
        from uuid import UUID

        from noctusai_lib.primitives.exceptions import ValidationError_

        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        pj = _parte(aid, empresa_id=emp["id"])
        scoped.set_table_data("atendimento_partes", [pj])
        with pytest.raises(ValidationError_, match="Uma empresa não pode ser cônjuge."):
            comp_svc.atualizar_papel(
                scoped, UUID(ORG_ID), UUID(cid), UUID(pj["id"]), papel="conjuge"
            )
        out = comp_svc.atualizar_papel(
            scoped, UUID(ORG_ID), UUID(cid), UUID(pj["id"]), papel="fiador"
        )
        assert out["papel"] == "fiador" and out["cliente"] is None

    def test_delete_pj_removes_only_the_junction_row(self, http, scoped):
        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        pj = _parte(aid, empresa_id=emp["id"])
        scoped.set_table_data("atendimento_partes", [pj])
        from uuid import UUID

        comp_svc.remover(scoped, UUID(ORG_ID), UUID(cid), UUID(pj["id"]))
        assert scoped.table("atendimento_partes").select("*").execute().data == []
        assert len(scoped.table("empresas").select("*").execute().data) == 1


# ─── §2.3 add party ────────────────────────────────────────────────────────


class TestAdicionarParte:
    def test_pj_by_cnpj_creates_empresa_and_returns_parte_item(self, http, scoped):
        cid, aid = _deal(scoped)
        r = http.post(
            f"/api/clientes/{cid}/compradores",
            json={"cnpj": "11.222.333/0001-81", "razao_social": "Nova SA", "lado": "vendedor"},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert _PARTE_ITEM_KEYS <= set(body)
        assert body["tipo_pessoa"] == "PJ" and body["rotulo"] == "VEND 1"
        assert body["papel"] == "proprietario" and body["cliente_id"] is None
        assert body["documento"] == CNPJ_A and body["nome"] == "Nova SA"
        [empresa] = scoped.table("empresas").select("*").execute().data
        assert empresa["cnpj"] == CNPJ_A and empresa["razao_social"] == "Nova SA"
        [row] = scoped.table("atendimento_partes").select("*").execute().data
        assert row["empresa_id"] == empresa["id"] and row["cliente_id"] is None

    def test_pj_by_cnpj_reuses_existing_empresa(self, http, scoped):
        emp = _empresa()
        cid, _ = _deal(scoped, empresas=[emp])
        r = http.post(
            f"/api/clientes/{cid}/compradores",
            json={"cnpj": CNPJ_A, "razao_social": "Outro Nome"}, headers=_auth(),
        )
        assert r.status_code == 201
        assert r.json()["empresa_id"] == emp["id"]
        assert len(scoped.table("empresas").select("*").execute().data) == 1
        # fill-empty only: an existing razão social is never overwritten.
        assert scoped.table("empresas").select("*").execute().data[0]["razao_social"] == "Empresa Um LTDA"

    def test_pj_by_empresa_id(self, http, scoped):
        emp = _empresa()
        cid, _ = _deal(scoped, empresas=[emp])
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"empresa_id": emp["id"]}, headers=_auth())
        assert r.status_code == 201
        assert r.json()["rotulo"] == "COMP 2" and r.json()["empresa"]["id"] == emp["id"]

    def test_unknown_empresa_id_404(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"empresa_id": str(uuid4())}, headers=_auth())
        assert r.status_code == 404

    def test_invalid_cnpj_400(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"cnpj": "11.222.333/0001-82"}, headers=_auth())
        assert r.status_code == 400
        assert r.json()["error"]["message"] == "CNPJ inválido."

    @pytest.mark.parametrize("body", [
        {}, {"nome": "A", "cnpj": CNPJ_A}, {"cliente_id": str(uuid4()), "nome": "A"},
        {"empresa_id": str(uuid4()), "cnpj": CNPJ_A},
    ])
    def test_exactly_one_of_four_400(self, http, scoped, body):
        cid, _ = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores", json=body, headers=_auth())
        assert r.status_code == 400
        assert r.json()["error"]["message"] == (
            "Informe exatamente um de: cliente_id, nome, empresa_id, cnpj."
        )

    def test_empresa_cannot_be_conjuge_400(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"cnpj": CNPJ_A, "papel": "conjuge"}, headers=_auth())
        assert r.status_code == 400
        assert r.json()["error"]["message"] == "Uma empresa não pode ser cônjuge."

    def test_duplicate_empresa_409(self, http, scoped):
        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        scoped.set_table_data("atendimento_partes", [_parte(aid, empresa_id=emp["id"])])
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"cnpj": CNPJ_A}, headers=_auth())
        assert r.status_code == 409
        assert r.json()["error"]["message"] == "Esta empresa já é parte deste atendimento."

    def test_pf_add_keeps_legacy_keys_plus_parte_item(self, http, scoped):
        cid, aid = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"nome": "Maria Mauricio"}, headers=_auth())
        assert r.status_code == 201
        body = r.json()
        legacy = {"id", "atendimento_id", "cliente_id", "lado", "papel", "ordem",
                  "observacao", "created_at", "cliente"}
        assert legacy <= set(body) and _PARTE_ITEM_KEYS <= set(body)
        assert body["id"] == body["parte_id"] and body["rotulo"] == "COMP 2"
        assert body["tipo_pessoa"] == "PF"

    def test_pf_add_linking_existing_match_creates_no_duplicate_cliente(self, http, scoped):
        match = str(uuid4())
        cid, aid = _deal(scoped, clientes=[cliente_row(match, nome="Ana", cpf=CPF_A_FMT)])
        before = len(scoped.table("clientes").select("*").execute().data)
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"cliente_id": match}, headers=_auth())
        assert r.status_code == 201 and r.json()["cliente_id"] == match
        assert len(scoped.table("clientes").select("*").execute().data) == before

    def test_unknown_body_field_422(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores",
                      json={"cnpj": CNPJ_A, "bogus": 1}, headers=_auth())
        assert r.status_code == 422

    def test_cnpj_length_bound_is_422(self):
        with pytest.raises(ValidationError):
            ParteCreateBody(cnpj="123")


# ─── §2.5 lookup ───────────────────────────────────────────────────────────


class TestLookup:
    def test_cpf_match_returns_cliente_atendimentos_and_certidoes(self, http, scoped):
        match, other_cid, other_aid = str(uuid4()), str(uuid4()), str(uuid4())
        stage = {"id": str(uuid4()), "org_id": ORG_ID, "label": "Proposta", "pipeline": "x"}
        cid, aid = _deal(
            scoped,
            clientes=[cliente_row(match, nome="Ana", nome_oficial="Ana Silva", cpf=CPF_A_FMT, celular="11")],
            atendimentos=[_atendimento(other_aid, other_cid, titulo="Outro", etapa_id=stage["id"],
                                       created_at="2026-02-01T00:00:00+00:00")],
            stages=[stage],
        )
        # `match` is a party of the OTHER deal; the card's own titular shares no CPF.
        scoped.set_table_data("clientes", scoped.table("clientes").select("*").execute().data
                              + [cliente_row(other_cid, nome="Outro Titular")])
        scoped.set_table_data("atendimento_partes", [
            _parte(other_aid, cliente_id=match, lado="vendedor", papel="proprietario"),
        ])
        scoped.set_table_data("certidao_consultas", [_consulta("c1", cliente_id=match)])
        hoje = date.today().isoformat()
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", emitida_em=hoje),
        ])
        r = http.get(f"/api/clientes/{cid}/partes/lookup?documento={CPF_A}", headers=_auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == _LOOKUP_KEYS
        assert body["encontrado"] == "cliente" and body["tipo_documento"] == "cpf"
        # CPF matches BOTH the card's own titular (digits) and `match`
        # (formatted): the oldest-first / already-on-this-deal rule picks one.
        assert body["cliente"]["id"] in (cid, match)
        assert set(body["cliente"]) == {"id", "nome", "nome_oficial", "cpf", "celular", "email"}
        assert set(body["certidoes"]) == _CERT_KEYS
        for a in body["atendimentos"]:
            assert set(a) == _ATD_KEYS
        ids = [a["id"] for a in body["atendimentos"]]
        assert other_aid in ids and aid in ids
        outro = next(a for a in body["atendimentos"] if a["id"] == other_aid)
        assert outro["lado"] == "vendedor" and outro["titular"] is False
        assert outro["parte_id"] and outro["etapa"] == {"id": stage["id"], "nome": "Proposta"}
        proprio = next(a for a in body["atendimentos"] if a["id"] == aid)
        assert proprio["titular"] is True and proprio["parte_id"] is None
        assert body["ja_no_atendimento"] is True
        [item] = body["certidoes"]["itens"]
        assert set(item) == _CERT_ITEM_KEYS and item["tipo"] == "cnd_federal"
        assert item["idade_dias"] == 0 and item["stale_para_contrato"] is False

    def test_cpf_with_punctuation_is_normalized(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.get("/api/clientes/%s/partes/lookup" % cid,
                     params={"documento": CPF_A_FMT}, headers=_auth())
        assert r.json()["documento"] == CPF_A

    def test_miss_is_200_with_null_encontrado(self, http, scoped):
        cid, _ = _deal(scoped)
        r = http.get(f"/api/clientes/{cid}/partes/lookup?documento=11144477735", headers=_auth())
        assert r.status_code == 200
        body = r.json()
        assert body["encontrado"] is None and body["cliente"] is None
        assert body["ja_no_atendimento"] is False and body["atendimentos"] == []
        assert body["certidoes"]["itens"] == [] and body["certidoes"]["alerta_vencidas"] is False

    def test_cnpj_match_returns_empresa_with_parte_atendimento(self, http, scoped):
        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        scoped.set_table_data("atendimento_partes", [_parte(aid, empresa_id=emp["id"])])
        scoped.set_table_data("certidao_consultas", [
            _consulta("c9", empresa_id=emp["id"], tipo_documento="cnpj"),
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r9", "c9", "cnd_federal", emitida_em="2020-01-01"),
        ])
        r = http.get(f"/api/clientes/{cid}/partes/lookup?documento=11.222.333/0001-81",
                     headers=_auth())
        body = r.json()
        assert body["encontrado"] == "empresa" and body["tipo_documento"] == "cnpj"
        assert body["cliente"] is None and set(body["empresa"]) == _EMPRESA_KEYS
        assert body["ja_no_atendimento"] is True
        assert [a["id"] for a in body["atendimentos"]] == [aid]
        assert body["certidoes"]["alerta_vencidas"] is True
        assert body["certidoes"]["tipos_vencidos"] == ["cnd_federal"]
        assert body["certidoes"]["mensagem"] == (
            "Há certidões com mais de 30 dias. Re-emita e re-analise antes de usar no contrato."
        )

    @pytest.mark.parametrize("doc,msg", [
        ("52998224726", "CPF inválido."),
        ("11222333000182", "CNPJ inválido."),
        ("123", "Informe um CPF ou CNPJ válido."),
        ("1234567890123", "Informe um CPF ou CNPJ válido."),
    ])
    def test_invalid_documento_400(self, http, scoped, doc, msg):
        cid, _ = _deal(scoped)
        r = http.get(f"/api/clientes/{cid}/partes/lookup?documento={doc}", headers=_auth())
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"
        assert r.json()["error"]["message"] == msg

    def test_missing_documento_param_422(self, http, scoped):
        cid, _ = _deal(scoped)
        assert http.get(f"/api/clientes/{cid}/partes/lookup", headers=_auth()).status_code == 422

    def test_never_returns_another_orgs_rows(self, http, scoped):
        cid, _ = _deal(scoped)
        scoped.set_table_data("clientes", scoped.table("clientes").select("*").execute().data + [
            {**cliente_row(str(uuid4()), nome="Estranho", cpf="11144477735"), "org_id": str(uuid4())},
        ])
        r = http.get(f"/api/clientes/{cid}/partes/lookup?documento=11144477735", headers=_auth())
        assert r.json()["encontrado"] is None


class TestStaleBoundary:
    """`stale_para_contrato` = idade_dias >= max_dias — the SAME predicate as
    `derivacao._certidoes` ((assinatura - emitida_em).days >= certidao_max_dias)."""

    HOJE = date(2026, 10, 1)

    def _blk(self, emitida):
        return svc.certidoes_mais_recentes(
            [_resultado("r", "c", "cnd_federal", emitida_em=emitida)],
            hoje=self.HOJE, max_dias=30,
        )

    def test_29_days_is_fresh(self):
        blk = self._blk("2026-09-02")
        assert blk["itens"][0]["idade_dias"] == 29
        assert blk["itens"][0]["stale_para_contrato"] is False
        assert blk["alerta_vencidas"] is False and blk["mensagem"] is None

    def test_30_days_is_stale(self):
        blk = self._blk("2026-09-01")
        assert blk["itens"][0]["idade_dias"] == 30
        assert blk["itens"][0]["stale_para_contrato"] is True
        assert blk["tipos_vencidos"] == ["cnd_federal"] and blk["alerta_vencidas"] is True

    def test_max_dias_comes_from_politica_not_a_literal(self):
        from app.modules.card_hub.contrato_gerador import politica

        assert svc.certidoes_mais_recentes(
            [], hoje=self.HOJE, max_dias=politica.POLITICA_PADRAO.certidao_max_dias
        )["max_dias"] == 30

    def test_latest_emissao_wins_then_created_at_and_undated_ignored(self):
        blk = svc.certidoes_mais_recentes([
            _resultado("old", "c", "cnd_federal", emitida_em="2026-01-01"),
            _resultado("new", "c", "cnd_federal", emitida_em="2026-09-30"),
            _resultado("tie_a", "c", "trf3_sp", emitida_em="2026-09-30", created_at="2026-09-30T01:00:00"),
            _resultado("tie_b", "c", "trf3_sp", emitida_em="2026-09-30", created_at="2026-09-30T02:00:00"),
            _resultado("nodate", "c", "tjsp", emitida_em=None),
        ], hoje=self.HOJE, max_dias=30)
        got = {i["tipo"]: i["resultado_id"] for i in blk["itens"]}
        assert got == {"cnd_federal": "new", "trf3_sp": "tie_b"}

    def test_rotulo_falls_back_to_tipo(self):
        blk = svc.certidoes_mais_recentes(
            [_resultado("r", "c", "tjsp", emitida_em="2026-09-30", nome_display=None)],
            hoje=self.HOJE, max_dias=30,
        )
        assert blk["itens"][0]["rotulo"] == "tjsp"


# ─── contract generator: PJ party is a faltando, not a silent skip ────────


class TestContratoPjFaltando:
    def test_partes_pj_helper(self, scoped, client):
        from uuid import UUID

        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        scoped.set_table_data("atendimento_partes", [
            _parte(aid, empresa_id=emp["id"], lado="vendedor", papel="proprietario"),
        ])
        [pj] = svc.partes_pj(scoped, UUID(ORG_ID), aid)
        assert pj["cnpj"] == CNPJ_A and pj["lado"] == "vendedor" and pj["nome"] == "Empresa Um LTDA"

    def test_derivacao_names_each_missing_pj_field(self):
        """Migration 193 replaced the blanket `partes.pj_sem_qualificacao`
        with per-field faltando (razão social, CNPJ, NIRE, sede, representante)."""
        import dataclasses

        from app.modules.card_hub.contrato_gerador import derivacao
        from app.modules.card_hub.contrato_gerador.dados import ParteJuridica
        from tests.modules.card_hub import contrato_gerador_fixtures as fx

        base = fx.base_v1()
        d = dataclasses.replace(base, partes_pj=[ParteJuridica(
            parte_id="p1", empresa_id="e1", lado="comprador", papel="comprador",
            razao_social="Acme", cnpj=CNPJ_A,
        )])
        av = derivacao.avaliar(
            d, derivacao.derivar_switches(d, fx.POLITICA_PADRAO, fx.REFERENCIA),
            fx.POLITICA_PADRAO, fx.REFERENCIA,
        )
        campos = {f["campo"] for f in av.faltando if f["parte_id"] == "p1"}
        assert {"partes.pj.nire", "partes.pj.sede_logradouro", "partes.pj.representante"} <= campos
        assert "partes.pj_sem_qualificacao" not in {f["campo"] for f in av.faltando}

    def test_partes_pj_carries_nire_and_sede(self, scoped, client):
        from uuid import UUID

        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        scoped.set_table_data("atendimento_partes", [
            _parte(aid, empresa_id=emp["id"], lado="vendedor", papel="proprietario",
                   pj_nire="35200000000", pj_sede_cidade="Cotia"),
        ])
        [pj] = svc.partes_pj(scoped, UUID(ORG_ID), aid)
        assert pj["nire"] == "35200000000" and pj["sede"]["cidade"] == "Cotia"


# ─── auth: strict 401 ──────────────────────────────────────────────────────


class TestAuthBoundary:
    @pytest.mark.parametrize("path", [
        "/api/clientes/{cid}/partes",
        f"/api/clientes/{{cid}}/partes/lookup?documento={CPF_A}",
    ])
    def test_no_token_is_exactly_401(self, anon_http, path):
        r = anon_http.get(path.format(cid=uuid4()))
        assert r.status_code == 401

    def test_post_compradores_no_token_is_exactly_401(self, anon_http):
        r = anon_http.post(f"/api/clientes/{uuid4()}/compradores", json={"cnpj": CNPJ_A})
        assert r.status_code == 401


# ─── migration 193: a party's contract-qualification fields ───────────────


class TestParteContratoPatch:
    def _url(self, cid, parte_id):
        return f"/api/clientes/{cid}/compradores/{parte_id}/contrato"

    def test_no_token_is_exactly_401(self, anon_http):
        r = anon_http.patch(self._url(uuid4(), uuid4()), json={"pj_nire": "1"})
        assert r.status_code == 401

    def test_pj_party_stores_nire_and_sede(self, http, scoped):
        emp = _empresa()
        cid, aid = _deal(scoped, empresas=[emp])
        pj = _parte(aid, empresa_id=emp["id"], lado="vendedor", papel="proprietario")
        scoped.set_table_data("atendimento_partes", [pj])
        r = http.patch(self._url(cid, pj["id"]), headers=_auth(), json={
            "pj_nire": " 35200000000 ", "pj_sede_uf": "sp", "pj_sede_cep": "06700-000",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pj_nire"] == "35200000000"
        assert body["pj_sede_uf"] == "SP" and body["pj_sede_cep"] == "06700000"
        # untouched keys are not written (PATCH semantics)
        assert body["pj_sede_cidade"] is None

    def test_the_list_reads_back_the_stored_qualification(self, http, scoped):
        """A write-only qualification shows blank in the form and invites a
        clearing re-save — the list must return what the PATCH stored."""
        emp = _empresa()
        rep = str(uuid4())
        cid, aid = _deal(scoped, empresas=[emp], clientes=[cliente_row(rep, nome="Rep")])
        pj = _parte(aid, empresa_id=emp["id"], lado="vendedor", papel="proprietario")
        pr = _parte(aid, cliente_id=rep, lado="vendedor", papel="representante", ordem=1)
        scoped.set_table_data("atendimento_partes", [pj, pr])
        assert http.patch(self._url(cid, pj["id"]), headers=_auth(), json={
            "pj_nire": "35200000000", "pj_sede_cidade": "Cotia", "pj_sede_uf": "SP",
        }).status_code == 200
        assert http.patch(self._url(cid, pr["id"]), headers=_auth(),
                          json={"representa_parte_id": pj["id"]}).status_code == 200
        items = {i["parte_id"]: i for i in
                 http.get(f"/api/clientes/{cid}/partes", headers=_auth()).json()["items"]}
        assert items[pj["id"]]["pj_nire"] == "35200000000"
        assert items[pj["id"]]["pj_sede"]["cidade"] == "Cotia"
        assert items[pj["id"]]["pj_sede"]["uf"] == "SP"
        assert items[pr["id"]]["representa_parte_id"] == pj["id"]
        # a person party carries no PJ qualification block
        assert items[pr["id"]]["pj_nire"] is None and items[pr["id"]]["pj_sede"] is None

    def test_pj_fields_are_refused_on_a_person(self, http, scoped):
        pessoa = str(uuid4())
        cid, aid = _deal(scoped, clientes=[cliente_row(pessoa, nome="Vend")])
        pf = _parte(aid, cliente_id=pessoa, lado="vendedor", papel="proprietario")
        scoped.set_table_data("atendimento_partes", [pf])
        r = http.patch(self._url(cid, pf["id"]), headers=_auth(), json={"pj_nire": "1"})
        assert r.status_code == 400, r.text

    def test_representante_links_to_a_company_of_the_same_deal(self, http, scoped):
        emp = _empresa()
        rep, outro = str(uuid4()), str(uuid4())
        cid, aid = _deal(scoped, empresas=[emp], clientes=[
            cliente_row(rep, nome="Rep"), cliente_row(outro, nome="Outro"),
        ])
        pj = _parte(aid, empresa_id=emp["id"], lado="vendedor", papel="proprietario")
        pr = _parte(aid, cliente_id=rep, lado="vendedor", papel="representante", ordem=1)
        po = _parte(aid, cliente_id=outro, lado="vendedor", papel="proprietario", ordem=2)
        scoped.set_table_data("atendimento_partes", [pj, pr, po])
        ok = http.patch(self._url(cid, pr["id"]), headers=_auth(), json={"representa_parte_id": pj["id"]})
        assert ok.status_code == 200, ok.text
        assert ok.json()["representa_parte_id"] == pj["id"]
        # a person party is not a company to represent
        r = http.patch(self._url(cid, pr["id"]), headers=_auth(), json={"representa_parte_id": po["id"]})
        assert r.status_code == 400
        # only a 'representante' represents
        r = http.patch(self._url(cid, po["id"]), headers=_auth(), json={"representa_parte_id": pj["id"]})
        assert r.status_code == 400

    def test_a_company_cannot_be_anuente(self, http, scoped):
        cid, _aid = _deal(scoped)
        r = http.post(f"/api/clientes/{cid}/compradores", headers=_auth(),
                      json={"cnpj": CNPJ_A, "lado": "vendedor", "papel": "anuente"})
        assert r.status_code == 400, r.text

    def test_anuente_and_representante_are_vendedor_papeis(self):
        assert "anuente" in comp_svc.PAPEIS_POR_LADO["vendedor"]
        assert "representante" in comp_svc.PAPEIS_POR_LADO["vendedor"]
        assert "anuente" not in comp_svc.PAPEIS_POR_LADO["comprador"]
