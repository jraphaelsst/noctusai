"""The adapter surface consumers depend on — Fake and Real both satisfy it.

Note what is NOT here: the inbound direction. The lead feed we actually
want is ImovelWeb POSTing at us, and that needs no adapter — it is
`webhook.parse_imovelweb_callback` plus a receiver. A Fake of a pure
parser would exercise the same code the Real one does, which is the
seed's own test for whether the quartet is warranted.

What IS here is everything we *call*: authentication, the self-served
callback registration, the reconciliation reads that make a missed
delivery recoverable, and the enrichment reads.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .types import CallbackConfig


@runtime_checkable
class ImovelWebAdapter(Protocol):
    """OpenNavent client. Every method may raise `ImovelWebConfigError`
    (424 — not configured) or `ImovelWebUpstreamError` (vendor status,
    else 502)."""

    # -- introspection -----------------------------------------------------

    @property
    def configured(self) -> bool:
        """Whether credentials are present. Pure — no network."""
        ...

    def connection_status(self) -> dict[str, Any]:
        """Describe readiness **without making a single API call**.

        An agent asking "is this set up?" must not spend a request, and an
        unconfigured connector must not raise something an operator reads
        as an outage.
        """
        ...

    # -- auth ---------------------------------------------------------------

    async def login(self) -> dict[str, Any]: ...

    async def logout(self) -> None:
        """Explicit-only. Never wire to a shutdown hook — the connector and
        the backend may share credentials, and one logout revokes both."""
        ...

    # -- callback configuration (the core seam) -----------------------------

    async def get_callback_config(self) -> CallbackConfig: ...

    async def put_callback_config(self, config: CallbackConfig) -> CallbackConfig:
        """⚠️ **INTEGRATOR-WIDE.** There is no agency code in the path, so
        one write redirects every agency's leads. Callers confirm first,
        then read back and diff — a PUT that silently drops
        `subscriptions` is otherwise invisible, and an empty subscription
        list delivers nothing at all."""
        ...

    async def subscribe_event(self, event: str) -> Any: ...
    async def unsubscribe_event(self, event: str) -> Any: ...

    # -- reconciliation (the safety net for the 72h expiry) -----------------

    async def list_agency_messages(
        self,
        codigo_imobiliaria: str,
        *,
        from_date: str,
        to_date: Optional[str] = None,
        page: int = 0,
        size: int = 100,
    ) -> dict[str, Any]:
        """Paged `{content, number, size, total}`. `from_date` is
        `yyyyMMdd`."""
        ...

    async def get_message(self, id_mensaje: int) -> dict[str, Any]:
        """Authoritative re-fetch of one message.

        Background use only — an upstream round-trip does not fit inside
        the vendor's 1.5-second response budget for the callback itself.
        """
        ...

    async def list_listing_messages(
        self, codigo_imobiliaria: str, codigo_anuncio: str
    ) -> dict[str, Any]: ...

    # -- enrichment ---------------------------------------------------------

    async def get_contact(
        self, codigo_imobiliaria: str, id_contato: int
    ) -> dict[str, Any]: ...

    async def get_smartlead(self, id_mensagem: int) -> dict[str, Any]: ...

    async def get_seeker_profile(self, user_id_navplat: str) -> dict[str, Any]: ...

    async def list_contact_actions(self) -> list[dict[str, Any]]:
        """The authoritative `contactTypeId` catalog — replaces our
        transcribed copy at Gate 1.11."""
        ...

    # -- agencies -----------------------------------------------------------

    async def list_agencies(self, *, page: int = 0, size: int = 100) -> dict[str, Any]: ...

    async def unlink_agency(self, codigo_imobiliaria: str) -> Any: ...

    # -- sandbox only -------------------------------------------------------

    async def emit_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ask the sandbox to push a synthetic event at our receiver.

        **Refuses on a non-sandbox host** — a refusal, not a warning. This
        is the instrument that lets the contract be proven before any real
        lead exists; pointed at production it would fire synthetic leads
        into a live CRM.
        """
        ...


__all__ = ["ImovelWebAdapter"]
