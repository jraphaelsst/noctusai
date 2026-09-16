"""
Agentes configuration.

Extends the framework's ProductSettings with the G1b (agents API + SSE)
and G2 (runtime + gate) fields per contract §E / §E.5 / §E.9 / §D / §F
(``projects/julia-agents-academia-CONTRACT.md``). Both slices needed the
same settings object; reconciled here at integration into one declaration
per field (``NOC-REMEDIATE[config-merge]`` closed).
"""
from __future__ import annotations

from pydantic import field_validator

from noctusai_lib.config.csv_settings import parse_csv_setting, reject_json_array
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Agentes specific settings."""

    cors_origins: str = "@registry:own:agents"

    # ── social-wiring bridge client (contract §E.6) ────────────────────
    # Token held by the agents product to call social-wiring's
    # `agents-bridge` routes (`social-wiring:one-chat:read` +
    # `:toggle` scopes only). Never logged.
    social_wiring_api_token: str = ""

    # ── Approvals (contract §E.2 / §D) ──────────────────────────────────
    # An unanswered approval request becomes `expirada` after this many
    # seconds; the waiting tool call is then denied (app/runtime/broker.py).
    approval_timeout_seconds: int = 900

    # Contract §E.10 (security review 2026-09-14): the escrita handler
    # refuses `approval_invalid` once `decided_at` is older than this —
    # bounds how long a valid, unconsumed approval stays usable between a
    # human's decision and the tool call actually reaching academia
    # (app/runtime/tools.py's `_escrita` handler).
    approval_use_window_seconds: int = 120

    # `X-Approval-Assertion` HS256 signing/verification keys (contract §D).
    # Raw comma-separated string field (NOT `list[str]`) — the platform's
    # established CSV-setting idiom (see
    # `noctusai_lib.config.csv_settings` for why): `pydantic-settings`
    # 2.5.2 JSON-decodes any complex (list/dict) env-sourced field BEFORE
    # any `field_validator` runs, so a plain
    # `APPROVAL_ASSERTION_SECRETS=key1,key2` env value raised
    # `SettingsError` at boot for a `list[str]`-typed field — confirmed
    # against this repo's installed `pydantic-settings` 2.5.2 (D1
    # boot-crash fix). `agents` SIGNS with element [0] of
    # `approval_assertion_secrets_list` (app/runtime/assertion.py); an
    # academia-side product would ACCEPT any element (not this product's
    # concern). Empty/missing → the product refuses to start in a deploy
    # context (`required_prod_config` at app boot); the key is never
    # exposed to the Julia CLI subprocess (contract §E.5 — the `env -i`
    # wrapper strips it either way). The `_list` property below is the
    # single point every consumer reads; never split
    # `approval_assertion_secrets` ad hoc at a call site.
    approval_assertion_secrets: str = ""

    @property
    def approval_assertion_secrets_list(self) -> list[str]:
        """Resolve `approval_assertion_secrets` into the concrete key list."""
        return parse_csv_setting(self.approval_assertion_secrets)

    @field_validator("approval_assertion_secrets")
    @classmethod
    def _approval_assertion_secrets_no_json_shape(cls, v: str) -> str:
        """Fail loud on a `["a","b"]`-shaped env value — that string would
        silently parse as ONE key (the literal bracketed text) instead of
        the intended list, since this field is a raw `str` (see the field
        docstring for why it isn't `list[str]`)."""
        return reject_json_array(v, "APPROVAL_ASSERTION_SECRETS")

    # ── Julia runtime (contract §E.5 / §E.9) ───────────────────────────
    # Dedicated, spend-capped key for Julia's workspace — never shared
    # with any other product's LLM calls. Consumed by
    # `app.runtime.get_agent_runtime`; re-exported into the CLI subprocess
    # env by `bin/julia-cli-exec` ONLY (never passed via `options.env`).
    anthropic_api_key: str = ""

    # Product token the control plane sends as `Authorization: Bearer` when
    # calling academia-de-reciclagem's HTTP API from the in-process MCP
    # tool proxies (contract §C / §E.5 "How tools reach academia"). Never
    # reaches the Julia CLI subprocess.
    academia_api_token: str = ""

    # The `agents.agents` row id for the `julia` key — contract §D `sub`
    # claim. ONE agents deployment holds exactly ONE `ACADEMIA_API_TOKEN`
    # (a single product token, not per-org — contract §B.0), and that
    # token's `principal_agent_id` is set ONCE when it is minted; this
    # value must equal it exactly, or every §D step 5 verification on the
    # academia side fails. Set alongside `ACADEMIA_API_TOKEN` at deploy
    # time (same secret-provisioning step, never guessed at runtime).
    julia_agent_id: str = ""

    # Per-user rate limit on `POST /api/conversations/{id}/messages`
    # (contract §E "Rate limit ... per user with the product limiter").
    messages_rate_limit: str = "20/minute"

    # ── Julia CLI path (contract §E.5, roadmap D1) ──────────────────────
    # Where the `env -i` wrapper (`bin/julia-cli-exec`) lands inside the
    # image. Was a bare Python literal duplicated in two places with no
    # link between them — `app/runtime/claude_runtime.py::DEFAULT_CLI_PATH`
    # and the Dockerfile's `COPY ... /app/bin/julia-cli-exec` — so the two
    # could silently drift (a Dockerfile relocation with no matching code
    # change would fail every real Julia turn at subprocess-spawn time,
    # never at build or test time). This field is now the single
    # deploy-configurable source of truth: `get_agent_runtime` reads it
    # and passes it to `ClaudeAgentSdkRuntime`, so the code default and
    # the image layout only need to agree ONCE (here), and an operator
    # can still override via `JULIA_CLI_PATH` if the image layout ever
    # changes without a code change.
    julia_cli_path: str = "/app/bin/julia-cli-exec"

    # ── Per-conversation isolation (contract §E.11) ─────────────────────
    # Fixed slot count: uid/gid `2000+K` for K in `range(julia_cli_slots)`,
    # each with its own tmpfs mount `/run/julia-K`. `app.runtime.slots.
    # RealSlotPool` reads this (falling back to the bare `JULIA_CLI_SLOTS`
    # env var, then to 3) to discover the fixed slot set. User decision
    # 2026-09-15: 3 slots.
    julia_cli_slots: int = 3

settings = SeedSettings()
