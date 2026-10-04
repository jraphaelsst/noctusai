"""`certidoes_partes_service` — the per-party Certidões tab (CONTRACT §1).

Pins: party set + labels (titular = COMP 1, PF/PJ share the per-lado
numbering, derived EMP columns); the cell-selection rule (newest EMISSION wins,
a dated cell is never shadowed by an undated/failed newer one); staleness =
`idade_dias >= politica.certidao_max_dias`; N/A rules; certidões follow the
person across atendimentos; the exact §1.1 field names; and the three writes
(emissão, reemitir, garantir célula) incl. every contract error code.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from noctusai_lib.primitives.exceptions import AppException

from app.modules.card_hub import certidoes_partes_service as svc
from app.modules.card_hub import partes_service
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.card_hub.services import AmbiguousAtendimento
from app.modules.certidoes.registry import CERTIDOES_CONFIG
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_certidoes_matriz import (
    _atendimento,
    _consulta,
    _empresa,
    _parte,
    _participacao,
    _resultado,
    _seed_tables,
)

HOJE = date(2026, 10, 1)
CPF = "41295423898"
CNPJ = "11222333000181"


def _dados(scoped, tabela: str) -> list[dict]:
    """The table's rows as a SELECT sees them — seeded rows PLUS every row a
    write inserted (the mock propagates inserts/updates to later reads)."""
    return scoped.table(tabela).select("*").execute().data


def _dia(dias_atras: int) -> str:
    return (HOJE - timedelta(days=dias_atras)).isoformat()


def _parte_pj(atendimento_id: str, empresa_id: str, *, lado="vendedor", ordem=0) -> dict:
    row = _parte(atendimento_id, str(uuid4()), lado=lado, papel="proprietario")
    row.update({"cliente_id": None, "empresa_id": empresa_id, "ordem": ordem})
    return row


def _card(scoped, *, vendedores=1):
    """Titular + `vendedores` PF vendedor parties, one open atendimento."""
    cid, aid = str(uuid4()), str(uuid4())
    vids = [str(uuid4()) for _ in range(vendedores)]
    _seed_tables(scoped)
    scoped.set_table_data("clientes", [
        cliente_row(cid, nome="Titular", cpf=CPF, nome_oficial="Titular Oficial"),
        *[cliente_row(v, nome=f"Vend {i}", cpf=f"0000000000{i}") for i, v in enumerate(vids)],
    ])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_partes", [
        _parte(aid, v) for v in vids
    ])
    return cid, aid, vids


# ─── pure cell logic ──────────────────────────────────────────────────────


class TestCelula:
    def test_stale_no_limite_exato_da_politica(self):
        limite = POLITICA_PADRAO.certidao_max_dias
        assert svc.max_dias() == limite
        no_limite = svc.montar_celula(
            "cnd_federal",
            {"id": "r", "status": "sucesso", "resultado": "negativa", "emitida_em": _dia(limite)},
            HOJE, limite,
        )
        um_antes = svc.montar_celula(
            "cnd_federal",
            {"id": "r", "status": "sucesso", "resultado": "negativa", "emitida_em": _dia(limite - 1)},
            HOJE, limite,
        )
        assert (no_limite["idade_dias"], no_limite["stale_para_contrato"]) == (limite, True)
        assert (um_antes["idade_dias"], um_antes["stale_para_contrato"]) == (limite - 1, False)

    def test_sem_emissao_nao_ha_idade_nem_stale(self):
        c = svc.montar_celula("cnd_federal", {"id": "r", "status": "pendente"}, HOJE, 30)
        assert c["idade_dias"] is None and c["stale_para_contrato"] is False
        assert (c["status"], c["texto"]) == ("pendente", "Pendente")

    def test_celula_vazia_e_pendente_sem_resultado(self):
        c = svc.montar_celula("trf3", None, HOJE, 30)
        assert c["resultado_id"] is None and c["status_processamento"] is None
        assert c["tem_arquivo"] is False and c["confirmado"] is False and c["origem"] is None

    def test_arquivo_e_confirmacao(self):
        c = svc.montar_celula(
            "cnd_federal",
            {"id": "r", "status": "sucesso", "resultado": "positiva", "arquivo_url": "k/x.pdf",
             "arquivo_nome": "x.pdf", "confirmado_em": "2026-09-30T00:00:00+00:00",
             "resultado_origem": "ia"},
            HOJE, 30,
        )
        assert (c["tem_arquivo"], c["arquivo_nome"], c["confirmado"], c["origem"]) == (
            True, "x.pdf", True, "ia",
        )
        assert c["status"] == "constam"

    def test_arquivo_manual_so_para_upload_no_bucket(self):
        """The FE shows "Ler o documento novamente" off this flag: a stored
        key with no `api_response` is a human's upload; a live emission is not."""
        base = {"id": "r", "status": "sucesso", "arquivo_url": "org/certidoes/c/x.pdf"}
        assert svc.montar_celula("serasa", {**base, "api_response": None}, HOJE, 30)["arquivo_manual"] is True
        ao_vivo = svc.montar_celula("cnd_federal", {**base, "api_response": {"code": 200}}, HOJE, 30)
        assert ao_vivo["arquivo_manual"] is False and ao_vivo["tem_arquivo"] is True
        assert svc.montar_celula("trf3", None, HOJE, 30)["arquivo_manual"] is False

    def test_pode_reler_todo_pdf_no_bucket_e_expoe_a_releitura(self):
        from datetime import datetime, timezone

        base = {"id": "r", "status": "sucesso", "arquivo_url": "org/certidoes/c/x.pdf"}
        ao_vivo = svc.montar_celula("cenprot", {**base, "api_response": {"code": 200}}, HOJE, 30)
        assert ao_vivo["pode_reler"] is True and ao_vivo["releitura"] is None
        externo = svc.montar_celula("cenprot", {**base, "arquivo_url": "https://x.example/a.pdf"}, HOJE, 30)
        assert externo["pode_reler"] is False
        div = [{"campo": "numero", "valor_atual": None, "valor_lido": "0123456789"}]
        lendo = svc.montar_celula("cenprot", {**base, "releitura": {
            "estado": "em_andamento", "iniciada_em": datetime.now(timezone.utc).isoformat(),
        }}, HOJE, 30)
        assert lendo["releitura"]["em_andamento"] is True
        feita = svc.montar_celula("cenprot", {**base, "releitura": {
            "estado": "concluida", "concluida_em": "2026-10-03T10:00:00+00:00", "divergencias": div,
        }}, HOJE, 30)
        assert feita["releitura"] == {
            "em_andamento": False, "concluida_em": "2026-10-03T10:00:00+00:00", "divergencias": div,
        }
        interrompida = svc.montar_celula("cenprot", {**base, "releitura": {
            "estado": "em_andamento", "iniciada_em": "2026-01-01T00:00:00+00:00",
        }}, HOJE, 30)
        assert interrompida["releitura"]["em_andamento"] is False

    def test_placeholder_de_consulta_manual_le_origem_manual(self):
        placeholder = {"id": "r", "status": "pendente", "consulta_origem": "manual"}
        assert svc.montar_celula("serasa", placeholder, HOJE, 30)["origem"] == "manual"

    def test_origem_manual_so_enquanto_pendente(self):
        """Once an upload flips it to `processando` the FE must poll again."""
        em_leitura = {"id": "r", "status": "processando", "consulta_origem": "manual"}
        assert svc.montar_celula("serasa", em_leitura, HOJE, 30)["origem"] is None

    def test_automatico_pendente_nao_e_manual(self):
        row = {"id": "r", "status": "pendente", "consulta_origem": None}
        assert svc.montar_celula("cnd_federal", row, HOJE, 30)["origem"] is None


class TestVencedor:
    def test_emissao_mais_nova_vence(self):
        a = {"id": "a", "tipo": "cnd_federal", "emitida_em": "2026-08-01", "created_at": "2026-09-30"}
        b = {"id": "b", "tipo": "cnd_federal", "emitida_em": "2026-09-01", "created_at": "2026-08-01"}
        por_tipo, _ = svc.indexar_vencedores([a, b])
        assert por_tipo["cnd_federal"]["id"] == "b"

    def test_celula_datada_nunca_e_sombreada_por_uma_sem_data(self):
        """A failed / still-pending re-emission has `emitida_em` NULL and a
        newer `created_at` — the valid certidão on file must still win."""
        velha_valida = {"id": "v", "tipo": "cnd_federal", "emitida_em": "2026-09-20", "created_at": "2026-09-20"}
        nova_erro = {"id": "e", "tipo": "cnd_federal", "emitida_em": None, "created_at": "2026-10-01"}
        por_tipo, _ = svc.indexar_vencedores([nova_erro, velha_valida])
        assert por_tipo["cnd_federal"]["id"] == "v"

    def test_empate_desempata_por_created_at(self):
        a = {"id": "a", "tipo": "trf3", "emitida_em": "2026-09-01", "created_at": "2026-09-01T10:00"}
        b = {"id": "b", "tipo": "trf3", "emitida_em": "2026-09-01", "created_at": "2026-09-01T11:00"}
        assert svc.indexar_vencedores([a, b])[0]["trf3"]["id"] == "b"

    def test_sem_datas_vence_o_mais_recente_criado(self):
        a = {"id": "a", "tipo": "trf3", "emitida_em": None, "created_at": "2026-09-01"}
        b = {"id": "b", "tipo": "trf3", "emitida_em": None, "created_at": "2026-09-02"}
        assert svc.indexar_vencedores([a, b])[0]["trf3"]["id"] == "b"

    def test_linha_customizada_indexada_pela_linha(self):
        r = {"id": "c", "tipo": "outras_custom", "linha_customizada_id": "L1", "emitida_em": None,
             "created_at": "x"}
        por_tipo, por_linha = svc.indexar_vencedores([r])
        assert por_tipo == {} and por_linha["L1"]["id"] == "c"


# ─── GET montar ───────────────────────────────────────────────────────────


class TestMontar:
    def test_resposta_tem_os_campos_exatos_do_contrato(self, scoped):
        cid, aid, [vid] = _card(scoped)
        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)

        assert set(out) == {"atendimento_id", "data_referencia", "max_dias", "linhas", "partes"}
        assert out["atendimento_id"] == aid
        assert out["data_referencia"] == "2026-10-01"
        assert out["max_dias"] == POLITICA_PADRAO.certidao_max_dias
        assert set(out["linhas"][0]) == {
            "tipo", "chave", "id", "linha", "rotulo", "custom", "automatico",
        }
        parte = out["partes"][0]
        assert set(parte) == {
            "chave", "kind", "tipo_pessoa", "rotulo", "lado", "papel", "titular", "nome",
            "documento", "cliente_id", "empresa_id", "parte_id", "totais", "celulas",
        }
        assert set(parte["totais"]) == {"nao_constam", "constam", "pendente", "vencidas"}
        assert set(parte["celulas"]["cnd_federal"]) == {
            "status", "texto", "tipo", "resultado_id", "consulta_id", "status_processamento",
            "resultado", "numero", "emitida_em", "validade_ate", "idade_dias",
            "stale_para_contrato", "arquivo_url", "tem_arquivo", "arquivo_manual", "pode_reler", "releitura", "arquivo_nome", "origem",
            "confirmado", "analise_ia", "erro_mensagem", "segunda_via", "pcen", "pendencia",
        }

    def test_titular_e_comp_1_e_partes_numeradas_por_lado(self, scoped):
        cid, aid, [v1, v2] = _card(scoped, vendedores=2)
        comprador_id = str(uuid4())
        scoped.set_table_data("clientes", [
            *_dados(scoped, "clientes"),
            cliente_row(comprador_id, nome="Conjuge"),
        ])
        scoped.set_table_data("atendimento_partes", [
            *_dados(scoped, "atendimento_partes"),
            _parte(aid, comprador_id, lado="comprador", papel="conjuge"),
        ])

        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)

        assert [(p["rotulo"], p["lado"], p["titular"]) for p in out["partes"]] == [
            ("COMP 1", "comprador", True),
            ("COMP 2", "comprador", False),
            ("VEND 1", "vendedor", False),
            ("VEND 2", "vendedor", False),
        ]
        titular = out["partes"][0]
        assert titular["parte_id"] is None and titular["papel"] == "comprador"
        assert titular["cliente_id"] == cid and titular["empresa_id"] is None
        assert titular["nome"] == "Titular Oficial" and titular["documento"] == CPF
        assert out["partes"][1]["parte_id"] is not None

    def test_parte_pj_compartilha_a_numeracao_do_lado(self, scoped):
        cid, aid, [v1] = _card(scoped)
        emp = _empresa(cnpj=CNPJ, razao_social="Vende LTDA")
        scoped.set_table_data("empresas", [emp])
        scoped.set_table_data("atendimento_partes", [
            *_dados(scoped, "atendimento_partes"),
            _parte_pj(aid, emp["id"], ordem=5),
        ])

        _alvo, partes = partes_service.listar_partes(
            scoped, ORG_ID, UUID(cid), atendimento_id=UUID(aid)
        )

        assert [(p["rotulo"], p["tipo_pessoa"]) for p in partes] == [
            ("COMP 1", "PF"), ("VEND 1", "PF"), ("VEND 2", "PJ"),
        ]
        pj = partes[-1]
        assert (pj["empresa_id"], pj["cliente_id"], pj["documento"], pj["nome"]) == (
            emp["id"], None, CNPJ, "Vende LTDA",
        )
        assert svc._chave(pj) == f"e:{emp['id']}" and svc._kind(pj) == "empresa"

    def test_celula_sinaliza_segunda_via_pela_marca_do_api_response(self):
        from app.modules.certidoes.service import MARCA_SEGUNDA_VIA

        base = {"id": "r1", "status": "sucesso", "emitida_em": "2026-07-01", "resultado": "negativa"}
        com = svc.montar_celula(
            "cnd_federal", {**base, "api_response": {MARCA_SEGUNDA_VIA: {"preferencia_emissao": "2via"}}},
            HOJE, 30,
        )
        sem = svc.montar_celula("cnd_federal", {**base, "api_response": {"code": 200}}, HOJE, 30)
        assert com["segunda_via"] is True and com["stale_para_contrato"] is True
        assert sem["segunda_via"] is False
        assert svc.montar_celula("cnd_federal", None, HOJE, 30)["segunda_via"] is False

    def test_na_pf_nao_tem_fgts_e_pj_nao_tem_serasa(self):
        linhas = svc.montar_linhas.__globals__["MATRIZ_LINHAS"]
        assert linhas  # the fixed 13
        pf = {"tipo_pessoa": "PF", "rotulo": "COMP 1", "lado": "comprador", "papel": "",
              "titular": True, "nome": "A", "documento": CPF, "cliente_id": "c",
              "empresa_id": None, "parte_id": None}
        pj = {**pf, "tipo_pessoa": "PJ", "cliente_id": None, "empresa_id": "e", "documento": CNPJ}
        linhas_fmt = [svc._linha(l) for l in linhas]
        col_pf = svc.montar_parte(pf, linhas_fmt, [], HOJE, 30)
        col_pj = svc.montar_parte(pj, linhas_fmt, [], HOJE, 30)
        assert col_pf["celulas"]["fgts_regularidade"]["status"] == "na"
        assert col_pj["celulas"]["serasa"]["status"] == "na"
        # 13 lines minus the one N/A each; all absent ⇒ pendente.
        assert col_pf["totais"] == {"nao_constam": 0, "constam": 0, "pendente": 12, "vencidas": 0}
        assert col_pj["totais"] == {"nao_constam": 0, "constam": 0, "pendente": 12, "vencidas": 0}

    def test_linhas_automatico_derivado_do_registry(self):
        automaticas = {l["tipo"] for l in map(svc._linha, svc.montar_linhas.__globals__["MATRIZ_LINHAS"])
                       if l["automatico"]}
        assert automaticas == {
            "cnd_federal", "trf3_sp", "trf3", "trt2_digital", "trt2_fisico",
            "cnd_trabalhista_tst", "cenprot", "cnd_fazenda_sp", "divida_ativa_sp",
        }
        manuais = {l["tipo"] for l in map(svc._linha, svc.montar_linhas.__globals__["MATRIZ_LINHAS"])
                   if not l["automatico"]}
        assert manuais == {"tjsp_esaj", "tjsp_eproc", "serasa", "fgts_regularidade"}

    def test_linha_customizada_nao_e_automatica_e_aparece_para_todas_as_partes(self, scoped):
        cid, aid, [vid] = _card(scoped)
        linha_id = str(uuid4())
        scoped.set_table_data("certidao_matriz_linhas_customizadas", [{
            "id": linha_id, "org_id": ORG_ID, "cliente_id": cid, "nome": "Foo", "ordem": 14,
            "excluida_em": None, "created_at": "2026-01-01T00:00:00+00:00",
        }])

        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)

        custom = out["linhas"][-1]
        assert (custom["custom"], custom["automatico"], custom["chave"]) == (True, False, linha_id)
        assert all(linha_id in p["celulas"] for p in out["partes"])
        assert out["partes"][0]["celulas"][linha_id]["status"] == "pendente"

    def test_a_certidao_segue_a_pessoa_entre_atendimentos(self, scoped):
        """Linked to the cliente via ANOTHER deal's parte (a stale
        `atendimento_parte_id`) — still shown here: selection is by party."""
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("certidao_consultas", [{
            **_consulta("c1", cliente_id=vid), "atendimento_parte_id": str(uuid4()),
        }])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="sucesso", resultado="negativa",
                       emitida_em=_dia(5)),
        ])

        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)

        vend = next(p for p in out["partes"] if p["rotulo"] == "VEND 1")
        cel = vend["celulas"]["cnd_federal"]
        assert (cel["status"], cel["idade_dias"], cel["stale_para_contrato"]) == (
            "nao_constam", 5, False,
        )
        assert vend["totais"]["nao_constam"] == 1

    def test_vencidas_conta_so_as_stale(self, scoped):
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c1", cliente_id=vid)])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="sucesso", resultado="negativa",
                       emitida_em=_dia(60)),
            _resultado("r2", "c1", "trf3", status="sucesso", resultado="negativa",
                       emitida_em=_dia(2)),
        ])
        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)
        vend = next(p for p in out["partes"] if p["rotulo"] == "VEND 1")
        assert vend["totais"]["vencidas"] == 1 and vend["totais"]["nao_constam"] == 2
        assert vend["celulas"]["cnd_federal"]["stale_para_contrato"] is True

    def test_consulta_excluida_nao_aparece(self, scoped):
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("certidao_consultas", [
            {**_consulta("c1", cliente_id=vid), "excluida_em": "2026-09-01T00:00:00+00:00"},
        ])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r1", "c1", "cnd_federal", status="sucesso", resultado="negativa"),
        ])
        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)
        vend = next(p for p in out["partes"] if p["rotulo"] == "VEND 1")
        assert vend["celulas"]["cnd_federal"]["resultado_id"] is None

    def test_ambiguo_e_200_vazio_com_as_13_linhas(self, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo")])
        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)
        assert out["atendimento_id"] is None and out["partes"] == []
        assert len(out["linhas"]) == 13 and all("automatico" in l for l in out["linhas"])

    def test_atendimento_explicito_de_outro_cliente_e_404(self, scoped):
        cid, aid, _ = _card(scoped)
        outro, outro_aid = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [*_dados(scoped, "clientes"), cliente_row(outro)])
        scoped.set_table_data("atendimentos", [
            *_dados(scoped, "atendimentos"), _atendimento(outro_aid, outro),
        ])
        with pytest.raises(AppException) as exc:
            svc.montar(scoped, ORG_ID, cid, atendimento_id=outro_aid, hoje=HOJE)
        assert exc.value.status_code == 404

    def test_cliente_desconhecido_e_404(self, scoped):
        _seed_tables(scoped)
        with pytest.raises(AppException) as exc:
            svc.montar(scoped, ORG_ID, str(uuid4()), hoje=HOJE)
        assert exc.value.status_code == 404


# ─── writes ───────────────────────────────────────────────────────────────


def _sem_credencial_faltando(_org):
    return []


class TestEmissao:
    def test_sem_tipos_emite_os_automaticos_sem_tjsp(self, scoped):
        cid, aid, [vid] = _card(scoped)
        out = svc.solicitar_emissao(
            scoped, ORG_ID, cid, "pessoa", vid, tipos=None, atendimento_id=None,
            user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
        )

        esperados = [c["tipo"] for c in CERTIDOES_CONFIG if c["tipo"] != "tjsp"]
        assert sorted(r["tipo"] for r in out["resultados"]) == sorted(esperados)
        assert all(r["status_processamento"] == "pendente" for r in out["resultados"])
        assert set(out) == {"consulta_id", "resultados"}
        [consulta] = _dados(scoped, "certidao_consultas")
        assert consulta["id"] == out["consulta_id"]
        assert (consulta["tipo_documento"], consulta["documento"]) == ("cpf", "00000000000")
        assert consulta["cliente_id"] == vid and consulta.get("empresa_id") is None
        assert consulta["status"] == "pendente" and consulta["total_certidoes"] == len(esperados)
        parte_id = next(p["id"] for p in _dados(scoped, "atendimento_partes"))
        assert consulta["atendimento_parte_id"] == parte_id
        assert len(_dados(scoped, "certidao_resultados")) == len(esperados)

    def test_titular_nao_tem_atendimento_parte_id_e_copia_dados_do_cliente(self, scoped):
        cid, aid, _ = _card(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular", cpf=CPF, data_nascimento="1980-02-03",
                        genero="F", rg="123", nome_mae="Mae"),
            *[r for r in _dados(scoped, "clientes") if r["id"] != cid],
        ])
        svc.solicitar_emissao(
            scoped, ORG_ID, cid, "pessoa", cid, tipos=["cnd_federal"], atendimento_id=None,
            user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
        )
        [c] = _dados(scoped, "certidao_consultas")
        assert c["cliente_id"] == cid and c.get("atendimento_parte_id") is None
        assert (c["data_nascimento"], c["genero"], c["rg"], c["nome_mae"]) == (
            "1980-02-03", "F", "123", "Mae",
        )
        assert c["total_certidoes"] == 1

    def test_parte_pj_gera_consulta_cnpj(self, scoped):
        cid, aid, _ = _card(scoped)
        emp = _empresa(cnpj=CNPJ, razao_social="Vende LTDA")
        scoped.set_table_data("empresas", [emp])
        scoped.set_table_data("atendimento_partes", [
            *_dados(scoped, "atendimento_partes"), _parte_pj(aid, emp["id"]),
        ])
        svc.solicitar_emissao(
            scoped, ORG_ID, cid, "empresa", emp["id"], tipos=["cnd_federal"], atendimento_id=None,
            user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
        )
        [c] = _dados(scoped, "certidao_consultas")
        assert (c["tipo_documento"], c["documento"], c["empresa_id"], c.get("cliente_id")) == (
            "cnpj", CNPJ, emp["id"], None,
        )
        assert c["atendimento_parte_id"]

    def test_nunca_muta_resultado_existente(self, scoped):
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c0", cliente_id=vid)])
        antigo = _resultado("r0", "c0", "cnd_federal", status="sucesso", resultado="negativa",
                            emitida_em="2026-06-23")
        scoped.set_table_data("certidao_resultados", [antigo])
        svc.solicitar_emissao(
            scoped, ORG_ID, cid, "pessoa", vid, tipos=["cnd_federal"], atendimento_id=None,
            user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
        )
        rows = {r["id"]: r for r in _dados(scoped, "certidao_resultados")}
        assert rows["r0"]["emitida_em"] == "2026-06-23" and rows["r0"]["status"] == "sucesso"
        assert len(rows) == 2

    @pytest.mark.parametrize("tipo,codigo,trecho", [
        ("serasa", "TIPO_NAO_AUTOMATICO", "Serasa é registrada manualmente — envie o PDF na célula."),
        ("tjsp_esaj", "TIPO_NAO_AUTOMATICO", "TJSP e-SAJ é registrada manualmente"),
        ("fgts_regularidade", "TIPO_NAO_AUTOMATICO", "é registrada manualmente"),
        ("outras_custom", "TIPO_NAO_AUTOMATICO", "é registrada manualmente"),
        ("nao_existe", "TIPO_INVALIDO", "Tipo de certidão inválido: nao_existe."),
    ])
    def test_tipos_invalidos_422_sem_escrita(self, scoped, tipo, codigo, trecho):
        cid, aid, [vid] = _card(scoped)
        with pytest.raises(AppException) as exc:
            svc.solicitar_emissao(
                scoped, ORG_ID, cid, "pessoa", vid, tipos=[tipo], atendimento_id=None,
                user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
            )
        assert (exc.value.status_code, exc.value.code) == (422, codigo)
        assert trecho in exc.value.message
        assert _dados(scoped, "certidao_consultas") == []

    def test_documento_ausente_422_sem_escrita(self, scoped):
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("clientes", [
            {**r, "cpf": None} if r["id"] == vid else r for r in _dados(scoped, "clientes")
        ])
        with pytest.raises(AppException) as exc:
            svc.solicitar_emissao(
                scoped, ORG_ID, cid, "pessoa", vid, tipos=None, atendimento_id=None,
                user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
            )
        assert (exc.value.status_code, exc.value.code) == (422, "DOCUMENTO_AUSENTE")
        assert exc.value.message == "Informe o CPF/CNPJ da parte antes de solicitar certidões."
        assert _dados(scoped, "certidao_consultas") == []

    def test_credenciais_faltando_422_antes_de_qualquer_escrita(self, scoped):
        cid, aid, [vid] = _card(scoped)
        with pytest.raises(AppException) as exc:
            svc.solicitar_emissao(
                scoped, ORG_ID, cid, "pessoa", vid, tipos=None, atendimento_id=None,
                user_id=str(uuid4()),
                check_credentials=lambda _o: ["Token InfoSimples ausente."],
            )
        assert exc.value.status_code == 422
        assert exc.value.message == "Token InfoSimples ausente. Configure em Configurações → Chaves de API."
        assert _dados(scoped, "certidao_consultas") == []

    def test_parte_de_fora_do_atendimento_404(self, scoped):
        cid, aid, _ = _card(scoped)
        with pytest.raises(AppException) as exc:
            svc.solicitar_emissao(
                scoped, ORG_ID, cid, "pessoa", str(uuid4()), tipos=None, atendimento_id=None,
                user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
            )
        assert exc.value.status_code == 404
        assert exc.value.message == "Parte não encontrada neste atendimento."

    def test_kind_invalido_404(self, scoped):
        cid, aid, [vid] = _card(scoped)
        with pytest.raises(AppException) as exc:
            svc.solicitar_emissao(
                scoped, ORG_ID, cid, "pessoas", vid, tipos=None, atendimento_id=None,
                user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
            )
        assert exc.value.status_code == 404

    def test_ambiguo_e_409(self, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo", cpf=CPF)])
        with pytest.raises(AmbiguousAtendimento) as exc:
            svc.solicitar_emissao(
                scoped, ORG_ID, cid, "pessoa", cid, tipos=None, atendimento_id=None,
                user_id=str(uuid4()), check_credentials=_sem_credencial_faltando,
            )
        assert exc.value.status_code == 409 and exc.value.code == "AMBIGUOUS_ATENDIMENTO"


class TestReemitir:
    def _com_cert(self, scoped, tipo="cnd_federal"):
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c0", cliente_id=vid)])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r0", "c0", tipo, status="sucesso", resultado="negativa",
                       emitida_em="2026-06-23"),
        ])
        return cid, vid

    def test_cria_nova_consulta_e_nao_toca_o_original(self, scoped):
        cid, vid = self._com_cert(scoped)
        out = svc.reemitir(
            scoped, ORG_ID, cid, "r0", user_id=str(uuid4()),
            check_credentials=_sem_credencial_faltando,
        )
        assert len(out["resultados"]) == 1 and out["resultados"][0]["tipo"] == "cnd_federal"
        novo = next(c for c in _dados(scoped, "certidao_consultas") if c["id"] == out["consulta_id"])
        assert novo["cliente_id"] == vid and novo["total_certidoes"] == 1
        original = next(r for r in _dados(scoped, "certidao_resultados") if r["id"] == "r0")
        assert original["emitida_em"] == "2026-06-23" and original["status"] == "sucesso"

    def test_tipo_manual_422(self, scoped):
        cid, vid = self._com_cert(scoped, tipo="serasa")
        with pytest.raises(AppException) as exc:
            svc.reemitir(scoped, ORG_ID, cid, "r0", user_id="u",
                         check_credentials=_sem_credencial_faltando)
        assert (exc.value.status_code, exc.value.code) == (422, "TIPO_NAO_AUTOMATICO")

    def test_resultado_de_parte_estranha_ao_card_404(self, scoped):
        cid, vid = self._com_cert(scoped)
        estranho = str(uuid4())
        scoped.set_table_data("clientes", [*_dados(scoped, "clientes"), cliente_row(estranho)])
        scoped.set_table_data("certidao_consultas", [
            *_dados(scoped, "certidao_consultas"), _consulta("c9", cliente_id=estranho),
        ])
        scoped.set_table_data("certidao_resultados", [
            *_dados(scoped, "certidao_resultados"),
            _resultado("r9", "c9", "cnd_federal", status="sucesso"),
        ])
        with pytest.raises(AppException) as exc:
            svc.reemitir(scoped, ORG_ID, cid, "r9", user_id="u",
                         check_credentials=_sem_credencial_faltando)
        assert exc.value.status_code == 404

    def test_resultado_inexistente_404(self, scoped):
        cid, vid = self._com_cert(scoped)
        with pytest.raises(AppException) as exc:
            svc.reemitir(scoped, ORG_ID, cid, str(uuid4()), user_id="u",
                         check_credentials=_sem_credencial_faltando)
        assert exc.value.status_code == 404


class TestGarantirCelula:
    def _args(self, cid, vid, chave, **over):
        return dict(kind="pessoa", alvo_id=vid, linha_chave=chave, atendimento_id=None,
                    user_id=str(uuid4()), **over)

    def test_celula_vazia_cria_placeholder_manual_201(self, scoped):
        cid, aid, [vid] = _card(scoped)
        body, criado = svc.garantir_celula(scoped, ORG_ID, cid, **self._args(cid, vid, "serasa"))
        assert criado is True and set(body) == {"resultado_id", "consulta_id", "criado"}
        assert body["criado"] is True
        [consulta] = _dados(scoped, "certidao_consultas")
        assert consulta["origem"] == "manual" and consulta["cliente_id"] == vid
        [resultado] = _dados(scoped, "certidao_resultados")
        assert (resultado["tipo"], resultado["status"]) == ("serasa", "pendente")
        # …and the very next read reports it as origem=manual so the FE stops polling.
        out = svc.montar(scoped, ORG_ID, cid, hoje=HOJE)
        vend = next(p for p in out["partes"] if p["rotulo"] == "VEND 1")
        assert vend["celulas"]["serasa"]["origem"] == "manual"
        assert vend["celulas"]["serasa"]["resultado_id"] == body["resultado_id"]

    def test_celula_existente_devolve_200_sem_criar(self, scoped):
        cid, aid, [vid] = _card(scoped)
        scoped.set_table_data("certidao_consultas", [_consulta("c0", cliente_id=vid)])
        scoped.set_table_data("certidao_resultados", [
            _resultado("r0", "c0", "cnd_federal", status="sucesso", emitida_em="2026-09-01"),
        ])
        body, criado = svc.garantir_celula(scoped, ORG_ID, cid, **self._args(cid, vid, "cnd_federal"))
        assert criado is False
        assert body == {"resultado_id": "r0", "consulta_id": "c0", "criado": False}
        assert len(_dados(scoped, "certidao_consultas")) == 1

    def test_celula_customizada(self, scoped):
        cid, aid, [vid] = _card(scoped)
        linha_id = str(uuid4())
        scoped.set_table_data("certidao_matriz_linhas_customizadas", [{
            "id": linha_id, "org_id": ORG_ID, "cliente_id": cid, "nome": "Foo", "ordem": 14,
            "excluida_em": None, "created_at": "2026-01-01T00:00:00+00:00",
        }])
        body, criado = svc.garantir_celula(scoped, ORG_ID, cid, **self._args(cid, vid, linha_id))
        assert criado is True
        [r] = _dados(scoped, "certidao_resultados")
        assert (r["tipo"], r["linha_customizada_id"], r["nome_display"]) == (
            "outras_custom", linha_id, "Outras: Foo",
        )

    @pytest.mark.parametrize("chave,kind", [("fgts_regularidade", "pessoa")])
    def test_combinacao_nao_aplicavel_422(self, scoped, chave, kind):
        cid, aid, [vid] = _card(scoped)
        with pytest.raises(AppException) as exc:
            svc.garantir_celula(scoped, ORG_ID, cid, **self._args(cid, vid, chave))
        assert (exc.value.status_code, exc.value.code) == (422, "CELULA_NAO_APLICAVEL")
        assert exc.value.message == "Esta certidão não se aplica a este tipo de parte."

    def test_serasa_em_pj_nao_aplicavel(self, scoped):
        cid, aid, _ = _card(scoped)
        emp = _empresa(cnpj=CNPJ)
        scoped.set_table_data("empresas", [emp])
        scoped.set_table_data("atendimento_partes", [
            *_dados(scoped, "atendimento_partes"), _parte_pj(aid, emp["id"]),
        ])
        with pytest.raises(AppException) as exc:
            svc.garantir_celula(
                scoped, ORG_ID, cid, kind="empresa", alvo_id=emp["id"], linha_chave="serasa",
                atendimento_id=None, user_id="u",
            )
        assert exc.value.code == "CELULA_NAO_APLICAVEL"

    def test_linha_desconhecida_422(self, scoped):
        cid, aid, [vid] = _card(scoped)
        with pytest.raises(AppException) as exc:
            svc.garantir_celula(scoped, ORG_ID, cid, **self._args(cid, vid, "nao-existe"))
        assert exc.value.status_code == 422
