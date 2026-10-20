"""Julia's listing search: hard filters, widening, ranking. PURE -- rows in, rows out, no I/O.

`julia_ferramentas_service.buscar_imoveis` reads the Vista mirror (an explicit column allow-list) and hands
the rows here; nothing in this module touches a client, so every rule below is unit-testable on plain dicts.

THE RULES (julia-v2 RESEARCH 3, "Similarity")
  - Must-haves are HARD filters: operacao (done upstream), tipo, quartos_min, vagas_min, the price band, the
    region, and `itens_essenciais`. A listing missing a field a filter needs does NOT pass (unknown is not a match).
  - Items are standard option KEYS mapped to a catalogue predicate by `ITENS_PADRAO` (free text: folded substring).
    An item the catalogue CANNOT verify (pets, proximidades, terreo on a non-house) never filters and never ranks;
    it is returned in `itens_nao_verificaveis` for Julia to confirm with the lead / broker.
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


def norm(valor: Any) -> str:
    """Case- and accent-folded text, '' for anything that is not text."""
    if not isinstance(valor, str):
        return ""
    return " ".join(fold_accents(valor).casefold().split())


#: The standard `tipo_imovel` values agents sends (qualification standard v1 options) -> the Vista catalogue's
#: `categoria` vocabulary, as folded stems: (any of these, none of these). `casa` also takes the condominium house
#: (a lead who says "casa" has not excluded it); `casa_condominio` does not take the street house. Checked against
#: the live catalogue's categorias (2026-10-20): "Casa comercial" is commercial, never a home; "Área" is land.
TIPOS_PADRAO: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "casa": (("casa", "sobrado"), ("comercial",)),
    "casa_condominio": (("casa", "sobrado"), ("comercial",)),  # also requires "condominio" (see casa_tipo)
    "apartamento": (("apartamento", "cobertura", "flat", "studio", "kitnet", "loft"), ()),
    "terreno": (("terreno", "lote", "area"), ()),
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
    if chave in TIPOS_PADRAO:
        algum, nenhum = TIPOS_PADRAO[chave]
        if chave == "casa_condominio" and "condomin" not in cat:
            return False
        return any(x in cat for x in algum) and not any(x in cat for x in nenhum)
    return t in cat


def _chave(item: Any) -> str:
    """A standard option key as the map spells it ('Jardim quintal' -> 'jardim_quintal'); '' when not text."""
    return norm(item).replace(" ", "_")


def _compacto(c: str) -> str:
    return c.replace(" ", "").replace("_", "")


@dataclass(frozen=True)
class Recursos:
    """Feature predicate: some catalogue feature contains one of `algum` and none of `nenhum` (per FEATURE, so
    a listing with both `quintal` and `jardiminverno` still has a garden). Stems are compact folded text."""

    algum: tuple[str, ...]
    nenhum: tuple[str, ...] = ()


#: `pavimentos == 1` on a house; an apartment's floor count is the building's, so it is unverifiable there.
TERREO_CASA = "terreo_casa"

#: The standard `itens_essenciais` / `caracteristicas` / `itens_desejaveis` option KEYS agents sends (qualification
#: standard v1) -> how the Vista catalogue can verify them. Checked against the live `imoveis.caracteristicas`
#: vocabulary (2026-10-20: compact flags -- quintal, churrasqueira, sacadacomchurrasqueira, piscina, jardiminverno,
#: sacada, terraco, ...) and its columns (`pavimentos`; no pet field, no proximity data). `None` = the catalogue
#: CANNOT verify it: such an item never filters and never ranks, it is reported in `itens_nao_verificaveis` so
#: Julia confirms it with the lead / broker. A value that is not a key here keeps the folded-substring match.
ITENS_PADRAO: dict[str, Optional[Recursos | str]] = {
    # `jardiminverno` is an indoor winter garden, not a garden/yard
    "jardim_quintal": Recursos(("quintal", "jardim"), ("jardiminverno",)),
    "piscina": Recursos(("piscina",)),
    "churrasqueira": Recursos(("churrasqueira",)),  # includes sacadacomchurrasqueira
    "varanda": Recursos(("varanda", "sacada", "terraco")),
    "terreo_sem_escadas": TERREO_CASA,
    # no catalogue field
    "elevador": None, "portaria": None, "area_lazer": None,
    "pet": None, "pets": None, "aceita_pet": None, "aceita_pets": None, "animais": None, "aceita_animais": None,
    # proximidades: no proximity data in the catalogue
    "escola_perto": None, "comercio_perto": None, "acesso_rodovia": None, "transporte_publico": None,
    "comercio": None, "escolas": None, "rodovias": None, "transporte": None, "saude": None,
}


def avaliar_item(row: dict[str, Any], item: Any) -> Optional[bool]:
    """Does the listing have `item`? True / False, or None when the catalogue cannot tell (never a filter)."""
    chave = _chave(item)
    if not chave:
        return False
    if chave in ITENS_PADRAO:
        pred = ITENS_PADRAO[chave]
        if pred is None:
            return None
        if pred == TERREO_CASA:
            if not casa_tipo("casa", row.get("categoria")):
                return None
            pav = row.get("pavimentos")
            return pav is not None and pav == 1  # unknown is not a match
        return any(_atende(pred, c) for c in _carac(row))
    n = norm(item)
    return any(n in c for c in _carac(row))


def _atende(pred: Recursos, c: str) -> bool:
    cc = _compacto(c)
    return any(s in cc for s in pred.algum) and not any(s in cc for s in pred.nenhum)


def feature_atende(item: Any, feature: Any) -> bool:
    """Is this one catalogue feature string what `item` asks for? (Highlights: the lead's own items first.)"""
    chave, c = _chave(item), norm(feature)
    if not chave or not c:
        return False
    pred = ITENS_PADRAO.get(chave, "")
    if isinstance(pred, Recursos):
        return _atende(pred, c)
    if chave in ITENS_PADRAO:
        return False
    return norm(item) in c


def nao_verificaveis(q: "Consulta", linhas: Iterable[dict[str, Any]]) -> list[str]:
    """The asked items the catalogue could not verify, in ask order (must-haves first), deduped: an item with no
    predicate always; a field predicate (terreo) when it was unverifiable for a returned listing."""
    linhas = list(linhas)
    out: list[str] = []
    for item in (*q.essenciais, *q.desejaveis):
        chave = _chave(item)
        if not chave or chave in out or chave not in ITENS_PADRAO:
            continue
        pred = ITENS_PADRAO[chave]
        if pred is None or (pred == TERREO_CASA and any(avaliar_item(r, item) is None for r in linhas)):
            out.append(chave)
    return out


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
    #: asked items the catalogue cannot verify (never filtered / ranked by) -- Julia confirms them with the lead
    itens_nao_verificaveis: list[str] = field(default_factory=list)


def preco_da_linha(row: dict[str, Any], operacao: str) -> Optional[float]:
    v = row.get("valor_venda" if operacao == "compra" else "valor_locacao")
    return float(v) if v is not None else None


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
    # an item the catalogue cannot verify (None) never filters -- unknown-to-the-catalogue is not "absent"
    if any(avaliar_item(row, i) is False for i in q.essenciais):
        return False
    if q.desejaveis and not folgas.desejaveis:
        # nice-to-haves are a filter only while they are not relaxed: every verifiable one must be there
        if any(avaliar_item(row, i) is False for i in q.desejaveis):
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
    desejados = sum(1 for i in q.desejaveis if avaliar_item(row, i) is True)
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
    linhas = passam[:limite]
    return Resultado(linhas=linhas, relaxado=relaxado, restantes=max(len(passam) - limite, 0),
                     itens_nao_verificaveis=nao_verificaveis(q, linhas))
