"""
Academia de Reciclagem configuration.

Extends the framework's ProductSettings with the SEED-1 approval-assertion
key list (contract §D) — the shared HMAC secret(s) the `agents` control
plane signs `X-Approval-Assertion` headers with, and academia verifies
against.
"""
from pydantic import field_validator

from noctusai_lib.config.csv_settings import parse_csv_setting, reject_json_array
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Academia de Reciclagem specific settings."""

    cors_origins: str = "@registry:own:academia-de-reciclagem"

    # ── Approval-assertion keys (contract §D) ──────────────────────────
    # Raw comma-separated string field (NOT `list[str]`) — the platform's
    # established CSV-setting idiom, see `noctusai_lib.config.csv_settings`
    # for why (`pydantic-settings` JSON-decodes any complex env-sourced
    # field BEFORE any `field_validator` runs — confirmed against this
    # repo's installed `pydantic-settings` 2.5.2). The `_list` property
    # below is the single point every consumer reads; never split
    # `approval_assertion_secrets` ad hoc at a call site.
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
        return parse_csv_setting(self.approval_assertion_secrets)

    @field_validator("approval_assertion_secrets")
    @classmethod
    def _approval_assertion_secrets_no_json_shape(cls, v: str) -> str:
        """Fail loud on a `["a","b"]`-shaped env value — that string
        would silently parse as ONE key (the literal bracketed text)
        instead of the intended list, since this field is a raw `str`
        (see the field docstring for why it isn't `list[str]`)."""
        return reject_json_array(v, "APPROVAL_ASSERTION_SECRETS")

    # ── Rotating ring published by `agents` (contract §D "Rotation") ───
    # The `agents` control plane stores the §D key ring encrypted in
    # `agents.app_integration_config` under `approval_assertion_ring_key`
    # (Fernet, the fleet-wide `ENCRYPTION_KEY`). When that row exists it
    # WINS over `approval_assertion_secrets` above — the SAME DB-first /
    # env-fallback rule `agents` signs with
    # (`noctusai_lib.security.key_ring.resolve_key_ring`), which is what
    # keeps a UI-driven rotation consistent on both sides by construction.
    # A missing/invalid `ENCRYPTION_KEY` degrades to the env list (logged).
    encryption_key: str = ""
    approval_assertion_ring_schema: str = "agents"
    approval_assertion_ring_key: str = "approval_assertion_secrets:academia-de-reciclagem"

    # ── Primary-source host allowlist (contract §B.5 `POST /api/sources`) ──
    # Comma-separated hostnames (same raw-`str` CSV-setting idiom as
    # `approval_assertion_secrets` above). Empty by
    # default: contract §B.5 defines the AVISO behaviour but not the
    # allowlist's contents, so the safe default is "warn on every host
    # until an operator configures the known primary-source domains"
    # (e.g. `.gov.br` regulatory sites) rather than silently trusting an
    # unconfigured allowlist of unknown provenance.
    primary_source_allowlist: str = ""

    @property
    def primary_source_allowlist_list(self) -> list[str]:
        return parse_csv_setting(self.primary_source_allowlist, lower=True)


settings = SeedSettings()
