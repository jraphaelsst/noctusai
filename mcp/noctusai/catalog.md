# NoctusAI Shared Library Catalog

> **Auto-generated** by `python mcp/noctusai/cli.py --catalog`. Do not edit by hand.
> This artifact replaces the drift-prone handwritten catalog. It answers:
> *what's in the lib, who uses it, and what's duplicated across products that probably shouldn't be.*

- **Lib roots scanned**: `noctusai_lib` (seed/lib/backend/noctusai_lib), `noctusai_seed` (seed/framework/backend/noctusai_seed)
- **Products scanned**: `adconnect`, `daily-life`, `erp-imobiliario`, `mailing`, `personal-finance`, `seed`, `therapy-platform`
- **Totals**: 112 symbols · 34 orphans · 43 single-consumer · 27 duplicate candidates

## Symbols

### `noctusai_lib.action_log`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `log_action` | def | `(db, table_name: str, user_id_column: str, user_id: str, tip…` | Insert a row into a product's action log table. | erp-imobiliario, therapy-platform | 2 |

### `noctusai_lib.app_factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_app` | def | `(app: FastAPI, settings, *, limiter=None, cors_allow_headers…` | Apply shared configuration to a FastAPI app instance. | lib:noctusai_seed | 1 |

### `noctusai_lib.auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `first_or_none` | def | `(result) -> Optional[dict]` | Extract first record from a Supabase list response, or None. | adconnect, daily-life, erp-imobiliario, personal-finance, seed, therapy-platform | 13 |
| `get_sso_context` | def | `(user) -> dict` | Extract all SSO-synced context from user_metadata. | — | 0 |
| `make_get_current_user` | def | `(get_supabase_client_fn)` | Factory that creates a product-specific get_current_user dependency. | — | 0 |
| `require_role` | def | `(get_user_role_fn, *allowed_roles: str)` | FastAPI dependency factory that enforces role-based access. | — | 0 |
| `resolve_sso_role` | def | `(user) -> Optional[str]` | Check SSO metadata for product-level admin access. | adconnect, daily-life, erp-imobiliario, lib:noctusai_seed, personal-finance, seed, therapy-platform | 7 |

### `noctusai_lib.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BaseAppSettings` | class | `` | Shared settings base for all NoctusAI backends. | lib:noctusai_seed | 1 |

### `noctusai_lib.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_credentials` | def | `(*, supabase_url: str, supabase_anon_key: str, supabase_serv…` | Configure credential resolution. Call once at product startup. | lib:noctusai_lib, lib:noctusai_seed | 2 |
| `resolve_credential` | def | `(key: str, org_id: Optional[str]=None) -> Optional[str]` | Resolve a credential value through the 3-tier chain. | erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed | 9 |

### `noctusai_lib.database`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_supabase_client` | def | `(url: str, anon_key: str, service_role_key: str, schema: Opt…` | Create a Supabase client with the given configuration. | lib:noctusai_lib, lib:noctusai_seed | 2 |

### `noctusai_lib.email_templates`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `send_password_reset_email` | def | `(to: str, product_name: str, reset_url: str) -> bool` | Send a password reset email with product branding. | — | 0 |
| `send_product_invitation_email` | def | `(to: str, product_name: str, org_name: str, role_label: str,…` | Send a product-level team invitation email. | lib:noctusai_seed, therapy-platform | 2 |

### `noctusai_lib.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AppException` | class | `` | Base application exception with standardized error response. | lib:noctusai_lib | 2 |
| `ConflictError` | class | `` | Resource conflict (e.g., duplicate). | — | 0 |
| `ForbiddenError` | class | `` | Access denied. | — | 0 |
| `InternalError` | class | `` | Internal server error. | — | 0 |
| `NotFoundError` | class | `` | Resource not found. | — | 0 |
| `UnauthorizedError` | class | `` | Authentication required. | — | 0 |
| `ValidationError_` | class | `` | Validation error for business logic. | — | 0 |
| `app_exception_handler` | async def | `(request: Request, exc: AppException) -> JSONResponse` | Handle AppException and return standardized error response. | lib:noctusai_lib | 1 |
| `format_error_response` | def | `(code: str, message: str, details: Optional[dict]=None) -> d…` | Format a standardized error response. | — | 0 |
| `generic_exception_handler` | async def | `(request: Request, exc: Exception) -> JSONResponse` | Handle unexpected exceptions. | lib:noctusai_lib | 1 |
| `http_exception_handler` | async def | `(request: Request, exc: HTTPException) -> JSONResponse` | Handle FastAPI HTTPException and return standardized error response. | lib:noctusai_lib | 1 |
| `postgrest_exception_handler` | async def | `(request: Request, exc: Exception) -> JSONResponse` | Handle PostgREST APIError with proper status codes for common PG errors. | lib:noctusai_lib | 1 |
| `validation_exception_handler` | async def | `(request: Request, exc: ValidationError) -> JSONResponse` | Handle Pydantic ValidationError and return standardized error response. | lib:noctusai_lib | 1 |

### `noctusai_lib.invitations`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `accept_invitation` | def | `(db, table: str, invitation_id: str) -> None` | Mark an invitation as accepted. | lib:noctusai_seed, therapy-platform | 2 |
| `cancel_invitation` | def | `(db, table: str, invitation_id: str, org_id: str) -> None` | Cancel a pending invitation. Verifies it belongs to the org and is pending. | lib:noctusai_seed | 1 |
| `create_invitation` | def | `(db, table: str, org_id: str, email: str, role: str, invited…` | Create an invitation record with a unique token. | lib:noctusai_seed | 1 |
| `expire_old_invitations` | def | `(db, table: str) -> int` | Expire all invitations past their expires_at. Returns count expired. | — | 0 |
| `generate_invite_token` | def | `() -> str` | Generate a cryptographically secure invitation token. | therapy-platform | 1 |
| `list_pending_invitations` | def | `(db, table: str, org_id: str) -> list` | List all pending invitations for an organization. | lib:noctusai_seed | 1 |
| `validate_invitation` | def | `(db, table: str, token: str) -> dict` | Validate an invitation token. Returns the invitation record. | lib:noctusai_seed, therapy-platform | 2 |

### `noctusai_lib.llm.audio`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `transcribe_audio` | async def | `(audio: bytes, *, model: Optional[str]=None, provider: Optio…` | Transcribe audio bytes to text via the configured provider. | lib:noctusai_lib, therapy-platform | 3 |

### `noctusai_lib.llm.cache`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CacheBackend` | class | `` | Minimal Redis-like interface we need. Production uses `redis.asyncio`; | lib:noctusai_lib | 1 |
| `InMemoryCacheBackend` | class | `` | Simple dict-backed CacheBackend — for tests and dev environments | lib:noctusai_lib | 1 |
| `build_cache_key` | def | `(*, product: str, provider: str, model: str, prompt_version:…` | Build a deterministic cache key from the request shape. | lib:noctusai_lib | 2 |
| `flush_for_model` | async def | `(backend: CacheBackend, *, product: str, provider: str, mode…` | Delete every cached entry for a given (product, provider, model). | — | 0 |
| `try_get` | async def | `(backend: CacheBackend, key: str) -> tuple[bool, Optional[An…` | Attempt a cache read. Returns (hit, value). Never raises — cache | lib:noctusai_lib | 1 |
| `try_set` | async def | `(backend: CacheBackend, key: str, value: Any, ttl_seconds: i…` | Attempt a cache write. Never raises — write failures are swallowed | lib:noctusai_lib | 1 |

### `noctusai_lib.llm.chat`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_cached_messages` | def | `(static_system: str, dynamic_user: str, *, provider: Optiona…` | Structure a message list for maximum prompt-cache hit rate. | lib:noctusai_lib | 1 |
| `chat_completion` | async def | `(messages: list[dict], *, model: Optional[str]=None, provide…` | Route a chat completion through the configured provider. | erp-imobiliario, lib:noctusai_lib, therapy-platform | 4 |

### `noctusai_lib.llm.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_llm` | def | `(config: LLMConfig) -> None` | Install an LLMConfig as the process-wide active configuration. | lib:noctusai_seed | 2 |
| `get_llm_config` | def | `() -> LLMConfig` | Return the active LLMConfig. Raises if `configure_llm()` wasn't called. | lib:noctusai_lib, lib:noctusai_seed | 6 |
| `get_provider` | def | `(name: Optional[str]=None) -> LLMProvider` | Return a Provider instance by name (or the configured default). | lib:noctusai_lib | 4 |
| `resolve_api_key` | def | `(provider: str, org_id: Optional[str]=None) -> str` | Resolve an API key via the active config's key_provider. | lib:noctusai_lib | 4 |
| `shutdown_llm` | async def | `() -> None` | Close every cached provider and clear the active config. | lib:noctusai_seed | 2 |

### `noctusai_lib.llm.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMConfig` | class | `` | Product-level LLM configuration. | lib:noctusai_lib, lib:noctusai_seed | 6 |

### `noctusai_lib.llm.embeddings`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `generate_embedding` | async def | `(text: str, *, model: Optional[str]=None, provider: Optional…` | Generate an embedding vector via the configured provider. | erp-imobiliario, lib:noctusai_lib, therapy-platform | 3 |

### `noctusai_lib.llm.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMAPIError` | class | `` | Downstream error from an LLM provider's API (rate-limit, timeout, etc.). | lib:noctusai_lib | 3 |
| `LLMNotConfigured` | class | `` | The resolved API key for the requested provider is empty/missing. | lib:noctusai_lib, therapy-platform | 8 |
| `ProviderNotImplemented` | class | `` | A stub provider's method was called outside UI-development mode. | lib:noctusai_lib | 4 |

### `noctusai_lib.llm.models`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ModelEntry` | class | `` | One row of the catalog. Immutable so it's safely shareable. | lib:noctusai_lib | 1 |
| `all_providers` | def | `() -> list[str]` | All distinct provider names present in the catalog (sorted). | lib:noctusai_lib, lib:noctusai_seed | 2 |
| `is_stub_model` | def | `(provider: str, model_id: str) -> bool` | True if the given (provider, model_id) pair is served by a stub. | lib:noctusai_lib | 1 |
| `models_for` | def | `(provider: str, kind: Optional[ModelKind]=None) -> list[Mode…` | Return the catalog entries for a provider, optionally filtered by kind. | lib:noctusai_lib, lib:noctusai_seed | 2 |

### `noctusai_lib.llm.providers.anthropic_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AnthropicProvider` | class | `` | Stub Anthropic provider. Replace bodies with `AsyncAnthropic` SDK calls. | — | 0 |

### `noctusai_lib.llm.providers.base`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMProvider` | class | `` | Protocol all providers implement. See module docstring for the rules. | lib:noctusai_lib | 4 |

### `noctusai_lib.llm.providers.fake_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeProvider` | class | `` | Scripted test double. Not registered; tests use it via LLMConfig override. | lib:noctusai_lib | 2 |

### `noctusai_lib.llm.providers.gemini_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GeminiProvider` | class | `` | Stub Gemini provider. Replace bodies with `google.generativeai` calls. | — | 0 |

### `noctusai_lib.llm.providers.openai_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OpenAIProvider` | class | `` | Real OpenAI provider using the official `openai` SDK. | — | 0 |

### `noctusai_lib.llm.registry`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_provider_class` | def | `(name: str) -> Type[LLMProvider]` | Look up a registered provider class by name. Raises KeyError if absent. | lib:noctusai_lib | 2 |
| `list_providers` | def | `() -> list[str]` | All currently registered provider names (sorted). | lib:noctusai_lib | 1 |
| `register` | def | `(name: str, cls: Type[LLMProvider]) -> None` | Register a provider class under a name. | lib:noctusai_lib | 4 |

### `noctusai_lib.llm.vision`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `analyze_image` | async def | `(image: Union[bytes, str], prompt: str, *, model: Optional[s…` | Analyze an image against a text prompt via the configured provider. | lib:noctusai_lib, therapy-platform | 2 |

### `noctusai_lib.logging_config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_logging` | def | `(debug: bool=True, json_logs: bool=False, app_name: str='noc…` | Configure application logging. | lib:noctusai_seed, personal-finance, therapy-platform | 3 |

### `noctusai_lib.middleware`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CorrelationIdMiddleware` | class | `` | Middleware that generates or extracts correlation IDs for request tracking. | lib:noctusai_lib | 1 |
| `RequestLoggingMiddleware` | class | `` | Middleware that logs request/response details with timing. | lib:noctusai_lib | 1 |
| `get_correlation_id` | def | `() -> str` | Get the current request's correlation ID. | lib:noctusai_lib | 1 |

### `noctusai_lib.notifications`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `map_notification_from_pt` | def | `(data: dict) -> dict` | Map Portuguese API fields back to core notification record (English). | — | 0 |
| `map_notification_to_pt` | def | `(record: dict) -> dict` | Map a core notification record (English fields) to Portuguese API fields. | lib:noctusai_seed | 1 |

### `noctusai_lib.page_status`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_visible_pages` | def | `(db, user_org_role: str | None=None) -> list[str]` | Return list of visible page route names for the given user role. | — | 0 |

### `noctusai_lib.rate_limit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_limiter` | def | `(redis_url: Optional[str]=None, default_limits: Optional[lis…` | Create a slowapi Limiter with optional Redis backing. | lib:noctusai_seed | 1 |

### `noctusai_lib.responses`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PaginatedResponse` | class | `` | Standardized paginated response. | — | 0 |
| `PaginationMeta` | class | `` | Pagination metadata. | — | 0 |
| `calculate_pagination` | def | `(page: int, page_size: int, max_page_size: int=200) -> tuple…` | Calculate pagination parameters with validation. | — | 0 |
| `deleted_response` | def | `(resource: str, resource_id: str) -> dict` | Create a standardized deletion response. | — | 0 |
| `ok_response` | def | `(message: str='Operação realizada com sucesso') -> dict` | Create a simple success acknowledgment response. | daily-life | 5 |
| `paginated_response` | def | `(data: list, total: int, page: int, page_size: int) -> dict` | Create a standardized paginated response. | daily-life, mailing | 7 |
| `success_response` | def | `(data: Any, total: Optional[int]=None) -> dict` | Create a standardized success response. | daily-life, mailing | 13 |

### `noctusai_lib.roles`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ADMIN_ROLES` | const | `` |  | — | 0 |
| `DEV_ROLES` | const | `` |  | lib:noctusai_lib | 1 |
| `MANAGE_TEAM_ROLES` | const | `` |  | — | 0 |
| `ORG_ROLES` | const | `` |  | — | 0 |
| `ORG_ROLE_LABELS` | const | `` |  | lib:noctusai_seed | 1 |
| `PRODUCT_ADMIN_ROLES` | const | `` |  | — | 0 |
| `can_manage_billing` | def | `(org_role: str | None) -> bool` | Check if the user can manage billing/subscription. | — | 0 |
| `can_manage_team` | def | `(org_role: str | None) -> bool` | Check if the user can invite/remove team members. | — | 0 |
| `is_dev_or_owner` | def | `(org_role: str | None) -> bool` | Check if the user can see in-development pages. | — | 0 |

### `noctusai_lib.testing.clients`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthClient` | class | `` | Wraps FastAPI TestClient with automatic Authorization header. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, mailing, personal-finance, seed, therapy-platform | 8 |
| `MockUser` | class | `` | Simulates a Supabase auth user object. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, mailing, personal-finance, seed, therapy-platform | 9 |
| `MockUserResponse` | class | `` | Wraps MockUser to simulate supabase.auth.get_user() response. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, mailing, personal-finance, seed, therapy-platform | 9 |

### `noctusai_lib.testing.mocks`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MockFilterBuilder` | class | `` | Mirrors SyncFilterRequestBuilder. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, therapy-platform | 7 |
| `MockQueryBuilder` | class | `` | Mirrors SyncQueryRequestBuilder. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, therapy-platform | 7 |
| `MockRequestBuilder` | class | `` | Mirrors SyncRequestBuilder — the object returned by .table(name). | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, therapy-platform | 7 |
| `MockSelectBuilder` | class | `` | Mirrors SyncSelectRequestBuilder. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, therapy-platform | 7 |
| `MockSupabaseClient` | class | `` | Mocked Supabase client with per-table data control and response queues. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, mailing, personal-finance, seed, therapy-platform | 13 |
| `MockSupabaseResponse` | class | `` | Simulates a Supabase PostgREST response. | adconnect, daily-life, erp-imobiliario, lib:noctusai_lib, mailing, personal-finance, seed, therapy-platform | 26 |

### `noctusai_seed.app`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_product_app` | def | `(name: str, schema: str, settings, routers: Optional[list]=N…` | Create a fully configured FastAPI app for a NoctusAI product. | adconnect, daily-life, erp-imobiliario, lib:noctusai_seed, mailing, personal-finance, seed, therapy-platform | 8 |

### `noctusai_seed.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductSettings` | class | `` | Base settings that every product inherits. | adconnect, daily-life, erp-imobiliario, lib:noctusai_seed, mailing, personal-finance, seed, therapy-platform | 8 |

### `noctusai_seed.database`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DatabaseModule` | class | `` | Encapsulates database client factories for a product schema. | — | 0 |
| `create_database_module` | def | `(settings, schema: str) -> DatabaseModule` | Factory to create database module for a product. | adconnect, daily-life, erp-imobiliario, lib:noctusai_seed, mailing, personal-finance, seed, therapy-platform | 16 |

### `noctusai_seed.dependencies`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductDependencies` | class | `` | Encapsulates standard FastAPI dependencies for a product. | — | 0 |
| `create_dependencies` | def | `(db) -> ProductDependencies` | Factory to create standard dependencies for a product. | adconnect, daily-life, erp-imobiliario, lib:noctusai_seed, mailing, personal-finance, seed, therapy-platform | 9 |

### `noctusai_seed.llm_defaults`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_LLM_CONFIG` | const | `` |  | lib:noctusai_seed | 1 |
| `default_llm_config` | def | `(**overrides: Any) -> LLMConfig` | Build an LLMConfig using platform defaults, with optional overrides. | lib:noctusai_seed | 2 |

### `noctusai_seed.llm_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ModelInfo` | class | `` |  | — | 0 |
| `PreferencesBody` | class | `` |  | — | 0 |
| `ProviderInfo` | class | `` |  | — | 0 |
| `create_llm_router` | def | `(deps) -> APIRouter` | Build the `/api/llm/*` router for a product. | lib:noctusai_seed | 1 |

### `noctusai_seed.rate_limit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_product_limiter` | def | `(settings)` | Create a rate limiter using the product's settings. | adconnect, daily-life, erp-imobiliario, mailing, personal-finance, seed, therapy-platform | 7 |

### `noctusai_seed.routers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_standard_routers` | def | `(deps, settings, product_name: str, version: str='0.1.0') ->…` | Create the standard routers every product includes. | lib:noctusai_seed | 1 |

## Orphans

Symbols defined in the lib but with **zero importers** across all products.
Candidates for deletion — but confirm first (may be staged for imminent use,
or intentionally-public for future consumers).

| Symbol | Kind | Location |
|---|---|---|
| `noctusai_lib.auth.get_sso_context` | def | `seed/lib/backend/noctusai_lib/auth.py:117` |
| `noctusai_lib.auth.make_get_current_user` | def | `seed/lib/backend/noctusai_lib/auth.py:62` |
| `noctusai_lib.auth.require_role` | def | `seed/lib/backend/noctusai_lib/auth.py:140` |
| `noctusai_lib.email_templates.send_password_reset_email` | def | `seed/lib/backend/noctusai_lib/email_templates.py:136` |
| `noctusai_lib.exceptions.ConflictError` | class | `seed/lib/backend/noctusai_lib/exceptions.py:92` |
| `noctusai_lib.exceptions.ForbiddenError` | class | `seed/lib/backend/noctusai_lib/exceptions.py:81` |
| `noctusai_lib.exceptions.InternalError` | class | `seed/lib/backend/noctusai_lib/exceptions.py:107` |
| `noctusai_lib.exceptions.NotFoundError` | class | `seed/lib/backend/noctusai_lib/exceptions.py:40` |
| `noctusai_lib.exceptions.UnauthorizedError` | class | `seed/lib/backend/noctusai_lib/exceptions.py:70` |
| `noctusai_lib.exceptions.ValidationError_` | class | `seed/lib/backend/noctusai_lib/exceptions.py:55` |
| `noctusai_lib.exceptions.format_error_response` | def | `seed/lib/backend/noctusai_lib/exceptions.py:122` |
| `noctusai_lib.invitations.expire_old_invitations` | def | `seed/lib/backend/noctusai_lib/invitations.py:205` |
| `noctusai_lib.llm.cache.flush_for_model` | async def | `seed/lib/backend/noctusai_lib/llm/cache.py:116` |
| `noctusai_lib.llm.providers.anthropic_provider.AnthropicProvider` | class | `seed/lib/backend/noctusai_lib/llm/providers/anthropic_provider.py:33` |
| `noctusai_lib.llm.providers.gemini_provider.GeminiProvider` | class | `seed/lib/backend/noctusai_lib/llm/providers/gemini_provider.py:27` |
| `noctusai_lib.llm.providers.openai_provider.OpenAIProvider` | class | `seed/lib/backend/noctusai_lib/llm/providers/openai_provider.py:30` |
| `noctusai_lib.notifications.map_notification_from_pt` | def | `seed/lib/backend/noctusai_lib/notifications.py:26` |
| `noctusai_lib.page_status.get_visible_pages` | def | `seed/lib/backend/noctusai_lib/page_status.py:17` |
| `noctusai_lib.responses.PaginatedResponse` | class | `seed/lib/backend/noctusai_lib/responses.py:25` |
| `noctusai_lib.responses.PaginationMeta` | class | `seed/lib/backend/noctusai_lib/responses.py:17` |
| `noctusai_lib.responses.calculate_pagination` | def | `seed/lib/backend/noctusai_lib/responses.py:110` |
| `noctusai_lib.responses.deleted_response` | def | `seed/lib/backend/noctusai_lib/responses.py:92` |
| `noctusai_lib.roles.ADMIN_ROLES` | const | `seed/lib/backend/noctusai_lib/roles.py:13` |
| `noctusai_lib.roles.MANAGE_TEAM_ROLES` | const | `seed/lib/backend/noctusai_lib/roles.py:16` |
| `noctusai_lib.roles.ORG_ROLES` | const | `seed/lib/backend/noctusai_lib/roles.py:10` |
| `noctusai_lib.roles.PRODUCT_ADMIN_ROLES` | const | `seed/lib/backend/noctusai_lib/roles.py:23` |
| `noctusai_lib.roles.can_manage_billing` | def | `seed/lib/backend/noctusai_lib/roles.py:47` |
| `noctusai_lib.roles.can_manage_team` | def | `seed/lib/backend/noctusai_lib/roles.py:42` |
| `noctusai_lib.roles.is_dev_or_owner` | def | `seed/lib/backend/noctusai_lib/roles.py:37` |
| `noctusai_seed.database.DatabaseModule` | class | `seed/framework/backend/noctusai_seed/database.py:25` |
| `noctusai_seed.dependencies.ProductDependencies` | class | `seed/framework/backend/noctusai_seed/dependencies.py:28` |
| `noctusai_seed.llm_router.ModelInfo` | class | `seed/framework/backend/noctusai_seed/llm_router.py:38` |
| `noctusai_seed.llm_router.PreferencesBody` | class | `seed/framework/backend/noctusai_seed/llm_router.py:46` |
| `noctusai_seed.llm_router.ProviderInfo` | class | `seed/framework/backend/noctusai_seed/llm_router.py:32` |

## Single-consumer symbols

Lib symbols imported by exactly **one product**. Informational only —
a symbol may legitimately live in lib because it encodes a platform-wide
policy, even if currently only one product exercises it.

| Symbol | Used by | Imports |
|---|---|---|
| `noctusai_lib.app_factory.configure_app` | lib:noctusai_seed | 1 |
| `noctusai_lib.config.BaseAppSettings` | lib:noctusai_seed | 1 |
| `noctusai_lib.exceptions.AppException` | lib:noctusai_lib | 2 |
| `noctusai_lib.exceptions.app_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.exceptions.generic_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.exceptions.http_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.exceptions.postgrest_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.exceptions.validation_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.invitations.cancel_invitation` | lib:noctusai_seed | 1 |
| `noctusai_lib.invitations.create_invitation` | lib:noctusai_seed | 1 |
| `noctusai_lib.invitations.generate_invite_token` | therapy-platform | 1 |
| `noctusai_lib.invitations.list_pending_invitations` | lib:noctusai_seed | 1 |
| `noctusai_lib.llm.cache.CacheBackend` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.cache.InMemoryCacheBackend` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.cache.build_cache_key` | lib:noctusai_lib | 2 |
| `noctusai_lib.llm.cache.try_get` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.cache.try_set` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.chat.build_cached_messages` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.client.configure_llm` | lib:noctusai_seed | 2 |
| `noctusai_lib.llm.client.get_provider` | lib:noctusai_lib | 4 |
| `noctusai_lib.llm.client.resolve_api_key` | lib:noctusai_lib | 4 |
| `noctusai_lib.llm.client.shutdown_llm` | lib:noctusai_seed | 2 |
| `noctusai_lib.llm.exceptions.LLMAPIError` | lib:noctusai_lib | 3 |
| `noctusai_lib.llm.exceptions.ProviderNotImplemented` | lib:noctusai_lib | 4 |
| `noctusai_lib.llm.models.ModelEntry` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.models.is_stub_model` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.providers.base.LLMProvider` | lib:noctusai_lib | 4 |
| `noctusai_lib.llm.providers.fake_provider.FakeProvider` | lib:noctusai_lib | 2 |
| `noctusai_lib.llm.registry.get_provider_class` | lib:noctusai_lib | 2 |
| `noctusai_lib.llm.registry.list_providers` | lib:noctusai_lib | 1 |
| `noctusai_lib.llm.registry.register` | lib:noctusai_lib | 4 |
| `noctusai_lib.middleware.CorrelationIdMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.middleware.RequestLoggingMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.middleware.get_correlation_id` | lib:noctusai_lib | 1 |
| `noctusai_lib.notifications.map_notification_to_pt` | lib:noctusai_seed | 1 |
| `noctusai_lib.rate_limit.create_limiter` | lib:noctusai_seed | 1 |
| `noctusai_lib.responses.ok_response` | daily-life | 5 |
| `noctusai_lib.roles.DEV_ROLES` | lib:noctusai_lib | 1 |
| `noctusai_lib.roles.ORG_ROLE_LABELS` | lib:noctusai_seed | 1 |
| `noctusai_seed.llm_defaults.DEFAULT_LLM_CONFIG` | lib:noctusai_seed | 1 |
| `noctusai_seed.llm_defaults.default_llm_config` | lib:noctusai_seed | 2 |
| `noctusai_seed.llm_router.create_llm_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.routers.create_standard_routers` | lib:noctusai_seed | 1 |

## Duplication candidates

Public top-level functions/classes with the **same name** in 2+ products,
and **not** already exported by the shared lib. Strong signal that they
belong in `noctusai_lib`. Name-based matching has false positives —
review occurrences before absorbing.

### `AtivosService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/ativos_service.py:15`
- `personal-finance` — `products/personal-finance/backend/app/services/ativos_service.py:10`

### `atualizar_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:265`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:58`

### `atualizar_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:135`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:228`

### `atualizar_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:137`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:376`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:60`

### `criar_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:214`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:47`

### `criar_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:90`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:150`

### `criar_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:88`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:357`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:49`

### `dashboard_resumo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/bi.py:132`
- `personal-finance` — `products/personal-finance/backend/app/routers/dashboard.py:22`

### `excluir_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:312`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:72`

### `excluir_meta` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:391`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:74`

### `fluxo_caixa` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/financeiro.py:170`
- `personal-finance` — `products/personal-finance/backend/app/routers/relatorios.py:38`

### `generate_token` (def)

- `mailing` — `products/mailing/backend/app/routers/unsubscribe.py:15`
- `therapy-platform` — `products/therapy-platform/backend/app/services/livekit_service.py:72`

### `get_message_history` (def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:279`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:191`

### `list_all` (def)

- `adconnect` — `products/adconnect/backend/app/routers/distributors.py:30`
- `mailing` — `products/mailing/backend/app/routers/lists.py:21`

### `list_invoices` (def)

- `adconnect` — `products/adconnect/backend/app/routers/financial.py:22`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/invoices.py:47`
- `therapy-platform` — `products/therapy-platform/backend/app/services/invoice_service.py:61`

### `list_reports` (def)

- `adconnect` — `products/adconnect/backend/app/routers/sellout.py:21`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/support.py:104`

### `listar_ativos` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:138`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:15`

### `listar_checkins` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:199`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/campo.py:132`

### `listar_eventos` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:60`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:96`

### `listar_metas` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:61`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:323`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:15`

### `login` (def)

- `adconnect` — `products/adconnect/backend/app/routers/auth.py:66`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/auth.py:82`
- `therapy-platform` — `products/therapy-platform/backend/app/services/auth_service.py:234`

### `obter_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:203`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:36`

### `obter_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:121`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:215`

### `obter_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:117`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:27`

### `registrar_checkin` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:181`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/campo.py:113`

### `send_message` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:164`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/messaging.py:161`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/whatsapp_therapy.py:27`
- `therapy-platform` — `products/therapy-platform/backend/app/services/messaging_service.py:179`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:161`

### `send_via_waha` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:319`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:44`

