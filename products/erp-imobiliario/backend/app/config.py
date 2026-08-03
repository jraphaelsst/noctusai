"""
ERP Imobiliario configuration — extends seed framework.
"""
from typing import Optional

from noctusai_seed import ProductSettings


class ERPSettings(ProductSettings):
    """ERP-specific application settings."""

    # CORS — ERP frontend default port
    cors_origins: str = "@registry:own:erp-imobiliario"

    # AI (optional — graceful degradation if not set)
    openai_api_key: Optional[str] = None

    # Email (optional — dry-run if not set)
    resend_api_key: Optional[str] = None
    email_from: str = "noreply@noctus.app"
    email_from_name: str = "NoctusAI ERP"

    # InfoSimples (optional — dry-run if not set)
    infosimples_token: Optional[str] = None

    # Digital signatures (optional — internal mock if not set)
    clicksign_api_token: Optional[str] = None
    clicksign_environment: str = "sandbox"
    docusign_integration_key: Optional[str] = None
    docusign_account_id: Optional[str] = None
    d4sign_api_token: Optional[str] = None
    d4sign_crypt_key: Optional[str] = None

    # Vista CRM showcase (admin-only, backend-only — never VITE_-prefixed).
    # See products/erp-imobiliario/projects/vista-crm-wiring/PROJECT.md.
    vista_base_url: Optional[str] = None
    vista_api_key: Optional[str] = None

    # Direct Postgres connection — used ONLY by the SQLAlchemy session
    # backing the seed `make_audit_writer(db, ToolCallAudit)` contract
    # (`app/services/audit_hook.py`). ERP's primary data path is the
    # Supabase admin client; this URL is opt-in (empty → noop writer).
    # See `KB § PATTERNS/llm-tool-audit.md` for the rollout recipe.
    postgres_url: str = ""

    # Meta App Secret — signs EVERY inbound Lead-Ads webhook POST into
    # `X-Hub-Signature-256`. 🔴 This is NOT `meta_config.webhook_verify_token`:
    # that token answers the one-time GET handshake and proves to META that we
    # own the URL, while THIS secret proves to US that a POST came from Meta.
    # Conflating them was a live defect here (`routers/meta_api.py` resolved
    # the verify token as the signing secret, so the receiver could never
    # validate genuine Meta traffic). Empty ⇒ the receiver 401s every POST,
    # which is the correct posture for an unconfigured webhook — never
    # "accept unverified".
    meta_app_secret: str = ""


settings = ERPSettings()
