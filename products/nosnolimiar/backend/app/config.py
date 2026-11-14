"""
Nós no Limiar configuration.

Extends the framework's ProductSettings -- the CRM of Monica Tangerino's psychoanalysis practice. Every knob
that differs between dev and prod and has no safe shared default is EMPTY here and fails loud when used (a 503
with a clear message), never a silent Fake in a real deploy (KB § PATTERNS/devops/deploy-config-contract.md).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Nós no Limiar specific settings."""

    cors_origins: str = "@registry:own:nosnolimiar"

    # Fernet key of `nosnolimiar.whatsapp_connections` (the WAHA api key is encrypted at rest). Unset => the connection
    # routes answer 503 instead of persisting plaintext (`noctusai_lib.security.api_keys.require_fernet`).
    encryption_key: str = ""

    # -- WhatsApp (WAHA) ---------------------------------------------------------------------------
    # Nós no Limiar's OWN WAHA instance. There is deliberately NO default: the shared WAHA on the fleet is a CORE-tier,
    # single-session instance used by social-wiring's "One Chat" number -- it must never be reused. Unset =>
    # `POST /api/whatsapp/connections` answers 503 "WAHA server not configured" (never a Fake in prod).
    nosnolimiar_waha_base_url: str = ""
    nosnolimiar_waha_session: str = "default"
    # Line policy v1 (JSON; declared in deploy/fleet/waha-instances.yml, keeper-checked against the prod compose). Without
    # it the seed REFUSES every write on Nós no Limiar's line (fail-closed). KB § INTEGRATIONS/whatsapp.md § 6a.
    nosnolimiar_waha_line_policy: str = ""
    # Must equal the global WHATSAPP_HOOK_HMAC_KEY of that WAHA instance (the seed registers `hmac: None` per hook).
    nosnolimiar_waha_webhook_hmac_secret: str = ""
    # Inbox realtime (SSE) bus: Redis when REDIS_URL is set. The in-process bus is a single-worker decision that
    # must be declared (never inferred in a deploy): NOSNOLIMIAR_INBOX_REALTIME_IN_PROCESS=true.
    redis_url: str = ""
    nosnolimiar_inbox_realtime_in_process: bool = False

    # -- Contexto (org specs live in the agents product) --------------------------------------------
    # Base URL of the agents product; empty => resolved from PRODUCT_URL_AGENTS / the catalog. The fake client is
    # a dev/test-only choice (AGENTS_ALLOW_FAKE=true) -- unset in a deploy => 503, not scripted answers.
    agents_url: str = ""
    agents_allow_fake: bool = False
    # The agent DEFINITION whose org specs this page edits (Nós no Limiar's future lead agent -- not activated anywhere).
    nosnolimiar_agent_key: str = "nosnolimiar-leads"


settings = SeedSettings()
