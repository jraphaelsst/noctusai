"""Vista payload → showcase DTO mappers — canonical platform implementation.

See `KB § INTEGRATIONS/vista.md § 5.2` for the full normalizer field-mapping
contract — every Vista key, every type-coercion rule, every per-tenant
fallback chain.

Vista quirks defended against:
- Numeric fields come back as strings (`"250000.00"`) or empty strings.
- `Caracteristicas` is a deeply nested object whose keys vary per property.
- `Foto` is missing on `/imoveis/detalhes` — pull from `/imoveis/listar`.
- `Estado` ‖ `UF`, `Banheiros` ‖ `BanheiroSocial`, `Foto` ‖ `FotoDestaque`
  fallbacks because per-tenant permissions vary.
- `Corretor` is dict-keyed-by-id on most tenants but flat on some.
"""
from __future__ import annotations

from typing import Any, Optional

from .types import (
    ShowcaseAgencia,
    ShowcaseImovel,
    ShowcaseImovelDetalhes,
    ShowcaseUsuario,
)


# ─── Type coercion helpers ───────────────────────────────────────────────


def _to_float(value: Any) -> Optional[float]:
    """Empty/None → None. 0/'0' → 0.0. Comma decimal separator normalized."""
    if value in (None, "", "0", 0):
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
    """Walk both flat and dict-keyed-by-id Corretor shapes; return first usable name.

    Vista returns `Corretor` as a dict keyed by corretor id on most tenants:
      `{"103": {"Nome": "Fernanda", ...}, "104": {"Nome": "Elisa", ...}}`.
    A flat shape `{"Nome": "..."}` appears on some single-corretor payloads.
    Returns ONLY the first matched name — not a list.
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


# ─── Payload mappers ─────────────────────────────────────────────────────


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
        # Per-tenant fallback (vista.md § 5.2): public docs say `Estado`,
        # `oneconsu-rest` only exposes `UF`.
        estado=_str_or_none(payload.get("UF") or payload.get("Estado")),
        valor_venda=_to_float(payload.get("ValorVenda")),
        valor_locacao=_to_float(payload.get("ValorLocacao")),
        area_total=_to_float(payload.get("AreaTotal")),
        area_privativa=_to_float(payload.get("AreaPrivativa")),
        area_construida=_to_float(payload.get("AreaConstruida")),
        dormitorios=_to_int(payload.get("Dormitorios")),
        suites=_to_int(payload.get("Suites")),
        vagas=_to_int(payload.get("Vagas")),
        # `Banheiros` (count) is denied on `oneconsu-rest`; `BanheiroSocial`
        # is what's exposed there. Try both for tenant portability.
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
    """Compose detail view from /imoveis/detalhes + (optionally) the matching
    /imoveis/listar row, since `Foto` is unavailable on detalhes.

    Merge strategy: `{**listing, **detalhes}` (detail wins). Plus a special
    `Foto` override: if listing has it and detalhes doesn't, listing wins.
    See vista.md § 4.1 (`/imoveis/detalhes` quirks).
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


__all__ = [
    "vista_imovel_to_showcase",
    "vista_imovel_detalhes_to_showcase",
    "vista_usuario_to_showcase",
    "vista_agencia_to_showcase",
]
