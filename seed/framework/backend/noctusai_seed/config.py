"""
Base configuration for all NoctusAI products.

Products extend ProductSettings with their domain-specific fields.
The structural fields (JWT, CORS, core URL) are standardized here.
"""
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import SettingsConfigDict
from noctusai_lib.config import BaseAppSettings

_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class ProductSettings(BaseAppSettings):
    """Base settings that every product inherits.

    Provides:
      - JWT secret with production safety validation
      - Core API URL for cross-product communication
      - CORS origins

    Products extend this with domain-specific fields::

        class MailingSettings(ProductSettings):
            resend_api_key: str = ""
            max_sends_per_hour: int = 1000
    """

    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    core_api_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Inbound request body cap. Applies to every endpoint via
    # `MaxBodySizeMiddleware`; bumps the 1 MB default for products that
    # legitimately receive large payloads (file-upload-via-webhook, etc.).
    max_body_bytes: int = 1 * 1024 * 1024  # 1 MB

    # Rate limit applied to inbound webhook routes via the product's
    # slowapi `@limiter.limit(settings.webhook_rate_limit)` decorator.
    # Tuned generous-but-not-absurd: providers commonly burst on retry
    # (Meta / Resend redrive a queue on outage), but a single attacker
    # IP shouldn't sustain hundreds per minute. Override per product if
    # legitimate burst exceeds the default.
    webhook_rate_limit: str = "60/minute"

    # ── Dev-auth (pre-seeded local identity) ──────────────────────────
    # Explicit, double-gated bypass for "scaffolded product runs
    # end-to-end on day one" (see noctusai_seed.dev_auth). MUST be off in
    # production: a `seed_dev_auth=True` in a non-debug env still cannot
    # activate (the factory requires BOTH this flag AND `debug`). Set
    # `SEED_DEV_AUTH=true` on the local/template .env, never on prod
    # compose/CI. `local_dev_user_id` / `local_dev_org_id` let a product
    # pin the synthesized identity to its own seeded org row when it has
    # one; defaults are fixed sentinels otherwise.
    seed_dev_auth: bool = False
    local_dev_user_id: str = ""
    local_dev_org_id: str = ""

    # ── Database backend (local-dev SQLite, parallel to Postgres) ─────
    # `supabase` (default) keeps the Postgres/Supabase path 100%
    # unchanged (parallel, never-modify — same discipline as
    # `dev_auth.py`). `sqlite` activates the pre-seeded local-dev
    # backend (`noctusai_seed.apply_sqlite_migrations`) so a scaffolded
    # product runs end-to-end with NO Supabase project provisioned.
    # `sqlite` is double-gated exactly like `seed_dev_auth`: it can
    # NEVER be active in a production-shaped env (the validator below
    # fails loud if `debug` is off). Set `DATABASE_BACKEND=sqlite` only
    # on the local/template .env, never on prod compose/CI.
    database_backend: str = "supabase"
    sqlite_db_path: str = "noctus-dev.sqlite3"

    @field_validator("database_backend")
    @classmethod
    def validate_database_backend(cls, v, info):
        """Constrain values + fail loud if `sqlite` in a prod env.

        Mirrors the ``seed_dev_auth`` guard: a non-debug deploy that
        still carries ``DATABASE_BACKEND=sqlite`` is a misconfiguration
        that would silently swap the prod datastore for an ephemeral
        local file. ``sqlite`` is dev-only by construction.
        """
        allowed = {"supabase", "sqlite"}
        if v not in allowed:
            raise ValueError(
                f"DATABASE_BACKEND must be one of {sorted(allowed)}, got {v!r}."
            )
        debug = info.data.get("debug", True) if info.data else True
        if v == "sqlite" and not debug:
            raise ValueError(
                "SECURITY ERROR: DATABASE_BACKEND=sqlite but debug is off. "
                "The local-dev SQLite backend must NEVER be enabled in "
                "production (it would silently replace the real datastore "
                "with an ephemeral local file). Unset DATABASE_BACKEND (or "
                "set DEBUG=true only in local dev)."
            )
        return v

    @field_validator("seed_dev_auth")
    @classmethod
    def validate_seed_dev_auth(cls, v, info):
        """Fail loud if dev-auth is requested in a production-shaped env.

        Mirrors the ``jwt_secret`` guard: a non-debug deploy that still
        carries ``SEED_DEV_AUTH=true`` is a misconfiguration that would
        otherwise become a silent auth backdoor.
        """
        debug = info.data.get("debug", True) if info.data else True
        if v and not debug:
            raise ValueError(
                "SECURITY ERROR: SEED_DEV_AUTH is true but debug is off. "
                "The dev-auth bypass must NEVER be enabled in production. "
                "Unset SEED_DEV_AUTH (or set DEBUG=true only in local dev)."
            )
        return v

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v, info):
        """Fail if using default JWT secret in production."""
        debug = info.data.get("debug", True) if info.data else True
        if v == "noctus-dev-secret-change-in-prod" and not debug:
            raise ValueError(
                "SECURITY ERROR: JWT_SECRET must be changed from default value in production. "
                "Set JWT_SECRET environment variable to a secure random string."
            )
        return v


def make_get_settings(settings_instance):
    """Factory that creates a product-specific ``get_settings`` FastAPI dependency.

    Sibling of :func:`noctusai_lib.api.auth.make_get_current_user_org`: products
    bind it once at module load with their already-constructed
    ``ProductSettings`` (or subclass) instance, then depend on the returned
    callable wherever a router needs config values::

        # app/dependencies.py
        from noctusai_seed import make_get_settings
        from app.config import settings  # module-level SocialWiringSettings()
        get_settings = make_get_settings(settings)

        # a router
        @router.get("/keys")
        def keys(settings: SocialWiringSettings = Depends(get_settings)):
            return {"configured": bool(settings.youtube_client_id)}

    The point is the **test seam**, not runtime indirection: in production the
    dep just returns the same singleton the module already reads. But because
    it is a FastAPI dependency, tests override the value through the framework's
    own mechanism instead of mutating the module global::

        # honest DI override — no monkeypatch of our own symbol
        app.dependency_overrides[get_settings] = lambda: SocialWiringSettings(
            youtube_client_id="cid", encryption_key="",
        )

    This is the production-DI replacement for the ``settings_override`` conftest
    fixture / direct ``monkeypatch.setattr(settings, "X", "Y")`` pattern that
    trips ``check_no_self_monkeypatch``. The keeper cannot tell a settings-value
    patch from a logic-guard patch; routing config through ``Depends`` removes
    the need to patch the global at all.

    Surfaced as the N>=3 recurrence formalization in
    ``social-wiring-settings-di-rewrite`` (erp-imobiliario / core / daily-life /
    seed all carry the same ``monkeypatch.setattr(settings, ...)`` shape).
    Social-wiring is the first adopter.

    Parameters:
        settings_instance: The product's module-level ``ProductSettings``
            (or subclass) instance. Returned as-is by the dependency.

    Returns:
        A zero-arg callable suitable for ``Depends(...)`` that returns
        ``settings_instance``. Override in tests via
        ``app.dependency_overrides[get_settings] = lambda: <other settings>``.
    """

    def get_settings():
        return settings_instance

    return get_settings
