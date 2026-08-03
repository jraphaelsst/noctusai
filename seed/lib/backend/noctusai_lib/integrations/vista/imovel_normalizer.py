"""Vista payload → canonical `Imovel`.

Separate from `normalizers.py` on purpose: that module maps to the
`Showcase*` DTOs, which are a *presentation* shape for the ERP showcase and
the MCP tool surface. This one maps to the canonical domain model.

**The listar/detalhes asymmetry is the load-bearing fact.** The two
endpoints return overlapping-but-different key sets — measured at 27 vs 30
keys, holding on 75/75 sampled imóveis:

- listar-only:   ``FotoDestaque``, ``BanheiroSocial``, ``CodigoImobiliaria``,
                 ``Corretor_Codigo``
- detalhes-only: ``Caracteristicas``, ``Numero``, ``Complemento``,
                 ``Empreendimento``, ``Construtora``, ``FinalidadeStatus``,
                 ``DataAtualizacaoDias``

So a complete `Imovel` needs BOTH calls, and neither is a superset of the
other. `vista_to_imovel` therefore takes both and merges — listar first,
detalhes overlaid — rather than pretending either alone is sufficient.
Calling it with only a listar row is legal and yields a partial imóvel
(no amenities, no finalidade from `FinalidadeStatus`); that is the
documented trade-off of a listar-only sync, not a bug.
"""

from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain.real_estate.imovel import (
    Imovel,
    clean_text,
    derive_finalidades,
    parse_area,
    parse_caracteristicas,
    parse_corretores,
    parse_count,
    parse_date,
    parse_money,
    parse_sim_nao,
)


def merge_vista_payloads(
    listing: Optional[dict] = None, detalhes: Optional[dict] = None
) -> dict:
    """Merge a listar row and a detalhes payload into one dict.

    Detalhes wins on conflict — it is the richer, per-imóvel call — EXCEPT
    that a detalhes value which is absent/blank never overwrites a populated
    listar value. Without that guard the merge would erase `FotoDestaque`
    and `BanheiroSocial` (listar-only fields) on every imóvel.
    """
    merged: dict = dict(listing or {})
    for key, value in (detalhes or {}).items():
        if value in (None, ""):
            if key in merged:
                continue
        merged[key] = value
    return merged


def vista_to_imovel(
    listing: Optional[dict] = None, detalhes: Optional[dict] = None
) -> Imovel:
    """Build a canonical `Imovel` from either or both Vista payloads.

    Raises `ValueError` when neither payload carries a `Codigo` — an imóvel
    with no identity is not a partial record, it is a broken one, and
    silently returning a blank model would push the failure downstream.
    """
    payload = merge_vista_payloads(listing, detalhes)

    codigo = clean_text(payload.get("Codigo"))
    if not codigo:
        raise ValueError(
            "vista_to_imovel: payload carries no `Codigo` — cannot build an Imovel "
            f"(keys seen: {sorted(payload)[:12]})"
        )

    return Imovel(
        codigo=codigo,
        codigo_imobiliaria=clean_text(payload.get("CodigoImobiliaria")),
        titulo=clean_text(payload.get("TituloSite") or payload.get("Titulo")),
        categoria=clean_text(payload.get("Categoria")),
        status=clean_text(payload.get("Status")),
        finalidades=derive_finalidades(
            finalidade_status=payload.get("FinalidadeStatus"),
            status=payload.get("Status"),
            finalidade=payload.get("Finalidade"),
        ),
        cep=clean_text(payload.get("CEP")),
        logradouro=clean_text(payload.get("Endereco")),
        numero=clean_text(payload.get("Numero")),
        complemento=clean_text(payload.get("Complemento")),
        bairro=clean_text(payload.get("Bairro")),
        cidade=clean_text(payload.get("Cidade")),
        # Public docs say `Estado`; `oneconsu-rest` only exposes `UF`. Both,
        # for tenant portability — same fallback the showcase normalizer uses.
        uf=clean_text(payload.get("UF") or payload.get("Estado")),
        empreendimento=clean_text(payload.get("Empreendimento")),
        latitude=_coord(payload.get("Latitude")),
        longitude=_coord(payload.get("Longitude")),
        valor_venda=parse_money(payload.get("ValorVenda")),
        valor_locacao=parse_money(payload.get("ValorLocacao")),
        area_total=parse_area(payload.get("AreaTotal")),
        area_privativa=parse_area(payload.get("AreaPrivativa")),
        area_construida=parse_area(payload.get("AreaConstruida")),
        dormitorios=parse_count(payload.get("Dormitorios")),
        suites=parse_count(payload.get("Suites")),
        vagas=parse_count(payload.get("Vagas")),
        banheiro_social=parse_sim_nao(payload.get("BanheiroSocial")),
        foto_destaque=clean_text(payload.get("FotoDestaque") or payload.get("Foto")),
        fotos=_photo_list(payload.get("Fotos")),
        corretores=parse_corretores(payload.get("Corretor")),
        construtora=clean_text(payload.get("Construtora")),
        data_cadastro=parse_date(payload.get("DataCadastro")),
        data_atualizacao=parse_date(payload.get("DataAtualizacao")),
        data_atualizacao_dias=parse_count(payload.get("DataAtualizacaoDias")),
        caracteristicas=parse_caracteristicas(payload.get("Caracteristicas")),
        caracteristicas_raw=payload.get("Caracteristicas") or {},
        vista_raw=payload,
    )


def _coord(value: Any) -> Optional[float]:
    """Latitude/longitude — blank on 36.8% of the catalog, so `None` is normal.

    Unlike money and area, ``0`` is NOT special-cased here: the equator and
    the prime meridian are real coordinates. Blank is the only absent state.
    """
    text = clean_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _photo_list(value: Any) -> list[str]:
    """Normalize Vista's photo collection, which is dict-keyed like `Corretor`."""
    if isinstance(value, dict):
        entries: Any = value.values()
    elif isinstance(value, list):
        entries = value
    else:
        return []
    out: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            url = clean_text(entry)
        elif isinstance(entry, dict):
            url = clean_text(entry.get("Foto") or entry.get("FotoGrande") or entry.get("URL"))
        else:
            url = None
        if url:
            out.append(url)
    return out


__all__ = ["merge_vista_payloads", "vista_to_imovel"]
