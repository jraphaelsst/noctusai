"""Pure `response JSON -> CnpjRegistryFields` mappers, one per source.

No IO here — `real.py` owns the HTTP calls and the not-found/upstream-error
branching; these functions only ever see a JSON body that already parsed
and already looked like the expected shape (a `KeyError`/`TypeError` here
is `real.py`'s cue to raise `CnpjRegistryUpstreamError`, never something
this module hides).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from noctusai_lib.integrations.documents.situacao_cadastral import normalizar

from .types import CnpjRegistryFields

_DATA_BR_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})")


def _data_iso(texto: Optional[str]) -> Optional[date]:
    """BrasilAPI prints `data_situacao_cadastral` as `YYYY-MM-DD` (an ISO
    date, possibly with a time component this only ever takes the first
    10 characters of). `None` for blank/unparseable — never a guess."""
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10])
    except ValueError:
        return None


def _data_br(texto: Optional[str]) -> Optional[date]:
    """ReceitaWS prints `data_situacao` as `DD/MM/YYYY` — Brazil's usual
    written order, NOT ISO. `None` for blank/unparseable — never a guess."""
    if not texto:
        return None
    m = _DATA_BR_RE.match(texto.strip())
    if not m:
        return None
    dia, mes, ano = m.groups()
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


def parse_brasilapi_response(payload: dict[str, Any], cnpj: str) -> CnpjRegistryFields:
    """`GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}`'s 200 body ->
    `CnpjRegistryFields`. Fields probed live 2026-09-30: `razao_social`,
    `descricao_situacao_cadastral` (e.g. `"ATIVA"`), `data_situacao_
    cadastral` (`"2010-03-15"`)."""
    situacao_bruta = payload.get("descricao_situacao_cadastral")
    return CnpjRegistryFields(
        cnpj=cnpj,
        razao_social=(payload.get("razao_social") or None),
        situacao_cadastral=normalizar(situacao_bruta),
        situacao_cadastral_bruta=situacao_bruta,
        data_situacao_cadastral=_data_iso(payload.get("data_situacao_cadastral")),
        source="brasilapi",
        raw=payload,
    )


def parse_receitaws_response(payload: dict[str, Any], cnpj: str) -> CnpjRegistryFields:
    """`GET https://receitaws.com.br/v1/cnpj/{cnpj}`'s `status="OK"` body ->
    `CnpjRegistryFields`. Fields: `nome`, `situacao` (e.g. `"ATIVA"`),
    `data_situacao` — the Brazilian `DD/MM/YYYY` order, NOT ISO (see
    `_data_br`). `real.py` is the one that branches on `status` before
    calling this — this mapper only ever sees the success shape."""
    situacao_bruta = payload.get("situacao")
    return CnpjRegistryFields(
        cnpj=cnpj,
        razao_social=(payload.get("nome") or None),
        situacao_cadastral=normalizar(situacao_bruta),
        situacao_cadastral_bruta=situacao_bruta,
        data_situacao_cadastral=_data_br(payload.get("data_situacao")),
        source="receitaws",
        raw=payload,
    )


__all__ = ["parse_brasilapi_response", "parse_receitaws_response"]
