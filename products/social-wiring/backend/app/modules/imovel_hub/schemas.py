"""Request bodies for `/api/imoveis/{codigo}/...`.

`StrictHttpModel` (house default) rejects unknown keys, so a typo'd field is
a 422 naming it rather than a silently-ignored value.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class ImovelDadosPatchBody(StrictHttpModel):
    """The cartório fields a human may set.

    Every field is Optional AND nullable, and absence is what means "leave
    alone" — `None` is a real value, because clearing a wrongly-typed
    matrícula number has to be possible. `model_fields_set` is what the
    service reads, never `is None`.
    """

    numero_matricula: Optional[str] = Field(default=None, max_length=64)
    #: Migration 099. Free TEXT rather than a Literal over
    #: `dados_service.SITUACOES_ONUS`: the rules that consume this are
    #: deliberately not decided yet, and pinning the vocabulary at the HTTP
    #: boundary would make the first new value a schema change in two places.
    #: The UI offers the tuple; this accepts what the UI sends.
    situacao_onus: Optional[str] = Field(default=None, max_length=64)
    onus_observacoes: Optional[str] = Field(default=None, max_length=4000)
    onus_certidao_em: Optional[date] = None
    onus_documento_id: Optional[UUID] = None
    #: 200, not 64: the value is the cartório's full name as the certidão
    #: heading prints it ("OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE SÃO
    #: PAULO/SP"), which migration 154's extraction now fills — a human must
    #: be able to save back what the machine wrote.
    numero_registro_imoveis: Optional[str] = Field(default=None, max_length=200)
    prefeitura_cadastro_imobiliario: Optional[str] = Field(
        default=None, max_length=200
    )
    #: 🔴 A user id, never a name. The 5% captação slice (migration 076) is
    #: attributed to whoever brought the property in, and free text cannot be
    #: aggregated: two spellings become two people and "what did I earn this
    #: month" stops being answerable.
    captador_user_id: Optional[UUID] = None


class EnderecoManualPatchBody(StrictHttpModel):
    """Manual override for the 4 address fields `contrato_gerador.derivacao`
    reads (migration 149) — this product has no write-back to the Vista
    mirror those fields normally come from.

    Same `model_fields_set` contract as `ImovelDadosPatchBody`: absence means
    "leave alone", `None` means "clear the override and fall back to the
    mirror".
    """

    logradouro: Optional[str] = Field(default=None, max_length=200)
    numero: Optional[str] = Field(default=None, max_length=20)
    cidade: Optional[str] = Field(default=None, max_length=120)
    uf: Optional[str] = Field(default=None, max_length=2)


class ImovelDocumentoExtracaoPatchBody(StrictHttpModel):
    """The operator's confirmation/edit of one document's structured
    extraction (migration 118) — `PATCH .../documentos/{id}/extracao`.

    Every field is Optional, and `model_fields_set` (not `is None`) is what
    the service reads: an empty body is a valid "I reviewed this and it is
    correct" confirmation, not a no-op. `documentos_service.confirmar_
    extracao` refuses any field this document's `tipo_documento` does not
    carry (e.g. `resultado` on a `guia_iptu`) — this schema stays generic
    across every extractable tipo rather than branching on it at the HTTP
    boundary.
    """

    numero: Optional[str] = Field(default=None, max_length=64)
    emitida_em: Optional[date] = None
    validade_ate: Optional[date] = None
    resultado: Optional[
        Literal["negativa", "positiva", "positiva_com_efeito_de_negativa"]
    ] = None
    inscricao_imobiliaria: Optional[str] = Field(default=None, max_length=64)


class DecidirConflitoImovelBody(StrictHttpModel):
    """A human's decision on an `imovel_campo_conflitos` row (migration 154,
    D1). `aceitar=True` lands the extracted value, confirmed by the decider;
    `aceitar=False` leaves `imovel_dados` untouched."""

    aceitar: bool


__all__ = [
    "DecidirConflitoImovelBody",
    "EnderecoManualPatchBody",
    "ImovelDadosPatchBody",
    "ImovelDocumentoExtracaoPatchBody",
]
