"""
Assistant configuration.

The Assistant shadows one personal WhatsApp line (D46) and, since 2026-11-12, can ANSWER it through the owner's agent
hosted in `agents` (live reply, OFF by default, `ASSISTANT_REPLY_ENABLED`). Every knob that differs between dev and
prod and has no safe shared default is EMPTY here and fails loud when used (a 503 / a refused boot), never a silent
Fake or an unsigned webhook in a real deploy (KB § PATTERNS/devops/deploy-config-contract.md).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Assistant specific settings."""

    cors_origins: str = "@registry:own:assistant"

    # Fernet key of `assistant.whatsapp_connections` (the WAHA api key is encrypted at rest). Unset => the connection
    # routes answer 503 instead of persisting plaintext.
    encryption_key: str = ""

    # -- WhatsApp (WAHA) -------------------------------------------------------------------------------
    # The Assistant's OWN WAHA instance (never the shared core one). Unset => `POST /api/whatsapp/connections`
    # answers 503 "WAHA server not configured".
    assistant_waha_base_url: str = ""
    assistant_waha_session: str = "default"
    # Line policy v1 (JSON, from deploy/fleet/waha-instances.yml). The live reply needs a `send: enabled` line; without a
    # declared policy the seed refuses every write on the line anyway (fail-closed). KB § INTEGRATIONS/whatsapp.md § 6a.
    assistant_waha_line_policy: str = ""
    # REQUIRED: must equal the WAHA instance's global WHATSAPP_HOOK_HMAC_KEY. No secret => the webhook answers 401 to
    # everything and a deploy refuses to boot (plan item 10).
    assistant_waha_webhook_hmac_secret: str = ""
    # Server-side key that HMACs a third party's chat id into the opaque `chat_ref` (LGPD minimisation: no raw phone
    # is stored). REQUIRED; rotating it re-keys future rows only.
    assistant_identity_hmac_key: str = ""
    # Comma-separated phones / chat ids that are never taken in (compared by digits).
    assistant_excluded_numbers: str = ""

    # -- Classifier (S3, classification only) -----------------------------------------------------------
    # Kill switch of the classification worker. It also needs NOCTUS_SCHEDULERS_ENABLED (deployed container only) and
    # an ENFORCED LLM_SPEND_LIMITS entry covering it; missing either => not started, intake rows stay pending.
    assistant_classifier_enabled: bool = True
    # Message text sent to the model is cut at this many characters (per-call cost cap; the cut is recorded).
    assistant_classifier_max_chars: int = 4000

    # -- Google connection (S7, D50) --------------------------------------------------------------------
    # The NoctusAI GCP project's OAuth client (D39): the APP identity, shared by every org. The per-org tokens live
    # encrypted in `assistant.oauth_credentials` (never here). Unset => "Conectar Google" answers 503.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # Optional override of the redirect URI (local dev only); default = <assistant product url>/api/google/oauth/callback.
    google_oauth_redirect_uri: str = ""

    # -- Live reply (owner decision 2026-11-12) ------------------------------------------------------------
    # Product kill switch: OFF => the webhook only shadows (intake + classifier), no turn, no send. The on/off of the
    # agent itself and the allow-list of numbers live in `agents` (the agent's controls); this switch is the second,
    # product-side key.
    assistant_reply_enabled: bool = False
    # The agents channel credential + the agent key are NOT settings: `agents` delivers them as a platform grant
    # (`PUT /api/platform/grants/agents`, stored encrypted in `assistant.agent_grants`, `app.services.agents_grant`) and
    # the base URL resolves like social-wiring's (`PRODUCT_URL_AGENTS`). No grant = the live reply answers nobody.
    # An inbound message older than this (webhook redelivery after an outage) is NOT answered.
    assistant_reply_max_age_seconds: int = 900
    # Pause between two reply bubbles (one WhatsApp message per paragraph).
    assistant_reply_paragraph_delay_seconds: float = 0.6
    # Debounce: a conversation must be quiet this long before its burst of messages becomes ONE agent turn.
    assistant_reply_debounce_seconds: float = 4.0
    #: Comma-separated E.164 numbers of the line owner's OTHER phones: a message from one is sent to agents as
    #: `remetente="dono"` (else "contato"). Empty = nobody is the owner. PII: never logged.
    assistant_owner_numbers: str = ""

    # -- Conversas (the owner's inbox, migration 022) ------------------------------------------------------
    # Inbox realtime (SSE) bus: Redis when REDIS_URL is set; the in-process bus only as a declared single-worker choice
    # (outside a deploy it is always allowed). A deploy with neither refuses to boot (InboxRealtimeNotConfigured).
    assistant_inbox_realtime_in_process: bool = False

    # Rate-limit for the public webhook (per-IP). Public surface -- DDOS guard.
    webhook_rate_limit: str = "60/minute"


settings = SeedSettings()
