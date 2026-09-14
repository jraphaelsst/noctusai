"""
Academia de Reciclagem configuration.

Extends the framework's ProductSettings with the SEED-1 approval-assertion
key list (contract §D) — the shared HMAC secret(s) the `agents` control
plane signs `X-Approval-Assertion` headers with, and academia verifies
against.
"""
from pydantic import field_validator

from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Academia de Reciclagem specific settings."""

    cors_origins: str = "@registry:own:academia-de-reciclagem"

    # ── Approval-assertion keys (contract §D) ──────────────────────────
    # Raw comma-separated string field (NOT `list[str]`) — mirrors the
    # platform's established `cors_origins` idiom
    # (`noctusai_lib.config.settings.BaseAppSettings.cors_origins_list`):
    # `pydantic-settings` attempts a JSON `json.loads()` on ANY complex
    # (list/dict) env-sourced field BEFORE any `field_validator` runs, so
    # a plain `APPROVAL_ASSERTION_SECRETS=key1,key2` env value would raise
    # `SettingsError` at boot for a `list[str]`-typed field — confirmed
    # against this repo's installed `pydantic-settings` 2.5.2. The
    # `_list` property below is the single point every consumer reads;
    # never split `approval_assertion_secrets` ad hoc at a call site.
    #
    # `academia` accepts ANY element (rotation = prepend the new key,
    # deploy both, then drop the old one — contract §D). Empty by
    # default → `required_prod_config` in `app/main.py` aborts boot in a
    # deploy context; never a silent "no key configured" 500 at the
    # first assertion.
    approval_assertion_secrets: str = ""

    @property
    def approval_assertion_secrets_list(self) -> list[str]:
        """Resolve `approval_assertion_secrets` into the concrete key list."""
        return [s.strip() for s in self.approval_assertion_secrets.split(",") if s.strip()]

    @field_validator("approval_assertion_secrets")
    @classmethod
    def _approval_assertion_secrets_no_json_shape(cls, v: str) -> str:
        """Fail loud on a `["a","b"]`-shaped env value — that string
        would silently parse as ONE key (the literal bracketed text)
        instead of the intended list, since this field is a raw `str`
        (see the field docstring for why it isn't `list[str]`)."""
        if v.strip().startswith("["):
            raise ValueError(
                "APPROVAL_ASSERTION_SECRETS is comma-separated "
                "('key1,key2'), not a JSON array — got a JSON-array-"
                f"shaped value: {v!r}"
            )
        return v

    # ── Primary-source host allowlist (contract §B.5 `POST /api/sources`) ──
    # Comma-separated hostnames (same raw-`str` idiom as
    # `approval_assertion_secrets` above — pydantic-settings would choke
    # on a comma-separated value for a `list[str]` field). Empty by
    # default: contract §B.5 defines the AVISO behaviour but not the
    # allowlist's contents, so the safe default is "warn on every host
    # until an operator configures the known primary-source domains"
    # (e.g. `.gov.br` regulatory sites) rather than silently trusting an
    # unconfigured allowlist of unknown provenance.
    primary_source_allowlist: str = ""

    @property
    def primary_source_allowlist_list(self) -> list[str]:
        return [s.strip().lower() for s in self.primary_source_allowlist.split(",") if s.strip()]


settings = SeedSettings()
