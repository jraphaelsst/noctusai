"""
Agentes configuration.

Extends the framework's ProductSettings — minimal additions to support
the inherited skeletons (webhook receiver, etc.), plus the G2 runtime +
gate fields per contract §E.9 / §E.5 / §D
(``projects/julia-agents-academia-CONTRACT.md``).

NOC-REMEDIATE[config-merge]: ``approval_assertion_secrets`` /
``approval_timeout_seconds`` / ``anthropic_api_key`` are ALSO declared by
G1b's in-flight ``feat/agents-api-routes`` branch (routes need them too —
same settings object, two parallel slices). Field names/types/defaults
below were mirrored from that branch's uncommitted diff to keep the merge
a no-op on these fields; the tech-lead reconciles the two diffs at
integration. — 2026-09-14.
"""
from __future__ import annotations

from pydantic import field_validator

from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Agentes specific settings."""

    cors_origins: str = "@registry:own:agents"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    webhook_rate_limit: str = "60/minute"

    # ── Approvals (contract §E.2 / §D) ─────────────────────────────────
    # An unanswered approval request becomes `expirada` after this many
    # seconds; the waiting tool call is then denied (app/runtime/broker.py).
    approval_timeout_seconds: int = 900

    # `X-Approval-Assertion` HS256 signing keys (contract §D). Comma-separated
    # in the env var. `agents` SIGNS with element [0] (app/runtime/assertion.py).
    # Empty/missing → the product refuses to start in a deploy context
    # (`required_prod_config` at app boot); never exposed to the Julia CLI
    # subprocess (contract §E.5 — the `env -i` wrapper strips it either way).
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


settings = SeedSettings()
