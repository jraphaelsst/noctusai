"""The office's contract policy — the 15 answers, in ONE place.

The 15 questions in `contracts/f5-template-spec.md` §6.2 were published to the
office and ANSWERED on 2026-09-15. Each answer below is either:

- a field of `Politica` whose DEFAULT is the answer (an office knob that stays
  a knob — e.g. the optional clauses of Q1, the age limits of Q10/Q11), or
- a fixed rule in `derivacao` / `frases` / `modelo_texto`, with only a comment
  here citing the question — an answer that removed an alternative leaves no
  toggle behind, because a toggle set against the answer is a latent
  misconfiguration, not a feature.

Values the office holds per organisation (posse multa diária, signing
platform, pendências prazo default) are DATA, not policy: they live on
`dados.Imobiliaria` and a missing one is `faltando`, never an invented value.

`POLITICA_PADRAO` is what production uses (`deps.get_politica_contrato`).
Tests pass a `dataclasses.replace(POLITICA_PADRAO, ...)` through the same
parameter — a DI seam, never a patch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

#: `imovel_dados.situacao_onus` values that mean an active financing debt on
#: the imóvel (spec §1.1 `tem_saldo_devedor`).
ONUS_COM_SALDO: tuple[str, ...] = ("hipoteca", "alienacao_fiduciaria")

#: `situacao_onus` values the generator can word today. `penhora`,
#: `usufruto`, `indisponibilidade` and `outro` have no clause in the sample
#: contracts — generating would print "livre de ônus" over a real one, so
#: they BLOCK rather than fall through.
ONUS_SUPORTADOS: tuple[str, ...] = ("livre",) + ONUS_COM_SALDO

#: Spec §3 #16 — `imovel.em_condominio` "derivable from imoveis.empreendimento
#: (rule to confirm)". A named rule, not an inline truthiness test.
EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO = True

#: [Q9] Receita Federal situação cadastral of a CNPJ consulta
#: (`Certidao.consulta_situacao_cadastral`).
SITUACOES_CADASTRAIS: tuple[str, ...] = ("ativa", "baixada", "inapta", "suspensa", "nula")
#: [Q9] A company in one of these is ALWAYS certified.
SITUACOES_PJ_EXIGIDAS: tuple[str, ...] = ("ativa", "inapta")
#: [Q9] A `baixada` company is certified only when it was closed recently.
SITUACAO_PJ_BAIXADA = "baixada"

#: Owner decision (2026-09-24): a contract carries 2 to 5 witnesses. The
#: minimum is a READINESS rule (`derivacao._imobiliaria` — a contract being
#: filled in may hold fewer while the operator picks); the maximum is refused
#: at write time (`contrato_testemunhas_service.definir`).
MIN_TESTEMUNHAS = 2
MAX_TESTEMUNHAS = 5

#: [Q9] The (non-signatory, lado vendedor) papel of a previous owner whose
#: certidões the contract presents.
PAPEL_ANTIGO_PROPRIETARIO = "antigo_proprietario"

#: [Q12 / §6.1 #12] The posse marco vocabulary is the STORAGE one (migration
#: 114): 'assinatura' | 'parcela' | 'protocolo_registro', where 'parcela'
#: NAMES its parcela. The generator's earlier 'parcela_financiamento' was an
#: answer inferred from ONE sample contract; it is gone rather than mapped,
#: because a mapping would have had to assume the marco parcela IS the
#: financiamento parcela and would print the wrong number when it is not.
#: The vocabulary itself lives in `frases.MARCOS_POSSE`.


@dataclass(frozen=True)
class Politica:
    # [Q1] Declaração das Partes (Lei 8.212/91; Dec. 93.240/86) — answered:
    # NOT standard → OFF. A contract that needs it turns it on here.
    tem_declaracao_partes: bool = False
    # [Q1] Notice + cure period before rescisão — answered: NOT standard → none.
    rescisao_cura_dias: Optional[int] = None
    # [Q1] Resolutiva mora constituted by e-mail notice — answered: NOT
    # standard → OFF.
    resolutiva_notificacao_email: bool = False

    # [Q2] Answered: cite the Lei 6.515/77 for every CASAMENTO (not união
    # estável), by the marriage date: on/after this day → ", na vigência da
    # Lei 6.515/77"; before → ", anterior à vigência da Lei 6.515/77". A
    # casado without `Pessoa.data_casamento` is `faltando`.
    lei_6515_vigencia_desde: date = date(1977, 12, 26)

    # [Q3] Answered: the multa rescisória IS the sinal's valor, always.
    # Fixed rule (contexto `multa_rescisoria`) — no override field.

    # [Q4] Answered: rescisão ¶2 is always "multa (valor do sinal) + every
    # cost proven to have been generated during the purchase-and-sale process
    # up to the rescisão", paid by the party that caused it. Fixed wording in
    # `modelo_texto` — the honorários/custos/nenhum variants are gone.

    # [Q5] Answered: the corretagem % owed on rescisão is the deal's
    # `pct_comissao`, always. Fixed rule (contexto `corretagem.pct_rescisao`).

    # [Q6] Answered: FGTS + financiamento are ONE parcela. A `financiamento`
    # parcela with `Financiamento.fgts` reads "através do uso de FGTS e
    # financiamento imobiliário"; a separate `tipo='fgts'` parcela BLOCKS
    # (PARCELA_FGTS_SEPARADA). Fixed rule — no toggle.

    # [Q7] Answered: `tipo='saldo'` is the open financing balance on the
    # imóvel, to be paid off. A saldo parcela without an active ônus BLOCKS
    # (SALDO_SEM_ONUS). Fixed rule.

    # [Q8] Answered: the system-emitted `tjsp` certidão IS the TJSP document
    # (it stands in for `tjsp_esaj` when no manual one exists);
    # `trf3_sp` → 1ª instância, `trf3` → 2ª instância. Fixed rule.

    # [Q9] Answered: a parte's company (CNPJ consulta) is certified when it
    # is `ativa` or `inapta`, or `baixada` less than this many years before
    # the assinatura (the group is then titled "… - Baixada"); `suspensa` /
    # `nula` / older baixadas are omitted.
    pj_baixada_janela_anos: int = 5
    # [Q9] Answered: when the last registered transfer of ownership of the
    # imóvel (compra e venda, permuta, dação em pagamento, arrematação —
    # `titulo_service.NATUREZAS_ULTIMA_TRANSFERENCIA`) happened less than
    # this many years before the assinatura, the previous owner(s) present
    # full certidões too.
    antigo_proprietario_janela_anos: int = 5

    # [Q10] Answered: EVERY certidão must have been emitted less than this
    # many days before the assinatura ((assinatura − emitida_em).days < N);
    # a stated `validade_ate` is still checked on top. No per-tipo default
    # validity any more.
    certidao_max_dias: int = 30

    # [Q11] Answered: pendências prazo defaults to 10 days — used when neither
    # the contract (`DadosContrato.prazo_pendencias_dias`) nor the office
    # (`Imobiliaria.prazo_pendencias_padrao_dias`) sets one.
    prazo_pendencias_padrao_dias: int = 10
    prazo_esclarecimentos_dias: int = 10
    # [Q11] Answered: the estado-civil certidão must be less than 90 days old
    # at the assinatura (`Pessoa.certidao_estado_civil_emitida_em`).
    certidao_estado_civil_max_dias: int = 90

    # [Q12] Answered: the posse multa diária is the office's value
    # (`Imobiliaria.posse_multa_diaria`, missing → faltando) and applies in
    # permuta too — the same daily fine for each party's delivery.

    # [Q13] Answered: registry costs + ITBI of each imóvel are paid by the
    # party RECEIVING it. Fixed permuta wording in `modelo_texto`.

    # [Q14] Answered: keep each signatory's e-mail beside the name (D4sign);
    # witnesses print their CPF (not RG) — the gate requires the CPF.

    # [Q15] Answered: contract 01's split and 08's card price were DATA
    # errors — no code default. The gate keeps blocking any Σ parcelas ≠
    # valor_negociado (bloqueio SOMA_PARCELAS_DIFERENTE_DO_PRECO).


POLITICA_PADRAO = Politica()

__all__ = [
    "EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO",
    "ONUS_COM_SALDO",
    "ONUS_SUPORTADOS",
    "PAPEL_ANTIGO_PROPRIETARIO",
    "POLITICA_PADRAO",
    "Politica",
    "SITUACAO_PJ_BAIXADA",
    "SITUACOES_CADASTRAIS",
    "SITUACOES_PJ_EXIGIDAS",
]
