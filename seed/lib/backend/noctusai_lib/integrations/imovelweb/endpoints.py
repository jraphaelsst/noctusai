"""Hosts, endpoint baseline and reference material for OpenNavent.

Everything an operator or an agent needs to reach the vendor, kept here so
the MCP connector's diagnostics tools read it from code rather than from a
doc page that drifts.
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Endpoint status vocabulary.
#
# NOC-REMEDIATE[dry-lift]: third instance of this vocabulary
# (`vista/client.py`, `olx/endpoints.py`, here). `olx/endpoints.py` already
# carries the obligation in a comment — the recurrence rule says a THIRD
# connector MUST lift it to `noctusai_lib/integrations/endpoint_status.py`
# and rewrite the other two to import it. Sequenced, not waived: both call
# sites belong to a branch still in flight. Do it once that branch lands.
# ---------------------------------------------------------------------------
ENDPOINT_LIVE = "live"
ENDPOINT_PERMISSION_GATED = "permission_gated"
ENDPOINT_WRITE_ONLY = "write_only"
ENDPOINT_ABSENT = "absent"
ENDPOINT_UNVERIFIED = "unverified"
ENDPOINT_INBOUND = "inbound"

# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------
IMOVELWEB_PROD_BR = "https://api-br-open.navent.com"
IMOVELWEB_SANDBOX_BR = "https://api-br-sandbox-open.navent.com"
IMOVELWEB_PROD_AR = "https://api-zp-open.navent.com"
IMOVELWEB_PROD_RELA = "https://api-rela-open.navent.com"

IMOVELWEB_HOSTS: dict[str, dict[str, str]] = {
    "br": {"prod": IMOVELWEB_PROD_BR, "sandbox": IMOVELWEB_SANDBOX_BR},
    "ar": {"prod": IMOVELWEB_PROD_AR, "sandbox": ""},
    "rela": {"prod": IMOVELWEB_PROD_RELA, "sandbox": ""},
}

#: The sandbox is NOT always up. A timeout outside this window is normal
#: operation, not an incident — surfacing it as a typed error rather than a
#: mystery hang is why this constant exists.
IMOVELWEB_SANDBOX_WINDOW = "07:00-21:00 UTC-3"

#: Public and unauthenticated on BOTH hosts — which is what makes
#: `imovelweb.diagnostics.fetch_swagger` possible, and why the doc-vs-reality
#: loop can close here without waiting for live traffic.
IMOVELWEB_SWAGGER_PATH = "/v2/api-docs?group=opennavent-realestate"

# ---------------------------------------------------------------------------
# Path spellings — SETTLED against the generated spec on 2026-08-18.
#
# The hand-written docs and the generated spec disagreed. Probing could not
# settle it: `/v1/**` returns 401 before routing (Spring Security's filter
# chain runs ahead of the dispatcher), so a bogus path answers 401 exactly
# like a real one.
#
# What settled it was reading the vendor's own generated spec from BOTH BR
# hosts (`imovelweb.diagnostics.fetch_swagger`, prod `2.105.01-RC1` /
# sandbox `ON-10172`):
#
#   * `/v1/configuracao/callbacks`      PRESENT (get, put)
#   * `/v1/configuracion/callbacks`     ABSENT
#   * `/v1/callbacks/geracao/eventos`   PRESENT (post) — sandbox host ONLY
#   * `/v1/callbacks/generacion/evento` ABSENT
#
# So the first spelling in each tuple is confirmed and the second is a
# documentation artefact. The losing spellings are KEPT rather than deleted:
# the spec is generated from the running BR code, which makes absence strong
# evidence but not proof — an undocumented alias controller would not appear.
# Gate 1 retires them for good with a credentialed call.
# ---------------------------------------------------------------------------
IMOVELWEB_PATH_VARIANTS: dict[str, tuple[str, ...]] = {
    # (spec spelling first, prose spelling second)
    "callback_config": ("/v1/configuracao/callbacks", "/v1/configuracion/callbacks"),
    "callback_event": (
        "/v1/configuracao/callbacks/{evento}",
        "/v1/configuracion/callbacks/{evento}",
    ),
    "sandbox_emit": (
        "/v1/callbacks/geracao/eventos",
        "/v1/callbacks/generacion/evento",
    ),
}


def preferred_path(key: str) -> str:
    """The spelling to try first — the generated spec's."""
    variants = IMOVELWEB_PATH_VARIANTS.get(key)
    if not variants:
        raise ValueError(f"unknown path key {key!r}")
    return variants[0]


# ---------------------------------------------------------------------------
# Endpoint baseline.
#
# `expected_status` is None on EVERY row, deliberately. A guessed expectation
# makes the probe print `as_expected` for a number we invented, and an
# operator who learns the report lies stops reading it. Gate 1 replaces each
# None with what was OBSERVED.
# ---------------------------------------------------------------------------
IMOVELWEB_ENDPOINT_BASELINE: tuple[dict[str, Any], ...] = (
    {"method": "POST", "path": "/v1/application/login",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "OAuth2 client credentials. Secret rides in the query string as "
              "documented; Gate 0.8 could not test whether Basic + form body "
              "also works, because the grant handler never runs unauthenticated."},
    {"method": "POST", "path": "/v1/application/logout",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Revokes a token. Explicit-only — never a shutdown hook."},
    {"method": "GET", "path": "/v1/configuracao/callbacks",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Read-back half of register-then-diff."},
    {"method": "PUT", "path": "/v1/configuracao/callbacks",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "INTEGRATOR-WIDE — no agency in the path. One bad write "
              "redirects every agency's leads. Confirm-gated everywhere."},
    {"method": "PUT", "path": "/v1/configuracao/callbacks/{evento}",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Subscribe. With no subscriptions nothing is ever delivered."},
    {"method": "DELETE", "path": "/v1/configuracao/callbacks/{evento}",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None, "notes": "Unsubscribe."},
    {"method": "POST", "path": "/v1/callbacks/geracao/eventos",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "SANDBOX ONLY — absent from the prod spec. The event simulator: "
              "the instrument that lets Gate 1 close without live traffic."},
    {"method": "GET", "path": "/v2/imobiliarias/{codigoImobiliaria}/mensagens",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Paged reconciliation read. fromDate=yyyyMMdd."},
    {"method": "GET", "path": "/v1/imobiliarias/{codigoImobiliaria}/mensagens",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "The v1 read. Accepts `yyyyMMdd HH:mm:ss`, so it takes a "
              "narrower window than the v2 paged read."},
    {"method": "GET",
     "path": "/v1/imobiliarias/{codigoImobiliaria}/anuncios/{codigoAnuncio}/mensagens",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Per-listing messages. `ImovelWebAdapter.list_listing_messages` "
              "calls this — it was missing from this baseline until "
              "fetch_swagger diffed the client against the spec on 2026-08-18."},
    {"method": "GET", "path": "/v1/mensagens/{idMensaje}",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Authoritative re-fetch. Background only — an upstream "
              "round-trip does not fit the 1.5s response budget."},
    {"method": "GET", "path": "/v1/mensagen/{idMensagen}/smartLead",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Buyer-intent enrichment. Note the vendor's own typo: "
              "'mensagen', singular-with-n, unlike every sibling path."},
    {"method": "GET", "path": "/v1/imobiliarias/{codigoImobiliaria}/contatos/{idContato}",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Questionnaire answers + smartlead for one contact."},
    {"method": "GET", "path": "/v1/seekers/br/{userIdNavplat}/profile",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Richer seeker profile. Behavioural profiling of an identified "
              "person — LGPD Art. 20 engages if leads are scored on it."},
    {"method": "GET", "path": "/v1/contatos/acoes",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Authoritative contactTypeId catalog. Replaces our transcribed "
              "IMOVELWEB_CONTACT_TYPES at Gate 1.11."},
    {"method": "GET", "path": "/v1/imobiliarias",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Agencies authorized to our integration."},
    {"method": "DELETE", "path": "/v1/imobiliarias/{codigoImobiliaria}/",
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "Unlink an agency. Note the trailing slash — the vendor's."},
    {"method": "GET", "path": IMOVELWEB_SWAGGER_PATH,
     "status": ENDPOINT_UNVERIFIED, "expected_status": None,
     "notes": "PUBLIC, no auth. Prod served 2.105.01-RC1 and sandbox ON-10172 "
              "on 2026-08-17."},
    {"method": "POST", "path": "<our receiver>",
     "status": ENDPOINT_INBOUND, "expected_status": None,
     "notes": "Inbound. Exercised by imovelweb.webhook.simulate."},
)

#: The agency-authorization widget. WE choose CODIGOIMOBILIARIA, which is
#: what makes tenant resolution a pure lookup rather than a guess.
IMOVELWEB_LOGIN_BUTTON_URLS: dict[str, str] = {
    "br": "https://loginbr-open.navent.com/[INTEGRADOR]/[CODIGOIMOBILIARIA].js",
    "ar": "https://login-open.navent.com/[INTEGRADOR]/[CODIGOINMOBILIARIA].js",
    "rela": "https://loginrela-open.navent.com/[INTEGRADOR]/[CODIGOINMOBILIARIA].js",
}

IMOVELWEB_REFERENCE_URLS: dict[str, str] = {
    "docs_br": "https://open-classifieds.notion.site/bra",
    "docs_br_legacy_redirect": "https://open-docs.navent.com/bra/",
    "swagger_prod_br": f"{IMOVELWEB_PROD_BR}{IMOVELWEB_SWAGGER_PATH}",
    "swagger_sandbox_br": f"{IMOVELWEB_SANDBOX_BR}{IMOVELWEB_SWAGGER_PATH}",
    "support_desk": "https://navent.atlassian.net/servicedesk/customer/portal/9",
}

IMOVELWEB_SUPPORT_CONTACTS: dict[str, str] = {
    "credentials_and_callbacks": "integracao@imovelweb.com.br",
    "platform_contact_of_record": "open@navent.com",
    # The OTHER pipe: activating ImovelWeb inside Grupo OLX's Gestor de
    # Leads. Different vendor, different integration, lossy attribution.
    "grupo_olx_bridge_activation": "atendimento@imovelweb.com.br",
}


def base_url(region: str = "br", *, sandbox: bool = False) -> str:
    """Resolve a host. Raises rather than silently falling back to prod —
    a sandbox call that quietly hit production would be a real incident."""
    hosts = IMOVELWEB_HOSTS.get(region)
    if hosts is None:
        raise ValueError(
            f"unknown region {region!r}; known: {', '.join(IMOVELWEB_HOSTS)}"
        )
    url = hosts["sandbox"] if sandbox else hosts["prod"]
    if not url:
        raise ValueError(
            f"no {'sandbox' if sandbox else 'prod'} host known for region {region!r}"
        )
    return url


def is_sandbox_host(url: Optional[str]) -> bool:
    """True only for a known sandbox host.

    Deliberately an allowlist, not a substring heuristic: this gates
    `emit_event`, and a false positive would fire synthetic leads at a
    production integration.
    """
    if not url:
        return False
    normalized = url.rstrip("/")
    return any(
        normalized == hosts["sandbox"].rstrip("/")
        for hosts in IMOVELWEB_HOSTS.values()
        if hosts["sandbox"]
    )


__all__ = [
    "ENDPOINT_ABSENT",
    "ENDPOINT_INBOUND",
    "ENDPOINT_LIVE",
    "ENDPOINT_PERMISSION_GATED",
    "ENDPOINT_UNVERIFIED",
    "ENDPOINT_WRITE_ONLY",
    "IMOVELWEB_ENDPOINT_BASELINE",
    "IMOVELWEB_HOSTS",
    "IMOVELWEB_LOGIN_BUTTON_URLS",
    "IMOVELWEB_PATH_VARIANTS",
    "IMOVELWEB_PROD_AR",
    "IMOVELWEB_PROD_BR",
    "IMOVELWEB_PROD_RELA",
    "IMOVELWEB_REFERENCE_URLS",
    "IMOVELWEB_SANDBOX_BR",
    "IMOVELWEB_SANDBOX_WINDOW",
    "IMOVELWEB_SUPPORT_CONTACTS",
    "IMOVELWEB_SWAGGER_PATH",
    "base_url",
    "is_sandbox_host",
    "preferred_path",
]
