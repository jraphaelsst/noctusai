"""F5 contract generator — the two routes over the mock DB, real loader.

WHAT THESE PIN
--------------
- GET .../geracao on a sparse card answers 200 with the contract shape and a
  NAMED faltando list (production passes no §6.1 complementos);
- a deleted contract, or one from another org, is a 404 on both routes;
- POST .../gerar refuses with 400 CONTRATO_INCOMPLETO carrying the same
  faltando the GET reported — nothing rendered, nothing saved;
- a fully-seeded card (complementos injected through the DI seam) is read
  through the real services and saved as a version with origem='gerado' and a
  64-hex `contexto_sha256`, and the matrícula text read is access-logged.

All data is synthetic (see `contrato_gerador_fixtures`).
"""
from __future__ import annotations

import re
from uuid import uuid4

import pytest

from app.modules.card_hub.contrato_gerador.deps import get_complementos_contrato
from app.modules.card_hub.contrato_gerador.frases import CERTIDOES
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

_T0 = "2026-01-01T00:00:00+00:00"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _rows(scoped, tabela: str) -> list[dict]:
    """Read-side introspection, same shape `test_contratos.py` uses."""
    return scoped.table(tabela).select("*").execute().data or []


def _qualificado(cid: str, nome: str, genero: str, cpf_base: str, rg: str) -> dict:
    return cliente_row(
        cid,
        nome=nome,
        nome_completo=nome,
        nome_oficial=nome,
        nacionalidade="Brasileiro(a)",
        genero=genero,
        estado_civil="solteiro",
        regime_bens=None,
        conjuge_cliente_id=None,
        profissao="Analista",
        cpf=fx.cpf_sintetico(cpf_base),
        rg=rg,
        rg_orgao_expedidor="SSP/SP",
        email=f"{cid[:8]}@exemplo.test",
        endereco_cep="01000000",
        endereco_logradouro="Rua das Amostras",
        endereco_numero="10",
        endereco_complemento=None,
        endereco_bairro="Bairro Teste",
        endereco_cidade="Cidade Exemplo",
        endereco_uf="SP",
    )


def _seed_base(scoped, *, contrato_over=None) -> dict:
    ids = {"cliente": str(uuid4()), "atendimento": str(uuid4()), "contrato": str(uuid4())}
    scoped.set_table_data("clientes", [_qualificado(ids["cliente"], "Beltrana Exemplo", "Feminino", "987654321", "22.222.222-2")])
    scoped.set_table_data("atendimentos", [{
        "id": ids["atendimento"], "org_id": ORG_ID, "cliente_id": ids["cliente"], "lead_id": None,
        "meta_ads_lead_id": None, "status": "aberta", "substituida_por": None, "arquivado": False,
        "titulo": "Compra do apto", "created_at": _T0, "closed_at": None,
    }])
    contrato = {
        "id": ids["contrato"], "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
        "titulo": "Promessa de compra e venda", "modelo": "compra_venda", "status": "rascunho",
        "status_em": None, "status_por": None, "origem": "upload", "criado_por": None,
        "deleted_at": None, "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": _T0, "updated_at": None,
    }
    contrato.update(contrato_over or {})
    scoped.set_table_data("atendimento_contratos", [contrato])
    for tabela in (
        "atendimento_contrato_versoes", "atendimento_contrato_versao_acessos", "atendimento_partes",
        "cliente_membros", "lead_corretores", "atendimento_negociacao", "negociacao_defaults",
        "imovel_dados", "imovel_registry", "imoveis", "atendimento_negociacao_parcelas",
        "atendimento_favorecidos", "atendimento_intermediarios", "atendimento_financiamento",
        "atendimento_documentos", "certidao_consultas", "certidao_resultados",
        "atendimento_contrato_matricula_atos", "matricula_extracoes", "matricula_atos",
        "imovel_documento_acessos", "org_dados_cadastrais", "org_testemunhas",
    ):
        scoped.set_table_data(tabela, [])
    return ids


def _seed_completo(scoped) -> dict:
    ids = _seed_base(scoped)
    vendedor_id, parte_id, consulta_id = str(uuid4()), str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", _rows(scoped,"clientes") + [
        _qualificado(vendedor_id, "Fulano de Tal", "Masculino", "123456789", "11.111.111-1")
    ])
    scoped.set_table_data("atendimento_partes", [{
        "id": parte_id, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "cliente_id": vendedor_id,
        "lado": "vendedor", "papel": "proprietario", "ordem": 0, "observacao": None,
        "created_at": _T0, "created_by": None, "updated_at": None,
    }])
    scoped.set_table_data("certidao_consultas", [{
        "id": consulta_id, "org_id": ORG_ID, "created_by": str(uuid4()), "tipo_documento": "cpf",
        "documento": fx.cpf_sintetico("123456789"), "nome": "Fulano de Tal", "status": "concluida",
        "total_certidoes": 12, "concluidas": 12, "cliente_id": vendedor_id,
        "atendimento_parte_id": parte_id, "created_at": _T0, "updated_at": _T0,
    }])
    scoped.set_table_data("certidao_resultados", [
        {"id": str(uuid4()), "consulta_id": consulta_id, "org_id": ORG_ID, "tipo": tipo, "nome_display": tipo,
         "ordem": i, "status": "sucesso", "numero": f"SIM-{i:04d}", "emitida_em": "2026-09-01",
         "validade_ate": "2026-12-01", "resultado": "negativa", "created_at": _T0, "updated_at": _T0}
        for i, (tipo, *_r) in enumerate(CERTIDOES, start=1)
    ])

    scoped.set_table_data("atendimento_negociacao", [{
        "atendimento_id": ids["atendimento"], "org_id": ORG_ID, "imovel_codigo": "EX001",
        "valor_negociado": "500000.00", "pct_comissao": "6", "tem_parceria": False, "pct_parceria": "50",
        "pct_agencia": "50", "pct_agentes": "45", "pct_captador": "5", "formas_pagamento": None,
        "parcelas": None, "financiamento": True, "fgts": False, "observacoes": None, "posse_data": None,
        "posse_condicoes": None, "permuta_ativo_id": None, "created_at": _T0, "updated_at": None,
    }])
    scoped.set_table_data("imovel_registry", [{"org_id": ORG_ID, "codigo_canonical": "EX001", "ativo_no_vista": True}])
    scoped.set_table_data("imoveis", [{
        "org_id": ORG_ID, "codigo": "EX001", "codigo_norm": "EX001", "titulo": "Apartamento",
        "empreendimento": "Edifício Exemplo", "logradouro": "Rua Fictícia", "numero": "100",
        "complemento": "Apto 11", "bairro": "Bairro Modelo", "cidade": "Cidade Exemplo", "uf": "SP",
        "cep": "01000000", "foto_destaque": None, "corretores": [],
    }])

    extracao_id, abertura_id, r1_id = str(uuid4()), str(uuid4()), str(uuid4())
    texto = fx.MATRICULA_TEXTO
    corte = texto.index("R.1/12.345")
    scoped.set_table_data("matricula_extracoes", [{
        "id": extracao_id, "org_id": ORG_ID, "user_id": str(uuid4()), "nome_arquivo": "matricula.pdf",
        "texto_extraido": texto, "status": "concluida", "codigo": "EX001", "created_at": _T0, "updated_at": _T0,
    }])
    scoped.set_table_data("matricula_atos", [
        {"id": abertura_id, "org_id": ORG_ID, "extracao_id": extracao_id, "ordem": 0, "kind": "abertura",
         "numero": None, "char_inicio": 0, "char_fim": corte, "header_inicio": None, "header_fim": None, "created_at": _T0},
        {"id": r1_id, "org_id": ORG_ID, "extracao_id": extracao_id, "ordem": 1, "kind": "R",
         "numero": 1, "char_inicio": corte, "char_fim": len(texto), "header_inicio": None, "header_fim": None, "created_at": _T0},
    ])
    scoped.set_table_data("atendimento_contrato_matricula_atos", [
        {"id": str(uuid4()), "org_id": ORG_ID, "contrato_id": ids["contrato"], "extracao_id": extracao_id,
         "ato_id": ato, "ordem": ordem, "selecionado_por": None, "created_at": _T0}
        for ordem, ato in ((1, abertura_id), (2, r1_id))
    ])
    scoped.set_table_data("imovel_dados", [{
        "org_id": ORG_ID, "codigo": "EX001", "numero_matricula": "12345",
        "numero_registro_imoveis": "1º Oficial de Registro de Imóveis de Cidade Exemplo",
        "prefeitura_cadastro_imobiliario": "000.000.0000-0", "captador_user_id": None,
        "situacao_onus": "livre", "onus_observacoes": None, "onus_certidao_em": "2026-09-02",
        "onus_documento_id": None, "titulo_aquisitivo_extracao_id": extracao_id,
        "titulo_aquisitivo_ato_id": r1_id, "titulo_aquisitivo_char_inicio": corte,
        "titulo_aquisitivo_char_fim": len(texto), "titulo_aquisitivo_origem": "manual",
        "titulo_aquisitivo_confirmado_por": None, "titulo_aquisitivo_confirmado_em": _T0,
        "onus_fonte_extracao_id": None, "onus_fonte_atos": None, "onus_fonte_origem": None,
        "updated_at": _T0,
    }])

    fav_v, fav_org, int_id = str(uuid4()), str(uuid4()), str(uuid4())
    scoped.set_table_data("atendimento_favorecidos", [
        {"id": fav_v, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "nome": "Fulano de Tal",
         "cpf_cnpj": fx.cpf_sintetico("123456789"), "banco": "Banco Exemplo", "agencia": "0001",
         "conta": "12345-6", "pix": None, "created_at": _T0, "updated_at": None},
        {"id": fav_org, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "nome": "Imobiliária Exemplo Ltda",
         "cpf_cnpj": "11222333000181", "banco": "Banco Exemplo", "agencia": "0002", "conta": "65432-1",
         "pix": None, "created_at": "2026-01-02T00:00:00+00:00", "updated_at": None},
    ])
    scoped.set_table_data("atendimento_negociacao_parcelas", [
        {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "tipo": tipo, "valor": valor,
         "vencimento": None, "evento": evento, "forma_pagamento": forma, "favorecido_id": fav,
         "confissao_divida": False, "ordem": ordem, "created_at": _T0, "updated_at": None}
        for ordem, tipo, valor, evento, forma, fav in (
            (1, "sinal", "50000.00", "no ato da assinatura do presente instrumento", "PIX", fav_v),
            (2, "intermediaria", "50000.00", "na assinatura do financiamento", "Transferência", fav_v),
            (3, "financiamento", "400000.00", "na liberação do financiamento", None, None),
        )
    ])
    scoped.set_table_data("atendimento_intermediarios", [{
        "id": int_id, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "corretor_id": str(uuid4()),
        "nome": "Corretor Exemplo", "creci": "000001-F", "tipo": "percentual", "valor": "6",
        "created_at": _T0, "updated_at": None,
    }])
    scoped.set_table_data("atendimento_financiamento", [{
        "atendimento_id": ids["atendimento"], "org_id": ORG_ID, "situacao": "aprovado", "situacao_em": None,
        "situacao_motivo": None, "fgts": False, "observacoes": None, "agente_financeiro_id": None,
        "numero_proposta": None, "created_at": _T0, "updated_at": None,
    }])
    scoped.set_table_data("org_dados_cadastrais", [{
        "org_id": ORG_ID, "razao_social": "Imobiliária Exemplo Ltda", "nome_fantasia": None,
        "cnpj": "11222333000181", "creci_pj": "00001-J", "responsavel_nome": "Sicrano Responsável",
        "responsavel_creci": "000002-F", "telefone": None, "email": "contato@exemplo.test",
        "endereco_cep": "01000000", "endereco_logradouro": "Rua das Amostras", "endereco_numero": "200",
        "endereco_complemento": None, "endereco_bairro": "Bairro Teste", "endereco_cidade": "Cidade Exemplo",
        "endereco_uf": "SP", "updated_at": _T0,
    }])
    scoped.set_table_data("org_testemunhas", [
        {"id": str(uuid4()), "org_id": ORG_ID, "nome": nome, "cpf": None, "rg": rg, "created_at": _T0, "updated_at": None}
        for nome, rg in (("Testemunha Um", "33.333.333-3"), ("Testemunha Dois", "44.444.444-4"))
    ])
    ids.update(fav_org=fav_org, intermediario=int_id)
    return ids


@pytest.fixture
def complementos_injetados(client):
    from dataclasses import replace

    from app.main import app

    estado: dict = {}

    def definir(intermediario_id: str, favorecido_id: str) -> None:
        comp = replace(
            fx._complementos_base(),
            corretagem_favorecidos={intermediario_id: favorecido_id},
        )
        app.dependency_overrides[get_complementos_contrato] = lambda: comp
        estado["on"] = True

    yield definir
    app.dependency_overrides.pop(get_complementos_contrato, None)


def _url(ids: dict, sufixo: str) -> str:
    return f"/api/clientes/{ids['cliente']}/contratos/{ids['contrato']}/{sufixo}"


class TestGeracao:
    def test_a_sparse_card_reports_named_missing_fields(self, client, scoped):
        ids = _seed_base(scoped)
        r = client.get(_url(ids, "geracao"), headers=_auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"contrato_id", "pronto", "modelo_derivado", "modelo_confere", "switches",
                             "faltando", "bloqueios", "avisos"}
        assert body["contrato_id"] == ids["contrato"] and body["pronto"] is False
        assert body["modelo_derivado"] == "compra_venda_a_vista" and body["modelo_confere"] is False
        campos = {f["campo"] for f in body["faltando"]}
        assert {"partes.vendedores", "negociacao.imovel", "negociacao.valor_negociado",
                "negociacao.parcelas", "contrato.posse_prazo_dias", "imobiliaria.razao_social",
                "imobiliaria.testemunhas", "imobiliaria.plataforma_assinatura"} <= campos
        for f in body["faltando"]:
            assert set(f) == {"campo", "rotulo", "onde", "parte_id"}

    @pytest.mark.parametrize("sufixo, metodo", [("geracao", "get"), ("gerar", "post")])
    def test_deleted_contract_is_404(self, client, scoped, sufixo, metodo):
        ids = _seed_base(scoped, contrato_over={"deleted_at": _T0})
        kwargs = {"json": {}} if metodo == "post" else {}
        r = getattr(client, metodo)(_url(ids, sufixo), headers=_auth(), **kwargs)
        assert r.status_code == 404, r.text

    @pytest.mark.parametrize("sufixo, metodo", [("geracao", "get"), ("gerar", "post")])
    def test_another_orgs_contract_is_404(self, client, scoped, sufixo, metodo):
        ids = _seed_base(scoped, contrato_over={"org_id": str(uuid4())})
        kwargs = {"json": {}} if metodo == "post" else {}
        r = getattr(client, metodo)(_url(ids, sufixo), headers=_auth(), **kwargs)
        assert r.status_code == 404, r.text


class TestGerar:
    def test_an_incomplete_contract_is_refused_with_the_same_missing_list(self, client, scoped, fake_storage):
        ids = _seed_base(scoped)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        r = client.post(_url(ids, "gerar"), json={}, headers=_auth())
        assert r.status_code == 400, r.text
        erro = r.json()["error"]
        assert erro["code"] == "CONTRATO_INCOMPLETO"
        assert [f["campo"] for f in erro["details"]["faltando"]] == [f["campo"] for f in geracao["faltando"]]
        assert _rows(scoped,"atendimento_contrato_versoes") == []

    def test_a_ready_contract_is_saved_as_a_generated_version(
        self, client, scoped, fake_storage, complementos_injetados
    ):
        ids = _seed_completo(scoped)
        complementos_injetados(ids["intermediario"], ids["fav_org"])

        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["pronto"] is True, (geracao["faltando"], geracao["bloqueios"])

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": "2026-09-14"}, headers=_auth())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["versao"]["origem"] == "gerado"
        assert body["versao"]["numero"] == 1
        assert isinstance(body["avisos"], list) and body["avisos"]

        versoes = _rows(scoped,"atendimento_contrato_versoes")
        assert len(versoes) == 1 and versoes[0]["origem"] == "gerado"
        assert re.fullmatch(r"[0-9a-f]{64}", versoes[0]["contexto_sha256"])
        assert versoes[0]["tamanho_bytes"] > 0
        assert versoes[0]["mime_type"].endswith("wordprocessingml.document")
        assert any(a["acao"] == "text_view" for a in _rows(scoped,"imovel_documento_acessos"))

        listagem = client.get(f"/api/clientes/{ids['cliente']}/contratos", headers=_auth()).json()
        assert listagem["contratos"][0]["versao_atual"]["origem"] == "gerado"
