"""Contract PDF + signature dispatch — Módulo 1.

Follows the shapes ERP already established: `reportlab` for generation
(`products/erp-imobiliario/backend/app/services/pdf_service.py`) and the
platform's documented DRY-RUN pattern for the signing provider — "services log
actions and return mock responses when credentials are missing"
(`KB § CONTEXT/02-LANDSCAPE.md § External Services`).

That makes the whole flow exercisable end-to-end today: a real PDF is produced
and stored, a signature request is recorded, and the webhook that activates the
client works — with `dry_run=True` marking the one step that did not reach a
vendor. When credentials arrive, only :func:`enviar_para_assinatura` changes.

N=2 NOTE: ERP has its own `assinatura_service`. That is the recurrence-rule
trigger — a THIRD consumer should not copy this again; promote a shared
signature adapter to `noctusai_lib/integrations/signature/` instead.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

__all__ = ["PROVEDORES", "AssinaturaSolicitada", "gerar_pdf_contrato", "enviar_para_assinatura"]

PROVEDORES: tuple[str, ...] = ("interno", "clicksign", "docusign", "autentique")


@dataclass(frozen=True, slots=True)
class AssinaturaSolicitada:
    external_id: str
    link_assinatura: str
    provedor: str
    #: True when no vendor was contacted. Carried all the way to the API
    #: response so nobody mistakes a dry run for a sent contract.
    dry_run: bool


def gerar_pdf_contrato(
    *,
    cliente_nome: str,
    titulo: str,
    valor_mensal: float,
    posts_por_mes: int | None,
    vigencia: str | None = None,
    clausulas: list[str] | None = None,
) -> bytes:
    """Render a contract PDF.

    Deliberately a plain, readable document rather than a template engine: the
    spec asks for "minutas a partir de templates dinâmicos", and until the
    agency supplies real templates, inventing a templating layer would be
    speculative. The seam to add one is this function's signature.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=titulo,
    )
    estilos = getSampleStyleSheet()
    corpo: list = [
        Paragraph(titulo, estilos["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Contratante:</b> {cliente_nome}", estilos["Normal"]),
        Paragraph(f"<b>Valor mensal:</b> R$ {valor_mensal:,.2f}", estilos["Normal"]),
    ]
    if posts_por_mes:
        corpo.append(
            Paragraph(f"<b>Pacote mensal:</b> {posts_por_mes} entregas", estilos["Normal"])
        )
    if vigencia:
        corpo.append(Paragraph(f"<b>Vigência:</b> {vigencia}", estilos["Normal"]))
    corpo.append(Spacer(1, 0.5 * cm))

    for i, clausula in enumerate(clausulas or [], start=1):
        corpo.append(Paragraph(f"<b>Cláusula {i}.</b> {clausula}", estilos["Normal"]))
        corpo.append(Spacer(1, 0.2 * cm))

    corpo.append(Spacer(1, 1 * cm))
    corpo.append(Paragraph(
        f"Emitido em {datetime.now(timezone.utc).strftime('%d/%m/%Y')}.", estilos["Italic"]
    ))
    doc.build(corpo)
    return buffer.getvalue()


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
        marca = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
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
