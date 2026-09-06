"""Request bodies for the permutas module.

`StrictHttpModel` forbids unknown keys, so a typo in a field name is a 422 at
the boundary rather than a silently ignored value — which matters more than
usual here, because a dropped `valor_maximo` does not fail, it just widens
what the engine will match.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from noctusai_lib.api import StrictHttpModel
from pydantic import Field


class InteresseBody(StrictHttpModel):
    """One thing an ativo will accept in exchange."""

    tipo: str = "imovel"
    tipo_imovel: Optional[str] = None
    zona: Optional[str] = None
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    valor_minimo: Optional[float] = None
    valor_maximo: Optional[float] = None
    # The proportion of the deal the swap should cover. See migration 101 —
    # "estuda permuta de 30% a 50%" is the single most common thing written in
    # these notes, and the legacy schema had nowhere to put it.
    percentual_min: Optional[int] = Field(default=None, ge=0, le=100)
    percentual_max: Optional[int] = Field(default=None, ge=0, le=100)
    marca: Optional[str] = None
    modelo: Optional[str] = None
    ano_min: Optional[int] = None
    ano_max: Optional[int] = None
    observacoes: Optional[str] = None


class AtivoCreateBody(StrictHttpModel):
    """Register a swap intent."""

    natureza: str
    # Required when natureza == 'imovel'; the service raises a readable 400
    # rather than letting the DB CHECK surface as a constraint name.
    imovel_codigo: Optional[str] = None
    codigo: Optional[str] = None
    corretor_id: Optional[UUID] = None

    proprietario_nome: Optional[str] = None
    proprietario_telefone: Optional[str] = None
    proprietario_email: Optional[str] = None

    tipo_imovel: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    zona: Optional[str] = None
    condominio_nome: Optional[str] = None

    valor: Optional[float] = None
    area_total: Optional[float] = None
    area_privativa: Optional[float] = None
    quartos: Optional[int] = None
    suites: Optional[int] = None
    vagas: Optional[int] = None

    faixa_preco_min: Optional[float] = None
    faixa_preco_max: Optional[float] = None
    regiao_preferida: Optional[list[str]] = None
    aceita_completar_diferenca: Optional[bool] = None
    limite_complemento: Optional[float] = None
    percentual_min: Optional[int] = Field(default=None, ge=0, le=100)
    percentual_max: Optional[int] = Field(default=None, ge=0, le=100)

    observacoes: Optional[str] = None
    status: Optional[str] = None

    interesses: Optional[list[InteresseBody]] = None


class AtivoPatchBody(AtivoCreateBody):
    """Patch a swap intent.

    `natureza` is optional on a patch — inherited as required from the create
    body, so it is re-declared. Changing it is allowed but rare; what it must
    not be is silently required on every edit.
    """

    natureza: Optional[str] = None


class GerarMatchesBody(StrictHttpModel):
    """Run the engine. No `ativo_id` means a full scan."""

    ativo_id: Optional[UUID] = None
    # Exposed rather than fixed at the lib default so the page can loosen the
    # floor when a scan returns nothing — with 14 offers against 135 intents,
    # "no matches" is a plausible real answer and being able to see the
    # near-misses is how you tell that apart from a broken projection.
    score_minimo: Optional[float] = Field(default=None, ge=0, le=100)


class EmbutirBody(StrictHttpModel):
    """Generate the two vectors for the org's ativos."""

    apenas_pendentes: bool = True
    ativo_ids: Optional[list[UUID]] = None


class EtapaPatchBody(StrictHttpModel):
    """Move a match through the funnel."""

    etapa: str
    observacoes: Optional[str] = None


__all__ = [
    "AtivoCreateBody",
    "AtivoPatchBody",
    "EmbutirBody",
    "EtapaPatchBody",
    "GerarMatchesBody",
    "InteresseBody",
]
