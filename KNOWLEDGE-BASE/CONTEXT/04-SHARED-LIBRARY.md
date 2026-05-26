# NoctusAI Shared Library Catalog

> Check here before building anything new. If it exists, use it.

## Backend: `noctusai_lib` (Python)

Install: `pip install -e seed/lib/backend`. Import: `from noctusai_lib.<module> import ...`

### `auth.py` — Authentication & SSO

| Function | Purpose |
|----------|---------|
| `first_or_none(result)` | Extract first record from Supabase response |
| `resolve_sso_role(user)` | Check SSO metadata → `"platform_admin"` or `None` |
| `get_sso_context(user)` | Extract all SSO context (role, org, plan, license) |
| `make_require_role(get_current_user_fn, get_user_role_fn)` | Factory for product-specific `require_role(*roles)` dependency factory. Mirrors `make_get_current_user`: products bind once at module load, then use `Depends(require_role("platform_admin"))` at every router site. Retired the prior broken `require_role(get_user_role_fn, *roles)` (passed `_get_supabase_client=None` blindly → RuntimeError on first use; zero callers anywhere in the monorepo per `therapy-platform-wiring` Phase 1 absorption sweep 2026-05-03). |
| `get_current_user(authorization, ...)` | JWT validation (base — products define own wrapper) |
| `make_get_current_user(get_supabase_client_fn)` | Factory for product-specific `get_current_user` |

### `roles.py` — Role System Constants

`ORG_ROLES` (all 7), `ADMIN_ROLES` (owner, admin), `MANAGE_TEAM_ROLES` (+manager), `DEV_ROLES` (owner, dev), `ORG_ROLE_LABELS` (Portuguese). Helpers: `is_dev_or_owner()`, `can_manage_team()`, `can_manage_billing()`.

### `invitations.py` — Invitation System

`generate_invite_token()`, `create_invitation()`, `validate_invitation()`, `accept_invitation()`, `cancel_invitation()`, `list_pending_invitations()`, `expire_old_invitations()`.

### `email_templates.py` — Product-Branded Emails

`send_product_invitation_email()` (branded invite with accept button), `send_password_reset_email()` (branded reset).

### `page_status.py` — Dev-Gated Page Visibility

`get_visible_pages(db, user_org_role)` — returns visible page route names based on role.

### `notifications.py` — Notification Field Mapping

`map_notification_to_pt()` / `map_notification_from_pt()` — English↔Portuguese field mapping for core notifications.

### `app_factory.py`

`configure_app(app, settings)` — registers exception handlers, CORS, middleware, rate limiting, Sentry.

### `config.py`

`BaseAppSettings` — Pydantic BaseSettings with `cors_origins_list`, `is_production`, `debug`, `jwt_secret` validation.

### `database.py`

`make_supabase_client(url, key, schema?, token?)` — create Supabase client targeting a specific schema.

### `responses.py`

`success_response(data)`, `paginated_response(data, total, page, page_size)`, `ok_response(message)`, `deleted_response()`.

### `exceptions.py`

`AppException` hierarchy. Auto-registered via `configure_app()`.

### `primitives/timeutil.py` — Wallclock + period reference

Single source of truth for "current time" / "current period reference" so production + tests always agree. Replaces hand-rolled `datetime.now(timezone.utc).strftime("%Y-%m")` etc. across products. Adopted 2026-04-30 by `projects/timeutil-absorption/` after a date-rollover bug where a test mixed `date.today()` (local) with the service's `datetime.now(timezone.utc)` and broke at UTC midnight.

| Symbol | Purpose |
|---|---|
| `now_utc() -> datetime` | Aware UTC datetime. Use this instead of `datetime.now(timezone.utc)` so `frozen_time(...)` works. |
| `today_utc() -> date` | UTC `date` (no time, no tz). Use this instead of `date.today()` whenever the result is compared against UTC-stored timestamps. |
| `current_month_ref() -> str` | `"YYYY-MM"` — the canonical "what month are we in" string for period bucketing. |
| `current_day_ref() -> str` | `"YYYY-MM-DD"` — the canonical "today's date as a sortable string". |
| `frozen_time(value: datetime)` | Context manager that pins the wallclock for the with-block. Rejects naive datetimes (the bug class this module exists to prevent). |

```python
from noctusai_lib.primitives.timeutil import current_month_ref, frozen_time
from datetime import datetime, timezone

def test_period_at_utc_midnight():
    with frozen_time(datetime(2026, 5, 1, 0, 47, tzinfo=timezone.utc)):
        assert current_month_ref() == "2026-05"
```

**Migration boundary.** `datetime.utcnow()` is deprecated in Python 3.12+ — every site that used it has been migrated to `now_utc()`. New code uses `now_utc()` directly; legacy `datetime.now(timezone.utc)` calls keep working but are tidier when swapped.

### `middleware.py`

`CorrelationIdMiddleware` (unique request ID), `RequestLoggingMiddleware` (timing).

### `logging_config.py`

`configure_logging(debug)` — JSON (prod) or human-readable (dev).

### `credentials.py` — 3-Tier Credential Resolution

`resolve_credential(key_name, org_id=None)` — `org_settings` → `platform_settings` → env var. Lifted from ERP's local resolver in the LLM consolidation. `configure_credentials(url, anon_key, service_role_key)` is auto-called by `create_product_app()` from `settings.supabase_*` — products get tier 1+2 for free from the single root `.env`.

### `security/` — Webhook signatures + (future) secret-redaction

Top-level seed-lib layer for cross-product security primitives. Today it ships `webhook_signatures` (every inbound webhook in the monorepo verifies through this module). Future redaction / scrubbing helpers land here too.

| Symbol | Purpose |
|---|---|
| `compute_hmac_sha256_hex(body, secret)` | Hex-encoded HMAC-SHA256 of `body` keyed with `secret`. Use when the provider sends a bare hex digest (WAHA, internal). |
| `verify_hmac_sha256(body, signature, secret, *, timestamp_value=None, max_age_seconds=300)` | Verify a `sha256=<hex>` header (Meta `X-Hub-Signature-256`, GitHub). Constant-time; pass `timestamp_value` to enforce a replay window. |
| `verify_hmac_sha256_hex(body, signature_hex, secret, *, timestamp_value=None, max_age_seconds=300)` | Symmetric counterpart for bare-hex digests (no `sha256=` prefix). Forces callers off `==`. |
| `verify_svix_signature(*, svix_id, svix_timestamp, body, signature_header, secret, enforce_replay_window=False, max_age_seconds=300)` | Verify Svix-protocol headers (Resend etc.). Multi-version header rotation supported. |
| `webhook_endpoint(*, secret_env, signature_header, ...)` | FastAPI dependency factory — verifies before the handler runs, returns the raw body bytes (Phase 2 deliverable). |

**Adopters:** ERP (`assinaturas`, `meta_api`, `whatsapp_webhook`) and Mailing (`webhooks/resend`). Stripe SDK is the documented carve-out — it ships its own verifier; don't wrap it. → `KB § PATTERNS/security/webhook-signatures.md` for the four-shape catalog + universal rules.

### `llm/` — Multi-Provider LLM Client

Every product accesses LLMs exclusively through this package. No product code imports `openai` / `anthropic` / `google-generativeai` directly.

**Configuration** (inherited from seed-injector):
- `LLMConfig(key_provider, default_provider, default_chat_model, default_embedding_model, default_audio_model, default_vision_model, cache_enabled, cache_backend, default_cache_ttl_chat, default_cache_ttl_embedding)` — module singleton after `configure_llm()`.
- `default_llm_config(**overrides)` (in `noctusai_seed`) — build using platform defaults + selective overrides (e.g. `default_chat_model="gpt-4o"` for Therapy).
- `configure_llm()` / `get_llm_config()` / `shutdown_llm()` — framework lifecycle hooks.
- `get_provider(name=None)` — per-name cached provider instance. Providers are stateless wrt API keys.
- `resolve_api_key(provider, org_id)` — routes through `key_provider`; raises `LLMNotConfigured` on empty.

**Providers** (auto-register on `import noctusai_lib.llm`):
- `OpenAIProvider` — real, `AsyncOpenAI` SDK, per-key client cache.
- `AnthropicProvider` — STUB, guarded by `NOCTUSAI_ALLOW_STUB_PROVIDERS=1`.
- `GeminiProvider` — STUB, same guard pattern.
- `FakeProvider` — test-only, NOT registered; tests inject via `LLMConfig`.
- `LLMProvider` Protocol — the contract all providers implement.

**Model catalog**: `MODELS` tuple (~12 entries), `models_for(provider, kind=None)`, `all_providers()`, `is_stub_model(provider, id)`. Each entry tagged `kind: chat|embedding|audio|vision` + `stub: bool`.

**Registry**: `register(name, cls)` / `get_provider_class(name)` / `list_providers()`.

**High-level entry points** (what services call):
| Function | Purpose |
|---|---|
| `chat_completion(messages, model=None, provider=None, org_id=None, cache=True, temperature=..., ...)` | Chat; response cache gated on `cache=True × enabled × backend × temperature==0` |
| `chat_completion_stream(messages, ...)` → `AsyncIterator[str]` | Streaming chat; cache kwargs dropped automatically; OpenAI / Anthropic / Gemini / FakeProvider all implement |
| `build_cached_messages(static_system, dynamic_user, *, provider)` | Stable-prefix-first + Anthropic `cache_control` markers |
| `generate_embedding(text, model=None, provider=None, org_id=None)` | Dense vector; 1536-dim default |
| `transcribe_audio(audio, model="whisper-1", ...)` | OpenAI-only real body today |
| `analyze_image(image, prompt, model="gpt-4o", ...)` | URL or raw bytes |

**Exceptions** (all subclass `AppException`): `LLMNotConfigured` (400 + Portuguese message), `LLMAPIError` (502), `ProviderNotImplemented` (501).

**Response cache** (Phase 8):
- `CacheBackend` Protocol (Redis-like), `InMemoryCacheBackend` for dev/test.
- `build_cache_key(product, provider, model, prompt_version, payload)`.
- `try_get` / `try_set` / `flush_for_model` — backend errors swallowed with WARN log.
- **LGPD**: gate blocks before hashing when `cache=False`. Therapy clinical calls always pass False.

**Usage tracking** (Phase 15):
- `UsageEvent` + `UsageSink` Protocol + `InMemoryUsageSink` (dev/test) + `SupabaseUsageSink(db_client, schema, table="llm_usage")` (prod).
- `record_usage(...)` called by every real provider after a successful call; reads `LLMConfig.usage_sink`; safe with `sink=None`.
- `estimate_cost_usd(provider, model, prompt_tokens, completion_tokens)` — catalog-driven from `ModelEntry.cost_per_1m_input_tokens` / `cost_per_1m_output_tokens`.
- Opt-in per product via `LLM_USAGE_TRACKING=1`; framework auto-wires a `SupabaseUsageSink` to the product schema's `llm_usage` table.
- Endpoints: per-product `GET /api/llm/usage` (RLS-scoped, shared router) + Core `GET /api/admin/llm-usage` (platform admin, all schemas).
- **LGPD**: `UsageEvent` stores counts + provider/model + org_id only — never prompt text. See `PATTERNS/backend/llm-usage.md`.

**Credential contract** (`key_provider` callable): `(provider: str, org_id: Optional[str] = None) -> Optional[str]`. Default implementation routes through `resolve_credential(f"{provider}_api_key", org_id)`.

### `testing/` — Mock Supabase Infrastructure

| Class / function | Purpose |
|-------|---------|
| `MockSupabaseClient` | `.table()`, `.set_table_data()`, `.set_sequential_responses()`, `.rpc()` |
| `MockSelectBuilder` | Chainable: `.eq()`, `.order()`, `.single()`, `.or_()`, `.gte()`, `.lte()`, `.ilike()` (no-op) |
| `MockFilterBuilder` | For `.update()` / `.delete()` chains |
| `MockQueryBuilder` | For `.insert()` / `.upsert()` |
| `MockUser` | Parameterized: `MockUser(role="therapist", org_id="x", clinic_id="y")` |
| `AuthClient` | Wraps TestClient with Bearer auth. `.mock_supabase` property, `.raw()` for unauth |
| `bind_consent_module_to_mock(mock_sb)` | **Per-fixture rewire of the X6 consent module's FastAPI deps to a mock supabase.** Solves the boot-order trap where `TestClient` caches the app + `configure_consent_module(...)` captures the FIRST fixture's `mock_sb` reference permanently. Idempotent. Required in every product's `client` fixture — see `KB § PATTERNS/compliance/testing.md § Consent-guard product conftest pattern` for the full rationale + canonical conftest shape. Default in `templates/product-seed/backend/tests/conftest.py` since 2026-04-27. |

### `integrations/supabase_identity.py` — Bulk auth.users → display-name + email resolver

Shipped 2026-05-03 by `therapy-platform-wiring` Phase 1 to absorb the per-product N+1 `db.auth.admin.get_user_by_id(...)` pattern that admin / list endpoints hit when DTO-mapping rows that need `nome` + `email` from `auth.users` (which lives outside every product schema). Replaces inline `_fetch_user_identity` helpers — first concrete absorber was therapy-platform's `app/services/admin_service.py::_fetch_user_identity` (now retired).

| Symbol | Purpose |
|---|---|
| `UserIdentity` | `@dataclass(frozen=True)` carrying `user_id`, `nome`, `email`, `foto_url` plus a `display_name` property (fallback chain: nome → email-local-part → "Usuário") |
| `fetch_user_identities(db, user_ids) -> Dict[str, UserIdentity]` | Bulk resolve. Dedupes input, skips falsy IDs, returns deterministic shape for every requested ID (missing users → empty `UserIdentity`). Per-user lookup errors are caught + logged at WARNING; the function never raises. |
| `fetch_user_identity(db, user_id) -> UserIdentity` | Single-user convenience wrapper. Same error → empty-shape contract. |

**Sync vs async.** Function is `def` (sync), not `async def`. The `supabase-py` admin SDK is sync; `async def` would block the event loop without yielding. Callers needing non-blocking concurrency wrap with `asyncio.to_thread(fetch_user_identities, db, ids)`. For typical admin pages (10-100 IDs), a sequential loop completes in well under a second.

```python
from noctusai_lib.integrations.supabase_identity import (
    UserIdentity,
    fetch_user_identities,
)

# Inside a list endpoint mapping product rows to admin DTOs
user_ids = [row.get("user_id") for row in rows if row.get("user_id")]
identities = fetch_user_identities(admin_db, user_ids)

dtos = []
for row in rows:
    uid = row.get("user_id") or ""
    identity = identities.get(uid, UserIdentity(user_id=uid))
    dtos.append({
        "id": uid,
        "nome": identity.display_name,
        "email": identity.email,
        # ... product-specific fields ...
    })
```

### `integrations/email/` — Templates + scheduled-digest helper + Jinja renderer

The `email_templates.py` flat module became a sub-package on 2026-04-25 (ai-expansion Tier 2 Phase 4) so the new `digest.py` could land alongside the existing invitation-email helper. Two callers were updated (`noctusai_seed.routers` + `therapy-platform invitations` router); no compat shim ships. **Jinja-based `render()` was formalized 2026-04-25 (ai-expansion Phase 12 close)** after 5 digest adopters surfaced — the prior inline-f-string pattern was retired in the same change.

| Symbol | Purpose |
|---|---|
| `send_product_invitation_email(...)` | Existing invitation email (was `email_templates.py`); now at `noctusai_lib.integrations.email.templates`. |
| `Digest(subject, text, html=None)` | Pre-rendered digest dataclass. |
| `DigestSendResult(sent, dry_run, external_id, error, subject)` | Structured outcome — `send_digest` never raises. |
| `send_digest(digest, *, recipient, org_id=None, log_prefix="DIGEST")` | Resend POST + dry-run-on-no-key fallback + Resend-failure swallow. |
| `render(*, html_template, text_template, context, search_paths)` | Jinja-backed `(html, text)` renderer. Auto-escape on by default; `keep_trailing_newline=True`; products extend the lib's `_digest_base.{html,txt}.j2` and override blocks. |

### `domain/sql_templates.py` — Authoring-time helpers for canonical SQL DDL

Pure string-emission helpers for the conventions every product schema reuses. Adopted 2026-05-01 by `projects/sql-templates-absorption/` after the migration scanner flagged 88 `SET search_path` + 21 `updated_at trigger` + 14 `auth.uid()` subquery occurrences as recurrence-rule trips. Existing migration files stay verbatim (replay-log rule); the helpers are for fresh migrations + the scaffold tool.

| Symbol | Purpose |
|---|---|
| `set_search_path(*schemas) -> str` | `SET search_path = <schemas>, public` — schema-lock prelude for SECURITY DEFINER functions. |
| `updated_at_function(schema, function_name="set_updated_at") -> str` | Standard auto-touch helper function for the schema. SECURITY DEFINER + search-path locked. |
| `updated_at_trigger(schema, table, function_name="set_updated_at", trigger_name=None) -> str` | BEFORE-UPDATE trigger calling the helper. Default trigger name = `set_updated_at_<table>`. |
| `rls_subquery_policy(schema, table, policy_name, command, using=..., with_check=..., to_role="authenticated") -> str` | CREATE POLICY using the canonical `(SELECT auth.uid())` subquery shape (planner caches once per query vs per row). Validates that INSERT has `with_check`, SELECT/DELETE has `using`. |

```python
from noctusai_lib.domain.sql_templates import updated_at_function, rls_subquery_policy

# In a fresh migration or scaffold output:
print(updated_at_function("therapy"))
# → CREATE OR REPLACE FUNCTION therapy.set_updated_at() ... LANGUAGE plpgsql SECURITY DEFINER SET search_path = therapy, public ...

print(rls_subquery_policy(
    "erp", "metas", "metas_insert", "INSERT",
    with_check="usuario_id = (SELECT auth.uid())",
))
# → CREATE POLICY "metas_insert" ON erp.metas FOR INSERT TO authenticated WITH CHECK (usuario_id = (SELECT auth.uid()));
```

Detection contract: `mcp/noctusai/tools/recurrence.py::scan_migration_patterns` flags drift (any new migration that re-rolls these conventions instead of using the helpers). Run via `cli.py --scan-migrations`.

### `domain/digest/` — Narrative + render-with-narrative + build-and-send

Sits *upstream* of `integrations/email/digest.py` (which owns the Resend transport). Absorbs the recurring N=4 narrative-pipeline shape across 4 product digest services (audit / PF monthly / Daily Life weekly / Mailing campaign). Shipped 2026-04-30 by `digest-pipeline-absorption` (Wave C of `execution-workflow-codequality-rollout`).

| Symbol | Purpose |
|---|---|
| `narrative(*, system, user_prompt, model, cache, org_id, fallback, max_tokens=600, temperature=0.0)` | Wraps `chat_completion(...)` with the standard digest posture (temperature=0, max_tokens=600). Returns `fallback` string + `logger.warning(...)` when the LLM is unavailable. Never raises. |
| `render_with_narrative(*, html_template, text_template, narrative, context, search_paths, prompt_version)` | Wraps `integrations/email/digest.render(...)` and auto-derives `narrative_paragraphs` (the `\n\n` split) + threads `prompt_version` into the rendering context. Caller's `context` keys win on collision. |
| `build_and_send(digest, *, recipient, org_id, log_prefix)` | Wraps `integrations/email/digest.send_digest(...)` and normalizes the per-recipient return shape to `{"sent", "dry_run", "external_id", "error", "subject"}`. |

**Adoption pattern (Wave C 2026-04-30):**

```python
from noctusai_lib.domain.digest import (
    build_and_send,
    narrative as digest_narrative,
    render_with_narrative,
)
from noctusai_lib.integrations.email.digest import Digest

# Inside _generate_narrative(...):
return await digest_narrative(
    system=PRODUCT_SYSTEM_PROMPT,
    user_prompt=formatted_aggregates,
    model="gpt-4o-mini",
    cache=True,                  # False for personal-narrative-adjacent (LGPD)
    org_id=org_id,
    fallback=deterministic_string,
)

# Inside _render_bodies(...):
return render_with_narrative(
    html_template="my_digest.html.j2",
    text_template="my_digest.txt.j2",
    narrative=narrative,
    context={"my_specific_field": ...},
    search_paths=[_TEMPLATE_DIR],
    prompt_version=PROMPT_VERSION,
)

# Inside send_X(...):
result = await build_and_send(
    digest, recipient=email, org_id=org_id, log_prefix="MY DIGEST",
)
return {**result, "summary": summary}
```

**Adopters (4):** `products/core/.../audit_digest_service.py`, `products/personal-finance/.../monthly_narrative_service.py`, `products/daily-life/.../weekly_review_service.py`, `products/social-wiring/app/modules/email_marketing/.../campaign_debrief_service.py` (absorbed from the retired `mailing` product 2026-05-16, `social-wiring-absorption` Wave 4). ERP metas digest does NOT use `domain/digest` — it has no LLM narrative and preserves a bespoke return shape; documented accept-with-rationale in the closed project.

**Adoption pattern (P3 from ai-expansion §5a).** Products ship per-service Jinja templates in `app/email_templates/` (live next to `app/services/`), inherit from the lib base, and call `render()` to produce both bodies. Send-and-fallback machinery comes from `send_digest`.

```python
from pathlib import Path
from noctusai_lib.email.digest import Digest, render as render_digest, send_digest

_TEMPLATES = Path(__file__).resolve().parent.parent / "email_templates"

html, text = render_digest(
    html_template="my_digest.html.j2",
    text_template="my_digest.txt.j2",
    context={"user_label": user.nome, "narrative_paragraphs": [...], ...},
    search_paths=[_TEMPLATES],
)
digest = Digest(subject=f"...{user.nome}", text=text, html=html)
result = await send_digest(digest, recipient=user.email, org_id=org_id, log_prefix="MY DIGEST")
```

**Template authoring conventions:**

- Filename pair: `<service>.html.j2` + `<service>.txt.j2` per service.
- Both extend the lib base: `{% extends "_digest_base.html.j2" %}` (or `.txt.j2`).
- Override blocks: `header` (h2 content), `subheader` (sub-line / <p>), `body` (main content), `footer` (suffix after "Gerado por NoctusAI").
- Auto-escape applies to HTML templates — use `{{ var | safe }}` only for trusted pre-rendered HTML fragments. The text variant doesn't need `| safe`.
- Pre-format domain values in Python (e.g. BRL strings, percentages) and pass them as plain strings to keep templates declarative.
- For services whose layout fundamentally differs from the lib base (e.g. ERP metas digest emits a full `<!DOCTYPE>` document with a card design), templates may opt out of `extends` and emit raw markup. Auto-escape still applies to interpolations.

**Adopter map (5 products, 2026-04-25):**

| Service | Templates | Notes |
|---|---|---|
| `products/erp-imobiliario/.../metas_digest_service.py` | `metas_digest.{html,txt}.j2` | Self-contained `<!DOCTYPE>` document — does NOT extend the lib base (richer card layout). |
| `products/core/.../audit_digest_service.py` | `audit_digest.{html,txt}.j2` | Extends lib base. C2 weekly audit-log narrative. |
| `products/personal-finance/.../monthly_narrative_service.py` | `monthly_narrative.{html,txt}.j2` | Extends lib base. P2-opp PF monthly. |
| `products/daily-life/.../weekly_review_service.py` | `weekly_review.{html,txt}.j2` | Extends lib base. D6 Friday review. |
| `products/social-wiring/app/modules/email_marketing/.../campaign_debrief_service.py` | `campaign_debrief.{html,txt}.j2` | Extends lib base. Post-send debrief. Absorbed from the retired `mailing` product 2026-05-16. |

**Dep:** `jinja2>=3.1.0` in `seed/lib/backend/pyproject.toml` (added 2026-04-25 alongside the helper).

### `domain/metas/` — Goals / targets / value-and-target tracking primitives

Lifted 2026-05-03 by `projects/metas-domain-seed-absorption/` per N=3 MUST-FORMALIZE — the same metas/goals math (`obter_progresso`, `_calcular_meta_proporcional`, `accumulate valor_atual`) recurred byte-for-similar across PF (`metas_service.py`, `orcamentos_service.py`), ERP (`metas_service.py`, `meta_periodos_service.py`) and Daily Life (`goals_service.py`). Pure-domain — no DB, no FastAPI, no SDK; product persistence stays product-side.

| Symbol | Purpose |
|---|---|
| `Goal`, `Target`, `Progress`, `Period`, `Contribution`, `ProgressTransition` | Frozen dataclasses — value objects with invariants (Target rejects negative, Period rejects end-before-start, Contribution exposes `yyyymm` for monthly bucketing). |
| `GoalStatus`, `PeriodKind` | StrEnums — `pending/in_progress/on_track/at_risk/overdue/completed/abandoned` and `daily/weekly/fortnightly/monthly/quarterly/yearly/open_ended`. Products may persist `.value` directly. |
| `compute_progress(target, current, *, contributions, today, period_remaining_pct)` | Pure derivation of `Progress` (percent_complete capped at 100, remaining floor at 0, ETA from contribution history, status from `next_status`). |
| `accumulate_contribution(target, current, increment) -> ProgressTransition` | Mirrors PF `adicionar_contribuicao` + Daily Life `register_checkin`. Returns new value, completed flag, and 25/50/75/100 milestone-crossed pct. |
| `project_completion_date(target, current, contribs, today)` | ETA from monthly avg (stdlib month math; no `dateutil` dep). |
| `period_bounds(kind, ref) -> (start, end)` | Inclusive bounds. ERP's quinzena (1-15 / 16-end-of-month) + ISO-week conventions baked in. |
| `proportional_target(monthly, kind, ref) -> int` | ERP's `_calcular_meta_proporcional` lifted verbatim + extended to QUARTERLY. |
| `count_business_days(start, end)` + `working_days_*_in_*` family | Mon-Fri counts, inclusive; helpers shared with `period_bounds`. |
| `next_status(current, *, percent_complete, period_remaining_pct?)` | State-machine transition. Sticky terminals (COMPLETED / ABANDONED). |
| `can_transition`, `from_pt_string`, `to_pt_string` | Guard rail + PT-BR ↔ enum mapping (legacy: `ativa/concluida/no_prazo/atrasada`). |
| `GoalRepository`, `InMemoryGoalRepository` | Optional Protocol seam for consumers that want to inject persistence (per `KB § PATTERNS/architect/seed-lib-layout.md § Consumer-injection seams`). InMemory implementation for tests / demos. |

```python
from noctusai_lib.domain.metas import (
    accumulate_contribution, compute_progress, Target, Contribution,
    PeriodKind, proportional_target,
)

# PF — register a contribution:
transition = accumulate_contribution(target=50_000, current=12_500, increment=2_500)
# → ProgressTransition(new_current=15_000, completed=False, crossed_threshold_pct=25.0)

# ERP — daily target from monthly:
target_today = proportional_target(monthly_target=300, kind=PeriodKind.DAILY, ref=date.today())
```

**Adopters (target):** PF metas/orcamentos services, ERP metas service, Daily Life goals service. Wiring is a follow-up cycle — three per-product wiring projects refactor each service to consume the seed without changing the product's persistence shape. Tests: 111 cases under `seed/lib/backend/tests/domain/metas/`.

See `KB § PATTERNS/backend/metas-seed.md` for the wiring recipe + status mapping table.

### `ai/` — Per-entity AI-output storage (P1 pattern)

Shipped 2026-04-25 by ai-expansion Tier 2 Phase 3. Standardizes how products persist + retrieve per-entity AI outputs (categorizations, scores, flags, narratives).

| Symbol | Purpose |
|---|---|
| `AIOutput` | Dataclass mirroring one `<schema>.ai_outputs` row. Validated kind whitelist (`classification`/`score`/`flag`/`extraction`/`narrative`); chip soft-trim to 20 chars; explanation soft-trim to 280 chars. |
| `persist_output(db, schema, output)` | Insert one row via `db.schema(schema).table('ai_outputs').insert(...)`. Returns the persisted dict. |
| `fetch_outputs_for(db, schema, ref_type, ref_id, *, limit=50)` | Read newest-first rows for an entity. Used by the `/api/ai/outputs` standard router. |

**Backend opt-in.** `create_product_app(standard_routers=[..., "ai_outputs"])` registers `GET /api/ai/outputs?ref_type=&ref_id=&limit=` (RLS-scoped via the user-token-bound client).

**Migration template** — every product wiring this in ships a one-time migration:

```sql
CREATE TABLE <schema>.ai_outputs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ref_type     TEXT NOT NULL,
    ref_id       UUID NOT NULL,
    kind         TEXT NOT NULL,            -- classification | score | flag | extraction | narrative
    label        TEXT NOT NULL,
    score        NUMERIC,
    chip         TEXT,
    explanation  TEXT,
    confidence   NUMERIC,
    model_version TEXT,
    prompt_version TEXT,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON <schema>.ai_outputs (ref_type, ref_id);
CREATE INDEX ON <schema>.ai_outputs (created_at DESC);
ALTER TABLE <schema>.ai_outputs ENABLE ROW LEVEL SECURITY;
-- product-specific RLS: typically scopes by org through the entity referenced by ref_id.
```

**Frontend partner.** `<AIIndicator refType refId />` in `@noctusai/lib/design-system` (auto-hides when no output exists). Per-product implementations may continue to ship their own indicators when they need compound shapes (e.g. ERP's `MetaEventoIndicator` shows multi-row aggregated metas-domain data — different shape from the generic single-output indicator).

### `ai/consent.py` — Per-feature AI consent (X6 / LGPD)

Shipped 2026-04-26 by ai-expansion Phase 19. Platform-wide opt-in/opt-out for AI features that consume personal data. Backed by Core migration `012_ai_consent.sql` + `/api/me/consents` endpoints. Full LGPD pattern lives at `KB § PATTERNS/security/lgpd.md § 9`.

| Symbol | Purpose |
|---|---|
| `AIConsentRequired(AppException)` | HTTP 412 — raised by the `require` guard. Frontends should redirect to consent settings. |
| `MandatoryFeatureCannotBeToggled(AppException)` | HTTP 403 — raised by `upsert_decision` (and pre-checked at the `me_consents.py` PUT router) when the user attempts to toggle a `toggleable=False` feature. |
| `ConsentFeature(key, title, rationale, default_granted, product?, toggleable=True)` | One catalog entry. `toggleable=False` marks infrastructure-tier features visible for billing transparency but locked-on. Registered at import time. |
| `register_feature(key, *, title, rationale, default_granted=False, product?, toggleable=True)` | Add to module-level catalog. Idempotent (re-registration overrides). |
| `get_feature(key)` / `get_catalog()` | Catalog reads. `get_catalog()` returns sorted by `(product, key)`. |
| `is_granted(db, user_id, feature_key)` | Resolution order: catalog `toggleable=False` → True (locked-on) → stored decision → catalog default → False (fail-closed). |
| `require(db, user_id, feature_key)` | Raises `AIConsentRequired` if not granted. Service-layer guard — call manually when router-level isn't viable. |
| `upsert_decision(db, user_id, feature_key, *, granted, org_id?)` | Snapshots rationale; records `granted_at`/`revoked_at`. |
| `list_user_consent_view(db, user_id)` | Catalog × decisions merge — powers the user profile UI. |
| `pending_count(view)` | N undecided features — powers the `LayoutEnrichment.aiBadge` prompt. |
| `reset_catalog_for_test()` | Test-only — clears registry. |
| `consent_required(feature_key)` | **FastAPI dep factory** (consent-guard-rollout Phase 1, 2026-04-27). Returns a `Depends(...)`-friendly callable that resolves user_id + admin db at request time and raises `AIConsentRequired` if not granted. Router-layer guard — keeps services LGPD-agnostic. Mirrors `noctusai_lib.llm.budget`'s module-level injection pattern. |
| `configure_consent_module(*, get_current_user, admin_client_factory)` | Wired by the seed at `create_product_app` time when `consent_gating=True` (default). Pass both as `None` to disable guard creation entirely. |
| `is_consent_module_configured()` / `reset_consent_module_for_test()` | Inspect / clear the wired factories. |
| **Catalog auto-load** via `create_product_app(consent_features="app.services.ai_consent_features")` | Framework-side seam (formalized 2026-04-28). Imports the dotted path once per process; the module's `register_feature(...)` calls populate the catalog as a side effect. Replaces the per-product `from app.services import ai_consent_features  # noqa: F401` line in `app/main.py`. Failure is non-fatal — logged warning, catalog stays empty. |
| **Test catalog auto-load** via `noctusai_lib.testing.pytest_plugin` (entry point `pytest11`) | Auto-registered by every test session that has `noctusai-lib` installed. Probes `app.main`; if importable, imports it (which triggers the framework's catalog load via the seam above). Non-product test sessions silently no-op. **Zero per-product `tests/conftest.py` boilerplate** — the bootstrap line lives in seed-lib, not in each product's conftest. |

**Frontend consent UI** (Wave 4 — `consent-ui-rollout`, shipped 2026-04-28 to `seed/lib/frontend/src/design-system/ai/`):

| Symbol | Purpose |
|---|---|
| `<AIConsentToggles/>` | Settings-panel component. Renders the user's catalog grouped by product, sections sorted by descending pending-count. Each row: title + rationale + accessible toggle (`<button role="switch">`). "padrão" annotation when `!decision_recorded`; locked + "infraestrutura" pill when `!toggleable`. Empty / loading / error states surfaced explicitly. |
| `<PendingConsentBadge/>` | Compact "N consentimento(s) pendente(s)" badge. Links to `/settings/ai`. Null-renders when `pending=0` or on load/error (ambient nudge, not critical). Default-mounted by the framework layout factory in the `aiBadge` slot. |
| `useConsents()` | TanStack query against `GET /api/me/consents`. `staleTime: 60s`, `retry: 1`. Returns `{items, pending}`. |
| `useUpdateConsent()` | TanStack mutation against `PUT /api/me/consents/{key}`. Optimistic flip + revert-on-error + PT-BR toast + invalidate-on-settle (so `granted_at`/`revoked_at` come fresh from the server, not synthesized client-side — required for LGPD audit trail). Decrements optimistic `pending` only when the user is making their first explicit decision. |
| `CONSENTS_QUERY_KEY` | Exported tuple — for tests + sibling hooks that need to invalidate the catalog. |

**Frontend framework auto-integration** (consumes the seed-lib components above):

- `seed/framework/frontend/src/pages/ConsentSettingsPage.tsx` — page wrapper at `/settings/ai`. Title + LGPD-friendly intro paragraph + `<AIConsentToggles/>`. Auto-routed by `createProductApp` for both flat and role-based products.
- `seed/framework/frontend/src/app.tsx` — `SEED_ROUTES` list (single entry today; extensible) injected into both `FlatContent` and `RoleContent` `<Routes>` trees BEFORE product routes.
- `seed/framework/frontend/src/layout.tsx` — `aiBadge` slot defaults to `<PendingConsentBadge/>` when `enrichment.aiBadge === undefined`. Products pass `null` to opt out, or pass any other React node to override (e.g. Wave 5's `<AIBadgeStack/>` will compose multiple badges here).
- `seed/framework/frontend/src/index.ts` — re-exports `ConsentSettingsPage` for products that want to host the panel inside their own route shell.

**Per-product code count: zero.** Every product picks up `/settings/ai` + the pending badge automatically by virtue of calling `createProductApp(...)`. Verified via cross-product `vite build` × 8 (consent-ui-rollout Phase 2 close, 2026-04-28).

**LLM spend badge stack** (Wave 5 — `llm-spend-badge-mount`, shipped 2026-04-28 to `seed/lib/frontend/src/design-system/ai/`):

| Symbol | Purpose |
|---|---|
| `<LLMSpendBadge/>` | Admin-only chip surfacing the org's MTD LLM spend status. Reads `useAuthStore` for user metadata; calls `useLLMSpend(orgId, isAdmin)`. Null-renders for non-admins, `unset`, or `ok` status. Yellow chip at `warn`, red chip at `hard_stop`. Click opens `<SpendDetailModal/>` (or routes to a product-supplied `onOpenDetail(orgId)` if provided). |
| `<AIBadgeStack/>` | Composer for multiple badges in `LayoutEnrichment.aiBadge`. Inline-flex with 8px gap, each child null-renders when empty. Used by the seed framework's default `aiBadge` fill: `<AIBadgeStack badges={DEFAULT_AI_BADGES}/>`. |
| `<SpendDetailModal/>` | Inline modal showing the full spend status dict (status / spent / budget / used% / soft+hard thresholds) with a hint about the budget endpoint. Closes on Escape, backdrop click, or close button. |
| `useLLMSpend(orgId, isAdmin)` | TanStack query against `GET /api/admin/llm-spend/{org_id}`. `enabled: orgId && isAdmin` — non-admins never fetch. `refetchInterval: 5min` (spend doesn't change at sub-minute granularity). |
| `LLM_SPEND_REFETCH_INTERVAL_MS` | 5 × 60s. Tunable if products need a different cadence. |

**Default `aiBadge` stack** (in `seed/framework/frontend/src/layout.tsx`):

`DEFAULT_AI_BADGES = [<PendingConsentBadge/>, <LLMSpendBadge/>]` — the seed-mounted default. Layout factory composes `<AIBadgeStack badges={DEFAULT_AI_BADGES}/>` when `enrichment.aiBadge` is `undefined` (use default). Products that want product-specific badges spread the defaults: `aiBadge: <AIBadgeStack badges={[<MyBadge/>, ...DEFAULT_AI_BADGES]}/>`. Reference adopter: Daily Life (composes `<DailyBriefBadge/>` with the seed defaults; one-line update in `daily-life/frontend/src/App.tsx`). Every other product gets the default stack automatically — per-product code count = 0.

**Per-product code count: zero for the default case** (every product picks up the consent + spend badges automatically). Daily Life is the single legitimate exception (~1 line) because it has its own product-specific `<DailyBriefBadge/>` that needs to compose with the defaults — that's domain-specific content, not replication. Verified via cross-product `vite build` × 8 (llm-spend-badge-mount close, 2026-04-28).

**Digest narrative card** (`digest-ui-pages` — shipped 2026-04-28 to `seed/lib/frontend/src/design-system/ai/`):

| Symbol | Purpose |
|---|---|
| `<DigestCard title paragraphs outputRef? promptVersion? isLoading? error? headerActions?/>` | Uniform container for AI-generated digest narratives. Renders title row + optional header actions slot + paragraph body + footer `<AIFeedbackButtons/>` (when `outputRef` provided). Loading skeleton, inline error block, empty-state message all built in. |
| `splitProseIntoParagraphs(prose)` | Helper: splits a raw prose string into paragraphs by blank lines, trims each, drops empties. Use when the backend returns prose as a single string instead of pre-split. |

**Reference adopters** (each is a small per-product wrapper that consumes a product-specific hook + passes data into `<DigestCard/>`):

| Adopter | Hook | Placement | Output ref convention |
|---|---|---|---|
| PF — `<MonthlyNarrativeCard/>` (`products/personal-finance/frontend/src/components/MonthlyNarrativeCard.tsx`) | existing `useMonthlyNarrative()` | `pages/Dashboard.tsx` (above KPI cards) | `digest:pf:monthly:YYYY-MM` |
| Daily Life — `<WeeklyReviewCard/>` (`products/daily-life/frontend/src/components/WeeklyReviewCard.tsx`) | existing `useWeeklyReview()` | `pages/Dashboard.tsx` (below daily content) | `digest:daily_life:weekly:YYYY-Www` |
| Social-Wiring email-marketing — `<CampaignDebriefSection/>` (`products/social-wiring/frontend/src/.../CampaignDebriefSection.tsx`; absorbed from the retired `mailing` product 2026-05-16) | new `useCampaignDebrief(campaignId)` | `pages/CampaignDetail.tsx` (only for sent campaigns) | `digest:mailing:debrief:<campaign_id>` |
| Core — `<AdminAuditDigest/>` (`products/core/frontend/src/pages/admin/AdminAuditDigest.tsx`) | new inline `useAuditDigestPreview(orgId, periodDays)` | new `/admin/audit-digest` route + sidebar entry | `digest:audit:<period>d` |

**Per-product code count: ~10-30 lines per surface** — wrapper component + placement code. Legitimately domain-specific (different data sources, different placements, different gating); NOT replication. The `<DigestCard/>` container itself is the seed-first absorption.

**Storage**: `public.ai_consent (id, user_id, org_id, feature_key, granted, granted_at, revoked_at, rationale_pt, created_at, updated_at)` with `UNIQUE(user_id, feature_key)` for upsert-as-toggle. RLS scopes by `auth.uid()` + admin-role bypass for DSAR.

**Visible-but-locked features (`toggleable=False`).** Some AI features are infrastructure-tier — they're consumed silently by other features (e.g. `erp.embeddings` powers lead-matching + search-relevance) and can't be turned off without breaking those features. **They're still registered in the catalog** so users see what's burning their tokens (billing transparency: users are charged by token usage and need to know what's consuming). The frontend renders these with the toggle disabled + the rationale shown next to it. `is_granted` short-circuits to `True` regardless of any stored decision; `pending_count` excludes them (no decision is needed); `upsert_decision` raises `MandatoryFeatureCannotBeToggled` (HTTP 403) for direct callers, and core's PUT `/api/me/consents/{key}` returns 403 with a PT-BR explanation. Inaugural adopter (consent-guard-rollout Phase 1, 2026-04-27): `erp.embeddings`. Future infrastructure-tier features adopt the same `toggleable=False` pattern.

**Canonical router-layer guard pattern** (preferred over service-level `await require(...)`):

```python
from fastapi import APIRouter, Depends
from noctusai_lib.ai import consent_required

router = APIRouter()

@router.post("/api/ai/leads/{id}/follow-up-draft")
async def draft_follow_up(
    id: str,
    _consent: None = Depends(consent_required("erp.lead_score")),
    # ... other deps + body
):
    # Service is LGPD-agnostic — gate enforced at router layer.
    return await ai_service.draft_follow_up(id)
```

Wiring: `consent_gating=True` is the default for `create_product_app`. Products that import `consent_required(...)` get the guard at zero per-product config cost. Disable globally via `settings.consent_gating = False` (rare — only useful for internal-tooling products that bypass consent entirely).

### `llm/budget.py` — Per-org cost guardrails (X4)

Shipped 2026-04-26 by ai-expansion Phase 18. Wraps three concerns into one module: monthly-budget storage (`org_settings.monthly_llm_budget_brl`), spend computation (USD across every product's `<schema>.llm_usage`, converted to BRL via `LLM_USD_TO_BRL` env, default 5.0), and pre-dispatch enforcement.

| Symbol | Purpose |
|---|---|
| `LLMBudgetExceeded(AppException)` | Raised at the hard threshold; HTTP 429. Message in PT-BR with spent/budget figures. |
| `configure_budget_module(*, admin_client_factory)` | Wired by the seed at `create_product_app` time when `llm_usage_tracking=True`. Pass `None` to disable. |
| `is_configured()` | Boolean — guard short-circuits silently when False. |
| `fetch_budget_brl(org_id)` | Reads `org_settings.monthly_llm_budget_brl`. Returns `None` if unset / malformed. |
| `compute_spend_usd(org_id, *, start_iso?, end_iso?)` | Sums `cost_estimate_usd` across all `_PRODUCT_SCHEMAS`. Defaults to month-to-date window. |
| `compute_status(org_id)` | `{spent_brl, budget_brl, used_pct, status, soft_pct, hard_pct}` with `status ∈ {unset, ok, warn, hard_stop}`. Never raises. |
| `enforce_budget(org_id)` | Called by `chat_completion` + `chat_completion_stream` before provider dispatch. Raises `LLMBudgetExceeded` at hard, logs at soft. **Fail-open** on any read error. |

**Tunables (env vars)**: `LLM_BUDGET_SOFT_PCT` (default 0.80), `LLM_BUDGET_HARD_PCT` (default 1.00), `LLM_USD_TO_BRL` (default 5.0).

**Admin endpoint** (Core, platform-admin only): `GET /api/admin/llm-spend/{org_id}` → status dict; `PUT /api/admin/llm-spend/{org_id}/budget {monthly_brl}` → upsert. Pass `monthly_brl=0` to clear (back to fail-open / unlimited). **Frontend UX shipped 2026-04-28 by `llm-spend-badge-mount` Wave 5:** `<LLMSpendBadge/>` is auto-mounted in every product's `LayoutEnrichment.aiBadge` slot via the framework's `DEFAULT_AI_BADGES` stack. Admin-only render; null-renders for `ok`/`unset`. Click opens `<SpendDetailModal/>` (or product-supplied `onOpenDetail(orgId)` callback). See `§ ai/consent.py § LLM spend badge stack` above.

### `ai_feedback/` — Per-output feedback (X3 cross-cutting widget)

Shipped 2026-04-25 by ai-expansion Tier 2 Phase 17. Standardizes thumbs-up/down feedback for every AI surface (indicators + digest narratives).

| Symbol | Purpose |
|---|---|
| `ai_feedback` standard router | Registered via `create_product_app(standard_routers=[..., "ai_feedback"])`. Provides `POST /api/ai/feedback` (upsert) + `GET /api/ai/feedback?output_ref=...` (current user's feedback for one output). |
| `<AIFeedbackButtons output_ref/>` | Frontend component in `@noctusai/lib/design-system`. Thumbs-up/down + optimistic state + de-dup on no-op clicks. |
| `useAIFeedback(output_ref)` | Read-side hook — returns the current user's feedback row for an output (or `null`). |
| `useSubmitAIFeedback()` | Mutation hook — upserts on `(user_id, output_ref)`. |

**Migration template** — every product wiring this ships a one-time migration scoped to its schema (RLS varies between org-scoped and user-scoped products):

```sql
CREATE TABLE <schema>.ai_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID,                                 -- nullable for user-scoped products
    user_id         UUID NOT NULL,
    output_ref      TEXT NOT NULL,                        -- 'ai_output:<id>' OR 'digest:<service>:<token>'
    rating          INT NOT NULL CHECK (rating IN (-1, 1)),
    notes           TEXT,
    prompt_version  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, output_ref)                           -- toggle-friendly upsert
);
CREATE INDEX ON <schema>.ai_feedback (output_ref);
ALTER TABLE <schema>.ai_feedback ENABLE ROW LEVEL SECURITY;
-- product-specific RLS: org-scoped via current_org_id() OR user-scoped via auth.uid().
```

**`output_ref` conventions** (free-form string, ≤200 chars):
- Indicator: `"ai_output:<uuid>"` — points at a row in the same schema's `ai_outputs` table.
- Digest: `"digest:<service>:<token>"` (e.g. `"digest:audit_digest:org-1-2026-W17"` or `"digest:metas_digest:periodo-uuid"`). The token must be stable within the same period so a user re-rating doesn't create duplicates.

**Adoption pattern.** `<AIIndicator>` accepts an `enableFeedback?: boolean` prop that mounts `<AIFeedbackButtons output_ref={`ai_output:${out.id}`}/>` next to each output row. Digest narratives mount the component directly:

```tsx
<AIFeedbackButtons output_ref={`digest:audit_digest:${period_token}`} prompt_version="core-audit-digest@v1" />
```

**Adopter map (5 products, 2026-04-25 — opt-in via `standard_routers=[..., "ai_feedback"]`):** erp-imobiliario (`erp.ai_feedback`), personal-finance (`"personal-finance".ai_feedback`), mailing (`mailing.ai_feedback`), core (`public.ai_feedback`), daily-life (`daily_life.ai_feedback` — user-scoped RLS).

**Concrete digest mount (2026-04-27, `digest-feedback-mount` project):** Daily Life's `DailyBriefBadge.tsx` panel mounts `<AIFeedbackButtons output_ref={`digest:dl-daily-brief:${YYYY-MM-DD}`} size="sm"/>` at the bottom of the expanded panel. The daily ISO date is the period token, so reopening the panel on the same day reads back the same upserted feedback. Other digests (PF monthly narrative, DL weekly review, mailing campaign-debrief, core audit-digest) ship as backend-only today — UI pages tracked under the `digest-ui-pages` follow-up project; once each lands, the same mount pattern applies with the per-service `output_ref` shape (`digest:pf-monthly:<YYYY-MM>`, `digest:dl-weekly:<YYYY-Www>`, `digest:mailing-debrief:<campaign_id>`, `digest:audit:<org_id>:<period_token>`).

---

## Frontend: `@noctusai/lib` (TypeScript)

Import: `import { ... } from '@noctusai/lib'`

### `api.ts` — HTTP Client

`createApiClient(options)` — factory with `safeFetch`, 401 retry via `onTokenExpired`, auto-auth headers. `extractErrorMessage(error)`.

### `roles.ts` — Role System Constants

`ORG_ROLES`, `ADMIN_ROLES`, `DEV_ROLES`, `MANAGE_TEAM_ROLES`, `PRODUCT_ADMIN_ROLES`, `ASSIGNABLE_ROLES`, `ORG_ROLE_LABELS`. Helpers: `isDevOrOwner()`, `canManageTeam()`, `canManageBilling()`. Type: `OrgRole`.

### `page-status.ts` — Dev-Gated Page Visibility

`usePageStatus(supabase)` — TanStack Query hook (10min staleTime). `isPageVisible()`, `filterNavByPageStatus()` — hides dev/disabled pages, adds DEV badge.

### `sso.ts` — SSO Context & Role Resolution

`resolveSSORoles(metadata)` → `{ isSSO, isProductAdmin }`. `resolveSSOContext(metadata)` → full context with plan/subscription/license/org. `isTrial()`, `subscriptionDaysRemaining()`, `licenseDaysRemaining()`.

### `auth.ts`

`useSupabaseAuthInit(supabase, setUser, setInitialized?)` — session + auth change subscription.

### `stores.ts`

`createAuthStore()` — Zustand with user/isInitialized. `createFiltrosStore(name)` — persisted date range filter.

### `hooks.ts`

`createCrudHooks<T>(options)` → `useList`, `useOne`, `useCreate`, `useUpdate`, `useDelete` with auto-invalidation. **TanStack-Query data layer** — requires a `QueryClientProvider` in the host app. NOTE: most products are NOT wired for react-query, so the no-dependency default for a CRUD page is `<ResourceManager/>` (see `components/`), which is self-contained on the `api` client. Use `createCrudHooks` only when the product already opts into react-query.

### `notifications.ts`

`createNotificationHooks(api, useAuthStore)` → `useNotificacoes`, `useContagemNaoLidas`, `useMarcarComoLida`, `useMarcarTodasComoLidas`.

### `env.ts` — Shared Environment Configuration

| Export | Purpose |
|--------|---------|
| `env` | Typed access to all VITE_ product env vars with fallbacks |
| `validateEnv()` | Call in `main.tsx` — logs missing required vars to console |
| `generateEnvExample(port)` | Generates `.env.example` content for a given backend port |
| `ENV_VARS` | Definition object for all required vars (viteKey, description, required, defaultDev) |

Required vars: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`. Optional with defaults: `VITE_BACKEND_API_URL`, `VITE_CORE_URL`, `VITE_CORE_API_URL`.

### `supabase.ts`

`createProductSupabase(schema?)` — creates client using `env.SUPABASE_URL` + `env.SUPABASE_PUBLISHABLE_KEY` from shared env module.

### `utils.ts`

`cn()` (Tailwind class merger), `formatCurrency()` (BRL), `formatDate()` (pt-BR), `getTodayAtMidnight()`, `stripTime()`.

### `components/`

`SSOCallback` (token exchange + session setup), `ErrorBoundary` / `withErrorBoundary`, `createAuthProvider(supabase, useAuthStore)`, `FakeModeBadge`.

**`ResourceManager<T>`** — the canonical **page-scoped-CRUD** component (the product-internal-wiring rule's UI half). One config-driven component renders list/table + "Novo" button + create/edit modal + delete-confirm + loading/empty/error states, driven by `columns` (display) + `fields` (form). **Self-contained on the `api` client** (plain `useState` + `sonner` toasts; NO `QueryClientProvider` needed) so any product adopts it with zero host setup. Import `from '@noctusai/lib/components'`. **Before hand-rolling a list+manage page, use this** (it formalizes the ~290-line `AdminPlans`-style hand-roll into config-only). Canonical consumer + usage example: `products/seed/frontend/src/pages/Example.tsx`. Adopters: seed (reference) · core (AdminOrganizations/Subscriptions) · social-wiring (EmailMarketing). Props: `title`/`api`/`apiPath`/`singularName`/`columns`/`fields` + optional `idKey`/`extractRows`/`toForm`/`toPayload`/`canCreate|canEdit|canDelete`/`deleteLabel`/`rowActions`/`onMutate`.

---

## Design System: `@noctusai/lib/design-system`

Import: `import { ... } from '@noctusai/lib/design-system'`

### Layout

`AppShell` (sidebar + header + content, responsive), `Sidebar` (prop-driven with NavGroups, brand, footer), `Header` (HoverCard user card, theme toggle, logout).

### UI Components

`NotificationBell` (bell + popover + mark-as-read), `LoginForm` (Supabase email/password with branding), `AcceptInvitePage` (token validation + signup), `ForgotPasswordPage` (Supabase reset), `PageSkeleton` (animated loading), `PoweredByFooter` (sidebar + landing variants), `InactivityWarning` (session expiry), `HoverCard` (Radix-based).

### Hooks

`useTheme(options?)` — dark/light with localStorage + DOM + optional DB persistence. `useActivityRefresh(options)` — proactive token refresh every 5min.

### Styling

`tokens.css` — single source of CSS custom properties. `tailwind.config.base.ts` — shared Tailwind theme (products extend via presets).

### Types

`NavGroup`, `NavItem`, `NotificationHooks`, `LoginFormProps`.

---

## Adding Shared Code

1. **Backend**: `seed/lib/backend/noctusai_lib/<module>.py`
2. **Frontend**: `seed/lib/frontend/src/<module>.ts`, export from `index.ts`
3. **Design system**: `seed/lib/frontend/src/design-system/components/`, export from `design-system/index.ts`
4. **Document**: Update this file
5. **Update seed product**: `products/seed/` — the live reference implementation. Template auto-syncs via the pre-commit hook when seed files are staged.

## Scripts & Automation

| Script | Purpose | Run when |
|--------|---------|----------|
| `scripts/setup.sh` | Full repo setup (hooks + venv + deps) | Once after `git clone` |
| `noctus.dev.sync_seed_template` | Sync seed → template with `{{PLACEHOLDERS}}` | Automatic via hook, or manual |
| `scripts/install-hooks.sh` | Git hooks only (subset of setup.sh) | If hooks need reinstalling |
| `start.sh` | Start all backend + frontend servers | When developing |

The pre-commit hook auto-syncs `products/seed/` → `templates/product-seed/` whenever seed files are staged — the template lands in the same commit, no amend. See `scripts/README.md` for details.
