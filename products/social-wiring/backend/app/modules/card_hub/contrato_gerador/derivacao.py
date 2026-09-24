"""Switches, derived modelo, completeness gate and consistency checks (spec §1, §5).

Pure over `DadosContrato`. Three outputs, never mixed:

- `faltando`  — a value the contract needs and nobody has entered. Named field
                + pt-BR label + where in the card it is fixed + a machine-usable
                `destino` the UI links to + `sugestoes` (S2, additive): which
                `tipo_documento`(s) — `proveniencia.fontes.FONTES` — could
                supply it, `[]` when none does (most negotiation/office
                fields genuinely have no document behind them).
- `bloqueios` — the data is there but contradicts itself, the law of the
                instrument, or the wording the office actually wrote
                (Σ parcelas ≠ preço, RG = CPF, old certidão, a stored enum with
                no clause).
- `avisos`    — generation proceeds, but a human should know.

`pronto` is `not faltando and not bloqueios`. A switch that needs a MISSING
field adds a `faltando`; optional wording whose switch is off is omitted.
The office's policy answers (spec §6.2, answered 2026-09-15) are cited as
[Qn] next to the rule that implements each — see `politica.py`.

🔴 NOTHING HERE IS "NOT IN THE SYSTEM" ANY MORE. Migrations 114-118 gave every
spec §6.1 field real storage (see `dados`'s module docstring), so a gap is now
always an un-filled FORM, never a missing column — which is why every refusal
can name a screen. The two things still genuinely absent are named as such:
procurador/inventariante wording (`PAPEIS_SEM_REDACAO`) and the stored-but-
unwritten clauses (`ja_quitado`, `obrigacoes_vendedor`,
`permuta_obrigacoes_entrega`).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from noctusai_lib.domain.texto_ptbr import formatar_brl, parse_brl
from noctusai_lib.integrations.documents import derivar_endereco, has_raw_markup
from noctusai_lib.integrations.documents.cpf import is_valid as cpf_valido

from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.concordancia import normalizar_genero
from app.modules.card_hub.contrato_gerador.dados import (
    PAPEIS_SEM_REDACAO,
    Certidao,
    CertidaoImovel,
    DadosContrato,
    Empresa,
    Parcela,
    Pessoa,
    parcela_permuta,
    signatarios,
)
from app.modules.card_hub.contrato_gerador.numeracao import num2
from app.modules.card_hub.contrato_gerador.politica import (
    ONUS_COM_SALDO,
    ONUS_SUPORTADOS,
    PAPEL_ANTIGO_PROPRIETARIO,
    SITUACAO_PJ_BAIXADA,
    SITUACOES_CADASTRAIS,
    SITUACOES_PJ_EXIGIDAS,
    Politica,
)
from app.modules.card_hub.proveniencia import fontes as fontes_mod

MODELO_COMPRA_VENDA = "compra_venda"
MODELO_A_VISTA = "compra_venda_a_vista"
MODELO_PERMUTA = "compra_venda_permuta"

#: Parcelas paid into an account the contract must print (spec §5.1).
TIPOS_PAGOS_A_FAVORECIDO = frozenset({"sinal", "intermediaria", "direta", "saldo"})

ROTULO_QUALIFICACAO = {
    "nome_oficial": "Nome oficial",
    "nacionalidade": "Nacionalidade",
    "profissao": "Profissão",
    "estado_civil": "Estado civil",
    "rg": "RG",
    "rg_orgao_expedidor": "Órgão expedidor do RG",
    "cpf": "CPF",
    "endereco": "Endereço completo",
    "regime_bens": "Regime de bens",
    "conjuge": "Cônjuge vinculado",
    "conjuge_qualificacao": "Qualificação do cônjuge",
    "genero": "Gênero",
    "data_casamento": "Data do casamento",
}

#: The qualificação keys read off the ONE "Documento de identidade (RG e CPF)"
#: checklist item (2026-09-23). Their `falta` names that item, so the operator
#: knows the fix is to send the CIN or the CNH (or type the number) — not to
#: look for a separate "RG" upload that no longer exists.
_CHAVES_DO_DOCUMENTO_DE_IDENTIDADE = frozenset({"rg", "cpf"})
SUFIXO_DOCUMENTO_DE_IDENTIDADE = " (Documento de identidade: CIN ou CNH)"

#: [E1] `classificar_empresa` outcomes.
PJ_EXIGIDO = "exigido"
PJ_EXIGIDO_BAIXADA = "exigido_baixada"
PJ_OMITIDO = "omitido"
PJ_SEM_SITUACAO = "sem_situacao"
PJ_SEM_DATA_SITUACAO = "sem_data_situacao"
PJ_SITUACAO_DESCONHECIDA = "situacao_desconhecida"

#: [Q9] The title suffix of a recently-closed company's certidão group.
SUFIXO_PJ_BAIXADA = "Baixada"

#: The imóvel certidão group's print order (spec §2.5).
ORDEM_CERTIDOES_IMOVEL: tuple[str, ...] = ("matricula", "cnd_iptu", "cnd_condominio")


# ─── imóvel/matrícula address (2026-09-19) ─────────────────────────────────
#
# 🔴 At at least one tenant, the CRM/Vista mirror's PÚBLICO `imoveis.endereco`
# is a DELIBERATE DECOY: the office publishes the portaria/gatehouse address
# there — visible to agents outside the firm — and keeps the real property
# address only on the matrícula, so outside agents cannot harvest it. See
# `dados.Imovel.endereco`'s docstring and `KB § INTEGRATIONS/vista.md`.
#
# The posse clauses ("...a posse do imóvel situado à ...") must print the
# REGISTRY's own address, never that CRM field — a bank or a lawyer
# rejecting a signed instrument over a wrong address is a real business
# risk, not a hypothetical. `resolver_endereco_posse` below sources it, in
# order: (1) an operator-CONFIRMED override (`imovel_dados.
# endereco_registro_texto`, migration 139 — an escape hatch for a
# matrícula whose phrasing defeats derivation), else (2) DERIVED from the
# matrícula itself via the seed's `derivar_endereco` (the abertura's street
# + the LATEST averbação that officialises a número, or an explicit "s/nº").
# `None` — logradouro could not be confidently derived at all — is a named
# `faltando`, never a fallback to the CRM address: printing the gatehouse is
# worse than refusing.
#
# This is a SEPARATE signal from the coherence check just below:
# `_verificar_coerencia_endereco` compares the CRM's published street AND
# area against the matrícula and only ever `avisa`, never `bloqueia` — for
# the street per the office's explicit instruction (the divergence is the
# EXPECTED state under this business rule); for area because nobody has yet
# validated, against real data, that a beyond-tolerance mismatch never fires
# on a genuine same-property match (see `_verificar_coerencia_endereco`'s
# own docstring for the promotion recommendation). The one RELIABLE "this
# might be a different property" signal that already blocks is the
# matrícula NUMBER (`MATRICULA_DE_OUTRO_IMOVEL` in `_imovel` below).


def resolver_endereco_posse(
    confirmado: Optional[str], texto_imovel: str, texto_atos: str
) -> Optional[str]:
    """The short address ("Rua X, nº 100" / "Rua X, s/nº") a posse clause
    prints — the operator-confirmed override when set, else derived from the
    matrícula. `None` means neither source resolved a street: a genuine gap
    the caller must gate on (`Avaliacao.falta`), never a fallback to the CRM."""
    if confirmado:
        return confirmado
    endereco = derivar_endereco(texto_imovel, texto_atos)
    if not endereco.logradouro:
        return None
    if endereco.numero:
        return f"{endereco.logradouro}, nº {endereco.numero}"
    if endereco.numero_confirmado_ausente:
        return f"{endereco.logradouro}, s/nº"
    return None


#: [endereco-portaria-vs-imovel] Tolerance for the imóvel/matrícula AREA
#: coherence aviso (`_verificar_coerencia_endereco` below). An ABSOLUTE m²
#: tolerance rather than a percentage: the divergence this catches is
#: measurement/rounding noise between a brokerage-entered gross figure and
#: the registry's precise one (the reference case: 1052 vs 1.050,24 m² —
#: 1,76 m² apart), which does not scale with property size the way a
#: genuinely different property would (typically hundreds/thousands of m²
#: off). 2 m² comfortably covers that noise without hiding a real mismatch.
TOLERANCIA_AREA_M2 = Decimal("2")

#: "área [total|privativa|construída|do terreno] de 1.050,24 m²" / "...m2" —
#: matched against an accent/case-folded copy of the text (see
#: `_dobra_acentos`); the captured group is the BRL-shaped number
#: (`noctusai_lib.domain.texto_ptbr.parse_brl` already parses exactly this
#: "1.234,56" shape, reused rather than re-derived).
_AREA_RE = re.compile(
    r"AREA\s*(?:TOTAL|PRIVATIVA|CONSTRUIDA|DO\s+TERRENO)?\s*(?:DE|:)?\s*"
    r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*M[²2]"
)


def _dobra_acentos(texto: str) -> str:
    """Upper-case, accent-stripped — same fold `parse_brl`'s BRL grammar
    does not need but this module's free-text matching does (comparing a
    CRM street name / hunting an "área ... m²" phrase inside prose)."""
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)
    )
    return sem_acento.upper()


def _area_da_matricula(texto: str) -> Optional[Decimal]:
    """The first "área ... de X m²" figure quoted in `texto`, or `None` when
    none is found — never a guess, the caller treats `None` as "no signal",
    not as a mismatch."""
    if not texto:
        return None
    m = _AREA_RE.search(_dobra_acentos(texto))
    if not m:
        return None
    try:
        # The regex's captured group always carries `,\d{2}` — the same
        # shape `parse_brl` parses (its `formatar_brl` inverse).
        return parse_brl(m.group(1))
    except ValueError:
        return None


#: "nesta cidade, município e comarca de Carapicuíba" — the abertura's own
#: registry boilerplate. Deliberately narrow: "Foro e Comarca de Sorocaba"
#: (a citation INSIDE an averbação, about a DIFFERENT instrument) never
#: reads "município e comarca de" and so never matches.
_COMARCA_MUNICIPIO_RE = re.compile(r"munic[íi]pio\s+e\s+comarca\s+de\s+([^,;.\n]+)", re.IGNORECASE)
#: "Registro de imóveis da comarca de Cotia – SP" — the cartório's own
#: heading. Deliberately narrow: "registro civil da comarca de X" (a
#: person's marriage/birth registry, cited in a qualificação paragraph)
#: reads "civil", never "de imóveis", and so never matches either.
_COMARCA_REGISTRO_RE = re.compile(
    r"registro\s+de\s+im[óo]veis\s+da\s+comarca\s+de\s+"
    r"([^,;.\n\-–—]+?)(?:\s*[-–—]\s*([A-Za-z]{2}))?(?=[,;.\n]|$)",
    re.IGNORECASE,
)


def comarca_de_texto(texto: Optional[str]) -> Optional[str]:
    """[Owner directive, 2026-09-23] The DA ELEIÇÃO DO FORO clause's
    comarca, read off a matrícula's OWN transcription — never a manual
    field, never the imóvel's registration address (which can legitimately
    differ from the registering comarca). Called once at load time
    (`carregador.carregar`) over the resolved extraction's FULL raw text,
    independent of which acts the operator selected to quote — the comarca
    is a fact about the property's registry, not a clause excerpt.

    Matches ONLY the two shapes a matrícula's own abertura/registry
    boilerplate uses (see the two regexes above); `None` when neither is
    found — the caller (`_contrato`) treats that as a real gap to name,
    never a guess."""
    if not texto:
        return None
    m = _COMARCA_MUNICIPIO_RE.search(texto)
    if m:
        cidade = re.sub(r"\s+", " ", m.group(1)).strip(" .")
        if cidade:
            return cidade
    m = _COMARCA_REGISTRO_RE.search(texto)
    if m:
        cidade = re.sub(r"\s+", " ", m.group(1)).strip(" .")
        if cidade:
            uf = m.group(2)
            return f"{cidade}/{uf.upper()}" if uf else cidade
    return None


def _verificar_coerencia_endereco(
    av: Avaliacao,
    *,
    logradouro: Optional[str],
    area: Optional[Decimal],
    texto_matricula: str,
    rotulo: str,
) -> None:
    """[owner-approved 2026-09-19; re-confirmed 2026-09-23] WARNING-ONLY:
    `logradouro` is the PROPERTY TABLE's address (owner rule 2026-09-23 —
    the manual override, `carregador._endereco_manual`, when an operator set
    one, else the CRM/Vista mirror as-is) and is NOT a reliable "same
    property?" signal against the matrícula, so a mismatch only ever
    `avisa`, never `bloqueia`. Two known-legitimate reasons a divergence is
    NOT an error, both already covered without special-casing (this stays a
    dumb substring check either way — the human reading the warning is the
    judge, not this function):
      · the portaria business rule — at least one tenant deliberately
        publishes the gatehouse address on the CRM's `imoveis.logradouro`
        rather than the unit's (see the module header above);
      · a condomínio's GATE address vs. a UNIT's own internal address (e.g.
        Vista's "Itália, 343" vs. the unit's actual "Alameda Alemanha, 535")
        — once an operator sets the internal address as the override
        (migration 159), `logradouro` here already reads the OVERRIDE, not
        the gate, so a genuine unit correctly stops divergent-warning
        against its own matrícula; only an UNSET override still compares
        the gate address and may still warn, which is the honest state
        ("nobody has confirmed the internal address yet"), not a bug.
    AREA is a much stronger signal — there is no policy reason to publish a
    fake square footage — but it is ALSO only an `avisa` here: this platform
    has not yet observed it in practice, and a false `bloqueia` on a
    legitimate rounding/measurement difference would refuse a real contract
    on a signal nobody has validated. Recommendation for a later pass: once
    real data confirms area divergence beyond tolerance never fires on a
    genuine same-property match, promote IT (not the street) to a
    `bloqueia`."""
    if logradouro and texto_matricula:
        alvo = _dobra_acentos(logradouro).strip()
        corpo = _dobra_acentos(texto_matricula)
        if alvo and alvo not in corpo:
            av.avisa(
                "ENDERECO_DIVERGENTE_DA_MATRICULA",
                f"O logradouro cadastrado do imóvel {rotulo} ('{logradouro}') não aparece "
                "na descrição da matrícula — pode ser a política de publicar o endereço da "
                "portaria em vez do imóvel, um condomínio cujo endereço interno da unidade "
                "diverge do endereço da portaria, ou um endereço realmente divergente; "
                "confira o endereço confirmado do registro antes de assinar.",
            )
    if area is not None:
        area_matricula = _area_da_matricula(texto_matricula)
        if area_matricula is not None and abs(area - area_matricula) > TOLERANCIA_AREA_M2:
            av.avisa(
                "AREA_DIVERGENTE_DA_MATRICULA",
                f"A área do CRM {rotulo} ({area} m²) diverge da área citada na matrícula "
                f"({area_matricula} m²) além da tolerância de {TOLERANCIA_AREA_M2} m² — "
                "confirme se é o mesmo imóvel.",
            )


# ─── destino: where a missing field is fixed ──────────────────────────────
#
# `onde` already grouped the readiness list by screen; `destino` makes that
# machine-usable so the UI can LINK instead of asking the operator to find it.
#
# `rota` is a REAL route from the SPA's own table (`frontend/src/App.tsx`);
# `ancora` is an in-screen target the screen already switches on — a card
# subpage key (`CardSubpageKey`, `frontend/src/components/card/
# CardSidebarNav.tsx`) or a Settings tab value.
#
# 🔴 A card destino names `/clientes` + the subpage, NOT a deep link. The card
# is a dialog the board opens with `open`/`onClose` props and it owns its
# subpage in local state (`ClienteCardDialog`), so there is no URL that opens
# it today. Emitting `?cliente=…` would be inventing a parameter the SPA
# ignores — the honest answer is the route that CAN show it plus the subpage
# to select. If deep-linking lands later, only this table changes.

#: onde -> (tela, rota, ancora padrão)
_DESTINO_POR_ONDE: dict[str, tuple[str, str, Optional[str]]] = {
    "partes": ("card_partes", "/clientes", "geral"),
    "certidoes": ("certidoes", "/certidoes", None),
    # [E1/E8] The card's Empresas tab (§F, `cardSubpages.ts`) — deal-scoped,
    # never routed through a person's `parte_id` (a `falta` here is per
    # EMPRESA, E4-deduped, not per owner).
    "empresas": ("card_empresas", "/clientes", "empresas"),
    "matricula": ("matriculas", "/matriculas", None),
    "imovel": ("imovel", "/imoveis", None),
    "negociacao": ("card_negociacao", "/clientes", "negociacao"),
    "financiamento": ("card_financiamento", "/clientes", "financiamento"),
    "contrato": ("card_contratos", "/clientes", "contratos"),
    "imobiliaria": ("configuracoes", "/configuracoes", "imobiliaria"),
}

#: The card subpage each side's parties live on — a vendedor is fixed on the
#: `vendedor` subpage, a comprador on `geral` (which carries the buyer panel).
_ANCORA_POR_LADO: dict[str, str] = {"vendedor": "vendedor", "comprador": "geral"}


@dataclass(frozen=True)
class Destinos:
    """The ids every `destino` needs to point somewhere concrete."""

    cliente_id: Optional[str] = None
    contrato_id: Optional[str] = None
    imovel_codigo: Optional[str] = None

    def para(
        self,
        onde: str,
        *,
        parte_id: Optional[str] = None,
        ancora: Optional[str] = None,
        alvo: Optional[str] = None,
    ) -> dict:
        tela, rota, ancora_padrao = _DESTINO_POR_ONDE[onde]
        escopo_imovel = onde in ("imovel", "matricula")
        if onde == "imovel" and self.imovel_codigo:
            rota = f"/imoveis/{self.imovel_codigo}"
        ids = {
            chave: valor
            for chave, valor in (
                ("cliente_id", self.cliente_id),
                ("contrato_id", self.contrato_id),
                ("parte_id", parte_id),
                ("imovel_codigo", self.imovel_codigo if escopo_imovel else None),
            )
            if valor
        }
        return {
            "tela": tela,
            "rota": rota,
            "ancora": ancora or ancora_padrao,
            # The CONTROL on that screen that answers the falta — a DOM id the
            # screen renders (`ALVO_*` below). `None` = the screen itself is
            # the answer. Lets "Resolver" land on the field, not just the page.
            "alvo": alvo,
            "ids": ids,
        }


#: DOM ids of the controls a `destino.alvo` may name. Declared here — the
#: producer — and rendered verbatim as `id=` by the screen that owns each
#: control, so the two halves share one spelling.
#:
#: - the Negociação subpage's "Termos do negócio" answers
#:   (`TermosNegocioSection`): the explicit itens-integrantes choice and the
#:   explicit ad-corpus sim/não.
#: - the imóvel page's documents card (`ImovelDocumentosCard`), where the
#:   matrícula the foro comarca is read from is uploaded.
ALVO_ITENS_INTEGRANTES = "termos-itens-integrantes-resposta"
ALVO_AD_CORPUS = "termos-ad-corpus-resposta"
ALVO_DOCUMENTOS_DO_IMOVEL = "imovel-documentos"


def _sugestoes_para_campo(campo: str) -> list[dict]:
    """`fontes.FONTES` candidates for a `falta()` `campo` string (S2,
    additive) — matched on its LAST dotted segment (`qualificacao.
    nome_oficial` -> `nome_oficial` -> canonical `nome` via `fontes.
    RENOMEADOS_CAMPO`, the same translation `REGISTRO` needs). Most
    `falta()` fields (negotiation terms, office data, testemunhas, ...) are
    genuinely `fontes.MANUAL_APENAS` — no document backs them — so `[]` is
    their honest answer, not a gap; `destino` is NOT set here (the caller
    already computed the one `destino` shared with the `faltando` entry
    itself and injects it)."""
    sufixo = campo.rsplit(".", 1)[-1]
    canonico = fontes_mod.RENOMEADOS_CAMPO.get(sufixo, sufixo)
    return [
        {
            "tipo_documento": f.tipo_documento,
            "rotulo": fontes_mod.ROTULOS_TIPO_DOCUMENTO.get(f.tipo_documento, f.tipo_documento),
        }
        for f in fontes_mod.FONTES.values()
        if canonico in f.campos
    ]


@dataclass
class Avaliacao:
    faltando: list[dict] = field(default_factory=list)
    bloqueios: list[dict] = field(default_factory=list)
    avisos: list[dict] = field(default_factory=list)
    destinos: Destinos = field(default_factory=Destinos)

    @property
    def pronto(self) -> bool:
        return not self.faltando and not self.bloqueios

    def falta(
        self,
        campo: str,
        rotulo: str,
        onde: str,
        parte_id: Optional[str] = None,
        *,
        ancora: Optional[str] = None,
        alvo: Optional[str] = None,
        destino_em: Optional[str] = None,
    ) -> None:
        """`onde` GROUPS the falta (the readiness list's section header);
        `destino_em` — default `onde` — is the screen the "Resolver" link
        opens, for the rare falta grouped under one screen but fixed on
        another (the foro comarca: a matrícula fact, fixed on the imóvel's
        documents)."""
        chave = (campo, parte_id)
        if any((f["campo"], f["parte_id"]) == chave for f in self.faltando):
            return
        destino = self.destinos.para(
            destino_em or onde, parte_id=parte_id, ancora=ancora, alvo=alvo
        )
        self.faltando.append(
            {
                "campo": campo,
                "rotulo": rotulo,
                "onde": onde,
                "parte_id": parte_id,
                "destino": destino,
                "sugestoes": [
                    {**s, "destino": destino} for s in _sugestoes_para_campo(campo)
                ],
            }
        )

    def bloqueia(self, codigo: str, mensagem: str) -> None:
        if not any(b["codigo"] == codigo and b["mensagem"] == mensagem for b in self.bloqueios):
            self.bloqueios.append({"codigo": codigo, "mensagem": mensagem})

    def avisa(self, codigo: str, mensagem: str) -> None:
        if not any(a["codigo"] == codigo and a["mensagem"] == mensagem for a in self.avisos):
            self.avisos.append({"codigo": codigo, "mensagem": mensagem})


# ─── dates ────────────────────────────────────────────────────────────────


def anos_antes(referencia: date, anos: int) -> date:
    """The same calendar day `anos` years earlier (29/02 → 28/02)."""
    try:
        return referencia.replace(year=referencia.year - anos)
    except ValueError:
        return referencia.replace(year=referencia.year - anos, day=28)


def ha_menos_de_anos(data: date, referencia: date, anos: int) -> bool:
    """True when `data` is LESS than `anos` years before `referencia` —
    exactly `anos` years earlier is not "less than"."""
    return data > anos_antes(referencia, anos)


def _hoje_padrao() -> date:
    """[E1/H2] The office's calendar date — the SAME computation as
    `contrato_gerador.service.hoje()`, duplicated here (not imported:
    `service.py` imports FROM this module, so the reverse import would
    cycle) so every caller of `derivar_switches`/`avaliar` that does not
    pass an explicit `hoje` still classifies empresas against TODAY, never
    the assinatura date. `service.py`'s `gerar`/`obter_geracao` should pass
    `hoje=hoje()` explicitly at integration — see this slice's delivery
    note (`service.py` is outside this file's ownership)."""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


# ─── switches ─────────────────────────────────────────────────────────────


def parcelas_ordenadas(d: DadosContrato) -> list[Parcela]:
    return sorted(d.parcelas, key=lambda p: p.ordem)


def numero_da_parcela(d: DadosContrato, parcela_id: Optional[str]) -> Optional[str]:
    """The printed number (`num2`) of the parcela an id NAMES, or None when it
    names one that is not in this deal. Used for [§6.1 #12]'s posse marco:
    the clause cites a COMPUTED number, never a typed one."""
    if not parcela_id:
        return None
    for i, p in enumerate(parcelas_ordenadas(d), start=1):
        if p.id == parcela_id:
            return num2(i)
    return None


def parcelas_antes_de(d: DadosContrato, parcela_id: Optional[str]) -> list[str]:
    """The numbers of the parcelas that fall BEFORE the marco parcela — the
    posse condition ("com a condição que as parcelas 01 e 02 …")."""
    numeros: list[str] = []
    for i, p in enumerate(parcelas_ordenadas(d), start=1):
        if p.id == parcela_id:
            return numeros
        numeros.append(num2(i))
    return []


def corretagem_marcos(d: DadosContrato) -> list[str]:
    """[§6.1 #23] The parcelas whose receipt triggers the corretagem payment,
    as computed numbers — the marco is `Parcela.dispara_corretagem` (114),
    never a typed parcela index."""
    return [
        num2(i) for i, p in enumerate(parcelas_ordenadas(d), start=1) if p.dispara_corretagem
    ]


def certidoes_imovel(d: DadosContrato) -> tuple[CertidaoImovel, ...]:
    """[§6.1 #14] The imóvel certidões the contract PRESENTS, in print order.

    A `matricula` row (migration 118) answers when there is one. When there is
    not, `imovel_dados.onus_certidao_em` + `numero_matricula` answer the SAME
    question for every card that predates 118 — the same fact from an older
    source, so it is composed here rather than making the contract ask for a
    matrícula certidão the office already has on file.
    """
    im = d.imovel
    if im is None:
        return ()
    por_tipo = {c.tipo: c for c in im.certidoes if c.emitida_em}
    if "matricula" not in por_tipo and im.onus_certidao_em and im.numero_matricula:
        por_tipo["matricula"] = CertidaoImovel(
            tipo="matricula", numero=im.numero_matricula, emitida_em=im.onus_certidao_em
        )
    return tuple(por_tipo[tipo] for tipo in ORDEM_CERTIDOES_IMOVEL if tipo in por_tipo)


def derivar_switches(
    d: DadosContrato, politica: Politica, referencia: Optional[date] = None
) -> dict[str, bool]:
    """Spec §1.1 — computed, never typed. `referencia` (default TODAY —
    `_hoje_padrao`, E1/H2) is the empresa-classification date `tem_pj_
    certidoes` needs; it is NEVER the assinatura (E2)."""
    referencia = referencia or _hoje_padrao()
    tipos = {p.tipo for p in d.parcelas}
    tem_financiamento = "financiamento" in tipos
    tem_parcelas_diretas = "direta" in tipos
    # 🔴 114: a permuta IS a parcela of tipo 'permuta' paid with linked
    # `permuta_ativos` — not the legacy one-asset `negociacao.permuta_ativo_id`.
    tem_permuta = parcela_permuta(d) is not None
    termos = d.termos
    return {
        "tem_financiamento": tem_financiamento,
        # [Q6] FGTS is part of the financiamento parcela, never its own.
        "tem_fgts": tem_financiamento and d.financiamento.fgts,
        "tem_intermediaria": "intermediaria" in tipos,
        "tem_permuta": tem_permuta,
        "tem_parcelas_diretas": tem_parcelas_diretas,
        "tem_confissao": any(p.tipo == "direta" and p.confissao_divida for p in d.parcelas),
        # 🔴 No parcelas at all is UNKNOWN, not à vista: a deal whose payment
        # still lives only in the legacy free-text field (e.g. a financed one)
        # was derived "à vista" by absence. `negociacao.parcelas` is already
        # `faltando` in that state, so the gate still blocks generation.
        "a_vista": bool(tipos)
        and not (tem_financiamento or "fgts" in tipos or tem_parcelas_diretas),
        "tem_saldo_devedor": bool(d.imovel and d.imovel.situacao_onus in ONUS_COM_SALDO),
        "tem_intermediacao": bool(d.intermediarios),
        "tem_itens_integrantes": bool((termos.itens_integrantes or "").strip()),
        "ad_corpus": bool(termos.ad_corpus),
        # [E1] A REQUIRED empresa (ativa/inapta/baixada-<5y from `referencia`),
        # not merely "some CNPJ certidão exists somewhere" (the old reading).
        "tem_pj_certidoes": bool(
            empresas_exigidas(d, {"tem_permuta": tem_permuta}, referencia, politica)
        ),
        "tem_declaracao_partes": politica.tem_declaracao_partes,
        # [Q12] the office's value, in every modelo (permuta included).
        "tem_multa_diaria_posse": d.imobiliaria.posse_multa_diaria is not None,
        # Migration 157 — a FÍSICA contract is printed and signed by hand:
        # no DA ASSINATURA DIGITAL clause, signature lines instead.
        "tem_assinatura_digital": d.modalidade_assinatura != "fisica",
    }


def modelo_derivado(switches: dict[str, bool]) -> str:
    """The `modelo` label the switches imply — a check, never a selector."""
    if switches["tem_permuta"]:
        return MODELO_PERMUTA
    if switches["a_vista"]:
        return MODELO_A_VISTA
    return MODELO_COMPRA_VENDA


def prazo_pendencias(d: DadosContrato, politica: Politica) -> int:
    """[Q11] contract override → office default → 10 days."""
    if d.prazo_pendencias_dias is not None:
        return d.prazo_pendencias_dias
    if d.imobiliaria.prazo_pendencias_padrao_dias is not None:
        return d.imobiliaria.prazo_pendencias_padrao_dias
    return politica.prazo_pendencias_padrao_dias


# ─── certidões index ──────────────────────────────────────────────────────


def tipos_exigidos(tipo_documento: str) -> list[str]:
    coluna = 3 if tipo_documento == "cpf" else 4
    return [c[0] for c in frases.CERTIDOES if c[coluna]]


def indice_certidoes(certidoes: list[Certidao], tipo_documento: str) -> dict[str, Certidao]:
    """tipo -> the result to print for ONE consulta kind. [Q8] The
    system-emitted `tjsp` certidão IS the TJSP document: it stands in for
    `tjsp_esaj` when no manual E-SAJ result exists."""
    idx: dict[str, Certidao] = {}
    for c in certidoes:
        if c.consulta_tipo_documento != tipo_documento:
            continue
        atual = idx.get(c.tipo)
        # Most recently emitted wins when a type was issued more than once.
        if atual is None or (c.emitida_em or date.min) > (atual.emitida_em or date.min):
            idx[c.tipo] = c
    if "tjsp_esaj" not in idx and "tjsp" in idx:
        idx["tjsp_esaj"] = idx["tjsp"]
    return idx


@dataclass(frozen=True)
class EmpresaExigida:
    """[E1] One company (E4-deduped: one `Empresa` row in `d.empresas` is
    one entry here even when both spouses hold a participação) whose
    certidão group is required — `sufixo` names it "Baixada" in the title
    when required-because-recently-closed; `owner` is the certificando
    `Pessoa` the check/falta is attributed to."""

    empresa: Empresa
    sufixo: Optional[str]
    owner: Pessoa


def _empresas_de_certificandos(d: DadosContrato, sw: dict[str, bool]) -> list[tuple[Empresa, Pessoa]]:
    """[E1/E3/E6] Every `d.empresas` row a certificando pessoa holds a
    participação in — signing vendedores + their cônjuges (E3: a married
    vendedor's cônjuge is a vendedor too), plus signing compradores +
    cônjuges when `tem_permuta` (E6: the comprador giving an imóvel gets
    exactly the vendedor treatment). Paired with the certificando `Pessoa`
    (from `empresa.owners`) the readiness report attributes it to — one
    pair per `Empresa` (E4; `d.empresas` already carries one row per
    DISTINCT company, `owners` holding every participant)."""
    certificandos = signatarios(d.vendedores) + (
        signatarios(d.compradores) if sw["tem_permuta"] else []
    )
    ids = {p.cliente_id for p in certificandos}
    ids |= {p.conjuge_cliente_id for p in certificandos if p.conjuge_cliente_id}
    pares: list[tuple[Empresa, Pessoa]] = []
    for e in d.empresas:
        dono = next((o for o in e.owners if o.cliente_id in ids), None)
        if dono is not None:
            pares.append((e, dono))
    return pares


def _conjuges_sem_pessoa(d: DadosContrato, sw: dict[str, bool]) -> list[Pessoa]:
    """[E3] Certificando vendedores (and, in a permuta, certificando
    compradores: E6) whose `conjuge_cliente_id` points at a cliente NOT
    loaded as a `Pessoa` anywhere on this card. E3 says the cônjuge of a
    married vendedor IS a vendedor, so a card that never added them is a
    genuine data gap — their empresas are unreachable, and the honest
    answer is a named `faltando` (the office must add them as a card
    party), never a silent exclusion from `owners`."""
    certificandos = signatarios(d.vendedores) + (
        signatarios(d.compradores) if sw["tem_permuta"] else []
    )
    ids_no_card = {p.cliente_id for p in d.vendedores + d.compradores}
    return [
        p for p in certificandos
        if p.conjuge_cliente_id and p.conjuge_cliente_id not in ids_no_card
    ]


def classificar_empresa(e: Empresa, referencia: date, politica: Politica) -> str:
    """[E1] Whether an empresa's certidão group is required, from its OWN
    Cartão-CNPJ-sourced `situacao_cadastral`/`data_situacao_cadastral`
    (never a certidão-consulta row, which may not exist yet): `ativa`/
    `inapta` always; `baixada` only when closed less than `pj_baixada_
    janela_anos` before `referencia` (TODAY — `_hoje_padrao`/`service.
    hoje()`, NEVER the assinatura: E2/H2); `suspensa`/`nula`/older baixadas
    are omitted. NULL `situacao_cadastral` (no Cartão uploaded yet)
    -> `PJ_SEM_SITUACAO`, the caller's `faltando: cartao_cnpj` (E1, H4)."""
    situacao = e.situacao_cadastral
    if situacao is None:
        return PJ_SEM_SITUACAO
    if situacao not in SITUACOES_CADASTRAIS:
        return PJ_SITUACAO_DESCONHECIDA
    if situacao in SITUACOES_PJ_EXIGIDAS:
        return PJ_EXIGIDO
    if situacao != SITUACAO_PJ_BAIXADA:
        return PJ_OMITIDO
    if e.data_situacao_cadastral is None:
        return PJ_SEM_DATA_SITUACAO
    if ha_menos_de_anos(e.data_situacao_cadastral, referencia, politica.pj_baixada_janela_anos):
        return PJ_EXIGIDO_BAIXADA
    return PJ_OMITIDO


def empresas_exigidas(
    d: DadosContrato, sw: dict[str, bool], referencia: date, politica: Politica
) -> list[EmpresaExigida]:
    """(empresa, title suffix, attributed owner) of each REQUIRED company —
    E1 classification against `referencia` (TODAY, never the assinatura).
    A company with no Cartão yet, or an unresolved baixada date, is NOT
    "required" here (it is a named `faltando`/`bloqueia` instead — see
    `_empresas_certidoes`, which walks EVERY certificando-owned company,
    not just this filtered set)."""
    saida: list[EmpresaExigida] = []
    for e, dono in _empresas_de_certificandos(d, sw):
        motivo = classificar_empresa(e, referencia, politica)
        if motivo == PJ_EXIGIDO:
            saida.append(EmpresaExigida(empresa=e, sufixo=None, owner=dono))
        elif motivo == PJ_EXIGIDO_BAIXADA:
            saida.append(EmpresaExigida(empresa=e, sufixo=SUFIXO_PJ_BAIXADA, owner=dono))
    return saida


def antigos_proprietarios(d: DadosContrato) -> list[Pessoa]:
    return [p for p in d.vendedores if p.papel == PAPEL_ANTIGO_PROPRIETARIO]


def exige_antigo_proprietario(d: DadosContrato, assinatura: date, politica: Politica) -> Optional[bool]:
    """[Q9] True when the last registered transfer of ownership is less than
    `antigo_proprietario_janela_anos` before the assinatura; `False` when a
    human confirmed there is none at all (`ultima_transferencia_sem_
    registro_confirmado`, migration 152 — an ANSWER, not a fallback); `None`
    = unknown (still faltando)."""
    if d.imovel is None:
        return None
    if d.imovel.ultima_transferencia_em is not None:
        return ha_menos_de_anos(
            d.imovel.ultima_transferencia_em, assinatura, politica.antigo_proprietario_janela_anos
        )
    if d.imovel.ultima_transferencia_sem_registro_confirmado:
        return False
    return None


def pessoas_certificadas(
    d: DadosContrato, sw: dict[str, bool], assinatura: date, politica: Politica
) -> list[Pessoa]:
    """Whose certidões the contract presents, in group order: the signing
    vendedores, the signing compradores in a permuta, then the previous
    owner(s) when [Q9] requires them."""
    pessoas = signatarios(d.vendedores) + (signatarios(d.compradores) if sw["tem_permuta"] else [])
    if exige_antigo_proprietario(d, assinatura, politica):
        pessoas += antigos_proprietarios(d)
    return pessoas


# ─── the gate ─────────────────────────────────────────────────────────────


def _nome(p: Pessoa) -> str:
    """A person as the readiness report names them. Without `nome_oficial`
    the card's own name still says WHO is meant — flagged, so it is never
    mistaken for the official one (which is what the instrument prints)."""
    if p.nome:
        return p.nome
    if p.nome_cadastro:
        return f"{p.nome_cadastro} (sem nome oficial)"
    return "(sem nome oficial)"


def _doc_norm(valor: Optional[str]) -> str:
    return re.sub(r"\W", "", (valor or "").upper())


def _ancora(p: Pessoa) -> str:
    return _ANCORA_POR_LADO.get(p.lado, "geral")


def _partes(av: Avaliacao, d: DadosContrato) -> None:
    vend, comp = signatarios(d.vendedores), signatarios(d.compradores)
    antigos = antigos_proprietarios(d)
    if not vend:
        av.falta("partes.vendedores", "Ao menos um vendedor (proprietário) no card", "partes", ancora="vendedor")
    if not comp:
        av.falta("partes.compradores", "Ao menos um comprador no card", "partes")
    for p in d.vendedores + d.compradores:
        if p not in vend and p not in comp and p not in antigos:
            av.avisa(
                "PARTE_NAO_SIGNATARIA",
                f"{_nome(p)} ({p.papel}) não entra na qualificação nem assina o contrato.",
            )

    documentos: dict[str, str] = {}
    for lado_pessoas in (vend, comp):
        ids_lado = {p.cliente_id: p for p in lado_pessoas}
        for p in lado_pessoas:
            for chave in p.faltando_qualificacao:
                conjuge = ids_lado.get(p.conjuge_cliente_id or "")
                if chave == "conjuge_qualificacao" and conjuge is not None:
                    continue  # the spouse is a signatory and is gated on their own
                # [Owner directive, 2026-09-23] "all those data are
                # mandatory for the deal contract" — `profissao` is no
                # longer waved through with `PARTE_SEM_PROFISSAO` (a
                # 2026-09-22 aviso arguing the office's own reference
                # contract 08 qualifies a party with none): it now blocks
                # like every other qualificação field, generic path below.
                sufixo = (
                    SUFIXO_DOCUMENTO_DE_IDENTIDADE
                    if chave in _CHAVES_DO_DOCUMENTO_DE_IDENTIDADE
                    else ""
                )
                av.falta(
                    f"qualificacao.{chave}",
                    f"{ROTULO_QUALIFICACAO.get(chave, chave)}{sufixo} — {_nome(p)}",
                    "partes",
                    p.parte_id,
                    ancora=_ancora(p),
                )
            if normalizar_genero(p.genero) is None:
                av.falta("qualificacao.genero", f"Gênero — {_nome(p)}", "partes", p.parte_id, ancora=_ancora(p))
            if p.papel in PAPEIS_SEM_REDACAO:
                # [§6.1 #20] Genuinely absent: no sample contract qualifies a
                # procurador/inventariante, so there is no wording to generate.
                av.falta(
                    f"qualificacao.{p.papel}",
                    f"Redação de {p.papel} (procuração/inventário) — {_nome(p)}: "
                    "o gerador não tem texto para este papel",
                    "partes",
                    p.parte_id,
                    ancora=_ancora(p),
                )
            # [Q14] the e-mail is printed beside the name in the signature
            # block — of a DIGITAL contract only; a física one (migration
            # 157) prints name + CPF under a signature line, no e-mail.
            if not p.email and d.modalidade_assinatura != "fisica":
                av.avisa("PARTE_SEM_EMAIL", f"{_nome(p)} não tem e-mail; o bloco de assinatura sai sem ele.")
            if p.cpf and not cpf_valido(p.cpf):
                av.bloqueia("CPF_INVALIDO", f"O CPF de {_nome(p)} não confere (dígitos verificadores).")
            # [Owner revision, 2026-09-23 — supersedes the 2026-09-22
            # RG_IGUAL_CPF aviso] "Documento de identidade (RG e CPF)" is
            # ONE checklist item per person, already blocking: `rg`/`cpf`
            # are both `documento_checklist_service._CAMPOS_QUALIFICACAO_
            # CONTRATO` entries, so a MISSING one already reaches `av.falta`
            # via `faltando_qualificacao` above, naming exactly which is
            # absent — no separate check needed. An RG that happens to read
            # identical to the CPF is not itself an error: the Carteira de
            # Identidade Nacional (CIN) uses the CPF number as the identity
            # number BY DESIGN (contract 08 qualifies "TAUANE GONÇALVES DIAS
            # ... RG 448.864.938-66-IIGDR-SP e inscrita no CPF/MF
            # 448.864.938-66", correctly) — so the collision itself needs no
            # confirmation and is never checked here.
            for valor in (p.cpf, p.rg):
                norm = _doc_norm(valor)
                if not norm:
                    continue
                dono = documentos.setdefault(norm, p.cliente_id)
                if dono != p.cliente_id:
                    av.bloqueia(
                        "DOCUMENTO_DUPLICADO",
                        f"{_nome(p)} tem RG/CPF igual ao de outra parte do contrato.",
                    )

            if p.estado_civil in frases.ESTADOS_EM_NUCLEO and p.conjuge_cliente_id:
                conjuge = ids_lado.get(p.conjuge_cliente_id)
                if conjuge is None:
                    av.bloqueia(
                        "CONJUGE_FORA_DO_LADO",
                        f"O cônjuge/companheiro(a) de {_nome(p)} precisa estar no mesmo lado do contrato.",
                    )
                    continue
                if conjuge.conjuge_cliente_id != p.cliente_id:
                    av.bloqueia("CONJUGE_NAO_RECIPROCO", f"O vínculo de cônjuge de {_nome(p)} não é recíproco.")
                if p.estado_civil == "casado":
                    if (p.regime_bens or "") != (conjuge.regime_bens or ""):
                        av.bloqueia("REGIME_DIVERGENTE", f"{_nome(p)} e o cônjuge têm regimes de bens diferentes.")
                    if p.regime_bens == "separacao_total":
                        av.avisa(
                            "CONJUGE_SEPARACAO_TOTAL",
                            f"{_nome(p)} é casado(a) em separação total; o cônjuge ainda assina.",
                        )
                    # [Q2] the date decides the Lei 6.515/77 wording.
                    if p.data_casamento is None:
                        av.falta(
                            "qualificacao.data_casamento",
                            f"Data do casamento (Lei 6.515/77) — {_nome(p)}",
                            "partes",
                            p.parte_id,
                            ancora=_ancora(p),
                        )
                    elif conjuge.data_casamento is not None and conjuge.data_casamento != p.data_casamento:
                        av.bloqueia(
                            "DATA_CASAMENTO_DIVERGENTE",
                            f"{_nome(p)} e o cônjuge têm datas de casamento diferentes.",
                        )


def _imovel(av: Avaliacao, d: DadosContrato, sw: dict[str, bool], politica: Politica, assinatura: date) -> None:
    im = d.imovel
    if im is None:
        av.falta("negociacao.imovel", "Imóvel negociado no card", "negociacao")
        return
    for campo, rotulo in (
        ("logradouro", "Logradouro do imóvel"),
        ("numero", "Número do imóvel"),
        ("cidade", "Cidade do imóvel"),
        ("uf", "UF do imóvel"),
    ):
        if not getattr(im.endereco, campo):
            av.falta(f"imovel.{campo}", rotulo, "imovel")
    for campo, rotulo in (
        ("numero_matricula", "Número da matrícula"),
        ("numero_registro_imoveis", "Cartório de registro de imóveis"),
        ("inscricao_municipal", "Inscrição municipal (cadastro na prefeitura)"),
    ):
        if not getattr(im, campo):
            av.falta(f"imovel.{campo}", rotulo, "imovel")

    if d.matricula.num_atos == 0 or not d.matricula.texto.strip():
        av.falta("matricula.atos", "Atos da matrícula selecionados para o contrato", "matricula")
    elif d.matricula.codigo != im.codigo:
        av.bloqueia(
            "MATRICULA_DE_OUTRO_IMOVEL",
            "Os atos selecionados são de uma matrícula de outro imóvel.",
        )
    # 🔴 The highest-value check in this file: text with a literal `**`/`<u>`
    # marker reaching a SIGNED DEED is the actual harm — a pre-migration-135
    # transcription (or a malformed vision reply `parse_markup` had to keep
    # literal) quoted verbatim into a legal instrument. This runs on the
    # ACTUAL quoted text (the selected acts' concatenation), independent of
    # `matricula_extracoes.possui_marcacao_bruta`, so it also catches a
    # markered act inside an otherwise-clean extraction.
    if d.matricula.texto and has_raw_markup(d.matricula.texto):
        av.bloqueia(
            "MATRICULA_COM_MARCACAO_BRUTA",
            "O texto da matrícula selecionado contém marcação de formatação "
            "bruta (** ou <u>) em vez de negrito/sublinhado — a transcrição "
            "precisa ser reenviada antes de entrar no contrato.",
        )
    if not im.titulo_aquisitivo_confirmado:
        av.falta("matricula.titulo_aquisitivo", "Título aquisitivo confirmado na matrícula", "matricula")
    # [§6.1 #8] Migration 115 stores the CONFIRMED wording on the imóvel.
    if not (im.titulo_aquisitivo_texto or "").strip():
        av.falta(
            "matricula.titulo_aquisitivo_texto",
            "Redação confirmada do título aquisitivo (instrumento, data, livro/folhas, tabelionato)",
            "matricula",
        )

    # 🔴 [endereco-portaria-vs-imovel] The posse clause's address — NEVER
    # `im.endereco` (the CRM/Vista mirror's público endereço; a deliberate
    # portaria/gatehouse decoy at at least one tenant — see this module's
    # "imóvel/matrícula address" section above). Confirmed override, else
    # derived from the matrícula; `None` is a named gap, never a fallback.
    # No atos selected yet for THIS contract is ALREADY named above
    # (`matricula.atos`) — without an override, there is nothing here to
    # derive FROM, so this stays quiet rather than repeating the same root
    # cause under a second name.
    if not resolver_endereco_posse(
        im.endereco_registro_texto,
        d.matricula.descricao_imovel_texto or d.matricula.texto,
        d.matricula.texto,
    ) and (im.endereco_registro_texto or (d.matricula.texto or "").strip()):
        av.falta(
            "imovel.endereco_registro_texto",
            "Endereço do imóvel confirmado a partir do registro (nunca o endereço "
            "público do CRM)",
            "imovel",
        )
    _verificar_coerencia_endereco(
        av,
        logradouro=im.endereco.logradouro,
        area=im.area_total,
        texto_matricula=d.matricula.descricao_imovel_texto or d.matricula.texto,
        rotulo="do imóvel",
    )

    if not im.situacao_onus:
        av.falta("imovel.situacao_onus", "Situação de ônus do imóvel", "imovel")
    elif im.situacao_onus not in ONUS_SUPORTADOS:
        av.bloqueia(
            "ONUS_NAO_SUPORTADO",
            f"O gerador não tem redação para ônus do tipo '{im.situacao_onus}'.",
        )

    _certidoes_do_imovel(av, d, politica, assinatura)

    if sw["tem_saldo_devedor"]:
        termos = d.termos
        if not im.onus_fonte_atos:
            av.falta("matricula.onus_fonte", "Atos da matrícula que registram o ônus", "matricula")
        elif any(a.kind not in ("R", "AV") or a.numero is None for a in im.onus_fonte_atos):
            av.bloqueia("ONUS_FONTE_INVALIDA", "O ônus aponta para um ato sem número (abertura).")
        # [§6.1 #11] Migration 115 stores the confirmed creditor on the imóvel,
        # read off the ônus acts — so it is fixed on the matrícula surface.
        if not im.onus_credor:
            av.falta("matricula.onus_credor", "Credor confirmado do financiamento que onera o imóvel", "matricula")
        if not termos.onus_quitacao:
            av.falta("negociacao.onus_quitacao", "Forma de quitação do saldo devedor", "negociacao")
        elif termos.onus_quitacao == frases.QUITACAO_ONUS_SEM_REDACAO:
            # Stored by 114, but no sample contract has this clause — refusing
            # by name beats printing a paragraph the office never wrote.
            av.bloqueia(
                "ONUS_QUITACAO_SEM_REDACAO",
                "A quitação do ônus está marcada como 'já quitado (com termo)', e o gerador "
                "ainda não tem redação para esse caso — nenhum contrato modelo o traz.",
            )
        elif termos.onus_quitacao not in frases.QUITACOES_ONUS:
            av.bloqueia("ONUS_QUITACAO_INVALIDA", f"Forma de quitação desconhecida: {termos.onus_quitacao}.")
        elif termos.onus_quitacao == "compradores_prazo" and not termos.onus_prazo_dias:
            av.falta("negociacao.onus_prazo_dias", "Prazo (dias) para os compradores quitarem o saldo", "negociacao")
        elif termos.onus_quitacao == "parcela" and not any(p.tipo == "saldo" for p in d.parcelas):
            av.bloqueia("ONUS_QUITACAO_SEM_PARCELA_SALDO", "A quitação do ônus é por parcela, mas não há parcela de saldo.")


def _certidoes_do_imovel(
    av: Avaliacao, d: DadosContrato, politica: Politica, assinatura: date
) -> None:
    """[§6.1 #14 / Q10] The imóvel's own certidões (migration 118) answer to
    the SAME 30-day rule as a party's — an old IPTU CND is as stale on the
    signing table as an old federal one."""
    for c in certidoes_imovel(d):
        rotulo = (
            "Certidão da matrícula"
            if c.tipo == "matricula"
            else frases.CERTIDOES_IMOVEL_ROTULO[c.tipo]
        )
        if c.emitida_em is None:  # pragma: no cover — `certidoes_imovel` filters these out
            continue
        if c.emitida_em > assinatura:
            av.bloqueia(
                "CERTIDAO_IMOVEL_EMITIDA_APOS_ASSINATURA",
                f"{rotulo} do imóvel tem emissão posterior à assinatura.",
            )
        elif (assinatura - c.emitida_em).days >= politica.certidao_max_dias:
            av.bloqueia(
                "CERTIDAO_IMOVEL_EMISSAO_ANTIGA",
                f"{rotulo} do imóvel foi emitida há {(assinatura - c.emitida_em).days} dias; "
                f"precisa ter menos de {politica.certidao_max_dias} dias na data da assinatura.",
            )
        if c.validade_ate is not None and c.validade_ate < assinatura:
            av.bloqueia("CERTIDAO_IMOVEL_VENCIDA", f"{rotulo} do imóvel está vencida na data da assinatura.")
        if c.resultado in frases.RESULTADOS_COM_APONTAMENTO:
            av.avisa(
                "CERTIDAO_IMOVEL_COM_APONTAMENTO",
                f"{rotulo} do imóvel não é negativa; exige esclarecimentos.",
            )


def _negociacao(av: Avaliacao, d: DadosContrato, sw: dict[str, bool], assinatura: date) -> None:
    if d.valor_negociado is None:
        av.falta("negociacao.valor_negociado", "Valor negociado", "negociacao")
    parcelas = parcelas_ordenadas(d)
    if not parcelas:
        av.falta("negociacao.parcelas", "Parcelas do preço", "negociacao")
    else:
        sinais = [p for p in parcelas if p.tipo == "sinal"]
        if not sinais:
            av.falta("negociacao.parcela_sinal", "Parcela de sinal", "negociacao")
        elif len(sinais) > 1:
            av.bloqueia("MAIS_DE_UM_SINAL", "O contrato admite exatamente uma parcela de sinal.")
        if len([p for p in parcelas if p.tipo == "permuta"]) > 1:
            # The permuta clauses speak about "the" permuta parcela; with two,
            # which one they mean is a guess.
            av.bloqueia("MAIS_DE_UMA_PARCELA_PERMUTA", "O contrato admite no máximo uma parcela de permuta.")

    favorecidos = {f.id: f for f in d.favorecidos}
    cpfs_vendedores = {frases.so_digitos(p.cpf) for p in signatarios(d.vendedores) if p.cpf}
    ultimo_venc: Optional[date] = None
    for i, p in enumerate(parcelas, start=1):
        rot = f"Parcela {num2(i)}"
        if p.valor is None or p.valor <= 0:
            av.falta(f"negociacao.parcela.{p.id}.valor", f"Valor da {rot}", "negociacao")
        if not p.vencimento and not (p.evento or "").strip() and p.tipo != "permuta":
            # A permuta parcela is settled by the deed, not on a date: its
            # wording carries the imóveis, never a vencimento/evento.
            av.falta(f"negociacao.parcela.{p.id}.momento", f"Vencimento ou evento da {rot}", "negociacao")
        if p.tipo in TIPOS_PAGOS_A_FAVORECIDO:
            if not p.favorecido_id:
                av.falta(f"negociacao.parcela.{p.id}.favorecido", f"Favorecido da {rot}", "negociacao")
            else:
                fav = favorecidos.get(p.favorecido_id)
                if fav is None:
                    av.bloqueia("FAVORECIDO_INEXISTENTE", f"O favorecido da {rot} não existe mais.")
                else:
                    if not fav.conta and not fav.pix:
                        av.falta(f"negociacao.favorecido.{fav.id}.conta", f"Conta ou chave PIX de {fav.nome}", "negociacao")
                    if fav.conta and not (fav.banco and fav.agencia):
                        av.falta(f"negociacao.favorecido.{fav.id}.banco", f"Banco e agência de {fav.nome}", "negociacao")
                    if frases.so_digitos(fav.cpf_cnpj) not in cpfs_vendedores:
                        av.avisa("FAVORECIDO_TERCEIRO", f"{fav.nome} ({rot}) não é um dos vendedores.")
            if not (p.forma_pagamento or "").strip():
                av.falta(f"negociacao.parcela.{p.id}.forma_pagamento", f"Forma de pagamento da {rot}", "negociacao")
        if "financiamento" in (p.evento or "").lower() and not sw["tem_financiamento"]:
            av.bloqueia("EVENTO_CITA_FINANCIAMENTO", f"A {rot} cita financiamento, mas não há parcela de financiamento.")
        # [Q7] saldo = the open financing balance on the imóvel, paid off.
        if p.tipo == "saldo" and not sw["tem_saldo_devedor"]:
            av.bloqueia("SALDO_SEM_ONUS", f"A {rot} é de saldo (quitação do financiamento que onera o imóvel), mas o imóvel não tem ônus.")
        if p.confissao_divida and p.tipo != "direta":
            av.bloqueia("CONFISSAO_EM_PARCELA_NAO_DIRETA", f"Só parcelas diretas entram na confissão de dívida ({rot}).")
        if p.vencimento:
            if ultimo_venc is not None and p.vencimento <= ultimo_venc:
                av.bloqueia("VENCIMENTOS_FORA_DE_ORDEM", f"O vencimento da {rot} não é posterior ao da parcela anterior.")
            ultimo_venc = p.vencimento

    # [Q15] Σ parcelas must equal the price — the sample-contract errors were
    # data. The permuta value is one of the parcelas now (114), so it is in
    # this sum by construction rather than added on the side.
    if d.valor_negociado is not None and parcelas and all(p.valor is not None for p in parcelas):
        soma = sum((p.valor for p in parcelas), Decimal("0"))  # type: ignore[misc]
        if soma != d.valor_negociado:
            av.bloqueia(
                "SOMA_PARCELAS_DIFERENTE_DO_PRECO",
                f"As parcelas somam {formatar_brl(soma)}, mas o preço é {formatar_brl(d.valor_negociado)}.",
            )

    _posse(av, d, d.termos.posse_marco, d.termos.posse_prazo_dias, d.termos.posse_marco_parcela_id, escopo="posse")

    if sw["tem_confissao"]:
        if d.termos.confissao_juros_am is None:
            av.falta("negociacao.confissao_juros_am", "Juros remuneratórios ao mês da confissão de dívida", "negociacao")
        for i, p in enumerate(parcelas, start=1):
            if not p.confissao_divida:
                continue
            if not p.vencimento:
                av.falta(f"negociacao.parcela.{p.id}.vencimento", f"Vencimento da Parcela {num2(i)} (confissão de dívida)", "negociacao")
            elif p.vencimento <= assinatura:
                av.bloqueia("CONFISSAO_VENCIMENTO_PASSADO", f"A Parcela {num2(i)} da confissão vence antes da assinatura.")


def _posse(
    av: Avaliacao,
    d: DadosContrato,
    marco: Optional[str],
    prazo: Optional[int],
    marco_parcela_id: Optional[str],
    *,
    escopo: str,
) -> None:
    """[§6.1 #12] One rule for both posse clauses (the imóvel's and, in a
    permuta, the exchanged imóvel's) — they are the same clause pointed at
    different properties, so a second copy would be a second thing to drift."""
    rotulo = "da posse" if escopo == "posse" else "da posse do imóvel da permuta"
    if not prazo:
        av.falta(f"negociacao.{escopo}_prazo_dias", f"Prazo de entrega {rotulo} (dias)", "negociacao")
    if not marco:
        av.falta(f"negociacao.{escopo}_marco", f"Marco inicial do prazo {rotulo}", "negociacao")
    elif marco not in frases.MARCOS_POSSE:
        av.bloqueia("POSSE_MARCO_INVALIDO", f"Marco {rotulo} desconhecido: {marco}.")
    elif marco == "parcela" and numero_da_parcela(d, marco_parcela_id) is None:
        # 114's CHECK guarantees the id is SET when the marco is 'parcela'; it
        # cannot guarantee the parcela still belongs to this deal's schedule.
        av.bloqueia(
            "POSSE_MARCO_PARCELA_DESCONHECIDA",
            f"O marco {rotulo} aponta para uma parcela que não está no preço deste contrato.",
        )


def _financiamento(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    if sw["tem_financiamento"]:
        if not d.financiamento.existe:
            av.falta("financiamento", "Registro do financiamento do atendimento", "financiamento")
        elif d.financiamento.situacao == "recusado":
            av.bloqueia("FINANCIAMENTO_RECUSADO", "O financiamento deste atendimento está recusado.")
    # [Q6] ONE parcela: FGTS is worded inside the financiamento parcela.
    for i, p in enumerate(parcelas_ordenadas(d), start=1):
        if p.tipo == "fgts":
            av.bloqueia(
                "PARCELA_FGTS_SEPARADA",
                f"A Parcela {num2(i)} é de FGTS: o FGTS entra na parcela de financiamento — junte o valor "
                "na parcela de financiamento e marque o uso de FGTS no financiamento.",
            )
    if d.financiamento.fgts and not sw["tem_financiamento"]:
        av.avisa(
            "FGTS_SEM_PARCELA",
            "O financiamento marca uso de FGTS, mas não há parcela de financiamento; o FGTS não aparece no contrato.",
        )


def _permuta(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    if not sw["tem_permuta"]:
        return
    parcela = parcela_permuta(d)
    assert parcela is not None  # the switch IS this parcela
    if not parcela.permuta_ativo_ids:
        av.falta(
            "negociacao.permuta_imoveis",
            "Imóvel(is) de permuta vinculado(s) à parcela de permuta",
            "negociacao",
        )
    for imovel in d.permuta_imoveis:
        alvo = f"negociacao.permuta.{imovel.permuta_ativo_id}"
        if imovel.num_atos == 0 or not (imovel.descricao_matricula or "").strip():
            av.falta(
                f"matricula.permuta.{imovel.permuta_ativo_id}.atos",
                "Atos da matrícula do imóvel dado em permuta selecionados para o contrato",
                "matricula",
            )
        elif has_raw_markup(imovel.descricao_matricula or ""):
            av.bloqueia(
                "MATRICULA_COM_MARCACAO_BRUTA",
                "O texto da matrícula do imóvel dado em permuta contém "
                "marcação de formatação bruta (** ou <u>) — a transcrição "
                "precisa ser reenviada antes de entrar no contrato.",
            )
        for campo, rotulo in (
            ("inscricao_municipal", "Inscrição municipal do imóvel da permuta"),
            ("matricula_numero", "Número da matrícula do imóvel da permuta"),
            ("cartorio", "Cartório de registro do imóvel da permuta"),
        ):
            if not getattr(imovel, campo):
                av.falta(f"{alvo}.{campo}", rotulo, "imovel")
        for campo, rotulo in (
            ("logradouro", "Logradouro do imóvel da permuta"),
            ("numero", "Número do imóvel da permuta"),
            ("cidade", "Cidade do imóvel da permuta"),
        ):
            if not getattr(imovel.endereco, campo):
                av.falta(f"{alvo}.{campo}", rotulo, "imovel")
        # 🔴 [endereco-portaria-vs-imovel] Same rule as `_imovel` above — the
        # permuta posse clause prints the REGISTRY address, never
        # `imovel.endereco` (same decoy risk as the main imóvel's). No atos
        # selected for this ativo is ALREADY named above (`...atos`); stays
        # quiet then rather than repeating the same root cause twice.
        if not resolver_endereco_posse(
            imovel.endereco_registro_texto,
            imovel.descricao_imovel_texto or imovel.descricao_matricula or "",
            imovel.descricao_matricula or "",
        ) and (imovel.endereco_registro_texto or (imovel.descricao_matricula or "").strip()):
            av.falta(
                f"{alvo}.endereco_registro_texto",
                "Endereço do imóvel da permuta confirmado a partir do registro "
                "(nunca o endereço público do CRM)",
                "imovel",
            )
        _verificar_coerencia_endereco(
            av,
            logradouro=imovel.endereco.logradouro,
            area=None,
            texto_matricula=imovel.descricao_imovel_texto or imovel.descricao_matricula or "",
            rotulo="do imóvel da permuta",
        )
    _posse(
        av,
        d,
        d.termos.permuta_posse_marco,
        d.termos.permuta_posse_prazo_dias,
        d.termos.permuta_posse_marco_parcela_id,
        escopo="permuta_posse",
    )


def _certidoes(
    av: Avaliacao,
    d: DadosContrato,
    sw: dict[str, bool],
    politica: Politica,
    assinatura: date,
    hoje: Optional[date] = None,
) -> None:
    hoje = hoje or _hoje_padrao()
    signatarios_certificados = signatarios(d.vendedores) + (
        signatarios(d.compradores) if sw["tem_permuta"] else []
    )
    com_apontamento: list[str] = []

    def tempo(codigo: str, mensagem: str) -> None:
        """The certidão TIME rules (emission age / validade) only —
        `CERTIDAO_EMITIDA_APOS_ASSINATURA` is a data error, not an age
        rule, and is NEVER routed through here; every call site keeps
        calling `av.bloqueia` for it directly.

        [Owner directive, 2026-09-22] `d.processo_legado` (migration 151,
        set ONLY through `PUT .../processo-legado`, admin-only, never an
        automatic date heuristic) dispenses these for a deal that started
        before the platform: a warning instead of a block, so the
        contract can still generate while the dispensation stays visible
        on the readiness report.
        """
        if d.processo_legado:
            av.avisa(codigo, f"{mensagem} (processo anterior à plataforma)")
        else:
            av.bloqueia(codigo, mensagem)

    def conferir(p: Pessoa, certs: list[Certidao], tipo_documento: str, nome_grupo: str) -> None:
        idx = indice_certidoes(certs, tipo_documento)
        for tipo in tipos_exigidos(tipo_documento):
            rotulo = frases.rotulo_certidao(tipo, None)
            c = idx.get(tipo)
            if c is None or not c.resultado:
                # [R1, reverses df54184ab] EVERY certificando — a vendedor
                # (lado="vendedor": every signing seller AND, since they are
                # stored in `d.vendedores` too, an `antigo_proprietario`)
                # included — needs the full CPF/CNPJ set (CND federal, TRF,
                # TRT, TJSP, Serasa, Cenprot, Fazenda SP). The seller-relief
                # this block used to grant (df54184ab, live in prod since
                # d1dc3f834) is revoked by owner directive (roadmap
                # `sw-drive-extraction-2026-09.md` §R1, 2026-09-24).
                av.falta(f"certidao.{tipo}", f"{rotulo} — {nome_grupo}", "certidoes", p.parte_id)
                continue
            if c.resultado == "nao_emitida":
                continue
            if not c.numero:
                av.falta(f"certidao.{tipo}.numero", f"Número da {rotulo} — {nome_grupo}", "certidoes", p.parte_id)
            if not c.emitida_em:
                av.falta(f"certidao.{tipo}.emitida_em", f"Data de emissão da {rotulo} — {nome_grupo}", "certidoes", p.parte_id)
                continue
            if c.emitida_em > assinatura:
                av.bloqueia("CERTIDAO_EMITIDA_APOS_ASSINATURA", f"{rotulo} de {nome_grupo} tem emissão posterior à assinatura.")
            elif (assinatura - c.emitida_em).days >= politica.certidao_max_dias:
                # [Q10] every certidão is emitted less than 30 days before signing.
                tempo(
                    "CERTIDAO_EMISSAO_ANTIGA",
                    f"{rotulo} de {nome_grupo} foi emitida há {(assinatura - c.emitida_em).days} dias; "
                    f"precisa ter menos de {politica.certidao_max_dias} dias na data da assinatura.",
                )
            if c.validade_ate is not None and c.validade_ate < assinatura:
                tempo("CERTIDAO_VENCIDA", f"{rotulo} de {nome_grupo} está vencida na data da assinatura.")
            # [§6.1 #15] A positiva AND a negativa-com-homônimos both need the
            # esclarecimentos paragraph — the homônimo apontamentos are exactly
            # what has to be explained away (migration 116).
            if c.resultado in frases.RESULTADOS_COM_APONTAMENTO:
                com_apontamento.append(f"{rotulo} ({nome_grupo})")

    def conferir_pessoa(p: Pessoa) -> None:
        # Migration 116 reaches EVERY party's certidões, the titular included,
        # so an empty list is "none issued yet" and each tipo is named below —
        # it is no longer an unreachable-data refusal.
        conferir(p, p.certidoes, "cpf", _nome(p))

    def conferir_empresas() -> None:
        """[E1] Every empresa a certificando holds a participação in — the
        NULL-situação gap (no Cartão CNPJ uploaded yet) is a named
        `faltando`, never a silent skip (E1, H4); required companies get
        the same 11-item CNPJ certidão check as a person (E5)."""
        for e, dono in _empresas_de_certificandos(d, sw):
            nome_pj = e.razao_social or e.cnpj
            motivo = classificar_empresa(e, hoje, politica)
            if motivo == PJ_SEM_SITUACAO:
                av.falta(f"empresa.{e.id}.cartao_cnpj", f"Cartão CNPJ — {nome_pj}", "empresas")
            elif motivo == PJ_SEM_DATA_SITUACAO:
                av.falta(
                    f"empresa.{e.id}.data_situacao_cadastral",
                    f"Data da baixa da empresa {nome_pj}",
                    "empresas",
                )
            elif motivo == PJ_SITUACAO_DESCONHECIDA:
                av.bloqueia(
                    "SITUACAO_CADASTRAL_DESCONHECIDA",
                    f"A situação cadastral da empresa {nome_pj} não é reconhecida.",
                )
            elif motivo in (PJ_EXIGIDO, PJ_EXIGIDO_BAIXADA):
                conferir(dono, e.certidoes, "cnpj", nome_pj)

    def conferir_conjuges_ausentes() -> None:
        """[E3] A married certificando's cônjuge who is not a `Pessoa` on
        this card at all — their empresas are unreachable, so this is a
        named `faltando`, never a silent drop from `_empresas_de_
        certificandos`'s owner-matching (tech-lead review, S2b)."""
        for p in _conjuges_sem_pessoa(d, sw):
            av.falta(
                f"parte.{p.cliente_id}.conjuge",
                f"Cônjuge de {_nome(p)} não está no card",
                "partes",
                p.parte_id,
                ancora=_ancora(p),
            )

    conferir_empresas()
    conferir_conjuges_ausentes()
    for p in signatarios_certificados:
        conferir_pessoa(p)
        # [Q11] the estado-civil certidão is less than 90 days old.
        emitida = p.certidao_estado_civil_emitida_em
        if emitida is None:
            av.falta(
                "qualificacao.certidao_estado_civil_emissao",
                f"Certidão de estado civil com data de emissão — {_nome(p)}",
                "partes",
                p.parte_id,
                ancora=_ancora(p),
            )
        elif emitida > assinatura:
            av.bloqueia(
                "CERTIDAO_EMITIDA_APOS_ASSINATURA",
                f"A certidão de estado civil de {_nome(p)} tem emissão posterior à assinatura.",
            )
        elif (assinatura - emitida).days >= politica.certidao_estado_civil_max_dias:
            tempo(
                "CERTIDAO_ESTADO_CIVIL_ANTIGA",
                f"A certidão de estado civil de {_nome(p)} foi emitida há {(assinatura - emitida).days} dias; "
                f"precisa ter menos de {politica.certidao_estado_civil_max_dias} dias na data da assinatura.",
            )

    # [Q9] previous owner(s) when the last transfer of ownership is recent.
    antigos = antigos_proprietarios(d)
    if d.imovel is not None:
        exige = exige_antigo_proprietario(d, assinatura, politica)
        if exige is None:
            av.falta(
                "matricula.ultima_transferencia",
                "Data do registro da última transferência de propriedade na matrícula "
                "— confirme na página do imóvel",
                "imovel",
            )
        elif exige and d.processo_legado:
            # [Owner directive, 2026-09-22] Same posture as `tempo()` above:
            # a deal that started before the platform keeps the requirement
            # VISIBLE but never blocks on it — the human-made reference
            # contract for a legacy 2023 acquisition qualifies only the
            # seller, with no previous-owner section at all. Skip every
            # `falta` this branch would otherwise raise (name/gênero/
            # certidões of the antigos) — they never enter a legacy contract.
            av.avisa(
                "ANTIGO_PROPRIETARIO_PROCESSO_LEGADO",
                "A última transferência foi registrada há menos de "
                f"{politica.antigo_proprietario_janela_anos} anos, mas o processo é anterior à "
                "plataforma: os antigos proprietários não entram no contrato "
                "(processo anterior à plataforma).",
            )
        elif exige:
            if not antigos:
                nomes = ", ".join(d.imovel.ultima_transferencia_transmitentes)
                quem = f" — consta(m) na matrícula: {nomes}" if nomes else ""
                av.falta(
                    "partes.antigo_proprietario",
                    "Antigo(s) proprietário(s) do imóvel no card — a última transferência de "
                    f"propriedade foi registrada há menos de {politica.antigo_proprietario_janela_anos} anos{quem}",
                    "partes",
                    ancora="vendedor",
                )
            for a in antigos:
                if not a.nome:
                    av.falta("qualificacao.nome_oficial", f"Nome oficial — {_nome(a)} (antigo proprietário)", "partes", a.parte_id, ancora="vendedor")
                if normalizar_genero(a.genero) is None:
                    av.falta("qualificacao.genero", f"Gênero — {_nome(a)} (antigo proprietário)", "partes", a.parte_id, ancora="vendedor")
                conferir_pessoa(a)
        elif antigos:
            av.avisa(
                "ANTIGO_PROPRIETARIO_DISPENSADO",
                f"A última transferência de propriedade foi registrada há {politica.antigo_proprietario_janela_anos} "
                "anos ou mais; as certidões do(s) antigo(s) proprietário(s) não entram no contrato.",
            )

    if com_apontamento:
        av.avisa(
            "CERTIDOES_POSITIVAS",
            "Certidões positivas exigem esclarecimentos: " + "; ".join(com_apontamento) + ".",
        )


def _imobiliaria(av: Avaliacao, d: DadosContrato, politica: Politica) -> None:
    org = d.imobiliaria
    for valor, campo, rotulo in (
        (org.razao_social, "razao_social", "Razão social da imobiliária"),
        (org.cnpj, "cnpj", "CNPJ da imobiliária"),
        (org.responsavel_nome, "responsavel_nome", "Responsável legal da imobiliária"),
        (org.responsavel_creci, "responsavel_creci", "CRECI do responsável"),
        (org.endereco.cidade, "endereco_cidade", "Cidade da imobiliária (local de assinatura)"),
    ):
        if not valor:
            av.falta(f"imobiliaria.{campo}", rotulo, "imobiliaria")
    if len(d.testemunhas) != 2:
        av.falta("imobiliaria.testemunhas", "Duas testemunhas cadastradas", "imobiliaria")
    for i, t in enumerate(d.testemunhas, start=1):
        if not t.nome:
            av.falta(f"imobiliaria.testemunha.{i}.nome", f"Nome da testemunha {i}", "imobiliaria")
        # [Q14 revisited] The contract prints RG, not CPF (Contract 08's own
        # witnesses only carry RG — f5-template-spec.md §5.1 lists "nome +
        # rg" as the hard-required pair) — RG is required, not optional.
        if not t.rg:
            av.falta(f"imobiliaria.testemunha.{i}.rg", f"RG da testemunha {i}", "imobiliaria")
        # CPF stays OPTIONAL — an office may or may not hold one for a given
        # witness — but a CPF that IS supplied must still pass mod-11, same
        # "check what's given, never require what isn't there" posture
        # `posse_multa_diaria`/`prazo_pendencias` take below.
        if t.cpf and not cpf_valido(t.cpf):
            av.bloqueia("CPF_INVALIDO", f"O CPF da testemunha {i} não confere (dígitos verificadores).")
        # [Owner directive, 2026-09-23] E-mail used to gate only SENDING for
        # signature (`assinatura_service.enviar` / D4Sign), never generating
        # the document — an aviso a witness the office hadn't e-mail'd yet
        # never blocked on. It now blocks readiness itself, same terms as
        # nome/rg above, for a digital contract (a física one still never
        # needs it — no signature-platform clause at all).
        if not t.email and d.modalidade_assinatura != "fisica":
            av.falta(f"imobiliaria.testemunha.{i}.email", f"E-mail da testemunha {i}", "imobiliaria")
    # Only the DIGITAL clause names the platform — a física contract
    # (migration 157) has no such clause, so it never needs one.
    if d.modalidade_assinatura != "fisica" and (
        not org.plataforma_assinatura_nome or not org.plataforma_assinatura_url
    ):
        av.falta(
            "imobiliaria.plataforma_assinatura",
            "Plataforma de assinatura digital (nome e endereço)",
            "imobiliaria",
        )
    # [Q12] the office's posse multa diária.
    if org.posse_multa_diaria is None:
        av.falta(
            "imobiliaria.posse_multa_diaria",
            "Multa diária por atraso na entrega da posse (valor da imobiliária)",
            "imobiliaria",
        )
    elif org.posse_multa_diaria <= 0:
        av.bloqueia("MULTA_DIARIA_POSSE_INVALIDA", "A multa diária da posse precisa ser maior que zero.")
    # [Q11] pendências prazo.
    if prazo_pendencias(d, politica) <= 0:
        av.bloqueia("PRAZO_PENDENCIAS_INVALIDO", "O prazo para apresentar as pendências precisa ser maior que zero.")


def pct_intermediarios(d: DadosContrato) -> Decimal:
    """[§6.1 #5] The sum of every percentual-type intermediário's cut.

    A SINGLE function on purpose — [owner directive, 2026-09-23] a parallel
    slice adds "parceiro sem CRECI" favorecidos that must count in this same
    sum, and folding that in here (once it exists) is the one place both
    `_intermediacao`'s readiness check and anything else that needs the
    total stay in agreement, instead of a second ad-hoc sum growing beside
    this one."""
    return sum(
        (i.valor for i in d.intermediarios if i.tipo == "percentual" and i.valor is not None),
        Decimal("0"),
    )


def _intermediacao(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    if not sw["tem_intermediacao"]:
        return
    termos = d.termos
    favorecidos = {f.id: f for f in d.favorecidos}
    for it in d.intermediarios:
        # Migration 162 — a 'parceiro_split' row is a commission-split
        # beneficiary the clause header never qualifies (never rendered by
        # `frases.qualificacao_intermediario` — see `contexto.py`'s
        # `qualificados` list), so it is never a licensed broker and never
        # required to carry a CRECI. Only a (default) 'intermediario' row —
        # a party the header DOES qualify — needs one.
        if it.natureza == "intermediario" and not it.creci:
            av.falta(f"negociacao.intermediario.{it.id}.creci", f"CRECI de {it.nome}", "negociacao")
        if it.valor is None:
            av.falta(f"negociacao.intermediario.{it.id}.valor", f"Valor da corretagem de {it.nome}", "negociacao")
        # [§6.1 #21] An EXTERNAL intermediário carries its own qualification
        # (114); the office's own is qualified from `Imobiliaria`.
        if not it.corretor_id and not (it.pessoa_tipo and it.documento):
            av.falta(
                f"negociacao.intermediario.{it.id}.qualificacao",
                f"Qualificação (PF/PJ e CPF/CNPJ) do intermediário externo {it.nome}",
                "negociacao",
            )
        # [§6.1 #22] The favorecido link now lives ON the intermediário.
        if not it.favorecido_id:
            av.falta(
                f"negociacao.intermediario.{it.id}.favorecido",
                f"Favorecido que recebe a corretagem de {it.nome}",
                "negociacao",
            )
        elif it.favorecido_id not in favorecidos:
            av.bloqueia("FAVORECIDO_INEXISTENTE", f"O favorecido da corretagem de {it.nome} não existe.")
        elif not favorecidos[it.favorecido_id].conta and not favorecidos[it.favorecido_id].pix:
            fav = favorecidos[it.favorecido_id]
            av.falta(f"negociacao.favorecido.{fav.id}.conta", f"Conta ou chave PIX de {fav.nome}", "negociacao")
    if not termos.corretagem_contratantes:
        av.falta("negociacao.corretagem_contratantes", "Quem paga a corretagem (vendedores, compradores ou ambas as partes)", "negociacao")
    elif termos.corretagem_contratantes not in ("vendedores", "compradores", "partes"):
        av.bloqueia("CORRETAGEM_CONTRATANTES_INVALIDO", f"Pagador de corretagem desconhecido: {termos.corretagem_contratantes}.")
    # [§6.1 #23] The marco is the parcela's own `dispara_corretagem` flag.
    if not corretagem_marcos(d):
        av.falta(
            "negociacao.corretagem_parcelas_marco",
            "Parcela(s) cujo recebimento dispara o pagamento da corretagem "
            "(marque-a na parcela, em Negociação)",
            "negociacao",
        )
    # [Q5] the corretagem % owed on rescisão is the deal's commission.
    if d.pct_comissao is None:
        av.falta("negociacao.pct_comissao", "Percentual de comissão", "negociacao")
    else:
        pct_total = pct_intermediarios(d)
        if pct_total and pct_total != d.pct_comissao:
            # [Owner directive, 2026-09-23] A mismatched sum is deal DATA
            # that disagrees with itself, not an unfilled field — a
            # bloqueio, same footing as SOMA_PARCELAS_DIFERENTE_DO_PRECO.
            av.bloqueia(
                "CORRETAGEM_PERCENTUAL_DIVERGE",
                f"Os percentuais dos intermediários somam {pct_total}%, mas o "
                f"percentual de comissão do contrato é {d.pct_comissao}%.",
            )


def _contrato(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    derivado = modelo_derivado(sw)
    if d.modelo != derivado:
        av.avisa("MODELO_DIVERGENTE", f"O modelo do contrato é '{d.modelo}', mas os dados indicam '{derivado}'.")
    # [Owner directive, 2026-09-23] "the paragraph is required, so no
    # silent omission" — `itens_integrantes` alone cannot tell "nobody
    # answered" from "confirmed: none" (blank collapses to `None` on write,
    # Migration 163's header). A human EITHER fills the text OR ticks
    # `itens_integrantes_ausente_confirmado`; only then does the paragraph's
    # legitimate omission (spec §1.3 variant 3 — no itens integrantes at
    # all) stay reachable without leaving the question permanently
    # unanswered.
    if d.termos.itens_integrantes is None and not d.termos.itens_integrantes_ausente_confirmado:
        av.falta(
            "negociacao.itens_integrantes",
            "Itens integrantes (relacione-os, ou confirme que não há nenhum)",
            "negociacao",
            alvo=ALVO_ITENS_INTEGRANTES,
        )
    # [Owner directive, 2026-09-23] "None → block, and an explicit false is
    # fine" — same tri-state shape `itens_integrantes_ausente_confirmado`
    # gives `itens_integrantes` above, except `ad_corpus` was ALREADY a
    # real bool (no text-collapses-blank ambiguity to solve).
    if d.termos.ad_corpus is None:
        av.falta(
            "negociacao.ad_corpus", "Venda ad corpus (sim ou não)", "negociacao",
            alvo=ALVO_AD_CORPUS,
        )
    # Stored by 114, with no clause in any sample contract — announced so the
    # operator knows the text they typed is NOT on the instrument.
    for valor, codigo, rotulo in (
        (d.termos.obrigacoes_vendedor, "OBRIGACOES_VENDEDOR_SEM_REDACAO", "As obrigações do vendedor"),
        (
            d.termos.permuta_obrigacoes_entrega,
            "PERMUTA_OBRIGACOES_SEM_REDACAO",
            "As obrigações de entrega do imóvel da permuta",
        ),
    ):
        if (valor or "").strip():
            av.avisa(codigo, f"{rotulo} foram preenchidas, mas o gerador ainda não tem cláusula para elas; o texto não entra no contrato.")
    # [Owner revision, 2026-09-23 — supersedes an earlier `foro_comarca`
    # manual-field draft] NO manual field, NO imóvel-city fallback: the
    # comarca is read off the SAME matrícula transcription the contract
    # already quotes, resolved once at load time (`carregador.carregar` ->
    # `comarca_de_texto`) onto `d.matricula.comarca`. `FORO_PELA_CIDADE`
    # (an always-on aviso computing it from the imóvel address) is
    # deleted — an unreadable matrícula now blocks instead of silently
    # guessing.
    #
    # 🔴 Resolver lands on the IMÓVEL's documents (2026-09-23), not on the
    # generic `/matriculas` extractor list: the comarca is missing because
    # this imóvel's matrícula was never uploaded/read, or its text lacks the
    # cartório heading — both are fixed where the imóvel's matrícula lives.
    # Still GROUPED under "Matrícula" (`onde`), since that is what it is.
    if d.imovel is not None and not d.matricula.comarca:
        av.falta(
            "negociacao.foro_comarca",
            "Comarca do cartório da matrícula (não encontrada no texto da matrícula)",
            "matricula",
            destino_em="imovel",
            alvo=ALVO_DOCUMENTOS_DO_IMOVEL,
        )


def avaliar(
    d: DadosContrato,
    switches: dict[str, bool],
    politica: Politica,
    assinatura: date,
    hoje: Optional[date] = None,
) -> Avaliacao:
    """`hoje` (default TODAY — `_hoje_padrao`) is the E1 empresa-
    classification reference date, distinct from `assinatura` (E2/H2)."""
    av = Avaliacao(
        destinos=Destinos(
            cliente_id=d.cliente_id,
            contrato_id=d.contrato_id,
            imovel_codigo=d.imovel.codigo if d.imovel else None,
        )
    )
    _partes(av, d)
    _imovel(av, d, switches, politica, assinatura)
    _negociacao(av, d, switches, assinatura)
    _financiamento(av, d, switches)
    _permuta(av, d, switches)
    _certidoes(av, d, switches, politica, assinatura, hoje)
    _imobiliaria(av, d, politica)
    _intermediacao(av, d, switches)
    _contrato(av, d, switches)
    return av


__all__ = [
    "ALVO_AD_CORPUS",
    "ALVO_DOCUMENTOS_DO_IMOVEL",
    "ALVO_ITENS_INTEGRANTES",
    "Avaliacao",
    "Destinos",
    "EmpresaExigida",
    "MODELO_A_VISTA",
    "MODELO_COMPRA_VENDA",
    "MODELO_PERMUTA",
    "ORDEM_CERTIDOES_IMOVEL",
    "SUFIXO_DOCUMENTO_DE_IDENTIDADE",
    "SUFIXO_PJ_BAIXADA",
    "anos_antes",
    "antigos_proprietarios",
    "avaliar",
    "certidoes_imovel",
    "classificar_empresa",
    "comarca_de_texto",
    "corretagem_marcos",
    "derivar_switches",
    "empresas_exigidas",
    "exige_antigo_proprietario",
    "ha_menos_de_anos",
    "indice_certidoes",
    "modelo_derivado",
    "numero_da_parcela",
    "parcelas_antes_de",
    "parcelas_ordenadas",
    "pct_intermediarios",
    "pessoas_certificadas",
    "prazo_pendencias",
    "tipos_exigidos",
]
