"""Lais wave 12 -- the outbound transport seam (lais-build-contract 14 / A6).

One Protocol, two implementations, one factory per connection:

  WahaTransporte      free text ONLY (1:1 inside the conversation). A template, a business-profile update and a
                      template submission raise `OperacaoRequerApiOficial` -- WAHA free text is NEVER a mass
                      send (A6), so there is no code path that could turn a template into a text.
  CloudApiTransporte  Meta Cloud API over the SEED `MetaCloudClient` (real) or `FakeMetaCloudClient` (the
                      seed's own Fake: the factory returns it when no access token is configured, and tests
                      inject it): text, approved template, business profile, template submission.

`transporte_da_conexao(connection)` picks per `whatsapp_connections.transporte` (waha | cloud, default waha).
`cloud_configurada(connection)` is the single predicate every dispatch endpoint gates on: it is False while the
owner has not verified the app with Meta (no phone-number id / access token), and the endpoints answer 409
`transporte_indisponivel` -- everything else (create / save / schedule) keeps working.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.whatsapp import (
    chat_id_for_phone,
    get_meta_cloud_client,
    get_whatsapp_client,
)
from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

TRANSPORTE_WAHA = "waha"
TRANSPORTE_CLOUD = "cloud"
IDIOMA_PADRAO = "pt_BR"


class OperacaoRequerApiOficial(Exception):
    """The operation exists only on the WhatsApp Cloud API (official) transport."""


class TemplateRequerApiOficial(OperacaoRequerApiOficial):
    """A template message can only be sent through the Cloud API."""


def transporte_indisponivel() -> AppException:
    """The 409 every dispatch endpoint answers while the connection is not a configured Cloud one."""
    return AppException(
        "transporte_indisponivel",
        "O envio exige a API oficial do WhatsApp (Cloud API), ainda aguardando a verificação da Meta.",
        status_code=409,
    )


@runtime_checkable
class Transporte(Protocol):
    nome: str

    async def enviar_texto(self, telefone: str, texto: str) -> dict[str, Any]: ...

    async def enviar_template(
        self, telefone: str, template_nome: str, parametros: list[str], idioma: str = IDIOMA_PADRAO,
    ) -> dict[str, Any]: ...

    async def atualizar_perfil(self, perfil: dict[str, Any]) -> dict[str, Any]: ...

    async def submeter_modelo(
        self, nome: str, categoria_meta: str, corpo: str, exemplos: list[str], idioma: str = IDIOMA_PADRAO,
    ) -> dict[str, Any]: ...


class WahaTransporte:
    """WAHA: text only. Mass / template / profile operations are refused by construction."""

    nome = TRANSPORTE_WAHA

    def __init__(self, client: Any):
        self._client = client

    async def enviar_texto(self, telefone: str, texto: str) -> dict[str, Any]:
        return await self._client.send_text(chat_id_for_phone(telefone), texto)

    async def enviar_template(
        self, telefone: str, template_nome: str, parametros: list[str], idioma: str = IDIOMA_PADRAO,
    ) -> dict[str, Any]:
        raise TemplateRequerApiOficial("Template exige a API oficial do WhatsApp (Cloud API).")

    async def atualizar_perfil(self, perfil: dict[str, Any]) -> dict[str, Any]:
        raise OperacaoRequerApiOficial("O perfil do WhatsApp Business só é atualizado pela API oficial.")

    async def submeter_modelo(
        self, nome: str, categoria_meta: str, corpo: str, exemplos: list[str], idioma: str = IDIOMA_PADRAO,
    ) -> dict[str, Any]:
        raise OperacaoRequerApiOficial("Modelos só são enviados para aprovação pela API oficial.")


class CloudApiTransporte:
    """Meta Cloud API over the seed client (real or fake -- both expose the same async surface)."""

    nome = TRANSPORTE_CLOUD

    def __init__(self, client: Any):
        self._client = client

    @property
    def client(self) -> Any:
        return self._client

    async def enviar_texto(self, telefone: str, texto: str) -> dict[str, Any]:
        return await self._client.send_text(telefone.lstrip("+"), texto)

    async def enviar_template(
        self, telefone: str, template_nome: str, parametros: list[str], idioma: str = IDIOMA_PADRAO,
    ) -> dict[str, Any]:
        return await self._client.send_template(telefone.lstrip("+"), template_nome, idioma, list(parametros))

    async def atualizar_perfil(self, perfil: dict[str, Any]) -> dict[str, Any]:
        return await self._client.update_business_profile(perfil)

    async def submeter_modelo(
        self, nome: str, categoria_meta: str, corpo: str, exemplos: list[str], idioma: str = IDIOMA_PADRAO,
    ) -> dict[str, Any]:
        return await self._client.create_template(nome, categoria_meta, idioma, corpo, list(exemplos))


def cloud_configurada(connection: Any) -> bool:
    """True only for a connection set to `cloud` WITH a phone-number id and an access token (the decrypted
    `api_key`). Anything less is "awaiting Meta verification"."""
    return bool(
        connection is not None
        and getattr(connection, "transporte", TRANSPORTE_WAHA) == TRANSPORTE_CLOUD
        and getattr(connection, "cloud_phone_number_id", None)
        and getattr(connection, "api_key", None)
    )


def transporte_da_conexao(
    connection: Any,
    *,
    waha_factory: Optional[Callable[..., Any]] = None,
    cloud_client_factory: Optional[Callable[..., Any]] = None,
) -> Transporte:
    """The transport of one connection. `cloud` without credentials still returns a transport (the seed's
    Fake, via `get_meta_cloud_client`) so a unit under test can exercise the flow; production dispatch gates
    on `cloud_configurada` BEFORE it asks for one."""
    if getattr(connection, "transporte", TRANSPORTE_WAHA) == TRANSPORTE_CLOUD:
        factory = cloud_client_factory or get_meta_cloud_client
        return CloudApiTransporte(factory(
            phone_number_id=getattr(connection, "cloud_phone_number_id", None),
            api_key=getattr(connection, "api_key", None),
            waba_id=getattr(connection, "cloud_waba_id", None),
        ))
    factory = waha_factory or get_whatsapp_client
    return WahaTransporte(factory(
        base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name,
    ))


__all__ = [
    "CloudApiTransporte", "IDIOMA_PADRAO", "OperacaoRequerApiOficial", "TRANSPORTE_CLOUD", "TRANSPORTE_WAHA",
    "TemplateRequerApiOficial", "Transporte", "WahaTransporte", "cloud_configurada", "transporte_da_conexao",
    "transporte_indisponivel",
]
