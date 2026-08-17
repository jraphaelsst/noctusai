"""Deterministic in-memory `ImovelWebAdapter` — no network, no clock.

**Mirrors the Real client's refusals exactly.** A Fake that is more
permissive than production makes tests lie: they pass here and fail
against the vendor, which is the worst possible place to find out. So this
one validates callback configs the same way, refuses `emit_event` on a
non-sandbox host the same way, and raises `ImovelWebConfigError` when
unconfigured the same way.

Bi-directional, because the surface is read+write: writes are recorded
(`put_calls`, `subscribed`, `emitted`) and reads are injectable
(`inject_messages`, `inject_agencies`, `inject_smartlead`).
"""

from __future__ import annotations

from typing import Any, Optional

from .endpoints import IMOVELWEB_SANDBOX_BR, IMOVELWEB_SANDBOX_WINDOW, is_sandbox_host
from .errors import ImovelWebConfigError
from .types import IMOVELWEB_CONTACT_TYPES, CallbackConfig


class FakeImovelWebClient:
    """In-memory adapter for tests and for driving a receiver locally."""

    def __init__(
        self,
        *,
        configured: bool = True,
        base_url: str = IMOVELWEB_SANDBOX_BR,
        callback_config: Optional[CallbackConfig] = None,
    ) -> None:
        self._configured = configured
        self._base_url = base_url.rstrip("/")
        self._callback_config = callback_config

        # Recorded writes.
        self.put_calls: list[CallbackConfig] = []
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.emitted: list[dict[str, Any]] = []
        self.login_calls: int = 0
        self.logout_calls: int = 0
        self.unlinked: list[str] = []

        # Injectable reads.
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._message_by_id: dict[int, dict[str, Any]] = {}
        self._agencies: list[dict[str, Any]] = []
        self._smartleads: dict[int, dict[str, Any]] = {}
        self._contacts: dict[tuple[str, int], dict[str, Any]] = {}
        self._seeker_profiles: dict[str, dict[str, Any]] = {}

    # -- injection ---------------------------------------------------------

    def inject_messages(self, codigo_imobiliaria: str, messages: list[dict[str, Any]]) -> None:
        self._messages[codigo_imobiliaria] = list(messages)
        for message in messages:
            for key in ("idMensaje", "id"):
                if message.get(key) is not None:
                    self._message_by_id[int(message[key])] = message
                    break

    def inject_agencies(self, agencies: list[dict[str, Any]]) -> None:
        self._agencies = list(agencies)

    def inject_smartlead(self, id_mensagem: int, payload: dict[str, Any]) -> None:
        self._smartleads[id_mensagem] = payload

    def inject_contact(self, codigo: str, id_contato: int, payload: dict[str, Any]) -> None:
        self._contacts[(codigo, id_contato)] = payload

    def inject_seeker_profile(self, user_id: str, payload: dict[str, Any]) -> None:
        self._seeker_profiles[user_id] = payload

    # -- introspection -----------------------------------------------------

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def base_url(self) -> str:
        return self._base_url

    def connection_status(self) -> dict[str, Any]:
        return {
            "vendor": "imovelweb",
            "configured": self._configured,
            "base_url": self._base_url,
            "region": "br",
            "sandbox": is_sandbox_host(self._base_url),
            "sandbox_window": (
                IMOVELWEB_SANDBOX_WINDOW if is_sandbox_host(self._base_url) else None
            ),
            "missing": [] if self._configured else ["client_id", "client_secret"],
            "verified_against_live_traffic": False,
            "fake": True,
        }

    def _require_config(self) -> None:
        if not self._configured:
            raise ImovelWebConfigError(
                "ImovelWeb is not configured (fake) — missing client_id, client_secret"
            )

    # -- auth ---------------------------------------------------------------

    async def login(self) -> dict[str, Any]:
        self._require_config()
        self.login_calls += 1
        return {"token_type": "bearer", "expires_at": None, "scope": []}

    async def logout(self) -> None:
        self._require_config()
        self.logout_calls += 1

    # -- callback configuration --------------------------------------------

    async def get_callback_config(self) -> CallbackConfig:
        self._require_config()
        if self._callback_config is None:
            # The vendor's "nothing registered" shape, which is also the
            # most dangerous real state: no subscriptions, no delivery.
            return CallbackConfig(
                url="", authorization_header_value="", subscriptions=()
            )
        return self._callback_config

    async def put_callback_config(self, config: CallbackConfig) -> CallbackConfig:
        self._require_config()
        # Same validation as the Real client — see the module docstring.
        problems = config.validate()
        if problems:
            raise ImovelWebConfigError(
                "refusing to register an invalid callback config: "
                + "; ".join(problems)
            )
        self.put_calls.append(config)
        self._callback_config = config
        return config

    async def subscribe_event(self, event: str) -> Any:
        self._require_config()
        self.subscribed.append(event)
        if self._callback_config is not None and event not in self._callback_config.subscriptions:
            self._callback_config = CallbackConfig(
                url=self._callback_config.url,
                authorization_header_value=self._callback_config.authorization_header_value,
                authorization_header_key=self._callback_config.authorization_header_key,
                language=self._callback_config.language,
                subscriptions=tuple(self._callback_config.subscriptions) + (event,),
            )
        return "ok"

    async def unsubscribe_event(self, event: str) -> Any:
        self._require_config()
        self.unsubscribed.append(event)
        if self._callback_config is not None:
            self._callback_config = CallbackConfig(
                url=self._callback_config.url,
                authorization_header_value=self._callback_config.authorization_header_value,
                authorization_header_key=self._callback_config.authorization_header_key,
                language=self._callback_config.language,
                subscriptions=tuple(
                    e for e in self._callback_config.subscriptions if e != event
                ),
            )
        return "ok"

    # -- reconciliation -----------------------------------------------------

    async def list_agency_messages(
        self,
        codigo_imobiliaria: str,
        *,
        from_date: str,
        to_date: Optional[str] = None,
        page: int = 0,
        size: int = 100,
    ) -> dict[str, Any]:
        self._require_config()
        all_messages = self._messages.get(codigo_imobiliaria, [])
        start = page * size
        window = all_messages[start:start + size]
        return {
            "content": window,
            "number": page,
            "size": size,
            "total": len(all_messages),
        }

    async def get_message(self, id_mensaje: int) -> dict[str, Any]:
        self._require_config()
        return self._message_by_id.get(int(id_mensaje), {})

    async def list_listing_messages(
        self, codigo_imobiliaria: str, codigo_anuncio: str
    ) -> dict[str, Any]:
        self._require_config()
        messages = [
            m for m in self._messages.get(codigo_imobiliaria, [])
            if m.get("codigoAviso") == codigo_anuncio
        ]
        return {"content": messages, "number": 0, "size": len(messages),
                "total": len(messages)}

    # -- enrichment ---------------------------------------------------------

    async def get_contact(self, codigo_imobiliaria: str, id_contato: int) -> dict[str, Any]:
        self._require_config()
        return self._contacts.get((codigo_imobiliaria, int(id_contato)), {})

    async def get_smartlead(self, id_mensagem: int) -> dict[str, Any]:
        self._require_config()
        return self._smartleads.get(int(id_mensagem), {})

    async def get_seeker_profile(self, user_id_navplat: str) -> dict[str, Any]:
        self._require_config()
        return self._seeker_profiles.get(user_id_navplat, {})

    async def list_contact_actions(self) -> list[dict[str, Any]]:
        self._require_config()
        return [{"id": i, "tipo": t} for i, t in sorted(IMOVELWEB_CONTACT_TYPES.items())]

    # -- agencies -----------------------------------------------------------

    async def list_agencies(self, *, page: int = 0, size: int = 100) -> dict[str, Any]:
        self._require_config()
        start = page * size
        window = self._agencies[start:start + size]
        return {"content": window, "number": page, "size": size,
                "total": len(self._agencies)}

    async def unlink_agency(self, codigo_imobiliaria: str) -> Any:
        self._require_config()
        self.unlinked.append(codigo_imobiliaria)
        self._agencies = [
            a for a in self._agencies
            if a.get("codigoInmobiliaria") != codigo_imobiliaria
        ]
        return "ok"

    # -- sandbox only -------------------------------------------------------

    async def emit_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Records the emission. **Refuses a non-sandbox host, exactly as
        the Real client does** — a Fake that allowed it would let a test
        pass over a guard that fires in production."""
        self._require_config()
        if not is_sandbox_host(self._base_url):
            raise ImovelWebConfigError(
                f"emit_event refuses a non-sandbox host ({self._base_url!r}). "
                "It fabricates lead events; against production those would be "
                "indistinguishable from real customers."
            )
        self.emitted.append(payload)
        return {"status": "emitted", "fake": True}


__all__ = ["FakeImovelWebClient"]
