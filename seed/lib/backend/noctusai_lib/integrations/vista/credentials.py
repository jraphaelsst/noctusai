"""Per-org Vista credential helpers (julia-v3, owner 2026-11-03: "our keys are to be stored in the DB, not .env").

The credential itself is a `CredentialStore` record (`VISTA_PROVIDER`, bundle `{base_url, api_key}`) read through
`credential_resolvers.VistaCredentialResolver`. This module is the provider-neutral rest of the lifecycle:

- `validar_base_url` -- the SSRF guard: the host must be `<tenant>.vistahost.com.br`, https only, no userinfo / port /
  path. A stored base URL is fetched server-side with the org's key attached, so an arbitrary host would be a credential
  exfiltration and an internal-network probe in one.
- `chave_final` -- the ONLY part of a key that may ever be shown (last 4).
- `verificar_conexao` -- the live, read-only check run before a key is stored (`/corretores/listar`, one row).
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from noctusai_lib.integrations.vista.client import VistaClient, VistaError, redact_api_key

HOST_VISTA = re.compile(r"^[a-z0-9-]+\.vistahost\.com\.br$")


class VistaBaseUrlInvalida(ValueError):
    """The base URL is not an https `<tenant>.vistahost.com.br` origin."""


def validar_base_url(valor: str) -> str:
    """The normalised `https://<host>` origin, or `VistaBaseUrlInvalida`. Trailing slash tolerated; nothing else."""
    bruto = (valor or "").strip()
    partes = urlsplit(bruto)
    host = (partes.hostname or "").lower()
    try:
        porta = partes.port
    except ValueError:
        porta = -1
    if (
        partes.scheme != "https" or partes.username is not None or partes.password is not None
        or porta is not None or partes.path not in ("", "/") or partes.query or partes.fragment
        or not HOST_VISTA.fullmatch(host)
    ):
        raise VistaBaseUrlInvalida("Use o endereço https://<empresa>.vistahost.com.br (sem caminho, porta ou parâmetros).")
    return f"https://{host}"


def chave_final(api_key: str) -> str:
    """Last 4 characters of the key -- never more."""
    return (api_key or "").strip()[-4:]


async def verificar_conexao(base_url: str, api_key: str, *, client: VistaClient | None = None) -> None:
    """Live read-only check: one broker row from `/corretores/listar`. Raises `VistaError` (key already redacted from
    its message) when Vista rejects the key or is unreachable."""
    cliente = client or VistaClient(base_url, api_key)
    try:
        await cliente.listar_corretores(page=1, page_size=1)
    except VistaError:
        raise
    except Exception as exc:  # transport failures that escape the client's own mapping
        raise VistaError(redact_api_key(f"{type(exc).__name__}: {exc}", api_key)) from exc


__all__ = ["HOST_VISTA", "VistaBaseUrlInvalida", "chave_final", "validar_base_url", "verificar_conexao"]
