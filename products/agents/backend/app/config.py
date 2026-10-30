"""
Agentes configuration.

Extends the framework's ProductSettings with the G1b (agents API + SSE)
and G2 (runtime + gate) fields per contract §E / §E.5 / §E.9 / §D / §F
(``projects/julia-agents-academia-CONTRACT.md``). Both slices needed the
same settings object; reconciled here at integration into one declaration
per field (``NOC-REMEDIATE[config-merge]`` closed).
"""
from __future__ import annotations

from pydantic import AliasChoices, Field, field_validator, model_validator

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
    # Default 300 (user decision 2026-09-15, down from 900, contract
    # §E.11 "Timeout") — a waiting approval holds one of Bia's three
    # slots, so the timeout also bounds how long a pending approval can
    # block a slot from returning to the pool.
    approval_timeout_seconds: int = 300

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
    # exposed to the Bia CLI subprocess (contract §E.5 — the `env -i`
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

    # ── Bia runtime (contract §E.5 / §E.9) ───────────────────────────
    # Dedicated, spend-capped key for Bia's workspace — never shared
    # with any other product's LLM calls. Consumed by
    # `app.runtime.get_agent_runtime`; re-exported into the CLI subprocess
    # env by `bin/bia-cli-exec` ONLY (never passed via `options.env`).
    anthropic_api_key: str = ""

    # Product token the control plane sends as `Authorization: Bearer` when
    # calling academia-de-reciclagem's HTTP API from the in-process MCP
    # tool proxies (contract §C / §E.5 "How tools reach academia"). Never
    # reaches the Bia CLI subprocess.
    academia_api_token: str = ""

    # NOC-REMEDIATE[agents-legacy-runtime-names]: `bia_agent_id` / `bia_max_turns` / `bia_cli_path` /
    # `bia_cli_slots` are the env + credential names of the legacy `claude_sdk` chat runtime, which only the
    # academia agent runs. Every ROUTE is de-pinned (agents-unified CONTRACT §5); these names go with that runtime
    # in the Renata cutover slice (products/agents/projects/agents-unified/CONTRACT.md §8) — 2026-10-29.
    # The `agents.agents` row id for the `bia` key — contract §D `sub`
    # claim. ONE agents deployment holds exactly ONE `ACADEMIA_API_TOKEN`
    # (a single product token, not per-org — contract §B.0), and that
    # token's `principal_agent_id` is set ONCE when it is minted; this
    # value must equal it exactly, or every §D step 5 verification on the
    # academia side fails. Set alongside `ACADEMIA_API_TOKEN` at deploy
    # time (same secret-provisioning step, never guessed at runtime).
    # NOC-REMEDIATE[drop-julia-env-alias]: the pre-rename env name (JULIA_AGENT_ID) is still read for one
    # release so a prod .env/.env.fleet not yet updated keeps working — 2026-10-19.
    bia_agent_id: str = Field(
        default="",
        validation_alias=AliasChoices("bia_agent_id", "julia_agent_id"),
    )

    # Per-user rate limit on `POST /api/conversations/{id}/messages`
    # (contract §E "Rate limit ... per user with the product limiter").
    messages_rate_limit: str = "20/minute"

    # ── Credential store (contract §B.0 / §E.5 notes, 2026-09-16) ───────
    # Every secret above is resolved DB-first (`agents.app_integration_
    # config`, Fernet-encrypted with this key — the fleet-wide
    # `ENCRYPTION_KEY`) with the env value as fallback; see
    # `app/credentials/`. Empty/invalid key => the store is disabled
    # (env-only) and writes from the Credenciais page are refused (503).
    encryption_key: str = ""

    # How stale a DB-stored credential may be in ANOTHER worker process
    # after an in-app change (the writing process sees it at once). Bounds
    # "picks up a changed value without a redeploy".
    credential_cache_ttl_seconds: int = 30

    # Days before expiry at which a product token raises the in-app
    # warning + the platform-admin notification (contract D1 deferral).
    credential_expiry_warning_days: int = 30

    # §D rotation timing (Credenciais page). The new key is staged and
    # accepted by academia at once but only SIGNED with after
    # `approval_key_activation_delay_seconds` (> both products' credential
    # cache TTL); the old key stays accepted for
    # `approval_key_retire_after_seconds` after the switch.
    approval_key_activation_delay_seconds: int = 120
    approval_key_retire_after_seconds: int = 86400

    # Contract §E.5 `max_turns=<config, default 40>`. `None` => the value
    # in `agents/bia/spec.yaml`. An admin override lives in
    # `agents.runtime_settings` (Configurações do agente page) and wins.
    # NOC-REMEDIATE[drop-julia-env-alias]: the pre-rename env name (JULIA_MAX_TURNS) is still read for one
    # release so a prod .env/.env.fleet not yet updated keeps working — 2026-10-19.
    bia_max_turns: int | None = Field(
        default=None,
        validation_alias=AliasChoices("bia_max_turns", "julia_max_turns"),
    )

    # ── Bia CLI path (contract §E.5, roadmap D1) ──────────────────────
    # Where the `env -i` wrapper (`bin/bia-cli-exec`) lands inside the
    # image. Was a bare Python literal duplicated in two places with no
    # link between them — `app/runtime/claude_runtime.py::DEFAULT_CLI_PATH`
    # and the Dockerfile's `COPY ... /app/bin/bia-cli-exec` — so the two
    # could silently drift (a Dockerfile relocation with no matching code
    # change would fail every real Bia turn at subprocess-spawn time,
    # never at build or test time). This field is now the single
    # deploy-configurable source of truth: `get_agent_runtime` reads it
    # and passes it to `ClaudeAgentSdkRuntime`, so the code default and
    # the image layout only need to agree ONCE (here), and an operator
    # can still override via `BIA_CLI_PATH` if the image layout ever
    # changes without a code change.
    # NOC-REMEDIATE[drop-julia-env-alias]: the pre-rename env name (JULIA_CLI_PATH) is still read for one
    # release so a prod .env/.env.fleet not yet updated keeps working — 2026-10-19.
    bia_cli_path: str = Field(
        default="/app/bin/bia-cli-exec",
        validation_alias=AliasChoices("bia_cli_path", "julia_cli_path"),
    )

    # ── Provider-neutral runtime (`runtime='llm'`, Lais A1) ─────────────
    # Concurrent in-process LLM turns (no subprocess, so no uid slots —
    # `app.runtime.llm_runtime.LlmTurnLimiter`); a full limiter is a 429
    # `capacidade`.
    llm_turn_capacity: int = 8
    # Memory per turn: the last N stored messages of the conversation.
    llm_history_messages: int = 20
    # Cap on tool-call rounds per turn (also bounded by the version's
    # `max_turns`).
    llm_max_tool_iterations: int = 6
    # Per-ORG daily spend cap in USD over the stored turn costs
    # (`agents.messages.custo_usd`); 0 disables it. The seed's monthly BRL
    # budget (`org_settings.monthly_llm_budget_brl`) applies on top, always.
    llm_daily_budget_usd: float = 0.0

    # ── Channel turn API (Lais A2, contract §3 / §10.1 M4 + M5) ──────────
    # Per-ORG daily spend cap (USD) for CHANNEL turns (a lead on a transport
    # such as WhatsApp). Unlike `llm_daily_budget_usd` it is ON by default: a
    # flood of inbound messages must hit a 429 `capacidade` out of the box,
    # not only after someone remembered to configure a cap. 0 disables it.
    channel_daily_budget_usd: float = 5.0
    # The synchronous hop's budget: the transport waits at most 60 s, so the
    # turn stops here first (and answers 502 `llm_upstream`, no reply).
    channel_turn_timeout_seconds: int = 55
    # LGPD retention (M5): a channel conversation idle for this long is purged
    # by the daily cron.
    channel_retention_days: int = 180
    # The channel token (§4): 30 days, overlapping rotation.
    channel_token_ttl_days: int = 30

    # ── Per-conversation isolation (contract §E.11) ─────────────────────
    # Fixed slot count: uid/gid `2000+K` for K in `range(bia_cli_slots)`,
    # each with its own tmpfs mount `/run/bia-K`. `app.runtime.slots.
    # RealSlotPool` reads this (falling back to the bare `BIA_CLI_SLOTS`
    # env var, then to 3) to discover the fixed slot set. User decision
    # 2026-09-15: 3 slots.
    # NOC-REMEDIATE[drop-julia-env-alias]: the pre-rename env name (JULIA_CLI_SLOTS) is still read for one
    # release so a prod .env/.env.fleet not yet updated keeps working — 2026-10-19.
    bia_cli_slots: int = Field(
        default=3,
        validation_alias=AliasChoices("bia_cli_slots", "julia_cli_slots"),
    )

    # ── Turn deadline + lock TTL (contract §E.11 "Route order") ─────────
    # A turn's whole `run_turn(...)` iteration is wrapped in
    # `asyncio.timeout(turn_timeout_seconds)` (app/routers/
    # conversations_router.py::_run_turn_background). Default 600 —
    # generous headroom over a real Bia turn, bounded so a stuck
    # subprocess can never hold a slot forever.
    turn_timeout_seconds: int = 600

    # How long `POST .../messages` holds the per-conversation turn lock
    # before another request is allowed to reclaim it (crash recovery).
    # Was a bare module constant in conversations_router.py; moved here
    # so the invariant below can be enforced once, at settings
    # construction, instead of scattered across call sites.
    turn_lock_ttl_seconds: int = 900

    # ── Agent Studio — eval run cost cap (contract §L "Controle de
    # custo") ─────────────────────────────────────────────────────────
    # Default `limite_usd` for `POST .../evals/runs` when the request omits
    # it — `app.studio.evals.EvalRunner` stops starting new cases once the
    # run's accumulated `custo_usd` reaches this. `STUDIO_EVAL_RUN_BUDGET_
    # USD` env override; the request body can still set a higher (<= 50,
    # migration 014 CHECK) or lower per-run value.
    studio_eval_run_budget_usd: float = 2.00
    # Cost cap for `POST .../draft/mecanismo-runs` (the multi-turn mechanism suite, LIVE model).
    # `STUDIO_MECANISMO_RUN_BUDGET_USD` env override. A run that reaches it is cut short and never
    # opens the publish gate.
    studio_mecanismo_run_budget_usd: float = 5.00

    # ── Public ask (projects/limiar-open-question S3) ──────────────────
    # The anonymous `POST /api/public/ask/{app_slug}` surface. OFF by default:
    # the route 404s until the owner's public-surface consent
    # (`noctus.dev.prod_consent`) — `PUBLIC_ASK_ENABLED=true` is the switch.
    public_ask_enabled: bool = False
    # Decision Board `nnl-classifier-outage` (OPEN): what an unavailable /
    # indeterminate classifier answers. "amarelo_editorial" (recommended) |
    # "seguranca". Rules-red always wins either way.
    on_classifier_outage: str = "amarelo_editorial"
    # Global daily cost circuit breaker (model-spending requests per UTC day).
    public_ask_daily_call_cap: int = 2000
    # Where the Limiar agent's curated knowledge lives. Unset ⇒ no retrieval
    # ⇒ the editorial fallback (never an improvised answer).
    public_ask_org_id: str = ""
    public_ask_agent_id: str = ""
    public_ask_colecao: str = ""

    @field_validator("on_classifier_outage")
    @classmethod
    def _on_classifier_outage_known(cls, v: str) -> str:
        if v not in ("amarelo_editorial", "seguranca"):
            raise ValueError('on_classifier_outage must be "amarelo_editorial" or "seguranca"')
        return v

    @model_validator(mode="after")
    def _turn_lock_ttl_outlives_turn_timeout(self) -> "SeedSettings":
        """Fail loud at boot (contract §E.11 "Route order": "`_TURN_LOCK_
        TTL_SECONDS` must stay greater than `TURN_TIMEOUT_SECONDS`") — a
        lock TTL at or below the turn deadline would let a SECOND request
        reclaim the lock via crash-recovery while the FIRST turn is still
        legitimately running (merely slow, not crashed), corrupting the
        "at most one live turn per conversation" invariant this lock
        exists to enforce."""
        if self.turn_lock_ttl_seconds <= self.turn_timeout_seconds:
            raise ValueError(
                "turn_lock_ttl_seconds "
                f"({self.turn_lock_ttl_seconds}) must be greater than "
                f"turn_timeout_seconds ({self.turn_timeout_seconds}) — a "
                "turn that legitimately runs right up to its own deadline "
                "must never have its lock reclaimed as if it had crashed."
            )
        return self

settings = SeedSettings()
