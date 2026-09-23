"""Signature dispatch — Módulo 1.

The contract PDF itself is `app/services/documentos_pdf.py` (xhtml2pdf via the
seed's `render_html_pdf`); the contrato lifecycle is `app/services/contratos.py`.
This module is only the signing-provider leg, following the platform's
documented DRY-RUN pattern for the signing provider — "services log
actions and return mock responses when credentials are missing"
(`KB § CONTEXT/02-LANDSCAPE.md § External Services`).

That makes the whole flow exercisable end-to-end today: a real PDF is produced
and stored, a signature request is recorded, and the webhook that activates the
client works — with `dry_run=True` marking the one step that did not reach a
vendor. When credentials arrive, only :func:`enviar_para_assinatura` changes.

N=2 NOTE: ERP has its own `assinatura_service`. The shared adapter now exists
(`noctusai_lib.integrations.signature`, D4Sign Fake+Real+factory); moving this
dry-run path onto it is `NOC-REMEDIATE[igig-assinatura]` below — do not copy
this module into a third product.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = ["PROVEDORES", "AssinaturaSolicitada", "enviar_para_assinatura"]

PROVEDORES: tuple[str, ...] = ("interno", "clicksign", "docusign", "autentique")


@dataclass(frozen=True, slots=True)
class AssinaturaSolicitada:
    external_id: str
    link_assinatura: str
    provedor: str
    #: True when no vendor was contacted. Carried all the way to the API
    #: response so nobody mistakes a dry run for a sent contract.
    dry_run: bool


def enviar_para_assinatura(
    *,
    org_id: str,
    provedor: str,
    documento_nome: str,
    signatario_email: str | None,
    token: str | None = None,
) -> AssinaturaSolicitada:
    """Send a document for signature, or record a dry run.

    `external_id` always carries the org as its first dot-separated segment,
    so the webhook can resolve the contract without a session.

    Mirrors ERP + the platform dry-run pattern: with no credentials the call
    returns a mock result flagged `dry_run=True` rather than raising. That is
    the right trade HERE — unlike publishing, nothing is asserted to the client
    as done, and the flag travels to the UI so an operator sees plainly that no
    vendor was contacted.
    """
    if provedor not in PROVEDORES:
        raise ValueError(f"provedor inválido: {provedor!r}; esperado um de {PROVEDORES}")

    if provedor == "interno" or not token:
        # 🔴 A CSPRNG token, not a timestamp: the id was `dry-<provedor>-
        # <YYYYmmddHHMMSS>`, i.e. guessable to the second (smoke finding 2).
        marca = secrets.token_urlsafe(24)
        # `<org_id>.<resto>` — the SAME shape the approval portal's token uses,
        # and for the same reason: the signature webhook arrives with no
        # session, and the store requires an org on every call. Embedding it
        # keeps every lookup org-scoped instead of punching a cross-org query
        # through the persistence seam.
        logger.info(
            "assinatura DRY-RUN provedor=%s documento=%s (sem credenciais)",
            provedor, documento_nome,
        )
        return AssinaturaSolicitada(
            external_id=f"{org_id}.dry-{provedor}-{marca}",
            link_assinatura=f"https://exemplo.invalido/assinar/dry-{marca}",
            provedor=provedor,
            dry_run=True,
        )

    # NOC-REMEDIATE[igig-assinatura]: real Clicksign/DocuSign/Autentique call
    # pending credentials. ERP already implements these providers — promote a
    # shared adapter to noctusai_lib rather than copying, per the N=2 note in
    # this module's docstring. — 2026-08-09
    raise NotImplementedError(
        f"Integração {provedor} ainda não homologada para IgIg (token presente)."
    )
