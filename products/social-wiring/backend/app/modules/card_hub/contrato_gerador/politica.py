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

#: [Migration 193] The usufruto the seller must cancel (corpus deal 839's
#: objeto paragraph — worded ONLY as a precondition of the buyers'
#: financing, so `derivacao._imovel` blocks it without a financiamento).
ONUS_USUFRUTO = "usufruto"

#: `situacao_onus` values the generator can word today. `penhora`,
#: `indisponibilidade` and `outro` have no clause in the signed contracts
#: (corpus catalog §4: 0 real cases — only boilerplate "livre de penhoras")
#: — generating would print "livre de ônus" over a real one, so they BLOCK
#: rather than fall through.
ONUS_SUPORTADOS: tuple[str, ...] = ("livre", ONUS_USUFRUTO) + ONUS_COM_SALDO

#: Spec §3 #16 — whether the CND-de-condomínio pendência applies is derived from
#: `imoveis.empreendimento` (A named rule, not an inline truthiness test).
#: Since 2026-10-05 this NO LONGER drives the vistoria clause's wording: that
#: defaults to the condomínio wording (91/93 signed) unless the card says
#: explicitly the imóvel is not in a condomínio (`imovel_dados.em_condominio`,
#: migration 202).
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


# ─── Termos fixos do escritório ──────────────────────────────────────────
#
# The office's STANDARD legal terms, printed verbatim in every contract
# (`modelo_texto.TERMOS_FIXOS` splices them into the wording). Not one of the
# Q1–Q15 answers and not a per-deal value: they come from the office's own
# signed contracts, which all carry these exact terms. Kept here, named, so a
# change to the office standard is ONE reviewed edit in the policy file —
# never a hunt through clause text. Each value is the EXACT printed phrase
# (number + por extenso), so moving it here changed no wording.
#
#: Confissão de dívida (encargo I) and DA MORA — multa moratória.
MULTA_MORATORIA = "2% (dois por cento)"
#: Confissão de dívida (encargo II) and DA MORA — juros moratórios ao mês.
JUROS_MORATORIOS_AM = "1% (um por cento)"
#: Confissão de dívida (encargo III) and DA MORA — correção monetária.
INDICE_CORRECAO_MONETARIA = "IGPM"
#: Confissão de dívida — the delay that accelerates every vincenda.
VENCIMENTO_ANTECIPADO_ATRASO = "30 (trinta) dias"
#: Confissão de dívida — the missed-parcelas count that accelerates them.
VENCIMENTO_ANTECIPADO_PARCELAS = "02 (duas) parcelas"
#: Irretratabilidade — how long the vendedor has to refund on rescisão.
PRAZO_DEVOLUCAO_RESCISAO = "2 dias úteis"
#: Tributos — how long after the posse the cadastros must be updated.
PRAZO_ATUALIZACAO_CADASTROS = "30 dias"


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

    # [Q3] Answered: the multa rescisória IS the sinal's valor, always — the
    # SUM of the sinal parcelas when the sinal is paid in tranches (owner,
    # 2026-10-03). Fixed rule (contexto `multa_rescisoria`) — no override.

    # [Q4] Answered: rescisão ¶2 is always "multa (valor do sinal) + every
    # cost proven to have been generated during the purchase-and-sale process
    # up to the rescisão", paid by the party that caused it. Fixed wording in
    # `modelo_texto` — the honorários/custos/nenhum variants are gone.

    # [Q5] Answered: the corretagem % owed on rescisão is the deal's
    # `pct_comissao`, always. Fixed rule (contexto `corretagem.pct_rescisao`).

    # [Q6] Answered: FGTS + financiamento are ONE printed parcela. Revised
    # 2026-10-03 against the signed contracts (the old "através do uso de
    # FGTS e financiamento imobiliário" appears in 0/34): the parcela reads
    # "onde será utilizado {FGTS}, por meio do uso das contas vinculadas ao
    # FGTS e {FIN} por meio de recursos de financiamento imobiliário …" when
    # the split is known (`Parcela.valor_fgts`, migration 192, OR a separate
    # `tipo='fgts'` parcela, which joins the financing parcela's line), and
    # the combined "por meio do uso das contas vinculadas ao FGTS e de
    # recursos de financiamento …" otherwise. Fixed rule — no toggle.

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
    # [Q11] The estado-civil certidão must be less than N days old at the
    # assinatura (`Pessoa.certidao_estado_civil_emitida_em`). N = 30 by owner
    # decision 2026-10-05 (83 signed contracts say 30); the earlier [Q11]
    # answer, 90, is superseded. The ONE constant: the readiness age rule
    # (`derivacao`) and the pendência wording (`frases`) both read it.
    certidao_estado_civil_max_dias: int = 30
    # [P5 F8, 2026-10-03] A non-owner who signs as a seller's COMPANION
    # (união estável — or the partner of a seller whose own estado civil is
    # solteiro/divorciado/viúvo/separado, i.e. not married to them) is NOT a
    # certificando: the signed corpus (deal 867) presents no certidão group
    # for her. The owner rule "the cônjuge of a married vendedor IS a
    # vendedor" stays exactly that — MARRIED. True = the office wants the
    # companion's full certidão set too.
    companheiro_apresenta_certidoes: bool = False

    # [Q12] Answered: the posse multa diária is the office's value
    # (`Imobiliaria.posse_multa_diaria`, missing → faltando) and applies in
    # permuta too — the same daily fine for each party's delivery.

    # [Q13] Answered: registry costs + ITBI of each imóvel are paid by the
    # party RECEIVING it. Fixed permuta wording in `modelo_texto`.

    # [Q14] Answered: keep each signatory's e-mail beside the name (D4sign);
    # witnesses print their CPF (not RG) — the gate requires the CPF.
    # Re-confirmed 2026-10-05 although every signed contract prints RG: "with
    # the CIN changes, soon the RG number will no longer exist, only CPFs".

    # [Q15] Answered: contract 01's split and 08's card price were DATA
    # errors — no code default. The gate keeps blocking any Σ parcelas ≠
    # valor_negociado (bloqueio SOMA_PARCELAS_DIFERENTE_DO_PRECO).

    # [D2 → one final review, owner decision 2026-09-30, verbatim: asked
    # "replace the per-field confirmations with one final review of the
    # finished contract by the legal team?" → "yes"; standing directive:
    # "Human reviews are meant to be the exception, not the rule."]
    #
    # True (the answer): `service.gerar` no longer waits for a per-field
    # accept/reject of every machine-extracted value (migration 156's gate).
    # It generates, and the version RECORDS which contract-feeding values
    # were machine-derived and not yet human-validated
    # (`atendimento_contrato_versoes.revisao_juridica_campos`, migration
    # 177). Such a version is "aguardando revisão jurídica" until ONE
    # contract-level "Aprovar revisão jurídica" (`revisao_juridica.aprovar`)
    # — which also confirms every recorded value on its own row, so the
    # provenance stays truthful. Sending it for signature, and "Baixar para
    # impressão", require that approval. Open extraction CONFLICTS still
    # block `gerar`: two readings disagree and the system cannot tell which
    # one the contract should print — that is the exception a human exists
    # for, not a confirmation.
    #
    # False: the pre-2026-09-30 per-field gate (`validacao_extracao.
    # exigir_sem_pendentes`), kept verbatim for rollback. This is the ONE
    # source of truth — `matriculas.autopiloto_service.
    # REVISAO_FINAL_UNICA_POR_CONTRATO` reads it, never a second copy.
    revisao_final_unica: bool = True


POLITICA_PADRAO = Politica()

__all__ = [
    "EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO",
    "INDICE_CORRECAO_MONETARIA",
    "JUROS_MORATORIOS_AM",
    "MULTA_MORATORIA",
    "PRAZO_ATUALIZACAO_CADASTROS",
    "PRAZO_DEVOLUCAO_RESCISAO",
    "VENCIMENTO_ANTECIPADO_ATRASO",
    "VENCIMENTO_ANTECIPADO_PARCELAS",
    "ONUS_COM_SALDO",
    "ONUS_SUPORTADOS",
    "ONUS_USUFRUTO",
    "PAPEL_ANTIGO_PROPRIETARIO",
    "POLITICA_PADRAO",
    "Politica",
    "SITUACAO_PJ_BAIXADA",
    "SITUACOES_CADASTRAIS",
    "SITUACOES_PJ_EXIGIDAS",
]
