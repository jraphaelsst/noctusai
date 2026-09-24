"""`POST/PATCH/DELETE /api/clientes/{cliente_id}/certidoes/matriz/linhas` —
per-card CUSTOM rows on the Certidões matriz tab (`card_hub.certidoes_
matriz_linhas_service`, migration 170).

Pins: `ordem`/"5.14" assignment (never reused after a removal); the
create-time fan-out writes one `pendente` resultado per consulta already
linked to a column of this card; a soft-deleted row drops off `montar_matriz`
/`listar` while its `certidao_resultados` rows stay untouched; a rename
keeps the row's `id` stable and is reflected live on the matrix; blank-name
validation.

Auth is NOT re-tested here — `card_hub/test_auth_boundary.py`'s
route-enumeration already covers these mounted routes.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub import certidoes_matriz_linhas_service as linhas_svc
from app.modules.card_hub import certidoes_matriz_service as matriz_svc
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


def _consulta(id_, *, cliente_id=None, empresa_id=None, tipo_documento="cpf", documento="12345678901") -> dict:
    return {
        "id": id_, "org_id": ORG_ID, "empresa_id": empresa_id,
        "cliente_id": cliente_id, "atendimento_parte_id": None,
        "tipo_documento": tipo_documento, "documento": documento, "nome": "Fulano",
        "excluida_em": None, "situacao_cadastral": None, "data_situacao": None,
        "situacao_origem": None,
    }


def _resultado(id_, consulta_id, tipo, *, status="pendente", resultado=None, linha_customizada_id=None, **over) -> dict:
    row = {
        "id": id_, "org_id": ORG_ID, "consulta_id": consulta_id, "tipo": tipo,
        "status": status, "resultado": resultado, "numero": None,
        "emitida_em": None, "validade_ate": None, "analise_ia": None,
        "erro_mensagem": None, "ordem": 0, "created_at": "2026-01-01T00:00:00+00:00",
        "linha_customizada_id": linha_customizada_id,
    }
    row.update(over)
    return row


def _seed_tables(scoped) -> None:
    for t in (
        "clientes", "atendimentos", "atendimento_partes",
        "atendimento_negociacao_parcelas", "empresas",
        "cliente_empresa_participacoes", "certidao_consultas",
        "certidao_resultados", "empresa_documentos",
        "certidao_matriz_linhas_customizadas",
    ):
        scoped.set_table_data(t, [])


def _card_com_vendedor(scoped) -> tuple[str, str, str]:
    """A minimal card: titular + one vendedor with an OPEN cpf consulta."""
    cid, aid, vendedor_id = str(uuid4()), str(uuid4()), str(uuid4())
    _seed_tables(scoped)
    scoped.set_table_data("clientes", [
        cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
    ])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_partes", [_parte(aid, vendedor_id)])
    scoped.set_table_data("certidao_consultas", [
        _consulta("c1", cliente_id=vendedor_id, tipo_documento="cpf"),
    ])
    return cid, aid, vendedor_id


class TestCriar:
    def test_cria_com_ordem_14_e_fan_out_para_a_consulta_ja_ligada(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)

        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="  Consulta Municipal  ")

        assert linha["ordem"] == 14
        assert linha["nome"] == "Consulta Municipal"  # trimmed
        resultados = scoped.table("certidao_resultados").select("*").execute().data
        [novo] = [r for r in resultados if r.get("linha_customizada_id") == linha["id"]]
        assert novo["consulta_id"] == "c1"
        assert novo["tipo"] == "outras_custom"
        assert novo["status"] == "pendente"
        assert novo["nome_display"] == "Outras: Consulta Municipal"

    def test_sem_nenhuma_coluna_no_card_fan_out_e_zero_mas_a_linha_existe(self, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo")])

        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="Outra coisa")

        assert linha["ordem"] == 14
        assert scoped.table("certidao_resultados").select("*").execute().data == []

    def test_nome_em_branco_e_recusado(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        with pytest.raises(ValidationError_):
            linhas_svc.criar(scoped, ORG_ID, cid, nome="   ")

    def test_ordem_nunca_e_reutilizada_apos_remocao(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)

        primeira = linhas_svc.criar(scoped, ORG_ID, cid, nome="Primeira")
        linhas_svc.remover(scoped, ORG_ID, cid, primeira["id"])
        segunda = linhas_svc.criar(scoped, ORG_ID, cid, nome="Segunda")

        assert primeira["ordem"] == 14
        assert segunda["ordem"] == 15


class TestRenomear:
    def test_renomeia_mantendo_o_id(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="Nome Antigo")

        renomeada = linhas_svc.renomear(scoped, ORG_ID, cid, linha["id"], nome="Nome Novo")

        assert renomeada["id"] == linha["id"]
        assert renomeada["nome"] == "Nome Novo"

    def test_linha_inexistente_e_404(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        with pytest.raises(NotFoundError):
            linhas_svc.renomear(scoped, ORG_ID, cid, str(uuid4()), nome="X")


class TestRemover:
    def test_remove_a_linha_mas_preserva_os_resultados_ja_gravados(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="Municipal")
        antes = scoped.table("certidao_resultados").select("*").execute().data
        assert len(antes) == 1

        linhas_svc.remover(scoped, ORG_ID, cid, linha["id"])

        depois = scoped.table("certidao_resultados").select("*").execute().data
        assert depois == antes  # untouched
        assert linhas_svc.listar(scoped, ORG_ID, cid) == []

    def test_remover_duas_vezes_e_404_na_segunda(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="X")
        linhas_svc.remover(scoped, ORG_ID, cid, linha["id"])
        with pytest.raises(NotFoundError):
            linhas_svc.remover(scoped, ORG_ID, cid, linha["id"])


class TestNaMatriz:
    def test_linha_customizada_aparece_como_5_14_aplicavel_a_pf_e_pj(self, scoped):
        cid, _aid, vendedor_id = _card_com_vendedor(scoped)
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [{
            "id": empresa_id, "org_id": ORG_ID, "cnpj": "11222333000181",
            "razao_social": "Empresa Um LTDA", "nome_fantasia": None,
            "natureza_juridica": None, "data_abertura": None,
            "situacao_cadastral": "ativa", "data_situacao_cadastral": None,
            "motivo_situacao": None, "dados_origem": None, "dados_documento_id": None,
            "dados_em": None, "dados_confirmado_por": None, "dados_confirmado_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
        }])
        scoped.set_table_data("cliente_empresa_participacoes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": vendedor_id,
            "empresa_id": empresa_id, "participacao_pct": "100.00", "desde": None,
            "fonte_documento_id": None, "origem": "manual",
            "confirmado_por": None, "confirmado_em": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }])

        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="Consulta Extra")

        resultado = matriz_svc.montar_matriz(scoped, ORG_ID, cid)
        [linha_matriz] = [l for l in resultado["linhas"] if l["custom"]]
        assert linha_matriz["linha"] == "5.14"
        assert linha_matriz["rotulo"] == "Outras: Consulta Extra"
        assert linha_matriz["chave"] == linha["id"]

        [pessoa] = [c for c in resultado["colunas"] if c["kind"] == "pessoa"]
        [empresa_col] = [c for c in resultado["colunas"] if c["kind"] == "empresa"]
        # Pendente by absence on the empresa column (no consulta linked to
        # it yet, so no placeholder was fanned out there) — NEVER "na":
        # a custom row applies to both PF and PJ, unlike FGTS/SERASA.
        assert resultado["celulas"][linha["id"]][pessoa["id"]]["status"] == "pendente"
        assert resultado["celulas"][linha["id"]][empresa_col["id"]]["status"] == "pendente"

    def test_linha_removida_some_da_matriz(self, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        linha = linhas_svc.criar(scoped, ORG_ID, cid, nome="Some Daqui")
        linhas_svc.remover(scoped, ORG_ID, cid, linha["id"])

        resultado = matriz_svc.montar_matriz(scoped, ORG_ID, cid)
        assert all(not l["custom"] for l in resultado["linhas"])
        assert len(resultado["linhas"]) == 13


class TestRotaHttp:
    def test_post_cria_patch_renomeia_delete_remove(self, client, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)

        criado = client.post(
            f"/api/clientes/{cid}/certidoes/matriz/linhas",
            headers=_auth(), json={"nome": "Consulta Nova"},
        )
        assert criado.status_code == 201
        linha_id = criado.json()["id"]
        assert criado.json()["nome"] == "Consulta Nova"

        renomeado = client.patch(
            f"/api/clientes/{cid}/certidoes/matriz/linhas/{linha_id}",
            headers=_auth(), json={"nome": "Consulta Renomeada"},
        )
        assert renomeado.status_code == 200
        assert renomeado.json()["nome"] == "Consulta Renomeada"

        removido = client.delete(
            f"/api/clientes/{cid}/certidoes/matriz/linhas/{linha_id}", headers=_auth(),
        )
        assert removido.status_code == 204

        matriz = client.get(f"/api/clientes/{cid}/certidoes/matriz", headers=_auth())
        assert all(not l["custom"] for l in matriz.json()["linhas"])

    def test_post_nome_em_branco_e_422(self, client, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        resp = client.post(
            f"/api/clientes/{cid}/certidoes/matriz/linhas",
            headers=_auth(), json={"nome": ""},
        )
        assert resp.status_code == 422

    def test_patch_linha_inexistente_e_404(self, client, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        resp = client.patch(
            f"/api/clientes/{cid}/certidoes/matriz/linhas/{uuid4()}",
            headers=_auth(), json={"nome": "X"},
        )
        assert resp.status_code == 404

    def test_delete_linha_inexistente_e_404(self, client, scoped):
        cid, _aid, _vendedor_id = _card_com_vendedor(scoped)
        resp = client.delete(
            f"/api/clientes/{cid}/certidoes/matriz/linhas/{uuid4()}", headers=_auth(),
        )
        assert resp.status_code == 404
