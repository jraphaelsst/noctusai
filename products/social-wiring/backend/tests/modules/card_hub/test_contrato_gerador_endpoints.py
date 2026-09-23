"""F5 contract generator — the two routes over the mock DB, real loader.

WHAT THESE PIN
--------------
- GET .../geracao on a sparse card answers 200 with the contract shape and a
  NAMED faltando list, every item carrying a `destino` the UI can link to;
- a deleted contract, or one from another org, is a 404 on both routes;
- POST .../gerar refuses with 400 CONTRATO_INCOMPLETO carrying the same
  faltando the GET reported — nothing rendered, nothing saved;
- 🔴 a FULLY-seeded card GENERATES. Every value the instrument needs is read
  through the real services off real rows: the per-deal clauses (114), the
  confirmed título/ônus wording + the last compra e venda (115), certidões
  incl. the titular's (116), data_casamento + the office's operational
  settings (117), and the imóvel's own certidões (118);
- each of the 6 distinct variants of spec §1.3 generates end-to-end;
- `assinatura_data` precedence: the stored contract date beats "today", and an
  explicit date in the POST body beats both;
- the SAVED version is a real PDF (`%PDF-` magic bytes), `mime_type
  application/pdf`, a `.pdf` filename — AND (migration 120, 2026-09-16) the
  `.docx` the generator builds is ALSO saved, as a sibling artifact on the
  SAME version row (`docx_storage_path`), a real docx (`PK\x03\x04` zip
  magic bytes), never a second `numero`.

All data is synthetic (see `contrato_gerador_fixtures`).
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from app.modules.card_hub.contrato_gerador.deps import get_politica_contrato
from app.modules.card_hub.contrato_gerador.frases import CERTIDOES
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.card_hub.contrato_gerador.service import hoje
from app.modules.card_hub.deps import BUCKET
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.conftest import ORG_ID, cliente_row

_T0 = "2026-01-01T00:00:00+00:00"

#: [Owner directive, 2026-09-23] `derivacao.comarca_de_texto` reads the
#: RAW extraction text (`matricula_extracoes.texto_extraido`), never the
#: selected-acts quote — appended after `fx.MATRICULA_TEXTO` (never
#: inside it: `fx.MATRICULA_TEXTO`'s own exact shape is pinned byte-for-
#: byte elsewhere, `test_contrato_gerador.py`'s
#: `test_descricao_imovel_block_narrows_the_imovel_clause_when_present`).
#: `_imovel()`'s `texto_len` stays `len(fx.MATRICULA_TEXTO)` (the OLD,
#: shorter length) so the confirmed título aquisitivo quote keeps citing
#: only the R.1 sentence, never this suffix.
_MATRICULA_TEXTO_COM_COMARCA = (
    fx.MATRICULA_TEXTO + " Situado nesta cidade, município e comarca de Cidade Exemplo."
)

#: Every table the generator's loader reads. Seeded empty by `_seed_base` so a
#: sparse card exercises "nothing filled in" rather than an unknown table.
_TABELAS = (
    "atendimento_contrato_versoes", "atendimento_contrato_versao_acessos", "atendimento_partes",
    "cliente_membros", "lead_corretores", "atendimento_negociacao", "negociacao_defaults",
    "imovel_dados", "imovel_registry", "imoveis", "atendimento_negociacao_parcelas",
    "atendimento_favorecidos", "atendimento_intermediarios", "atendimento_financiamento",
    "atendimento_documentos", "certidao_consultas", "certidao_resultados",
    "atendimento_contrato_matricula_atos", "matricula_extracoes", "matricula_atos",
    "imovel_documento_acessos", "org_dados_cadastrais", "org_testemunhas",
    # Migrations 114-118.
    "atendimento_negociacao_termos", "atendimento_parcela_permuta_ativos", "permuta_ativos",
    "matricula_ato_detalhes", "imovel_documentos", "cliente_documentos",
)


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
        data_casamento=None,  # migration 117 — required only for a `casado`
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
        # Migration 114.
        "assinatura_data": None, "prazo_pendencias_dias": None,
        "created_at": _T0, "updated_at": None,
    }
    contrato.update(contrato_over or {})
    scoped.set_table_data("atendimento_contratos", [contrato])
    for tabela in _TABELAS:
        scoped.set_table_data(tabela, [])
    return ids


def _certidoes_de(nome: str, cpf_base: str, *, cliente_id: str, parte_id: str | None):
    """One concluded consulta + the full result set for one person.

    Relative to the office calendar: a certidão must be < 30 days old at the
    assinatura [Q10]. `parte_id=None` is the TITULAR's shape — migration 116
    links the consulta by `cliente_id`, which is the only way to reach them.
    """
    consulta_id = str(uuid4())
    emitida = hoje() - timedelta(days=5)
    consulta = {
        "id": consulta_id, "org_id": ORG_ID, "created_by": str(uuid4()), "tipo_documento": "cpf",
        "documento": fx.cpf_sintetico(cpf_base), "nome": nome, "status": "concluida",
        "total_certidoes": 12, "concluidas": 12, "cliente_id": cliente_id,
        "atendimento_parte_id": parte_id,
        # Migration 116 — irrelevant for a CPF consulta, present for shape.
        "situacao_cadastral": None, "data_situacao": None, "situacao_origem": None,
        "created_at": _T0, "updated_at": _T0,
    }
    resultados = [
        {"id": str(uuid4()), "consulta_id": consulta_id, "org_id": ORG_ID, "tipo": tipo,
         "nome_display": tipo, "ordem": i, "status": "sucesso", "numero": f"SIM-{i:04d}",
         "emitida_em": emitida.isoformat(),
         "validade_ate": (emitida + timedelta(days=90)).isoformat(), "resultado": "negativa",
         "created_at": _T0, "updated_at": _T0}
        for i, (tipo, *_r) in enumerate(CERTIDOES, start=1)
    ]
    return consulta, resultados


def _documento_estado_civil(cliente_id: str) -> dict:
    """[Q11 / migration 117] The estado-civil certidão's OWN emission date —
    `certidao_estado_civil_mais_recente` reads it off the document row."""
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cliente_id,
        "tipo_documento": "certidao_casamento", "deleted_at": None,
        "extracao_descartada_em": None,
        "extracao_data_emissao": (hoje() - timedelta(days=10)).isoformat(),
        "extracao_data_emissao_confianca": "alta", "extracao_data_emissao_rotulo": None,
        "created_at": _T0,
    }


def _matricula(scoped, ids: dict, *, codigo: str, texto: str, corte_em: str) -> dict:
    """An extraction + its abertura/R.1 acts, plus the R.1 act's typed details
    (migration 115) — which is what makes the última compra e venda readable."""
    extracao_id, abertura_id, r1_id = str(uuid4()), str(uuid4()), str(uuid4())
    corte = texto.index(corte_em)
    scoped.set_table_data("matricula_extracoes", _rows(scoped, "matricula_extracoes") + [{
        "id": extracao_id, "org_id": ORG_ID, "user_id": str(uuid4()), "nome_arquivo": "matricula.pdf",
        "texto_extraido": texto, "status": "concluida", "codigo": codigo,
        "formatacao": None, "created_at": _T0, "updated_at": _T0,
    }])
    scoped.set_table_data("matricula_atos", _rows(scoped, "matricula_atos") + [
        {"id": abertura_id, "org_id": ORG_ID, "extracao_id": extracao_id, "ordem": 0, "kind": "abertura",
         "numero": None, "char_inicio": 0, "char_fim": corte, "header_inicio": None, "header_fim": None, "created_at": _T0},
        {"id": r1_id, "org_id": ORG_ID, "extracao_id": extracao_id, "ordem": 1, "kind": "R",
         "numero": 1, "char_inicio": corte, "char_fim": len(texto), "header_inicio": None, "header_fim": None, "created_at": _T0},
    ])
    # [Q9] The last registered compra e venda, ≥ 5 years old — so no previous
    # owner's certidões are required (the fixtures' own posture).
    scoped.set_table_data("matricula_ato_detalhes", _rows(scoped, "matricula_ato_detalhes") + [{
        "id": str(uuid4()), "org_id": ORG_ID, "extracao_id": extracao_id, "ato_id": r1_id,
        "natureza": "compra_e_venda", "data_registro": "2020-01-10", "valor": None,
        "transmitentes": [{"nome": "Antiga Dona Exemplo", "cpf_cnpj": None}],
        "adquirentes": [{"nome": "Fulano de Tal", "cpf_cnpj": None}],
        "credor": None, "instrumento": None, "atos_referidos": [],
        "origem": "confirmado", "confirmado_por": None, "confirmado_em": _T0, "created_at": _T0,
    }])
    return {"extracao_id": extracao_id, "abertura_id": abertura_id, "r1_id": r1_id, "corte": corte}


def _imovel(scoped, *, codigo: str, empreendimento, logradouro: str, numero: str,
            complemento, matricula: str, inscricao: str, extracao_id: str, ato_id: str,
            corte: int, texto_len: int, onus: str = "livre", credor=None) -> None:
    scoped.set_table_data("imovel_registry", _rows(scoped, "imovel_registry") + [
        {"org_id": ORG_ID, "codigo_canonical": codigo, "ativo_no_vista": True}
    ])
    scoped.set_table_data("imoveis", _rows(scoped, "imoveis") + [{
        "org_id": ORG_ID, "codigo": codigo, "codigo_norm": codigo, "titulo": "Apartamento",
        "empreendimento": empreendimento, "logradouro": logradouro, "numero": numero,
        "complemento": complemento, "bairro": "Bairro Modelo", "cidade": "Cidade Exemplo",
        "uf": "SP", "cep": "01000000", "foto_destaque": None, "corretores": [],
    }])
    scoped.set_table_data("imovel_dados", _rows(scoped, "imovel_dados") + [{
        "org_id": ORG_ID, "codigo": codigo, "numero_matricula": matricula,
        "numero_registro_imoveis": "1º Oficial de Registro de Imóveis de Cidade Exemplo",
        "prefeitura_cadastro_imobiliario": inscricao, "captador_user_id": None,
        "situacao_onus": onus, "onus_observacoes": None,
        # The matrícula certidão's own emission date — inside [Q10]'s 30 days.
        "onus_certidao_em": (hoje() - timedelta(days=12)).isoformat(),
        "onus_documento_id": None, "titulo_aquisitivo_extracao_id": extracao_id,
        "titulo_aquisitivo_ato_id": ato_id, "titulo_aquisitivo_char_inicio": corte,
        "titulo_aquisitivo_char_fim": texto_len, "titulo_aquisitivo_origem": "manual",
        "titulo_aquisitivo_confirmado_por": None, "titulo_aquisitivo_confirmado_em": _T0,
        "onus_fonte_extracao_id": extracao_id if credor else None,
        "onus_fonte_atos": [{"ato_id": ato_id}] if credor else None,
        "onus_fonte_origem": "manual" if credor else None,
        # Migration 115 — the operator's CONFIRMED contract wording.
        "titulo_aquisitivo_texto": (
            "pela escritura pública lavrada aos 10 de janeiro de 2020 no 1º Tabelionato de "
            "Notas de Cidade Exemplo"
        ),
        "titulo_aquisitivo_texto_confirmado_por": None,
        "titulo_aquisitivo_texto_confirmado_em": _T0,
        "onus_credor": credor, "onus_credor_confirmado_por": None,
        "onus_credor_confirmado_em": _T0 if credor else None,
        "updated_at": _T0,
    }])


def _parcela_row(ids: dict, pid: str, tipo: str, valor: str, ordem: int, *, evento=None,
                 forma=None, fav=None, confissao=False, corretagem=False) -> dict:
    return {
        "id": pid, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "tipo": tipo,
        "valor": valor, "vencimento": None, "evento": evento, "forma_pagamento": forma,
        "favorecido_id": fav, "confissao_divida": confissao, "ordem": ordem,
        # Migration 114.
        "dispara_corretagem": corretagem,
        "created_at": _T0, "updated_at": None,
    }


def _termos_row(ids: dict, **over) -> dict:
    linha = {
        "atendimento_id": ids["atendimento"], "org_id": ORG_ID,
        "posse_prazo_dias": 30, "posse_marco": "parcela", "posse_marco_parcela_id": "p3",
        "permuta_posse_prazo_dias": None, "permuta_posse_marco": None,
        "permuta_posse_marco_parcela_id": None, "permuta_obrigacoes_entrega": None,
        "itens_integrantes": "armários planejados da cozinha e dos dormitórios.",
        # [Owner directive, 2026-09-23] `False` (unanswered) by default;
        # every variant below that nulls `itens_integrantes` also confirms
        # this, same tri-state shape `ad_corpus` already uses.
        "itens_integrantes_ausente_confirmado": False,
        "ad_corpus": False, "obrigacoes_vendedor": None,
        "onus_quitacao": None, "onus_prazo_dias": None,
        "confissao_juros_am": None, "confissao_garantia": None,
        "corretagem_contratantes": "vendedores", "corretagem_num_parcelas": 1,
        "created_at": _T0, "updated_at": None,
    }
    linha.update(over)
    return linha


def _seed_completo(scoped, n: int = 1) -> dict:
    """A card with EVERY value the instrument needs, shaped as spec §1.3's
    variant `n`. The same 6 combinations `contrato_gerador_fixtures` builds
    synthetically, here as real rows read through the real services."""
    ids = _seed_base(scoped)
    vendedor_id, parte_id = str(uuid4()), str(uuid4())
    permuta = n in (5, 6)

    scoped.set_table_data("clientes", _rows(scoped, "clientes") + [
        _qualificado(vendedor_id, "Fulano de Tal", "Masculino", "123456789", "11.111.111-1")
    ])
    scoped.set_table_data("atendimento_partes", [{
        "id": parte_id, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "cliente_id": vendedor_id,
        "lado": "vendedor", "papel": "proprietario", "ordem": 0, "observacao": None,
        "created_at": _T0, "created_by": None, "updated_at": None,
    }])

    # Certidões: the vendedor always; the TITULAR too in a permuta, where the
    # buyer side is certified as well (migration 116 reaches them by cliente_id).
    consultas, resultados = [], []
    consulta, res = _certidoes_de("Fulano de Tal", "123456789", cliente_id=vendedor_id, parte_id=parte_id)
    consultas.append(consulta)
    resultados += res
    if permuta:
        consulta, res = _certidoes_de(
            "Beltrana Exemplo", "987654321", cliente_id=ids["cliente"], parte_id=None
        )
        consultas.append(consulta)
        resultados += res
    scoped.set_table_data("certidao_consultas", consultas)
    scoped.set_table_data("certidao_resultados", resultados)
    scoped.set_table_data(
        "cliente_documentos",
        [_documento_estado_civil(vendedor_id), _documento_estado_civil(ids["cliente"])],
    )

    valor = "550000.00" if n == 5 else "500000.00"
    scoped.set_table_data("atendimento_negociacao", [{
        "atendimento_id": ids["atendimento"], "org_id": ORG_ID, "imovel_codigo": "EX001",
        "valor_negociado": valor, "pct_comissao": "6", "tem_parceria": False, "pct_parceria": "50",
        "pct_agencia": "50", "pct_agentes": "45", "pct_captador": "5", "formas_pagamento": None,
        "parcelas": None, "financiamento": n != 4, "fgts": n == 2, "observacoes": None,
        "posse_data": None, "posse_condicoes": None, "permuta_ativo_id": None,
        "created_at": _T0, "updated_at": None,
    }])

    objeto = _matricula(scoped, ids, codigo="EX001", texto=_MATRICULA_TEXTO_COM_COMARCA, corte_em="R.1/12.345")
    onus = "alienacao_fiduciaria" if n in (2, 4, 5) else "livre"
    credor = "Banco Credor Exemplo S.A." if onus != "livre" else None
    _imovel(
        scoped, codigo="EX001", empreendimento="Edifício Exemplo", logradouro="Rua Fictícia",
        numero="100", complemento="Apto 11", matricula="12345", inscricao="000.000.0000-0",
        extracao_id=objeto["extracao_id"], ato_id=objeto["r1_id"], corte=objeto["corte"],
        texto_len=len(fx.MATRICULA_TEXTO), onus=onus, credor=credor,
    )
    selecao = [
        {"id": str(uuid4()), "org_id": ORG_ID, "contrato_id": ids["contrato"],
         "extracao_id": objeto["extracao_id"], "ato_id": ato, "ordem": ordem,
         "papel": "objeto", "permuta_ativo_id": None, "selecionado_por": None, "created_at": _T0}
        for ordem, ato in ((1, objeto["abertura_id"]), (2, objeto["r1_id"]))
    ]

    fav_v, fav_org, int_id = str(uuid4()), str(uuid4()), str(uuid4())
    scoped.set_table_data("atendimento_favorecidos", [
        {"id": fav_v, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "nome": "Fulano de Tal",
         "cpf_cnpj": fx.cpf_sintetico("123456789"), "banco": "Banco Exemplo", "agencia": "0001",
         "conta": "12345-6", "pix": None, "created_at": _T0, "updated_at": None},
        {"id": fav_org, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
         "nome": "Imobiliária Exemplo Ltda", "cpf_cnpj": "11222333000181", "banco": "Banco Exemplo",
         "agencia": "0002", "conta": "65432-1", "pix": None,
         "created_at": "2026-01-02T00:00:00+00:00", "updated_at": None},
    ])

    # ── the per-variant schedule + clauses (spec §1.3) ──
    termos_extra: dict = {}
    if n == 4:
        parcelas = [
            _parcela_row(ids, "p1", "sinal", "100000.00", 1, evento="no ato da assinatura do presente instrumento",
                         forma="PIX", fav=fav_v, corretagem=True),
            _parcela_row(ids, "p2", "saldo", "400000.00", 2,
                         evento="mediante boleto emitido pelo credor, na data da escritura",
                         forma="Boleto", fav=fav_v),
        ]
        termos_extra = {"posse_marco": "assinatura", "posse_marco_parcela_id": None,
                        "onus_quitacao": "parcela"}
    elif n == 5:
        parcelas = [
            _parcela_row(ids, "p1", "sinal", "50000.00", 1, evento="no ato da assinatura do presente instrumento",
                         forma="PIX", fav=fav_v, corretagem=True),
            _parcela_row(ids, "p3", "financiamento", "250000.00", 2, evento="na liberação do financiamento"),
            _parcela_row(ids, "p5", "direta", "50000.00", 3, forma="PIX", fav=fav_v, confissao=True),
            _parcela_row(ids, "p6", "direta", "50000.00", 4, forma="PIX", fav=fav_v, confissao=True),
            _parcela_row(ids, "p-permuta", "permuta", "150000.00", 5),
        ]
        parcelas[2]["vencimento"] = "2027-01-10"
        parcelas[3]["vencimento"] = "2027-02-10"
        termos_extra = {"itens_integrantes": None, "itens_integrantes_ausente_confirmado": True,
                        "confissao_juros_am": "1",
                        "onus_quitacao": "compradores_prazo", "onus_prazo_dias": 30}
    elif n == 6:
        parcelas = [
            _parcela_row(ids, "p1", "sinal", "50000.00", 1, evento="no ato da assinatura do presente instrumento",
                         forma="PIX", fav=fav_v, corretagem=True),
            _parcela_row(ids, "p2", "intermediaria", "50000.00", 2, evento="na assinatura do financiamento",
                         forma="Transferência", fav=fav_v),
            _parcela_row(ids, "p3", "financiamento", "300000.00", 3, evento="na liberação do financiamento"),
            _parcela_row(ids, "p-permuta", "permuta", "100000.00", 4),
        ]
        termos_extra = {"itens_integrantes": None, "itens_integrantes_ausente_confirmado": True, "ad_corpus": True}
    else:
        parcelas = [
            _parcela_row(ids, "p1", "sinal", "50000.00", 1, evento="no ato da assinatura do presente instrumento",
                         forma="PIX", fav=fav_v, corretagem=True),
            _parcela_row(ids, "p2", "intermediaria", "50000.00", 2, evento="na assinatura do financiamento",
                         forma="Transferência", fav=fav_v),
            _parcela_row(ids, "p3", "financiamento", "400000.00", 3,
                         evento="com prazo máximo de pagamento de 90 (noventa) dias corridos, a contar da assinatura do presente instrumento"),
        ]
        if n == 2:
            termos_extra = {"onus_quitacao": "interveniente_quitante"}
        elif n == 3:
            termos_extra = {"itens_integrantes": None, "itens_integrantes_ausente_confirmado": True, "ad_corpus": True}
    scoped.set_table_data("atendimento_negociacao_parcelas", parcelas)

    # ── permuta: the parcela's ativo, its imóvel, and its own matrícula quote ──
    if permuta:
        ativo_id = str(uuid4())
        scoped.set_table_data("permuta_ativos", [{
            "id": ativo_id, "org_id": ORG_ID, "natureza": "permuta_imovel", "imovel_codigo": "EX002",
            "codigo": "PM0001", "corretor_id": None, "proprietario_nome": "Beltrana Exemplo",
            "proprietario_telefone": None, "proprietario_email": None, "tipo_imovel": "casa",
            "cep": "01000000", "logradouro": "Avenida Amostra", "numero": "5", "complemento": None,
            "bairro": "Bairro Modelo", "cidade": "Cidade Exemplo", "uf": "SP", "zona": None,
            "condominio_nome": None, "valor": "150000.00", "created_at": _T0,
        }])
        scoped.set_table_data("atendimento_parcela_permuta_ativos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "parcela_id": "p-permuta",
            "permuta_ativo_id": ativo_id, "created_at": _T0, "created_por": None,
        }])
        troca = _matricula(
            scoped, ids, codigo="EX002", texto=fx.MATRICULA_PERMUTA_TEXTO, corte_em="A casa situada"
        )
        _imovel(
            scoped, codigo="EX002", empreendimento=None, logradouro="Avenida Amostra", numero="5",
            complemento=None, matricula="54321", inscricao="111.111.1111-1",
            extracao_id=troca["extracao_id"], ato_id=troca["r1_id"], corte=troca["corte"],
            texto_len=len(fx.MATRICULA_PERMUTA_TEXTO),
        )
        # Migration 115's `papel`/`permuta_ativo_id`: THIS is the per-imóvel
        # act role — the quote belongs to the ativo, not to the deal at large.
        selecao.append({
            "id": str(uuid4()), "org_id": ORG_ID, "contrato_id": ids["contrato"],
            "extracao_id": troca["extracao_id"], "ato_id": troca["r1_id"], "ordem": 3,
            "papel": "permuta", "permuta_ativo_id": ativo_id, "selecionado_por": None,
            "created_at": _T0,
        })
        termos_extra.update(permuta_posse_prazo_dias=60, permuta_posse_marco="assinatura")
        ids["permuta_ativo"] = ativo_id
    scoped.set_table_data("atendimento_contrato_matricula_atos", selecao)
    scoped.set_table_data("atendimento_negociacao_termos", [_termos_row(ids, **termos_extra)])

    # V5/V6 have no intermediação clause at all (spec §1.3).
    intermediarios = [] if permuta else [{
        "id": int_id, "org_id": ORG_ID, "atendimento_id": ids["atendimento"], "corretor_id": str(uuid4()),
        "nome": "Corretor Exemplo", "creci": "000001-F", "tipo": "percentual", "valor": "6",
        # Migration 114 — the favorecido link + PF/PJ qualification.
        "favorecido_id": fav_org, "pessoa_tipo": None, "documento": None, "email": None,
        "endereco_cep": None, "endereco_logradouro": None, "endereco_numero": None,
        "endereco_complemento": None, "endereco_bairro": None, "endereco_cidade": None,
        "endereco_uf": None, "representante_nome": None, "representante_cpf": None,
        "created_at": _T0, "updated_at": None,
    }]
    scoped.set_table_data("atendimento_intermediarios", intermediarios)

    scoped.set_table_data("atendimento_financiamento", [] if n == 4 else [{
        "atendimento_id": ids["atendimento"], "org_id": ORG_ID, "situacao": "aprovado",
        "situacao_em": None, "situacao_motivo": None, "fgts": n == 2, "observacoes": None,
        "agente_financeiro_id": None, "numero_proposta": None, "created_at": _T0, "updated_at": None,
    }])

    scoped.set_table_data("org_dados_cadastrais", [{
        "org_id": ORG_ID, "razao_social": "Imobiliária Exemplo Ltda", "nome_fantasia": None,
        "cnpj": "11222333000181", "creci_pj": "00001-J", "responsavel_nome": "Sicrano Responsável",
        "responsavel_creci": "000002-F", "telefone": None, "email": "contato@exemplo.test",
        "endereco_cep": "01000000", "endereco_logradouro": "Rua das Amostras", "endereco_numero": "200",
        "endereco_complemento": None, "endereco_bairro": "Bairro Teste", "endereco_cidade": "Cidade Exemplo",
        "endereco_uf": "SP",
        # Migration 117 — the office's operational answers.
        "plataforma_assinatura_nome": "Plataforma Exemplo",
        "plataforma_assinatura_url": "https://assinatura.exemplo.test",
        "posse_multa_diaria": "500.00", "prazo_pendencias_padrao_dias": 10,
        "updated_at": _T0,
    }])
    scoped.set_table_data("org_testemunhas", [
        # [Owner directive, 2026-09-23] e-mail now blocks readiness (see
        # `derivacao._imobiliaria`) for a digital contract.
        {"id": str(uuid4()), "org_id": ORG_ID, "nome": nome, "cpf": fx.cpf_sintetico(base), "rg": rg,
         "email": email, "created_at": _T0, "updated_at": None}
        for nome, rg, base, email in (
            ("Testemunha Um", "33.333.333-3", "321654987", "testemunha.um@exemplo.test"),
            ("Testemunha Dois", "44.444.444-4", "456789123", "testemunha.dois@exemplo.test"),
        )
    ])
    ids.update(fav_org=fav_org, fav_vendedor=fav_v, intermediario=int_id,
               vendedor=vendedor_id, parte_vendedor=parte_id)
    return ids


@pytest.fixture
def politica_declaracao(client):
    """[Q1] V6's Declaração das Partes, through the policy DI seam — the same
    parameter production passes, never a patch."""
    from app.main import app

    def ligar() -> None:
        app.dependency_overrides[get_politica_contrato] = lambda: replace(
            POLITICA_PADRAO, tem_declaracao_partes=True
        )

    yield ligar
    app.dependency_overrides.pop(get_politica_contrato, None)


def _url(ids: dict, sufixo: str) -> str:
    return f"/api/clientes/{ids['cliente']}/contratos/{ids['contrato']}/{sufixo}"


def _contrato_over(scoped, ids: dict, **campos) -> None:
    linha = {**_rows(scoped, "atendimento_contratos")[0], **campos}
    scoped.set_table_data("atendimento_contratos", [linha])


class TestGeracao:
    def test_a_sparse_card_reports_named_missing_fields(self, client, scoped):
        ids = _seed_base(scoped)
        r = client.get(_url(ids, "geracao"), headers=_auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"contrato_id", "pronto", "modelo_derivado", "modelo_confere",
                             "modelo_automatico", "processo_legado", "modalidade_assinatura",
                             "switches", "faltando", "bloqueios", "avisos"}
        # Migration 157 — a contract row with no stored modalidade is digital.
        assert body["modalidade_assinatura"] == "digital"
        assert body["contrato_id"] == ids["contrato"] and body["pronto"] is False
        # No parcelas is UNKNOWN, never "à vista" by absence.
        assert body["switches"]["a_vista"] is False
        assert body["modelo_derivado"] == "compra_venda" and body["modelo_confere"] is True
        # An uploaded contract's modelo is the user's label — only flagged.
        assert body["modelo_automatico"] is False
        # Migration 151 — never true unless an admin explicitly set it.
        assert body["processo_legado"] is False
        campos = {f["campo"] for f in body["faltando"]}
        assert {"partes.vendedores", "negociacao.imovel", "negociacao.valor_negociado",
                "negociacao.parcelas", "negociacao.posse_prazo_dias", "imobiliaria.razao_social",
                "imobiliaria.testemunhas", "imobiliaria.plataforma_assinatura"} <= campos
        for f in body["faltando"]:
            assert set(f) == {"campo", "rotulo", "onde", "parte_id", "destino", "sugestoes"}

    def test_every_missing_field_says_which_screen_fixes_it(self, client, scoped):
        """The `destino` contract the readiness UI links from."""
        ids = _seed_base(scoped)
        body = client.get(_url(ids, "geracao"), headers=_auth()).json()
        por_campo = {f["campo"]: f["destino"] for f in body["faltando"]}

        assert por_campo["imobiliaria.plataforma_assinatura"] == {
            "tela": "configuracoes",
            "rota": "/configuracoes",
            "ancora": "imobiliaria",
            "ids": {"contrato_id": ids["contrato"], "cliente_id": ids["cliente"]},
        }
        assert por_campo["partes.vendedores"]["ancora"] == "vendedor"
        assert por_campo["negociacao.posse_prazo_dias"]["tela"] == "card_negociacao"
        for destino in por_campo.values():
            assert set(destino) == {"tela", "rota", "ancora", "ids"}
            assert destino["rota"].startswith("/")

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
        assert _rows(scoped, "atendimento_contrato_versoes") == []

    def test_a_fully_seeded_card_is_ready(self, client, scoped, fake_storage):
        """🔴 The whole point of the F6 wiring: nothing is `faltando` once the
        office has filled the forms migrations 114-118 added."""
        ids = _seed_completo(scoped)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["faltando"] == [], geracao["faltando"]
        assert geracao["bloqueios"] == [], geracao["bloqueios"]
        assert geracao["pronto"] is True
        assert geracao["modelo_derivado"] == "compra_venda" and geracao["modelo_confere"] is True

    def test_a_ready_contract_is_saved_as_a_generated_version(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["pronto"] is True, (geracao["faltando"], geracao["bloqueios"])

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["versao"]["origem"] == "gerado"
        assert body["versao"]["numero"] == 1
        # [Owner directive, 2026-09-23] Several formerly-guaranteed avisos on
        # this exact fixture (missing profissão, RG==CPF, witness e-mail,
        # itens integrantes, ad corpus, the imóvel-city foro) all became
        # blocking `faltando` or were removed outright — a fully-answered
        # card can legitimately carry ZERO avisos now. This only asserts the
        # response shape, not that this particular card produces one.
        assert isinstance(body["avisos"], list)

        versoes = _rows(scoped, "atendimento_contrato_versoes")
        assert len(versoes) == 1 and versoes[0]["origem"] == "gerado"
        assert re.fullmatch(r"[0-9a-f]{64}", versoes[0]["contexto_sha256"])
        assert versoes[0]["tamanho_bytes"] > 0
        # The primary artifact is a real PDF, never `.docx` mime/extension
        # (contract §5).
        assert versoes[0]["mime_type"] == "application/pdf"
        assert versoes[0]["nome_original"].endswith(".pdf")
        assert not versoes[0]["nome_original"].endswith(".docx")
        blob = asyncio.run(fake_storage.get(bucket=BUCKET, key=versoes[0]["storage_path"]))
        assert blob is not None and blob.data[:5] == b"%PDF-"
        assert body["versao"]["mime_type"] == "application/pdf"

        # The editable `.docx` is ALSO stored, as a sibling artifact on the
        # SAME version row — migration 120, 2026-09-16.
        assert body["versao"]["docx_disponivel"] is True
        assert versoes[0]["docx_storage_path"] == f"{versoes[0]['storage_path']}.docx"
        assert versoes[0]["docx_tamanho_bytes"] > 0
        docx_blob = asyncio.run(
            fake_storage.get(bucket=BUCKET, key=versoes[0]["docx_storage_path"])
        )
        assert docx_blob is not None and docx_blob.data[:4] == b"PK\x03\x04"

        assert any(a["acao"] == "text_view" for a in _rows(scoped, "imovel_documento_acessos"))

        listagem = client.get(f"/api/clientes/{ids['cliente']}/contratos", headers=_auth()).json()
        assert listagem["contratos"][0]["versao_atual"]["origem"] == "gerado"

    def test_a_character_the_pdf_font_cannot_represent_is_a_refusal_not_a_500(
        self, client, scoped, fake_storage
    ):
        # `render_abnt_pdf` (seed) raises `UnsupportedGlyphError` for a
        # character the core Times font's WinAnsiEncoding cannot represent;
        # `service.gerar` maps it to `ContratoPdfNaoGerado` (422) — never a
        # silent 500 (contract §5).
        ids = _seed_completo(scoped)
        testemunhas = _rows(scoped, "org_testemunhas")
        testemunhas[0] = {**testemunhas[0], "nome": "Testemunha 🏠 Um"}
        scoped.set_table_data("org_testemunhas", testemunhas)

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())

        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "CONTRATO_PDF_NAO_GERADO"
        assert _rows(scoped, "atendimento_contrato_versoes") == []


class TestVariantes:
    """🔴 THE END-TO-END PROOF: one FULL card per distinct variant of spec
    §1.3, seeded as real rows, generating a real PDF with no bloqueios."""

    MODELO = {
        1: "compra_venda",
        2: "compra_venda",
        3: "compra_venda",
        4: "compra_venda_a_vista",
        5: "compra_venda_permuta",
        6: "compra_venda_permuta",
    }

    @pytest.mark.parametrize("n", range(1, 7))
    def test_each_variant_generates_end_to_end(
        self, client, scoped, fake_storage, politica_declaracao, n
    ):
        if n == 6:
            politica_declaracao()
        ids = _seed_completo(scoped, n)

        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["faltando"] == [], (n, geracao["faltando"])
        assert geracao["bloqueios"] == [], (n, geracao["bloqueios"])
        assert geracao["pronto"] is True
        assert geracao["modelo_derivado"] == self.MODELO[n]

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, (n, r.text)

        versoes = _rows(scoped, "atendimento_contrato_versoes")
        assert len(versoes) == 1
        assert versoes[0]["mime_type"] == "application/pdf"
        blob = asyncio.run(fake_storage.get(bucket=BUCKET, key=versoes[0]["storage_path"]))
        assert blob is not None and blob.data[:5] == b"%PDF-"

    @pytest.mark.parametrize("n", [5, 6])
    def test_a_permuta_variant_quotes_the_exchanged_imovels_own_matricula(
        self, client, scoped, fake_storage, n
    ):
        """[§6.1 #2, #3] The permuta parcela's ativo carries its OWN matrícula
        quote (`papel='permuta'`), so the clause describes the right property."""
        ids = _seed_completo(scoped, n)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["pronto"] is True, (geracao["faltando"], geracao["bloqueios"])
        assert geracao["switches"]["tem_permuta"] is True


class TestModalidadeAssinatura:
    """Migration 157 — the generated VERSION records which modalidade it was
    rendered with, so "Baixar para impressão" only offers a física rendering."""

    @pytest.mark.parametrize("modalidade", ["digital", "fisica"])
    def test_the_version_carries_the_modalidade_it_was_rendered_with(
        self, client, scoped, fake_storage, modalidade
    ):
        ids = _seed_completo(scoped)
        _contrato_over(scoped, ids, modalidade_assinatura=modalidade)

        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["modalidade_assinatura"] == modalidade
        assert geracao["switches"]["tem_assinatura_digital"] is (modalidade == "digital")

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        assert r.json()["versao"]["modalidade_assinatura"] == modalidade
        assert _rows(scoped, "atendimento_contrato_versoes")[0]["modalidade_assinatura"] == modalidade

        contrato = client.get(f"/api/clientes/{ids['cliente']}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["modalidade_assinatura"] == modalidade
        assert contrato["versao_atual"]["modalidade_assinatura"] == modalidade


class TestAssinaturaData:
    """Migration 114's stored signing date, and who wins."""

    def test_the_stored_contract_date_beats_today(self, client, scoped, fake_storage):
        # Certidões were emitted 5 days ago; dating the instrument 40 days back
        # puts them AFTER the assinatura — a bloqueio that can only appear if
        # the stored date is what the gate measured against.
        ids = _seed_completo(scoped)
        _contrato_over(scoped, ids, assinatura_data=(hoje() - timedelta(days=40)).isoformat())

        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["pronto"] is False
        assert "CERTIDAO_EMITIDA_APOS_ASSINATURA" in {b["codigo"] for b in geracao["bloqueios"]}

    def test_an_explicit_body_date_beats_the_stored_one(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        _contrato_over(scoped, ids, assinatura_data=(hoje() - timedelta(days=40)).isoformat())

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        assert len(_rows(scoped, "atendimento_contrato_versoes")) == 1

    def test_the_contract_prazo_overrides_the_office_default(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        _contrato_over(scoped, ids, prazo_pendencias_dias=0)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert "PRAZO_PENDENCIAS_INVALIDO" in {b["codigo"] for b in geracao["bloqueios"]}


class TestIniciar:
    """POST /contratos/gerar — the card's "Gerar contrato" button."""

    def _iniciar(self, client, ids: dict):
        return client.post(f"/api/clientes/{ids['cliente']}/contratos/gerar", headers=_auth())

    def test_it_creates_a_generated_draft_with_no_version_and_its_readiness(self, client, scoped, fake_storage):
        ids = _seed_base(scoped)
        r = self._iniciar(client, ids)
        assert r.status_code == 201, r.text
        body = r.json()
        contrato, geracao = body["contrato"], body["geracao"]

        novo = [c for c in _rows(scoped, "atendimento_contratos") if c["id"] == contrato["id"]]
        assert len(novo) == 1
        assert novo[0]["origem"] == "gerado" and novo[0]["status"] == "rascunho"
        assert novo[0]["atendimento_id"] == ids["atendimento"]
        assert contrato["versoes"] == [] and contrato["versao_atual"] is None
        assert _rows(scoped, "atendimento_contrato_versoes") == []

        # The modelo is the DERIVED one, so the generator never opens on a
        # "modelo diverge" warning — and a sparse card derives the generic
        # compra e venda, never "à vista" by absence of parcelas.
        assert contrato["modelo"] == novo[0]["modelo"] == "compra_venda"
        assert geracao["contrato_id"] == contrato["id"]
        assert geracao["modelo_confere"] is True
        assert geracao["modelo_automatico"] is True
        assert geracao["pronto"] is False and geracao["faltando"]

    def test_on_a_complete_card_only_the_per_contract_selection_is_missing(self, client, scoped, fake_storage):
        """The matrícula acts are chosen PER CONTRACT — a new contract has
        none yet. [Owner directive, 2026-09-23] the comarca derivation
        (`derivacao.comarca_de_texto`) also has nothing to read yet: this
        seed's matrícula never went through the imóvel-page upload flow
        `estrutura_service._extracao_padrao_do_imovel` resolves against, so
        a brand-new contract's `obter_selecao` finds no default extraction
        either — the readiness report names BOTH gaps."""
        ids = _seed_completo(scoped)
        body = self._iniciar(client, ids).json()
        assert body["contrato"]["modelo"] == "compra_venda"
        assert {f["campo"] for f in body["geracao"]["faltando"]} == {
            "matricula.atos", "negociacao.foro_comarca",
        }

    def test_a_card_with_no_open_atendimento_is_refused_and_writes_nothing(self, client, scoped, fake_storage):
        """Same `cliente_id` resolution every contratos route inherits: no
        atendimento in this org -> 409 AMBIGUOUS_ATENDIMENTO, before any write."""
        _seed_base(scoped)
        antes = _rows(scoped, "atendimento_contratos")
        r = client.post(f"/api/clientes/{uuid4()}/contratos/gerar", headers=_auth())
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "AMBIGUOUS_ATENDIMENTO"
        assert _rows(scoped, "atendimento_contratos") == antes

    def test_a_second_click_reuses_the_unrendered_draft_instead_of_duplicating_it(
        self, client, scoped, fake_storage
    ):
        """🔴 [2026-09-22] The bug behind RODRIGO MORASCHI ENRIQUEZ's 5 empty
        prod drafts: re-clicking "Gerar contrato" before ever rendering must
        leave exactly ONE `origem='gerado'` row, not one per click."""
        ids = _seed_base(scoped)
        r1 = self._iniciar(client, ids)
        assert r1.status_code == 201, r1.text
        contrato_id_1 = r1.json()["contrato"]["id"]

        r2 = self._iniciar(client, ids)
        assert r2.status_code == 200, r2.text
        contrato_id_2 = r2.json()["contrato"]["id"]

        assert contrato_id_1 == contrato_id_2
        gerados = [
            c for c in _rows(scoped, "atendimento_contratos")
            if c["origem"] == "gerado" and c["atendimento_id"] == ids["atendimento"]
        ]
        assert len(gerados) == 1
        assert gerados[0]["id"] == contrato_id_1

    def test_a_click_after_a_real_version_exists_starts_a_new_draft(
        self, client, scoped, fake_storage
    ):
        """Once the reused draft actually renders (a real version lands),
        the NEXT click must not silently keep filling the now-rendered
        contract — it starts a fresh one, same as the very first click."""
        ids = _seed_completo(scoped)
        primeiro = self._iniciar(client, ids).json()["contrato"]["id"]

        # The matrícula-act selection is PER CONTRACT by design (`iniciar`
        # never copies it) — mirror `_seed_completo`'s seeded selection
        # (keyed to `ids["contrato"]`) onto the new draft so it is "pronto"
        # and `.../gerar` below can actually succeed.
        selecao_base = _rows(scoped, "atendimento_contrato_matricula_atos")
        extra = [
            {**linha, "id": str(uuid4()), "contrato_id": primeiro}
            for linha in selecao_base if linha["contrato_id"] == ids["contrato"]
        ]
        scoped.set_table_data(
            "atendimento_contrato_matricula_atos", selecao_base + extra
        )

        r = client.post(
            _url({"cliente": ids["cliente"], "contrato": primeiro}, "gerar"),
            json={"assinatura_data": hoje().isoformat()},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text

        r2 = self._iniciar(client, ids)
        assert r2.status_code == 201, r2.text
        assert r2.json()["contrato"]["id"] != primeiro
        gerados = [
            c for c in _rows(scoped, "atendimento_contratos")
            if c["origem"] == "gerado" and c["atendimento_id"] == ids["atendimento"]
        ]
        assert len(gerados) == 2


class TestModeloDeContratoGerado:
    """A 'gerado' contract's modelo follows the data; an upload's never does."""

    def test_generating_syncs_a_generated_contracts_modelo(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        _contrato_over(scoped, ids, origem="gerado", modelo="compra_venda_a_vista")
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["modelo_confere"] is False and geracao["modelo_automatico"] is True

        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        assert _rows(scoped, "atendimento_contratos")[0]["modelo"] == "compra_venda"

    def test_generating_never_overrides_an_uploaded_contracts_modelo(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        _contrato_over(scoped, ids, modelo="compra_venda_a_vista")
        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        assert _rows(scoped, "atendimento_contratos")[0]["modelo"] == "compra_venda_a_vista"

    def test_a_person_without_official_name_is_labelled_by_the_card_name(self, client, scoped):
        ids = _seed_base(scoped)
        titular = _rows(scoped, "clientes")[0]
        scoped.set_table_data("clientes", [{**titular, "nome": "Beltrana do Card", "nome_oficial": None}])
        body = client.get(_url(ids, "geracao"), headers=_auth()).json()
        rotulos = [f["rotulo"] for f in body["faltando"]] + [a["mensagem"] for a in body["avisos"]]
        assert any("Beltrana do Card (sem nome oficial)" in r for r in rotulos), rotulos
        assert not any(r.endswith("— (sem nome oficial)") for r in rotulos), rotulos
