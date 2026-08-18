"""DI seams: the vendor client, its HTTP transport, and the observed corpus.

Three seams, one module, because all three are "the thing a tool reaches
for that a test needs to replace".

`get_client()` is settings-resolved and 424-gated when unconfigured. It
deliberately does NOT fall back to the seed Fake: an operator running a
diagnostic against an unconfigured tenant must see a loud, typed signal,
not fabricated data that looks like an answer.

The HTTP transport is a seam of its own because the seed client takes it
as an argument rather than constructing one — the same design that makes
the seed testable without monkeypatching makes it the connector's job to
supply. `httpx` is imported lazily, inside the factory, so a broken or
absent transport library cannot take down the zero-IO contract tools:
those are what an operator reaches for DURING an outage, and a connector
that dies at import is one more thing that is down.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from noctusai_lib.integrations.imovelweb import make_imovelweb_client

from . import api
from .settings import get_settings

_client_override: Optional[Any] = None
_http_client: Optional[Any] = None
_http_client_override: Optional[Any] = None
_corpus_dir_override: Optional[Path] = None

#: Recorded live bodies live beside the connector so the corpus travels
#: with the code that interprets it.
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "observed"


def configure_client(client: Optional[Any]) -> None:
    """Inject the vendor client (tests only). `None` restores the
    settings-resolved production path."""
    global _client_override
    _client_override = client


def configure_http_client(http_client: Optional[Any]) -> None:
    """Inject the HTTP transport (tests only)."""
    global _http_client_override, _http_client
    _http_client_override = http_client
    _http_client = None


def http_client() -> Any:
    """One shared `httpx.AsyncClient` for the life of the process.

    Shared rather than per-call because the reconciliation reads page, and
    a fresh client per page would re-handshake TLS every time. Never
    closed: the MCP server's lifetime IS the client's lifetime, and a
    close hook would have to guess when the last tool call happened.
    """
    global _http_client
    if _http_client_override is not None:
        return _http_client_override
    if _http_client is None:
        import httpx  # lazy — see the module docstring

        _http_client = httpx.AsyncClient(timeout=get_settings().timeout_seconds)
    return _http_client


def get_client() -> Any:
    if _client_override is not None:
        return _client_override
    settings = get_settings()
    api.require_api_configured(settings)
    return make_imovelweb_client(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        region=settings.region,
        sandbox=settings.sandbox,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        http_client=http_client(),
        callback_header_value=_callback_header_value(settings),
    )


def _callback_header_value(settings) -> Optional[str]:
    """The header we registered, handed to the client for ONE reason: so
    it can redact that value out of anything it surfaces. It is a secret
    that we chose, which makes it no less a secret."""
    if not settings.webhook_secret:
        return None
    from noctusai_lib.integrations.imovelweb import basic_credential

    return basic_credential(settings.webhook_secret)


def configure_corpus_dir(path: Optional[Path]) -> None:
    """Point the observed corpus somewhere else (tests only)."""
    global _corpus_dir_override
    _corpus_dir_override = path


def corpus_dir() -> Path:
    return _corpus_dir_override if _corpus_dir_override is not None else DEFAULT_CORPUS_DIR


__all__ = [
    "DEFAULT_CORPUS_DIR",
    "configure_client",
    "configure_corpus_dir",
    "configure_http_client",
    "corpus_dir",
    "get_client",
    "http_client",
]
