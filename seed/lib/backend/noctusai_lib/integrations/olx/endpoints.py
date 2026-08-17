"""The Grupo OLX endpoint baseline — one source for probe AND catalog.

`olx.diagnostics.probe` measures against these rows and
`olx.diagnostics.list_known_endpoints` lists them, so the catalog can
never disagree with what the probe reports.

**The expected status is `None` on every row today, and that is the
point.** Nothing here has been probed against the live API yet (Gate 1).
A guessed expected-status is worse than none: the report would show
`as_expected` for a number we invented, and an operator who learns the
report lies stops reading it. `None` makes the probe classify the row as
`unverified` and print what it actually observed, which is the input
Gate 1 needs. Fill a row in only from a real observation, and stamp the
date in `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/olx.md`'s change log.
"""

from __future__ import annotations

from typing import Optional

# Probe-status vocabulary. Deliberately the same strings
# `integrations/vista/client.py` uses, NOT an import from it — coupling
# two unrelated vendor packages to share four constants is the worse
# trade. This is N=2 (vista, olx); the DRY recurrence rule says a THIRD
# connector needing this vocabulary must lift it to a shared module
# rather than copy it again.
ENDPOINT_LIVE = "live_probed"                     # reachable, behaves as recorded
ENDPOINT_PERMISSION_GATED = "permission_gated"    # 401 — exists, key lacks the grant
ENDPOINT_WRITE_ONLY = "write_only"                # 405 — exists, rejects GET
ENDPOINT_ABSENT = "absent"                        # 404 — no such route
ENDPOINT_UNVERIFIED = "unverified"                # documented, never probed
ENDPOINT_INBOUND = "inbound"                      # THEY call US; nothing to probe

#: Gestor de Leads receiver — the only authenticated endpoint the vendor
#: exposes to us, and therefore the only live proof that a key works.
OLX_LEAD_MANAGER_BASE_URL = "https://crm-leadmanager-leadreceiver-api.olx.com.br"

#: `(path, expected_bare_GET_status | None, probe_status, note)`
OLX_ENDPOINT_BASELINE: tuple[tuple[str, Optional[int], str, str], ...] = (
    (
        "/v1/addLeads",
        None,
        ENDPOINT_UNVERIFIED,
        "Gestor de Leads receiver. POST + X-API-KEY + X-Agent-Name. A bare GET "
        "most likely answers 405, but that is an inference — Gate 1 records the "
        "real number. Wrapped by olx.leads.push.",
    ),
    (
        "<inbound>/webhooks/lead",
        None,
        ENDPOINT_INBOUND,
        "OUR receiver, registered with OLX during homologation. Nothing to probe "
        "outbound; olx.webhook.simulate exercises it from our side.",
    ),
)

OLX_PROBE_PATHS: tuple[str, ...] = tuple(
    row[0] for row in OLX_ENDPOINT_BASELINE if row[2] != ENDPOINT_INBOUND
)

#: Documentation surfaces — not API, but the pages a human is sent to.
OLX_REFERENCE_URLS: dict[str, str] = {
    "lead_webhook_contract":
        "https://developers.grupozap.com/webhooks/integration_leads.html",
    "webhook_security":
        "https://developers.grupozap.com/webhooks/security.html",
    "endpoint_validator":
        "https://developers.grupozap.com/webhooks/endpoint_validator/",
    "lead_manager_api":
        "https://developers.grupozap.com/leadManager/api_lead_integration.html",
    "imovelweb_casa_mineira":
        "https://developers.grupozap.com/leadManager/imovelweb_casamineira.html",
}

#: Who to email. Kept in code because an agent asked to unblock an
#: integration should not have to go find it.
OLX_SUPPORT_CONTACTS: dict[str, str] = {
    "lead_integration": "integracaoleads@grupozap.com",
    "integration_tickets": "chamado.integracao@olxbr.com",
    "imovelweb_activation": "atendimento@imovelweb.com.br",
}


__all__ = [
    "ENDPOINT_ABSENT",
    "ENDPOINT_INBOUND",
    "ENDPOINT_LIVE",
    "ENDPOINT_PERMISSION_GATED",
    "ENDPOINT_UNVERIFIED",
    "ENDPOINT_WRITE_ONLY",
    "OLX_ENDPOINT_BASELINE",
    "OLX_LEAD_MANAGER_BASE_URL",
    "OLX_PROBE_PATHS",
    "OLX_REFERENCE_URLS",
    "OLX_SUPPORT_CONTACTS",
]
