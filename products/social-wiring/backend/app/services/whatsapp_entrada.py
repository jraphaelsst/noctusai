"""The slim inbound helper of Julia's line: what the webhook needs to identify a sender, built from the CONNECTION record.

It replaces the old `WhatsAppIntakeService` builder the webhook used (the "One Chat" operator bot is retired, 2026-11-04): no
authorized-number list, no bound chats, no env WAHA session. It answers three questions only:

* ``canonical_session_id(sender)`` -- the phone form of a chat id when the LID is known (one conversation, one key);
* the LID cache (``whatsapp:lid_to_phone:<lid>``, Redis, 30 days) -- READ, and written back whenever WAHA resolved one;
* ``phone_do_lid(lid)`` -- cache first, then WAHA ``get_lid_phone`` (which never raises).

Redis is OPTIONAL everywhere: no client / a failing Redis answers "unknown", never an error (a LID then resolves through WAHA).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from app.services import julia_agente_service as julia

logger = logging.getLogger(__name__)

_LID_TTL_S = 30 * 24 * 3600


def _chave_lid(lid: str) -> str:
    return f"whatsapp:lid_to_phone:{lid}"


class EntradaDaLinha:
    """One inbound's view of the line it arrived on. `registro_provider` returns the connection with its key DECRYPTED (or None); it
    is called lazily and once -- decrypting costs a read and a phone-form sender never needs it. `waha_factory` builds the WAHA client
    from that record (`base_url=`, `api_key=`, `session=`)."""

    def __init__(
        self, *, org_id: UUID, connection_id: UUID | None, redis: Any = None,
        registro_provider: Optional[Callable[[], Any]] = None, waha_factory: Optional[Callable[..., Any]] = None,
    ):
        self.org_id = org_id
        self.connection_id = connection_id
        self._redis = redis
        self._registro_provider = registro_provider
        self._waha_factory = waha_factory
        self._registro: Any = None
        self._registro_lido = False

    def registro_da_conexao(self) -> Any:
        """The connection record with the decrypted key, or None (no store / no credentials). Read once per inbound."""
        if not self._registro_lido:
            self._registro_lido = True
            if self._registro_provider is not None:
                self._registro = self._registro_provider()
        return self._registro

    def _waha(self) -> Any:
        registro = self.registro_da_conexao()
        if registro is None or not registro.api_key:
            return None
        factory = self._waha_factory
        if factory is None:
            from noctusai_lib.integrations.whatsapp import get_whatsapp_client as factory
        return factory(base_url=registro.base_url or None, api_key=registro.api_key, session=registro.session_name)

    # -- LID cache (Redis optional) ----------------------------------------------------
    def lid_em_cache(self, lid: str) -> str | None:
        if self._redis is None:
            return None
        try:
            return self._redis.get(_chave_lid(lid))
        except Exception as exc:
            logger.warning("whatsapp: LID cache unreadable (%s) -- resolving through WAHA", type(exc).__name__)
            return None

    def lembrar_lid(self, lid: str, telefone: str) -> None:
        if self._redis is None or not lid or not telefone:
            return
        try:
            self._redis.set(_chave_lid(lid), telefone, ex=_LID_TTL_S)
        except Exception as exc:
            logger.warning("whatsapp: LID cache not written (%s)", type(exc).__name__)

    # -- identity ---------------------------------------------------------------------
    def canonical_session_id(self, raw_sender: str) -> str:
        """Phone form (`+<digits>`) when the sender is a phone or a LID with a cached phone; the raw id otherwise."""
        raw = (raw_sender or "").strip()
        if not raw:
            return raw
        if julia.is_lid(raw):
            return self.lid_em_cache(raw) or raw
        limpo = raw.replace("@c.us", "").replace("@s.whatsapp.net", "")
        if limpo and not limpo.startswith("+") and limpo.isdigit():
            return f"+{limpo}"
        return limpo or raw

    async def phone_do_lid(self, lid: str) -> str | None:
        """Phone DIGITS behind an `@lid`: the cache, then WAHA `get_lid_phone` (a hit is cached). None when unknown."""
        em_cache = self.lid_em_cache(lid)
        if em_cache:
            digitos = str(em_cache).replace("@c.us", "").replace("@s.whatsapp.net", "").lstrip("+")
            if digitos.isdigit():
                return digitos
        try:
            waha = self._waha()
            if waha is None:
                return None
            phone = await waha.get_lid_phone(lid)
        except Exception:
            logger.warning("WAHA LID->phone lookup failed", exc_info=True)
            return None
        digitos = julia.phone_digits(phone) if phone else None
        if digitos:
            self.lembrar_lid(lid, f"+{digitos}")
        return digitos


def entrada_da_conexao(
    connection: Any, *, redis: Any = None, registro_provider: Optional[Callable[[], Any]] = None,
    waha_factory: Optional[Callable[..., Any]] = None,
) -> EntradaDaLinha:
    """Build the helper from a `WhatsAppConnectionRecord` (the org that owns the line, the connection id)."""
    return EntradaDaLinha(
        org_id=connection.org_id, connection_id=connection.id, redis=redis,
        registro_provider=registro_provider, waha_factory=waha_factory,
    )


__all__ = ["EntradaDaLinha", "entrada_da_conexao"]
