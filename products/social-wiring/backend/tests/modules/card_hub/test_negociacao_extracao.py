"""Negociação/financiamento document extraction — S2 contract
`sw-negociacao-extracao-contract.md` §E1-E3/§E5.

WHAT THESE PIN
--------------
- Fill-empty for `valor_negociado` / the financiamento parcela / `fgts` /
  `numero_proposta` / `agente_financeiro_id` / `situacao`; a DISAGREEING
  later reading opens exactly one `atendimento_campo_conflitos` row per
  field, never a silent overwrite (H2/H6).
- `documento_de_outro_negocio` applies NOTHING when the document reads at
  least one valid CPF and none match a deal party.
- `>=2` financiamento parcelas -> `aviso='varias_parcelas_financiamento'`,
  no write at all.
- An exception inside `aplicar_leitura` ends `extrair` in `erro`, NEVER a
  false `ok` (lesson G6).
- A human PATCH stamps `origem='manual'`, confirmed-by-construction.
- H4: the derived intermediária suggestion only appears once a
  financiamento parcela exists, is `origem='derivado'`, and is never
  recreated over a human-typed one.
- H5: the Quadro Resumo's seller credit account fills a favorecido matched
  to a vendedor by CPF.
- H7: an unmatched bank code auto-creates `agentes_financeiros`
  (`origem='auto'`).

Auth is not re-tested here — `test_auth_boundary.py`'s generic sweep
asserts a strict 401 on every mounted route, including the ones this file
adds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence
from uuid import uuid4

import pytest

from app.dependencies import coerce_org_uuid
from app.modules.card_hub import negociacao_extracao_service as nx
from app.modules.card_hub import negociacao_estruturada_service as neg_estruturada
from app.services import extracao_retentativa, table_reads
from noctusai_lib.integrations.storage import FakeStorageBackend

from tests.modules.card_hub.conftest import ORG_ID, cliente_row

ORG_UUID = coerce_org_uuid(ORG_ID) if isinstance(ORG_ID, str) else ORG_ID


def _t(scoped, name: str):
    return table_reads.table(scoped, name)


# ─── duck-typed `leitura` fakes (S1 shape, per the coordinator's handoff) ──


@dataclass(frozen=True)
class _Pessoa:
    nome: Optional[str] = None
    cpf: Optional[str] = None
    cpf_valido: bool = False


@dataclass(frozen=True)
class _ContaCreditoVendedor:
    banco_nome: Optional[str] = None
    banco_codigo: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None
    titular_cpf: Optional[str] = None
    titular_cpf_valido: bool = False


@dataclass(frozen=True)
class _GuiaItbiLeitura:
    valor_transacao: Optional[Decimal] = None
    compradores: Sequence[_Pessoa] = field(default_factory=tuple)
    vendedores: Sequence[_Pessoa] = field(default_factory=tuple)
    confiancas: Mapping[str, str] = field(default_factory=dict)
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None
    source: Optional[str] = "vision"


@dataclass(frozen=True)
class _FinanciamentoLeitura:
    documento: str = "contrato"
    banco_nome: Optional[str] = None
    banco_codigo: Optional[str] = None
    numero_proposta: Optional[str] = None
    valor_compra_venda: Optional[Decimal] = None
    valor_financiado: Optional[Decimal] = None
    valor_fgts: Optional[Decimal] = None
    conta_credito_vendedor: Optional[_ContaCreditoVendedor] = None
    quadro_encontrado: bool = False
    compradores: Sequence[_Pessoa] = field(default_factory=tuple)
    vendedores: Sequence[_Pessoa] = field(default_factory=tuple)
    confiancas: Mapping[str, str] = field(default_factory=dict)
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None
    source: Optional[str] = "vision"


CPF_COMPRADOR = "39053344705"  # valid check-digit
CPF_VENDEDOR = "11144477735"  # valid check-digit


# ─── seed helpers ──────────────────────────────────────────────────────────


def _atendimento(aid: str, cliente_id: str, **over) -> dict:
    row = {
        "id": aid, "org_id": ORG_ID, "cliente_id": cliente_id,
        "lead_id": None, "meta_ads_lead_id": None, "status": "aberta",
        "substituida_por": None, "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }
    row.update(over)
    return row


def _documento(doc_id: str, aid: str, tipo: str, **over) -> dict:
    row = {
        "id": doc_id, "org_id": ORG_ID, "atendimento_id": aid,
        "storage_path": f"{ORG_ID}/atendimentos/{aid}/{doc_id}",
        "nome_original": "arquivo.pdf", "mime_type": "application/pdf",
        "tamanho_bytes": 100, "tipo_documento": tipo,
        "categoria_lgpd": "financeiro", "retencao_ate": None,
        "extracao_status": "pendente", "extracao_em": None, "extracao_fonte": None,
        "extracao_erro": None, "extracao_tentativas": 0,
        "extracao_descartada_em": None, "extracao_descartada_por": None,
        "extracao_dados": None, "extracao_aviso": None,
        "enviado_por": None, "deleted_at": None, "delete_motivo": None,
        "delete_solicitado_por": None, "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(over)
    return row


def _seed(
    scoped, *, aid=None, com_negociacao=False, negociacao_over=None,
    com_vendedor=False, parcelas=None, financiamento=None, favorecidos=None,
    agentes=None,
):
    cid, aid = str(uuid4()), (aid or str(uuid4()))
    clientes = [cliente_row(cid, nome="Comprador", cpf=CPF_COMPRADOR)]
    partes = []
    if com_vendedor:
        vid = str(uuid4())
        clientes.append(cliente_row(vid, nome="Vendedor", cpf=CPF_VENDEDOR))
        partes.append(
            {
                "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
                "cliente_id": vid, "lado": "vendedor", "papel": "proprietario",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
    scoped.set_table_data("clientes", clientes)
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_partes", partes)
    negociacao_row = None
    if com_negociacao:
        negociacao_row = {
            "atendimento_id": aid, "org_id": ORG_ID, "imovel_codigo": None,
            "valor_negociado": "500000.00", "valor_negociado_origem": "manual",
            "valor_negociado_documento_id": None,
            "valor_negociado_em": "2026-01-01T00:00:00+00:00",
            "valor_negociado_confirmado_por": None,
            "valor_negociado_confirmado_em": "2026-01-01T00:00:00+00:00",
            "pct_comissao": "6", "tem_parceria": False, "pct_parceria": "50",
            "pct_agencia": "50", "pct_agentes": "45", "pct_captador": "5",
            "formas_pagamento": None, "parcelas": None, "financiamento": False,
            "fgts": False, "observacoes": None, "posse_data": None,
            "posse_condicoes": None, "permuta_ativo_id": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
        }
        if negociacao_over:
            negociacao_row.update(negociacao_over)
    scoped.set_table_data("atendimento_negociacao", [negociacao_row] if negociacao_row else [])
    scoped.set_table_data("negociacao_defaults", [])
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("atendimento_negociacao_parcelas", parcelas or [])
    scoped.set_table_data("atendimento_financiamento", [financiamento] if financiamento else [])
    scoped.set_table_data("atendimento_favorecidos", favorecidos or [])
    scoped.set_table_data("atendimento_campo_conflitos", [])
    scoped.set_table_data("agentes_financeiros", agentes or [])
    scoped.set_table_data("cliente_membros", [])
    scoped.set_table_data("lead_corretores", [])
    return cid, aid


def _financiamento_row(aid: str, **over) -> dict:
    row = {
        "atendimento_id": aid, "org_id": ORG_ID, "situacao": "pendente",
        "situacao_em": None, "situacao_por": None, "situacao_motivo": None,
        "situacao_origem": None, "situacao_documento_id": None,
        "situacao_confirmado_por": None, "situacao_confirmado_em": None,
        "fgts": False, "fgts_origem": None, "fgts_documento_id": None,
        "fgts_em": None, "fgts_confirmado_por": None, "fgts_confirmado_em": None,
        "numero_proposta": None, "numero_proposta_origem": None,
        "numero_proposta_documento_id": None, "numero_proposta_em": None,
        "numero_proposta_confirmado_por": None, "numero_proposta_confirmado_em": None,
        "agente_financeiro_id": None, "agente_financeiro_origem": None,
        "agente_financeiro_documento_id": None, "agente_financeiro_em": None,
        "agente_financeiro_confirmado_por": None, "agente_financeiro_confirmado_em": None,
        "observacoes": None, "created_at": "2026-01-01T00:00:00+00:00",
        "created_por": None, "updated_at": None, "updated_por": None,
    }
    row.update(over)
    return row


def _parcela_row(aid: str, tipo: str, valor=None, **over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
        "tipo": tipo, "valor": valor, "vencimento": None, "evento": None,
        "forma_pagamento": None, "favorecido_id": None,
        "confissao_divida": False, "dispara_corretagem": False, "ordem": 0,
        "origem": None, "documento_id": None, "extraido_em": None,
        "confirmado_por": None, "confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "created_por": None,
        "updated_at": None,
    }
    row.update(over)
    return row


# ─── (b) belongs-to-this-deal ───────────────────────────────────────────


class TestBelongsToThisDeal:
    def test_no_matching_cpf_applies_nothing(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])

        leitura = _GuiaItbiLeitura(
            valor_transacao=Decimal("500000.00"),
            compradores=[_Pessoa(cpf="00000000000", cpf_valido=True)],
        )
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        assert resultado["status"] == nx.SEM_DADOS
        assert resultado["aviso"] == "documento_de_outro_negocio"
        negociacao = _t(scoped, "atendimento_negociacao").select("*").execute().data
        assert negociacao == []

    def test_no_cpf_read_at_all_is_inconclusive_not_blocked(self, scoped):
        """No valid CPF on the document -> the apply still runs (mirrors
        `aplicar_cartao`'s own `if leitura.cnpj and ...` conditional)."""
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])

        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("500000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        assert resultado["status"] == nx.OK
        negociacao = _t(scoped, "atendimento_negociacao").select("*").execute().data
        assert negociacao[0]["valor_negociado"] == "500000.00"


# ─── H2: valor_negociado — fill-empty, else conflict ────────────────────


class TestValorNegociado:
    def test_fills_an_empty_value(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])

        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("500000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        assert resultado["status"] == nx.OK
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado"] == "500000.00"
        assert row["valor_negociado_origem"] == "guia_itbi"
        assert row["valor_negociado_documento_id"] == doc_id
        assert row["valor_negociado_confirmado_em"] is None

    def test_a_differing_later_reading_opens_a_conflict_never_overwrites(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )

        leitura = _FinanciamentoLeitura(valor_compra_venda=Decimal("480000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        # Untouched — H2: no source is authoritative.
        assert row["valor_negociado"] == "500000.00"
        assert len(resultado["conflitos"]) == 1
        conflito = resultado["conflitos"][0]
        assert conflito["campo"] == "valor_negociado"
        assert conflito["valor_anterior"] == "500000.00"
        assert conflito["valor_proposto"] == "480000.00"
        assert conflito["origem_proposto"] == "contrato_financiamento"

        pendentes = (
            _t(scoped, "atendimento_campo_conflitos").select("*")
            .eq("status", "pendente").execute().data
        )
        assert len(pendentes) == 1

    def test_same_value_is_a_no_op(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])

        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("500000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        assert resultado["conflitos"] == []
        pendentes = _t(scoped, "atendimento_campo_conflitos").select("*").execute().data
        assert pendentes == []


# ─── financiamento parcela — [Q6] financiado + FGTS ──────────────────────


class TestFinanciamentoParcela:
    def test_no_parcela_creates_one(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )

        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("400000.00"), valor_fgts=Decimal("20000.00"),
        )
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        parcelas = (
            _t(scoped, "atendimento_negociacao_parcelas")
            .select("*").eq("tipo", "financiamento").execute().data
        )
        assert len(parcelas) == 1
        assert parcelas[0]["valor"] == "420000.00"
        assert parcelas[0]["origem"] == "contrato_financiamento"
        assert parcelas[0]["documento_id"] == doc_id

    def test_a_null_valor_parcela_fills(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            parcelas=[_parcela_row(aid, "financiamento", valor=None)],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_financiado=Decimal("400000.00"))
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura)

        parcela = (
            _t(scoped, "atendimento_negociacao_parcelas").select("*")
            .eq("tipo", "financiamento").execute().data[0]
        )
        assert parcela["valor"] == "400000.00"

    def test_a_differing_parcela_valor_opens_a_conflict(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            parcelas=[_parcela_row(aid, "financiamento", valor="400000.00", origem="manual")],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_financiado=Decimal("390000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        parcela = (
            _t(scoped, "atendimento_negociacao_parcelas").select("*")
            .eq("tipo", "financiamento").execute().data[0]
        )
        assert parcela["valor"] == "400000.00"  # untouched
        assert len(resultado["conflitos"]) == 1
        assert resultado["conflitos"][0]["campo"].startswith("parcela.")

    def test_two_or_more_existing_parcelas_get_an_aviso_and_no_write(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            parcelas=[
                _parcela_row(aid, "financiamento", valor="100000.00"),
                _parcela_row(aid, "financiamento", valor="200000.00"),
            ],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_financiado=Decimal("400000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "varias_parcelas_financiamento" in (resultado["aviso"] or "")
        parcelas = (
            _t(scoped, "atendimento_negociacao_parcelas").select("*")
            .eq("tipo", "financiamento").execute().data
        )
        assert sorted(p["valor"] for p in parcelas) == ["100000.00", "200000.00"]


# ─── fgts — fill-empty judged by *_origem, never the boolean ────────────


class TestFgts:
    def test_fills_when_origem_is_unset(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_fgts=Decimal("15000.00"))
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["fgts"] is True
        assert row["fgts_origem"] == "contrato_financiamento"

    def test_a_false_boolean_with_origem_set_disagrees_and_conflicts(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            financiamento=_financiamento_row(aid, fgts=False, fgts_origem="manual"),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_fgts=Decimal("15000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["fgts"] is False  # untouched
        assert any(c["campo"] == "financiamento.fgts" for c in resultado["conflitos"])


# ─── H6 — situacao aprovado, one-way, never overrides recusado ─────────


class TestSituacaoAprovada:
    def test_quadro_encontrado_fills_pendente_to_aprovado(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(quadro_encontrado=True)
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["situacao"] == "aprovado"
        assert row["situacao_origem"] == "contrato_financiamento"

    def test_never_overrides_recusado_opens_a_conflict_instead(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            financiamento=_financiamento_row(
                aid, situacao="recusado", situacao_origem="manual",
            ),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(quadro_encontrado=True)
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["situacao"] == "recusado"  # untouched
        assert any(c["campo"] == "financiamento.situacao" for c in resultado["conflitos"])

    def test_no_quadro_found_does_nothing(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(quadro_encontrado=False)
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )
        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["situacao"] == "pendente"
        assert resultado["conflitos"] == []


# ─── H7 — auto-create the agentes_financeiros row ───────────────────────


class TestAgenteFinanceiro:
    def test_unmatched_bank_code_auto_creates_the_registry_row(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        leitura = _FinanciamentoLeitura(banco_nome="Itaú", banco_codigo="341")
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura)

        agentes = _t(scoped, "agentes_financeiros").select("*").execute().data
        assert len(agentes) == 1
        assert agentes[0]["codigo_banco"] == "341"
        assert agentes[0]["origem"] == "auto"

        financiamento = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert financiamento["agente_financeiro_id"] == agentes[0]["id"]
        assert financiamento["agente_financeiro_origem"] == "proposta_financiamento"

    def test_exactly_one_active_match_fills_without_creating(self, scoped):
        agente_id = str(uuid4())
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
            agentes=[
                {
                    "id": agente_id, "org_id": ORG_ID, "nome": "Caixa",
                    "codigo_banco": "104", "ativo": True, "origem": "manual",
                    "agencia": None, "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        leitura = _FinanciamentoLeitura(banco_codigo="104")
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura)

        agentes = _t(scoped, "agentes_financeiros").select("*").execute().data
        assert len(agentes) == 1  # no second row created
        financiamento = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert financiamento["agente_financeiro_id"] == agente_id


# ─── H5 — favorecido bank data from the Quadro Resumo ───────────────────


class TestFavorecidoVendedor:
    def test_fills_a_new_favorecido_matched_by_cpf(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True, com_vendedor=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        conta = _ContaCreditoVendedor(
            banco_nome="Bradesco", agencia="1234", conta="56789-0",
            titular_cpf=CPF_VENDEDOR, titular_cpf_valido=True,
        )
        leitura = _FinanciamentoLeitura(conta_credito_vendedor=conta)
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        favorecidos = _t(scoped, "atendimento_favorecidos").select("*").execute().data
        assert len(favorecidos) == 1
        assert favorecidos[0]["banco"] == "Bradesco"
        assert favorecidos[0]["cpf_cnpj"] == CPF_VENDEDOR
        assert favorecidos[0]["origem"] == "contrato_financiamento"

    def test_an_invalid_cpf_never_matches(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True, com_vendedor=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        conta = _ContaCreditoVendedor(
            banco_nome="Bradesco", titular_cpf=CPF_VENDEDOR, titular_cpf_valido=False,
        )
        leitura = _FinanciamentoLeitura(conta_credito_vendedor=conta)
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        assert _t(scoped, "atendimento_favorecidos").select("*").execute().data == []


# ─── H4 — the derived intermediária suggestion ──────────────────────────


class TestIntermediariaDerivada:
    def test_offered_once_a_financiamento_parcela_exists(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_financiado=Decimal("400000.00"))
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        intermediarias = (
            _t(scoped, "atendimento_negociacao_parcelas").select("*")
            .eq("tipo", "intermediaria").execute().data
        )
        assert len(intermediarias) == 1
        assert intermediarias[0]["origem"] == "derivado"
        # 500000 (valor_negociado) - 0 (sinal) - 400000 (financiamento)
        assert intermediarias[0]["valor"] == "100000.00"

    def test_never_recreated_over_a_typed_intermediaria(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            parcelas=[_parcela_row(aid, "intermediaria", valor="90000.00", origem="manual")],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_financiado=Decimal("400000.00"))
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        intermediarias = (
            _t(scoped, "atendimento_negociacao_parcelas").select("*")
            .eq("tipo", "intermediaria").execute().data
        )
        assert len(intermediarias) == 1
        assert intermediarias[0]["valor"] == "90000.00"  # untouched


# ─── DPS tripwire + D3 permanence ────────────────────────────────────────


class TestErrosPermanentes:
    def test_dps_and_quadro_not_found_are_never_retried(self):
        assert extracao_retentativa.retentavel("documento_sensivel_dps") is False
        assert extracao_retentativa.retentavel("quadro_resumo_nao_encontrado") is False


# ─── lesson G6 — never a false 'ok' ───────────────────────────────────────


class TestExtrairNeverFalseOk:
    @pytest.mark.asyncio
    async def test_an_exception_in_apply_ends_in_erro(self, scoped):
        """A pre-existing `financiamento` parcela row with NO `id` key (a
        genuinely malformed row — not a patched collaborator) makes
        `_aplicar_financiamento_parcela`'s conflict-open path raise a REAL
        `KeyError` once its value disagrees with the reading's. `extrair`
        must end in `erro`, NEVER a false `ok` — the reading itself is
        already safely written before this point (lesson G6: Crednet once
        stamped `ok` before its side effects crashed)."""
        aid = str(uuid4())
        parcela_sem_id = {
            "org_id": ORG_ID, "atendimento_id": aid, "tipo": "financiamento",
            "valor": "100000.00", "vencimento": None, "evento": None,
            "forma_pagamento": None, "favorecido_id": None,
            "confissao_divida": False, "dispara_corretagem": False, "ordem": 0,
            "origem": "manual", "documento_id": None, "extraido_em": None,
            "confirmado_por": None, "confirmado_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "created_por": None,
        }
        cid, aid = _seed(scoped, aid=aid, com_negociacao=True, parcelas=[parcela_sem_id])
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        storage = FakeStorageBackend()
        await storage.put(
            bucket="social-wiring-documentos",
            key=f"{ORG_ID}/atendimentos/{aid}/{doc_id}",
            data=b"%PDF-1.4 fake",
            content_type="application/pdf",
        )

        class _Extractor:
            async def extract(self, data, *, mimetype=None, filename=None):
                return _FinanciamentoLeitura(valor_financiado=Decimal("250000.00"))

        resultado = await nx.extrair(
            scoped, storage, ORG_UUID, aid, doc_id, extractor=_Extractor(),
        )

        assert resultado["status"] == nx.ERRO
        row = _t(scoped, "atendimento_documentos").select("*").execute().data[0]
        assert row["extracao_status"] == "erro"
        assert row["extracao_status"] != "ok"
        # The reading itself survives — only the APPLY failed.
        assert row["extracao_dados"] is not None


# ─── D2 — confirmar / resolver ───────────────────────────────────────────


class TestConfirmarLeitura:
    def test_stamps_confirmado_on_every_pending_value_from_this_document(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])
        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("500000.00"))
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        usuario_id = uuid4()
        resultado = nx.confirmar_leitura(
            scoped, ORG_UUID, aid, doc_id, confirmado_por=usuario_id,
        )
        assert resultado["confirmados"] == 1
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado_confirmado_em"] is not None
        assert row["valor_negociado_confirmado_por"] == str(usuario_id)


class TestResolverConflito:
    def test_accept_applies_the_proposed_value_confirmed_by_construction(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")],
        )
        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("480000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)
        conflito_id = resultado["conflitos"][0]["id"]

        admin_id = uuid4()
        nx.resolver_conflito(
            scoped, ORG_UUID, conflito_id, aceitar=True, decidido_por=admin_id,
        )

        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado"] == "480000.00"
        assert row["valor_negociado_confirmado_por"] == str(admin_id)
        conflito = (
            _t(scoped, "atendimento_campo_conflitos").select("*")
            .eq("id", conflito_id).execute().data[0]
        )
        assert conflito["status"] == "aceito"

    def test_reject_leaves_the_target_untouched(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")],
        )
        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("480000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)
        conflito_id = resultado["conflitos"][0]["id"]

        nx.resolver_conflito(
            scoped, ORG_UUID, conflito_id, aceitar=False, decidido_por=uuid4(),
        )

        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado"] == "500000.00"

    def test_a_decided_conflict_cannot_be_decided_twice(self, scoped):
        from noctusai_lib.primitives.exceptions import ValidationError_

        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")],
        )
        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("480000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)
        conflito_id = resultado["conflitos"][0]["id"]
        nx.resolver_conflito(scoped, ORG_UUID, conflito_id, aceitar=True, decidido_por=uuid4())

        with pytest.raises(ValidationError_):
            nx.resolver_conflito(
                scoped, ORG_UUID, conflito_id, aceitar=False, decidido_por=uuid4(),
            )


# ─── Manual writers stamp provenance ─────────────────────────────────────


class TestManualWritersStampProvenance:
    def test_negociacao_service_atualizar_stamps_manual(self, scoped):
        from app.modules.card_hub import negociacao_service

        cid, aid = _seed(scoped, com_negociacao=False)
        negociacao_service.atualizar(
            scoped, ORG_UUID, cid, valores={"valor_negociado": "500000.00"},
            usuario_id=uuid4(),
        )
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado_origem"] == "manual"
        assert row["valor_negociado_confirmado_em"] is not None

    def test_financiamento_service_atualizar_stamps_manual(self, scoped):
        from app.modules.card_hub import financiamento_service

        cid, aid = _seed(scoped, com_negociacao=False)
        financiamento_service.atualizar(
            scoped, ORG_UUID, cid, valores={"fgts": True}, usuario_id=uuid4(),
        )
        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["fgts_origem"] == "manual"
        assert row["fgts_confirmado_em"] is not None

    def test_negociacao_estruturada_criar_parcela_stamps_manual(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        neg_estruturada.criar_parcela(
            scoped, ORG_UUID, cid,
            valores={"tipo": "sinal", "valor": "50000.00"}, usuario_id=uuid4(),
        )
        parcela = (
            _t(scoped, "atendimento_negociacao_parcelas").select("*")
            .eq("tipo", "sinal").execute().data[0]
        )
        assert parcela["origem"] == "manual"
        assert parcela["confirmado_em"] is not None


# ─── the fontes REGISTRO / MANUAL_APENAS sweep stays exhaustive ─────────
# (already exercised by `test_proveniencia_fontes.py::TestRegistroCoberto`
# — this file does not duplicate that guard.)
