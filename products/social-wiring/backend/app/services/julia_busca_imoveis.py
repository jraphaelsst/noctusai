"""Julia's listing search: hard filters, widening, ranking. PURE -- rows in, rows out, no I/O.

`julia_ferramentas_service.buscar_imoveis` reads the Vista mirror (an explicit column allow-list) and hands
the rows here; nothing in this module touches a client, so every rule below is unit-testable on plain dicts.

THE RULES (julia-v2 RESEARCH 3, "Similarity")
  - Must-haves are HARD filters: operacao (done upstream), tipo, quartos_min, vagas_min, the price band, the
    region, and `itens_essenciais`. A listing missing a field a filter needs does NOT pass (unknown is not a match).
  - Price band = -15% / +10% of the lead's range (`preco_min * 0.85` .. `preco_max * 1.10`).
  - Same condominio first, then same region, then adjacent regions (org-configured; none when unconfigured).
  - Ranked by matched nice-to-haves, then by the SEED matcher's category scores
    (`noctusai_lib.domain.real_estate.matching.calcular_compatibilidade_{regiao,preco,specs}`) -- the ranker is
    the seed's, not a new one.

WIDENING (fewer than `limite` results): relax ONE axis at a time, cumulatively, in this fixed order, stopping
as soon as enough listings pass, and name every axis that was relaxed so Julia can say what was widened:

    1. desejaveis          the nice-to-haves stop ranking-and-filtering (`itens_desejaveis` + `caracteristicas`)
    2. regiao_adjacente    the region set grows by the org's adjacent regions
    3. preco               the upper bound goes from +10% to +20% of `preco_max`
    4. tipologia           `tipo` is dropped and `quartos_min` lowered by one

An axis with nothing to relax (no nice-to-haves, no adjacent regions configured, no price ceiling, no tipo and
no quartos_min), or one the result did not need, is skipped and NOT reported. `must-haves` (`itens_essenciais`, `vagas_min`, the price floor)
are never relaxed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional

from noctusai_lib.domain.real_estate import matching
from noctusai_lib.primitives.accents import fold_accents

BANDA_PRECO_ABAIXO = 0.85
BANDA_PRECO_ACIMA = 1.10
BANDA_PRECO_ACIMA_LARGA = 1.20
ORDEM_AFROUXAMENTO = ("desejaveis", "regiao_adjacente", "preco", "tipologia")
#: `itens_essenciais` that name a policy, not a feature: matched against the listing's feature list by these stems.
SINONIMOS = {
    "pet": ("pet", "animal", "animais"), "pets": ("pet", "animal", "animais"),
    "aceita pet": ("pet", "animal", "animais"), "aceita pets": ("pet", "animal", "animais"),
    "animais": ("pet", "animal", "animais"), "aceita animais": ("pet", "animal", "animais"),
}


def norm(valor: Any) -> str:
    """Case- and accent-folded text, '' for anything that is not text."""
    if not isinstance(valor, str):
        return ""
    return " ".join(fold_accents(valor).casefold().split())


#: The standard `tipo_imovel` values agents sends (qualification standard v1 options) -> the Vista catalogue's
#: `categoria` vocabulary, as folded stems: (any of these, none of these). `casa` also takes the condominium house
#: (a lead who says "casa" has not excluded it); `casa_condominio` does not take the street house.
TIPOS_PADRAO: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "casa": (("casa", "sobrado"), ()),
    "casa_condominio": (("casa", "sobrado"), ()),  # also requires "condominio" in the categoria (see casa_tipo)
    "apartamento": (("apartamento", "cobertura", "flat", "studio", "kitnet", "loft"), ()),
    "terreno": (("terreno", "lote"), ()),
    "comercial": (("comercial", "sala", "loja", "galpao", "conjunto"), ()),
}


def casa_tipo(tipo: Optional[str], categoria: Any) -> bool:
    """Does the listing's catalogue `categoria` satisfy the requested `tipo`? A standard value is mapped through
    TIPOS_PADRAO; anything else (e.g. a free "Casa em Condominio" taken from a campaign listing) is a folded substring."""
    cat = norm(categoria)
    t = norm(tipo)
    if not t:
        return True
    chave = t.replace(" ", "_")
    if chave == "casa_condominio":
        return "condomin" in cat and any(x in cat for x in TIPOS_PADRAO["casa"][0])
    if chave in TIPOS_PADRAO:
        return any(x in cat for x in TIPOS_PADRAO[chave][0])
    return t in cat


@dataclass(frozen=True)
class Consulta:
    operacao: str  # compra | aluguel
    tipo: Optional[str] = None
    preco_min: Optional[float] = None
    preco_max: Optional[float] = None
    quartos_min: Optional[int] = None
    vagas_min: Optional[int] = None
    regioes: tuple[str, ...] = ()
    cidade: Optional[str] = None
    essenciais: tuple[str, ...] = ()
    desejaveis: tuple[str, ...] = ()
    condominio: Optional[str] = None  # the anchor listing's empreendimento: ranks first, never filters
    #: normalised region -> normalised adjacent regions (org-configured; empty = none)
    adjacentes: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Folgas:
    desejaveis: bool = False
    regiao_adjacente: bool = False
    preco: bool = False
    tipologia: bool = False


@dataclass(frozen=True)
class Resultado:
    linhas: list[dict[str, Any]]  # at most `limite`, best first
    relaxado: list[str]
    restantes: int


def preco_da_linha(row: dict[str, Any], operacao: str) -> Optional[float]:
    v = row.get("valor_venda" if operacao == "compra" else "valor_locacao")
    return float(v) if v is not None else None


def _tem_item(caracteristicas: Iterable[str], item: str) -> bool:
    n = norm(item)
    if not n:
        return False
    stems = SINONIMOS.get(n, (n,))
    return any(any(s in c for s in stems) for c in caracteristicas)


def _carac(row: dict[str, Any]) -> list[str]:
    return [norm(c) for c in (row.get("caracteristicas") or []) if isinstance(c, str)]


def _regioes_efetivas(q: Consulta, folgas: Folgas) -> tuple[set[str], set[str]]:
    base = {norm(r) for r in q.regioes if norm(r)}
    extra: set[str] = set()
    if folgas.regiao_adjacente:
        for r in base:
            extra.update(q.adjacentes.get(r, ()))
    return base, extra - base


def _casa_regiao(row: dict[str, Any], regioes: set[str]) -> bool:
    alvo = f"{norm(row.get('bairro'))} | {norm(row.get('empreendimento'))}"
    return any(r in alvo for r in regioes)


def _limites_preco(q: Consulta, folgas: Folgas) -> tuple[Optional[float], Optional[float]]:
    lo = q.preco_min * BANDA_PRECO_ABAIXO if q.preco_min else None
    fator = BANDA_PRECO_ACIMA_LARGA if folgas.preco else BANDA_PRECO_ACIMA
    hi = q.preco_max * fator if q.preco_max else None
    return lo, hi


def teto_largo(q: Consulta) -> Optional[float]:
    """The widest upper price bound any widening step can reach (the SQL pre-filter uses it)."""
    return q.preco_max * BANDA_PRECO_ACIMA_LARGA if q.preco_max else None


def piso(q: Consulta) -> Optional[float]:
    return q.preco_min * BANDA_PRECO_ABAIXO if q.preco_min else None


def quartos_minimos_largos(q: Consulta) -> Optional[int]:
    return None if q.quartos_min is None else max(q.quartos_min - 1, 0)


def passa(row: dict[str, Any], q: Consulta, folgas: Folgas) -> bool:
    if q.cidade and norm(q.cidade) not in norm(row.get("cidade")):
        return False
    base, extra = _regioes_efetivas(q, folgas)
    if base and not _casa_regiao(row, base | extra):
        return False
    if q.tipo and not folgas.tipologia and not casa_tipo(q.tipo, row.get("categoria")):
        return False
    quartos_min = q.quartos_min
    if quartos_min is not None and folgas.tipologia:
        quartos_min = max(quartos_min - 1, 0)
    if quartos_min is not None and (row.get("dormitorios") is None or row["dormitorios"] < quartos_min):
        return False
    if q.vagas_min is not None and (row.get("vagas") is None or row["vagas"] < q.vagas_min):
        return False
    lo, hi = _limites_preco(q, folgas)
    if lo is not None or hi is not None:
        preco = preco_da_linha(row, q.operacao)
        if preco is None or (lo is not None and preco < lo) or (hi is not None and preco > hi):
            return False
    carac = _carac(row)
    if not all(_tem_item(carac, i) for i in q.essenciais):
        return False
    if q.desejaveis and not folgas.desejaveis:
        # nice-to-haves are a filter only while they are not relaxed: every one must be there
        if not all(_tem_item(carac, i) for i in q.desejaveis):
            return False
    return True


def _aplicavel(eixo: str, q: Consulta) -> bool:
    if eixo == "desejaveis":
        return bool(q.desejaveis)
    if eixo == "regiao_adjacente":
        return any(q.adjacentes.get(norm(r)) for r in q.regioes)
    if eixo == "preco":
        return bool(q.preco_max)
    return bool(q.tipo) or bool(q.quartos_min)


def _pontuar(row: dict[str, Any], q: Consulta, folgas: Folgas) -> tuple:
    """Sort key (ascending = better). Tier: same condominio < same region < adjacent < unconstrained region."""
    base, _ = _regioes_efetivas(q, folgas)
    if q.condominio and norm(q.condominio) and norm(q.condominio) == norm(row.get("empreendimento")):
        tier = 0
    elif base and _casa_regiao(row, base):
        tier = 1
    elif base:
        tier = 2
    else:
        tier = 3
    carac = _carac(row)
    desejados = sum(1 for i in q.desejaveis if _tem_item(carac, i))
    preco = preco_da_linha(row, q.operacao)
    alvo = ((q.preco_min or 0) + (q.preco_max or 0)) / 2 if (q.preco_min or q.preco_max) else None
    imovel = {
        "estado": row.get("uf"), "cidade": row.get("cidade"), "bairro": row.get("bairro"), "valor": preco,
        "tipo_imovel": norm(row.get("categoria")), "quartos": row.get("dormitorios"), "vagas": row.get("vagas"),
        "area_total": row.get("area_total") or row.get("area_privativa"),
    }
    desejo = {
        "natureza": "permuta_imovel", "cidade": q.cidade, "regiao_preferida": list(q.regioes), "valor": alvo,
        "faixa_preco_min": q.preco_min, "faixa_preco_max": q.preco_max, "tipo_imovel": norm(q.tipo),
        "quartos_min": q.quartos_min, "vagas_min": q.vagas_min,
    }
    score = (
        matching.calcular_compatibilidade_regiao(imovel, desejo)
        + matching.calcular_compatibilidade_preco(imovel, desejo)
        + matching.calcular_compatibilidade_specs(imovel, desejo)
    )
    return (tier, -desejados, -score, str(row.get("codigo")))


def buscar(rows: list[dict[str, Any]], q: Consulta, *, limite: int, excluir: Iterable[str] = ()) -> Resultado:
    """Hard-filter, widen one axis at a time until `limite` pass, rank, cap."""
    fora = {str(c).strip().upper() for c in excluir}
    candidatos = [r for r in rows if str(r.get("codigo") or "").strip().upper() not in fora]
    folgas = Folgas()
    aplicados: list[str] = []
    passam = [r for r in candidatos if passa(r, q, folgas)]
    for eixo in ORDEM_AFROUXAMENTO:
        if len(passam) >= limite:
            break
        if not _aplicavel(eixo, q):
            continue
        folgas = replace(folgas, **{eixo: True})
        aplicados.append(eixo)
        passam = [r for r in candidatos if passa(r, q, folgas)]
    # Report only the axes the result actually NEEDED: un-relaxing an axis must lose at least one listing. (An
    # axis that was tried and added nothing is not "widened"; axes that are only useful together all show up.)
    relaxado = [
        e for e in aplicados
        if sum(1 for r in candidatos if passa(r, q, replace(folgas, **{e: False}))) < len(passam)
    ]
    passam.sort(key=lambda r: _pontuar(r, q, folgas))
    return Resultado(linhas=passam[:limite], relaxado=relaxado, restantes=max(len(passam) - limite, 0))
