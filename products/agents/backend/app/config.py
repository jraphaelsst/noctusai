"""
Agentes configuration.

Extends the framework's ProductSettings with the G1b (agents API + SSE)
and G2 (runtime + gate) fields per contract §E / §E.5 / §E.9 / §D / §F
(``projects/julia-agents-academia-CONTRACT.md``). Both slices needed the
same settings object; reconciled here at integration into one declaration
per field (``NOC-REMEDIATE[config-merge]`` closed).
"""
from __future__ import annotations

from pydantic import field_validator, model_validator

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
    # §E.11 "Timeout") — a waiting approval holds one of Julia's three
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
    # in `agents/julia/spec.yaml`. An admin override lives in
    # `agents.runtime_settings` (Configurações do agente page) and wins.
    julia_max_turns: int | None = None

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

    # ── Turn deadline + lock TTL (contract §E.11 "Route order") ─────────
    # A turn's whole `run_turn(...)` iteration is wrapped in
    # `asyncio.timeout(turn_timeout_seconds)` (app/routers/
    # conversations_router.py::_run_turn_background). Default 600 —
    # generous headroom over a real Julia turn, bounded so a stuck
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
