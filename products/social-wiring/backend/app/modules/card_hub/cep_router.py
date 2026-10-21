"""CEP lookup for the card's address form.

  GET /api/card-hub/cep/{cep}    -> {cep, logradouro, bairro, cidade, uf}  (404 when unresolved)

A thin HTTP face over the seed's `CepLookupAdapter` (ViaCEP, BrasilAPI
fallback) — the same adapter `identidade_extracao_service` already uses, via
the same `get_cep_lookup_adapter` DI seam (tests override it with the Fake).
Auth-gated: it proxies a third-party call on behalf of a logged-in operator.
Only the CEP (not personal data) is sent upstream; nothing is logged.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user_org
from app.modules.card_hub.deps import get_cep_lookup_adapter

router = APIRouter(tags=["cep"])

_CEP_8_DIGITOS = re.compile(r"^\d{8}$")


@router.get("/api/card-hub/cep/{cep}")
async def consultar_cep_route(
    cep: str,
    _auth=Depends(get_current_user_org),
    adapter=Depends(get_cep_lookup_adapter),
) -> dict:
    digitos = re.sub(r"\D", "", cep)
    if not _CEP_8_DIGITOS.match(digitos):
        raise HTTPException(status_code=400, detail="CEP deve ter 8 dígitos.")
    endereco = adapter.lookup(digitos)
    if endereco is None:
        raise HTTPException(status_code=404, detail="CEP não encontrado.")
    return {
        "cep": endereco.cep,
        "logradouro": endereco.logradouro,
        "bairro": endereco.bairro,
        "cidade": endereco.cidade,
        "uf": endereco.uf,
    }
