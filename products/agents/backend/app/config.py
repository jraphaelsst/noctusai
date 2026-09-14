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
    # Comma-separated in the env var — `agents` SIGNS with element [0]
    # (app/runtime/assertion.py); an academia-side product would ACCEPT any
    # element (not this product's concern). Empty/missing → the product
    # refuses to start in a deploy context (`required_prod_config` at app
    # boot); the key is never exposed to the Julia CLI subprocess (contract
    # §E.5 — the `env -i` wrapper strips it either way).
    approval_assertion_secrets: list[str] = []

    @field_validator("approval_assertion_secrets", mode="before")
    @classmethod
    def _split_csv_secrets(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return v
        return [s.strip() for s in str(v).split(",") if s.strip()]

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

settings = SeedSettings()
