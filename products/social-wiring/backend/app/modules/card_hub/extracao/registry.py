"""THE one `tipo_documento -> extractor` interface (CONTRACT §7.4).

WHY. Today every card document is read by `identidade_extracao_service.
extrair_identidade`, which itself branches on the type (ficha cadastral, pacto,
Crednet, else the generic identity vision read) and ends with an LLM reading.
Three callers need to start "the extraction of this document": the card upload
route, the re-run route and the unattended sweep -- and now the WhatsApp intake
(`documento_intake_service`, CONTRACT §2.3) and post-aceite (§7).

The owner's next-phase goal is ONE dedicated, rule-based parser per document
type, replacing the LLM reading one type at a time WITHOUT touching the
orchestration. That requires the orchestration to call a single seam, not
`extrair_identidade` by name. This module is that seam:

    extrator_para(tipo)  -> an async callable with `extrair_identidade`'s signature
    registrar(tipo, fn)  -> swap one type's extractor (the next phase's move)

A replacement extractor MUST honour the same contract as the default: never
raise (record a terminal `extracao_status`), stamp `processando`/terminal
status on the document row, and return the outcome dict.

This wraps the existing function -- it does not rewrite any extraction logic.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

#: `(client, storage, org_id, cliente_id, documento_id, *, extractor=,
#: notification_service=, cep_lookup=) -> dict` -- `extrair_identidade`'s shape.
ExtratorDocumento = Callable[..., Awaitable[dict]]

#: Per-type overrides. EMPTY today: every extractable type uses the default.
_REGISTRO: dict[str, ExtratorDocumento] = {}


class TipoNaoExtraivel(ValueError):
    """No extractor is defined for this `tipo_documento`."""


async def _leitura_padrao(*args: Any, **kwargs: Any) -> dict:
    # Deferred import: `identidade_extracao_service` imports `card_hub.deps`
    # and (lazily) this package's callers; resolving it at call time keeps the
    # dependency one-way and lets the sweep inside that module use the registry.
    from app.modules.card_hub import identidade_extracao_service as svc

    return await svc.extrair_identidade(*args, **kwargs)


def deve_extrair(tipo_documento: str) -> bool:
    """Is there an extractor for this type? (the registry's own answer)"""
    from app.modules.card_hub import identidade_extracao_service as svc

    return tipo_documento in _REGISTRO or svc.deve_extrair(tipo_documento)


def extrator_para(tipo_documento: str) -> ExtratorDocumento:
    """The extractor for one type. Raises `TipoNaoExtraivel` when there is none
    (e.g. `a_classificar`, `outro`) -- callers gate on `deve_extrair` first."""
    if tipo_documento in _REGISTRO:
        return _REGISTRO[tipo_documento]
    if deve_extrair(tipo_documento):
        return _leitura_padrao
    raise TipoNaoExtraivel(tipo_documento)


def registrar(tipo_documento: str, extrator: ExtratorDocumento) -> None:
    """Replace one type's extractor (next phase: a rule-based parser)."""
    _REGISTRO[tipo_documento] = extrator


async def extrair(
    tipo_documento: str,
    client: Any,
    storage: Any,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    extractor_factory: Optional[Callable[[Optional[str], Optional[str]], Any]] = None,
    notification_service: Optional[Any] = None,
    cep_lookup: Optional[Any] = None,
) -> dict:
    """Run the registered extractor for `tipo_documento` on one stored document.

    `extractor_factory(org_id, tipo)` builds the LLM-reading extractor the
    default path needs; a parser-based replacement simply ignores it.
    """
    fn = extrator_para(tipo_documento)
    extractor = (
        extractor_factory(str(org_id), tipo_documento) if extractor_factory else None
    )
    return await fn(
        client, storage, org_id, cliente_id, documento_id,
        extractor=extractor,
        notification_service=notification_service,
        cep_lookup=cep_lookup,
    )
