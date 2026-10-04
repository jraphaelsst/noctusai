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
    # `rotulos` — per-field found-labels map (finding [MED-HIGH], audit,
    # 2026-09-28): a key present (even with an unparseable value) means the
    # Quadro Resumo carried a labelled line for that field; absent means the
    # parser found none at all. See `nx._rotulo_lido`.
    rotulos: Mapping[str, str] = field(default_factory=dict)
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
    agentes=None, nome_comprador="Comprador", cpf_comprador=CPF_COMPRADOR,
):
    cid, aid = str(uuid4()), (aid or str(uuid4()))
    clientes = [cliente_row(cid, nome=nome_comprador, cpf=cpf_comprador)]
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

    def test_no_cpf_read_at_all_fills_the_empty_field_flagged_never_a_conflict(
        self, scoped
    ):
        """🔴 Finding [MEDIUM] (audit, 2026-09-28): the OLD behaviour here
        trusted an unverifiable document exactly as much as a verified one
        — `_pertence_ao_negocio` returned `PERTENCE`-equivalent (`True`)
        whenever NO CPF was read at all (vision CPFs often fail their check
        digit; ITBI guides often carry none), so another deal's ITBI guide
        could silently seed THIS atendimento's `valor_negociado`. The fix:
        this is now `NAO_VERIFICADO`, not `PERTENCE` — the D1 apply opens a
        PENDING conflict (never a direct fill), aviso `pertencimento_nao_
        verificado`, so a human decides whether it even belongs here.
        Preserves `test_no_matching_cpf_applies_nothing`'s "present-and-
        WRONG" behaviour untouched — this is the OTHER branch, "absent".

        🔴 P5 audit F1 (owner rule H1, 2026-10-03): that pending conflict
        had `valor_anterior=None` — a "divergence" with nothing, which
        blocked contract generation on 4 audited deals until a human
        accepted the very value the document carried. The empty field is
        now FILLED, machine-pending (`confirmado_em IS NULL` — the contract
        gate still asks a human to vouch), the aviso stays on the
        document."""
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])

        leitura = _GuiaItbiLeitura(valor_transacao=Decimal("500000.00"))
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        assert resultado["status"] == nx.OK
        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        assert _t(scoped, "atendimento_campo_conflitos").select("*").execute().data == []
        negociacao = _t(scoped, "atendimento_negociacao").select("*").execute().data
        assert negociacao[0]["valor_negociado"] == "500000.00"
        assert negociacao[0]["valor_negociado_origem"] == "guia_itbi"
        assert negociacao[0]["valor_negociado_documento_id"] == doc_id
        assert negociacao[0]["valor_negociado_confirmado_em"] is None

    def test_a_valid_conta_credito_cpf_counts_as_membership_evidence(self, scoped):
        """Finding [MEDIUM] (a), audit 2026-09-28 (live case, deal 883):
        the party-header CPFs are all misread by vision, but the Quadro
        Resumo's own account-box CPF is valid and matches the vendedora —
        that alone must verify membership and fill the empty field
        directly, not route it as `pertencimento_nao_verificado`."""
        cid, aid = _seed(scoped, com_negociacao=False, com_vendedor=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        conta = _ContaCreditoVendedor(
            banco_nome="Bradesco", titular_cpf=CPF_VENDEDOR, titular_cpf_valido=True,
        )
        leitura = _FinanciamentoLeitura(
            valor_compra_venda=Decimal("500000.00"), conta_credito_vendedor=conta,
        )
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "pertencimento_nao_verificado" not in (resultado["aviso"] or "")
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado"] == "500000.00"


# ─── H2: valor_negociado — fill-empty, else conflict ────────────────────


class TestPropostaLetterBelongsByProponente:
    """Live 2026-10-03: 5/5 proposta uploads read
    `pertencimento_nao_verificado`, so every value they proposed opened a
    conflict against an EMPTY field instead of filling it (H1). The bank's
    letter names its proponente — Itaú's with NO CPF at all ("Oi, <Nome>.
    Sua proposta foi aprovada"). Read through the REAL seed parser so the
    seed↔SW contract is exercised, not a hand-built fake. All names and
    numbers are invented."""

    _NOME = "Fulana Sintética de Teste"

    @staticmethod
    def _carta(nome: str) -> str:
        return (
            "Crédito imobiliário\nCarta de Crédito\nN. Proposta: 12345678\n"
            f"Oi, {nome}. Sua proposta foi aprovada e agora você pode conferir "
            "as condições do crédito através das informações abaixo:\n"
            "Valor do Imóvel: R$ 640.000,00\n"
            "Valor da entrada: R$ 140.000,00\n"
            "Valor do financiamento: R$ 500.000,00\n"
            "Prazo: 360 meses\n"
        )

    def _aplicar(self, scoped, nome_na_carta: str, **seed_over):
        from noctusai_lib.integrations.documents.financiamento_imobiliario import (
            parse_financiamento_imobiliario,
        )
        from noctusai_lib.integrations.documents.types import TextSource

        cid, aid = _seed(scoped, com_negociacao=False, **seed_over)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        leitura = parse_financiamento_imobiliario(
            self._carta(nome_na_carta), TextSource.OCR, "proposta"
        )
        return nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura,
        )

    def test_letter_naming_the_comprador_fills_the_empty_field_directly(self, scoped):
        resultado = self._aplicar(
            scoped, "FULANA SINTETICA DE TESTE", nome_comprador=self._NOME,
        )
        assert "pertencimento_nao_verificado" not in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        negociacao = _t(scoped, "atendimento_negociacao").select("*").execute().data
        assert negociacao[0]["valor_negociado"] == "640000.00"
        assert negociacao[0]["valor_negociado_origem"] == "proposta_financiamento"

    def test_comprador_without_a_registered_cpf_still_matches_by_name(self, scoped):
        resultado = self._aplicar(
            scoped, self._NOME, nome_comprador=self._NOME, cpf_comprador=None,
        )
        assert "pertencimento_nao_verificado" not in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []

    def test_letter_naming_someone_else_fills_the_empty_field_flagged(self, scoped):
        """Unverified (a name that matches no comprador — a stranger or a
        one-letter misread, indistinguishable) — H1: the empty field is
        filled machine-pending and the document flagged; never a conflict
        against an empty value (P5 audit F1)."""
        resultado = self._aplicar(
            scoped, "Beltrana Outra Pessoa", nome_comprador=self._NOME,
        )
        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        negociacao = _t(scoped, "atendimento_negociacao").select("*").execute().data
        assert negociacao[0]["valor_negociado"] == "640000.00"
        assert negociacao[0]["valor_negociado_confirmado_em"] is None
        assert resultado["conflitos"] == []

    def test_a_one_letter_misread_is_not_a_match(self, scoped):
        resultado = self._aplicar(
            scoped, "Fulana Sintetica de Tesre", nome_comprador=self._NOME,
        )
        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")

    def test_a_vendedor_s_name_does_not_verify_a_proposta(self, scoped):
        resultado = self._aplicar(scoped, "Vendedor", com_vendedor=True)
        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")

    def test_a_valid_cpf_of_someone_else_outranks_a_coinciding_name(self, scoped):
        leitura = _FinanciamentoLeitura(
            documento="proposta",
            valor_compra_venda=Decimal("640000.00"),
            compradores=[_Pessoa(nome="Comprador", cpf="52998224725", cpf_valido=True)],
        )
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura,
        )
        assert resultado["aviso"] == "documento_de_outro_negocio"


class TestGuiaVisaoBelongsByComprador:
    """Vision-read ITBI guides (2026-10-03): none yielded a comprador before,
    so every one read `pertencimento_nao_verificado` and its valor opened a
    conflict against an EMPTY field instead of filling it (H1). Read through
    the REAL seed parser. Invented names/numbers; real layouts."""

    _NOME = "Fulana Sintética de Teste"

    def _aplicar(self, scoped, texto: str, **seed_over):
        from noctusai_lib.integrations.documents.guia_itbi import parse_guia_itbi
        from noctusai_lib.integrations.documents.types import TextSource

        cid, aid = _seed(scoped, **{"com_negociacao": False, **seed_over})
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])
        leitura = parse_guia_itbi(texto, TextSource.OCR)
        return nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

    def _valor(self, scoped):
        return _t(scoped, "atendimento_negociacao").select("*").execute().data[0]["valor_negociado"]

    def test_contribuinte_line_with_the_comprador_cpf_below_fills_directly(self, scoped):
        texto = (
            "CONTRIBUINTE: Fulana Sintetica de Teste\n"
            "CPF/CNPJ: 390.533.447-05\n"
            "Valor da Transação: R$ 640.000,00\n"
        )
        resultado = self._aplicar(scoped, texto, nome_comprador=self._NOME)
        assert "pertencimento_nao_verificado" not in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        assert self._valor(scoped) == "640000.00"

    def test_blank_cpf_but_every_named_adquirente_is_a_comprador_fills(self, scoped):
        texto = (
            "Adquirente: Fulana Sintetica de Teste - CPF/CNPJ: [EM BRANCO]\n"
            "Transmitente: Ciclano Vendedor - CPF/CNPJ: [EM BRANCO]\n"
            "Valor da Transação: R$ 640.000,00\n"
        )
        resultado = self._aplicar(scoped, texto, nome_comprador=self._NOME)
        assert resultado["conflitos"] == []
        assert self._valor(scoped) == "640000.00"

    def test_one_named_stranger_withholds_it(self, scoped):
        texto = (
            "CONTRIBUINTE: Fulana Sintetica de Teste e Beltrano Estranho Silva\n"
            "CPF/CNPJ: [EM BRANCO]\n"
            "Valor da Transação: R$ 640.000,00\n"
        )
        resultado = self._aplicar(scoped, texto, nome_comprador=self._NOME)
        # Unverified -> flagged; H1 fills the EMPTY field machine-pending.
        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        assert self._valor(scoped) == "640000.00"

    def test_a_guide_naming_only_someone_else_is_flagged(self, scoped):
        texto = (
            "Adquirente: Beltrano Estranho Silva - CPF/CNPJ: [EM BRANCO]\n"
            "Valor da Transação: R$ 640.000,00\n"
        )
        resultado = self._aplicar(scoped, texto, nome_comprador=self._NOME)
        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        assert self._valor(scoped) == "640000.00"

    def test_a_valid_cpf_of_someone_else_refuses_the_guide(self, scoped):
        texto = (
            "CONTRIBUINTE: Fulana Sintetica de Teste\n"
            "CPF/CNPJ: 529.982.247-25\n"
            "Valor da Transação: R$ 640.000,00\n"
        )
        resultado = self._aplicar(scoped, texto, nome_comprador=self._NOME)
        assert resultado["aviso"] == "documento_de_outro_negocio"

    def test_a_differing_value_on_file_still_opens_a_conflict(self, scoped):
        texto = (
            "CONTRIBUINTE: Fulana Sintetica de Teste\n"
            "CPF/CNPJ: 390.533.447-05\n"
            "Valor da Transação: R$ 640.000,00\n"
        )
        resultado = self._aplicar(
            scoped, texto, nome_comprador=self._NOME, com_negociacao=True,
        )
        assert [c["campo"] for c in resultado["conflitos"]] == ["valor_negociado"]
        assert self._valor(scoped) == "500000.00"


class TestValorNegociado:
    def test_fills_an_empty_value(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=False)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(doc_id, aid, "guia_itbi")])

        # A validated, matching CPF — this document's membership IS
        # verified, so its empty `valor_negociado` fills directly (contrast
        # `TestBelongsToThisDeal`'s NAO_VERIFICADO case, which fills but
        # flags the document).
        leitura = _GuiaItbiLeitura(
            valor_transacao=Decimal("500000.00"),
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
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

    def test_a_previously_rejected_value_is_not_reopened(self, scoped):
        """Finding [MEDIUM] (audit, 2026-09-28), ported from `imovel_hub.
        campos_extraidos_service.aplicar`'s REJEITADO_ANTES check: a human
        already said no to `480000.00` — a re-run proposing the SAME value
        again must not re-open (and re-notify) the same question."""
        cid, aid = _seed(scoped, com_negociacao=True)
        scoped.set_table_data(
            "atendimento_campo_conflitos",
            [
                {
                    "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
                    "campo": "valor_negociado", "valor_anterior": "500000.00",
                    "origem_anterior": "manual", "valor_proposto": "480000.00",
                    "origem_proposto": "contrato_financiamento",
                    "documento_id_proposto": None, "confianca_proposta": None,
                    "fonte_tabela": None, "fonte_id": None,
                    "status": "rejeitado", "notificado_em": None,
                    "decidido_por": str(uuid4()),
                    "decidido_em": "2026-01-02T00:00:00+00:00",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )

        leitura = _FinanciamentoLeitura(valor_compra_venda=Decimal("480000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "conflito_ja_rejeitado" in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado"] == "500000.00"  # untouched
        pendentes = (
            _t(scoped, "atendimento_campo_conflitos").select("*")
            .eq("status", "pendente").execute().data
        )
        assert pendentes == []

    def test_a_re_read_of_the_same_pending_document_replaces_not_conflicts(
        self, scoped
    ):
        """Finding [MEDIUM] (audit, 2026-09-28), ported from `campo_
        conflitos.mesmo_documento_pendente`'s D1 same-document-re-read
        refinement: a re-extraction of the SAME document whose earlier
        pass is still machine-pending is a REFRESH, not a second opinion —
        it replaces the stale value and closes any conflict it had opened,
        rather than conflicting with itself."""
        aid = str(uuid4())
        doc_id = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            negociacao_over={
                "valor_negociado": "480000.00",
                "valor_negociado_origem": "contrato_financiamento",
                "valor_negociado_documento_id": doc_id,
                "valor_negociado_confirmado_em": None,
            },
        )
        scoped.set_table_data(
            "atendimento_campo_conflitos",
            [
                {
                    "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
                    "campo": "valor_negociado", "valor_anterior": "500000.00",
                    "origem_anterior": "manual", "valor_proposto": "480000.00",
                    "origem_proposto": "contrato_financiamento",
                    "documento_id_proposto": doc_id, "confianca_proposta": None,
                    "fonte_tabela": None, "fonte_id": None,
                    "status": "pendente", "notificado_em": None,
                    "decidido_por": None, "decidido_em": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )

        leitura = _FinanciamentoLeitura(valor_compra_venda=Decimal("490000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert resultado["conflitos"] == []
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado"] == "490000.00"  # replaced, not conflicted
        conflitos = _t(scoped, "atendimento_campo_conflitos").select("*").execute().data
        assert all(c["status"] != "pendente" for c in conflitos)

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
            rotulos={"valor_fgts": "FGTS"},
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
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

    def test_unverified_membership_fills_the_new_parcela_flagged(self, scoped):
        """No CPF at all was read. Finding [MEDIUM] (b) (2026-09-28) used to
        create the parcela EMPTY plus a conflict against it; P5 audit F1
        (owner rule H1, 2026-10-03): the new parcela carries the read value
        machine-pending, the document is flagged, no conflict."""
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("400000.00"), rotulos={"valor_fgts": "FGTS"},
        )
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        assert resultado["conflitos"] == []
        parcelas = (
            _t(scoped, "atendimento_negociacao_parcelas")
            .select("*").eq("tipo", "financiamento").execute().data
        )
        assert len(parcelas) == 1
        assert parcelas[0]["valor"] == "400000.00"
        assert parcelas[0]["origem"] == "contrato_financiamento"
        assert parcelas[0]["documento_id"] == doc_id
        assert parcelas[0]["confirmado_em"] is None

    def test_fgts_label_not_found_on_contrato_refuses_the_whole_compose(self, scoped):
        """Finding [MED-HIGH] (audit, 2026-09-28): a Quadro Resumo whose
        FGTS label the seed doesn't recognize must not silently compose the
        parcela from `valor_financiado` alone (the original bug: `or
        Decimal("0")` turned "unread" into "zero" with no human signal)."""
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("400000.00"),
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "fgts_nao_lido" in (resultado["aviso"] or "")
        parcelas = (
            _t(scoped, "atendimento_negociacao_parcelas")
            .select("*").eq("tipo", "financiamento").execute().data
        )
        assert parcelas == []

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
        # `proposta_financiamento` never carries a Quadro Resumo — the FGTS
        # gate is scoped to `contrato_financiamento` only, so no `rotulos`
        # is needed here.
        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("400000.00"),
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
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
        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("390000.00"), rotulos={"valor_fgts": "FGTS"},
        )
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
        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("400000.00"), rotulos={"valor_fgts": "FGTS"},
        )
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
        # A validated, matching CPF — this document's membership IS
        # verified, so its empty `fgts` fills directly (contrast
        # the `test_unverified_membership_*` sibling, filled but flagged).
        leitura = _FinanciamentoLeitura(
            valor_fgts=Decimal("15000.00"),
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["fgts"] is True
        assert row["fgts_origem"] == "contrato_financiamento"

    def test_unverified_membership_fills_empty_fgts_flagged(self, scoped):
        """No CPF at all was read — H1 (P5 audit F1): the EMPTY `fgts`
        (no provenance) is filled machine-pending, flagged, no conflict."""
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(valor_fgts=Decimal("15000.00"))
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["fgts"] is True
        assert row["fgts_origem"] == "contrato_financiamento"
        assert row["fgts_confirmado_em"] is None
        assert resultado["conflitos"] == []

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
        # A validated, matching CPF — this document's membership IS
        # verified, so `situacao` fills directly (contrast
        # the `test_unverified_membership_*` sibling (filled but flagged)).
        leitura = _FinanciamentoLeitura(
            quadro_encontrado=True,
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["situacao"] == "aprovado"
        assert row["situacao_origem"] == "contrato_financiamento"

    def test_unverified_membership_fills_the_default_situacao_flagged(self, scoped):
        """No CPF at all was read — H1 (P5 audit F1): the provenance-less
        `pendente` default IS the empty value; filled, flagged, no
        conflict."""
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        leitura = _FinanciamentoLeitura(quadro_encontrado=True)
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura,
        )

        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["situacao"] == "aprovado"
        assert row["situacao_origem"] == "contrato_financiamento"
        assert resultado["conflitos"] == []

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
        # A validated, matching CPF — membership IS verified, so the field
        # fills directly (contrast
        # the `test_unverified_membership_*` sibling (filled but flagged)).
        leitura = _FinanciamentoLeitura(
            banco_nome="Itaú", banco_codigo="341",
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
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
        leitura = _FinanciamentoLeitura(
            banco_codigo="104",
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura)

        agentes = _t(scoped, "agentes_financeiros").select("*").execute().data
        assert len(agentes) == 1  # no second row created
        financiamento = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert financiamento["agente_financeiro_id"] == agente_id

    def test_unverified_membership_fills_the_empty_agente_flagged(self, scoped):
        """No CPF at all was read — H1 (P5 audit F1): the EMPTY
        `agente_financeiro_id` is filled machine-pending, flagged, no
        conflict."""
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
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura,
        )

        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        financiamento = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert financiamento["agente_financeiro_id"] == agente_id
        assert financiamento["agente_financeiro_confirmado_em"] is None
        assert resultado["conflitos"] == []


class TestNumeroProposta:
    def test_fills_when_origem_is_unset(self, scoped):
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        # A validated, matching CPF — membership IS verified, so
        # `numero_proposta` fills directly (contrast
        # the `test_unverified_membership_*` sibling (filled but flagged)).
        leitura = _FinanciamentoLeitura(
            numero_proposta="PROP-123",
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura)

        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["numero_proposta"] == "PROP-123"
        assert row["numero_proposta_origem"] == "proposta_financiamento"

    def test_unverified_membership_fills_the_empty_numero_flagged(self, scoped):
        """No CPF at all was read — H1 (P5 audit F1): filled
        machine-pending, flagged, no conflict."""
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        leitura = _FinanciamentoLeitura(numero_proposta="PROP-123")
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura,
        )

        assert "pertencimento_nao_verificado" in (resultado["aviso"] or "")
        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["numero_proposta"] == "PROP-123"
        assert row["numero_proposta_confirmado_em"] is None
        assert resultado["conflitos"] == []


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
        assert favorecidos[0]["cpf_cnpj"] == "111.444.777-35"  # canonical, punctuated
        assert favorecidos[0]["origem"] == "contrato_financiamento"

    def test_a_favorecido_a_human_typed_punctuated_is_matched_not_duplicated(self, scoped):
        """Owner rule 2026-10-01 (`canonical-identifiers`): the same CPF in two
        spellings is ONE person. The old exact-digits `.eq` missed the human's
        `111.444.777-35` and the machine INSERTED a second favorecido."""
        cid, aid = _seed(scoped, com_negociacao=True, com_vendedor=True)
        favorecido_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_favorecidos",
            [{
                "id": favorecido_id, "org_id": ORG_ID, "atendimento_id": aid,
                "nome": "Vendedor", "cpf_cnpj": "111.444.777-35",
                "banco": None, "agencia": None, "conta": None, "pix": None,
                "origem": "manual", "documento_id": None,
                "confirmado_por": None, "confirmado_em": None,
                "created_at": "2026-01-01T00:00:00+00:00", "created_por": None,
                "updated_at": None, "updated_por": None,
            }],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        conta = _ContaCreditoVendedor(
            banco_nome="Bradesco", agencia="1234", conta="56789-0",
            titular_cpf=CPF_VENDEDOR, titular_cpf_valido=True,
        )
        nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "contrato_financiamento",
            _FinanciamentoLeitura(conta_credito_vendedor=conta),
        )
        favorecidos = _t(scoped, "atendimento_favorecidos").select("*").execute().data
        assert [f["id"] for f in favorecidos] == [favorecido_id]
        assert favorecidos[0]["banco"] == "Bradesco"

    def test_a_partial_fill_on_a_confirmed_row_reopens_confirmation(self, scoped):
        """🔴 Finding [MEDIUM] (audit, 2026-09-28): a vision-read value
        landing on an already-confirmed favorecido must not keep counting
        as confirmed. `banco`/`conta` were already human-confirmed;
        `agencia` was left empty and this reading fills it."""
        cid, aid = _seed(scoped, com_negociacao=True, com_vendedor=True)
        favorecido_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_favorecidos",
            [
                {
                    "id": favorecido_id, "org_id": ORG_ID, "atendimento_id": aid,
                    "nome": "Vendedor", "cpf_cnpj": CPF_VENDEDOR,
                    "banco": "Bradesco", "agencia": None, "conta": "56789-0",
                    "pix": None, "origem": "manual", "documento_id": None,
                    "confirmado_por": str(uuid4()), "confirmado_em": "2026-01-01T00:00:00+00:00",
                    "created_at": "2026-01-01T00:00:00+00:00", "created_por": None,
                    "updated_at": None, "updated_por": None,
                }
            ],
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        conta = _ContaCreditoVendedor(
            agencia="1234", titular_cpf=CPF_VENDEDOR, titular_cpf_valido=True,
        )
        leitura = _FinanciamentoLeitura(conta_credito_vendedor=conta)
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        row = (
            _t(scoped, "atendimento_favorecidos").select("*")
            .eq("id", favorecido_id).execute().data[0]
        )
        assert row["agencia"] == "1234"
        assert row["confirmado_por"] is None
        assert row["confirmado_em"] is None

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
        leitura = _FinanciamentoLeitura(
            valor_financiado=Decimal("400000.00"), rotulos={"valor_fgts": "FGTS"},
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
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

    def test_a_permanent_error_is_never_re_swept(self, scoped):
        """`NOC-REMEDIATE[extracao-varredura-colunas-erro]` (2026-09-28):
        `nx._COLUNAS_VARREDURA` was missing `extracao_erro` — the
        retryable-error leg's own filter (`extracao_retentativa.
        retentavel`) could not see it, so a PERMANENT error (below its
        attempt cap) was retried unconditionally instead of being left for
        a human."""
        from datetime import datetime, timedelta, timezone

        from app.services import extracao_varredura

        _cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        old = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        scoped.set_table_data(
            "atendimento_documentos",
            [_documento(
                doc_id, aid, "guia_itbi",
                extracao_status="erro", extracao_em=old, extracao_tentativas=0,
                extracao_erro="transcricao_truncada: pagina 2 excedeu o limite",
            )],
        )
        candidatos = extracao_varredura.candidatos(
            scoped, nx._sweep_config(None), limite=50,
        )
        assert candidatos == []


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
        leitura = _GuiaItbiLeitura(
            valor_transacao=Decimal("500000.00"),
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        )
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "guia_itbi", leitura)

        usuario_id = uuid4()
        resultado = nx.confirmar_leitura(
            scoped, ORG_UUID, aid, doc_id, confirmado_por=usuario_id,
        )
        assert resultado["confirmados"] == 1
        row = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert row["valor_negociado_confirmado_em"] is not None
        assert row["valor_negociado_confirmado_por"] == str(usuario_id)

    def test_covers_situacao_and_favorecidos_too(self, scoped):
        """🔴 Finding [LOW] (audit, 2026-09-28): `situacao` and favorecidos
        were missing here — a user clicking "confirmar" on a `contrato_
        financiamento` still got the contract generator's 409 because H6's
        `situacao` (and H5's favorecido bank data) stayed machine-pending
        even after the document they came from was confirmed."""
        cid, aid = _seed(scoped, com_negociacao=True, com_vendedor=True)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        conta = _ContaCreditoVendedor(
            banco_nome="Bradesco", titular_cpf=CPF_VENDEDOR, titular_cpf_valido=True,
        )
        leitura = _FinanciamentoLeitura(quadro_encontrado=True, conta_credito_vendedor=conta)
        nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento", leitura)

        usuario_id = uuid4()
        resultado = nx.confirmar_leitura(
            scoped, ORG_UUID, aid, doc_id, confirmado_por=usuario_id,
        )
        assert resultado["confirmados"] == 2  # situacao + favorecido
        financiamento = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert financiamento["situacao"] == "aprovado"
        assert financiamento["situacao_confirmado_em"] is not None
        assert financiamento["situacao_confirmado_por"] == str(usuario_id)
        favorecido = _t(scoped, "atendimento_favorecidos").select("*").execute().data[0]
        assert favorecido["confirmado_em"] is not None
        assert favorecido["confirmado_por"] == str(usuario_id)


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


# ─── P5 audit (2026-10-03): F1 repair + F3 financing record ─────────────


def _conflito_atd(aid: str, campo: str, *, anterior=None, proposto="640000.00",
                  origem="proposta_financiamento", fonte=None) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "campo": campo,
        "valor_anterior": anterior, "origem_anterior": None,
        "valor_proposto": proposto, "origem_proposto": origem,
        "confianca_proposta": None, "fonte_tabela": "atendimento_documentos",
        "fonte_id": fonte or str(uuid4()), "documento_id_proposto": fonte,
        "status": "pendente", "notificado_em": None, "decidido_por": None,
        "decidido_em": None, "created_at": "2026-10-02T00:00:00+00:00",
    }


class TestP5F3FinancingRecord:
    """F3: a financing document that read a bank or a financed value is
    evidence the deal has a financing operation — the record the contract
    requires ("Registro do financiamento") must exist."""

    def _proposta(self, scoped, leitura, **seed_over):
        cid, aid = _seed(scoped, com_negociacao=True, **seed_over)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "proposta_financiamento")],
        )
        resultado = nx.aplicar_leitura(
            scoped, ORG_UUID, aid, doc_id, "proposta_financiamento", leitura,
        )
        return aid, doc_id, resultado

    def test_a_financed_value_alone_creates_the_record(self, scoped):
        aid, _doc, _ = self._proposta(scoped, _FinanciamentoLeitura(
            documento="proposta", valor_financiado=Decimal("400000.00"),
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        ))
        (row,) = _t(scoped, "atendimento_financiamento").select("*").execute().data
        assert row["atendimento_id"] == aid
        assert row["situacao"] == "pendente"
        parcelas = (
            _t(scoped, "atendimento_negociacao_parcelas")
            .select("*").eq("tipo", "financiamento").execute().data
        )
        assert len(parcelas) == 1  # the parcela is the value's home — no duplicate

    def test_a_bank_known_only_by_name_matches_the_registry(self, scoped):
        agente_id = str(uuid4())
        _aid, doc_id, _ = self._proposta(scoped, _FinanciamentoLeitura(
            documento="proposta", banco_nome="BANCO SINTETICO S.A.",
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        ), agentes=[{
            "id": agente_id, "org_id": ORG_ID, "nome": "Sintético", "codigo_banco": None,
            "ativo": True, "origem": "manual", "agencia": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }])
        (row,) = _t(scoped, "atendimento_financiamento").select("*").execute().data
        assert row["agente_financeiro_id"] == agente_id
        assert row["agente_financeiro_origem"] == "proposta_financiamento"
        assert row["agente_financeiro_documento_id"] == doc_id
        assert len(_t(scoped, "agentes_financeiros").select("*").execute().data) == 1

    def test_an_unknown_bank_name_is_auto_created_without_a_code(self, scoped):
        self._proposta(scoped, _FinanciamentoLeitura(
            documento="proposta", banco_nome="Banco Sintetico Novo",
            compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
        ))
        (agente,) = _t(scoped, "agentes_financeiros").select("*").execute().data
        assert agente["nome"] == "Banco Sintetico Novo"
        assert agente.get("codigo_banco") is None
        assert agente["origem"] == "auto"
        (row,) = _t(scoped, "atendimento_financiamento").select("*").execute().data
        assert row["agente_financeiro_id"] == agente["id"]

    def test_a_provenance_less_recusado_is_never_reopened(self, scoped):
        """H6 — a pre-171 human refusal carries no `situacao_origem`; it is
        NOT the empty default and must conflict, never flip to aprovado."""
        aid = str(uuid4())
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True,
            financiamento=_financiamento_row(aid, situacao="recusado"),
        )
        doc_id = str(uuid4())
        scoped.set_table_data(
            "atendimento_documentos", [_documento(doc_id, aid, "contrato_financiamento")],
        )
        resultado = nx.aplicar_leitura(scoped, ORG_UUID, aid, doc_id, "contrato_financiamento",
                                       _FinanciamentoLeitura(
                                           quadro_encontrado=True,
                                           compradores=[_Pessoa(cpf=CPF_COMPRADOR, cpf_valido=True)],
                                       ))
        row = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert row["situacao"] == "recusado"
        assert [c["campo"] for c in resultado["conflitos"]] == ["financiamento.situacao"]

    def test_stored_readings_are_reapplied_without_a_model_call(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True)
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_documentos", [_documento(
            doc_id, aid, "proposta_financiamento", extracao_status="ok",
            extracao_dados={
                "documento": "proposta", "valor_financiado": "400000.00",
                "banco_nome": "Banco Sintetico Novo",
                "compradores": [{"nome": "Comprador", "cpf": CPF_COMPRADOR, "cpf_valido": True}],
                "confiancas": {}, "rotulos": {},
            },
        )])
        out = nx.backfill_negociacao(scoped, ORG_UUID)
        assert out["documentos_reaplicados"] == 1
        (row,) = _t(scoped, "atendimento_financiamento").select("*").execute().data
        assert row["agente_financeiro_documento_id"] == doc_id
        parcela = (
            _t(scoped, "atendimento_negociacao_parcelas")
            .select("*").eq("tipo", "financiamento").execute().data
        )[0]
        assert parcela["valor"] == "400000.00"
        assert parcela["documento_id"] == doc_id
        # Idempotent: a second pass creates nothing new.
        nx.backfill_negociacao(scoped, ORG_UUID)
        assert len(_t(scoped, "atendimento_financiamento").select("*").execute().data) == 1
        assert len(
            _t(scoped, "atendimento_negociacao_parcelas").select("*").eq("tipo", "financiamento")
            .execute().data
        ) == 1
        assert _t(scoped, "atendimento_campo_conflitos").select("*").execute().data == []


class TestP5F1RepairDealConflicts:
    def test_a_conflict_against_an_empty_valor_negociado_is_settled_by_filling(self, scoped):
        cid, aid = _seed(scoped, com_negociacao=True, negociacao_over={
            "valor_negociado": None, "valor_negociado_origem": None,
            "valor_negociado_confirmado_em": None,
        })
        doc_id = str(uuid4())
        c = _conflito_atd(aid, "valor_negociado", fonte=doc_id)
        scoped.set_table_data("atendimento_campo_conflitos", [c])

        (settled,) = nx.resolver_conflitos_vazios(scoped, ORG_UUID)
        assert settled["id"] == c["id"]
        neg = _t(scoped, "atendimento_negociacao").select("*").execute().data[0]
        assert neg["valor_negociado"] == "640000.00"
        assert neg["valor_negociado_origem"] == "proposta_financiamento"
        assert neg["valor_negociado_documento_id"] == doc_id
        assert neg["valor_negociado_confirmado_em"] is None  # machine-pending
        row = _t(scoped, "atendimento_campo_conflitos").select("*").execute().data[0]
        assert row["status"] == "resolvido_automatico"
        assert row["decidido_por"] is None
        assert row["motivo_resolucao"].startswith(f"[{nx.REGRA_VAZIO_PREENCHIDO}]")
        assert doc_id in row["motivo_resolucao"]

    def test_an_empty_parcela_and_financing_fields_are_settled(self, scoped):
        aid = str(uuid4())
        parcela = _parcela_row(aid, "financiamento", valor=None)
        cid, aid = _seed(
            scoped, aid=aid, com_negociacao=True, parcelas=[parcela],
            financiamento=_financiamento_row(aid),
        )
        doc_id = str(uuid4())
        scoped.set_table_data("atendimento_campo_conflitos", [
            _conflito_atd(aid, f"parcela.{parcela['id']}.valor", proposto="400000.00", fonte=doc_id),
            _conflito_atd(aid, "financiamento.situacao", anterior="pendente", proposto="aprovado",
                          origem="contrato_financiamento", fonte=doc_id),
        ])
        assert len(nx.resolver_conflitos_vazios(scoped, ORG_UUID)) == 2
        p = _t(scoped, "atendimento_negociacao_parcelas").select("*").execute().data[0]
        assert p["valor"] == "400000.00" and p["confirmado_em"] is None
        f = _t(scoped, "atendimento_financiamento").select("*").execute().data[0]
        assert f["situacao"] == "aprovado" and f["situacao_origem"] == "contrato_financiamento"

    def test_a_conflict_against_a_real_value_is_left_for_a_human(self, scoped):
        """H2 — valor_negociado has no authoritative document."""
        cid, aid = _seed(scoped, com_negociacao=True)  # 500000.00 manual
        c = _conflito_atd(aid, "valor_negociado", anterior="500000.00")
        scoped.set_table_data("atendimento_campo_conflitos", [c])
        assert nx.resolver_conflitos_vazios(scoped, ORG_UUID) == []
        assert _t(scoped, "atendimento_negociacao").select("*").execute().data[0][
            "valor_negociado"
        ] == "500000.00"
        assert _t(scoped, "atendimento_campo_conflitos").select("*").execute().data[0][
            "status"
        ] == "pendente"
