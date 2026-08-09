"""Channel publishers — Módulo 5.

Protocol + Fake + Real + factory, the same shape as the seed's IO modules
(`KB § PATTERNS/backend/seed-fake-real-adapter.md`).

**Why this lives in the PRODUCT and not the seed.** noc ships
`noctusai_lib.integrations.meta`, but it is ads/leadgen-shaped (AdAccount,
AdCampaign, lead webhooks) — it does not publish organic posts, and there is
nothing for TikTok or LinkedIn. IgIg is the first consumer of a multi-channel
organic publisher, so per the recurrence rule this stays here at N=1. **When a
second product needs it, promote this module to
`noctusai_lib/integrations/social_publishing/` rather than copying it** — that
is the N=2 trigger, and this note is the reminder.

**What is and is not real today.** The scheduling machinery, the queue, the
retry accounting and the status transitions are real and exercised. The
network calls are NOT: no channel credentials exist yet, so the real adapters
raise :class:`PublisherNotConfigured` rather than pretending to succeed. That
refusal is the honest behaviour — a publisher that silently no-ops would mark
a post "publicada" that no client ever saw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "CANAIS",
    "PublishResult",
    "ChannelPublisher",
    "FakePublisher",
    "MetaPublisher",
    "TikTokPublisher",
    "LinkedInPublisher",
    "PublisherNotConfigured",
    "get_publisher",
]

#: Mirrors the DB CHECK on `publicacao.canal`.
CANAIS: tuple[str, ...] = ("instagram", "facebook", "tiktok", "linkedin")


class PublisherNotConfigured(RuntimeError):
    """The channel has no usable credentials.

    Raised instead of returning a failure result so a caller cannot mistake
    "we never tried" for "the platform rejected it" — they need different
    operator responses.
    """


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What a successful publish returns.

    `external_id` is required: without the platform's own post id there is no
    way to fetch metrics later, so a publisher that cannot supply one has not
    really succeeded.
    """

    external_id: str
    permalink: str | None = None


@runtime_checkable
class ChannelPublisher(Protocol):
    """Surface every channel publisher implements."""

    canal: str

    def publicar(
        self,
        *,
        texto: str,
        midia_urls: list[str],
        legenda_extra: str | None = None,
    ) -> PublishResult:
        ...


class FakePublisher:
    """Deterministic in-memory publisher.

    Records every call on `enviados` so a test can assert what WOULD have gone
    out, and mints a stable external id from the call index — assertable
    without capturing it first.
    """

    def __init__(self, canal: str = "instagram") -> None:
        self.canal = canal
        self.enviados: list[dict] = []

    def publicar(
        self,
        *,
        texto: str,
        midia_urls: list[str],
        legenda_extra: str | None = None,
    ) -> PublishResult:
        self.enviados.append(
            {"texto": texto, "midia_urls": list(midia_urls), "legenda_extra": legenda_extra}
        )
        indice = len(self.enviados)
        return PublishResult(
            external_id=f"fake-{self.canal}-{indice}",
            permalink=f"https://example.test/{self.canal}/{indice}",
        )


class _RealPublisherBase:
    """Shared shape for the credentialed publishers.

    Each subclass names its own credential requirement so the error tells an
    operator exactly which secret is missing, rather than a generic failure.
    """

    canal: str = ""
    env_hint: str = ""

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def publicar(
        self,
        *,
        texto: str,
        midia_urls: list[str],
        legenda_extra: str | None = None,
    ) -> PublishResult:
        if not self._token:
            raise PublisherNotConfigured(
                f"Canal {self.canal} sem credenciais: defina {self.env_hint}. "
                "Nenhuma publicação é marcada como enviada sem confirmação da plataforma."
            )
        # NOC-REMEDIATE[igig-publishing]: real API call pending channel
        # credentials + app review. Deliberately raises rather than returning
        # a fabricated external_id — marking a post 'publicada' that no client
        # ever saw is worse than failing loudly. — 2026-08-09
        raise PublisherNotConfigured(
            f"Integração {self.canal} ainda não homologada (token presente, chamada pendente)."
        )


class MetaPublisher(_RealPublisherBase):
    """Instagram / Facebook via the Meta Graph API."""

    def __init__(self, canal: str = "instagram", token: str | None = None) -> None:
        super().__init__(token)
        self.canal = canal
        self.env_hint = "IGIG_META_TOKEN"


class TikTokPublisher(_RealPublisherBase):
    canal = "tiktok"
    env_hint = "IGIG_TIKTOK_TOKEN"


class LinkedInPublisher(_RealPublisherBase):
    canal = "linkedin"
    env_hint = "IGIG_LINKEDIN_TOKEN"


def get_publisher(canal: str, *, token: str | None = None) -> ChannelPublisher:
    """Return the publisher for a channel.

    No token → :class:`FakePublisher`, mirroring every other factory on this
    platform (`get_calendar_adapter`, `get_whatsapp_client`, …): the product
    runs end-to-end in development, and only a configured environment reaches
    a real network.
    """
    if canal not in CANAIS:
        raise ValueError(f"canal inválido: {canal!r}; esperado um de {CANAIS}")
    if not token:
        return FakePublisher(canal)
    if canal in ("instagram", "facebook"):
        return MetaPublisher(canal, token)
    if canal == "tiktok":
        return TikTokPublisher(token)
    return LinkedInPublisher(token)
