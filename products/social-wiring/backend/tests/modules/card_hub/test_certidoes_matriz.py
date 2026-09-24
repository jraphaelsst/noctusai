"""`GET /api/clientes/{cliente_id}/certidoes/matriz` — the "Certidões" card
tab's matrix (`card_hub.certidoes_matriz_service.montar_matriz`).

Pins: empty-atendimento shape; vendedor columns include a registered spouse
even without their own `atendimento_partes` row (`empresas_service.
pessoas_do_card`, reused not restated); empresa columns are exactly the
`exige_certidoes=True` ones with a vendedor-side owner; the three cell
colors (Não constam / Constam / Pendente) plus the FGTS row's N/A on every
PF column; per-column totals.

Auth is NOT re-tested here — `card_hub/test_auth_boundary.py`'s
route-enumeration already covers this mounted route.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.modules.card_hub import certidoes_matriz_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str, **over) -> dict:
    row = {
        "id": aid, "org_id": ORG_ID, "cliente_id": cliente_id,
        "lead_id": None, "meta_ads_lead_id": None, "status": "aberta",
        "substituida_por": None, "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }
    row.update(over)
    return row


def _parte(atendimento_id: str, cliente_id: str, *, lado="vendedor", papel="proprietario") -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atendimento_id,
        "cliente_id": cliente_id, "lado": lado, "papel": papel,
        "ordem": 0, "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
        "created_by": None, "updated_at": None,
    }


def _empresa(id_=None, **over) -> dict:
    row = {
        "id": id_ or str(uuid4()), "org_id": ORG_ID, "cnpj": "11222333000181",
        "razao_social": "Empresa Um LTDA", "nome_fantasia": None,
        "natureza_juridica": None, "data_abertura": None,
        "situacao_cadastral": "ativa", "data_situacao_cadastral": None,
        "motivo_situacao": None, "dados_origem": None, "dados_documento_id": None,
        "dados_em": None, "dados_confirmado_por": None, "dados_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    }
    row.update(over)
    return row


def _participacao(cliente_id: str, empresa_id: str, **over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cliente_id,
        "empresa_id": empresa_id, "participacao_pct": "50.00", "desde": None,
        "fonte_documento_id": None, "origem": "manual",
        "confirmado_por": None, "confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(over)
    return row


def _consulta(id_, *, cliente_id=None, empresa_id=None, tipo_documento="cpf", documento="12345678901") -> dict:
    return {
        "id": id_, "org_id": ORG_ID, "empresa_id": empresa_id,
        "cliente_id": cliente_id, "atendimento_parte_id": None,
        "tipo_documento": tipo_documento, "documento": documento, "nome": "Fulano",
        "excluida_em": None, "situacao_cadastral": None, "data_situacao": None,
        "situacao_origem": None,
    }


def _resultado(id_, consulta_id, tipo, *, status="pendente", resultado=None, created_at="2026-01-01T00:00:00+00:00", **over) -> dict:
    row = {
        "id": id_, "org_id": ORG_ID, "consulta_id": consulta_id, "tipo": tipo,
        "status": status, "resultado": resultado, "numero": None,
        "emitida_em": None, "validade_ate": None, "analise_ia": None,
        "erro_mensagem": None, "ordem": 0, "created_at": created_at,
    }
    row.update(over)
    return row


def _seed_tables(scoped) -> None:
    for t in (
        "clientes", "atendimentos", "atendimento_partes",
        "atendimento_negociacao_parcelas", "empresas",
        "cliente_empresa_participacoes", "certidao_consultas",
        "certidao_resultados", "empresa_documentos",
    ):
        scoped.set_table_data(t, [])


class TestMatrizVazia:
    def test_sem_atendimento_aberto_retorna_matriz_vazia(self, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo")])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        assert resultado["atendimento_id"] is None
        assert resultado["colunas"] == []
        assert resultado["celulas"] == {}
        assert len(resultado["linhas"]) == 15

    def test_linhas_seguem_a_ordem_5_1_a_5_15_do_levantamento(self, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo")])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        assert [linha["linha"] for linha in resultado["linhas"]] == [
            f"5.{i}" for i in range(1, 16)
        ]
        assert resultado["linhas"][0]["tipo"] == "cnd_federal"
        assert resultado["linhas"][12]["tipo"] == "fgts_regularidade"


class TestColunas:
    def test_conjuge_sem_parte_propria_conta_como_coluna(self, scoped):
        """[migration 153] A vendedor's registered spouse counts as a VEND
        column even without its own `atendimento_partes` row —
        `pessoas_do_card`, reused."""
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id, conjuge_id = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"),
            cliente_row(vendedor_id, nome="Ronaldo", conjuge_cliente_id=conjuge_id),
            cliente_row(conjuge_id, nome="Fernanda"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        pessoas = [c for c in resultado["colunas"] if c["kind"] == "pessoa"]
        assert {p["nome"] for p in pessoas} == {"Ronaldo", "Fernanda"}
        assert [p["rotulo"] for p in pessoas] == ["VEND 1", "VEND 2"]

    def test_comprador_titular_nao_entra_nas_colunas(self, scoped):
        """Only the vendedor side — the titular (always a comprador) is out
        of THIS matrix's scope."""
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        pessoas_ids = {c["id"] for c in resultado["colunas"] if c["kind"] == "pessoa"}
        assert pessoas_ids == {vendedor_id}

    def test_empresa_exigida_entra_nao_exigida_fica_de_fora(self, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])
        exigida = _empresa(situacao_cadastral="ativa", razao_social="Ativa LTDA")
        antiga = date.today().replace(year=date.today().year - 6).isoformat()
        nao_exigida = _empresa(
            situacao_cadastral="baixada", data_situacao_cadastral=antiga,
            razao_social="Baixada Ha Anos LTDA",
        )
        scoped.set_table_data("empresas", [exigida, nao_exigida])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_id, exigida["id"]),
            _participacao(vendedor_id, nao_exigida["id"]),
        ])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        empresas = [c for c in resultado["colunas"] if c["kind"] == "empresa"]
        assert [e["id"] for e in empresas] == [exigida["id"]]
        assert empresas[0]["rotulo"] == "EMP 1"


class TestCelulas:
    def test_cores_nao_constam_constam_pendente(self, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])
        scoped.set_table_data("certidao_consultas", [
            _consulta("c1", cliente_id=vendedor_id, tipo_documento="cpf"),
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="sucesso", resultado="negativa"),
            _resultado("r2", "c1", "trf3_sp", status="sucesso", resultado="positiva"),
            # No resultado row at all for "trf3" -> Pendente by absence.
        ])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        [coluna] = [c for c in resultado["colunas"] if c["kind"] == "pessoa"]
        assert resultado["celulas"]["cnd_federal"][coluna["id"]]["status"] == "nao_constam"
        assert resultado["celulas"]["cnd_federal"][coluna["id"]]["texto"] == "Não constam"
        assert resultado["celulas"]["trf3_sp"][coluna["id"]]["status"] == "constam"
        assert resultado["celulas"]["trf3"][coluna["id"]]["status"] == "pendente"
        totais = resultado["totais"][coluna["id"]]
        assert totais["nao_constam"] == 1
        assert totais["constam"] == 1
        # Every one of the other 13 rows (minus the FGTS N/A, excluded from
        # any total bucket) is Pendente by absence.
        assert totais["pendente"] == 12

    def test_status_diferente_de_sucesso_e_pendente_mesmo_com_resultado_setado(self, scoped):
        """A `status != 'sucesso'` resultado (still processing/erro/na_fila)
        must read as Pendente — `resultado` alone is not enough."""
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])
        scoped.set_table_data("certidao_consultas", [
            _consulta("c1", cliente_id=vendedor_id, tipo_documento="cpf"),
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="erro", resultado=None),
        ])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        [coluna] = [c for c in resultado["colunas"] if c["kind"] == "pessoa"]
        assert resultado["celulas"]["cnd_federal"][coluna["id"]]["status"] == "pendente"

    def test_resultado_mais_recente_vence_quando_ha_mais_de_uma_consulta(self, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])
        scoped.set_table_data("certidao_consultas", [
            _consulta("c1", cliente_id=vendedor_id, tipo_documento="cpf"),
            _consulta("c2", cliente_id=vendedor_id, tipo_documento="cpf"),
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="sucesso", resultado="positiva",
                       created_at="2026-01-01T00:00:00+00:00"),
            _resultado("r2", "c2", "cnd_federal", status="sucesso", resultado="negativa",
                       created_at="2026-02-01T00:00:00+00:00"),
        ])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        [coluna] = [c for c in resultado["colunas"] if c["kind"] == "pessoa"]
        celula = resultado["celulas"]["cnd_federal"][coluna["id"]]
        assert celula["status"] == "nao_constam"
        assert celula["resultado_id"] == "r2"

    def test_fgts_e_na_para_pessoa_e_normal_para_empresa(self, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])
        empresa = _empresa(situacao_cadastral="ativa")
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_id, empresa["id"]),
        ])
        scoped.set_table_data("certidao_consultas", [
            _consulta("c1", empresa_id=empresa["id"], tipo_documento="cnpj", documento=empresa["cnpj"]),
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "fgts_regularidade", status="sucesso", resultado="negativa"),
        ])

        resultado = svc.montar_matriz(scoped, ORG_ID, cid)

        [pessoa] = [c for c in resultado["colunas"] if c["kind"] == "pessoa"]
        [empresa_col] = [c for c in resultado["colunas"] if c["kind"] == "empresa"]
        celula_pessoa = resultado["celulas"]["fgts_regularidade"][pessoa["id"]]
        assert celula_pessoa == {
            "status": "na", "texto": "N/A", "resultado_id": None, "consulta_id": None,
            "numero": None, "emitida_em": None, "validade_ate": None,
            "analise_ia": None, "erro_mensagem": None,
        }
        celula_empresa = resultado["celulas"]["fgts_regularidade"][empresa_col["id"]]
        assert celula_empresa["status"] == "nao_constam"
        # N/A cells never count toward any total bucket.
        assert resultado["totais"][pessoa["id"]]["nao_constam"] == 0
        assert resultado["totais"][pessoa["id"]]["constam"] == 0
        assert resultado["totais"][pessoa["id"]]["pendente"] == 14


class TestRotaHttp:
    def test_get_retorna_a_matriz_montada(self, client, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])

        r = client.get(f"/api/clientes/{cid}/certidoes/matriz", headers=_auth())

        assert r.status_code == 200
        body = r.json()
        assert len(body["linhas"]) == 15
        assert len(body["colunas"]) == 1
        assert body["colunas"][0]["nome"] == "Vendedor"
