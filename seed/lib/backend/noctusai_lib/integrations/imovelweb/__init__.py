"""ImovelWeb / OpenNavent portal leads (Navent · Grupo QuintoAndar).

**Not Grupo OLX.** ImovelWeb, Wimoveis and Casa Mineira belong to Navent,
whose real-estate operations QuintoAndar acquired in 2022. Grupo OLX does
publish an ImovelWeb bridge for its own Gestor de Leads, so one enquiry can
reach us down two pipes — but that bridge stamps leads `leadOrigin: "Grupo
OLX"` and loses the portal name, which is why this direct integration
exists. → `KB § INTEGRATIONS/imovelweb.md`

Two directions:

* **Inbound** — the vendor POSTs one event per request at a URL we register.
  A pure parser plus a receiver; no adapter, because a Fake here would
  exercise no code the Real one does. `parse_imovelweb_callback` +
  `imovelweb_lead_to_lead_payload`.
* **Outbound** — auth, callback registration, reconciliation and enrichment
  are real HTTP, and ship the full Protocol + Fake + Real + factory quartet.

Three vendor facts that shape everything downstream:

1. **1.5 seconds** to answer, or it is scored a timeout. That rules out
   tenant resolution, listing lookups and authoritative re-fetch inside the
   request — persist once, answer, then process.
2. **72 hours** of retries, then the callback goes `VENCIDO`. Combined with
   the pull API, a miss is *recoverable*: reconciliation, not the webhook,
   is the durability guarantee. That is what makes the tight budget
   survivable.
3. **No signature.** Only the static header we ourselves registered. TLS and
   idempotency on `eventId` are the compensations, and the body is a hint
   rather than truth for anything that matters.

**Status: TRANSCRIBED, NOT VERIFIED.** Every `FieldSpec.verified` is False
and every endpoint-baseline expected status is None until an observation
flips it. → `projects/imovelweb-portal-leads-ingestion/PROJECT.md`
"""

from __future__ import annotations

from .auth import (
    REFRESH_SKEW_SECONDS,
    AccessToken,
    ImovelWebAuth,
    InMemoryTokenCache,
    TokenCache,
    parse_expiry,
    token_from_payload,
)
from .contract import (
    IMOVELWEB_FIELD_SPECS,
    IMOVELWEB_RESPONSE_SEMANTICS,
    IMOVELWEB_RETRY_POLICY,
    IMOVELWEB_SAMPLE_BODIES,
    LANGUAGE_FIELD_ALIASES,
    FieldSpec,
    contract_summary,
    diff_observed,
    has_blocking_violation,
    imovelweb_json_schema,
    validate_imovelweb_payload,
)
from .endpoints import (
    IMOVELWEB_ENDPOINT_BASELINE,
    IMOVELWEB_HOSTS,
    IMOVELWEB_LOGIN_BUTTON_URLS,
    IMOVELWEB_PATH_VARIANTS,
    IMOVELWEB_PROD_BR,
    IMOVELWEB_REFERENCE_URLS,
    IMOVELWEB_SANDBOX_BR,
    IMOVELWEB_SANDBOX_WINDOW,
    IMOVELWEB_SUPPORT_CONTACTS,
    IMOVELWEB_SWAGGER_PATH,
    base_url,
    is_sandbox_host,
    preferred_path,
)
from .errors import (
    ImovelWebConfigError,
    ImovelWebError,
    ImovelWebUpstreamError,
    redact_secrets,
)
from .factory import make_imovelweb_client
from .fake import FakeImovelWebClient
from .protocol import ImovelWebAdapter
from .real import (
    DEFAULT_TIMEOUT_SECONDS,
    RATE_LIMIT_BUCKET,
    ImovelWebClient,
    describe_error_body,
)
from .normalizers import (
    IMOVELWEB_DEFAULT_SOURCE_SLUG,
    IMOVELWEB_ORIGIN_SLUGS,
    IMOVELWEB_PIPE,
    imovelweb_lead_to_lead_payload,
    imovelweb_timestamp_to_date,
    render_observacoes,
    resolve_source_slug,
)
from .types import (
    IMOVELWEB_CALLBACK_LANGUAGES,
    IMOVELWEB_CONTACT_TYPES,
    IMOVELWEB_EVENT_TYPES,
    IMOVELWEB_LEAD_EVENT_TYPES,
    IMOVELWEB_LEAD_ORIGINS,
    CallbackConfig,
    ImovelWebLead,
)
from .webhook import detect_callback_language, parse_imovelweb_callback

__all__ = [
    # types
    "CallbackConfig",
    "ImovelWebLead",
    "IMOVELWEB_CALLBACK_LANGUAGES",
    "IMOVELWEB_CONTACT_TYPES",
    "IMOVELWEB_EVENT_TYPES",
    "IMOVELWEB_LEAD_EVENT_TYPES",
    "IMOVELWEB_LEAD_ORIGINS",
    # contract
    "FieldSpec",
    "IMOVELWEB_FIELD_SPECS",
    "IMOVELWEB_RESPONSE_SEMANTICS",
    "IMOVELWEB_RETRY_POLICY",
    "IMOVELWEB_SAMPLE_BODIES",
    "LANGUAGE_FIELD_ALIASES",
    "contract_summary",
    "diff_observed",
    "has_blocking_violation",
    "imovelweb_json_schema",
    "validate_imovelweb_payload",
    # inbound parsing
    "detect_callback_language",
    "parse_imovelweb_callback",
    # normalization
    "IMOVELWEB_DEFAULT_SOURCE_SLUG",
    "IMOVELWEB_ORIGIN_SLUGS",
    "IMOVELWEB_PIPE",
    "imovelweb_lead_to_lead_payload",
    "imovelweb_timestamp_to_date",
    "render_observacoes",
    "resolve_source_slug",
    # endpoints
    "IMOVELWEB_ENDPOINT_BASELINE",
    "IMOVELWEB_HOSTS",
    "IMOVELWEB_LOGIN_BUTTON_URLS",
    "IMOVELWEB_PATH_VARIANTS",
    "IMOVELWEB_PROD_BR",
    "IMOVELWEB_REFERENCE_URLS",
    "IMOVELWEB_SANDBOX_BR",
    "IMOVELWEB_SANDBOX_WINDOW",
    "IMOVELWEB_SUPPORT_CONTACTS",
    "IMOVELWEB_SWAGGER_PATH",
    "base_url",
    "is_sandbox_host",
    "preferred_path",
    # errors
    "ImovelWebConfigError",
    "ImovelWebError",
    "ImovelWebUpstreamError",
    "redact_secrets",
    # auth
    "AccessToken",
    "ImovelWebAuth",
    "InMemoryTokenCache",
    "REFRESH_SKEW_SECONDS",
    "TokenCache",
    "parse_expiry",
    "token_from_payload",
    # adapter quartet — Protocol + Fake + Real + factory, shipped whole
    "DEFAULT_TIMEOUT_SECONDS",
    "FakeImovelWebClient",
    "ImovelWebAdapter",
    "ImovelWebClient",
    "RATE_LIMIT_BUCKET",
    "describe_error_body",
    "make_imovelweb_client",
]
