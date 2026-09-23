"""DI seams for the e-mail slice (wave-2 slice B).

Every outbound collaborator — the SMTP sender, the Gmail client, the Google
OAuth provider, the profile lookup, the Pub/Sub token verifier — is reached
through one of these FastAPI dependencies. Tests override them with the seed
Fakes (`FakeEmailSender`, `FakeGmailClient`, `FakeOAuthProvider`) via
``app.dependency_overrides``; nothing of ours is ever patched
(KB § PATTERNS/backend/di-test-seam.md).

🔴 None of the production defaults ever returns a Fake. The seed factories
(`make_email_sender(None)`, `make_gmail_client(oauth_credentials=None)`) fall
back to a Fake when unconfigured — correct for a seed default, WRONG here: a
Fake sender would report an orçamento "enviado" that no lead ever received.
So the sender factory is only ever called WITH a resolved `SmtpConfig`
(`email_config.resolver_smtp` refuses first), and the Gmail factory builds the
Real client directly.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from fastapi import Depends
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.email import EmailSender, SmtpConfig, make_email_sender
from noctusai_lib.integrations.gmail import GmailClient, OAuthGmailCredentials
from noctusai_lib.integrations.gmail.push import TokenVerifier
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.security.oauth import GoogleProvider, OAuthProvider

from app.config import settings
from app.services.email_config import EmailSettings

__all__ = [
    "EmailSenderFactory",
    "GmailClientFactory",
    "GmailProfileFetcher",
    "current_email_settings",
    "get_email_settings",
    "get_email_sender_factory",
    "get_gmail_client_factory",
    "get_gmail_oauth_provider",
    "get_gmail_profile_fetcher",
    "get_push_token_verifier",
    "get_pdf_storage",
    "real_gmail_client",
    "fetch_gmail_profile_email",
]

EmailSenderFactory = Callable[[SmtpConfig], EmailSender]
GmailClientFactory = Callable[[OAuthGmailCredentials], GmailClient]
GmailProfileFetcher = Callable[[OAuthGmailCredentials], Awaitable[str]]


def current_email_settings() -> EmailSettings:
    """Snapshot of the live config (also used by the renewal job)."""
    try:
        public_url: Optional[str] = resolve_product_url("igig")
    except ValueError:
        public_url = None
    return EmailSettings.de(settings, public_url)


def get_email_settings() -> EmailSettings:
    return current_email_settings()


def _sender_real(config: SmtpConfig) -> EmailSender:
    if config is None:  # defence: the seed factory would hand back a Fake
        raise ValueError("SmtpConfig obrigatório — sem config não há envio real")
    return make_email_sender(config)


def get_email_sender_factory() -> EmailSenderFactory:
    return _sender_real


def real_gmail_client(creds: OAuthGmailCredentials) -> GmailClient:
    from noctusai_lib.integrations.gmail import RealGmailClient

    return RealGmailClient(oauth_credentials=creds)


def get_gmail_client_factory() -> GmailClientFactory:
    return real_gmail_client


def get_gmail_oauth_provider(
    cfg: EmailSettings = Depends(get_email_settings),
) -> Optional[OAuthProvider]:
    """The Google OAuth provider, or None when the OAuth app is unset (503)."""
    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        return None
    return GoogleProvider(
        client_id=cfg.google_oauth_client_id,
        client_secret=cfg.google_oauth_client_secret,
    )


async def fetch_gmail_profile_email(creds: OAuthGmailCredentials) -> str:
    """`users.getProfile` → the mailbox address (covered by gmail.readonly)."""

    def _chamar() -> str:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        google_creds = Credentials(
            token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            scopes=list(creds.scopes),
        )
        servico = build("gmail", "v1", credentials=google_creds, cache_discovery=False)
        perfil = servico.users().getProfile(userId="me").execute()
        return str(perfil.get("emailAddress") or "")

    return await asyncio.to_thread(_chamar)


def get_gmail_profile_fetcher() -> GmailProfileFetcher:
    return fetch_gmail_profile_email


def get_push_token_verifier() -> Optional[TokenVerifier]:
    """None ⇒ the seed's google-auth OIDC verifier (production)."""
    return None


def get_pdf_storage() -> StorageBackend:
    """Where slice A's orçamento PDFs live (the private ``igig`` bucket)."""
    from app.storage import get_storage

    return get_storage()
