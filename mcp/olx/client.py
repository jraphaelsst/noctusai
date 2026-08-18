"""DI seam for the outbound Gestor de Leads client + the observed corpus.

Two seams, one module, because both are "the thing a tool reaches for
that a test wants to replace".

`get_client()` mirrors `mcp/n8n/client.py`: settings-resolved by default,
424-gated when unconfigured — this connector deliberately does NOT fall
back to the seed Fake, because an operator running a diagnostic against
an unconfigured tenant must see a loud signal, not fabricated data.

`corpus_dir()` is where real deliveries are recorded. Overridable so a
test never writes into the repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from noctusai_lib.integrations.olx import make_olx_lead_manager_client

from . import api
from .settings import get_settings

_client_override: Optional[Any] = None
_corpus_dir_override: Optional[Path] = None

#: Recorded live bodies live beside the connector so the corpus travels
#: with the code that interprets it.
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "observed"


def configure_client(client: Optional[Any]) -> None:
    """Inject the lead-manager client (tests only). `None` restores the
    settings-resolved production path."""
    global _client_override
    _client_override = client


def get_client() -> Any:
    if _client_override is not None:
        return _client_override
    settings = get_settings()
    api.require_lead_manager_configured(settings)
    return make_olx_lead_manager_client(
        api_key=settings.api_key,
        agent_name=settings.agent_name,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
    )


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
    "corpus_dir",
    "get_client",
]
