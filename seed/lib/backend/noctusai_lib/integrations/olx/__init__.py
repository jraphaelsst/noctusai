"""Grupo OLX (ZAP · VivaReal · OLX · ImovelWeb · Casa Mineira) leads.

One vendor, one package — the portals share a single lead pipe, so a
per-portal package would be four copies of this one.

**Two directions, and they are not symmetric.**

*Inbound* is the one that matters: OLX POSTs one lead per request to a
URL we register, authenticated with HTTP Basic (`vivareal:<SECRET_KEY>`,
one key per CRM). There is no pull API and no sandbox. Delivery is judged
purely on our HTTP status code — the response body is ignored — and a
non-2xx is retried 3× then dropped after 14 days. So:

    parse   →  webhook.parse_olx_lead_webhook
    check   →  contract.validate_olx_lead_payload
    map     →  normalizers.olx_lead_to_lead_payload

all pure, all zero-IO, so a product's receiver composes them without
inheriting anything from this package.

*Outbound* is `POST /v1/addLeads` on Gestor de Leads — pushing a lead we
hold into OLX's inbox. That one is an IO module and ships the full
Protocol + Fake + Real + factory.

**`contract.py` is the single source of truth for the payload.** The MCP
connector (`mcp/olx`) serves it to agents and diffs live bodies against
it; the product receiver validates with it. Two copies would disagree
within a release, and the disagreement would look like leads vanishing.

Everything in `contract.py` is transcribed from the vendor's docs and is
UNVERIFIED against live traffic until Gate 1 (see
`projects/olx-portal-leads-ingestion/PROJECT.md`).
"""

from __future__ import annotations

from .contract import (
    OLX_LEAD_FIELDS,
    OLX_RESPONSE_SEMANTICS,
    OLX_RETRY_POLICY,
    OLX_SAMPLE_LEAD,
    ContractViolation,
    OlxFieldSpec,
    contract_summary,
    diff_observed,
    has_blocking_violation,
    missing_client_listing_id,
    olx_lead_json_schema,
    validate_olx_lead_payload,
)
from .endpoints import (
    OLX_ENDPOINT_BASELINE,
    OLX_LEAD_MANAGER_BASE_URL,
    OLX_PROBE_PATHS,
    OLX_REFERENCE_URLS,
    OLX_SUPPORT_CONTACTS,
)
from .errors import OlxConfigError, OlxError, OlxUpstreamError, redact_secret
from .factory import make_olx_lead_manager_client
from .fake import FakeOlxLeadManagerClient
from .normalizers import (
    OLX_SOURCE_SLUG,
    olx_lead_to_lead_payload,
    olx_timestamp_to_date,
    render_observacoes,
)
from .protocol import OlxLeadManagerAdapter
from .real import OlxLeadManagerClient
from .types import (
    OLX_LEAD_ORIGIN_MCMV,
    OLX_LEAD_ORIGIN_STANDARD,
    OLX_LEAD_TYPES,
    OLX_TEMPERATURES,
    OLX_TRANSACTION_TYPES,
    OlxLead,
)
from .webhook import parse_olx_lead_webhook

__all__ = [
    "ContractViolation",
    "FakeOlxLeadManagerClient",
    "OLX_ENDPOINT_BASELINE",
    "OLX_LEAD_FIELDS",
    "OLX_LEAD_MANAGER_BASE_URL",
    "OLX_LEAD_ORIGIN_MCMV",
    "OLX_LEAD_ORIGIN_STANDARD",
    "OLX_LEAD_TYPES",
    "OLX_PROBE_PATHS",
    "OLX_REFERENCE_URLS",
    "OLX_RESPONSE_SEMANTICS",
    "OLX_RETRY_POLICY",
    "OLX_SAMPLE_LEAD",
    "OLX_SOURCE_SLUG",
    "OLX_SUPPORT_CONTACTS",
    "OLX_TEMPERATURES",
    "OLX_TRANSACTION_TYPES",
    "OlxConfigError",
    "OlxError",
    "OlxFieldSpec",
    "OlxLead",
    "OlxLeadManagerAdapter",
    "OlxLeadManagerClient",
    "OlxUpstreamError",
    "contract_summary",
    "diff_observed",
    "has_blocking_violation",
    "make_olx_lead_manager_client",
    "missing_client_listing_id",
    "olx_lead_json_schema",
    "olx_lead_to_lead_payload",
    "olx_timestamp_to_date",
    "parse_olx_lead_webhook",
    "redact_secret",
    "render_observacoes",
    "validate_olx_lead_payload",
]
