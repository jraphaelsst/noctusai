"""Vista payload → showcase DTO mappers.

Centralizing this in one place is a deliberate seam: a future migration
project will reuse these to seed `erp.ativos`, `erp.clientes`, etc. Don't
inline these into the service layer.

Vista quirks we deliberately defend against:
- Numeric fields come back as strings ("250000.00") or empty strings.
- `Caracteristicas` is a deeply nested object whose keys vary per property.
- `Foto` is missing on `/imoveis/detalhes` — pull from `/imoveis/listar`.
- Field names use Portuguese capitalization; preserve `raw` for debugging.
- The primary id (`Codigo`) is read from the payload, not from the dict
  key in `extract_items()` — the dict key may be alphanumeric or numeric.
"""
from __future__ import annotations

from typing import Any, Optional

from app.integrations.vista.types import (
    ShowcaseAgencia,
    ShowcaseImovel,
    ShowcaseImovelDetalhes,
    ShowcaseUsuario,
)


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "0", 0):
        # 0/'0' kept as None to keep "no data" distinct from "actually zero"
        # for valor/area fields. The raw payload preserves the literal value
        # for callers who need to disambiguate.
        return None if value in (None, "") else 0.0
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _first_corretor_nome(payload: dict) -> Optional[str]:
    """Vista returns `Corretor` as a dict keyed by corretor id:
    `{"103": {"Nome": "Fernanda", ...}, "104": {"Nome": "Elisa", ...}}`.
    The flat-shape `{"Nome": "..."}` only appears in some single-corretor
    payloads. Walk both shapes and return the first usable name.
    """
    corretor = payload.get("Corretor")
    if not isinstance(corretor, dict):
        return None
    direct = corretor.get("Nome")
    if isinstance(direct, str) and direct:
        return direct
    for value in corretor.values():
        if isinstance(value, dict):
            nome = value.get("Nome")
            if isinstance(nome, str) and nome:
                return nome
    return None


def vista_imovel_to_showcase(payload: dict) -> ShowcaseImovel:
    return ShowcaseImovel(
        codigo=str(payload.get("Codigo") or ""),
        titulo=_str_or_none(payload.get("TituloSite")),
        categoria=_str_or_none(payload.get("Categoria")),
        finalidade=_str_or_none(payload.get("Finalidade")),
        status=_str_or_none(payload.get("Status")),
        cidade=_str_or_none(payload.get("Cidade")),
        bairro=_str_or_none(payload.get("Bairro")),
        endereco=_str_or_none(payload.get("Endereco")),
        cep=_str_or_none(payload.get("CEP")),
        # Vista exposes the UF in either `UF` or `Estado` depending on the
        # tenant's permissioning — try both. On `oneconsu-rest` only `UF` works.
        estado=_str_or_none(payload.get("UF") or payload.get("Estado")),
        valor_venda=_to_float(payload.get("ValorVenda")),
        valor_locacao=_to_float(payload.get("ValorLocacao")),
        area_total=_to_float(payload.get("AreaTotal")),
        area_privativa=_to_float(payload.get("AreaPrivativa")),
        area_construida=_to_float(payload.get("AreaConstruida")),
        dormitorios=_to_int(payload.get("Dormitorios")),
        suites=_to_int(payload.get("Suites")),
        vagas=_to_int(payload.get("Vagas")),
        # `Banheiros` (aggregate) is denied on this tenant; `BanheiroSocial`
        # is what's exposed — fall through both so other tenants still work.
        banheiros=_to_int(payload.get("Banheiros") or payload.get("BanheiroSocial")),
        foto_url=_str_or_none(payload.get("Foto") or payload.get("FotoDestaque")),
        latitude=_to_float(payload.get("Latitude")),
        longitude=_to_float(payload.get("Longitude")),
        data_atualizacao=_str_or_none(payload.get("DataAtualizacao")),
        corretor_nome=_first_corretor_nome(payload),
        raw=payload,
    )


def vista_imovel_detalhes_to_showcase(
    detalhes_payload: dict,
    *,
    listing_payload: Optional[dict] = None,
) -> ShowcaseImovelDetalhes:
    """Compose detail view from /imoveis/detalhes + (optionally) the
    matching /imoveis/listar row, since `Foto` is unavailable on detalhes.
    """
    base_payload = {**(listing_payload or {}), **detalhes_payload}
    if listing_payload and listing_payload.get("Foto") and not detalhes_payload.get("Foto"):
        base_payload["Foto"] = listing_payload["Foto"]
    base = vista_imovel_to_showcase(base_payload)
    caracteristicas = detalhes_payload.get("Caracteristicas") or {}
    if not isinstance(caracteristicas, dict):
        caracteristicas = {}
    return ShowcaseImovelDetalhes(
        codigo=base.codigo,
        base=base,
        caracteristicas=caracteristicas,
        raw=detalhes_payload,
    )


def vista_usuario_to_showcase(payload: dict) -> ShowcaseUsuario:
    return ShowcaseUsuario(
        codigo=str(payload.get("Codigo") or ""),
        nome=_str_or_none(payload.get("Nome")),
        email=_str_or_none(payload.get("Email")),
        setor=_str_or_none(payload.get("Setor")),
        foto_url=_str_or_none(payload.get("Foto")),
        raw=payload,
    )


def vista_agencia_to_showcase(payload: dict) -> ShowcaseAgencia:
    return ShowcaseAgencia(
        codigo=str(payload.get("Codigo") or ""),
        nome=_str_or_none(payload.get("Nome")),
        endereco=_str_or_none(payload.get("Endereco")),
        cidade=_str_or_none(payload.get("Cidade")),
        bairro=_str_or_none(payload.get("Bairro")),
        site=_str_or_none(payload.get("Site")),
        raw=payload,
    )
