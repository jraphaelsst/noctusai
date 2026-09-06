"""Property-swap matching — pure scoring, no I/O.

Scores how well an *imóvel* (a listing whose owner accepts a swap) pairs with
a *permuta* (a property, or a vehicle, brought as swap currency).

Lifted 2026-09-06 from ``products/erp-imobiliario/backend/app/services/
matching.py`` when social-wiring became the second consumer. The weights,
thresholds and gates below are that implementation's, unchanged — this is a
promotion, not a rewrite, and erp's behaviour must not move because of it.

🔴 ONE DELIBERATE DIVERGENCE, and it is not cosmetic.
The self-match guard was ``if permuta.get('owner_id') == imovel.get('owner_id')``.
When BOTH sides lack an owner that comparison is ``None == None`` — true — so
every pair is skipped and the matcher returns an empty list while reporting
success. erp never hit it because ``erp.ativos.owner_id`` is always populated;
a consumer whose rows do not carry an owner would have found a silent
total failure with no error to read. The guard now requires a truthy
``owner_id`` before it can exclude anything. For erp the behaviour is
identical, because the column is never null there.

WHAT A CONSUMER OWES THIS MODULE
────────────────────────────────
Two plain dicts. Nothing here touches a database, a client or a settings
object, which is what makes it shareable: erp reads its ``ativos`` table,
social-wiring joins ``permuta_ativos`` against Vista-synced ``imoveis``, and
both hand over the same vocabulary:

    natureza          'imovel' | 'permuta_imovel' | 'permuta_automovel'
    valor             number
    estado/cidade/bairro/zona     strings
    tipo_imovel, quartos, vagas, area_total, area_privativa
    faixa_preco_min/max, metragem_min/max, quartos_min, vagas_min
    regiao_preferida  list[str]
    interesses        list[dict]  — see `_permuta_atende_interesse`
    aceita_permutas, aceita_completar_diferenca   bool
    titulo_anuncio, descricao_seo, fotos, tour_virtual_url,
    pontos_de_interesse, condominio_nome          — listing quality only
    embedding, embedding_interesses               list[float] | None

Anything absent is treated as unknown and scores zero for its category. That
is deliberate: a missing field must not fabricate compatibility.

THE SCORE
─────────
Hard filters run FIRST and are free — most pairs die there, and scoring a pair
that a gate would reject is the expensive mistake. Survivors get a 100-point
rule score:

    região 30 · preço 25 · specs 20 · interesses 15 · qualidade do anúncio 10

When BOTH sides carry BOTH vectors, bilateral similarity replaces the flat sum
with a composite that leads on meaning:

    40% semântica · 25% preço · 20% specs · 15% interesses

🔴 THE COMPOSITE IS WHY THIS EXISTS, AND IT HAS NEVER RUN IN PRODUCTION.
``erp.ativos`` carries ``embedding`` but not ``embedding_interesses`` —
migration ``012_bilateral_embeddings.sql`` was written and never applied — and
erp's ``_MATCHING_FIELDS`` does not SELECT that column either. Two independent
reasons :func:`calcular_bilateral_similarity` returns ``0.0`` on every pair, so
every match erp has ever produced is pure rule-based. A consumer that wants the
composite owes BOTH columns AND must select them; :func:`falta_vetor_bilateral`
exists so a caller can assert that rather than discover it as a silently
worse score.

Why it matters here: in the corpus this was promoted for, the structured
criteria are nearly empty (``cidade`` set on 0 of 135 legacy interest rows)
while the free text carries the real constraints — "casa sem escada", "rua do
condomínio sem ladeira", "quintal amplo". A rule score cannot read those. The
semantic half is not a refinement of this algorithm; it is the half that
answers the question.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "MIN_PRECO",
    "MIN_REGIAO",
    "MIN_SPECS",
    "SCORE_MINIMO_PADRAO",
    "SIM_THRESHOLD",
    "calcular_alinhamento_interesses",
    "calcular_bilateral_similarity",
    "calcular_compatibilidade_preco",
    "calcular_compatibilidade_regiao",
    "calcular_compatibilidade_specs",
    "calcular_qualidade_anuncio",
    "calcular_score_total",
    "falta_vetor_bilateral",
    "gerar_matches_para_imovel",
    "gerar_matches_para_permuta",
    "passa_filtros_minimos",
]

# Minimum a category must reach to count as "meaningful". Partial credit is
# easy to accumulate across three categories, so the gate below demands real
# signal in at least two rather than a total.
MIN_REGIAO = 5   # at least the same state
MIN_PRECO = 8    # near the band, or a decent value ratio
MIN_SPECS = 5    # at least a type or a bedroom-count match

#: Both directions must clear this before semantic similarity counts at all.
SIM_THRESHOLD = 0.60

#: The cutoff a match must reach to be emitted. erp's router has always passed
#: 45.0 explicitly; it is named here so a second consumer does not invent a
#: different one by accident.
SCORE_MINIMO_PADRAO = 45.0


def _lower(value: Any) -> str:
    """Comparable form of a possibly-missing string field.

    Every location comparison in this module is case-insensitive and
    NULL-tolerant, and writing that inline five times is how one of them ends
    up not being.
    """
    return (value or "").strip().lower() if isinstance(value, str) else ""


def _num(value: Any) -> float:
    """A number, or 0.0 for anything that is not one.

    The incoming dicts come from a database driver, so a numeric column can
    arrive as ``Decimal``, ``str`` or ``None`` depending on the client. A
    ``TypeError`` deep inside a scoring branch is a much worse failure than a
    zero, because it takes down a whole batch for one bad row.
    """
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def calcular_compatibilidade_regiao(imovel: dict, permuta: dict) -> int:
    """Location overlap. Max 30.

    Deliberately additive rather than hierarchical: same-bairro does not imply
    same-cidade in the data (bairro is frequently a condominium name, and
    ``cidade`` is blank on most legacy rows), so each level is scored on its
    own evidence.
    """
    score = 0

    if _lower(imovel.get("estado")) and _lower(imovel.get("estado")) == _lower(permuta.get("estado")):
        score += 5
    if _lower(imovel.get("cidade")) and _lower(imovel.get("cidade")) == _lower(permuta.get("cidade")):
        score += 10
    if _lower(imovel.get("bairro")) and _lower(imovel.get("bairro")) == _lower(permuta.get("bairro")):
        score += 10

    # A free-text region preference matched against the imóvel's own location
    # words. Substring, not equality: "Granja Viana" has to hit a bairro of
    # "Jardim Passargada - Granja Viana".
    regioes = permuta.get("regiao_preferida") or []
    if regioes:
        localizacao = " ".join(
            filter(None, [imovel.get("cidade") or "", imovel.get("estado") or "", imovel.get("bairro") or ""])
        ).lower()
        for regiao in regioes:
            if isinstance(regiao, str) and regiao.strip() and regiao.lower() in localizacao:
                score += 5
                break

    if _lower(imovel.get("zona")) and _lower(imovel.get("zona")) == _lower(permuta.get("zona")):
        score += 5

    return min(score, 30)


def calcular_compatibilidade_preco(imovel: dict, permuta: dict) -> int:
    """Price fit. Max 25.

    Two independent signals, deliberately summed: whether the imóvel falls in
    the band the permuta stated, AND how close the two headline values are. A
    permuta that stated no band still scores on the ratio, which is the common
    case — 53 of 135 legacy interest rows carry no ceiling at all.
    """
    valor_imovel = _num(imovel.get("valor"))
    if valor_imovel <= 0:
        # No price is not a cheap price. Scoring this as a perfect ratio would
        # float every unpriced listing to the top of every match list.
        return 0

    valor_permuta = _num(permuta.get("valor"))
    faixa_min = _num(permuta.get("faixa_preco_min"))
    faixa_max = _num(permuta.get("faixa_preco_max"))

    score = 0

    if faixa_min > 0 and faixa_max > 0:
        if faixa_min <= valor_imovel <= faixa_max:
            score += 15
        elif valor_imovel < faixa_min:
            if (faixa_min - valor_imovel) / faixa_min < 0.2:
                score += 8
        elif (valor_imovel - faixa_max) / faixa_max < 0.2:
            score += 8

    if valor_permuta > 0:
        ratio = min(valor_imovel, valor_permuta) / max(valor_imovel, valor_permuta)
        score += int(ratio * 10)

    # Willingness to pay the difference widens what counts as a fit, so it is
    # worth points on its own — but only three: it is a negotiating stance, not
    # a property attribute.
    if permuta.get("aceita_completar_diferenca"):
        score += 3

    return min(score, 25)


def calcular_compatibilidade_specs(imovel: dict, permuta: dict) -> int:
    """Property or vehicle specs. Max 20."""
    score = 0
    natureza = permuta.get("natureza", "")

    if natureza == "permuta_imovel":
        if (
            imovel.get("tipo_imovel")
            and permuta.get("tipo_imovel")
            and imovel["tipo_imovel"] == permuta["tipo_imovel"]
        ):
            score += 5

        # `quartos_min` is the stated floor; `quartos` is what they have, used
        # as a floor when no explicit minimum was given — someone swapping a
        # 3-bedroom rarely wants a 1-bedroom.
        quartos_imovel = _num(imovel.get("quartos"))
        quartos_min = _num(permuta.get("quartos_min")) or _num(permuta.get("quartos"))
        if quartos_min > 0 and quartos_imovel >= quartos_min:
            score += 5

        vagas_imovel = _num(imovel.get("vagas"))
        vagas_min = _num(permuta.get("vagas_min")) or _num(permuta.get("vagas"))
        if vagas_min > 0 and vagas_imovel >= vagas_min:
            score += 3

        area_imovel = _num(imovel.get("area_total")) or _num(imovel.get("area_privativa"))
        metragem_min = _num(permuta.get("metragem_min"))
        metragem_max = _num(permuta.get("metragem_max"))
        if metragem_min > 0 and area_imovel >= metragem_min:
            score += 4
        if metragem_max > 0 and area_imovel <= metragem_max:
            score += 3

    elif natureza == "permuta_automovel":
        # Vehicles are scored from the imóvel owner's stated interest, because
        # the imóvel row itself says nothing about cars.
        for interesse in imovel.get("interesses") or []:
            if interesse.get("tipo") != "automovel":
                continue
            if _lower(interesse.get("marca")) and _lower(interesse.get("marca")) == _lower(permuta.get("marca")):
                score += 10
            if _lower(interesse.get("modelo")) and _lower(interesse.get("modelo")) == _lower(permuta.get("modelo")):
                score += 5
            valor_min = _num(interesse.get("valor_min"))
            valor_max = _num(interesse.get("valor_max"))
            if valor_min <= _num(permuta.get("valor")) <= valor_max:
                score += 5
            break

    return min(score, 20)


def calcular_alinhamento_interesses(imovel: dict, permuta: dict) -> int:
    """Does what the permuta offers answer what the imóvel's owner asked for? Max 15."""
    interesses = imovel.get("interesses") or []
    if not interesses:
        return 0

    score = 0
    natureza = permuta.get("natureza", "")

    for interesse in interesses:
        tipo = interesse.get("tipo", "")
        if not (
            (tipo == "imovel" and natureza == "permuta_imovel")
            or (tipo == "automovel" and natureza == "permuta_automovel")
        ):
            continue

        score += 8
        if tipo == "imovel":
            if (
                interesse.get("tipo_imovel")
                and permuta.get("tipo_imovel")
                and interesse["tipo_imovel"] == permuta["tipo_imovel"]
            ):
                score += 4
            if _lower(interesse.get("cidade")) and _lower(interesse.get("cidade")) == _lower(permuta.get("cidade")):
                score += 3
        break

    return min(score, 15)


def calcular_qualidade_anuncio(imovel: dict) -> int:
    """How complete the listing is. Max 10.

    Not a compatibility signal — a tie-break. Between two equally compatible
    properties, the one a client can actually be shown wins, and this keeps a
    bare stub from outranking a fully photographed listing on a rounding
    difference.
    """
    score = 0
    if imovel.get("titulo_anuncio"):
        score += 2
    if imovel.get("descricao_seo"):
        score += 2

    fotos = imovel.get("fotos") or []
    if len(fotos) >= 3:
        score += 3
    elif len(fotos) >= 1:
        score += 1

    if imovel.get("tour_virtual_url"):
        score += 1
    if imovel.get("pontos_de_interesse"):
        score += 1
    if imovel.get("condominio_nome") or imovel.get("condominio_id"):
        score += 1

    return min(score, 10)


def _permuta_atende_interesse(permuta: dict, interesse: dict) -> bool:
    """Does what the permuta OFFERS satisfy one stated interest?

    Lenient by construction: only criteria the person actually filled in are
    checked. A blank field is "no preference", never "must be blank" — the
    legacy corpus has ``cidade`` empty on every single interest row, and
    treating that as a constraint would reject everything.
    """
    tipo = interesse.get("tipo", "")
    natureza = permuta.get("natureza", "")

    if tipo == "imovel" and natureza != "permuta_imovel":
        return False
    if tipo == "automovel" and natureza != "permuta_automovel":
        return False

    if tipo == "imovel":
        cidade_int, cidade_perm = _lower(interesse.get("cidade")), _lower(permuta.get("cidade"))
        if cidade_int and cidade_perm and cidade_int != cidade_perm:
            return False

        tipo_int, tipo_perm = _lower(interesse.get("tipo_imovel")), _lower(permuta.get("tipo_imovel"))
        if tipo_int and tipo_perm and tipo_int != tipo_perm:
            return False

        return _valor_na_faixa(_num(permuta.get("valor")), interesse)

    if tipo == "automovel":
        marca_int, marca_perm = _lower(interesse.get("marca")), _lower(permuta.get("marca"))
        if marca_int and marca_perm and marca_int != marca_perm:
            return False

        modelo_int, modelo_perm = _lower(interesse.get("modelo")), _lower(permuta.get("modelo"))
        if modelo_int and modelo_perm and modelo_int != modelo_perm:
            return False

        return _valor_na_faixa(_num(permuta.get("valor")), interesse)

    return True


def _valor_na_faixa(valor: float, interesse: dict) -> bool:
    """Is `valor` inside the interest's band, allowing 20% either side?

    The tolerance is the point. These ceilings are round numbers a person said
    out loud ("até 1,2 milhão"), not limits they would walk away over, and an
    exact bound turns a R$1.250.000 house into a non-match for someone who
    said 1,2M. 20% is what erp has always used.
    """
    valor_min = _num(interesse.get("valor_min"))
    valor_max = _num(interesse.get("valor_max"))
    if valor <= 0 or valor_min <= 0 or valor_max <= 0:
        return True
    return valor_min * 0.8 <= valor <= valor_max * 1.2


def _imovel_atende_permuta(imovel: dict, permuta: dict) -> bool:
    """The reverse direction — does the imóvel answer what the permuta wants?

    Two paths, in order of specificity. Explicit ``interesses`` win; otherwise
    the permuta's own search criteria (``faixa_preco_*``, ``regiao_preferida``)
    stand in. A permuta with neither wants anything, and passes.
    """
    interesses = permuta.get("interesses") or []
    if interesses:
        for interesse in interesses:
            if interesse.get("tipo") != "imovel":
                continue

            cidade_int, cidade_im = _lower(interesse.get("cidade")), _lower(imovel.get("cidade"))
            if cidade_int and cidade_im and cidade_int != cidade_im:
                continue

            tipo_int, tipo_im = _lower(interesse.get("tipo_imovel")), _lower(imovel.get("tipo_imovel"))
            if tipo_int and tipo_im and tipo_int != tipo_im:
                continue

            if not _valor_na_faixa(_num(imovel.get("valor")), interesse):
                continue

            return True
        return False

    valor_im = _num(imovel.get("valor"))
    faixa_min = _num(permuta.get("faixa_preco_min"))
    faixa_max = _num(permuta.get("faixa_preco_max"))
    if valor_im > 0 and faixa_min > 0 and faixa_max > 0:
        if not (faixa_min * 0.8 <= valor_im <= faixa_max * 1.2):
            return False

    regioes = permuta.get("regiao_preferida") or []
    if regioes:
        localizacao = " ".join(
            filter(None, [imovel.get("cidade") or "", imovel.get("bairro") or "", imovel.get("zona") or ""])
        ).lower()
        if not any(isinstance(r, str) and r.lower() in localizacao for r in regioes):
            return False

    return True


def passa_filtros_minimos(
    imovel: dict, permuta: dict, regiao: int, preco: int, specs: int
) -> bool:
    """The hard gate. False discards the pair before it is ever scored.

    Five rules, cheapest-and-most-decisive first:

      1. bilateral A→B — what the permuta offers must satisfy at least one of
         the imóvel owner's stated interests;
      2. bilateral B→A — the imóvel must satisfy what the permuta wants;
      3. property swaps must share at least a state;
      4. vehicle swaps require an explicit vehicle interest on the imóvel side;
      5. at least two of região/preço/specs must be meaningful.

    Rule 5 is the one that stops partial credit from manufacturing matches:
    5 + 8 + 0 clears a 45-point floor on nothing but "same state, roughly
    similar price", which is how a filter produces the 90% rejection rate the
    legacy funnel recorded.
    """
    natureza = permuta.get("natureza", "")
    interesses = imovel.get("interesses") or []

    if interesses and not any(_permuta_atende_interesse(permuta, i) for i in interesses):
        return False

    if not _imovel_atende_permuta(imovel, permuta):
        return False

    if natureza == "permuta_imovel":
        if regiao < MIN_REGIAO:
            return False
    elif natureza == "permuta_automovel":
        if not any(i.get("tipo") == "automovel" for i in interesses):
            return False

    meaningful = sum(
        (regiao >= MIN_REGIAO, preco >= MIN_PRECO, specs >= MIN_SPECS)
    )
    return meaningful >= 2


def falta_vetor_bilateral(imovel: dict, permuta: dict) -> bool:
    """True when the composite cannot run because a vector is missing.

    🔴 CALL THIS RATHER THAN INFERRING IT FROM A LOW SCORE. A pair with no
    embeddings still produces a perfectly plausible rule score, so the
    semantic half being absent is invisible in the output — which is exactly
    how erp shipped a dead composite path for months. A caller that intends to
    use embeddings should assert on this, log it, or surface it; what it must
    not do is quietly accept the weaker answer as the real one.
    """
    return not (
        imovel.get("embedding")
        and imovel.get("embedding_interesses")
        and permuta.get("embedding")
        and permuta.get("embedding_interesses")
    )


def calcular_bilateral_similarity(imovel: dict, permuta: dict) -> float:
    """Average of the two directional cosine similarities, or 0.0.

    B→A  cos(imovel.embedding,  permuta.embedding_interesses) — does the
         permuta WANT this imóvel?
    A→B  cos(permuta.embedding, imovel.embedding_interesses)  — does the
         imóvel's owner want what the permuta OFFERS?

    🔴 BOTH DIRECTIONS MUST CLEAR `SIM_THRESHOLD`, and the return is 0.0 if
    either fails — not the average, not the lower one. A swap is the one deal
    shape where one-sided enthusiasm is worth nothing: a property the owner
    would love, offered by someone who does not want theirs, is not a partial
    match. It is not a match.
    """
    if falta_vetor_bilateral(imovel, permuta):
        return 0.0

    sim_ba = _cosine(imovel["embedding"], permuta["embedding_interesses"])
    sim_ab = _cosine(permuta["embedding"], imovel["embedding_interesses"])

    if sim_ba < SIM_THRESHOLD or sim_ab < SIM_THRESHOLD:
        return 0.0

    return (sim_ba + sim_ab) / 2.0


def _cosine(a, b) -> float:
    """Cosine similarity of two vectors, 0.0 for a degenerate pair.

    Pure Python on purpose: this module is imported by every consumer of the
    seed lib, and pulling numpy in for a dot product would put a compiled
    dependency in the path of products that never score a match.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def calcular_score_total(imovel: dict, permuta: dict) -> Optional[dict]:
    """Score one pair. ``None`` means the hard gate rejected it.

    🔴 `None` IS NOT `0.0`. A rejected pair must never be persisted, not even
    as a zero — a stored zero reads as "we considered these and they are
    incompatible", which invites a UI to show it and a re-run to keep it
    alive. Rejected pairs simply do not exist.
    """
    regiao = calcular_compatibilidade_regiao(imovel, permuta)
    preco = calcular_compatibilidade_preco(imovel, permuta)
    specs = calcular_compatibilidade_specs(imovel, permuta)

    if not passa_filtros_minimos(imovel, permuta, regiao, preco, specs):
        return None

    interesses = calcular_alinhamento_interesses(imovel, permuta)
    qualidade = calcular_qualidade_anuncio(imovel)

    rule_score = float(regiao + preco + specs + interesses + qualidade)

    # Only computed for pairs that already survived the gate — embedding maths
    # on a pair nobody will see is the most expensive thing this module can do.
    similarity = calcular_bilateral_similarity(imovel, permuta)

    if similarity > 0:
        composite = (
            0.40 * (similarity * 100)
            + 0.25 * (preco / 25) * 100
            + 0.20 * (specs / 20) * 100
            + 0.15 * (interesses / 15) * 100
        )
        total = round(min(composite, 100.0), 1)
    else:
        total = rule_score

    partes = []
    if similarity >= 0.7:
        partes.append("Alta compatibilidade bilateral")
    elif similarity >= 0.5:
        partes.append("Boa compatibilidade bilateral")
    if regiao >= 15:
        partes.append("Boa compatibilidade de região")
    if preco >= 15:
        partes.append("Preço alinhado")
    if specs >= 10:
        partes.append("Características compatíveis")
    if interesses >= 8:
        partes.append("Alinhado com interesses")

    return {
        "score": total,
        "justificativa": ". ".join(partes) if partes else "Match parcial",
        "detalhes": {
            "compatibilidade_regiao": regiao,
            "compatibilidade_preco": preco,
            "compatibilidade_specs": specs,
            "alinhamento_interesses": interesses,
            "qualidade_anuncio": qualidade,
            "gap_valor": abs(_num(imovel.get("valor")) - _num(permuta.get("valor"))),
            "embedding_similarity": round(similarity, 4) if similarity > 0 else 0,
            # Recorded per pair so "why is this score low" is answerable from
            # the row itself, without re-running the scorer to find out that
            # the semantic half never ran.
            "semantica_disponivel": not falta_vetor_bilateral(imovel, permuta),
        },
        "score_breakdown": {
            "embedding_similarity": round(similarity * 100, 1) if similarity > 0 else 0,
            "compatibilidade_regiao": round((regiao / 30) * 100, 1),
            "compatibilidade_preco": round((preco / 25) * 100, 1),
            "compatibilidade_specs": round((specs / 20) * 100, 1),
            "qualidade_anuncio": round((qualidade / 10) * 100, 1),
            "interesses": round((interesses / 15) * 100, 1),
        },
    }


def _emitir(
    imovel: dict, permuta: dict, score_minimo: float
) -> Optional[dict]:
    """Score one oriented pair and shape it, or return None."""
    resultado = calcular_score_total(imovel, permuta)
    if resultado is None or resultado["score"] < score_minimo:
        return None
    return {
        # 🔴 ORIGEM IS ALWAYS THE IMÓVEL, DESTINO ALWAYS THE PERMUTA,
        # whichever direction the caller iterated from. A pair with two
        # representations defeats the unique index that makes a re-run an
        # upsert instead of a duplicate factory.
        "ativo_origem_id": imovel["id"],
        "ativo_destino_id": permuta["id"],
        **resultado,
    }


def gerar_matches_para_imovel(
    imovel: dict,
    permutas: list[dict],
    score_minimo: float = SCORE_MINIMO_PADRAO,
) -> list[dict]:
    """Every permuta worth showing against one listing, best first."""
    matches = []
    for permuta in permutas:
        # Someone's own property is not a swap partner for their other one.
        if permuta.get("owner_id") and permuta.get("owner_id") == imovel.get("owner_id"):
            continue
        if permuta.get("status", "ativo") != "ativo":
            continue
        emitido = _emitir(imovel, permuta, score_minimo)
        if emitido:
            matches.append(emitido)

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


def gerar_matches_para_permuta(
    permuta: dict,
    imoveis: list[dict],
    score_minimo: float = SCORE_MINIMO_PADRAO,
) -> list[dict]:
    """Every listing worth showing against one permuta, best first."""
    matches = []
    for imovel in imoveis:
        if imovel.get("owner_id") and imovel.get("owner_id") == permuta.get("owner_id"):
            continue
        # A listing whose owner has not said they accept a swap is not a
        # candidate, however well it scores.
        if not imovel.get("aceita_permutas"):
            continue
        if imovel.get("status", "ativo") != "ativo":
            continue
        emitido = _emitir(imovel, permuta, score_minimo)
        if emitido:
            matches.append(emitido)

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches
