"""Swap-shaped (cross-fit) matching — does EACH owner get what they asked for?

Pure scoring, no I/O. Sibling of :mod:`matching`, not a replacement for it.

WHY A SECOND SCORER EXISTS
──────────────────────────
:mod:`matching` scores how SIMILAR two properties are — same city, similar
price, same type, at least as many bedrooms. That is the right question for
"show me listings like this one" (social-wiring's `similares_service` still
asks it), and it is the wrong question for a swap. Measured 2026-10-26 on the
social-wiring corpus (113 ativos, 6237 pairs), the similarity engine:

  * emitted 143 matches, 104 of which (73%) broke at least one owner's own
    stated ceiling — 24 broke BOTH owners' ceilings;
  * recovered 1 of the 7 pairs the brokers had kept in the legacy funnel;
  * compressed every score into 45–59, so the ranking carried no signal.

The kept pairs show why. A R$3.3M house whose owner "accepts a smaller
property up to 50%" against a R$1.08M apartment whose owner wrote "Aceita
Permuta São Paulo 2" (the house's condominium) is a textbook deal — and
scored 29, because the two properties are in different cities and a 3:1
price ratio looks "incompatible" to a similarity score. A house whose owner
wants an APARTMENT against an apartment whose owner wants a HOUSE scored 0 on
specs, because specs rewarded the SAME type.

THE MODEL
─────────
A swap is two acceptances. For a pair (A, B):

    A receives B   — does B fit what A's owner stated (type, value, place)?
    B receives A   — does A fit what B's owner stated?

`valor_max` on an interest is the most valuable property that owner would
RECEIVE. Most owners trade DOWN (ceiling ≈ 40–80% of their own price, the
rest in cash), a few trade UP (ceiling above their own price). A pair works
only when one side's ceiling admits the other's value AND vice versa — which
is exactly why two trade-down owners can never swap with each other, and the
old scorer, by ignoring ceilings, kept pairing them.

Score, 100 points, symmetric (orientation never changes it):

    A recebe B   40   tipo 14 · valor 14 · lugar 12
    B recebe A   40
    proximidade  12   same state 2 · same city 5 · same bairro 5
    qualidade     8   listing completeness, averaged over both sides

An owner who stated nothing for a criterion gets a small neutral credit for
it (`NEUTRO_*`), never the full one: "estuda propostas" is a yes, but it is
not evidence of fit, and full credit would float every open owner to the top.

HARD GATES (a pair failing any one does not exist):
  * the same owner on both sides;
  * either side has no interest the other's property satisfies — a stated
    TYPE that does not match, or a VALUE beyond the ±20% tolerance;
  * two properties in different states.

PLACE IS SOFT, ON PURPOSE. Location wants are written as prose ("de
preferência na Granja Viana", "Km 21 ao Km 30") and the structured `zona`
is 80% the macro-region "Oeste", which every listing in this market sits in.
A place match earns points; a miss costs only the points. Gating on prose we
read with string matching would turn a parser limitation into a lost deal.

When all four vectors exist and both directions clear the semantic
threshold, the composite is ``0.6 × regras + 0.4 × semântica`` — the same
bilateral similarity :mod:`matching` uses, so a corpus is embedded once.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from noctusai_lib.domain.real_estate.matching import (
    _num,
    calcular_bilateral_similarity,
    calcular_qualidade_anuncio,
    falta_vetor_bilateral,
)
from noctusai_lib.primitives.accents import fold_accents

__all__ = [
    "MODELO",
    "SCORE_MINIMO_PERMUTA",
    "TOLERANCIA_VALOR",
    "avaliar_recebimento",
    "emitir_permuta",
    "emitir_permutas",
    "lugar_atende",
    "pontuar_permuta",
    "tipo_atende",
    "valor_atende",
]

#: Stamped on every emitted row, so a stored score says which model made it.
MODELO = "permuta_cruzada_v1"

#: A stated value bound is a round number someone said out loud ("até 1,2
#: milhão"), not a walk-away limit. 20% either side is what :mod:`matching`
#: has always allowed, and the two engines must agree on what "fits" means.
TOLERANCIA_VALOR = 0.20

#: Calibrated 2026-10-26 on the social-wiring corpus (113 ativos, 6237 pairs).
#: The bands read as evidence tiers:
#:
#:     60+     both owners have concrete criteria confirmed
#:     50–60   one confirmed criterion on each side
#:     40–50   one side confirmed, the other "aberto a propostas"
#:     < 40    two open owners — never emitted
#:
#: 40 is where all 7 pairs the brokers KEPT in the legacy funnel survive; at
#: 45 two of them are lost, and both are the commonest real shape (a seller
#: with a stated ceiling, a buyer who only said "estuda propostas").
SCORE_MINIMO_PERMUTA = 40.0

PESO_TIPO = 14
PESO_VALOR = 14
PESO_LUGAR = 12
PESO_LADO = PESO_TIPO + PESO_VALOR + PESO_LUGAR  # 40
PESO_PROXIMIDADE = 12
PESO_QUALIDADE = 8

#: Credit for a criterion the owner did not state. Low by design — see header.
NEUTRO_TIPO = 5
NEUTRO_VALOR = 5
NEUTRO_LUGAR = 4

#: Inside the band only after the tolerance: half credit.
VALOR_TOLERADO = PESO_VALOR // 2

#: With no stated ceiling, a trade UP beyond this multiple of the owner's own
#: value earns no value credit. Without it, "aceita permuta" with no number
#: read as "will pay any difference": the first calibration run ranked a R$2M
#: owner receiving a R$14M house at 80.
#:
#: 🔴 SOFT, NEVER A GATE. Gating on it (tried 2026-10-26) rejected 4 of the 7
#: pairs the brokers had KEPT — an R$1.08M apartment for an R$3.3M house, an
#: R$360k apartment for an R$1.48M house. In a partial permuta the property is
#: only part of the payment and the buyer's cash is unknown to us, so a big
#: trade-up is unproven, not impossible. It costs the credit, not the pair.
SUBIDA_MAXIMA_SEM_TETO = 2.0

#: Macro-regions. `zona='Oeste'` is on 95 of 118 interests in the corpus this
#: was calibrated on; a term every listing satisfies identifies none of them.
_MACROZONAS = frozenset({
    "oeste", "leste", "sul", "norte", "centro", "centro-oeste",
    "zona oeste", "zona leste", "zona sul", "zona norte",
    "litoral", "litoral sul", "litoral norte", "litoral sudeste",
    "interior", "capital", "grande sao paulo",
})

#: A property type that IS another for the purpose of "what I asked for".
#: Someone who wants an apartment has asked for a cobertura too; the reverse
#: is not true, which is why this maps the OFFER onto the wanted family.
_FAMILIA_TIPO = {
    "cobertura": "apartamento",
    "duplex": "apartamento",
    "triplex": "apartamento",
    "estudio": "apartamento",
    "studio": "apartamento",
    "flat": "apartamento",
    "kitnet": "apartamento",
    "loft": "apartamento",
    "garden": "apartamento",
    "sitio": "chacara",
    "fazenda": "chacara",
}

#: Words that never identify a place on their own — matching "jardim" or
#: "parque" in someone's prose would pair them with half the catalog.
_PALAVRAS_GENERICAS = frozenset({
    "da", "de", "do", "das", "dos", "e", "em", "na", "no",
    "jardim", "jd", "parque", "vila", "residencial", "condominio", "cond",
    "chacara", "recanto", "centro", "area", "terreno", "bairro", "alto",
    "nova", "novo", "sao", "santa", "santo", "km",
})

_KM = re.compile(r"\bkm\s*(\d{1,3})\b")
_KM_FAIXA = re.compile(
    r"\bkm\s*(\d{1,3})\s*(?:a|ao|ate|e|-|/)\s*(?:o\s+)?(?:km\s*)?(\d{1,3})\b"
)


def _norm(value: Any) -> str:
    """Accent-folded, lower-cased, whitespace-collapsed — or "" for non-text."""
    if not isinstance(value, str):
        return ""
    return " ".join(fold_accents(value).lower().split())


# ── Type ────────────────────────────────────────────────────────────────────


def tipo_atende(desejado: Any, oferecido: Any) -> Optional[bool]:
    """Does an offered property type satisfy a wanted one?

    ``None`` when either side is unknown — "unstated" is not "mismatch".
    A wanted type is a FAMILY head: "Casa" admits "Casa em Condomínio",
    "Terreno" admits "Terreno de Rua"; "Casa em condomínio" does NOT admit a
    street "Casa". Case and accents never matter — the corpus spells the same
    type "Casa em condomínio" on the interest and "Casa em Condomínio" in
    Vista, and an exact compare scored that as a mismatch.
    """
    d, o = _norm(desejado), _norm(oferecido)
    if not d or not o:
        return None
    familia = _FAMILIA_TIPO.get(o, o)
    return o == d or familia == d or o.startswith(d + " ")


# ── Value ───────────────────────────────────────────────────────────────────


def valor_atende(interesse: dict, valor: Any) -> Optional[int]:
    """Where an offered value sits against one interest's stated band.

    ``2`` inside the band · ``1`` inside only after the tolerance · ``0``
    beyond it · ``None`` when there is no bound or no value to compare.

    🔴 EACH BOUND IS CHECKED ON ITS OWN. The predecessor returned "fits" when
    the floor was missing, and the floor is missing on 116 of 118 interests in
    the corpus — so every stated ceiling was silently ignored.
    """
    v = _num(valor)
    vmin, vmax = _num(interesse.get("valor_min")), _num(interesse.get("valor_max"))
    if v <= 0 or (vmin <= 0 and vmax <= 0):
        return None
    if (vmin <= 0 or v >= vmin) and (vmax <= 0 or v <= vmax):
        return 2
    folga_min = vmin <= 0 or v >= vmin * (1 - TOLERANCIA_VALOR)
    folga_max = vmax <= 0 or v <= vmax * (1 + TOLERANCIA_VALOR)
    return 1 if folga_min and folga_max else 0


# ── Place ───────────────────────────────────────────────────────────────────


def _nomes_de_lugar(oferta: dict) -> list[str]:
    """Normalised place names that identify where the offered property is.

    The full bairro, its base name before Vista's " - Km 23" suffix, the city,
    and every two-word run of a multi-word name whose words are both specific
    ("granja viana" out of "Miolo Granja Viana") — the prose names regions,
    the catalog names sub-divisions of them. A name carrying a number keeps it
    whole: "São Paulo 2" is a condominium in Cotia, and splitting it would
    match "apartamento em São Paulo".
    """
    nomes: list[str] = []
    for bruto in (oferta.get("bairro"), oferta.get("condominio_nome"), oferta.get("cidade")):
        nome = _norm(bruto)
        if not nome:
            continue
        base = nome.split(" - ")[0].strip()
        for candidato in {nome, base}:
            if len(candidato) >= 4 and candidato not in _PALAVRAS_GENERICAS:
                nomes.append(candidato)
        palavras = base.split()
        if len(palavras) >= 3 and not any(p.isdigit() for p in palavras):
            for a, b in zip(palavras, palavras[1:]):
                if a not in _PALAVRAS_GENERICAS and b not in _PALAVRAS_GENERICAS:
                    nomes.append(f"{a} {b}")
    return nomes


def _menciona(texto: str, nome: str) -> bool:
    """`nome` as a whole phrase in `texto`, not followed by a number.

    The trailing-number guard is what keeps the city "São Paulo" from hitting
    prose about the condominium "São Paulo 2".
    """
    return re.search(rf"(?<!\w){re.escape(nome)}(?!\w)(?!\s*\d)", texto) is not None


def _km_da_oferta(oferta: dict) -> Optional[int]:
    """The Raposo Tavares km marker Vista appends to bairros ("… - Km 23")."""
    achado = _KM.search(_norm(oferta.get("bairro")))
    return int(achado.group(1)) if achado else None


def _km_atende(texto: str, km: int) -> bool:
    """Is `km` inside a range ("Km 21 ao Km 30") or next to a single "Km 23"?"""
    for faixa in _KM_FAIXA.finditer(texto):
        a, b = sorted((int(faixa.group(1)), int(faixa.group(2))))
        if a <= km <= b:
            return True
    return any(abs(int(m.group(1)) - km) <= 1 for m in _KM.finditer(texto))


def lugar_atende(interesse: dict, oferta: dict, texto_extra: str = "") -> Optional[bool]:
    """Is the offered property where this interest wants to be?

    ``True`` on positive evidence — a structured place term, a place named in
    the prose, or a km marker inside a stated km range. ``False`` only when
    the owner STRUCTURED a specific place and the offer is not in it.
    ``None`` otherwise: prose that names no place we can recognise is not a
    "no", it is "we cannot tell", and must not cost the pair anything more
    than the missing credit.
    """
    local_oferta = " ".join(
        _norm(oferta.get(k)) for k in ("bairro", "condominio_nome", "cidade")
    )
    termos = [
        t for t in (_norm(interesse.get(k)) for k in ("bairro", "cidade", "zona"))
        if t and t not in _MACROZONAS
    ]
    if any(_menciona(local_oferta, t) for t in termos):
        return True

    texto = _norm(" ".join(filter(None, (interesse.get("observacoes"), texto_extra))))
    if texto:
        if any(_menciona(texto, nome) for nome in _nomes_de_lugar(oferta)):
            return True
        km = _km_da_oferta(oferta)
        if km is not None and _km_atende(texto, km):
            return True

    return False if termos else None


# ── One direction ───────────────────────────────────────────────────────────


def avaliar_recebimento(quem_recebe: dict, oferta: dict) -> dict:
    """Would `quem_recebe`'s owner accept `oferta`? Scored out of 40.

    Every property-shaped interest is tried; the best ACCEPTING one wins. An
    interest accepts when no criterion it states is violated — a stated type
    that does not match, or a value beyond the tolerance. An owner with no
    property interest at all is open ("aberto") and accepts at neutral credit.

    Returns ``{"aceita", "aberto", "pontos", "tipo", "valor", "lugar",
    "teto", "subida_sem_teto"}`` — the per-criterion verdicts are kept so the justification can
    say WHY, which is the part a broker reads before calling anyone.
    """
    interesses = [
        i for i in (quem_recebe.get("interesses") or [])
        if (i.get("tipo") or "imovel") == "imovel"
    ]
    texto_extra = quem_recebe.get("observacoes") or ""

    if not interesses:
        # Someone who stated only a VEHICLE interest has said what they want,
        # and it is not a property: rejecting is reading them correctly.
        so_veiculo = any(
            i.get("tipo") == "automovel" for i in (quem_recebe.get("interesses") or [])
        )
        subida = (
            _num(quem_recebe.get("valor")) > 0
            and _num(oferta.get("valor"))
            > _num(quem_recebe.get("valor")) * SUBIDA_MAXIMA_SEM_TETO
        )
        return {
            "aceita": not so_veiculo,
            "aberto": True,
            "pontos": 0 if so_veiculo else NEUTRO_TIPO + NEUTRO_LUGAR + (0 if subida else NEUTRO_VALOR),
            "tipo": None, "valor": None, "lugar": None, "teto": None,
            "subida_sem_teto": subida,
        }

    proprio = _num(quem_recebe.get("valor"))
    oferecido = _num(oferta.get("valor"))
    melhor: Optional[dict] = None
    for interesse in interesses:
        tipo = tipo_atende(interesse.get("tipo_imovel"), oferta.get("tipo_imovel"))
        valor = valor_atende(interesse, oferta.get("valor"))
        if tipo is False or valor == 0:
            continue
        lugar = lugar_atende(interesse, oferta, texto_extra)
        subida = (
            _num(interesse.get("valor_max")) <= 0
            and proprio > 0
            and oferecido > proprio * SUBIDA_MAXIMA_SEM_TETO
        )

        pontos = (
            (PESO_TIPO if tipo else NEUTRO_TIPO)
            + (
                0 if subida  # see SUBIDA_MAXIMA_SEM_TETO
                else PESO_VALOR if valor == 2
                else VALOR_TOLERADO if valor == 1
                else NEUTRO_VALOR
            )
            + (PESO_LUGAR if lugar else 0 if lugar is False else NEUTRO_LUGAR)
        )
        if melhor is None or pontos > melhor["pontos"]:
            melhor = {
                "aceita": True,
                "aberto": tipo is None and valor is None and lugar is None,
                "pontos": pontos,
                "tipo": tipo,
                "valor": valor,
                "lugar": lugar,
                "teto": _num(interesse.get("valor_max")) or None,
                "subida_sem_teto": subida,
            }

    if melhor is None:
        return {
            "aceita": False, "aberto": False, "pontos": 0,
            "tipo": None, "valor": None, "lugar": None, "teto": None,
            "subida_sem_teto": False,
        }
    return melhor


# ── The pair ────────────────────────────────────────────────────────────────


def _proximidade(a: dict, b: dict) -> int:
    """Same market, out of 12. A weak signal, weighted as one.

    Uses state, city and bairro only. `zona` is deliberately absent: on the
    Vista side it holds the registry office ("R.I. Cotia"), not a region.
    """
    pontos = 0
    for chave, peso in (("estado", 2), ("cidade", 5), ("bairro", 5)):
        va, vb = _norm(a.get(chave)), _norm(b.get(chave))
        if va and va == vb:
            pontos += peso
    return min(pontos, PESO_PROXIMIDADE)


def _brl(valor: float) -> str:
    if valor >= 1_000_000:
        return f"R$ {valor / 1_000_000:.2f}M".replace(".", ",")
    return f"R$ {valor / 1_000:.0f} mil"


def _explicar(rotulo: str, lado: dict, oferta: dict) -> str:
    subida = " (sobe de patamar sem teto declarado)" if lado["subida_sem_teto"] else ""
    if lado["aberto"]:
        return f"{rotulo}: aberto a propostas{subida}"
    partes = []
    if lado["tipo"]:
        partes.append(f"tipo ✓ ({oferta.get('tipo_imovel')})")
    if lado["valor"] == 2:
        partes.append(f"valor ✓ ({_brl(_num(oferta.get('valor')))} ≤ teto {_brl(lado['teto'])})"
                      if lado["teto"] else "valor ✓")
    elif lado["valor"] == 1:
        partes.append("valor na tolerância")
    if lado["lugar"]:
        partes.append("local ✓")
    elif lado["lugar"] is False:
        partes.append("local fora do pedido")
    return f"{rotulo}: " + (", ".join(partes) if partes else "sem critério confirmado") + subida


def pontuar_permuta(a: dict, b: dict) -> Optional[dict]:
    """Score one pair as a swap. ``None`` means a hard gate rejected it.

    Symmetric: ``pontuar_permuta(a, b)`` and ``pontuar_permuta(b, a)`` give
    the same score with the two sides' details swapped. `None` is not `0` —
    a rejected pair must never be persisted (see :func:`matching.calcular_score_total`).
    """
    if a.get("owner_id") and a.get("owner_id") == b.get("owner_id"):
        return None
    ea, eb = _norm(a.get("estado")), _norm(b.get("estado"))
    if ea and eb and ea != eb:
        return None

    a_recebe = avaliar_recebimento(a, b)
    b_recebe = avaliar_recebimento(b, a)
    if not (a_recebe["aceita"] and b_recebe["aceita"]):
        return None

    proximidade = _proximidade(a, b)
    qualidade = round(
        (calcular_qualidade_anuncio(a) + calcular_qualidade_anuncio(b)) / 2 * PESO_QUALIDADE / 10
    )
    regras = float(a_recebe["pontos"] + b_recebe["pontos"] + proximidade + qualidade)

    # Only for pairs that survived the gates — vector maths on a pair nobody
    # will see is the most expensive thing a scorer can do.
    similaridade = calcular_bilateral_similarity(a, b)
    total = round(0.6 * regras + 0.4 * similaridade * 100, 1) if similaridade > 0 else regras

    va, vb = _num(a.get("valor")), _num(b.get("valor"))
    diferenca = abs(va - vb) if va > 0 and vb > 0 else None
    justificativa = ". ".join(filter(None, (
        _explicar("Origem recebe", a_recebe, b),
        _explicar("Destino recebe", b_recebe, a),
        (f"Diferença de {_brl(diferenca)}, complementada pelo lado "
         f"{'destino' if vb < va else 'origem'}") if diferenca else None,
        "Alta compatibilidade semântica" if similaridade >= 0.7 else None,
    )))

    def _lado(r: dict) -> dict:
        return {
            k: r[k]
            for k in ("aberto", "pontos", "tipo", "valor", "lugar", "teto", "subida_sem_teto")
        }

    return {
        "score": total,
        "justificativa": justificativa,
        "detalhes": {
            "modelo": MODELO,
            "origem_recebe": _lado(a_recebe),
            "destino_recebe": _lado(b_recebe),
            "proximidade": proximidade,
            "qualidade_anuncio": qualidade,
            "gap_valor": diferenca or 0,
            "embedding_similarity": round(similaridade, 4) if similaridade > 0 else 0,
            "semantica_disponivel": not falta_vetor_bilateral(a, b),
        },
        "score_breakdown": {
            "origem_recebe": round(a_recebe["pontos"] / PESO_LADO * 100, 1),
            "destino_recebe": round(b_recebe["pontos"] / PESO_LADO * 100, 1),
            "proximidade": round(proximidade / PESO_PROXIMIDADE * 100, 1),
            "qualidade_anuncio": round(qualidade / PESO_QUALIDADE * 100, 1),
            "embedding_similarity": round(similaridade * 100, 1) if similaridade > 0 else 0,
        },
    }


def emitir_permuta(
    origem: dict,
    destino: dict,
    score_minimo: float = SCORE_MINIMO_PERMUTA,
) -> Optional[dict]:
    """Score an oriented pair and shape it for persistence, or ``None``.

    Inactive ativos never pair. The orientation is the CALLER's (the score is
    symmetric, the stored row is not), so a consumer with a unique index on
    (origem, destino) keeps one canonical orientation per pair.
    """
    if origem.get("status", "ativo") != "ativo" or destino.get("status", "ativo") != "ativo":
        return None
    resultado = pontuar_permuta(origem, destino)
    if resultado is None or resultado["score"] < score_minimo:
        return None
    return {
        "ativo_origem_id": origem["id"],
        "ativo_destino_id": destino["id"],
        **resultado,
    }


def emitir_permutas(
    pares: Iterable[tuple[dict, dict]],
    score_minimo: float = SCORE_MINIMO_PERMUTA,
) -> list[dict]:
    """Every emitted pair, best first."""
    saida = [m for o, d in pares if (m := emitir_permuta(o, d, score_minimo))]
    saida.sort(key=lambda m: m["score"], reverse=True)
    return saida

