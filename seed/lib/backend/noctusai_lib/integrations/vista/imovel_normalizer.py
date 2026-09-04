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
    normalize_place_name,
    parse_area,
    parse_caracteristicas,
    parse_corretores,
    parse_count,
    parse_date,
    parse_measure_int,
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
        # `bairro` deliberately stays `clean_text`, NOT `normalize_place_name`,
        # even though it is the same kind of field. The measured census
        # found zero collisions on `Bairro` — but "no collision measured" and
        # "cannot collide" are different claims, and `Bairro` is a long tail
        # (60+ distinct values on this tenant, vs 18 `Cidade` / a handful of
        # `Empreendimento`) that has never been diffed word-by-word against
        # this normalizer's output the way `cidade`/`empreendimento` were
        # here. Applying an unverified transform to an unverified field is
        # exactly the failure mode this fix is guarding against elsewhere
        # ("a rule that fixes 3 rows and breaks 30 is a worse bug than the
        # one you started with"). NOC-REMEDIATE[bairro-place-name-census]:
        # run the same before/after diff against every live `Bairro` value,
        # then apply `normalize_place_name` here too — 2026-08-13.
        bairro=clean_text(payload.get("Bairro")),
        cidade=normalize_place_name(payload.get("Cidade")),
        # Public docs say `Estado`; `oneconsu-rest` only exposes `UF`. Both,
        # for tenant portability — same fallback the showcase normalizer uses.
        uf=clean_text(payload.get("UF") or payload.get("Estado")),
        empreendimento=normalize_place_name(payload.get("Empreendimento")),
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
        # ── the 29-field expansion (CONTRACT `imoveis-vista-field-surface`
        # § 1, 32 minus the `Lavabo`/`Copa`/`Escritorio` shadowing
        # correction below). Each Vista key runs through the coercion class its
        # CONTRACT row names — text (`clean_text`), money/measure-float
        # (`parse_money` / `parse_area`, both "0"→None), measure-int
        # (`parse_measure_int`, "0"→None, int-typed), count (`parse_count`,
        # "0"→0 preserved), bool (`parse_sim_nao`, "Sim"/"Nao"/""→None).
        descricao_web=clean_text(payload.get("DescricaoWeb")),
        observacoes=clean_text(payload.get("Observacoes")),
        zona=clean_text(payload.get("Zona")),
        regiao=clean_text(payload.get("Regiao")),
        valor_condominio=parse_money(payload.get("ValorCondominio")),
        valor_iptu=parse_money(payload.get("ValorIptu")),
        area_terreno=parse_area(payload.get("AreaTerreno")),
        frente=parse_area(payload.get("Frente")),
        fundos=parse_area(payload.get("Fundos")),
        # No `lavabo` / `copa` / `escritorio` mapping — Vista shadows these
        # three to null whenever `Caracteristicas` is in the same request
        # (our sync always requests it). See
        # `calibration.py::CANDIDATE_IMOVEL_DETAIL_FIELDS` for the measured
        # probe. Read them via `imovel.tem_caracteristica("Lavabo")` etc.
        closet=parse_count(payload.get("Closet")),
        ano_construcao=parse_measure_int(payload.get("AnoConstrucao")),
        situacao=clean_text(payload.get("Situacao")),
        ocupacao=clean_text(payload.get("Ocupacao")),
        pavimentos=parse_count(payload.get("Pavimentos")),
        posicao=clean_text(payload.get("Posicao")),
        elevador=parse_sim_nao(payload.get("Elevador")),
        portaria=parse_sim_nao(payload.get("Portaria")),
        exclusivo=parse_sim_nao(payload.get("Exclusivo")),
        aceita_permuta=parse_sim_nao(payload.get("AceitaPermuta")),
        aceita_financiamento=parse_sim_nao(payload.get("AceitaFinanciamento")),
        chave=clean_text(payload.get("Chave")),
        exibir_no_site=parse_sim_nao(payload.get("ExibirNoSite")),
        destaque_web=parse_sim_nao(payload.get("DestaqueWeb")),
        super_destaque_web=parse_sim_nao(payload.get("SuperDestaqueWeb")),
        video_destaque=clean_text(payload.get("VideoDestaque")),
        tour_360=clean_text(payload.get("Tour360")),
        referencia=clean_text(payload.get("Referencia")),
        # 🔴 `matricula_vista`, NOT `matricula` — the product schema already
        # owns a cartório-authored `matricula` (migration 075). See the
        # `Imovel.matricula_vista` field docstring.
        matricula_vista=clean_text(payload.get("Matricula")),
        inscricao_municipal=clean_text(payload.get("InscricaoMunicipal")),
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
    """Normalize Vista's photo collection, which is dict-keyed like `Corretor`.

    🔴 **Structurally empty on `oneconsu-rest` — do NOT "fix" by deleting or
    faking this field.** `payload.get("Fotos")` reads a key this tenant
    never sends, which is why `fotos` is empty on all 2057 live rows —
    confirmed by direct probe, not by absence of data. Every photo-array
    candidate name was probed against `/imoveis/detalhes` 2026-09-04 and
    rejected with `400 "Campo X não está disponível"`: `Fotos`, `Foto`,
    `Imagens`, `Galeria`, `FotoGrande`, `FotoMedia`, `FotoPequena`,
    `Planta`. `/imoveis/fotos` is write-only (`405` on `GET`). The ONLY
    photo this tenant exposes is `FotoDestaque` (single URL, mapped to
    `Imovel.foto_destaque` above). See CONTRACT
    `imoveis-vista-field-surface` § 2 — this comment is the durable record
    so nobody re-investigates.
    """
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
