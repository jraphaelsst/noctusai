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

- `confirmacoes` — not wrong data, but something the operator must KNOW
                (e.g. a Receita PCEN 2ª via): each carries `ciente`.

`pronto` is `not faltando and not bloqueios and not pendentes_confirmacao`
(every `confirmacoes` entry acknowledged). A switch that needs a MISSING
field adds a `faltando`; optional wording whose switch is off is omitted.
The office's policy answers (spec §6.2, answered 2026-09-15) are cited as
[Qn] next to the rule that implements each — see `politica.py`.

🔴 NOTHING HERE IS "NOT IN THE SYSTEM" ANY MORE. Migrations 114-118 gave every
spec §6.1 field real storage (see `dados`'s module docstring), so a gap is now
always an un-filled FORM, never a missing column — which is why every refusal
can name a screen. The two things still genuinely absent are named as such:
procurador/inventariante wording (`PAPEIS_SEM_REDACAO`) and penhora /
indisponibilidade (`ONUS_NAO_SUPORTADO`) — the signed-contract corpus has no
wording for either. `ja_quitado`, `obrigacoes_vendedor` and
`permuta_obrigacoes_entrega` are worded since migration 193.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from noctusai_lib.domain.texto_ptbr import formatar_brl, parse_brl
from noctusai_lib.integrations.documents import (
    derivar_endereco,
    has_raw_markup,
    segment_matricula_atos,
)
from noctusai_lib.integrations.documents.address import normalizar_uf
from noctusai_lib.integrations.documents.matricula_certidao import (
    MOTIVO_ANTERIOR_AO_ULTIMO_ATO,
    MOTIVO_DIVERGENTE,
    MOTIVO_NAO_ENCONTRADA,
    MOTIVO_VISUALIZACAO,
    TIPO_VISUALIZACAO,
)
from noctusai_lib.integrations.documents.cnpj import is_valid as cnpj_valido
from noctusai_lib.integrations.documents.cpf import is_valid as cpf_valido

from app.modules.card_hub.contrato_gerador import certidao_pcen, frases
from app.modules.card_hub.contrato_gerador.concordancia import normalizar_genero
from app.modules.card_hub.contrato_gerador.dados import (
    PAPEIS_SEM_REDACAO,
    PAPEL_ANUENTE,
    MODOS_CLAUSULA_EXTRA,
    Certidao,
    CertidaoImovel,
    DadosContrato,
    Empresa,
    Parcela,
    ParteJuridica,
    Pessoa,
    anuentes,
    parcela_permuta,
    parcelas_permuta,
    representantes,
    signatarios,
)
from app.modules.card_hub.contrato_gerador.numeracao import (
    CLAUSULA_CONDICIONAL,
    ORDEM_CLAUSULAS,
    num2,
    rotulo_clausula,
)
from app.modules.card_hub.contrato_gerador.politica import (
    MIN_TESTEMUNHAS,
    ONUS_COM_SALDO,
    POLITICA_PADRAO,
    ONUS_SUPORTADOS,
    ONUS_USUFRUTO,
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

#: `atendimento_financiamento.situacao` vocabulary (migration 078's CHECK).
SITUACOES_FINANCIAMENTO = frozenset({"pendente", "aprovado", "recusado"})

#: `atendimento_intermediarios.tipo` vocabulary (migration 108's CHECK).
TIPOS_INTERMEDIARIO = frozenset({"percentual", "valor_fixo"})

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

#: The qualificação keys read off the ONE "Documento de identidade (RG/CPF,
#: CNH ou CIN)" checklist item (2026-09-23; three slots since 2026-09-30).
#: Their `falta` names that item, so the operator knows the fix is to send one
#: of its documents (or type the value). Kept equal to
#: `documento_checklist_service.CAMPOS_DOCUMENTO_IDENTIDADE` by a test — not
#: imported, so this pure module stays free of the service layer.
_CHAVES_DO_DOCUMENTO_DE_IDENTIDADE = frozenset(
    {"nome_oficial", "rg", "rg_orgao_expedidor", "cpf"}
)
SUFIXO_DOCUMENTO_DE_IDENTIDADE = " (Documento de identidade: RG/CPF, CNH ou CIN)"

#: [E1] `classificar_situacao_pj`/`classificar_empresa` outcomes.
PJ_EXIGIDO = "exigido"
PJ_EXIGIDO_BAIXADA = "exigido_baixada"
PJ_OMITIDO = "omitido"
PJ_SEM_SITUACAO = "sem_situacao"
PJ_SEM_DATA_SITUACAO = "sem_data_situacao"
PJ_SITUACAO_DESCONHECIDA = "situacao_desconhecida"

#: The two "required" outcomes — the exact filter `empresas_exigidas` and
#: `motivo_publico` both apply.
PJ_CODIGOS_EXIGIDOS = frozenset({PJ_EXIGIDO, PJ_EXIGIDO_BAIXADA})

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


#: [2026-10-03, deal 869] The abertura's own registry boilerplate, in every
#: phrasing the office's matrículas use: "nesta cidade, município e comarca
#: de Carapicuíba", "desta cidade e comarca de Cotia", "município e comarca
#: de …". Deliberately narrow on the noun in front: "Foro e Comarca de
#: Sorocaba" (a citation INSIDE an averbação, about a DIFFERENT instrument)
#: never reads "cidade/município e comarca" and so never matches.
_COMARCA_MUNICIPIO_RE = re.compile(
    r"(?:cidade|munic[íi]pio)\s+e\s+comarca\s+d[aeo]\s+([^,;.\n()]+)", re.IGNORECASE
)
#: "Registro de imóveis da comarca de Cotia – SP" — the cartório's own
#: heading. Deliberately narrow: "registro civil da comarca de X" (a
#: person's marriage/birth registry, cited in a qualificação paragraph)
#: reads "civil", never "de imóveis", and so never matches either.
_COMARCA_REGISTRO_RE = re.compile(
    r"registro\s+de\s+im[óo]veis\s+da\s+comarca\s+d[aeo]\s+"
    r"([^,;.\n\-–—()]+?)(?:\s*[-–—]\s*([A-Za-z]{2}))?(?=[,;.\n(]|$)",
    re.IGNORECASE,
)
#: [2026-10-03] The bare "Comarca de Cotia" / "Comarca da Capital" a
#: matrícula heading also uses on its own. Only trusted when no clause-local
#: context names ANOTHER office (`_COMARCA_ALHEIA_RE`) and every bare
#: citation in the abertura agrees.
_COMARCA_SOLTA_RE = re.compile(r"(?<!\w)comarca\s+d[aeo]\s+([^,;.\n()]+)", re.IGNORECASE)
#: Within the same clause as a bare "comarca de X": a registro CIVIL, a
#: notary, a court/foro — a comarca that is NOT the matrícula's own.
_COMARCA_ALHEIA_RE = re.compile(
    r"civil|naturais|nota|tabeli|foro|vara|ju[íi]z|trabalh|cart[óo]rio\s+de\s+paz"
    r"|resid|domicil|nascid|natural",
    re.IGNORECASE,
)
#: A captured city's tails: " - SP" / "/SP" / "-SP" / " SP", and
#: "[do] Estado de São Paulo" — the UF they name, if any, is kept apart.
_COMARCA_TRAVESSAO_RE = re.compile(r"\s+[-–—]\s+")
_COMARCA_UF_INICIAL_RE = re.compile(r"([A-Za-z]{2})(?![\wÀ-ÿ])")
_COMARCA_UF_FINAL_RE = re.compile(r"\s*[/\-–—]\s*([A-Za-z]{2})$|(?-i:\s+([A-Z]{2}))$")
_COMARCA_ESTADO_RE = re.compile(r"[\s,]+(?:do\s+|no\s+)?estado\s+d[eo]\s+(.+)$", re.IGNORECASE)

#: UF -> capital — "Comarca da Capital" names no city by itself; the UF
#: (written next to it, or the imóvel's own) says which.
_CAPITAL_POR_UF: dict[str, str] = {
    "AC": "Rio Branco", "AL": "Maceió", "AP": "Macapá", "AM": "Manaus", "BA": "Salvador",
    "CE": "Fortaleza", "DF": "Brasília", "ES": "Vitória", "GO": "Goiânia", "MA": "São Luís",
    "MT": "Cuiabá", "MS": "Campo Grande", "MG": "Belo Horizonte", "PA": "Belém",
    "PB": "João Pessoa", "PR": "Curitiba", "PE": "Recife", "PI": "Teresina",
    "RJ": "Rio de Janeiro", "RN": "Natal", "RS": "Porto Alegre", "RO": "Porto Velho",
    "RR": "Boa Vista", "SC": "Florianópolis", "SP": "São Paulo", "SE": "Aracaju",
    "TO": "Palmas",
}


def _mesma_cidade(com_uf: str, sem_uf: str) -> bool:
    """Case/accent-insensitive city-name compare — either side may carry a
    "/UF" suffix (`_COMARCA_REGISTRO_RE`'s shape); only the city name itself
    is compared."""
    return _dobra_acentos(com_uf.split("/", 1)[0]) == _dobra_acentos(sem_uf.split("/", 1)[0])


def _cidade_da_comarca(bruto: str, uf_padrao: Optional[str]) -> Optional[str]:
    """One captured "comarca de <…>" tail -> the city, or `None`.

    Strips a UF/"Estado de …" tail; resolves "Capital" through the UF written
    beside it ("Capital do Estado de São Paulo", "Capital/SP") or, failing
    that, `uf_padrao` (the imóvel's UF) — never guessed without one."""
    texto = re.sub(r"\s+", " ", bruto).strip(" .")
    if not texto:
        return None
    uf: Optional[str] = None
    cabeca, *resto = _COMARCA_TRAVESSAO_RE.split(texto, maxsplit=1)
    if resto and (m := _COMARCA_UF_INICIAL_RE.match(resto[0])):
        uf = normalizar_uf(m.group(1))
    m = _COMARCA_ESTADO_RE.search(cabeca)
    if m:
        uf = uf or normalizar_uf(m.group(1).strip(" ."))
        cabeca = cabeca[: m.start()]
    m = _COMARCA_UF_FINAL_RE.search(cabeca)
    if m and (sigla := normalizar_uf(m.group(1) or m.group(2))):
        uf = uf or sigla
        cabeca = cabeca[: m.start()]
    cidade = cabeca.strip(" .,")
    if not cidade:
        return None
    if _dobra_acentos(cidade) == "CAPITAL":
        uf = uf or normalizar_uf(uf_padrao)
        return _CAPITAL_POR_UF.get(uf) if uf else None
    # An all-caps heading ("COMARCA DE ITAPEVI") prints as a name in the
    # foro clause, the same casing `frases.cartorio_texto` gives a city.
    return frases.cidade_titulo(cidade) if cidade.isupper() else cidade


def _comarcas_soltas(escopo: str, uf_padrao: Optional[str]) -> set[str]:
    """Every bare "comarca de X" in the abertura whose own clause does not
    name another office (`_COMARCA_ALHEIA_RE`), folded for comparison."""
    lidas: dict[str, str] = {}
    for m in _COMARCA_SOLTA_RE.finditer(escopo):
        inicio_clausula = max(escopo.rfind(sep, 0, m.start()) for sep in (".", ";", "\n"))
        if _COMARCA_ALHEIA_RE.search(escopo[inicio_clausula + 1 : m.start()]):
            continue
        cidade = _cidade_da_comarca(m.group(1), uf_padrao)
        if cidade:
            lidas.setdefault(_dobra_acentos(cidade), cidade)
    return set(lidas.values())


def comarca_de_texto(texto: Optional[str], *, uf: Optional[str] = None) -> Optional[str]:
    """[Owner directive, 2026-09-23] The DA ELEIÇÃO DO FORO clause's
    comarca, read off a matrícula's OWN transcription — never the imóvel's
    registration address (which can legitimately differ from the registering
    comarca). Called once at load time (`carregador.carregar`) over the
    resolved extraction's FULL raw text, independent of which acts the
    operator selected to quote — the comarca is a fact about the property's
    registry, not a clause excerpt. When the text names none, `foro_comarca`
    falls back to the cartório the operator confirmed on the imóvel.

    🔴 [foro-comarca-abertura-scope] Scoped to the matrícula's OWN abertura
    — everything before the first accepted R./AV header
    (`segment_matricula_atos`'s own boundary). Unscoped, an ACT's body can
    legitimately name an unrelated "município e comarca de X" (a notary's
    own city, cited inside an instrumento) — a Cotia matrícula whose R.5
    cites a "Tabelião de Notas do Município e Comarca de São Paulo" must
    never resolve to São Paulo.

    Precedence inside the abertura, most specific first: the registry's own
    heading (`_COMARCA_REGISTRO_RE`), then the "cidade/município e comarca
    de" boilerplate (`_COMARCA_MUNICIPIO_RE`) — when both are present and
    name DIFFERENT cidades neither is trusted (`None`) — then, only when
    neither exists, a bare "comarca de X" (`_COMARCA_SOLTA_RE`) provided
    every such citation not about another office agrees. "Comarca da
    Capital" resolves through the UF written beside it, else `uf` (the
    imóvel's). `None` is a real gap the caller names, never a guess."""
    if not texto:
        return None
    abertura = next(
        (a for a in segment_matricula_atos(texto) if a.kind == "abertura"), None
    )
    escopo = texto[: abertura.end] if abertura is not None else ""

    cabecalho: Optional[str] = None
    m = _COMARCA_REGISTRO_RE.search(escopo)
    if m:
        cidade = _cidade_da_comarca(m.group(1), m.group(2) or uf)
        if cidade:
            sigla = normalizar_uf(m.group(2)) if m.group(2) else None
            cabecalho = f"{cidade}/{sigla}" if sigla else cidade

    boilerplate: Optional[str] = None
    m = _COMARCA_MUNICIPIO_RE.search(escopo)
    if m:
        boilerplate = _cidade_da_comarca(m.group(1), uf)

    if cabecalho and boilerplate:
        return cabecalho if _mesma_cidade(cabecalho, boilerplate) else None
    if cabecalho or boilerplate:
        return cabecalho or boilerplate
    soltas = _comarcas_soltas(escopo, uf)
    return next(iter(soltas)) if len(soltas) == 1 else None


def foro_comarca(d: DadosContrato) -> Optional[str]:
    """The DA ELEIÇÃO DO FORO comarca — the ONE reader gate and template
    share. The matrícula's own text first (`comarca_de_texto`, resolved at
    load time onto `d.matricula.comarca`); otherwise the city of the cartório
    de registro de imóveis the operator confirmed on the imóvel
    (`imovel.numero_registro_imoveis`, itself a gated field) — the comarca
    IS the registering cartório's, so this is the same fact typed by a
    human, never the imóvel's street address."""
    if d.matricula.comarca:
        return d.matricula.comarca
    if d.imovel is None:
        return None
    partes = frases.cartorio_partes(d.imovel.numero_registro_imoveis)
    return partes[1] if partes else None


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
    # [Owner 2026-10-05] The previous owners live in the card's CERTIDÕES tab
    # (a group of the partes matrix), never in the parties list.
    "antigos_proprietarios": ("card_certidoes", "/clientes", "certidoes"),
    "matricula": ("matriculas", "/matriculas", None),
    "imovel": ("imovel", "/imoveis", None),
    "negociacao": ("card_negociacao", "/clientes", "negociacao"),
    "financiamento": ("card_financiamento", "/clientes", "financiamento"),
    "contrato": ("card_contratos", "/clientes", "contratos"),
    "imobiliaria": ("configuracoes", "/configuracoes", "imobiliaria"),
    # [Migration 215] The signing companies' own settings page (identity:
    # razão social, CNPJ, responsável, CRECI, cidade). Reached through a
    # falta grouped under `onde="imobiliaria"` via `destino_em=`.
    "imobiliarias": ("imobiliarias", "/imobiliarias", None),
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
#: The "Antigos proprietários" SUBTAB of the Certidões tab (its header carries
#: the required notice, dispense/undispense and manual add/remove). The id is
#: `certidoes-subtab-<grupo>` — the subtab key IS the certidões-partes
#: payload's `grupo`, so the UI selects the subtab straight from the alvo.
ALVO_ANTIGOS_PROPRIETARIOS = "certidoes-subtab-antigo_proprietario"
ALVO_ITENS_INTEGRANTES = "termos-itens-integrantes-resposta"
ALVO_AD_CORPUS = "termos-ad-corpus-resposta"
ALVO_DOCUMENTOS_DO_IMOVEL = "imovel-documentos"
#: The posse controls (prazo / marco / data fixa) of the Termos panel, and the
#: permuta imóvel's own posse controls — `TermosNegocioSection`'s two sections.
ALVO_POSSE = "termos-posse-controles"
ALVO_PERMUTA_POSSE = "termos-permuta-posse-controles"


def alvo_imobiliaria_select(contrato_id: Optional[str]) -> Optional[str]:
    """DOM id of the contract's "Imobiliária que assina" picker
    (`ImobiliariaSelect`). Per CONTRACT — a card lists several, so the id
    carries the contrato id (the `aditivo-<id>` convention). `None` when the
    evaluation has no contrato (the card subpage itself is the answer)."""
    return f"contrato-imobiliaria-select-{contrato_id}" if contrato_id else None


def alvo_testemunhas_select(contrato_id: Optional[str]) -> Optional[str]:
    """DOM id of the contract's witnesses picker block (`ContratosPanel`'s
    testemunhas wrapper — always mounted, unlike the collapsible's body)."""
    return f"contrato-testemunhas-select-{contrato_id}" if contrato_id else None


def alvo_emissao_certidao_imovel(tipo: str) -> str:
    """The imóvel page's certidão card input where an operator types a
    certidão's emission date by hand (`ImovelCertidoesCard`: id
    `certidao-${tipo}-${campo}`, saved through `PATCH …/documentos/{id}/
    extracao`, which locks the row against a later re-read)."""
    return f"certidao-{tipo}-emitida_em"


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
    #: Things that are NOT wrong data but must be KNOWN by the operator before
    #: the contract is generated (owner amendment 2026-10-01): each carries
    #: `ciente`; the contract is not `pronto` until every one is acknowledged.
    confirmacoes: list[dict] = field(default_factory=list)
    destinos: Destinos = field(default_factory=Destinos)
    #: [Migration 193] Wording the final legal review must read with care —
    #: recorded on the generated version (`revisao_juridica_itens`). Never a
    #: readiness condition: the review itself is the gate.
    itens_revisao: list[dict] = field(default_factory=list)

    @property
    def pendentes_confirmacao(self) -> list[dict]:
        return [c for c in self.confirmacoes if not c["ciente"]]

    @property
    def pronto(self) -> bool:
        return not self.faltando and not self.bloqueios and not self.pendentes_confirmacao

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

    def revisar(self, codigo: str, titulo: str, texto: str) -> None:
        item = {"codigo": codigo, "titulo": titulo, "texto": texto}
        if item not in self.itens_revisao:
            self.itens_revisao.append(item)


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
    """THE ordering point of the payment schedule — the printed "Parcela NN"
    numbers, every reference to them and every amount are derived from this
    one list (`grupos_de_parcelas` → `numeros_impressos`), never re-sorted.

    Rule: the persisted `ordem` (the operator's order, written by
    `PUT /negociacao/parcelas/ordem`; ties fall back to the read order, i.e.
    `created_at`) is the source of truth, with ONE invariant on top — the
    sinal is the first payment (all signed contracts print it as Parcela 01).
    A sinal created after an auto-suggested financiamento/intermediária
    stores a LATER `ordem` and used to print as "Parcela 03 (Sinal)" with
    every amount shifted; when the first sinal is not first, its consecutive
    run (a sinal paid in tranches, kept together) is hoisted to the front.
    Non-consecutive sinais stay where `ordem` put them so the
    `SINAIS_NAO_CONSECUTIVOS` gate still sees them.

    The hoist is the DEFAULT, adjustable per deal (`termos.sinal_primeira_parcela`,
    migration 206): turned OFF, the persisted `ordem` is followed exactly."""
    por_ordem = sorted(d.parcelas, key=lambda p: p.ordem)  # stable: ties keep read order
    if not d.termos.sinal_primeira_parcela:
        return por_ordem
    primeiro = next((i for i, p in enumerate(por_ordem) if p.tipo == "sinal"), None)
    if not primeiro:  # no sinal, or already first
        return por_ordem
    fim = primeiro
    while fim < len(por_ordem) and por_ordem[fim].tipo == "sinal":
        fim += 1
    return por_ordem[primeiro:fim] + por_ordem[:primeiro] + por_ordem[fim:]


def grupos_de_parcelas(d: DadosContrato) -> list[list[Parcela]]:
    """The PRINTED parcelas — one list per "Parcela NN" line, in schedule
    order. Two shapes print several stored parcelas as ONE line, both read
    off the office's signed contracts (clause catalog §2):

    - consecutive `sinal` parcelas: the sinal paid in tranches inside
      Parcela 01 ("Sinal e princípio de pagamento: {TOTAL}, a serem pagos da
      seguinte forma: {A} no ato da assinatura …, e {B} …" — the only signed
      shape with more than one sinal payment; no contract labels two
      parcelas "Sinal"). Non-consecutive sinais are NOT folded — the gate
      refuses them (`SINAIS_NAO_CONSECUTIVOS`).
    - an `fgts` parcela next to exactly ONE `financiamento` parcela: FGTS is
      printed inside the financing parcela with the split amounts in every
      signed contract that names it (5 deals; 0 print it as its own
      parcela). The fgts parcela joins the financing parcela's line; any
      other fgts shape is refused (`derivacao._financiamento`).

    Every number the contract prints — the parcela lines, the posse marco,
    the corretagem marcos, the sinal/financiamento references — is computed
    from these groups, so a folded parcela never leaves a gap."""
    ordenadas = parcelas_ordenadas(d)
    fins = [p for p in ordenadas if p.tipo == "financiamento"]
    fgts = [p for p in ordenadas if p.tipo == "fgts"]
    fgts_dobrado = fgts[0] if len(fins) == 1 and len(fgts) == 1 else None
    grupos: list[list[Parcela]] = []
    for p in ordenadas:
        if p is fgts_dobrado:
            continue
        if p.tipo == "sinal" and grupos and grupos[-1][0].tipo == "sinal":
            grupos[-1].append(p)
            continue
        grupos.append([p])
        if fgts_dobrado is not None and p is fins[0]:
            grupos[-1].append(fgts_dobrado)
    return grupos


def numeros_impressos(d: DadosContrato) -> dict[str, str]:
    """`{parcela_id: printed number}` — a folded parcela carries its line's
    number (`grupos_de_parcelas`)."""
    return {
        p.id: num2(i) for i, grupo in enumerate(grupos_de_parcelas(d), start=1) for p in grupo
    }


def numero_da_parcela(d: DadosContrato, parcela_id: Optional[str]) -> Optional[str]:
    """The printed number (`num2`) of the parcela an id NAMES, or None when it
    names one that is not in this deal. Used for [§6.1 #12]'s posse marco:
    the clause cites a COMPUTED number, never a typed one."""
    if not parcela_id:
        return None
    return numeros_impressos(d).get(parcela_id)


def parcelas_antes_de(d: DadosContrato, parcela_id: Optional[str]) -> list[str]:
    """The numbers of the parcelas that fall BEFORE the marco parcela — the
    posse condition ("com a condição que as parcelas 01 e 02 …")."""
    numeros: list[str] = []
    for i, grupo in enumerate(grupos_de_parcelas(d), start=1):
        if any(p.id == parcela_id for p in grupo):
            return numeros
        numeros.append(num2(i))
    return []


def corretagem_marcos(d: DadosContrato) -> list[str]:
    """[§6.1 #23] The parcelas whose receipt triggers the corretagem payment,
    as computed numbers — the marco is `Parcela.dispara_corretagem` (114),
    never a typed parcela index."""
    return [
        num2(i)
        for i, grupo in enumerate(grupos_de_parcelas(d), start=1)
        if any(p.dispara_corretagem for p in grupo)
    ]


def valores_da_divisao(p: Parcela) -> list[Optional[Decimal]]:
    """[Migration 192] Each share's amount in reais: its `valor`, or its
    `percentual` of the parcela rounded to the cent (the office prints both,
    "{VALOR}, correspondentes a {PCT}% … da parcela"). `None` when the share
    has neither yet. Whether they add up to the parcela is the gate's call
    (`DIVISAO_SOMA_DIVERGE` / `DIVISAO_PERCENTUAL_INEXATO`) — nothing here
    absorbs a rounding cent into some share."""
    saida: list[Optional[Decimal]] = []
    for q in p.divisao:
        if q.valor is not None:
            saida.append(q.valor)
        elif q.percentual is not None and p.valor is not None:
            saida.append((p.valor * q.percentual / Decimal("100")).quantize(Decimal("0.01"), ROUND_HALF_UP))
        else:
            saida.append(None)
    return saida


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
    # [P5] A matrícula VISUALIZAÇÃO (migration 199) is never presented as a
    # certidão, dated or not — `_certidoes_imovel_pendentes` asks for one.
    por_tipo = {c.tipo: c for c in im.certidoes if c.emitida_em and not _e_visualizacao(c)}
    # The pre-118 `onus_certidao_em` fallback answers ONLY a card with no
    # matrícula document at all: a visualização or an undated certidão on
    # file is a named gap, never silently answered by an older field (the
    # false-ready P5 found).
    tem_documento_matricula = any(c.tipo == "matricula" for c in im.certidoes)
    if (
        "matricula" not in por_tipo
        and not tem_documento_matricula
        and im.onus_certidao_em
        and im.numero_matricula
    ):
        por_tipo["matricula"] = CertidaoImovel(
            tipo="matricula", numero=im.numero_matricula, emitida_em=im.onus_certidao_em
        )
    return tuple(por_tipo[tipo] for tipo in ORDEM_CERTIDOES_IMOVEL if tipo in por_tipo)


def _e_visualizacao(c: CertidaoImovel) -> bool:
    return c.tipo == "matricula" and c.tipo_documento_matricula == TIPO_VISUALIZACAO


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
    situacao_onus = d.imovel.situacao_onus if d.imovel else None
    # [Migration 193] 'ja_quitado': the debt is PAID and its baixa requested
    # — nothing left to settle, so it is not a saldo devedor; deal 867's
    # objeto paragraph is printed instead.
    onus_ja_quitado = (
        situacao_onus in ONUS_COM_SALDO and termos.onus_quitacao == frases.QUITACAO_ONUS_JA_QUITADO
    )
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
        "tem_saldo_devedor": situacao_onus in ONUS_COM_SALDO and not onus_ja_quitado,
        "tem_onus_ja_quitado": onus_ja_quitado,
        "tem_usufruto": situacao_onus == ONUS_USUFRUTO,
        # [Migration 193] The seller's spouse/companion signing as ANUENTE.
        "tem_anuentes": bool(anuentes(d.vendedores)),
        # [Migration 193] Operator-typed obligations, printed verbatim.
        "tem_obrigacoes_vendedor": bool(frases.paragrafos_livres(termos.obrigacoes_vendedor)),
        "tem_permuta_obrigacoes": tem_permuta
        and bool(frases.paragrafos_livres(termos.permuta_obrigacoes_entrega)),
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
        "tem_multa_diaria_posse": posse_multa_diaria(d) is not None,
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


def posse_multa_diaria(d: DadosContrato) -> Optional[Decimal]:
    """[Q12 + migration 207] The daily fine for a late posse: the deal's own
    override (`Termos.posse_multa_diaria`) → the office value
    (`Imobiliaria.posse_multa_diaria`) → None (a `faltando`)."""
    if d.termos.posse_multa_diaria is not None:
        return d.termos.posse_multa_diaria
    return d.imobiliaria.posse_multa_diaria


def clausulas_extras_ativas(d: DadosContrato) -> dict[str, tuple[list[str], str]]:
    """[Migration 207] The clauses carrying special conditions that PRINT: clause
    key -> (typed paragraphs, modo), only for a non-empty entry on a known key.
    Iterated in the contract's own clause order, so every consumer (gate,
    context, review items) sees the same sequence."""
    saida: dict[str, tuple[list[str], str]] = {}
    for chave in ORDEM_CLAUSULAS:
        entrada = d.termos.clausulas_extras.get(chave)
        if entrada is None:
            continue
        paragrafos = frases.paragrafos_livres(entrada.texto)
        if paragrafos:
            saida[chave] = (paragrafos, entrada.modo)
    return saida


def prazo_pendencias(d: DadosContrato, politica: Politica) -> int:
    """[Q11] contract override → office default → 10 days."""
    if d.prazo_pendencias_dias is not None:
        return d.prazo_pendencias_dias
    if d.imobiliaria.prazo_pendencias_padrao_dias is not None:
        return d.imobiliaria.prazo_pendencias_padrao_dias
    return politica.prazo_pendencias_padrao_dias


# ─── certidões index ──────────────────────────────────────────────────────


def _rotulo_certidao_seguro(tipo: str) -> str:
    """A readiness-message label for ANY stored tipo — `frases.rotulo_
    certidao` only knows the printed ones (e.g. the system `tjsp`)."""
    if any(c[0] == tipo for c in frases.CERTIDOES):
        return frases.rotulo_certidao(tipo, None)
    return tipo


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


def _empresas_de_certificandos(
    d: DadosContrato,
    sw: dict[str, bool],
    politica: Politica = POLITICA_PADRAO,
    assinatura: Optional[date] = None,
) -> list[tuple[Empresa, Pessoa]]:
    """[E1/E3/E6] Every `d.empresas` row a certificando pessoa holds a
    participação in — signing vendedores + their cônjuges (E3: a married
    vendedor's cônjuge is a vendedor too), plus signing compradores +
    cônjuges when `tem_permuta` (E6: the comprador giving an imóvel gets
    exactly the vendedor treatment). Paired with the certificando `Pessoa`
    (from `empresa.owners`) the readiness report attributes it to — one
    pair per `Empresa` (E4; `d.empresas` already carries one row per
    DISTINCT company, `owners` holding every participant)."""
    certificandos = signatarios_certificandos(d, sw, politica)
    # [Owner 2026-10-05] An anuente (signs, owns nothing) is never certified
    # — nor are their companies, even when they are the registered cônjuge of
    # a certificando (E3 reaches the spouse through `conjuge_cliente_id`).
    ids = {p.cliente_id for p in certificandos}
    # A spouse is a certificando (E3); a companion is not (P5 F8).
    dispensados = {
        p.cliente_id for p in d.vendedores + d.compradores if companheiro_dispensado(d, p, politica)
    } | {a.cliente_id for a in anuentes(d.vendedores)}
    ids |= {
        p.conjuge_cliente_id for p in certificandos
        if p.conjuge_cliente_id and p.conjuge_cliente_id not in dispensados
    }
    pares: list[tuple[Empresa, Pessoa]] = []
    for e in d.empresas:
        dono = next((o for o in e.owners if o.cliente_id in ids), None)
        if dono is not None:
            pares.append((e, dono))
    # [Owner 2026-10-05] The companies of the PREVIOUS owners are certified
    # with the SAME rule as the sellers' (ATIVA/INAPTA any stake; baixada < 5
    # years; older baixadas omitted) — whenever the antigos enter the
    # contract. `_empresas_de_certificandos` is the one place that rule is
    # applied; an antigo is simply one more certificando here.
    if assinatura is not None and antigos_no_contrato(d, assinatura, politica):
        ids_antigos = {p.cliente_id for p in antigos_proprietarios(d)}
        ja = {e.id for e, _ in pares}
        for e in d.empresas:
            if e.id in ja:
                continue
            dono = next((o for o in e.owners if o.cliente_id in ids_antigos), None)
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


def classificar_situacao_pj(
    situacao_cadastral: Optional[str],
    data_situacao_cadastral: Optional[date],
    referencia: date,
    janela_anos: int,
) -> str:
    """[E1] The pure decision, on primitives alone — the SINGLE SOURCE for
    every empresa/PJ classification in this product. Whether an empresa's
    certidão group is required, from its OWN Cartão-CNPJ-sourced
    `situacao_cadastral`/`data_situacao_cadastral` (never a certidão-
    consulta row, which may not exist yet): `ativa`/`inapta` always;
    `baixada` only when closed less than `janela_anos` before `referencia`
    (TODAY — `_hoje_padrao`/`service.hoje()`, NEVER the assinatura: E2/H2);
    `suspensa`/`nula`/older baixadas are omitted. NULL `situacao_cadastral`
    (no Cartão uploaded yet) -> `PJ_SEM_SITUACAO`, the caller's `faltando:
    cartao_cnpj` (E1, H4).

    `classificar_empresa` (this module, the contract-generation gate) and
    `card_hub.empresas_service._motivo_e_exigencia` (the `GET /api/
    clientes/{id}/empresas` display-only badge, via `motivo_publico` below)
    both call this — an N=2 recurrence the recurrence rule flags at first
    sight, formalized here rather than shipped a third time."""
    if situacao_cadastral is None:
        return PJ_SEM_SITUACAO
    if situacao_cadastral not in SITUACOES_CADASTRAIS:
        return PJ_SITUACAO_DESCONHECIDA
    if situacao_cadastral in SITUACOES_PJ_EXIGIDAS:
        return PJ_EXIGIDO
    if situacao_cadastral != SITUACAO_PJ_BAIXADA:
        return PJ_OMITIDO
    if data_situacao_cadastral is None:
        return PJ_SEM_DATA_SITUACAO
    if ha_menos_de_anos(data_situacao_cadastral, referencia, janela_anos):
        return PJ_EXIGIDO_BAIXADA
    return PJ_OMITIDO


def classificar_empresa(e: Empresa, referencia: date, politica: Politica) -> str:
    """`classificar_situacao_pj`, unwrapping an `Empresa`/`Politica` — see
    that function for the actual decision."""
    return classificar_situacao_pj(
        e.situacao_cadastral, e.data_situacao_cadastral, referencia,
        politica.pj_baixada_janela_anos,
    )


#: `classificar_situacao_pj`'s codes that have exactly one fixed public
#: label, independent of `situacao_cadastral` — `PJ_EXIGIDO` (the label IS
#: the empresa's own situação string) and `PJ_OMITIDO` (means EITHER "never
#: a baixada" or "baixada, past the window" — disambiguated in
#: `motivo_publico` below) are handled separately.
_MOTIVO_PUBLICO_FIXO: dict[str, str] = {
    PJ_SEM_SITUACAO: "sem_cartao_cnpj",
    PJ_SEM_DATA_SITUACAO: "sem_cartao_cnpj",
    PJ_SITUACAO_DESCONHECIDA: "outra_situacao",
    PJ_EXIGIDO_BAIXADA: "baixada_menos_5_anos",
}


def motivo_publico(codigo: str, situacao_cadastral: Optional[str]) -> tuple[bool, str]:
    """`(exigido, motivo)` in `GET /api/clientes/{id}/empresas`'s own public
    vocabulary (contract §D1: `ativa|baixada_menos_5_anos|baixada_5_anos_
    ou_mais|sem_cartao_cnpj|outra_situacao|sem_socio_certificando` — the
    last is decided by the caller, off `owners`, not by this function) —
    the SAME decision `classificar_situacao_pj` made for the contract-
    generation gate, translated for `card_hub.empresas_service.listar`'s
    display-only badge. `exigido` mirrors `empresas_exigidas`' own
    `PJ_CODIGOS_EXIGIDOS` filter — never re-derived independently, so the
    badge and the gate can never disagree for the same empresa row."""
    exigido = codigo in PJ_CODIGOS_EXIGIDOS
    if codigo == PJ_EXIGIDO:
        return exigido, situacao_cadastral or ""
    if codigo == PJ_OMITIDO:
        motivo = (
            "baixada_5_anos_ou_mais" if situacao_cadastral == SITUACAO_PJ_BAIXADA
            else "outra_situacao"
        )
        return exigido, motivo
    return exigido, _MOTIVO_PUBLICO_FIXO.get(codigo, "outra_situacao")


def empresas_exigidas(
    d: DadosContrato,
    sw: dict[str, bool],
    referencia: date,
    politica: Politica,
    assinatura: Optional[date] = None,
) -> list[EmpresaExigida]:
    """(empresa, title suffix, attributed owner) of each REQUIRED company —
    E1 classification against `referencia` (TODAY, never the assinatura).
    A company with no Cartão yet, or an unresolved baixada date, is NOT
    "required" here (it is a named `faltando`/`bloqueia` instead — see
    `_empresas_certidoes`, which walks EVERY certificando-owned company,
    not just this filtered set)."""
    saida: list[EmpresaExigida] = []
    for e, dono in _empresas_de_certificandos(d, sw, politica, assinatura):
        motivo = classificar_empresa(e, referencia, politica)
        if motivo == PJ_EXIGIDO:
            saida.append(EmpresaExigida(empresa=e, sufixo=None, owner=dono))
        elif motivo == PJ_EXIGIDO_BAIXADA:
            saida.append(EmpresaExigida(empresa=e, sufixo=SUFIXO_PJ_BAIXADA, owner=dono))
    return saida


def antigos_proprietarios(d: DadosContrato) -> list[Pessoa]:
    return [p for p in d.vendedores if p.papel == PAPEL_ANTIGO_PROPRIETARIO]


def antigos_proprietarios_pj(d: DadosContrato) -> list[ParteJuridica]:
    """[P5, deals 858/869] A COMPANY that sold in the last registered
    transfer (a construtora, typically). Like a person antigo it signs
    nothing and is not qualified — it only presents its CNPJ certidões
    when the antigos enter the contract (`antigos_no_contrato`)."""
    return [pj for pj in d.partes_pj if pj.papel == PAPEL_ANTIGO_PROPRIETARIO]


def partes_pj_contratantes(d: DadosContrato) -> list[ParteJuridica]:
    """The company parties that ARE parties to this contract — every PJ but
    an antigo proprietário (`antigos_proprietarios_pj`)."""
    return [pj for pj in d.partes_pj if pj.papel != PAPEL_ANTIGO_PROPRIETARIO]


def conjuge_do_anuente(d: DadosContrato, a: Pessoa) -> Optional[Pessoa]:
    """[Migration 193] The signing VENDEDOR an anuente is the reciprocal
    spouse/companion of — the only anuente the corpus words (7 deals). `None`
    for any other anuente: no wording (`ANUENTE_SEM_REDACAO`)."""
    if a.lado != "vendedor" or not frases.forma_nucleo(a):
        return None
    conjuge = next(
        (v for v in signatarios(d.vendedores) if v.cliente_id == a.conjuge_cliente_id), None
    )
    if conjuge is None or conjuge.conjuge_cliente_id != a.cliente_id:
        return None
    return conjuge


#: Estados civis that say a person is NOT married to whoever they are
#: linked to — the link is then a companionship (união estável de fato).
_ESTADOS_SEM_CASAMENTO = frozenset({"solteiro", "divorciado", "viuvo", "separado_judicialmente"})


def companheiro_dispensado(d: DadosContrato, p: Pessoa, politica: Politica = POLITICA_PADRAO) -> bool:
    """[P5 F8] Is `p` a NON-OWNER signing as a seller's companion — not a
    spouse — and therefore not a certificando (`Politica.
    companheiro_apresenta_certidoes`)? Only papel `conjuge`/`anuente`, only
    with a linked partner on the card, and only when the couple is not
    married: either says `uniao_estavel`, or the partner's own estado civil
    says unmarried (deal 867: divorciado seller + companion whose estado
    civil is not even set). Unknown on both sides ⇒ not dispensed (the
    estado civil is its own `faltando`)."""
    if politica.companheiro_apresenta_certidoes or p.papel not in ("conjuge", PAPEL_ANUENTE):
        return False
    par = next(
        (q for q in d.vendedores + d.compradores if q.cliente_id == p.conjuge_cliente_id), None
    )
    if par is None:
        return False
    estados = {p.estado_civil, par.estado_civil}
    if "casado" in estados:
        return False
    # [198] `em_uniao_estavel` covers the flag beside a legal status too.
    return (
        frases.em_uniao_estavel(p)
        or frases.em_uniao_estavel(par)
        or par.estado_civil in _ESTADOS_SEM_CASAMENTO
    )


def signatarios_certificandos(
    d: DadosContrato, sw: dict[str, bool], politica: Politica = POLITICA_PADRAO
) -> list[Pessoa]:
    """The SIGNING certificandos: every signing vendedor — a companion
    excepted (`companheiro_dispensado`) — plus the signing compradores in a
    permuta (E6). The one list gate, template and empresa lookup share."""
    pessoas = signatarios(d.vendedores) + (signatarios(d.compradores) if sw["tem_permuta"] else [])
    return [p for p in pessoas if not companheiro_dispensado(d, p, politica)]


def pj_certificandas(d: DadosContrato, sw: dict[str, bool]) -> list[ParteJuridica]:
    """[Migration 193] PJ parties that present certidões: every PJ vendedor,
    and a PJ comprador in a permuta — the SAME rule as a person. A PJ
    presents only its own 11 CNPJ certidões; its representantes are not
    certificandos."""
    return [
        pj for pj in partes_pj_contratantes(d)
        if pj.lado == "vendedor" or (pj.lado == "comprador" and sw["tem_permuta"])
    ]


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


def empresas_impressas_como_parte(d: DadosContrato, assinatura: date, politica: Politica) -> set[str]:
    """The `empresa_id`s whose certidão group is printed as a PARTY's (the
    contracting PJs, plus a company antigo when the antigos enter the
    contract) — a certificando's Crednet company that is one of them is not
    printed a second time."""
    ids = {pj.empresa_id for pj in partes_pj_contratantes(d)}
    if antigos_no_contrato(d, assinatura, politica):
        ids |= {pj.empresa_id for pj in antigos_proprietarios_pj(d)}
    return ids


def antigos_no_contrato(d: DadosContrato, assinatura: date, politica: Politica) -> bool:
    """Do the previous owner(s) ENTER the instrument? [Q9] requires them —
    except on a `processo_legado` deal, whose gate (`_certidoes`) skips them
    and says so (`ANTIGO_PROPRIETARIO_PROCESSO_LEGADO`: "não entram no
    contrato"). The ONE predicate gate and template share, so a legacy deal
    never prints antigos the gate never checked (name, gênero, certidões)."""
    return (
        bool(exige_antigo_proprietario(d, assinatura, politica))
        and not d.processo_legado
        and not d.antigos_dispensados
    )


def pessoas_certificadas(
    d: DadosContrato, sw: dict[str, bool], assinatura: date, politica: Politica
) -> list[Pessoa]:
    """Whose certidões the contract presents, in group order: the signing
    vendedores, the signing compradores in a permuta, then the previous
    owner(s) when they enter the contract (`antigos_no_contrato`)."""
    pessoas = signatarios_certificandos(d, sw, politica)
    if antigos_no_contrato(d, assinatura, politica):
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


#: [P5 F7] A profissão that says the person runs a company.
_PROFISSAO_SOCIO_RE = re.compile(r"empres[áa]ri|s[óo]ci[oa]|administrador|comerciante", re.IGNORECASE)

#: [P5 F8] Qualificação keys a missing value of which WARNS instead of
#: blocking — the signed corpus omits them (see the call site), and the
#: wording omits the fragment cleanly. key -> (aviso code, message tail).
_CHAVES_QUALIFICACAO_AVISO: dict[str, tuple[str, str]] = {
    "profissao": ("PARTE_SEM_PROFISSAO", "não tem profissão; a qualificação sai sem ela."),
    "rg_orgao_expedidor": (
        "RG_SEM_ORGAO_EXPEDIDOR",
        "não tem órgão expedidor do RG; a qualificação sai só com o número.",
    ),
}

#: [Migration 193] Qualificação keys a REPRESENTANTE never prints: they sign
#: for a company and are qualified alone ("casada", no regime, no spouse) —
#: owner rule: no spouse anuência for a PJ by default.
_CHAVES_SEM_EFEITO_NO_REPRESENTANTE = frozenset(
    {"conjuge", "conjuge_qualificacao", "regime_bens", "data_casamento"}
)

#: [Migration 193] The PJ papéis the corpus's PJ wording covers (deal 866: a
#: company that IS the seller). Any other papel on a company is refused.
_PAPEIS_PJ_COM_REDACAO = frozenset({"proprietario", "comprador"})

PJ_REDACAO_A_CONFIRMAR = (
    "redação de PJ derivada de um único contrato assinado — confirme na revisão jurídica"
)


def _parte_juridica(av: Avaliacao, d: DadosContrato, pj: ParteJuridica) -> None:
    """[Migration 193] A company party — qualified with corpus deal 866's
    wording, every field of which is a named `faltando` (never the old
    blanket `partes.pj_sem_qualificacao`)."""
    nome = pj.razao_social or frases.documento(pj.cnpj)[1] or "empresa"
    ancora = _ANCORA_POR_LADO.get(pj.lado, "geral")
    for valor, campo, rotulo in (
        (pj.razao_social, "razao_social", "Razão social"),
        (pj.cnpj, "cnpj", "CNPJ"),
        (pj.nire, "nire", "NIRE (registro na Junta Comercial)"),
        (pj.sede.logradouro, "sede_logradouro", "Logradouro da sede"),
        (pj.sede.numero, "sede_numero", "Número da sede"),
        (pj.sede.bairro, "sede_bairro", "Bairro da sede"),
        (pj.sede.cidade, "sede_cidade", "Cidade da sede"),
        (pj.sede.uf, "sede_uf", "UF da sede"),
        (pj.sede.cep, "sede_cep", "CEP da sede"),
    ):
        if not (valor or "").strip():
            av.falta(f"partes.pj.{campo}", f"{rotulo} — {nome}", "partes", pj.parte_id, ancora=ancora)
    if pj.cnpj and not cnpj_valido(pj.cnpj):
        av.bloqueia("CNPJ_INVALIDO", f"O CNPJ de {nome} não confere (dígitos verificadores).")
    if pj.papel not in _PAPEIS_PJ_COM_REDACAO:
        av.bloqueia(
            "PJ_PAPEL_SEM_REDACAO",
            f"{nome} é parte como '{pj.papel}': o gerador só tem redação para a empresa que "
            "vende ou compra (proprietário/comprador).",
        )
    reps = representantes(d.vendedores + d.compradores, pj.parte_id)
    if not reps:
        av.falta(
            "partes.pj.representante",
            f"Representante legal (sócio(a) e administrador(a)) que assina por {nome} — "
            "adicione a pessoa como parte com o papel 'representante' vinculada à empresa",
            "partes",
            pj.parte_id,
            ancora=ancora,
        )
    elif len(reps) > 1:
        # The corpus's one PJ contract is signed by ONE representative —
        # joint representation has no wording.
        av.bloqueia(
            "PJ_MAIS_DE_UM_REPRESENTANTE",
            f"{nome} tem {len(reps)} representantes: o gerador só tem redação para um.",
        )
    elif reps[0].lado != pj.lado:
        av.bloqueia(
            "REPRESENTANTE_FORA_DO_LADO",
            f"O representante de {nome} precisa estar no mesmo lado do contrato que a empresa.",
        )
    av.avisa("PJ_REDACAO_A_CONFIRMAR", f"{nome}: {PJ_REDACAO_A_CONFIRMAR}.")
    av.revisar(
        "PJ_REDACAO_A_CONFIRMAR",
        f"Qualificação da empresa {nome}",
        PJ_REDACAO_A_CONFIRMAR,
    )


def _pacto_do_casal(
    av: Avaliacao, a: Pessoa, b: Pessoa, politica: Politica, vistos: set[frozenset[str]]
) -> None:
    """[Migration 193] The pacto antenupcial a married couple's qualification
    cites (corpus deal 858): an aviso when the regime needs one and none is on
    file, every missing field named when half-entered, refused when the two
    spouses' rows disagree."""
    par = frozenset({a.cliente_id, b.cliente_id})
    if par in vistos or a.estado_civil != "casado":
        return
    vistos.add(par)
    preenchidos = [p for p in (a, b) if p.pacto is not None and not p.pacto.vazio()]
    if len(preenchidos) == 2 and preenchidos[0].pacto != preenchidos[1].pacto:
        av.bloqueia(
            "PACTO_ANTENUPCIAL_DIVERGENTE",
            f"{_nome(a)} e o cônjuge têm dados de pacto antenupcial diferentes.",
        )
    pacto = frases.pacto_do_casal(a, b)
    if pacto is None:
        # [2026-10-03] An AVISO, not a faltando: the signed corpus cites the
        # pacto in only 1 of 3 separação-total contracts (deal 858) — the
        # office signs without the citation, so its absence cannot block.
        # Once ANY citation data is on file, the missing pieces below stay
        # faltando (a half-printed citation is worse than none).
        if frases.regime_exige_pacto(a.regime_bens, a.data_casamento, politica.lei_6515_vigencia_desde):
            av.avisa(
                "PACTO_ANTENUPCIAL_NAO_CITADO",
                f"{_nome(a)}: o regime de "
                f"{frases.REGIME_EXTENSO.get(a.regime_bens or '', a.regime_bens)} exige pacto "
                "antenupcial; cite-o se houver a escritura (data, tabelionato, livro e página).",
            )
        return
    dono = preenchidos[0]
    for valor, campo, rotulo in (
        (pacto.data, "data", "Data da escritura de pacto antenupcial"),
        (pacto.tabelionato, "tabelionato", "Tabelionato da escritura de pacto antenupcial"),
        (pacto.livro, "livro", "Livro da escritura de pacto antenupcial"),
        (pacto.folha, "folha", "Página da escritura de pacto antenupcial"),
    ):
        if not (str(valor).strip() if valor is not None else ""):
            av.falta(
                f"qualificacao.pacto_antenupcial_{campo}",
                f"{rotulo} — {_nome(dono)}",
                "partes",
                dono.parte_id,
                ancora=_ancora(dono),
            )


def _identidade(av: Avaliacao, p: Pessoa) -> None:
    """[Migration 193] RG vs RNE/RNM (a foreign party — corpus: 3 deals)."""
    tipo = (p.identidade_tipo or "rg").strip().lower()
    if tipo not in frases.IDENTIDADES_VALIDAS:
        av.bloqueia(
            "IDENTIDADE_TIPO_DESCONHECIDO",
            f"O tipo de documento de identidade de {_nome(p)} ('{p.identidade_tipo}') não tem redação no gerador.",
        )
        return
    brasileiro = frases.e_brasileiro(p)
    if tipo in frases.IDENTIDADES_ESTRANGEIRO and brasileiro:
        av.bloqueia(
            "IDENTIDADE_ESTRANGEIRO_BRASILEIRO",
            f"{_nome(p)} tem nacionalidade brasileira, mas está identificado(a) por "
            f"{frases.IDENTIDADES_ESTRANGEIRO[tipo]} (documento de estrangeiro).",
        )
    elif tipo == "rg" and (p.nacionalidade or "").strip() and not brasileiro:
        av.avisa(
            "ESTRANGEIRO_COM_RG",
            f"{_nome(p)} não tem nacionalidade brasileira e está identificado(a) por RG: confirme se o "
            "documento é um RNE/RNM e, se for, marque o tipo do documento.",
        )


def _partes(av: Avaliacao, d: DadosContrato, politica: Politica = POLITICA_PADRAO) -> None:
    """The parties gate. `politica` defaults to the office's — keeps the
    two-argument call `contrato_aditivo` makes working (its pacto check
    reads only `lei_6515_vigencia_desde`)."""
    vend, comp = signatarios(d.vendedores), signatarios(d.compradores)
    antigos = antigos_proprietarios(d)
    anu = anuentes(d.vendedores + d.compradores)
    reps = representantes(d.vendedores + d.compradores)
    contratantes_pj = partes_pj_contratantes(d)
    pj_ids = {pj.parte_id for pj in contratantes_pj}
    if not vend and not any(pj.lado == "vendedor" for pj in contratantes_pj):
        av.falta("partes.vendedores", "Ao menos um vendedor (proprietário) no card", "partes", ancora="vendedor")
    if not comp and not any(pj.lado == "comprador" for pj in contratantes_pj):
        av.falta("partes.compradores", "Ao menos um comprador no card", "partes")
    # A company antigo proprietário is not qualified (no NIRE/sede/
    # representante) — `_certidoes` gates it, like a person antigo.
    for pj in contratantes_pj:
        _parte_juridica(av, d, pj)
    for r in reps:
        if r.representa_parte_id not in pj_ids:
            av.bloqueia(
                "REPRESENTANTE_SEM_EMPRESA",
                f"{_nome(r)} é representante, mas não está vinculado(a) a uma empresa que seja parte "
                "deste contrato.",
            )
    for a in anu:
        if conjuge_do_anuente(d, a) is None:
            # [Migration 193] The corpus words ONE anuente: a signing seller's
            # spouse/companion (7 deals; the PJ's case is a representative's
            # spouse, refused by owner rule — no spouse anuência for a PJ).
            av.bloqueia(
                "ANUENTE_SEM_REDACAO",
                f"{_nome(a)} é anuente, mas não é cônjuge/companheiro(a) (vínculo recíproco no card) de "
                "um vendedor pessoa física: o gerador só tem redação de anuência de cônjuge/companheiro(a).",
            )
    for p in d.vendedores + d.compradores:
        if p not in vend and p not in comp and p not in antigos and p not in anu and p not in reps:
            av.avisa(
                "PARTE_NAO_SIGNATARIA",
                f"{_nome(p)} ({p.papel}) não entra na qualificação nem assina o contrato.",
            )

    documentos: dict[str, str] = {}
    casais: set[frozenset[str]] = set()
    # The anuente is qualified with (and gated against) the seller side: a
    # married seller whose spouse signs as anuente has that spouse "on the
    # side". A representante is qualified alone (`avulso`), its own group.
    for lado_pessoas, e_representante in ((vend + anu, False), (comp, False), (reps, True)):
        ids_lado = {p.cliente_id: p for p in lado_pessoas}
        for p in lado_pessoas:
            _identidade(av, p)
            # [Owner decision, 2026-10-03] a missing BAIRRO warns, never blocks
            # (the other address fields still gate via `faltando_qualificacao`).
            if (
                "endereco" not in p.faltando_qualificacao
                and p.endereco is not None
                and not (p.endereco.bairro or "").strip()
            ):
                av.avisa(
                    "ENDERECO_SEM_BAIRRO",
                    f"Endereço de {_nome(p)} sem bairro — o contrato sai sem o bairro.",
                )
            for chave in p.faltando_qualificacao:
                if e_representante and chave in _CHAVES_SEM_EFEITO_NO_REPRESENTANTE:
                    continue
                conjuge = ids_lado.get(p.conjuge_cliente_id or "")
                if chave == "conjuge_qualificacao" and conjuge is not None:
                    continue  # the spouse is a signatory and is gated on their own
                # [P5 F8, 2026-10-03 — owner delegated, under his rule "if
                # the signed contracts have it, it is required; if they
                # don't, it is a doubt"] supersedes the 2026-09-23 "all
                # mandatory": the office's signed contracts routinely
                # qualify a party with no profissão (deals 855/859/869/871/
                # 875) and with no RG órgão expedidor (871), and the
                # qualificação renders cleanly without either
                # (`frases.texto_pessoa` omits the profissão slot,
                # `frases.rg_texto` the "-ÓRGÃO" tail). A doubt, so an aviso.
                if chave in _CHAVES_QUALIFICACAO_AVISO:
                    codigo, texto = _CHAVES_QUALIFICACAO_AVISO[chave]
                    av.avisa(codigo, f"{_nome(p)} {texto}")
                    continue
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
            # Gate-backed here, not only through the checklist service's
            # `faltando_qualificacao` above (deduped by (campo, parte_id), so
            # never named twice): the qualificação and the certidão
            # pendências PRINT `p.nome`, and a blank would leave an empty
            # bold slot in the deed.
            if not (p.nome or "").strip():
                av.falta(
                    "qualificacao.nome_oficial",
                    f"{ROTULO_QUALIFICACAO['nome_oficial']}{SUFIXO_DOCUMENTO_DE_IDENTIDADE} — {_nome(p)}",
                    "partes",
                    p.parte_id,
                    ancora=_ancora(p),
                )
            if normalizar_genero(p.genero) is None:
                av.falta("qualificacao.genero", f"Gênero — {_nome(p)}", "partes", p.parte_id, ancora=_ancora(p))
            # An estado civil with no wording would silently drop out of the
            # qualificação (`frases.texto_pessoa` prints only the known ones).
            if p.estado_civil and p.estado_civil not in frases.ESTADOS_COM_REDACAO:
                av.bloqueia(
                    "ESTADO_CIVIL_SEM_REDACAO",
                    f"O estado civil de {_nome(p)} ('{p.estado_civil}') não tem redação no gerador.",
                )
            if p.estado_civil == "casado" and not e_representante:
                # The qualificação prints "casados no regime da <regime>": a
                # missing regime would leave the slot empty and an unknown one
                # would print its raw stored value — refuse both.
                if not p.regime_bens:
                    av.falta(
                        "qualificacao.regime_bens",
                        f"{ROTULO_QUALIFICACAO['regime_bens']} — {_nome(p)}",
                        "partes",
                        p.parte_id,
                        ancora=_ancora(p),
                    )
                elif p.regime_bens not in frases.REGIME_EXTENSO:
                    av.bloqueia(
                        "REGIME_BENS_SEM_REDACAO",
                        f"O regime de bens de {_nome(p)} ('{p.regime_bens}') não tem redação no gerador.",
                    )
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

            # [Migration 198] The flag says "lives in união estável" beside a
            # legal status that does not — never beside a marriage.
            if p.convive_uniao_estavel and p.estado_civil == "casado":
                av.bloqueia(
                    "CONVIVE_UNIAO_ESTAVEL_CASADO",
                    f"{_nome(p)} está como casado(a) e também como convivente em união estável: "
                    "desmarque um dos dois.",
                )
            elif p.convive_uniao_estavel and not p.conjuge_cliente_id and not e_representante:
                av.falta(
                    "qualificacao.conjuge",
                    f"Companheiro(a) vinculado(a) — {_nome(p)} convive em união estável",
                    "partes",
                    p.parte_id,
                    ancora=_ancora(p),
                )
            if frases.forma_nucleo(p) and p.conjuge_cliente_id and not e_representante:
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
                    _pacto_do_casal(av, p, conjuge, politica, casais)


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
    # [Corpus catalog §6, 34/34] The contract prints "Cartório de Registro de
    # Imóveis de <cidade>" — a reading with no city in it (a bare CNS, "… da
    # Capital") cannot be printed in that form and is named, never guessed.
    if im.numero_registro_imoveis and frases.cartorio_texto(im.numero_registro_imoveis) is None:
        av.falta(
            "imovel.numero_registro_imoveis",
            "Cartório de registro de imóveis com a cidade (ex.: \"1º Cartório de Registro de Imóveis de "
            f"Cotia\") — a cidade não foi encontrada em '{im.numero_registro_imoveis}'",
            "imovel",
        )

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
    # Migration 136 fallback, surfaced to the OPERATOR (not only a server
    # log): without a `descricao_imovel` block the IMÓVEL: clause quotes the
    # WHOLE selection (`contexto._descricao_matricula_rica`), which on a
    # resold property can name the PREVIOUS owners in the deed.
    if d.matricula.texto.strip() and d.matricula.descricao_imovel_texto is None:
        av.avisa(
            "MATRICULA_SEM_DESCRICAO_IMOVEL",
            "A leitura da matrícula não separou a descrição do imóvel: a cláusula IMÓVEL "
            "cita a seleção inteira dos atos. Confira no contrato se ela não inclui "
            "proprietários anteriores ou atos que não descrevem o imóvel.",
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
    elif im.situacao_onus == ONUS_USUFRUTO and not sw["tem_financiamento"]:
        # [Migration 193] Corpus deal 839 words the usufruto ONLY as the
        # precondition of the buyers' financing; without one there is no text.
        av.bloqueia(
            "ONUS_USUFRUTO_SEM_FINANCIAMENTO",
            "O imóvel tem usufruto, e a única redação dos contratos assinados condiciona a baixa do "
            "usufruto ao financiamento dos compradores — este negócio não tem parcela de financiamento.",
        )

    _certidoes_do_imovel(av, d, politica, assinatura)

    if im.situacao_onus in ONUS_COM_SALDO:
        termos = d.termos
        ja_quitado = termos.onus_quitacao == frases.QUITACAO_ONUS_JA_QUITADO
        fonte_valida = False
        if not im.onus_fonte_atos:
            av.falta("matricula.onus_fonte", "Atos da matrícula que registram o ônus", "matricula")
        elif any(a.kind not in ("R", "AV") or a.numero is None for a in im.onus_fonte_atos):
            av.bloqueia("ONUS_FONTE_INVALIDA", "O ônus aponta para um ato sem número (abertura).")
        else:
            fonte_valida = True
        # [§6.1 #11] Migration 115 stores the confirmed creditor on the imóvel,
        # read off the ônus acts — so it is fixed on the matrícula surface.
        # Deal 867's 'ja_quitado' paragraph names no creditor.
        if not im.onus_credor and not ja_quitado:
            av.falta("matricula.onus_credor", "Credor confirmado do financiamento que onera o imóvel", "matricula")
        if not termos.onus_quitacao:
            av.falta("negociacao.onus_quitacao", "Forma de quitação do saldo devedor", "negociacao")
        elif ja_quitado:
            # [Migration 193] Corpus deal 867: "protocolou, em <data>, junto ao
            # Registro de Imóveis de <cidade>, o requerimento de baixa da
            # Alienação Fiduciária registrada sob o R-<n>".
            protocolo = termos.onus_baixa_protocolo_em
            if protocolo is None:
                av.falta(
                    "negociacao.onus_baixa_protocolo_em",
                    "Data do protocolo do requerimento de baixa do ônus no Registro de Imóveis",
                    "negociacao",
                )
            elif protocolo > assinatura:
                av.bloqueia(
                    "ONUS_BAIXA_PROTOCOLO_POSTERIOR",
                    "O protocolo da baixa do ônus tem data posterior à assinatura.",
                )
            if fonte_valida and len(im.onus_fonte_atos) != 1:
                av.bloqueia(
                    "ONUS_JA_QUITADO_MAIS_DE_UM_ATO",
                    "A redação de ônus já quitado cita um único ato da matrícula (\"registrada sob o "
                    "R-…\"), mas o ônus aponta para vários.",
                )
        elif termos.onus_quitacao not in frases.QUITACOES_ONUS:
            av.bloqueia("ONUS_QUITACAO_INVALIDA", f"Forma de quitação desconhecida: {termos.onus_quitacao}.")
        elif termos.onus_quitacao == "compradores_prazo" and not termos.onus_prazo_dias:
            av.falta("negociacao.onus_prazo_dias", "Prazo (dias) para os compradores quitarem o saldo", "negociacao")
        elif termos.onus_quitacao == frases.QUITACAO_ONUS_VENDEDORES_BOLETO and not termos.onus_prazo_dias:
            av.falta(
                "negociacao.onus_prazo_dias",
                "Prazo (dias) para os vendedores quitarem o saldo por boleto",
                "negociacao",
            )
        elif termos.onus_quitacao == "parcela" and not any(p.tipo == "saldo" for p in d.parcelas):
            av.bloqueia("ONUS_QUITACAO_SEM_PARCELA_SALDO", "A quitação do ônus é por parcela, mas não há parcela de saldo.")


def _regra_de_tempo(av: Avaliacao, d: DadosContrato, codigo: str, mensagem: str) -> None:
    """A certidão TIME rule (emission age / validade) — party AND imóvel.

    [Owner directive, 2026-09-22 / 2026-09-25] `d.processo_legado` (migration
    151, set ONLY through `PUT .../processo-legado`, admin-only, never an
    automatic date heuristic) dispenses the AGE gates for a deal that started
    before the platform: a warning instead of a block, so the contract can
    still generate while the dispensation stays visible on the readiness
    report. A certidão emitted AFTER the signing date is a data
    contradiction, not an age rule — it goes through
    `_certidao_apos_assinatura`, never here."""
    if d.processo_legado:
        av.avisa(codigo, f"{mensagem} (processo anterior à plataforma)")
    else:
        av.bloqueia(codigo, mensagem)


def _certidao_apos_assinatura(av: Avaliacao, d: DadosContrato, codigo: str, mensagem: str) -> None:
    """A certidão emitted AFTER the signing date — party, estado civil AND imóvel.

    [Owner directive, 2026-10-05] Normally a data contradiction → a block.
    On a `processo_legado` deal (migration 151, admin-only flag) the office
    re-emitted the certidões after the original signing date when re-running
    an old, already-signed deal, so it is a warning (same code + message,
    visible on the readiness report) instead. Non-legacy deals keep the block."""
    if d.processo_legado:
        av.avisa(codigo, mensagem)
    else:
        av.bloqueia(codigo, mensagem)


#: [P5] Why a certidão has no emission date (`emissao_motivo`, migration 199
#: — `noctusai_lib.integrations.documents.matricula_certidao.MOTIVOS_EMISSAO`)
#: in the words the readiness list shows.
MOTIVO_EMISSAO_TEXTO: dict[str, str] = {
    MOTIVO_NAO_ENCONTRADA: "a data de emissão não foi encontrada no documento",
    MOTIVO_DIVERGENTE: "o documento traz datas de emissão divergentes",
    MOTIVO_ANTERIOR_AO_ULTIMO_ATO: "a data lida é anterior ao último ato da matrícula — não pode ser a emissão",
    MOTIVO_VISUALIZACAO: "o arquivo é uma visualização, sem valor de certidão",
}


def _rotulo_certidao_imovel(tipo: str) -> str:
    return "Certidão da matrícula" if tipo == "matricula" else frases.CERTIDOES_IMOVEL_ROTULO[tipo]


def _certidoes_imovel_pendentes(av: Avaliacao, d: DadosContrato) -> None:
    """[P5, migration 199] What `certidoes_imovel` CANNOT present, named
    instead of silently dropped (a visualização used to read as "nothing to
    check" — a false-ready):

    - a matrícula on file that is only a VISUALIZAÇÃO, with no certidão-typed
      matrícula beside it → `imovel.certidao.matricula` (upload the Certidão
      de Matrícula; the certidão wins when both exist);
    - a certidão with no emission date → `imovel.certidao.<tipo>.emitida_em`,
      saying why (`emissao_motivo`) and pointing at the field where it is
      typed by hand.

    PRESENCE and TYPE — `processo_legado` waives only the AGE rule
    (`_regra_de_tempo`), never these."""
    im = d.imovel
    if im is None:
        return
    matriculas = [c for c in im.certidoes if c.tipo == "matricula"]
    certidoes_matricula = [c for c in matriculas if not _e_visualizacao(c)]
    if matriculas and not certidoes_matricula:
        av.falta(
            "imovel.certidao.matricula",
            "Envie a Certidão de Matrícula — o arquivo enviado é uma visualização, sem valor de certidão",
            "imovel",
            alvo=ALVO_DOCUMENTOS_DO_IMOVEL,
        )
    matricula_datada = any(c.emitida_em for c in certidoes_matricula)
    for c in im.certidoes:
        if c.emitida_em is not None or _e_visualizacao(c):
            continue
        if c.tipo == "matricula" and matricula_datada:
            continue  # another matrícula certidão on file answers it
        motivo = MOTIVO_EMISSAO_TEXTO.get(c.emissao_motivo or "", "a data de emissão não foi lida")
        av.falta(
            f"imovel.certidao.{c.tipo}.emitida_em",
            f"Data de emissão da {_rotulo_certidao_imovel(c.tipo).replace('Certidão', 'certidão', 1)} "
            f"do imóvel — {motivo}; informe-a na página do imóvel (Certidões do imóvel)",
            "imovel",
            alvo=alvo_emissao_certidao_imovel(c.tipo),
        )


def _certidoes_do_imovel(
    av: Avaliacao, d: DadosContrato, politica: Politica, assinatura: date
) -> None:
    """[§6.1 #14 / Q10] The imóvel's own certidões (migration 118) answer to
    the SAME 30-day rule as a party's — an old IPTU CND is as stale on the
    signing table as an old federal one — and to the SAME `processo_legado`
    dispensation of that rule (`_regra_de_tempo`). What cannot be presented
    at all (a visualização, an undated certidão) is named first."""
    _certidoes_imovel_pendentes(av, d)
    for c in certidoes_imovel(d):
        rotulo = (
            "Certidão da matrícula"
            if c.tipo == "matricula"
            else frases.CERTIDOES_IMOVEL_ROTULO[c.tipo]
        )
        if c.emitida_em is None:  # pragma: no cover — `certidoes_imovel` filters these out
            continue
        if c.emitida_em > assinatura:
            _certidao_apos_assinatura(
                av,
                d,
                "CERTIDAO_IMOVEL_EMITIDA_APOS_ASSINATURA",
                f"{rotulo} do imóvel tem emissão posterior à assinatura.",
            )
        elif (assinatura - c.emitida_em).days >= politica.certidao_max_dias:
            _regra_de_tempo(
                av,
                d,
                "CERTIDAO_IMOVEL_EMISSAO_ANTIGA",
                f"{rotulo} do imóvel foi emitida há {(assinatura - c.emitida_em).days} dias; "
                f"precisa ter menos de {politica.certidao_max_dias} dias na data da assinatura.",
            )
        if c.validade_ate is not None and c.validade_ate < assinatura:
            _regra_de_tempo(
                av, d, "CERTIDAO_IMOVEL_VENCIDA", f"{rotulo} do imóvel está vencida na data da assinatura."
            )
        # [2026-10-03 bug fix] The printed line carries the certidão's OWN
        # resultado (`frases.CERTIDOES_IMOVEL_MODELO`) — it used to print
        # "Negativa" whatever it said. Missing/unknown is refused, never
        # printed as a guess. (The matrícula certidão has no resultado.)
        if c.tipo != "matricula":
            if not c.resultado:
                av.falta(
                    f"imovel.certidao.{c.tipo}.resultado",
                    f"Resultado da {rotulo.replace('Certidão Negativa', 'certidão')} do imóvel "
                    "(negativa, positiva ou positiva com efeito de negativa)",
                    "imovel",
                )
            elif c.resultado not in frases.RESULTADO_ROTULO:
                av.bloqueia(
                    "CERTIDAO_IMOVEL_RESULTADO_DESCONHECIDO",
                    f"{rotulo} do imóvel tem um resultado desconhecido ('{c.resultado}').",
                )
        if c.resultado in frases.RESULTADOS_COM_APONTAMENTO:
            av.avisa(
                "CERTIDAO_IMOVEL_COM_APONTAMENTO",
                f"{rotulo} do imóvel não é negativa; exige esclarecimentos.",
            )


def _negociacao(
    av: Avaliacao,
    d: DadosContrato,
    sw: dict[str, bool],
    assinatura: date,
    *,
    agrupar_parcelas: bool = False,
) -> None:
    """`agrupar_parcelas` — the caller prints parcelas through
    `grupos_de_parcelas` (the contract itself, `avaliar`): several sinais
    become one tranche line and an fgts parcela joins the financing line,
    so both are accepted. A caller that prints one line per stored parcela
    (the aditivo's restated schedule, `contrato_aditivo.avaliacao`) keeps the
    default `False` and with it the refusal of what it cannot print
    (`MAIS_DE_UM_SINAL`, an fgts parcela with no moment)."""
    if d.valor_negociado is None:
        av.falta("negociacao.valor_negociado", "Valor negociado", "negociacao")
    parcelas = parcelas_ordenadas(d)
    if not parcelas:
        av.falta("negociacao.parcelas", "Parcelas do preço", "negociacao")
    else:
        sinais = [p for p in parcelas if p.tipo == "sinal"]
        if not sinais:
            av.falta("negociacao.parcela_sinal", "Parcela de sinal", "negociacao")
        elif len(sinais) > 1 and agrupar_parcelas:
            _sinal_em_parcelas(av, d, sinais)
        elif len(sinais) > 1:
            av.bloqueia("MAIS_DE_UM_SINAL", "O contrato admite exatamente uma parcela de sinal.")

    favorecidos = {f.id: f for f in d.favorecidos}
    cpfs_vendedores = {frases.so_digitos(p.cpf) for p in signatarios(d.vendedores) if p.cpf}
    cpfs_vendedores |= {
        frases.so_digitos(pj.cnpj) for pj in partes_pj_contratantes(d) if pj.lado == "vendedor" and pj.cnpj
    }
    numeros = (
        numeros_impressos(d)
        if agrupar_parcelas
        else {p.id: num2(i) for i, p in enumerate(parcelas, start=1)}
    )
    sem_momento_proprio = ("permuta", "fgts") if agrupar_parcelas else ("permuta",)
    ultimo_venc: Optional[date] = None
    for p in parcelas:
        rot = f"Parcela {numeros[p.id]}"
        if p.valor is None or p.valor <= 0:
            av.falta(f"negociacao.parcela.{p.id}.valor", f"Valor da {rot}", "negociacao")
        if not p.vencimento and not (p.evento or "").strip() and p.tipo not in sem_momento_proprio:
            # A permuta parcela is settled by the deed, not on a date: its
            # wording carries the imóveis, never a vencimento/evento. An fgts
            # parcela prints inside the financing parcela, on ITS moment
            # (`grupos_de_parcelas`; any other fgts shape is refused).
            av.falta(f"negociacao.parcela.{p.id}.momento", f"Vencimento ou evento da {rot}", "negociacao")
        if p.divisao:
            _divisao(av, p, rot, favorecidos, cpfs_vendedores)
        if p.tipo in TIPOS_PAGOS_A_FAVORECIDO:
            # A divided parcela's payees are its shares (`_divisao` above).
            if p.divisao:
                pass
            elif not p.favorecido_id and p.tipo == "sinal":
                # The sinal's wording settles it INTO an account ("quitação
                # … com o efetivo crédito na conta corrente ora indicada") —
                # every signed sinal names one, so it stays required.
                av.falta(f"negociacao.parcela.{p.id}.favorecido", f"Favorecido da {rot}", "negociacao")
            elif not p.favorecido_id:
                # [P5 F8] An intermediária/direta/saldo with no account: the
                # signed corpus has them (884's intermediária "com prazo
                # máximo …", 783's consórcio) — the line prints its value,
                # moment and forma, no "em favor de". A doubt, so an aviso.
                av.avisa(
                    "PARCELA_SEM_FAVORECIDO",
                    f"A {rot} não tem favorecido; sai sem a conta de pagamento.",
                )
            else:
                fav = favorecidos.get(p.favorecido_id)
                if fav is None:
                    av.bloqueia("FAVORECIDO_INEXISTENTE", f"O favorecido da {rot} não existe mais.")
                else:
                    _checar_favorecido(av, fav, rot, cpfs_vendedores)
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

    _posse(
        av, d, d.termos.posse_marco, d.termos.posse_prazo_dias, d.termos.posse_marco_parcela_id,
        escopo="posse", data=d.termos.posse_data,
    )

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


def _checar_favorecido(av: Avaliacao, fav, rot: str, cpfs_vendedores: set[str]) -> None:
    """The account a favorecido is paid into must be printable (spec §5.1),
    whether it receives a whole parcela or one share of it (192)."""
    if not fav.conta and not fav.pix:
        av.falta(f"negociacao.favorecido.{fav.id}.conta", f"Conta ou chave PIX de {fav.nome}", "negociacao")
    if fav.conta and not (fav.banco and fav.agencia):
        av.falta(f"negociacao.favorecido.{fav.id}.banco", f"Banco e agência de {fav.nome}", "negociacao")
    if frases.so_digitos(fav.cpf_cnpj) not in cpfs_vendedores:
        av.avisa("FAVORECIDO_TERCEIRO", f"{fav.nome} ({rot}) não é um dos vendedores.")


def _divisao(
    av: Avaliacao, p: Parcela, rot: str, favorecidos: dict, cpfs_vendedores: set[str]
) -> None:
    """[Migration 192] One parcela paid to several favorecidos (6 signed
    deals). Every share names an existing favorecido with a printable
    account and ONE amount kind; the shares must add up to the parcela
    EXACTLY — a mismatch is the deal's own data disagreeing with itself
    (same footing as `SOMA_PARCELAS_DIFERENTE_DO_PRECO`)."""
    if p.tipo not in TIPOS_PAGOS_A_FAVORECIDO:
        av.bloqueia(
            "DIVISAO_EM_PARCELA_SEM_FAVORECIDO",
            f"A {rot} não é paga em conta (tipo {p.tipo}) e não pode ser dividida entre favorecidos.",
        )
        return
    if p.favorecido_id:
        av.bloqueia(
            "FAVORECIDO_E_DIVISAO",
            f"A {rot} tem um favorecido único E uma divisão entre favorecidos — deixe só um dos dois.",
        )
    if len(p.divisao) < 2:
        av.bloqueia(
            "DIVISAO_COM_UM_FAVORECIDO",
            f"A divisão da {rot} tem um só favorecido — use o favorecido da parcela.",
        )
    vistos: set[str] = set()
    for n, q in enumerate(p.divisao, start=1):
        alvo = f"negociacao.parcela.{p.id}.divisao.{n}"
        if not q.favorecido_id:
            av.falta(f"{alvo}.favorecido", f"Favorecido {n} da divisão da {rot}", "negociacao")
        elif q.favorecido_id in vistos:
            av.bloqueia("DIVISAO_FAVORECIDO_REPETIDO", f"Um favorecido aparece duas vezes na divisão da {rot}.")
        else:
            vistos.add(q.favorecido_id)
            fav = favorecidos.get(q.favorecido_id)
            if fav is None:
                av.bloqueia("FAVORECIDO_INEXISTENTE", f"Um favorecido da divisão da {rot} não existe mais.")
            else:
                _checar_favorecido(av, fav, rot, cpfs_vendedores)
        if q.valor is not None and q.percentual is not None:
            av.bloqueia("DIVISAO_VALOR_E_PERCENTUAL", f"A parte {n} da {rot} tem valor e percentual — deixe só um.")
        elif q.valor is None and q.percentual is None:
            av.falta(f"{alvo}.valor", f"Valor ou percentual da parte {n} da {rot}", "negociacao")
    com_valor = [q for q in p.divisao if q.valor is not None]
    com_pct = [q for q in p.divisao if q.percentual is not None]
    if com_valor and com_pct:
        av.bloqueia("DIVISAO_MISTA", f"A divisão da {rot} mistura valores e percentuais — use só um dos dois.")
        return
    if p.valor is None:
        return
    if com_valor and len(com_valor) == len(p.divisao):
        soma = sum((q.valor for q in com_valor), Decimal("0"))  # type: ignore[misc]
        if soma != p.valor:
            av.bloqueia(
                "DIVISAO_SOMA_DIVERGE",
                f"As partes da {rot} somam {formatar_brl(soma)}, mas a parcela é {formatar_brl(p.valor)}.",
            )
    elif com_pct and len(com_pct) == len(p.divisao):
        soma_pct = sum((q.percentual for q in com_pct), Decimal("0"))  # type: ignore[misc]
        if soma_pct != Decimal("100"):
            av.bloqueia(
                "DIVISAO_PERCENTUAL_DIVERGE",
                f"Os percentuais da divisão da {rot} somam {frases.pct_simples(soma_pct)}, não 100%.",
            )
        else:
            soma = sum((v for v in valores_da_divisao(p) if v is not None), Decimal("0"))
            if soma != p.valor:
                # Refusing beats absorbing the stray cent into some share.
                av.bloqueia(
                    "DIVISAO_PERCENTUAL_INEXATO",
                    f"Os percentuais da {rot} não dividem {formatar_brl(p.valor)} em centavos exatos "
                    "— informe o valor de cada parte.",
                )


def _sinal_em_parcelas(av: Avaliacao, d: DadosContrato, sinais: list[Parcela]) -> None:
    """More than one sinal parcela prints as ONE "Sinal e princípio de
    pagamento" line paid in tranches (`grupos_de_parcelas`, signed contract
    783's shape), and the multa rescisória is their sum [Q3]. That shape
    only exists when the tranches are consecutive and the line cannot
    mis-state what any of them triggers."""
    grupo = next((g for g in grupos_de_parcelas(d) if g[0].tipo == "sinal"), [])
    if len(grupo) != len(sinais):
        av.bloqueia(
            "SINAIS_NAO_CONSECUTIVOS",
            "As parcelas de sinal precisam ser consecutivas no preço — elas são impressas como "
            "uma só parcela de sinal paga em partes.",
        )
        return
    if any(p.divisao for p in grupo):
        # No signed contract splits a tranche of the sinal among payees;
        # the tranche wording carries ONE account per tranche.
        av.bloqueia(
            "SINAL_EM_PARCELAS_COM_DIVISAO",
            "Uma parte do sinal está dividida entre favorecidos — o contrato não tem redação para "
            "sinal em partes com divisão; use um favorecido por parte.",
        )
    disparos = [p.dispara_corretagem for p in grupo]
    if any(disparos) and not all(disparos):
        # "por ocasião do recebimento da Parcela 01" means the WHOLE sinal;
        # flagging only some tranches would print a later marco than agreed.
        av.bloqueia(
            "CORRETAGEM_SINAL_PARCIAL",
            "O disparo da corretagem está marcado só em algumas partes do sinal — o contrato cita a "
            "parcela de sinal inteira; marque todas as partes ou nenhuma.",
        )


def _posse(
    av: Avaliacao,
    d: DadosContrato,
    marco: Optional[str],
    prazo: Optional[int],
    marco_parcela_id: Optional[str],
    *,
    escopo: str,
    data: Optional[date] = None,
) -> None:
    """[§6.1 #12] One rule for both posse clauses (the imóvel's and, in a
    permuta, the exchanged imóvel's) — they are the same clause pointed at
    different properties, so a second copy would be a second thing to drift.

    🔴 `prazo == 0` is ANSWERED: "concomitante" with the marco (signed
    corpus 876 / 863) — only `None` is missing. A `data_fixa` marco (imóvel
    only; corpus 859) needs its DATE and no prazo."""
    rotulo = "da posse" if escopo == "posse" else "da posse do imóvel da permuta"
    marcos = frases.MARCOS_POSSE if escopo == "posse" else frases.MARCOS_POSSE_PERMUTA
    alvo = ALVO_POSSE if escopo == "posse" else ALVO_PERMUTA_POSSE
    if marco == "data_fixa":
        if data is None:
            av.falta("negociacao.posse_data", "Data fixa da entrega da posse", "negociacao", alvo=alvo)
    elif prazo is None:
        av.falta(
            f"negociacao.{escopo}_prazo_dias",
            f"Prazo de entrega {rotulo} (dias; 0 = concomitante ao marco)",
            "negociacao",
            alvo=alvo,
        )
    if not marco:
        av.falta(f"negociacao.{escopo}_marco", f"Marco inicial do prazo {rotulo}", "negociacao", alvo=alvo)
    elif marco not in marcos:
        av.bloqueia("POSSE_MARCO_INVALIDO", f"Marco {rotulo} desconhecido: {marco}.")
    elif marco == "parcela" and numero_da_parcela(d, marco_parcela_id) is None:
        # 114's CHECK guarantees the id is SET when the marco is 'parcela'; it
        # cannot guarantee the parcela still belongs to this deal's schedule.
        av.bloqueia(
            "POSSE_MARCO_PARCELA_DESCONHECIDA",
            f"O marco {rotulo} aponta para uma parcela que não está no preço deste contrato.",
        )
    elif marco == "parcela":
        # A sinal paid in tranches prints as ONE parcela, so "do recebimento
        # da parcela 01" means its LAST tranche — a marco on an earlier one
        # would print a later posse than agreed.
        grupo = next(g for g in grupos_de_parcelas(d) if any(p.id == marco_parcela_id for p in g))
        if grupo[0].tipo == "sinal" and len(grupo) > 1 and grupo[-1].id != marco_parcela_id:
            av.bloqueia(
                "POSSE_MARCO_PARTE_DO_SINAL",
                f"O marco {rotulo} aponta para uma parte do sinal que não é a última — o contrato "
                "cita a parcela de sinal inteira; aponte para a última parte.",
            )


def _financiamento(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    if sw["tem_financiamento"]:
        situacao = d.financiamento.situacao
        if not d.financiamento.existe:
            av.falta("financiamento", "Registro do financiamento do atendimento", "financiamento")
        elif not situacao:
            # Never read as "pendente" by default — unknown is a named gap.
            av.falta(
                "financiamento.situacao",
                "Situação do financiamento (pendente, aprovado ou recusado)",
                "financiamento",
            )
        elif situacao == "recusado":
            av.bloqueia("FINANCIAMENTO_RECUSADO", "O financiamento deste atendimento está recusado.")
        elif situacao not in SITUACOES_FINANCIAMENTO:
            av.bloqueia(
                "FINANCIAMENTO_SITUACAO_DESCONHECIDA",
                f"Situação do financiamento desconhecida: {situacao}.",
            )
        elif situacao != "aprovado":
            av.avisa(
                "FINANCIAMENTO_NAO_APROVADO",
                f"O financiamento deste atendimento ainda não está aprovado (situação: {situacao}); "
                "o contrato prevê uma parcela paga por financiamento.",
            )
    # [Q6, revised by the signed contracts] FGTS is printed INSIDE the
    # financiamento parcela — with the split amounts when known. It may be
    # stored either way: as `valor_fgts` on the financing parcela (192), or
    # as its own `fgts` parcela, which then joins the financing parcela's
    # line (`grupos_de_parcelas`). Any shape where that join is a guess is
    # refused.
    parcelas = parcelas_ordenadas(d)
    numeros = numeros_impressos(d)
    fins = [p for p in parcelas if p.tipo == "financiamento"]
    fgts = [p for p in parcelas if p.tipo == "fgts"]
    if len(fgts) > 1:
        av.bloqueia(
            "MAIS_DE_UMA_PARCELA_FGTS",
            "Há mais de uma parcela de FGTS: o FGTS entra na parcela de financiamento — junte-as "
            "numa só (ou informe o valor de FGTS na parcela de financiamento).",
        )
    elif fgts and len(fins) != 1:
        av.bloqueia(
            "PARCELA_FGTS_SEM_FINANCIAMENTO",
            f"A Parcela {numeros[fgts[0].id]} é de FGTS, mas o contrato "
            + ("não tem parcela de financiamento" if not fins else "tem mais de uma parcela de financiamento")
            + ": o FGTS é impresso dentro de UMA parcela de financiamento.",
        )
    elif fgts:
        fin, pf = fins[0], fgts[0]
        if fin.valor_fgts is not None:
            av.bloqueia(
                "FGTS_EM_DUPLICIDADE",
                f"O FGTS está informado duas vezes: como parcela própria e como valor de FGTS da "
                f"Parcela {numeros[fin.id]} (financiamento) — deixe só um.",
            )
        evento_fgts = (pf.evento or "").strip()
        if (pf.vencimento and pf.vencimento != fin.vencimento) or (
            evento_fgts and evento_fgts != (fin.evento or "").strip()
        ):
            av.bloqueia(
                "PARCELA_FGTS_MOMENTO_DIVERGENTE",
                "A parcela de FGTS tem vencimento/evento diferente da parcela de financiamento — o "
                "contrato imprime o FGTS dentro dela, no mesmo prazo; apague o da parcela de FGTS.",
            )
    for p in parcelas:
        if p.valor_fgts is None:
            continue
        if p.tipo != "financiamento":
            av.bloqueia(
                "VALOR_FGTS_FORA_DO_FINANCIAMENTO",
                f"A Parcela {numeros[p.id]} tem valor de FGTS, mas não é de financiamento.",
            )
        elif p.valor is not None and p.valor_fgts >= p.valor:
            av.bloqueia(
                "FGTS_MAIOR_QUE_PARCELA",
                f"O valor de FGTS da Parcela {numeros[p.id]} não é menor que a parcela — o restante "
                "é o valor financiado.",
            )
    usa_fgts_nas_parcelas = bool(fgts) or any(p.valor_fgts is not None for p in parcelas)
    if usa_fgts_nas_parcelas and not d.financiamento.fgts:
        av.bloqueia(
            "FGTS_NAO_MARCADO_NO_FINANCIAMENTO",
            "As parcelas usam FGTS, mas o financiamento não marca uso de FGTS — marque-o no "
            "financiamento (os documentos de FGTS dependem disso).",
        )
    if d.financiamento.fgts and not sw["tem_financiamento"]:
        av.avisa(
            "FGTS_SEM_PARCELA",
            "O financiamento marca uso de FGTS, mas não há parcela de financiamento; o FGTS não aparece no contrato.",
        )


def _permuta(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    if not sw["tem_permuta"]:
        return
    # Several permuta parcelas are allowed: each prints its OWN imóveis
    # (`contexto._texto_parcela_permuta`), so every link must resolve and
    # every loaded imóvel must belong to exactly one parcela.
    numeros = numeros_impressos(d)
    carregados = {i.permuta_ativo_id for i in d.permuta_imoveis}
    vinculados: set[str] = set()
    permutas = parcelas_permuta(d)
    for parcela in permutas:
        if not parcela.permuta_ativo_ids:
            # One permuta parcela keeps its historical field name.
            av.falta(
                "negociacao.permuta_imoveis"
                if len(permutas) == 1
                else f"negociacao.parcela.{parcela.id}.permuta_imoveis",
                f"Imóvel(is) de permuta vinculado(s) à Parcela {numeros[parcela.id]} (permuta)",
                "negociacao",
            )
        for ativo_id in parcela.permuta_ativo_ids:
            if ativo_id in vinculados:
                av.bloqueia(
                    "PERMUTA_IMOVEL_EM_DUAS_PARCELAS",
                    "Um imóvel de permuta está vinculado a mais de uma parcela.",
                )
            vinculados.add(ativo_id)
            if ativo_id not in carregados:
                av.bloqueia(
                    "PERMUTA_IMOVEL_NAO_CARREGADO",
                    f"Um imóvel de permuta da Parcela {numeros[parcela.id]} não foi encontrado.",
                )
    if carregados - vinculados:
        av.bloqueia(
            "PERMUTA_IMOVEL_SEM_PARCELA",
            "Há imóvel de permuta que não está vinculado a nenhuma parcela de permuta.",
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
        if (imovel.descricao_matricula or "").strip() and imovel.descricao_imovel_texto is None:
            # Same migration-136 fallback as the main imóvel's (`_imovel`),
            # surfaced to the operator — `contexto._descricao_matricula_permuta`.
            av.avisa(
                "MATRICULA_PERMUTA_SEM_DESCRICAO_IMOVEL",
                "A leitura da matrícula do imóvel dado em permuta não separou a descrição "
                "do imóvel: a parcela de permuta cita a seleção inteira dos atos. Confira no "
                "contrato se ela não inclui proprietários anteriores ou atos que não descrevem "
                "o imóvel.",
            )
        for campo, rotulo in (
            ("inscricao_municipal", "Inscrição municipal do imóvel da permuta"),
            ("matricula_numero", "Número da matrícula do imóvel da permuta"),
            ("cartorio", "Cartório de registro do imóvel da permuta"),
        ):
            if not getattr(imovel, campo):
                av.falta(f"{alvo}.{campo}", rotulo, "imovel")
        if imovel.cartorio and frases.cartorio_texto(imovel.cartorio) is None:
            av.falta(
                f"{alvo}.cartorio",
                "Cartório de registro do imóvel da permuta com a cidade — a cidade não foi encontrada "
                f"em '{imovel.cartorio}'",
                "imovel",
            )
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
    signatarios_certificados = signatarios_certificandos(d, sw, politica)
    for p in d.vendedores:
        if companheiro_dispensado(d, p, politica):
            av.avisa(
                "COMPANHEIRO_SEM_CERTIDOES",
                f"{_nome(p)} assina como companheiro(a) de um vendedor (não casados): não apresenta "
                "certidões.",
            )
    com_apontamento: list[str] = []

    def tempo(codigo: str, mensagem: str) -> None:
        """The certidão TIME rules (emission age / validade) only —
        `CERTIDAO_EMITIDA_APOS_ASSINATURA` is a data error, not an age
        rule, and is NOT routed through here; it has its own legacy
        dispensation, `_certidao_apos_assinatura` (2026-10-05).

        [Owner directive, 2026-09-22] `d.processo_legado` (migration 151,
        set ONLY through `PUT .../processo-legado`, admin-only, never an
        automatic date heuristic) dispenses these for a deal that started
        before the platform: a warning instead of a block, so the
        contract can still generate while the dispensation stays visible
        on the readiness report.
        """
        _regra_de_tempo(av, d, codigo, mensagem)

    def confirmar_pcen(parte_id: Optional[str], c: Certidao, rotulo: str, nome_grupo: str) -> None:
        """[Owner 2026-10-01, Option A + amendment] The Receita PCEN 2ª via is
        judged by its printed validity, but the operator must KNOW the
        difference: an acknowledgment gate (`confirmacoes`), never a silent
        pass. The aviso stays on the record once acknowledged."""
        ciente = certidao_pcen.ciente_vale(
            ciente_em=c.pcen_ciente_em, ciente_validade=c.pcen_ciente_validade,
            validade_ate=c.validade_ate,
        )
        mensagem = certidao_pcen.aviso(c.emitida_em, c.validade_ate)
        av.avisa(certidao_pcen.CODIGO_CONFIRMACAO, f"{mensagem} — {nome_grupo}")
        av.confirmacoes.append({
            "codigo": certidao_pcen.CODIGO_CONFIRMACAO,
            "titulo": certidao_pcen.TITULO,
            "rotulo": f"{rotulo} — {nome_grupo}",
            "mensagem": mensagem,
            "explicacao": certidao_pcen.explicacao(c.emitida_em, c.validade_ate),
            "parte_id": parte_id,
            "resultado_id": c.resultado_id,
            "emitida_em": c.emitida_em.isoformat() if c.emitida_em else None,
            "validade_ate": c.validade_ate.isoformat(),
            "ciente": ciente,
            "ciente_em": c.pcen_ciente_em if ciente else None,
            "ciente_por": c.pcen_ciente_por if ciente else None,
            "acoes": {"entendi": certidao_pcen.ACAO_ENTENDI, "duvida": certidao_pcen.ACAO_DUVIDA},
            "destino": av.destinos.para("certidoes", parte_id=parte_id),
        })

    def conferir(
        parte_id: Optional[str], certs: list[Certidao], tipo_documento: str, nome_grupo: str,
        *, antigo: bool = False,
    ) -> None:
        # A previous owner's missing certidão is fixed in the Certidões tab's
        # antigos group (owner 2026-10-05), not on the generic screen.
        onde = "antigos_proprietarios" if antigo else "certidoes"
        alvo = ALVO_ANTIGOS_PROPRIETARIOS if antigo else None
        # A result whose consulta kind (CPF/CNPJ) is unknown cannot be placed
        # in either group — named, never silently read as one of them.
        for c in certs:
            if c.consulta_tipo_documento is None:
                av.falta(
                    f"certidao.{c.tipo}.consulta_tipo_documento",
                    f"Tipo de consulta (CPF ou CNPJ) da certidão {_rotulo_certidao_seguro(c.tipo)} "
                    f"— {nome_grupo}",
                    onde,
                    parte_id,
                    alvo=alvo,
                )
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
                av.falta(f"certidao.{tipo}", f"{rotulo} — {nome_grupo}", onde, parte_id, alvo=alvo)
                continue
            if c.resultado == "nao_emitida":
                continue
            if c.resultado not in frases.RESULTADO_ROTULO:
                # The label is built FROM the resultado ("Certidão Negativa
                # de…"); an unknown one would print an empty slot.
                av.bloqueia(
                    "CERTIDAO_RESULTADO_DESCONHECIDO",
                    f"{rotulo} de {nome_grupo} tem um resultado desconhecido ('{c.resultado}').",
                )
                continue
            if not c.numero:
                av.falta(f"certidao.{tipo}.numero", f"Número da {rotulo} — {nome_grupo}", onde, parte_id, alvo=alvo)
            if not c.emitida_em:
                av.falta(f"certidao.{tipo}.emitida_em", f"Data de emissão da {rotulo} — {nome_grupo}", onde, parte_id, alvo=alvo)
                continue
            excecao_pcen = certidao_pcen.excecao_aplica(
                resultado=c.resultado, segunda_via=c.segunda_via, validade_ate=c.validade_ate
            )
            if c.emitida_em > assinatura:
                _certidao_apos_assinatura(
                    av, d, "CERTIDAO_EMITIDA_APOS_ASSINATURA",
                    f"{rotulo} de {nome_grupo} tem emissão posterior à assinatura.",
                )
            elif not excecao_pcen and (assinatura - c.emitida_em).days >= politica.certidao_max_dias:
                # [Q10] every certidão is emitted less than 30 days before signing.
                # (The Receita PCEN 2ª via is judged by its printed validity below.)
                tempo(
                    "CERTIDAO_EMISSAO_ANTIGA",
                    f"{rotulo} de {nome_grupo} foi emitida há {(assinatura - c.emitida_em).days} dias; "
                    f"precisa ter menos de {politica.certidao_max_dias} dias na data da assinatura.",
                )
            if c.validade_ate is not None and c.validade_ate < assinatura:
                tempo("CERTIDAO_VENCIDA", f"{rotulo} de {nome_grupo} está vencida na data da assinatura.")
            elif excecao_pcen and c.emitida_em <= assinatura:
                confirmar_pcen(parte_id, c, rotulo, nome_grupo)
            # A genuine positiva needs the esclarecimentos paragraph.
            # [Owner directive, 2026-09-25] `negativa_com_homonimos` no
            # longer does — reversed §6.1 #15's original read; see
            # `frases.RESULTADOS_COM_APONTAMENTO`'s docstring, the ONE
            # classifier this and `_certidoes_do_imovel` both defer to.
            if c.resultado in frases.RESULTADOS_COM_APONTAMENTO:
                com_apontamento.append(f"{rotulo} ({nome_grupo})")

    def conferir_pessoa(p: Pessoa, *, antigo: bool = False) -> None:
        # Migration 116 reaches EVERY party's certidões, the titular included,
        # so an empty list is "none issued yet" and each tipo is named below —
        # it is no longer an unreachable-data refusal.
        conferir(p.parte_id, p.certidoes, "cpf", _nome(p), antigo=antigo)

    def conferir_empresas() -> None:
        """[E1] Every empresa a certificando holds a participação in — the
        NULL-situação gap (no Cartão CNPJ uploaded yet) is a named
        `faltando`, never a silent skip (E1, H4); required companies get
        the same 11-item CNPJ certidão check as a person (E5)."""
        partes_pj = empresas_impressas_como_parte(d, assinatura, politica)
        for e, dono in _empresas_de_certificandos(d, sw, politica, assinatura):
            if e.id in partes_pj:
                continue  # the company IS a party: its own group below (`conferir_pj`)
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
                conferir(
                    dono.parte_id, e.certidoes, "cnpj", nome_pj,
                    antigo=dono.papel == PAPEL_ANTIGO_PROPRIETARIO,
                )

    def conferir_pj() -> None:
        """[Migration 193] A PJ party presents its OWN 11 CNPJ certidões."""
        for pj in pj_certificandas(d, sw):
            conferir(pj.parte_id, pj.certidoes, "cnpj", pj.razao_social or pj.cnpj or "empresa")

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

    def conferir_crednet() -> None:
        """[P5 F7] A certificando with no READ Serasa Crednet had their
        companies never looked for — `d.empresas` (the only source of the
        company certidão groups) comes from it. An aviso naming that, never
        a silent "no companies, nothing to demand"; never a block either
        (owner: the office decides whether to chase it). Stronger wording
        when the person's own data says sócio/administrador."""
        if d.clientes_com_crednet is None:
            return
        verificados = set(d.clientes_com_crednet)
        vistos: set[str] = set()
        for p in signatarios_certificados:
            if p.cliente_id in verificados or p.cliente_id in vistos:
                continue
            vistos.add(p.cliente_id)
            indicio = (
                " — a profissão indica sócio(a)/administrador(a)"
                if _PROFISSAO_SOCIO_RE.search(p.profissao or "")
                else ""
            )
            av.avisa(
                "EMPRESAS_NAO_VERIFICADAS",
                f"Empresas de {_nome(p)} não verificadas — sem Serasa Crednet lido{indicio}: o "
                "contrato não pede certidões de empresas dele(a).",
            )

    conferir_empresas()
    conferir_crednet()
    conferir_pj()
    conferir_conjuges_ausentes()
    for p in signatarios_certificados:
        conferir_pessoa(p)
        # [Q11] the estado-civil certidão is less than `politica.certidao_estado_civil_max_dias` (30) days old.
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
            _certidao_apos_assinatura(
                av,
                d,
                "CERTIDAO_EMITIDA_APOS_ASSINATURA",
                f"A certidão de estado civil de {_nome(p)} tem emissão posterior à assinatura.",
            )
        elif (assinatura - emitida).days >= politica.certidao_estado_civil_max_dias:
            tempo(
                "CERTIDAO_ESTADO_CIVIL_ANTIGA",
                f"A certidão de estado civil de {_nome(p)} foi emitida há {(assinatura - emitida).days} dias; "
                f"precisa ter menos de {politica.certidao_estado_civil_max_dias} dias na data da assinatura.",
            )

    # [Q9] previous owner(s) when the last transfer of ownership is recent —
    # people AND companies (P5: the seller in the last transfer of 858/869
    # was a construtora).
    antigos = antigos_proprietarios(d)
    antigos_pj = antigos_proprietarios_pj(d)
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
        elif exige and d.antigos_dispensados:
            # [Owner 2026-10-05] An operator dispensed the previous owners for
            # THIS deal (migration 203): visible, never a silent skip.
            av.avisa(
                "ANTIGO_PROPRIETARIO_DISPENSADO_NO_NEGOCIO",
                "Antigos proprietários não exigidos neste negócio (dispensa registrada por um "
                "administrador): a última transferência foi registrada há menos de "
                f"{politica.antigo_proprietario_janela_anos} anos, mas as certidões deles não entram "
                "no contrato.",
            )
        elif exige:
            if not antigos and not antigos_pj:
                nomes = ", ".join(d.imovel.ultima_transferencia_transmitentes)
                quem = f" — consta(m) na matrícula: {nomes}" if nomes else ""
                av.falta(
                    "partes.antigo_proprietario",
                    "Antigo(s) proprietário(s) do imóvel no card (pessoa ou empresa, papel 'Antigo "
                    "proprietário') — a última transferência de "
                    f"propriedade foi registrada há menos de {politica.antigo_proprietario_janela_anos} anos{quem}"
                    " (ou dispense-os neste negócio)",
                    "antigos_proprietarios",
                    alvo=ALVO_ANTIGOS_PROPRIETARIOS,
                )
            for a in antigos:
                if not a.nome:
                    av.falta("qualificacao.nome_oficial", f"Nome oficial — {_nome(a)} (antigo proprietário)", "antigos_proprietarios", a.parte_id, alvo=ALVO_ANTIGOS_PROPRIETARIOS)
                if normalizar_genero(a.genero) is None:
                    av.falta("qualificacao.genero", f"Gênero — {_nome(a)} (antigo proprietário)", "antigos_proprietarios", a.parte_id, alvo=ALVO_ANTIGOS_PROPRIETARIOS)
                conferir_pessoa(a, antigo=True)
            for pj in antigos_pj:
                nome_pj = pj.razao_social or frases.documento(pj.cnpj)[1] or "empresa"
                if not (pj.razao_social or "").strip():
                    av.falta(
                        "partes.pj.razao_social",
                        f"Razão social — {nome_pj} (antiga proprietária)",
                        "antigos_proprietarios", pj.parte_id, alvo=ALVO_ANTIGOS_PROPRIETARIOS,
                    )
                if not (pj.cnpj or "").strip():
                    av.falta(
                        "partes.pj.cnpj", f"CNPJ — {nome_pj} (antiga proprietária)",
                        "antigos_proprietarios", pj.parte_id, alvo=ALVO_ANTIGOS_PROPRIETARIOS,
                    )
                elif not cnpj_valido(pj.cnpj):
                    av.bloqueia("CNPJ_INVALIDO", f"O CNPJ de {nome_pj} não confere (dígitos verificadores).")
                conferir(pj.parte_id, pj.certidoes, "cnpj", nome_pj, antigo=True)
            if antigos_pj:
                av.avisa(
                    "PJ_ANTIGO_PROPRIETARIO_A_CONFIRMAR",
                    "Antiga proprietária pessoa jurídica: nenhum contrato assinado do escritório tem esta "
                    "redação — confirme na revisão jurídica.",
                )
                av.revisar(
                    "PJ_ANTIGO_PROPRIETARIO_A_CONFIRMAR",
                    "Certidões da antiga proprietária pessoa jurídica",
                    "redação sem precedente no acervo assinado — confirme na revisão jurídica",
                )
        elif antigos or antigos_pj:
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


def _corretagem_favorecido_vs_imobiliaria(av: Avaliacao, d: DadosContrato) -> None:
    """[Migration 215, D4] NON-BLOCKING aviso: the commission payee of the
    office's own intermediação is typed per deal and may legitimately differ
    from the company that signs — but a mismatch is worth a second look at the
    PIX. Never blocks."""
    org = d.imobiliaria
    cnpj_empresa = "".join(ch for ch in (org.cnpj or "") if ch.isdigit())
    if org.id is None or not cnpj_empresa:
        return
    favorecidos = {f.id: f for f in d.favorecidos}
    for it in d.intermediarios:
        if not it.corretor_id or not it.favorecido_id:
            continue
        fav = favorecidos.get(it.favorecido_id)
        digitos = "".join(ch for ch in ((fav.cpf_cnpj if fav else None) or "") if ch.isdigit())
        if fav is not None and digitos and digitos != cnpj_empresa:
            av.avisa(
                "CORRETAGEM_FAVORECIDO_DIFERENTE_DA_IMOBILIARIA",
                f"O favorecido da corretagem ({fav.nome}) não é a imobiliária que assina "
                f"o contrato ({org.razao_social or 'imobiliária'}). Confira o PIX.",
            )


def _imobiliaria(av: Avaliacao, d: DadosContrato, politica: Politica) -> None:
    org = d.imobiliaria
    # [Migration 215] The company that signs is the contract's CHOICE (or the
    # org's only active one — `imobiliarias_service.resolver`, resolved by the
    # carregador). None resolved => never a silent fallback: a named gap.
    if org.id is None:
        av.falta(
            "imobiliaria.selecao",
            "Imobiliária que assina o contrato",
            "imobiliaria",
            destino_em="contrato",
            alvo=alvo_imobiliaria_select(av.destinos.contrato_id),
        )
    for valor, campo, rotulo in (
        (org.razao_social, "razao_social", "Razão social da imobiliária"),
        (org.cnpj, "cnpj", "CNPJ da imobiliária"),
        (org.responsavel_nome, "responsavel_nome", "Responsável legal da imobiliária"),
        (org.responsavel_creci, "responsavel_creci", "CRECI do responsável"),
        (org.endereco.cidade, "endereco_cidade", "Cidade da imobiliária (local de assinatura)"),
    ):
        if not valor:
            av.falta(f"imobiliaria.{campo}", rotulo, "imobiliaria", destino_em="imobiliarias")
    _corretagem_favorecido_vs_imobiliaria(av, d)
    # [Migration 168, owner decision 2026-09-24] The registry is open-ended
    # and a contract SELECTS 2 to 5 witnesses (`contrato_testemunhas`) — the
    # carregador only ever loads the SELECTED set. Fewer than 2 is a gap, not
    # a refusal: the operator may still be picking.
    if len(d.testemunhas) < MIN_TESTEMUNHAS:
        av.falta(
            "imobiliaria.testemunhas",
            f"Ao menos {MIN_TESTEMUNHAS} testemunhas selecionadas",
            "imobiliaria",
            destino_em="contrato",
            alvo=alvo_testemunhas_select(av.destinos.contrato_id),
        )
    for i, t in enumerate(d.testemunhas, start=1):
        if not t.nome:
            av.falta(f"imobiliaria.testemunha.{i}.nome", f"Nome da testemunha {i}", "imobiliaria")
        # [Migration 168, owner decision — supersedes the Q14 RG-required
        # rule] The contract now prints CPF instead of RG; RG left the
        # registration form entirely. CPF is required, not optional — a
        # witness can only ever be SELECTED for a contract with one
        # (`contrato_testemunhas_service.definir`), so this is a second,
        # independent gate for the same rule, not a new one.
        if not t.cpf:
            av.falta(f"imobiliaria.testemunha.{i}.cpf", f"CPF da testemunha {i}", "imobiliaria")
        elif not cpf_valido(t.cpf):
            av.bloqueia("CPF_INVALIDO", f"O CPF da testemunha {i} não confere (dígitos verificadores).")
        # [Owner directive, 2026-09-23] E-mail used to gate only SENDING for
        # signature (`assinatura_service.enviar` / D4Sign), never generating
        # the document — an aviso a witness the office hadn't e-mail'd yet
        # never blocked on. It now blocks readiness itself, same terms as
        # nome/cpf above, for a digital contract (a física one still never
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
    multa_posse = posse_multa_diaria(d)
    if multa_posse is None:
        av.falta(
            "imobiliaria.posse_multa_diaria",
            "Multa diária por atraso na entrega da posse (valor da imobiliária)",
            "imobiliaria",
        )
    elif multa_posse <= 0:
        av.bloqueia("MULTA_DIARIA_POSSE_INVALIDA", "A multa diária da posse precisa ser maior que zero.")
    # [Q11] pendências prazo.
    if prazo_pendencias(d, politica) <= 0:
        av.bloqueia("PRAZO_PENDENCIAS_INVALIDO", "O prazo para apresentar as pendências precisa ser maior que zero.")


def _clausulas_extras(d: DadosContrato, sw: dict[str, bool], av: Avaliacao) -> None:
    """[Migration 207] Per-clause special conditions the card holds
    (`termos.clausulas_extras`): printed VERBATIM in the clause they name and
    ALWAYS a legal-review item — bespoke wording the office never standardised.
    "substituir" drops the clause's standard wording, so it is the stronger
    aviso. Refused (never silently dropped): a key that is not one of the
    generator's clauses, a mode outside `MODOS_CLAUSULA_EXTRA`, wording typed
    for a clause this contract does not have, formatting markup."""
    for chave, entrada in d.termos.clausulas_extras.items():
        paragrafos = frases.paragrafos_livres(entrada.texto)
        if chave not in ORDEM_CLAUSULAS:
            if paragrafos:
                av.bloqueia(
                    "CLAUSULA_EXTRA_DESCONHECIDA",
                    f"Condição especial para a cláusula '{chave}', que o contrato não tem — remova-a.",
                )
            continue
        if not paragrafos:
            continue
        titulo_clausula = rotulo_clausula(chave)
        if entrada.modo not in MODOS_CLAUSULA_EXTRA:
            av.bloqueia(
                "CLAUSULA_EXTRA_MODO_INVALIDO",
                f"Condição especial de '{titulo_clausula}': modo '{entrada.modo}' inválido "
                f"(use {' ou '.join(MODOS_CLAUSULA_EXTRA)}).",
            )
            continue
        chave_switch = CLAUSULA_CONDICIONAL.get(chave)
        if chave_switch is not None and not sw.get(chave_switch, False):
            av.bloqueia(
                "CLAUSULA_EXTRA_SEM_CLAUSULA",
                f"Há condição especial para '{titulo_clausula}', mas este contrato não tem essa "
                "cláusula — o texto não teria onde entrar. Apague-a ou ajuste o negócio.",
            )
            continue
        if any(has_raw_markup(t) for t in paragrafos):
            av.bloqueia(
                "TEXTO_LIVRE_COM_MARCACAO",
                f"Condição especial de '{titulo_clausula}': o texto contém marcação de formatação "
                "(** ou <u>) — remova-a.",
            )
        if entrada.modo == "substituir":
            codigo = f"CLAUSULA_SUBSTITUIDA_{chave.upper()}"
            titulo = f"Cláusula padrão SUBSTITUÍDA — {titulo_clausula} (texto digitado)"
            av.avisa(
                codigo,
                f"{titulo_clausula}: o texto padrão desta cláusula NÃO será impresso — vale somente o "
                "texto digitado, exatamente como digitado, e entra como item da revisão jurídica.",
            )
            av.revisar(codigo, titulo, "\n".join(paragrafos))
        else:
            codigo = f"CLAUSULA_EXTRA_{chave.upper()}"
            titulo = f"Condição especial acrescentada — {titulo_clausula} (texto digitado)"
            av.avisa(
                codigo,
                f"{titulo_clausula}: o texto digitado será acrescentado, exatamente como digitado, "
                "após os parágrafos padrão e entra como item da revisão jurídica.",
            )
            av.revisar(codigo, titulo, "\n".join(paragrafos))


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
        # The tipo decides how `valor` prints (a percentage of the price or a
        # fixed amount) — never assumed "percentual" when it is missing.
        if not it.tipo:
            av.falta(
                f"negociacao.intermediario.{it.id}.tipo",
                f"Tipo da corretagem de {it.nome} (percentual ou valor fixo)",
                "negociacao",
            )
        elif it.tipo not in TIPOS_INTERMEDIARIO:
            av.bloqueia(
                "INTERMEDIARIO_TIPO_DESCONHECIDO",
                f"Tipo de corretagem desconhecido para {it.nome}: {it.tipo}.",
            )
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
    # [Migration 193 — supersedes the 2026-10-03 OBRIGACOES_VENDEDOR_SEM_REDACAO
    # / PERMUTA_OBRIGACOES_SEM_REDACAO bloqueios] The signed contracts carry
    # these as FREE paragraphs (corpus catalog §5: 6 deals' seller
    # declarations/regularização, 1 permuta delivery), so the operator's text
    # is printed VERBATIM where the corpus puts it — seller obligations as a
    # paragraph of the ÔNUS clause (deal 859), the permuta delivery inside
    # the permuta posse clause (deal 873) — and recorded as a legal-review
    # item: wording the office never standardised gets a lawyer's eye.
    for valor, codigo, titulo, ligado in (
        (d.termos.obrigacoes_vendedor, "OBRIGACOES_VENDEDOR_TEXTO_LIVRE",
         "Obrigações/declarações do vendedor (texto digitado)", True),
        (d.termos.permuta_obrigacoes_entrega, "PERMUTA_OBRIGACOES_TEXTO_LIVRE",
         "Obrigações de entrega do imóvel da permuta (texto digitado)", sw["tem_permuta"]),
    ):
        paragrafos = frases.paragrafos_livres(valor)
        if not paragrafos:
            continue
        if not ligado:
            av.bloqueia(
                "PERMUTA_OBRIGACOES_SEM_PERMUTA",
                "As obrigações de entrega do imóvel da permuta foram preenchidas, mas o negócio não "
                "tem parcela de permuta — o texto não teria onde entrar. Apague o campo ou inclua a permuta.",
            )
            continue
        if any(has_raw_markup(t) for t in paragrafos):
            av.bloqueia(
                "TEXTO_LIVRE_COM_MARCACAO",
                f"{titulo}: o texto contém marcação de formatação (** ou <u>) — remova-a.",
            )
        av.avisa(
            codigo,
            f"{titulo}: será impresso exatamente como digitado e entra como item da revisão jurídica.",
        )
        av.revisar(codigo, titulo, "\n".join(paragrafos))
    _clausulas_extras(d, sw, av)
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
    #
    # [2026-10-03, deal 869] When the text names no comarca the cartório the
    # operator confirmed on the imóvel answers it (`foro_comarca`) — the
    # manual path the readiness item points at, no new field: the comarca is
    # the registering cartório's. Only when NEITHER resolves is it a gap,
    # and the falta now says where to type it.
    if d.imovel is not None and foro_comarca(d) is None:
        av.falta(
            "negociacao.foro_comarca",
            "Comarca do cartório da matrícula — não encontrada no texto da matrícula; informe o "
            "cartório de registro de imóveis na página do imóvel (ex.: \"1º Oficial de Registro de "
            "Imóveis de Cotia\")",
            "matricula",
            destino_em="imovel",
            alvo=ALVO_DOCUMENTOS_DO_IMOVEL,
        )
    elif (
        d.imovel is not None
        and d.matricula.comarca
        and (cartorio := frases.cartorio_partes(d.imovel.numero_registro_imoveis)) is not None
        and not _mesma_cidade(d.matricula.comarca, cartorio[1])
    ):
        av.avisa(
            "FORO_COMARCA_DIFERENTE_DO_CARTORIO",
            f"A comarca lida na matrícula ({d.matricula.comarca}) difere da cidade do cartório "
            f"informado ({cartorio[1]}); o foro sai como {d.matricula.comarca}.",
        )


#: Public name for the parties gate (`contrato_aditivo` reuses it).
avaliar_partes = _partes


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
    _partes(av, d, politica)
    _imovel(av, d, switches, politica, assinatura)
    _negociacao(av, d, switches, assinatura, agrupar_parcelas=True)
    _financiamento(av, d, switches)
    _permuta(av, d, switches)
    _certidoes(av, d, switches, politica, assinatura, hoje)
    _imobiliaria(av, d, politica)
    _intermediacao(av, d, switches)
    _contrato(av, d, switches)
    return av


__all__ = [
    "alvo_imobiliaria_select",
    "alvo_testemunhas_select",
    "ALVO_ANTIGOS_PROPRIETARIOS",
    "ALVO_AD_CORPUS",
    "ALVO_PERMUTA_POSSE",
    "ALVO_POSSE",
    "ALVO_DOCUMENTOS_DO_IMOVEL",
    "ALVO_ITENS_INTEGRANTES",
    "Avaliacao",
    "Destinos",
    "EmpresaExigida",
    "MODELO_A_VISTA",
    "MODELO_COMPRA_VENDA",
    "MODELO_PERMUTA",
    "MOTIVO_EMISSAO_TEXTO",
    "ORDEM_CERTIDOES_IMOVEL",
    "alvo_emissao_certidao_imovel",
    "SUFIXO_DOCUMENTO_DE_IDENTIDADE",
    "SUFIXO_PJ_BAIXADA",
    "PJ_REDACAO_A_CONFIRMAR",
    "anos_antes",
    "antigos_no_contrato",
    "companheiro_dispensado",
    "conjuge_do_anuente",
    "pj_certificandas",
    "antigos_proprietarios",
    "antigos_proprietarios_pj",
    "empresas_impressas_como_parte",
    "partes_pj_contratantes",
    "avaliar",
    "avaliar_partes",
    "certidoes_imovel",
    "classificar_empresa",
    "classificar_situacao_pj",
    "comarca_de_texto",
    "foro_comarca",
    "corretagem_marcos",
    "derivar_switches",
    "empresas_exigidas",
    "exige_antigo_proprietario",
    "ha_menos_de_anos",
    "indice_certidoes",
    "modelo_derivado",
    "motivo_publico",
    "numero_da_parcela",
    "parcelas_antes_de",
    "parcelas_ordenadas",
    "pct_intermediarios",
    "pessoas_certificadas",
    "signatarios_certificandos",
    "posse_multa_diaria",
    "prazo_pendencias",
    "tipos_exigidos",
    "clausulas_extras_ativas",
]
