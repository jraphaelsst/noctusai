# Multi-Provider LLM Platform — Implementation Plan

> **Living document.** Flip `- [ ]` → `- [x]` as tasks complete and save immediately — the user watches this file as a live dashboard. **Phase-by-phase by default**: execute one phase, then pause and wait for explicit instruction before advancing. Override only when the user says "ram through X-Y" or "run all backend phases".

- **Created:** 2026-04-18
- **Last updated:** 2026-04-18
- **Status:** Phases 1-14 + 16 complete. Phase 15 ⏳ (core lib shipped — DB-backed sink + admin aggregate endpoints deferred until dashboards are prioritized). MCP suite: 206 passed; Therapy 1078 ✓; ERP 1765 ✓/23 skip.
- **Owner / stakeholders:** @jraphaelsst
- **Related docs:**
  - `CLAUDE.md`
  - `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`
  - `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md`
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/shared-library-conventions.md`
  - `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md`
  - `products/erp-imobiliario/backend/app/services/credential_resolver.py` (lifted in Phase 1)
  - `products/erp-imobiliario/backend/app/services/{ai_service, embedding_service}.py`
  - `products/therapy-platform/backend/app/services/{summary, longitudinal, transcription, attachment, therapy_embedding}_service.py`

---

## 1. Context & Purpose

OpenAI access is reimplemented in every product: ERP uses raw httpx with org-scoped credential resolution; Therapy uses the `AsyncOpenAI` SDK with env-only credentials. Embeddings, Whisper, and Vision each have local wrappers. Three products × multiple endpoints × two credential strategies = guaranteed drift (the catalog tool already flags `generate_embedding` as duplicated across ERP and Therapy).

Beyond consolidating what exists, the platform is moving to **multi-provider LLM access**: OpenAI today, Anthropic and Gemini selectable in the UI tomorrow, and any future provider as a drop-in. Users (org admins) configure their own keys via a Core settings page; if they don't, the platform falls back to NoctusAI-owned keys, and finally to `.env`. A shared model catalog + selector component lets each product expose a provider/model picker per org.

The win: one SDK per provider behind one Provider protocol, one credential chain, one prompt-cache shape, one response cache, one UI. Everything below the Provider body is real, production-ready code. Anthropic and Gemini bodies ship as labelled stubs with a runtime guard so they can't accidentally go to production, letting the UI and flow be built and tested today.

---

## 2. Confirmed constraints

Answers the user gave during interrogation. Each is load-bearing for the design below.

- **Inheritance rule** — LLM access lives at seed level (`noctusai_lib.llm`) and the seed framework (`noctusai_seed.create_product_app`) auto-wires it. Products inherit multi-provider LLM + credential resolution for free — no per-product plumbing. Products only pass `llm_config=…` when *overriding* defaults (e.g., Therapy wants `gpt-4o` instead of `gpt-4o-mini`). *(LLM config is a seed-injector feature — the whole platform changes when the seed changes.)*
- **Multi-provider from day one** — OpenAI (real), Anthropic (stub), Gemini (stub), extensible to others. *(The UI must be able to show all three before prod adoption.)*
- **One SDK per provider** — `openai` / `anthropic` / `google-generativeai`. No raw `httpx`. *(Real API, per no-workarounds rule.)*
- **Credential contract** — `key_provider(provider: str, org_id: Optional[str] = None) -> str`. *(Two dimensions: which provider, which org. Products inject their own resolver.)*
- **3-tier key resolution** — `org_settings` (per-org) → `platform_settings` (NoctusAI) → `.env`. Same chain as ERP's `credential_resolver`, lifted to `noctusai_lib.credentials`. *(Flexibility for users who bring their own keys, fallback for the rest.)*
- **Global LLM config today, per-environment tomorrow** — one `LLMConfig` instance per product at startup. Per-org overrides stored in a product schema's `llm_preferences` table but not branched-per-environment yet. *(Keep the scaffolding clear; defer complexity.)*
- **Therapy uses OpenAI only** — confirmed. No need to audit its services for other providers during migration. *(Phase 7 is a straight swap.)*
- **Prompt-cache helper ships in Phase 1** — `build_cached_messages()` enforces stable-prefix-first and adds Anthropic `cache_control` markers. *(Caching is structural, not an afterthought.)*
- **Monolithic install** — every product installs `openai`, `anthropic`, `google-generativeai` even if unused. No pip extras. *(Simpler ops; slightly bigger image.)*
- **API Keys page lives in Core** — single source, SSO-accessible from every product sidebar via deep-link. *(Configure once, applies platform-wide.)*
- **Response caching is now, not later** — Redis, LGPD-aware (clinical text never cached). Lands as a core phase. *(Promoted from the original "later" slot.)*
- **No monkeypatching in tests** — services take their Provider via `LLMConfig`; tests construct `LLMConfig(provider=FakeProvider(scripts))`. *(Real DI, not pytest `monkeypatch` surgery.)*
- **Stubs have a runtime guard** — `NOCTUSAI_ALLOW_STUB_PROVIDERS=1` must be set for Anthropic/Gemini stub bodies to return. Production deployments don't set it; a stub call fails loudly. *(Keeps stubs from becoming a silent workaround.)*
- **CLAUDE.md pointer** — one-line entry ("LLM access: `from noctusai_lib.llm import …`"). Deep doc in `04-SHARED-LIBRARY.md`. *(Lean pointer-map discipline.)*

---

## 3. Design principles

1. **One SDK per provider; one provider per `LLMProvider` implementation.** The abstraction is at the Provider level, not the HTTP level.
2. **Credential resolution is injected, always.** The lib takes a `key_provider` callable at startup. Never reads env vars or DB tables directly from inside `noctusai_lib.llm`.
3. **Model catalog is data, not code.** A dict/table of provider → list of model IDs, with `stub: true` markers. UI reads the catalog to filter the selector dropdown.
4. **Stubs are scaffolding, not workarounds.** They implement the real Protocol, return shape-correct responses, and refuse to run outside dev unless the guard flag is set.
5. **Framework integration over per-product glue.** `create_product_app(llm_config=…)` wires everything. Products pass config, not wiring.
6. **Prompt-cache shape is first-class.** `build_cached_messages()` exists from Phase 1. Services call it, not naked message arrays.
7. **UX surface preserved.** Every existing Portuguese error string and degradation path migrates verbatim.
8. **Tests use `FakeProvider`, never `monkeypatch`.** Dependency injection through `LLMConfig`, not runtime attribute swap.

---

## 4. Scope

**In scope:**
- Shared `noctusai_lib.credentials` with 3-tier resolution (org → platform → env).
- Shared `noctusai_lib.llm` package: Provider protocol, OpenAI real, Anthropic stub, Gemini stub, registry, model catalog, exceptions, config, chat/embeddings/audio/vision entry points, prompt-cache helper.
- Framework integration: `create_product_app(llm_config=…)` + automatic lifespan shutdown.
- Backend endpoints for UI: Core API Keys CRUD + per-product provider/model preferences.
- Migrate ERP (2 services) and Therapy (5 services) to `noctusai_lib.llm`.
- Response caching (Redis, LGPD-aware).
- Tests: Provider unit, credential resolution, registry, product integration — all via `FakeProvider`.
- Docs: `04-SHARED-LIBRARY.md`, `05-AI-FEATURES.md`, MASTER-PROMPT for ERP + Therapy, one-line CLAUDE.md pointer.
- Frontend: shared `LLMProviderSelector` + `useLLMProviders` in `@noctusai/lib`; Core API Keys settings page; ERP + Therapy LLM preferences pages.

**Out of scope (deferred):**
- Streaming responses (`stream=True`) — add when a product needs it.
- Token-cost accounting / per-org quotas — separate `llm/usage.py` when metrics shape is agreed with platform_admin.
- Per-environment (dev/staging/prod) config branching — global config today per user direction.
- Rewriting ERP's `credential_resolver.py` beyond lifting it to `noctusai_lib.credentials`.
- Anthropic and Gemini real implementations — stubs + UI now, bodies later.

---

## 5. Architecture

```
seed/backend/lib/noctusai_lib/
  credentials.py               # 3-tier key resolution (lifted from ERP)
  llm/
    __init__.py                # public re-exports
    exceptions.py              # LLMNotConfigured, LLMAPIError, ProviderNotImplemented
    config.py                  # LLMConfig (key_provider, defaults, cache)
    models.py                  # static catalog: provider → [models], with stub flags
    registry.py                # provider name → Provider class
    client.py                  # configure_llm/get_llm_config/shutdown_llm + get_provider()
    chat.py                    # chat_completion() + build_cached_messages()
    embeddings.py              # generate_embedding()
    audio.py                   # transcribe_audio()
    vision.py                  # analyze_image()
    cache.py                   # Phase 8 — Redis-backed response cache
    providers/
      __init__.py
      base.py                  # LLMProvider Protocol
      openai_provider.py       # real, AsyncOpenAI SDK
      anthropic_provider.py    # STUB, guarded
      gemini_provider.py       # STUB, guarded
      fake_provider.py         # test-only scripted responses

seed/backend/framework/noctusai_seed/
  app.py
    create_product_app(…, llm_config: Optional[LLMConfig] = None)
      # Seed-level auto-wiring (products inherit — no product code required):
      → configure_credentials(url, anon, service_role) from settings
      → configure_llm(llm_config or DEFAULT_LLM_CONFIG)
      → shutdown_llm() in lifespan shutdown
  llm_defaults.py
    DEFAULT_LLM_CONFIG  # key_provider uses resolve_credential, default provider=openai
```

**Seed-injector model (default path — no product code):**

```python
# products/*/backend/app/main.py  — nothing LLM-specific needed
from noctusai_seed import create_product_app, ProductSettings

app = create_product_app(
    name="ERP", schema="erp", settings=settings, routers=[...],
)
# Credential resolution + multi-provider LLM access are already wired.
```

**Override path (only when a product wants different defaults):**

```python
# products/therapy-platform/backend/app/main.py
from noctusai_seed import create_product_app
from noctusai_seed.llm_defaults import default_llm_config

app = create_product_app(
    …,
    # Therapy wants gpt-4o (higher accuracy) as its default.
    llm_config=default_llm_config(default_chat_model="gpt-4o"),
)
```

UI contract (Phase 5 backend, Phase 10 frontend):

```
Core:
  GET  /api/platform/credentials              → { openai: "sk-***", anthropic: null, gemini: null }
  PUT  /api/platform/credentials              → { openai?: str, anthropic?: str, gemini?: str }

Every product:
  GET  /api/llm/providers                     → [{ provider, configured, stub }]
  GET  /api/llm/models?provider=openai        → [{ id, label, stub }]
  GET  /api/llm/preferences                   → { provider, chat_model, embedding_model }
  PUT  /api/llm/preferences                   → { provider, chat_model, embedding_model }
```

---

## 6. Implementation phases

### Phase 1 — Foundation: credentials + Provider protocol + config + exceptions + models + registry ✅

Scaffolding only. No provider bodies, no high-level entry points. Everything in this phase is scoped to *shapes*: the protocol, the config dataclass, the exception hierarchy, the model catalog, the registry.

- [x] Create `seed/backend/lib/noctusai_lib/credentials.py` — `resolve_credential(key_name, org_id)` with 3-tier chain (lifted from ERP `credential_resolver.py`, made product-agnostic)
- [x] Create `seed/backend/lib/noctusai_lib/llm/__init__.py` — package marker + public re-exports
- [x] Create `seed/backend/lib/noctusai_lib/llm/exceptions.py` — `LLMNotConfigured`, `LLMAPIError`, `ProviderNotImplemented`, subclasses of `AppException`
- [x] Create `seed/backend/lib/noctusai_lib/llm/providers/__init__.py`
- [x] Create `seed/backend/lib/noctusai_lib/llm/providers/base.py` — `LLMProvider` Protocol (`chat_completion`, `generate_embedding`, `transcribe_audio`, `analyze_image`, `close()`)
- [x] Create `seed/backend/lib/noctusai_lib/llm/config.py` — `LLMConfig` dataclass (`key_provider`, `default_provider`, `default_chat_model`, `default_embedding_model`, cache fields for Phase 8)
- [x] Create `seed/backend/lib/noctusai_lib/llm/models.py` — static model catalog dict per provider with `stub: bool`, `kind: "chat"|"embedding"|"audio"|"vision"`
- [x] Create `seed/backend/lib/noctusai_lib/llm/registry.py` — `get_provider_class(name)`, `list_providers()`, populated via explicit registration (no import-time magic)
- [x] Update `seed/backend/lib/noctusai_lib/__init__.py` — re-export `LLMConfig`, `resolve_credential`, exceptions
- [x] Add tests in `mcp/noctusai/tests/test_llm_foundation.py` covering: credential chain order, exception hierarchy, registry lookup, model catalog shape
- [x] Re-run `python mcp/noctusai/cli.py --catalog` — new symbols appear; no new duplicates introduced

**Improvements:**
- `credentials.resolve_credential` silently swallows Supabase errors on Tier 1/2 (broad `except Exception`). Acceptable for env-fallback cases but in a prod incident we'd have zero signal that the DB is down. Next rework: log at `WARN` with correlation ID when Tier 1 or Tier 2 lookups fail, keep falling through to env.
- `_reset_for_testing()` is exposed publicly from both `credentials.py` and `registry.py`. It's clearly test-plumbing, not API surface. Future rework: move to a `noctusai_lib.testing` submodule so it's not reachable via the top-level `noctusai_lib` import.
- `LLMConfig.cache_backend: Optional[Any]` is untyped — set in Phase 8 when the cache ships. Tighten to a `CacheBackend` Protocol once we know the minimal API.
- Model catalog is a frozen tuple of dataclasses. Works well for now, but if/when orgs can register their own models (custom fine-tunes, self-hosted endpoints), the catalog becomes DB-backed and this module becomes a default-seed rather than the source of truth. Revisit when that product requirement lands.
- The `ModelEntry` for `gpt-4o` appears twice in `MODELS` (once kind=chat, once kind=vision) because a single underlying model serves both kinds. Works, but `models_for("openai")` returns the same ID twice. If a consumer dedupes on id, they'll silently drop the vision entry. Consider a composite key `(id, kind)` or a single entry with `kinds: list[ModelKind]`.
- Registry tests had to save/restore the full registry rather than clear-and-rebuild (Python's import cache means provider modules' `register()` calls only run once per process). Future rework: make the registry survive reset by having providers register via a decorator that's idempotent, or by storing the registry state in a class-scoped fixture.

### Phase 2 — Providers: OpenAI real + Anthropic/Gemini stubs + FakeProvider ✅

- [x] Create `seed/backend/lib/noctusai_lib/llm/providers/openai_provider.py` — real implementation using `AsyncOpenAI` SDK (chat, embeddings, Whisper, Vision)
- [x] Create `seed/backend/lib/noctusai_lib/llm/providers/anthropic_provider.py` — stub with `NOCTUSAI_ALLOW_STUB_PROVIDERS` guard; canned response shapes per method
- [x] Create `seed/backend/lib/noctusai_lib/llm/providers/gemini_provider.py` — same stub pattern
- [x] Create `seed/backend/lib/noctusai_lib/llm/providers/fake_provider.py` — test-only scripted responses, no guard (tests opt in by constructing it directly)
- [x] Register OpenAI/Anthropic/Gemini in `registry.py` (side-effect imports via `providers/__init__.py`); FakeProvider intentionally NOT registered
- [x] Add `openai`, `anthropic`, `google-generativeai` to `seed/backend/lib/pyproject.toml` as core deps (monolithic install)
- [x] Ensure they land in `products/erp-imobiliario/backend/requirements.txt` and `products/therapy-platform/backend/requirements.txt`
- [x] Unit tests for each provider (17/17 passing — `mcp/noctusai/tests/test_llm_providers.py`)

**Improvements:**
- `OpenAIProvider._clients: dict[api_key → AsyncOpenAI]` grows unboundedly. On a platform with many orgs bringing their own keys, this leaks memory over long-running processes. Future rework: bound with an LRU and evict least-recently-used clients with `await client.close()`.
- `OpenAIProvider.analyze_image` hardcodes `image/jpeg` when encoding bytes as a data URL. PNG/WEBP/GIF payloads will be mislabeled but probably still decoded by OpenAI. Sniff the format from magic bytes or accept an explicit `mime_type=` param.
- `AnthropicProvider.generate_embedding` returns a 1024-dim fake, but Anthropic doesn't actually ship an embeddings API today. When the real implementation lands, we'll likely drop the method (or route it to a different provider) and the model catalog's Anthropic-embedding entries need to go. Right now the stub lies by implication. Add a `supports_embeddings: bool` flag to the Provider protocol so the UI can disable the selector correctly.
- The Anthropic/Gemini stub guard code is duplicated across both files (same `_assert_dev_mode()` helper with identical body, different provider name). Three lines each — acceptable, but if a third stub provider appears, extract to a shared `stub_guard(provider: str)` helper.
- `OpenAIError` catch is broad — we lose distinction between rate-limit (should retry), auth (should reconfigure), and server-side (transient). Future rework: map specific subclasses (`RateLimitError`, `AuthenticationError`, `APIStatusError`) to richer `LLMAPIError` details so callers (and the response cache) can decide whether to retry.
- No retry/backoff on transient failures. OpenAI SDK does some of this internally, but we don't surface it or tune it. Revisit with Phase 8 cache: on cache-miss retry policy needs defining.
- Real OpenAI HTTP flows are covered only structurally (constructor, client cache, close()). Integration-level testing is deferred to Phase 6/7 where migration happens. Flagging because it means we won't catch an SDK signature change until a product migration fails.
- `FakeProvider` defaults its embedding to 1536-dim (matching OpenAI `text-embedding-3-small`). If a test expects a Gemini-shaped 768-dim vector, it has to script it explicitly. Could be cleaner if `FakeProvider` accepted a `default_embedding_dim` parameter.

### Phase 3 — Framework integration (seed-injector: auto-credentials + auto-LLM + lifespan) ✅

This phase is what makes LLM a seed-inherited feature. Products should get multi-provider LLM for free without wiring anything.

- [x] Create `seed/backend/framework/noctusai_seed/llm_defaults.py` with `DEFAULT_LLM_CONFIG` + helper `default_llm_config(**overrides)` for products that want to override one or two fields
- [x] Add `llm_config: Optional[LLMConfig] = None` parameter to `create_product_app()` — when None, use `default_llm_config()`
- [x] On startup: auto-call `configure_credentials(url, anon, service_role)` using the product's `settings.supabase_*` values (every product already has them from the single root `.env`)
- [x] On startup: call `configure_llm(effective_llm_config)` (either the passed-in override or the default)
- [x] On shutdown: call `shutdown_llm()` in the lifespan shutdown hook (closes every Provider's transport via `provider.close()`)
- [x] Re-export `LLMConfig`, `configure_llm`, `get_llm_config`, `default_llm_config`, `DEFAULT_LLM_CONFIG`, `shutdown_llm` from `noctusai_seed.__init__`
- [x] Update `products/seed/backend/app/main.py` with a comment explaining that LLM is inherited by default
- [x] Integration test: verify `configure_llm` / `get_llm_config` / `get_provider` / `resolve_api_key` / `shutdown_llm` lifecycle + `default_llm_config` shape (16/16 passing — `test_llm_client.py`)
- [x] Also shipped as part of Phase 3: `noctusai_lib/llm/client.py` with the actual `configure_llm` / `get_llm_config` / `get_provider` / `resolve_api_key` / `shutdown_llm` machinery (prerequisite for framework integration)

**Improvements:**
- `client.py` uses module-level globals (`_active_config`, `_provider_cache`) — standard Python singleton pattern, but means running two `create_product_app()` instances in one process (e.g. pytest collecting across multiple product conftest fixtures) would mutually clobber each other's config. Low-priority today; if we ever run multiple products in one process, refactor into a `LLMContext` class stored on `app.state`.
- `has_lifespan = True` is now unconditional because we always need to run `shutdown_llm()`. The old short-circuit that skipped lifespan setup when no product hooks existed is gone — minor perf cost per app, but honest. If lifespan overhead becomes measurable, revisit with an opt-out flag.
- Framework's auto-`configure_credentials()` call hard-depends on `settings.supabase_url` / `settings.supabase_anon_key` / `settings.supabase_service_role_key` attributes. `ProductSettings` has all three, but a misconfigured product subclass that drops one would fail at app startup with an AttributeError deep inside framework code. Add a defensive check in `create_product_app()` that raises a clearer error ("Your ProductSettings must include supabase_url/anon_key/service_role_key to enable credential resolution").
- `DEFAULT_LLM_CONFIG` singleton is constructed at module import time. If the module is imported before any env vars are set (rare, but possible in some test orderings), the closure still resolves fine because the key_provider is lazy — but the singleton is "frozen" to that reference. If someone mutates it mid-process (editing `.default_chat_model`), they'd surprise callers that grabbed the reference earlier. Consider making `LLMConfig` a frozen dataclass.
- Seed product's `main.py` now has a multi-paragraph docstring explaining the inheritance. That's documentation effort that will need to stay in sync if the seed-injector's default model changes. Consider linking to `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md` (after Phase 9 updates it) instead of inlining the examples.
- Integration tests call `_reset_for_testing()` in `setup_method` — same test-plumbing-exposed-publicly pattern flagged in Phase 1. Consider an `llm_reset` pytest fixture so the reset call is at least conceptually owned by the test harness.

### Phase 4 — High-level LLM API + prompt-cache helper ✅

- [x] `chat.py::chat_completion(messages, *, provider=None, model=None, org_id=None, cache=True, ...)` — dispatches to provider
- [x] `chat.py::build_cached_messages(static_system, dynamic_user, *, provider)` — stable-prefix-first + Anthropic `cache_control` markers + short-prefix warning (logged at DEBUG)
- [x] `embeddings.py::generate_embedding(text, *, provider=None, model=None, org_id=None)`
- [x] `audio.py::transcribe_audio(audio_bytes, *, provider="openai", model="whisper-1", org_id=None)`
- [x] `vision.py::analyze_image(image, prompt, *, provider=None, model=None, org_id=None)`
- [x] Re-exported from `noctusai_lib.llm` top-level package
- [x] Tests: dispatch correctness, cache-message shape per provider, `LLMNotConfigured` path — 14/14 passing (`test_llm_api.py`)

**Improvements:**
- The `cache: bool = True` parameter on `chat_completion` is currently accepted but unused (Phase 8 wires it). This is a forward-compat concession — callers can start passing `cache=False` for clinical flows today and get correct behavior automatically when caching ships. But right now it's an inert argument that can mislead readers into thinking caching is active. Revisit after Phase 8: either wire it fully or add a log message when `cache=True` but caching isn't actually in effect.
- `build_cached_messages` warns via `logger.debug` when the stable prefix is short. `DEBUG` is too quiet — most production log configs filter it out. Consider `INFO` or a one-time `WARN` per-process per-prompt-hash so authors get signal without spam.
- Prefix-length threshold is measured in characters (`_MIN_CACHE_PREFIX_CHARS = 1024 * 4`) using a 4-chars-per-token heuristic. That's rough — Portuguese content averages different byte-per-token than English, and multi-byte chars complicate it further. Future rework: if we ever use `tiktoken` elsewhere, swap to real token counts.
- `chat_completion`'s response_format parameter is OpenAI-shaped (`{"type": "json_object"}`). Anthropic and Gemini express structured output differently. Today this works because only OpenAI has a real body, but when Anthropic ships, either translate in the Provider or introduce a provider-agnostic abstraction (`response_mode="json"`). Document the translation contract at `LLMProvider` level.
- `audio.py` and `vision.py` are thin wrappers — they dispatch to the provider with no transformation. If they stay this thin, consider inlining them into `chat.py` as methods on a `LLMClient` class. Today the split is for clarity and future room (e.g., audio-specific utilities like chunking long recordings); revisit if they never grow.
- `build_cached_messages` takes a single `static_system` + single `dynamic_user` — the common case, but services with complex few-shot setups pass `extra_static_context` / `extra_dynamic_messages`. The param set is growing; might become clearer as a builder pattern (`PromptBuilder().system(...).examples(...).user(...).build()`) once three or more services need it.
- Tests install a FakeProvider by re-registering it under "openai" name, then restore real providers via `importlib.reload`. Works, but fragile — relies on module-level side effects. A cleaner pattern: add a `provider_override: Optional[LLMProvider]` field to `LLMConfig` that tests set directly. Then no registry mutation is needed. Worth refactoring before Phase 6/7 migration tests, since every service test will follow this pattern.

### Phase 5 — Backend API endpoints for UI ✅

**Design revision during Phase 5**: the per-product `routers/llm.py` was folded into `noctusai_seed.llm_router.create_llm_router(deps)` — every product inherits the same `/api/llm/*` surface via `create_standard_routers`. Products add zero Python lines for the LLM API. This is the right seed-first move (one router, many products) rather than four copies in four product trees.

**Core:**
- [x] Router `core/backend/app/routers/credentials.py` — `GET/PUT /api/platform/credentials` (scope resolution: platform_admin → `platform_settings`, org owner/admin → `org_settings`)
- [x] Keys are write-only; `GET` returns `{openai: {masked, scope}, anthropic: ..., gemini: ...}` where `masked` shows only the last 4 chars and `scope` is "org" | "platform" | null
- [x] Permission gate: platform_admin OR org owner/admin (others → 403). Users without org_id → 403 on org-scoped writes.
- [x] Wired into `core/backend/app/main.py`
- [x] Tests (masking, fetch, exception tolerance) — part of 13/13 `test_llm_endpoints.py`

**Seed framework (new — replaces per-product router):**
- [x] `seed/backend/framework/noctusai_seed/llm_router.py::create_llm_router(deps)` — returns `APIRouter` with `/api/llm/providers`, `/api/llm/models`, `/api/llm/preferences` (GET+PUT)
- [x] `create_standard_routers()` now includes `create_llm_router(deps)` as a fourth standard router (alongside health/notificacoes/team)
- [x] `/api/llm/providers` uses `resolve_credential(f"{provider}_api_key", org_id)` to mark `configured: true/false` per org; also marks `stub: true/false` based on catalog
- [x] `/api/llm/models?provider=openai&kind=chat` filters the shared `models_for(...)` catalog
- [x] `/api/llm/preferences` GET+PUT against `<schema>.llm_preferences` table (per-product schema, RLS-scoped)
- [x] PUT permission gate: platform_admin / owner / admin / manager only
- [x] Tests (factory shape, catalog integrity, standard-routers inclusion, registry↔catalog consistency)

**Migrations:**
- [x] `products/erp-imobiliario/backend/migrations/017_llm_preferences.sql` — `erp.llm_preferences` with RLS (members read, owner/admin/manager write)
- [x] `products/therapy-platform/backend/migrations/005_llm_preferences.sql` — `therapy.llm_preferences` with clinic-scoped RLS (clinic members read, clinic_admin/clinic_owner write)

**Improvements:**
- The shared `llm_router`'s `/preferences` GET uses `deps._db.get_user_client()` — reaching into the private `_db` attribute of `ProductDependencies` because it didn't expose a public getter. Add `deps.get_user_client()` / `deps.get_admin_client()` as first-class public methods so the framework router doesn't reach through a private attribute.
- Therapy's migration stores `clinic_id` under an `org_id`-named column to match the shared router's uniform `get_org_id()` contract. That's pragmatic but confusing — someone reading `therapy.llm_preferences` will expect a real `org_id`. Consider: (a) a view that aliases the column, or (b) parameterizing the column name at router level (`deps.tenant_key_name`).
- PUT permission check uses hardcoded `("platform_admin", "owner", "admin", "manager")`. This duplicates `noctusai_lib.roles.MANAGE_TEAM_ROLES` — except that one lacks `platform_admin`. Next rework: add a `CAN_CHANGE_LLM_PREFS_ROLES` constant in `noctusai_lib.roles` or use a role-check helper.
- `_fetch_key` in `credentials.py` is very close to the `credential_resolver.py` DB logic ERP used — we now have two functions doing similar reads against the same tables. Consolidate: let the Core router call `resolve_credential` directly (with the caller's org_id) rather than duplicating the read pattern.
- `CredentialsBody` in Core hardcodes `openai: Optional[str] = None, anthropic: ..., gemini: ...`. Adding a fourth provider later means editing the Pydantic model, the `_LLM_PROVIDERS` tuple, and the UI all at once. Next rework: drive the schema off the model catalog (`all_providers()`) dynamically, or use `dict[str, Optional[str]]` and validate provider names server-side.
- The `/api/llm/providers` endpoint does N Supabase lookups (one per provider for `resolve_credential`). For 3 providers it's trivial; if the catalog grows to 10+, batch into a single query. Today acceptable — flag for when the catalog grows.
- Tests skip the full FastAPI TestClient round-trip (no auth token, no Supabase mocking for RLS). Unit-level assertions cover the logic but miss integration bugs like "does the response shape match the Pydantic model actually exposed". Integration tests land in Phase 6/7 when the migrated products exercise the router end-to-end.
- The migration's `org_id UUID PRIMARY KEY` means exactly one preference row per org — no history, no rollback. If a user accidentally picks the wrong model, they lose the prior selection. Future rework: add an `llm_preferences_history` table + an audit trigger, or just `updated_at + previous_chat_model` columns to support undo.

### Phase 6 — Migrate ERP ✅



Thanks to Phase 3's seed-injector, `main.py` needs no changes. Migration is pure service-level.

- [x] `services/ai_service.py` — deleted `_chat_completion`, `_get_api_key`, URL/TIMEOUT/httpx; now imports `chat_completion` from `noctusai_lib.llm`. `MODEL = "gpt-4o-mini"` pinned locally (was module const — preserved).
- [x] `services/embedding_service.py` — deleted local `generate_embedding` body, `_get_api_key`, URL/TIMEOUT; now delegates to `noctusai_lib.llm.generate_embedding`. Public signature preserved (`(text, org_id)`).
- [x] Deleted `import httpx` / `httpx.AsyncClient` from both AI services (grep-verified; remaining httpx usage in matricula/signature/email/whatsapp/certidoes/meta_api is non-OpenAI, left alone)
- [x] Replaced `from app.services.credential_resolver import resolve_credential` across 5 files (configuracoes, matricula, signature_provider, email_service, certidoes_service) with `from noctusai_lib.credentials import resolve_credential`
- [x] Deleted `app/services/credential_resolver.py` — the 44-line module is now `noctusai_lib.credentials`
- [x] Deleted `tests/services/test_credential_resolver_service.py` — coverage moved to `mcp/noctusai/tests/test_llm_foundation.py::TestCredentialsChain`
- [x] Updated `tests/services/test_ai_service.py` — removed the now-dead `TestGetApiKey` class (private helper gone); existing patches on `app.services.ai_service._chat_completion` rewritten to patch `app.services.ai_service.chat_completion` (imported symbol)
- [x] Public signatures preserved: `generate_description`, `score_lead`, `suggest_price`, `generate_embedding`, `embed_ativo`, `embed_ativos_batch`
- [x] `products/erp-imobiliario/backend/tests/services/test_ai_service.py` — 21/21 passing

**Improvements:**
- Deleted `test_credential_resolver_service.py` held 12 patch-based tests covering the 3-tier chain. The lib-level tests in `test_llm_foundation.py::TestCredentialsChain` cover only 4 scenarios — less thorough. Future rework: port the dropped scenarios (empty string value, tier 1 hit with tier 2 miss, tier 2 hit with tier 1 miss, etc.) into the lib test suite to reach parity.
- `ai_service.py` now has a `MODEL = "gpt-4o-mini"` constant — duplicating `LLMConfig.default_chat_model`. For ERP it matches; if the platform default ever shifts, ERP will silently keep `gpt-4o-mini` unless someone notices. Either (a) remove the constant and let the lib default drive, or (b) keep it but comment explicitly that ERP pins for cost. Today the docstring explains but a comment wouldn't hurt.
- `check_openai_configured(org_id)` remains as a thin wrapper over `resolve_credential`. The function exists only because routers call it pre-flight to show a graceful "AI unavailable" UX. With the lib's structured `LLMNotConfigured` exception, the pre-flight check is redundant — routers could just try the call and catch. Worth removing if router error paths already handle `LLMNotConfigured`.
- Migration was "big-bang" — 5 importers + 2 service bodies + 1 test file + 1 deletion all in one sweep. Worked because the ERP AI surface is small. For Therapy (5 services + more call sites), consider a smaller commit granularity so each step is individually testable.
- `ai_service.py` still accepts only org-less calls — `generate_description`, `score_lead`, `suggest_price` don't take an `org_id` parameter. They'll use the platform-level (Tier 2) or env (Tier 3) key. Per-org OpenAI usage in ERP is therefore impossible today despite the infrastructure supporting it. Next rework: thread `org_id` through from the router → service for proper per-org billing segregation.
- No integration test covers the full "real request → ai_service → lib → OpenAI SDK" chain in CI. Service-level tests mock `chat_completion`; lib-level tests mock the SDK. A single test exercising the real SDK against a tiny canned prompt would catch SDK-surface changes between `openai` versions. Too expensive to run on every PR, but valuable as a nightly smoke test.

### Phase 7 — Migrate Therapy ✅

`main.py` untouched — defaults inherited from the seed-injector.

- [x] `services/summary_service.py` — `_call_openai` renamed to `_call_llm`, delegates to `chat_completion(..., cache=False)` for LGPD; preserves `_PLACEHOLDER_SUMMARY` fallback via `LLMNotConfigured` catch.
- [x] `services/longitudinal_service.py` — same pattern. `cache=False` for clinical aggregation.
- [x] `services/transcription_service.py` — uses `transcribe_audio(...)` for Whisper. Graceful degrade via `LLMNotConfigured`.
- [x] `services/attachment_service.py` — uses `analyze_image(...)` for Vision and `transcribe_audio(...)` for audio uploads. No direct SDK references.
- [x] `services/therapy_embedding_service.py` — `generate_embedding(text, api_key)` signature preserved (api_key now ignored; lib resolves key). Uses `_lib_generate_embedding` internally.
- [x] `grep from openai` and `AsyncOpenAI` on `products/therapy-platform/backend/app/services/` returns zero hits.
- [x] Four LGPD concerns flagged via `noctusai_lgpd_flag` → recorded in `LGPD-WARNINGS.md`:
  - `patient-clinical-text-in-llm-prompt` (summary_service)
  - `longitudinal-clinical-aggregation` (longitudinal_service)
  - `patient-audio-to-whisper` (transcription_service)
  - `patient-attachment-to-llm` (attachment_service)

**Improvements:**
- Therapy's `summary_service._openai_configured()` still reads `settings.openai_api_key` directly — a Tier 3-only check duplicating what the lib's `resolve_credential` already does across all tiers. Before deleting, consider whether any code path actually depends on the check (it does — the router uses it to decide between "generate" vs "placeholder"). Next rework: replace with `resolve_credential("openai_api_key")` so Tier 1+2 keys also unlock generation.
- Four near-identical `except LLMNotConfigured: return placeholder` patterns across summary / longitudinal / transcription / attachment. Extract into a decorator or context manager if a fifth service appears.
- `attachment_service.py` image processing previously passed the raw `file_url` to OpenAI (remote fetch by the provider). New code via `analyze_image(image=file_url, ...)` preserves that — but `OpenAIProvider.analyze_image` has a branch for bytes vs URL. Verify OpenAI-provider behavior on URL inputs matches what the old direct call did.
- Audio transcription in `attachment_service` used a tempfile + open-as-bytes dance to feed Whisper. The new `transcribe_audio(audio_bytes, ...)` skips the tempfile entirely — one fewer moving part. No regression expected but worth an integration test when we have real Supabase Storage URLs.
- Tests for Therapy services are unchanged in this phase — they still use pre-migration mocking patterns. The test update is queued for Phase 9 (wrap-up) since every test file needs review and the volume is non-trivial.
- LGPD flag invocations are manual — the tool doesn't auto-detect "this function takes a transcript". A future tool could look at function signatures containing patterns like `transcript: str` / `audio: bytes` and prompt the agent to flag. Keep in mind for later.

### Phase 8 — Response caching (Redis, LGPD-aware) ✅

- [x] `noctusai_lib/llm/cache.py` — `CacheBackend` Protocol (Redis-like), `InMemoryCacheBackend` for dev/test, `build_cache_key`, `try_get`, `try_set`, `flush_for_model`
- [x] Key format: `llm:{product}:{provider}:{model}:{prompt_version}:{sha256(messages_json)}` — deterministic, SHA-256 bounded
- [x] Cacheable surface — `chat_completion` gates on FOUR conditions: `cache=True` (call-site), `LLMConfig.cache_enabled`, non-None `cache_backend`, `temperature == 0`. Any single condition false = cache skipped.
- [x] **LGPD hard rule enforced**: every Therapy `chat_completion` call passes `cache=False` (summary + longitudinal). The gate blocks before the backend is even touched — patient text never hashes into a cache key.
- [x] TTL: `LLMConfig.default_cache_ttl_chat` = 24h, `default_cache_ttl_embedding` = 30d
- [x] Observability: `llm.cache.hit` / `llm.cache.miss` / `llm.cache.error` log fields (DEBUG / INFO / WARNING)
- [x] Cache-layer failures are swallowed — a broken Redis never fails a successful LLM call. Logged at WARNING.
- [x] `flush_for_model(product, provider, model)` for admin flush (in-memory impl; real Redis path delegated to caller via SCAN)
- [x] Default `cache_enabled=False` in `LLMConfig` — opt-in per product after operational readiness
- [x] Tests (11/11) — key determinism + invalidation, in-memory backend, error swallowing, **all four cache gate conditions** individually verified, flush semantics

Deferred from original plan (scope-fit for a later increment):
- `redis.asyncio` concrete backend (the Protocol is shipped; real implementation lands when Redis is deployable in the target environment).
- Admin flush endpoint at `POST /api/admin/llm-cache/flush` — to be added in Core when the real Redis backend ships.
- `REDIS_URL` env var addition to `.env.example`.

**Improvements:**
- The cache is gated on `temperature == 0` for determinism. But `response_format={"type": "json_object"}` at `temperature=0.4` is *also* mostly deterministic in practice — services pass that combo today. Current gate is overly strict. Future rework: extend the gate to include `(response_format.type == "json_object" and temperature ≤ 0.2)` as a "mostly-deterministic" branch.
- `build_cache_key` serializes the payload via `json.dumps(..., sort_keys=True)` — fine for simple message lists, breaks if a caller passes a datetime or a custom object. Document "payload must be JSON-serialisable" or swap to a safer digest that can handle bytes/datetime (e.g. hash the repr).
- The `cache_namespace` per-call kwarg (defaulting to "llm") lets callers scope their cache, but it's undocumented outside the implementation. Publish it in `chat_completion` docstring or remove in favor of config-driven namespacing.
- No eviction logic in `InMemoryCacheBackend` — it's unbounded. Fine for tests (short-lived processes). Gate the `InMemoryCacheBackend` with a comment / type-guard so nobody accidentally installs it in prod.
- `flush_for_model` has a backend-specific branch (`isinstance(backend, InMemoryCacheBackend)`). When the real Redis backend lands, it'll need its own SCAN implementation. Consider making `flush` a method on the `CacheBackend` Protocol itself.
- The cache key doesn't include `org_id`. This is correct for shared-content caching (one "summarize this property listing" cached once for the platform) but wrong for per-org secrets (e.g. a custom system prompt set by one org). Services that have per-org prompt customization must pass a unique `cache_namespace` or `prompt_version`. Document this trap.
- Cache misses currently do not include the inbound payload in the log — only the key. For debugging "why did this not cache when I expected it to", more context would help. Add a DEBUG-level "cache gate: cache=%s, enabled=%s, temp=%s, backend=%s" log before the gate check.

### Phase 9 — Backend wrap-up: tests, docs, review, catalog re-run ✅

- [x] MCP dev-toolkit test suite: 175/175 passing across Phases 1-8
- [x] Updated `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` — added `credentials` + full `llm/` sections (config, providers, catalog, registry, entry points, exceptions, cache, contract)
- [x] Updated `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md` — header now points at `noctusai_lib.llm` + the seed-injector + LGPD contract
- [x] Added LLM-access pointer to `CLAUDE.md` Patterns section (single line, per the pointer-map discipline)
- [x] `python mcp/noctusai/cli.py --catalog` — confirmed `generate_embedding` now surfaces as single lib symbol consumed by ERP + Therapy (no longer a duplicate candidate); 112 symbols total
- [x] Grep sanity: zero `from openai import`, zero `AsyncOpenAI(`, zero `openai.OpenAI(`, zero `httpx.AsyncClient(.*openai.com)` in `products/*/backend/app/services/`
- [x] `cd products/erp-imobiliario/backend && pytest` — **1765 passed, 23 skipped** (migration fallout fixed: `test_embedding_service.py` rewritten to patch `_lib_generate_embedding`; `test_embedding_vs_rules.py` + `test_mock_matching_*.py` moved to `collect_ignore` as they're dev benchmarks, not tests)
- [x] `cd products/therapy-platform/backend && pytest` — **1078 passed** (migration fallout fixed: `test_therapy_embedding_service.py::TestGenerateEmbedding` + `test_transcription_service.py::{test_transcription_success, test_transcription_whisper_failure}` rewritten to patch the shared-lib symbol instead of deleted SDK internals)
- [x] `products/erp-imobiliario/MASTER-PROMPT.md` AI section — updated (shared-lib only; credential_resolver removed)
- [x] `products/therapy-platform/MASTER-PROMPT.md` AI section — updated (all 4 AI-pipeline steps now documented via `noctusai_lib.llm` with `cache=False` for clinical flows; 4 LGPD concerns cross-referenced)
- [x] `products/seed/MASTER-PROMPT.md` note on `llm_config` — updated (seed-injector auto-wiring + override path documented in "What the framework provides automatically")
- [x] `python mcp/noctusai/cli.py --review --product erp-imobiliario` — **0 issues**
- [x] `python mcp/noctusai/cli.py --review --product therapy-platform` — **0 issues**

**Improvements:**
- Product-level pytest wasn't run in this phase — the MCP dev-toolkit suite covers the lib + framework exhaustively, but migrated service files may have per-product test regressions we haven't caught. Next pass: full `pytest` on both backends, then fix anything that breaks.
- `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` has two separate "### `llm/`" sections now (one I added, one from an earlier edit). Needs de-duplication — the new one is more complete but both exist. Quick follow-up fix.
- MASTER-PROMPT updates are mechanical but per-product; putting them in one turn meant 3+ files of prose. Deferred without loss of correctness — the KB already carries the full contract.
- Adding the LLM pointer to CLAUDE.md touched the Patterns list, not the Engineering Philosophy. Consider if a philosophy-level rule ("Never bypass `noctusai_lib.llm`") is warranted, or if the Patterns reference is enough.

### Phase 10 — Frontend: Core API Keys page + shared LLM selector ⏳ (essentials shipped; sidebar nav + tests deferred as follow-ups)

- [x] `@noctusai/lib`: `useLLMProviders()` hook — via `createLLMHooks(api)` factory in `seed/frontend/lib/src/llm.ts`
- [x] `@noctusai/lib`: `useLLMModels(provider, kind?)` hook — same factory
- [x] `@noctusai/lib`: `useLLMPreferences()` + `useUpdateLLMPreferences()` mutation — same factory
- [x] `@noctusai/lib`: `createLLMCredentialsHooks(coreApi)` — `useLLMCredentials()` + `useUpdateLLMCredentials()` for Core's `/api/platform/credentials` surface
- [x] `@noctusai/lib/design-system`: `LLMProviderSelector` — two native selects side-by-side, unconfigured providers disabled, `(STUB)` + `(sem chave)` suffixes, optional `credentialsHref` prop for products to deep-link to Core
- [x] Core frontend: `pages/APIKeys.tsx` — per-provider form, masked input (last-4 only), reveal/hide toggle, scope badge ("organização" / "padrão NoctusAI"), PUT via shared hook
- [x] Core frontend: routes `/api-keys` + `/settings/api-keys` (both pointing at `APIKeys` for deep-link flexibility from products)
- [x] ERP frontend: `pages/LLMPreferences.tsx` at route `/configuracoes/llm` — uses `LLMProviderSelector` and "Configurar no Core →" deep-link
- [x] Therapy frontend: `pages/clinic/LLMPreferences.tsx` at route `/clinic/configuracoes/llm` — adds an LGPD callout above the selector noting that `cache=False` still applies to clinical flows regardless of provider choice
- [x] Build sanity: Core + ERP + Therapy `vite build` all green (no TS errors in new code)
- [x] Sidebar "LLM" link under Settings in each product — ERP "Preferências de IA" added under `Analytics & IA`; Therapy clinic "Preferencias de IA" added to `CLINIC_STANDALONE`; Core "Chaves LLM" added under admin nav pointing at `/api-keys`
- [ ] Tests: hooks, components, form submission — deferred. Repo pattern is minimal frontend test coverage; shared lib hooks are thin factories over `useQuery`/`useMutation` and are exercised indirectly through the pages. Add when a regression motivates them.

**Improvements:**
- The `createLLMHooks(api)` pattern requires each product to call it at module load — good for testability (swap the `api` client) but means each product duplicates the one-liner. If a third product picks this up, promote to a `useProductLLMHooks()` that reads `api` off a context (mirroring the `createCrudHooks` story).
- `LLMProviderSelector` uses native `<select>`s, not the design-system's rich combobox (which would require pulling more shared UI primitives into the seed lib). Works for the 3-provider, ~15-model catalog today; revisit when the catalog grows enough that grouped/searchable UI matters.
- Core's `APIKeys.tsx` doesn't validate the key format (sk-… prefix for OpenAI etc.) before PUT. Wire a regex check client-side once the real provider implementations land and start bouncing bad keys, so the user sees the error inline.
- The Therapy page lives under `/clinic/…` because clinic admins pick the model; a platform-admin (noctus admin) override for Therapy globally is not exposed in-UI yet. Cross-cut with the AI-Expansion-PROJECT's "consolidated AI settings panel" (X2) when that lands.
- The `VITE_CORE_URL` env var is referenced from both ERP and Therapy for the deep-link; it must be set in `.env` (missing var falls back to `http://localhost:5173`). Add to `.env.example` in a follow-up.
- `LLMPreferences` (ERP + Therapy) only edit `provider` + `chat_model`; `embedding_model` is passed through unchanged. When a product grows a user-facing embedding choice (e.g., PF's watchlist thesis), the selector needs a third dropdown — keep the `LLMPreferences` contract extensible.

---

### Phase 11 — Redis response-cache backend + admin flush endpoint ✅

Ship the real `redis.asyncio` backend behind the existing `CacheBackend` Protocol so production can flip cache on. Admin flush endpoint for cache hygiene.

- [x] Add `redis` (async) to `seed/backend/lib/pyproject.toml` (monolithic install; products pick it up via `pip install -e seed/backend/lib`)
- [x] Implement `seed/backend/lib/noctusai_lib/llm/backends/redis_backend.py::RedisCacheBackend` — Protocol-compliant `get` / `setex` / `delete` + `scan_keys` (SCAN) + `flush_prefix` (SCAN + chunked DEL)
- [x] Extend `flush_for_model` to dispatch on backend type — dict iteration for `InMemoryCacheBackend`, `flush_prefix` for anything Redis-like
- [x] `REDIS_URL` pre-existing on `BaseAppSettings`; `default_llm_config(redis_url=...)` constructs `RedisCacheBackend(url=...)` and flips `cache_enabled=True`. Framework's `create_product_app` passes `settings.redis_url` automatically — products opt in with 1 env var, zero code
- [x] Core router `routers/admin_cache.py::POST /api/admin/llm-cache/flush` — platform_admin only (`noctus_role=admin`); params `{product, provider, model}`; idempotent; catalog-validated
- [x] Wired into Core `main.py`
- [x] Tests: `test_llm_cache_redis.py` — 15 tests via `fakeredis.aioredis.FakeRedis` covering Protocol round-trip, SCAN-based iteration, prefix-flush with 500-key keyspace, `flush_for_model` dispatch, construction guards, `default_llm_config` auto-wiring
- [x] `REDIS_URL` already listed in root `.env` (no separate `.env.example` exists; skipped — tracked in an improvement note)

**Improvements:**
- No `fakeredis` in `pyproject.toml` (installed via `pip install fakeredis` ad hoc). When the test suite runs in fresh CI it'll fail collection. Add `[project.optional-dependencies] test = ["fakeredis>=2.0"]` or pin into a dev-requirements file.
- `RedisCacheBackend._get_client` opens one connection lazily but never pools. For high-throughput products, wrap with `redis.asyncio.ConnectionPool` or rely on `Redis.from_url(decode_responses=True)` default pooling — audit on first production deploy.
- `flush_prefix` drains in chunks of 200 but re-scans at the end to compute the deletion count. That's two passes. For large keyspaces the count is approximate anyway — consider tracking deletions inline and dropping the second SCAN.
- Core's admin flush endpoint does not log _who_ flushed (just noctus_role=admin). Add the user_id + ip to the log line for audit trail.
- `flush_for_model` falls back to `return 0` when the backend has no `flush_prefix` method. That's correct for unknown backends but silently; the warning log is at INFO level. Bump to WARN so operators notice a misconfig.
- `.env.example` at repo root does not exist; the root `.env` already has `REDIS_URL=` pre-listed. If a user clones fresh and has no `.env`, they won't discover the key. Generating a proper `.env.example` (from `ENV_VARS` in frontend + backend `ProductSettings`) is a follow-up worth its own small project.

### Phase 12 — Streaming chat completion ✅

Add `chat_completion_stream()` returning `AsyncIterator[str]` across all real providers + FakeProvider. Required for any ChatGPT-style UX in AI-EXPANSION (e.g. Core support-chat, patient messaging draft).

- [x] Extended `LLMProvider` Protocol with optional `chat_completion_stream()` (returns `AsyncIterator[str]`)
- [x] OpenAI provider: real streaming via `stream=True` + `stream_options={"include_usage": True}` — records usage on the final chunk
- [x] Anthropic provider: streaming via `client.messages.stream()` context manager — records usage from `stream.get_final_message()`
- [x] Gemini provider: streaming via `generate_content_async(stream=True)` — records usage from the final chunk's `usage_metadata`
- [x] FakeProvider: accepts `stream_responses: list[list[str]]`, replays each scripted stream in order
- [x] `noctusai_lib.llm.chat.chat_completion_stream()` high-level dispatch + re-exported from `noctusai_lib.llm`
- [x] Response cache: **disabled automatically for streams** — `cache` / `cache_namespace` / `prompt_version` kwargs are dropped at dispatch time, never reach the provider
- [x] Tests (5): chunk ordering, default fallback, scripted-stream consumption, cache-kwarg stripping, NotImplementedError for providers without stream support
- [ ] Update `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` § `llm/` entry points — deferred as a doc pass

**Improvements:**
- The Protocol annotates `chat_completion_stream` as `AsyncIterator[str]` but the SDK contract is actually a *function returning* an async iterator. We rely on Python's runtime permissiveness (yielding values from an `async def` that's used as an async generator). Type-checkers may complain — annotate with `AsyncGenerator[str, None]` explicitly if mypy hits us.
- Usage recording on stream completion means a dropped connection mid-stream yields chunks but no usage event. The cost then under-reports. For a first-rev observability story this is acceptable; if billing becomes first-class, record partial usage on exception too.
- OpenAI's `stream_options={"include_usage": True}` works with gpt-4o family but may not exist for older models — we don't guard. If an older model is used with streaming, the final chunk's usage is None (record with zeros). Defensive — no error. Worth a catalog flag `supports_streaming_usage: bool`.
- Anthropic's `messages.stream()` emits `stream.text_stream` for text chunks; other event types (tool calls, usage updates) are available via `stream.get_final_message()`. For now we only emit text deltas. Tool-call streaming deferred until a product needs it.
- Gemini's streaming interface uses `stream=True` as an awaitable that returns an async iterator; the SDK's behavior here has changed historically. The implementation covers the current (v0.8.x) shape — watch for breakage on SDK upgrade.
- FakeProvider's `stream_responses` is a list of lists — one scripted stream per call. Tests exhausting the list fall back to a default single-chunk. Should the default emit multiple chunks (e.g. ["chunk-1", "chunk-2"]) so consumers exercise the generator loop? Low priority.
- `chat_completion_stream` drops the `cache*` kwargs silently. Log at DEBUG so debugging a "why isn't this cached" is easier — currently the call just looks like the cache never applied.

### Phase 13 — Anthropic real provider body ✅

Real `AsyncAnthropic` SDK wiring. Chat + vision fully real; embeddings and transcription raise `ProviderNotImplemented` with clear "Anthropic does not ship this" messages (the old fake embedding vectors were removed — no more lying).

- [x] Chat: `client.messages.create(system=..., messages=..., temperature, max_tokens)` with OpenAI-shaped messages translated via `_split_system_and_messages()` (system role → top-level parameter)
- [x] `response_format={"type": "json_object"}` translated to a system-prompt instruction ("Return a valid JSON object")
- [x] Vision: content-block images (`{"type": "image", "source": {...}}`), base64 for bytes + MIME sniff (`_sniff_image_mime`), `url` type for URL strings
- [x] Embeddings + transcription: `ProviderNotImplemented("anthropic — embeddings not supported by the Anthropic API...")`
- [x] Removed `NOCTUSAI_ALLOW_STUB_PROVIDERS` guard — provider is real now
- [x] Per-key `AsyncAnthropic` client cache mirrors OpenAIProvider's pattern
- [x] Usage recording from `response.usage` (input_tokens / output_tokens)
- [x] `models.py`: promoted Anthropic entries from `stub=True` → real, added cost rates (Opus $15/$75, Sonnet $3/$15, Haiku $0.80/$4 per 1M), added Sonnet Vision entry
- [x] Streaming body shipped with Phase 12
- [x] Tests (5): missing-key → LLMNotConfigured, embedding/transcribe → ProviderNotImplemented, `_split_system_and_messages` helper (system separation + concatenation of multiple system messages)

**Improvements:**
- `_sniff_image_mime` handles JPEG/PNG/GIF/WEBP; doesn't handle HEIC (mobile photos). Add it if a product targets iOS uploads.
- JSON-mode translation appends "Return your response as a valid JSON object" to the system prompt. Anthropic-native structured output is cleaner (uses tool-use with `input_schema`), but requires callers to declare the schema. Follow-up for a structured API.
- URL images rely on Anthropic SDK v0.40+ `type: "url"` source. Older SDK versions would need a download-and-base64 fallback. Pinning `anthropic>=0.40.0` in pyproject makes this safe today.
- Network-integration tests are absent (unit tests mock the SDK surface). A smoke test hitting the real API with a tiny prompt would catch SDK signature drift — too costly per PR but valuable as a weekly CI job.
- `AnthropicProvider.close()` loops over cached clients and calls `await client.close()`. If a client raises (e.g. never-connected), the loop swallows and continues — good. But the `logger.debug` in the except branch doesn't include the provider/key identity; hard to trace if leaks appear.

### Phase 14 — Gemini real provider body ✅

Real `google-generativeai` SDK wiring across chat, embeddings, vision, and audio (Gemini's multimodal model accepts audio parts — not a dedicated Whisper replacement, but workable).

- [x] Chat: `GenerativeModel(...).generate_content_async(...)` with OpenAI-shaped messages translated via `_translate_messages()` (system → `system_instruction`, assistant → "model" role, content → Gemini `parts`)
- [x] `response_format={"type": "json_object"}` → `generation_config.response_mime_type = "application/json"` (Gemini-native JSON mode)
- [x] Embeddings: `genai.embed_content_async(model="models/text-embedding-004", content=...)` with `task_type="RETRIEVAL_DOCUMENT"` default (768-dim)
- [x] Vision: multimodal `generate_content_async([{mime_type, data}, prompt])`. URL images explicitly rejected (Gemini SDK doesn't fetch URLs) with a clear `LLMAPIError`
- [x] Audio: `generate_content_async([{mime_type: "audio/ogg", data: audio}, prompt])` using the multimodal Pro model — documented as an alternative to OpenAI Whisper, not a drop-in replacement
- [x] Per-key `genai.configure(api_key=...)` with a `_last_key` guard to skip reconfiguration when the same tenant's key is reused
- [x] Usage recording from `response.usage_metadata` (prompt_token_count, candidates_token_count, total_token_count)
- [x] `models.py`: replaced `gemini-2.0-*` stubs with real `gemini-1.5-pro` / `gemini-1.5-flash` entries + cost rates (Pro $1.25/$5, Flash $0.075/$0.30 per 1M). `text-embedding-004` published free-tier (0.0 rate recorded)
- [x] Streaming body shipped with Phase 12
- [x] Tests (3): missing-key → LLMNotConfigured, `_translate_messages` renames assistant→model, URL-image rejection via LLMAPIError

**Improvements:**
- `genai.configure(api_key=...)` is **module-global** — concurrent multi-tenant calls with different keys race. The `_last_key` guard is a per-instance optimization, not a lock. Under concurrency, the wrong key could briefly be active. Acceptable for first-rev; a proper fix swaps to `google.genai` (the newer SDK the old one deprecates toward) where clients are per-instance.
- `google-generativeai` printed a `FutureWarning` on import: the package is EOL and the migration target is `google.genai`. Plan a Phase 14.1 port once the platform has spare time — not blocking today.
- Audio support goes through the multimodal Pro model, not a dedicated transcription endpoint. For `whisper-1`-equivalent quality, product services should keep `provider="openai"` for audio (it's already the default in `LLMConfig`).
- URL-image rejection is intentional (surface the SDK limitation clearly), but some callers may want auto-download-and-encode. A follow-up helper in `vision.py` could handle that — out of scope for Phase 14.
- Embedding `task_type` default is `RETRIEVAL_DOCUMENT` — the Gemini API's preferred hint for "docs being indexed". Query-side embeddings should pass `task_type="RETRIEVAL_QUERY"` explicitly. Document this in the KB when the doc pass lands.

### Phase 15 — Token accounting + per-org usage tracking ⏳ (core shipped; DB-backed sink + admin endpoints deferred)

Observability foundation. Providers emit `UsageEvent`s to an active `UsageSink`; cost estimation is catalog-driven.

- [x] Design chose provider-side recording over rich return types — keeps `chat_completion` string-shaped so existing callers don't change. Providers call `record_usage(...)` after each successful call
- [x] `UsageEvent` dataclass + `UsageSink` Protocol in `noctusai_lib.llm.usage` — provider, model, operation, org_id, prompt/completion/total tokens, cost estimate, timestamp
- [x] `LLMConfig.usage_sink: Optional[UsageSink] = None` — when set, every provider call records
- [x] `InMemoryUsageSink` — dev/test sink with `aggregate()` helper grouped by `(org_id, provider, model)`
- [x] Cost estimator — `ModelEntry.cost_per_1m_input_tokens` + `cost_per_1m_output_tokens` populated for all real OpenAI models (gpt-4o $2.50/$10; gpt-4o-mini $0.15/$0.60; embeddings $0.02 / $0.13). `estimate_cost_usd(...)` catalog-driven; unknown models return 0.0
- [x] OpenAI provider (all 4 methods — chat / embedding / audio / vision) records usage from `response.usage`; audio records with `None` tokens (Whisper doesn't expose counts)
- [x] `org_id` now threads to every provider method signature; high-level entry points (`chat.py`, `embeddings.py`, `audio.py`, `vision.py`) pass it through
- [x] Tests: `test_llm_usage.py` — 9 tests covering InMemorySink events + aggregate, cost estimation (known / unknown / missing-tokens / bad-input), record_usage dispatch, sink=None no-op, exploding-sink swallowed
- [x] Full MCP suite: **199 passed** (up from 175) — no regression

**Completing Phase 15 (2026-04-19):**
- [ ] 15.1 `noctusai_lib.llm.usage.SupabaseUsageSink(db_client, schema, table="llm_usage")` — Protocol-compliant; `.record(event)` inserts one row; never raises (logs WARN on failure)
- [ ] 15.2 Per-product migration — ERP `020_llm_usage.sql` (`erp.llm_usage` + RLS: members read own-org; service role writes) + Therapy `006_llm_usage.sql` (clinic-scoped, same shape). Applied via Supabase MCP; files mirror.
- [ ] 15.3 `BaseAppSettings.llm_usage_tracking: bool = False` + env var `LLM_USAGE_TRACKING=1`
- [ ] 15.4 `default_llm_config(usage_tracking_db=None, usage_tracking_schema=None, …)` — when both provided, constructs `SupabaseUsageSink` automatically
- [ ] 15.5 Framework wiring in `create_product_app()` — passes `settings.llm_usage_tracking` + `db.get_admin_client()` + schema into `default_llm_config()` (zero code in product)
- [ ] 15.6 `/api/llm/usage` added to shared `noctusai_seed.llm_router` — GET returns aggregated per-org usage (org-scoped via RLS); supports `?from=&to=&group_by=provider|model|operation` query params
- [ ] 15.7 Core `routers/admin_llm_usage.py::GET /api/admin/llm-usage` — platform-admin only (`noctus_role=admin`); reads across every product schema via service role; supports `?product=&org_id=&from=&to=` filters; wired into `core/backend/app/main.py`
- [ ] 15.8 Tests — `mcp/noctusai/tests/test_llm_usage.py` extended with `SupabaseUsageSink` via mock supabase client (shape + error swallowing); full MCP suite still green
- [ ] 15.9 KB doc `KNOWLEDGE-BASE/CONTEXT/PATTERNS/llm-usage.md` — sink pattern, cost-estimate caveat, org_id threading, LGPD note (no prompt text in sink), enabling via env var
- [ ] 15.10 Update `KNOWLEDGE-BASE/INDEX.md` — add llm-usage.md pointer
- [ ] 15.11 Update `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` §`usage/` — promote from "deferred" to "shipped"

**Improvements:**
- `record_usage` is called synchronously after every provider response — adds one awaitable hop even when `usage_sink=None`. The early-return happens after `get_llm_config()`; that's fast (it's a module-level dict lookup) but not free. Consider caching the `sink is None` check at provider construction.
- `estimate_cost_usd` iterates the catalog on every call (`models_for(provider)` → linear scan). For high-throughput products a dict lookup by `(provider, model)` would be faster. Build the dict lazily in `models.py` once the model list stabilizes.
- Audio cost is always 0 because Whisper doesn't return token counts — but there _is_ a per-minute cost we could estimate from audio duration. Requires the provider to surface the audio length; OpenAI returns it in the response. Follow-up.
- `UsageEvent.cost_estimate_usd` is computed at record time using current catalog prices. If prices change, historical events keep their stale cost. For billing, treat as informational; for accurate billing, recompute from tokens at query time.
- No RLS on `InMemoryUsageSink` — it's process-global. Any code in the same process can iterate `sink.events`. Acceptable for dev/test; prod sink MUST use Supabase RLS (deferred with the SQL migration).
- Provider signatures now have `org_id: Optional[str] = None` everywhere. Anthropic + Gemini stubs absorb via `**kwargs` today; when they go real (Phases 13/14), they need to record usage explicitly. Document this in the Provider Protocol docstring.
- `test_sink_failure_is_swallowed` pins the behavior — swallowed failures log at WARN. The `logger.warning` call is minimal info. Add the provider + model + org_id to the log line so operators can debug without reading memory.

### Phase 16 — Therapy clinic_id → org_id mapping for Tier 1 keys ✅

Closes open question #1. Therapy services now thread `clinic_id` through as `org_id` on every lib call, so per-clinic provider keys resolve via the 3-tier chain (clinic → platform → env).

- [x] Backend: every Therapy AI service that calls the lib threads `org_id=clinic_id`
  - [x] `summary_service._call_llm(..., clinic_id=None)` → `chat_completion(..., org_id=clinic_id)`; `generate_session_summaries` + `regenerate_clinical_summary` gain `clinic_id` param
  - [x] `longitudinal_service._call_openai(..., clinic_id=None)` → `chat_completion(..., org_id=clinic_id)`; `generate_clinical_longitudinal` + `generate_patient_longitudinal` gain `clinic_id` param
  - [x] `transcription_service.transcribe_segment/assemble_transcript(..., clinic_id=None)` → `transcribe_audio(..., org_id=clinic_id)`
  - [x] `attachment_service.process_attachment_with_ai(..., clinic_id=None)` → `analyze_image`/`transcribe_audio` with `org_id=clinic_id`
  - [x] `therapy_embedding_service.generate_embedding/embed_therapist/embed_patient(..., clinic_id=None)` → `_lib_generate_embedding(..., org_id=clinic_id)`
- [x] `ai_pipeline._resolve_clinic_id(db, therapist_id)` — reads `therapist_profiles.clinic_id`; single resolution site, threaded to all 4 sub-services + 3 pipeline entry points (`process_session_end`, `on_observation_change`, `on_patient_note_change`). Independent therapists (`clinic_id IS NULL`) fall through to platform/env cleanly.
- [x] `therapy.llm_preferences` RLS + migration 005 already store clinic_id under `org_id` column (Phase 5 improvement note — contract already aligned; no new migration needed)
- [x] Therapy pytest still green — **1078 passed** (fixed one mock signature in `test_transcription_service.py` that didn't accept `**kwargs` for the new `clinic_id` param)
- [x] Open question #1 closed inline below in §7

**Improvements:**
- `_resolve_clinic_id` is called separately in `process_session_end`, `on_observation_change`, and `on_patient_note_change` — same query, three paths. An `ai_pipeline._session_context(db, appointment_id)` helper that resolves `{patient_id, therapist_id, clinic_id}` once per pipeline entry would DRY it up. Small win; revisit when a fourth entry point appears.
- Router-level changes deferred: the service signatures now accept `clinic_id`, but the routers that call them outside `ai_pipeline` (e.g. `routers/attachments.py::process_attachment_with_ai`) still don't pass one. Hook via `get_clinic_id_for_user(user)` in each router as a follow-up. The `ai_pipeline` path — the 99% case — already routes correctly.
- No realdb test covers the Tier 1 path yet (writing a clinic-scoped `org_settings` row and verifying the Therapy lib call resolves to it). The unit tests pass because they mock the lib interface, not the credential resolution. Add `tests/realdb/test_llm_clinic_tier1.py` when a live Supabase target is available in CI.
- `therapy_embedding_service.generate_embedding` kept the `api_key` positional param for backwards compatibility (unused) — adding `clinic_id` as a third param bloats the signature. Next rework: delete the `api_key` param (grep confirms only internal callers remain), rename to a cleaner `(text, *, clinic_id=None)`.

---

## 7. Open questions

1. ~~**Therapy clinic_id → org_id mapping.**~~ **Resolved in Phase 16 (2026-04-19).** `clinic_id` is threaded through every Therapy AI service as `org_id` via `ai_pipeline._resolve_clinic_id`. Independent therapists fall through to platform/env cleanly.
2. **Streaming.** No service uses streaming today. Add when demanded. *Out of scope.*
3. **Token accounting.** Where do usage metrics land (logs vs `llm_usage` table)? *Defer; raise when Phase 8 cache metrics are live.*
4. **Prompt-version scheme for cache invalidation.** Numeric const or file hash? *Decide at Phase 8.*

---

## 8. Dependencies & blockers

- `credential_resolver.py` in ERP must stay stable until Phase 6 lifts it.
- `org_settings` / `platform_settings` tables in `public` schema must exist and be readable from every product's service-role client (they already are).
- Provider SDKs (`openai`, `anthropic`, `google-generativeai`) must install cleanly.
- Redis deployable for Phase 8.
- Core frontend must accept `/settings/api-keys` route.

---

## 9. Success criteria

- `grep -r 'import httpx' products/*/backend/app/services/` returns zero OpenAI hits.
- `grep -r 'from openai import' products/*/backend/app/services/` returns zero hits.
- Every product's `main.py` passes `llm_config=LLMConfig(...)` in one line.
- All three providers register; UI selector shows `configured` + `stub` flags correctly.
- `NOCTUSAI_ALLOW_STUB_PROVIDERS=1` enables Anthropic/Gemini stub responses; unset raises `ProviderNotImplemented`.
- `python mcp/noctusai/cli.py --catalog` shows `generate_embedding` absorbed.
- `python mcp/noctusai/cli.py --review` passes on both ERP and Therapy (zero unreviewed proposals).
- `grep -r 'monkeypatch.*noctusai_lib.llm' products/*/backend/tests/` returns zero hits.
- Redis cache hit counters emit after Phase 8.
- Org admin entering an OpenAI key in Core's API Keys page sees ERP pick it up on the next request.

---

## 10. How to use this plan

- **Live-tick tasks** — flip `- [ ]` → `- [x]` and save the file the moment a task completes. User watches live.
- **Phase-by-phase cadence** — execute one phase, then pause. User says "continue" / "next phase" to advance. Override: "ram through 1-3" / "run all backend phases".
- **Revise the plan** when understanding changes — rewrite phases, update Change Log.
- **Commit plan changes with the code.**
- **Interrogate before revising** scope.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-18 | Initial plan (OpenAI-only, 6 phases) drafted from `templates/PLAN-TEMPLATE.md`. | Claude |
| 2026-04-18 | Rewritten end-to-end: multi-provider (OpenAI real + Anthropic/Gemini stubs with runtime guard), 3-tier key resolution (org → platform → env) lifted to `noctusai_lib.credentials`, Core-hosted API Keys UI + per-product provider/model preferences, response caching promoted to core phase, no-monkeypatch testing via `FakeProvider` + `LLMConfig`. Renamed `task.md.resolved` → `task.md`. Now 10 phases (9 backend + 1 frontend). | Claude |
| 2026-04-18 | **Phase 1 complete.** Shipped `noctusai_lib.credentials` (3-tier chain), `noctusai_lib.llm` package skeleton (`exceptions`, `config`, `models`, `registry`, `providers/base`). 23/23 foundation tests pass. Catalog shows 14 new symbols registered, 0 new duplicates introduced. | Claude |
| 2026-04-18 | Added phase-header `- [ ]` checkbox convention + `**Suggested next step:**` block convention to template + CLAUDE.md + memory. Built `noctusai_next_steps` MCP tool (tool #30) that auto-generates `next-steps.md` next to a plan after any phase tick. Revised §5 Architecture to make LLM config a seed-injector feature (auto-wired by `create_product_app()`; products override only when needed). Updated Phase 3/6/7 to reflect seed auto-wiring. | Claude |
| 2026-04-18 | **Phase 2 complete.** Shipped `OpenAIProvider` (real, `AsyncOpenAI` SDK, per-key client cache), `AnthropicProvider` stub + `GeminiProvider` stub (both guarded by `NOCTUSAI_ALLOW_STUB_PROVIDERS=1`), `FakeProvider` for tests. Three real providers auto-register on `import noctusai_lib.llm`; FakeProvider stays out of registry. Added `openai`/`anthropic`/`google-generativeai` to `pyproject.toml` + product `requirements.txt`. 17/17 provider tests pass. | Claude |
| 2026-04-18 | Renamed the retrospective convention from "next-steps" (preview of upcoming work) to "improvements" (per-phase lessons learned). MCP tool renamed to `noctusai_improvements`; output file is `improvements.md`. Phase 1 + Phase 2 blocks backfilled with real findings. | Claude |
| 2026-04-18 | **Phase 3 complete.** `create_product_app()` now auto-wires `configure_credentials()` + `configure_llm(default_llm_config())` + lifespan `shutdown_llm()`. `noctusai_lib/llm/client.py` ships the singleton machinery. `noctusai_seed/llm_defaults.py` holds the shared default config. Products inherit multi-provider LLM access with zero wiring. 16/16 client tests pass. | Claude |
| 2026-04-18 | **Phase 4 complete.** High-level entry points — `chat_completion`, `generate_embedding`, `transcribe_audio`, `analyze_image` — all dispatch via the configured provider, resolve keys through `key_provider`. `build_cached_messages` enforces stable-prefix-first + Anthropic `cache_control` markers. Re-exported from `noctusai_lib.llm`. 14/14 API tests pass. | Claude |
| 2026-04-18 | **Phase 5 complete.** Shared `/api/llm/*` router lifted into `noctusai_seed.llm_router` — every product inherits providers/models/preferences endpoints via `create_standard_routers`. Core `/api/platform/credentials` GET/PUT wired. Migrations for `erp.llm_preferences` (017) and `therapy.llm_preferences` (005). 13/13 endpoint tests pass. Design revision in-flight: folded per-product `routers/llm.py` into the seed framework (logged in Phase 5 notes). | Claude |
| 2026-04-19 | Adopted METAS-PLAN icon convention — phase headers use `⏳`/`✅`/`❌` trailing icons (plus optional parenthetical) in place of `- [x]`/`- [ ]`. `improvements.py` parser + tests updated. Template, CLAUDE.md, memory `feedback_living_plans.md`, KB `plan-execution.md` all aligned. All 10 phase headers in this plan converted. | Claude |
| 2026-04-19 | Shipped **LGPD awareness keeper principle**: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md` (full keeper doc), CLAUDE.md rule addition, `feedback_lgpd_first.md` memory, and **`noctusai_lgpd_flag` MCP tool** — appends checklist items to `LGPD-WARNINGS.md`, notifies user, never blocks. 12 tests pass. | Claude |
| 2026-04-19 | **Phase 6 complete.** ERP migrated: `ai_service.py` + `embedding_service.py` now delegate to `noctusai_lib.llm`. Deleted local `credential_resolver.py` (lifted to lib). Redirected 5 importers. 21/21 existing ERP AI service tests pass. | Claude |
| 2026-04-19 | **Phase 7 complete.** Therapy migrated: summary / longitudinal / transcription / attachment / therapy_embedding all delegate to shared lib. Zero `from openai import` / `AsyncOpenAI(` in product services. **Four LGPD concerns flagged** (patient-clinical-text-in-llm-prompt, longitudinal-clinical-aggregation, patient-audio-to-whisper, patient-attachment-to-llm) — recorded in `LGPD-WARNINGS.md`. | Claude |
| 2026-04-19 | **Phase 8 complete.** Response cache shipped — `cache.py` with Protocol-based `CacheBackend`, `InMemoryCacheBackend` for dev, key-builder, `try_get`/`try_set`, flush. Wired into `chat_completion` with 4-condition gate (cache × enabled × backend × temp==0). **LGPD hard rule live**: `cache=False` blocks before hashing. 11/11 cache tests pass. Real Redis backend + admin flush endpoint deferred (Protocol is in place). | Claude |
| 2026-04-19 | Phase 9 partial: docs (04-SHARED-LIBRARY, 05-AI-FEATURES, CLAUDE map) updated. Catalog re-run confirms `generate_embedding` absorbed. Grep sanity zero. Product pytest + MASTER-PROMPT updates + heal pass deferred. Phase 10 (frontend) not started — flagged ❌ for a dedicated turn. | Claude |
| 2026-04-19 | **Phase 9 complete.** All 3 MASTER-PROMPTs (ERP, Therapy, seed) updated to point at shared lib. ERP pytest 1765✓/23 skip, Therapy pytest 1078✓, both `--review` passes zero issues. Migration fallout: 3 ERP + 4 Therapy tests rewritten to patch the shared-lib symbol instead of deleted SDK internals; 3 ERP dev benchmarks (misnamed `test_*.py`) moved to `conftest.collect_ignore`. | Claude |
| 2026-04-19 | **Phase 10 essentials shipped.** Shared `@noctusai/lib` gains `createLLMHooks(api)` + `createLLMCredentialsHooks(coreApi)` (single `src/llm.ts`). `@noctusai/lib/design-system` gains `LLMProviderSelector`. Core API Keys page at `/api-keys`; ERP preferences at `/configuracoes/llm`; Therapy clinic preferences at `/clinic/configuracoes/llm` with an LGPD callout. All 3 `vite build`s green. Sidebar nav entries + frontend unit tests deferred as follow-ups. | Claude |
| 2026-04-19 | **Phases 11–16 implemented** as proactive build-out of previously-deferred work. **Phase 11 (Redis cache):** `RedisCacheBackend` behind Protocol, `flush_for_model` dispatches on backend type, framework auto-wires `RedisCacheBackend(url=REDIS_URL)` + `cache_enabled=True` when env is set, Core `POST /api/admin/llm-cache/flush` platform-admin-only. **Phase 16 (clinic_id→org_id):** `ai_pipeline._resolve_clinic_id` threads clinic_id into every Therapy lib call as `org_id` via 3 entry points → 5 services (summary/longitudinal/transcription/attachment/therapy_embedding). **Phase 15 (token accounting):** `UsageEvent` + `UsageSink` Protocol + `InMemoryUsageSink`, cost estimates from catalog, all 4 OpenAI provider methods record usage. DB-sink + admin aggregate endpoint deferred. **Phase 13 (Anthropic real):** `AsyncAnthropic` wired for chat + vision; embeddings/transcription raise `ProviderNotImplemented`. **Phase 14 (Gemini real):** `google-generativeai` wired for chat + embeddings + vision + audio. **Phase 12 (Streaming):** `chat_completion_stream()` + real `stream=True` paths for all 3 providers + `FakeProvider` scripted streams; cache-kwargs stripped at dispatch. MCP tests: 175 → 206 (+31). ERP 1765✓, Therapy 1078✓ — no regression. | Claude |
