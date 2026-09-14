"""The office's open policy questions — ONE named default each, in ONE place.

The 15 questions in `contracts/f5-template-spec.md` §6.2 were published to the
office and are unanswered. Every place the generator would otherwise have to
guess an answer reads a field of `Politica` instead, and each field's comment
cites its question number — so an answer becomes a config change here, not a
rewrite of the builder.

The default for each is the most conservative reading of the 8 signed
sample contracts: wording present in only one contract is OFF, a value the
system does not hold is NOT invented (the clause is omitted and an `aviso`
names the omission), and an unanswered data question is left to the gate.

`POLITICA_PADRAO` is what production uses (`deps.get_politica_contrato`).
Tests pass a `dataclasses.replace(POLITICA_PADRAO, ...)` through the same
parameter — a DI seam, never a patch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional

#: `imovel_dados.situacao_onus` values that mean an active financing debt on
#: the imóvel (spec §1.1 `tem_saldo_devedor`, "vocabulary to confirm").
ONUS_COM_SALDO: tuple[str, ...] = ("hipoteca", "alienacao_fiduciaria")

#: `situacao_onus` values the generator can word today. `penhora`,
#: `usufruto`, `indisponibilidade` and `outro` have no clause in the sample
#: contracts — generating would print "livre de ônus" over a real one, so
#: they BLOCK rather than fall through.
ONUS_SUPORTADOS: tuple[str, ...] = ("livre",) + ONUS_COM_SALDO

#: Spec §3 #16 — `imovel.em_condominio` "derivable from imoveis.empreendimento
#: (rule to confirm)". A named rule, not an inline truthiness test.
EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO = True

ENCARGOS_RESCISAO: tuple[str, ...] = ("honorarios", "custos", "nenhum")
DESPESAS_PERMUTA: tuple[str, ...] = ("compradores", "cada_parte")


@dataclass(frozen=True)
class Politica:
    # [Q1] Declaração das Partes (Lei 8.212/91; Dec. 93.240/86) appears only in
    # contract 07. Standard for all? Unanswered → OFF.
    tem_declaracao_partes: bool = False
    # [Q1] Notice + cure period before rescisão (07 only). Unanswered → none.
    rescisao_cura_dias: Optional[int] = None
    # [Q1] Resolutiva mora constituted by e-mail notice (07 only) → OFF.
    resolutiva_notificacao_email: bool = False

    # [Q2] "na vigência da Lei 6.515/77": every comunhão parcial, only
    # marriages after 26/12/1977, or never? The marriage date is MISSING
    # (§6.1 #19), so it is NOT cited and an aviso names the omission.
    citar_lei_6515: bool = False

    # [Q3] Multa rescisória = the sinal's valor (8/8 contracts). Negotiable?
    # Unanswered → derived from the sinal; there is no override field.
    multa_rescisoria_igual_sinal: bool = True

    # [Q4] Rescisão ¶2 encargo: "honorarios" | "custos" | "nenhum". Not
    # chosen (None) → the encargo wording is omitted and an aviso says so.
    rescisao_encargo: Optional[str] = None

    # [Q5] Corretagem % owed on rescisão = the deal's `pct_comissao`?
    # (it is not in 03 and 04) → yes, with an aviso.
    corretagem_rescisao_igual_comissao: bool = True

    # [Q6] FGTS + financiamento: one combined parcela (03) or two numbered
    # parcelas? → two parcelas, one row per `tipo` (the data model's shape).
    fgts_parcela_separada: bool = True

    # [Q7] `tipo='saldo'` means "payoff of the seller's existing financing"
    # (05's boleto)? → yes; a saldo parcela without an active ônus BLOCKS.
    saldo_quita_financiamento_vendedor: bool = True

    # [Q8] The API `tjsp` certidão is the same document as the manual
    # `tjsp_esaj` (used when no `tjsp_esaj` result exists), and
    # `trf3_sp` → 1ª instância / `trf3` → 2ª instância.
    tjsp_api_equivale_esaj: bool = True

    # [Q9] Which companies of a parte must be certified? Unanswered → none
    # is REQUIRED; CNPJ consultas already linked to a parte are rendered.
    exigir_certidoes_pj: bool = False

    # [Q10] Default validity (days) per certidão tipo when the document
    # states none. Unanswered → empty: such certidões are not freshness-
    # checked and an aviso lists them.
    validade_padrao_dias: Mapping[str, int] = field(default_factory=dict)

    # [Q11] Pendências prazo: 10 days default (05 = 15, when?). Estado-civil
    # comprovante max age: < 30 days (02 says 90).
    prazo_pendencias_dias: int = 10
    prazo_esclarecimentos_dias: int = 10
    comprovante_estado_civil_max_dias: int = 30

    # [Q12] Posse multa diária: a fixed office value? Unknown → None → the
    # paragraph is omitted (never an invented amount) and an aviso says so.
    posse_multa_diaria: Optional[Decimal] = None

    # [Q13] Permuta: who pays deed/ITBI of each imóvel — "compradores" (01)
    # or "cada_parte" (07)? Unanswered → None → a permuta contract is
    # `faltando` this decision.
    permuta_despesas: Optional[str] = None

    # [Q14] Keep e-mails beside names in the signature block (D4sign)? → yes,
    # when the person has one (missing → aviso). Witnesses carry RG only.
    email_no_bloco_assinatura: bool = True
    testemunha_exige_cpf: bool = False

    # [Q15] Contract 01's Σ parcelas ≠ preço and 08's card-vs-contract price
    # are DATA questions with no code default: the gate blocks any Σ parcelas
    # ≠ valor_negociado (bloqueio SOMA_PARCELAS_DIFERENTE_DO_PRECO).


POLITICA_PADRAO = Politica()

__all__ = [
    "DESPESAS_PERMUTA",
    "EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO",
    "ENCARGOS_RESCISAO",
    "ONUS_COM_SALDO",
    "ONUS_SUPORTADOS",
    "POLITICA_PADRAO",
    "Politica",
]
