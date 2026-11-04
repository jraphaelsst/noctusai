"""One credential source for the org's WhatsApp line (julia-line CONTRACT §A).

Every SW sender -- lead replies, staff/owner notices, notifications, photo-batch alerts, media downloads -- reads the WAHA
base URL / api key / session from the org's single ``whatsapp_connections`` row through `linha_da_org`. There is no env
WAHA sender and no fallback to another org's line: an org without a line gets the named error `SemLinha`
(``motivo == "sem_linha"``) and the caller records or logs that reason on its own channel.

Row choice: the org's ``agente_leads_ativo`` row, else its only row. Several rows and none active is `LinhaAmbigua`
(never a guess). The decrypted ``api_key`` lives only on the in-memory `LinhaDaOrg`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.whatsapp import get_whatsapp_client

from app.services.julia_transporte import Transporte, transporte_da_conexao

logger = logging.getLogger(__name__)

MOTIVO_SEM_LINHA = "sem_linha"
MOTIVO_LINHA_AMBIGUA = "linha_ambigua"


class LinhaIndisponivel(Exception):
    """The org has no usable WhatsApp line. ``motivo`` is the stable, loggable reason."""

    motivo = "linha_indisponivel"

    def __init__(self, org_id: Any):
        super().__init__(f"{self.motivo}: org={org_id}")
        self.org_id = str(org_id)


class SemLinha(LinhaIndisponivel):
    """The org has no WhatsApp connection."""

    motivo = MOTIVO_SEM_LINHA


class LinhaAmbigua(LinhaIndisponivel):
    """The org has several connections and none is the active Julia line."""

    motivo = MOTIVO_LINHA_AMBIGUA


@dataclass(frozen=True)
class LinhaDaOrg:
    """The org's line: the decrypted connection record plus ready-made senders."""

    org_id: UUID
    connection: Any  # WhatsAppConnectionRecord with `api_key` decrypted

    @property
    def connection_id(self) -> UUID:
        return self.connection.id

    @property
    def base_url(self) -> str:
        return self.connection.base_url or ""

    @property
    def api_key(self) -> Optional[str]:
        return self.connection.api_key

    @property
    def session(self) -> str:
        return self.connection.session_name or "default"

    def waha_client(self, factory: Optional[Callable[..., Any]] = None) -> Any:
        """A WAHA client bound to THIS line. `factory` is the DI seam (default: the seed `get_whatsapp_client`)."""
        return (factory or get_whatsapp_client)(base_url=self.base_url, api_key=self.api_key, session=self.session)

    def transporte(self, **kwargs: Any) -> Transporte:
        """The line's transport (WAHA or Cloud API), via `transporte_da_conexao`."""
        return transporte_da_conexao(self.connection, **kwargs)


def _escolher(rows: list[Any], org_id: Any) -> Any:
    if not rows:
        raise SemLinha(org_id)
    if len(rows) == 1:
        return rows[0]
    ativas = [r for r in rows if getattr(r, "agente_leads_ativo", False) is True]
    if len(ativas) == 1:
        return ativas[0]
    raise LinhaAmbigua(org_id)


def linha_da_org(org_id: UUID | str, *, store: Any = None, admin_client: Any = None) -> LinhaDaOrg:
    """The org's WhatsApp line, decrypted. Raises `SemLinha` / `LinhaAmbigua`. `store` is the DI seam (a
    `WhatsAppConnectionStore`); production builds one over the service-role client."""
    org = UUID(str(org_id))
    if store is None:
        from app.dependencies import get_admin_client  # local: keeps this module importable without the app wiring
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        store = build_whatsapp_connection_store(admin_client or get_admin_client())
    escolhida = _escolher(store.list_connections(org_id=org), org)
    decifrada = store.get_connection(connection_id=escolhida.id, org_id=org, decrypt=True)
    if decifrada is None:  # deleted between the list and the read
        raise SemLinha(org)
    return LinhaDaOrg(org_id=org, connection=decifrada)


def linha_da_conexao(connection: Any) -> LinhaDaOrg:
    """Wrap an already-resolved (decrypted) inbound connection record -- the webhook path already holds the line."""
    return LinhaDaOrg(org_id=connection.org_id, connection=connection)


__all__ = [
    "LinhaAmbigua", "LinhaDaOrg", "LinhaIndisponivel", "MOTIVO_LINHA_AMBIGUA", "MOTIVO_SEM_LINHA", "SemLinha",
    "linha_da_conexao", "linha_da_org",
]
