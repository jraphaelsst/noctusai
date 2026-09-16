# NoctusAI Shared Library Catalog

> **Auto-generated** by `python mcp/noctusai/cli.py --catalog`. Do not edit by hand.
> This artifact replaces the drift-prone handwritten catalog. It answers:
> *what's in the lib, who uses it, and what's duplicated across products that probably shouldn't be.*

- **Lib roots scanned**: `noctusai_lib` (seed/lib/backend/noctusai_lib), `noctusai_seed` (seed/framework/backend/noctusai_seed)
- **Products scanned**: `academia-de-reciclagem`, `adconnect`, `agents`, `core`, `daily-life`, `dev-team`, `erp-imobiliario`, `igig`, `knowledge-extractor`, `orbity`, `p-studio`, `personal-finance`, `seed`, `social-wiring`, `therapy-platform`
- **Totals**: 1496 symbols · 403 orphans · 767 single-consumer · 88 duplicate candidates

## Symbols

### `noctusai_lib`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SSOSessionCache` | class | `` | Thread-safe in-memory SSO session cache with TTL + per-key locking. | — | 0 |
| `SSO_AUDIENCE` | const | `` |  | — | 0 |
| `SSO_ISSUER` | const | `` |  | — | 0 |
| `create_sso_token_factory` | def | `(settings) -> Callable[..., str]` | Return a `create_sso_token` callable bound to `settings`. | — | 0 |
| `first_or_none` | def | `(result) -> Optional[dict]` | Extract first record from a Supabase list response, or None. | — | 0 |
| `get_calendar_adapter` | def | `(resolver: CalendarCredentialResolver | None=None, *, tenant…` | Return a calendar adapter wired for the supplied resolver, or | — | 0 |
| `get_docx_render_adapter` | def | `(*, real: bool=True) -> DocxRenderAdapter` | Return a DOCX-template render adapter. | — | 0 |
| `get_fx_rate_adapter` | def | `(live: bool=False, **kwargs: object) -> FxRateAdapter` | Return `BcbPtaxAdapter` when `live=True`; `FakeFxRateAdapter` otherwise. | — | 0 |
| `get_image_edit_adapter` | def | `(key_provider: KeyProvider | None=None, *, backend: str='ope…` | Return an image-edit adapter wired for the supplied key provider, | — | 0 |
| `get_image_gen_adapter` | def | `(key_provider: KeyProvider | None=None, *, backend: str='gem…` | Return an image-gen adapter wired for the supplied key provider, | — | 0 |
| `get_imaging_adapter` | def | `(*, real: bool=True) -> ImagingAdapter` | Return an imaging adapter. | — | 0 |
| `get_mailchimp_client` | def | `(api_key: str | None=None, *, server_prefix: str | None=None…` | Return a real ``HttpxMailchimpClient`` when ``api_key`` is set; | — | 0 |
| `get_media_resolver` | def | `(*, real: bool=False, document_prompt: str | None=None, scen…` | Return a media resolver. | — | 0 |
| `get_meta_adapter` | def | `(*, system_user_token: str | None=None, resolver: MetaCreden…` | Return a Meta adapter wired per the auth-resolution priority. | — | 0 |
| `get_meta_cloud_client` | def | `(*, phone_number_id: str | None=None, api_key: str | None=No…` | Return a real `MetaCloudClient` when `api_key` is set; `FakeMetaCloudClient` oth… | — | 0 |
| `get_n8n_client` | def | `(base_url: str | None=None, api_key: str | None=None, *, tim…` | Return a real ``HttpxN8nClient`` when both ``base_url`` and | — | 0 |
| `get_record_store` | def | `(*, supabase_client: Any | None=None, sqlite_path: str | Pat…` | Return the store the environment calls for. | — | 0 |
| `get_routing_adapter` | def | `(api_key: str | None=None) -> RoutingAdapter` | Routes API → Static fallback. Returns `GoogleMapsRoutingAdapter` | — | 0 |
| `get_sso_context` | def | `(user) -> dict` | Extract all SSO-synced context from user_metadata. | — | 0 |
| `get_svg_render_adapter` | def | `(*, real: bool=True, font_files: list[str] | None=None, uplo…` | Return an SVG→PNG render adapter. | — | 0 |
| `get_whatsapp_client` | def | `(*, base_url: str | None=None, api_key: str | None=None, ses…` | Return a real WAHA client when `base_url` is set; `FakeWahaClient` otherwise. | — | 0 |
| `make_credential_store` | def | `(*, client=None, fernet_key: Optional[bytes]=None, table: st…` | Real when ``client`` AND ``fernet_key`` are set; else Fake. | — | 0 |
| `make_get_current_user` | def | `(get_supabase_client_fn)` | Factory that creates a product-specific get_current_user dependency. | — | 0 |
| `make_get_current_user_org` | def | `(get_current_user_fn, get_org_id_fn, *, get_admin_client_fn:…` | Factory that creates a product-specific ``get_current_user_org`` dependency. | — | 0 |
| `make_require_role` | def | `(get_current_user_fn, get_user_role_fn)` | Factory that creates a product-specific ``require_role`` dependency factory. | — | 0 |
| `make_resolve_platform_role` | def | `(get_admin_client_fn: Callable[[], Any]) -> Callable[[Any], …` | Factory: returns a sync ``resolve_platform_role(user) -> Optional[str]``. | — | 0 |
| `require_credential_or_422` | def | `(key: str, org_id: Optional[str]=None, *, detail: Optional[s…` | Resolve a credential through `noctusai_lib.config.credentials.resolve_credential… | — | 0 |
| `resolve_sso_role` | def | `(user) -> Optional[str]` | Check SSO metadata for product-level admin access. | — | 0 |
| `resvg_available` | def | `() -> bool` | ``True`` when the ``resvg-py`` rasterizer can be imported. | — | 0 |
| `verify_sso_token_factory` | def | `(settings) -> Callable[[str], dict]` | Return a `verify_sso_token(token) -> payload` callable bound to `settings`. | — | 0 |

### `noctusai_lib.api.app_factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_app` | def | `(app: FastAPI, settings, *, limiter=None, cors_allow_headers…` | Apply shared configuration to a FastAPI app instance. | lib:noctusai_seed | 1 |

### `noctusai_lib.api.auth.platform`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `require_org_admin` | def | `(*, get_auth_context: Callable[..., Awaitable[AuthContext]],…` | Build a FastAPI dependency enforcing org-admin access, scoped to | — | 0 |
| `require_permission` | def | `(name: str, *, get_auth_context: Callable[..., Awaitable[Aut…` | Build a FastAPI dependency enforcing a named, product-agnostic | — | 0 |
| `require_platform_admin` | def | `(*, get_auth_context: Callable[..., Awaitable[AuthContext]],…` | Build a FastAPI dependency enforcing strict platform-admin access. | — | 0 |
| `resolve_platform_admin_role` | def | `(core_client: Any, user_id: Any) -> str | None` | Trusted-DB read of ONLY `public.noctus_users.role`. | — | 0 |

### `noctusai_lib.api.auth.session.api_tokens`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ApiTokenResolver` | class | `` | Resolves a raw ``pk_*`` bearer secret to an ``AuthContext``. | lib:noctusai_lib, lib:noctusai_seed | 4 |
| `FakeApiTokenResolver` | class | `` | Deterministic in-memory ``ApiTokenResolver``. | agents, erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed, social-wiring | 6 |
| `SupabaseApiTokenResolver` | class | `` | Concrete :class:`ApiTokenResolver` over a Supabase admin client. | academia-de-reciclagem, agents, erp-imobiliario, lib:noctusai_lib, social-wiring | 6 |
| `hash_token` | def | `(secret: str) -> str` | Return the lowercase hex SHA-256 digest of ``secret``. | erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed, social-wiring | 7 |

### `noctusai_lib.api.auth.session.audit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ApiTokenAuditWriter` | class | `` | Records one resolved product-token call. Never raises — a | lib:noctusai_lib | 2 |
| `FakeApiTokenAuditWriter` | class | `` | In-memory recorder — tests assert on ``.records``. | lib:noctusai_lib | 1 |
| `SupabaseApiTokenAuditWriter` | class | `` | Best-effort ``INSERT`` into ``<schema>.api_token_audit``. | lib:noctusai_lib | 1 |
| `make_api_token_audit_writer` | def | `(admin_client: Optional[Any]=None, *, schema: Optional[str]=…` | Return the appropriate writer for the environment. | academia-de-reciclagem, lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.api.auth.session.audit_middleware`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ApiTokenAuditMiddleware` | class | `` | Fires `audit_writer.record(...)` for every resolved | academia-de-reciclagem, lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.api.auth.session.dep`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_get_auth_context` | def | `(*, session_store: SessionStore, api_token_resolver: ApiToke…` | Build a FastAPI dependency returning an ``AuthContext``. | academia-de-reciclagem, agents, erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed, social-wiring | 7 |

### `noctusai_lib.api.auth.session.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_session_store` | def | `(redis_url: Optional[str]=None, *, client: Any=None, encrypt…` | Return the appropriate ``SessionStore`` for the environment. | lib:noctusai_lib, lib:noctusai_seed | 2 |

### `noctusai_lib.api.auth.session.redis_store`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RedisSessionStore` | class | `` | ``redis.asyncio``-backed ``SessionStore`` (satisfies the Protocol). | lib:noctusai_lib | 2 |

### `noctusai_lib.api.auth.session.scopes`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `require_scopes` | def | `(*scopes: str, user_roles: frozenset[str]=frozenset(), get_a…` | Build a FastAPI dependency enforcing scopes (product) / role (user). | academia-de-reciclagem, agents, lib:noctusai_lib, social-wiring | 4 |
| `resolve_org_role` | def | `(core_client: Any, user_id: Any) -> str | None` | Trusted-DB read of ``public.noctus_users.org_role`` for ``user_id``. | academia-de-reciclagem, agents, lib:noctusai_lib, lib:noctusai_seed | 6 |

### `noctusai_lib.api.auth.session.session_revoke`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeSessionRevoker` | class | `` | Deterministic in-memory ``SessionRevoker`` for dev + consumer tests. | lib:noctusai_lib | 1 |
| `SessionRevoker` | class | `` | Revoke a Supabase session upstream at logout (SEC-4). | lib:noctusai_lib, lib:noctusai_seed | 2 |
| `SupabaseSessionRevoker` | class | `` | Real ``SessionRevoker`` — revokes on a throwaway anon client (SEC-1). | lib:noctusai_lib | 1 |
| `make_default_revoke_fn` | def | `(url: str, anon_key: str) -> RevokeFn` | Build the SEC-1/SEC-4 revoke seam: sign out on a THROWAWAY anon client. | lib:noctusai_lib | 1 |
| `make_session_revoker` | def | `(*, supabase_url: Optional[str]=None, supabase_anon_key: Opt…` | Return the appropriate ``SessionRevoker`` for the environment. | lib:noctusai_lib, lib:noctusai_seed | 2 |

### `noctusai_lib.api.auth.session.store`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeSessionStore` | class | `` | Deterministic in-memory ``SessionStore``. | lib:noctusai_lib | 3 |
| `SessionStore` | class | `` | Server-side session-record persistence. | lib:noctusai_lib, lib:noctusai_seed | 6 |

### `noctusai_lib.api.auth.session.token_exchange`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeTokenExchanger` | class | `` | Deterministic in-memory ``TokenExchanger`` for dev + consumer tests. | erp-imobiliario, lib:noctusai_lib | 2 |
| `RefreshResult` | class | `` | The outcome of one upstream refresh call. | lib:noctusai_lib | 1 |
| `SupabaseTokenExchanger` | class | `` | Real ``TokenExchanger`` — cache-first, lock-serialized, SEC-1/2 safe. | lib:noctusai_lib | 1 |
| `TokenExchangeError` | class | `` | Raised when a valid access token could not be obtained despite the | lib:noctusai_lib | 1 |
| `TokenExchanger` | class | `` | Turn a session id into a valid Supabase access token. | lib:noctusai_lib | 1 |
| `make_default_refresh_fn` | def | `(url: str, anon_key: str) -> RefreshFn` | Build the SEC-1 refresh seam: refresh on a THROWAWAY anon client. | lib:noctusai_lib | 1 |
| `make_token_exchanger` | def | `(store: SessionStore, *, supabase_url: Optional[str]=None, s…` | Return the appropriate ``TokenExchanger`` for the environment. | erp-imobiliario, lib:noctusai_lib | 2 |

### `noctusai_lib.api.auth.session.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthContext` | class | `` | Canonical caller identity, independent of the credential shape. | academia-de-reciclagem, agents, erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed, social-wiring | 40 |
| `ExpiredSessionError` | class | `` | Raised by ``SessionStore.lookup`` (or callers polling the | lib:noctusai_lib | 2 |
| `InvalidCredentialsError` | class | `` | Raised by stores/resolvers when a credential is malformed or | lib:noctusai_lib | 3 |
| `RevokedApiTokenError` | class | `` | Raised by ``ApiTokenResolver.resolve`` when a token's row is | lib:noctusai_lib | 2 |
| `SessionTokens` | class | `` | Server-side-only token bundle for a user session. | lib:noctusai_lib | 3 |

### `noctusai_lib.api.crud_safety`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `delete_or_404` | def | `(db, table: str, *predicates: tuple[str, Any], message: str=…` | HTTPException-flavored convenience wrapper around `delete_with_existence_check`. | core, daily-life, erp-imobiliario, personal-finance, social-wiring | 32 |
| `delete_with_existence_check` | def | `(db, table: str, *predicates: tuple[str, Any], not_found_exc…` | Pre-check existence via SELECT; raise if absent; DELETE on success. | erp-imobiliario | 4 |

### `noctusai_lib.api.middleware`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CorrelationIdMiddleware` | class | `` | Middleware that generates or extracts correlation IDs for request tracking. | lib:noctusai_lib | 1 |
| `DEFAULT_MAX_BODY_BYTES` | const | `` |  | lib:noctusai_lib, lib:noctusai_seed | 2 |
| `KEEP_DEFAULT_MAX_BODY` | const | `` |  | lib:noctusai_seed | 1 |
| `MaxBodySizeMiddleware` | class | `` | Reject requests whose body exceeds a per-route cap with 413 before | adconnect, erp-imobiliario, igig, lib:noctusai_lib, social-wiring, therapy-platform | 6 |
| `RequestLoggingMiddleware` | class | `` | Middleware that logs request/response details with timing. | lib:noctusai_lib | 1 |
| `path_is_covered_by_overrides` | def | `(pattern_key: str, path_overrides: Optional[Mapping[str, obj…` | True if `pattern_key` (already in this module's wildcard-pattern | lib:noctusai_seed | 1 |
| `to_wildcard_pattern` | def | `(route_path: str) -> str` | Convert a FastAPI route-path template (`"/api/clientes/{cliente_id}/documentos"`… | lib:noctusai_seed | 1 |

### `noctusai_lib.api.rate_limit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_limiter` | def | `(redis_url: Optional[str]=None, default_limits: Optional[lis…` | Create a slowapi Limiter with optional Redis backing. | lib:noctusai_seed | 1 |

### `noctusai_lib.api.scheduler`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SCHEDULERS_ENABLED_ENV` | const | `` |  | — | 0 |
| `register` | def | `(name: str, fn: Callable[..., Awaitable[None]], *, hours: Op…` | Register an async job on the module-level scheduler. | — | 0 |
| `reset_for_testing` | def | `() -> None` | Clear all registered jobs + replace the singleton — TEST USE ONLY. | — | 0 |
| `schedulers_enabled` | def | `() -> bool` | Is this process authorised to run scheduled jobs? | — | 0 |
| `start_scheduler` | def | `() -> None` | Start the module-level scheduler. Idempotent — re-calling on a | — | 0 |
| `stop_scheduler` | def | `() -> None` | Shut down the scheduler gracefully. | — | 0 |

### `noctusai_lib.api.schemas`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StrictHttpModel` | class | `` | Pydantic base for HTTP-boundary schemas. Rejects unknown keys (422). | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, lib:noctusai_lib, lib:noctusai_seed, orbity, personal-finance, social-wiring, therapy-platform | 171 |

### `noctusai_lib.components.validation_signal`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `compute_signal_inputs` | def | `(component_path: Path, graph_neighbors_result: dict, repo_ro…` | Compute the raw signal inputs for :func:`derive_validation_status`. | — | 0 |
| `derive_validation_status` | def | `(component_name: str, consumers_count: int, has_test: bool, …` | Derive the validation status of a component from its observable signals. | — | 0 |

### `noctusai_lib.config.cors_registry`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `NATIVE_DEV_ENV` | const | `` |  | — | 0 |
| `ProductEntry` | class | `` | Parsed row from ``start.sh PRODUCTS``. | — | 0 |
| `derive_cors_origins` | def | `(start_sh: Optional[Path]=None, include_localhost_alts: bool…` | Return the canonical CORS origins list derivable from ``start.sh``. | lib:noctusai_lib | 1 |
| `parse_products_registry` | def | `(start_sh: Optional[Path]=None) -> List[ProductEntry]` | Parse the ``PRODUCTS=(...)`` array out of ``start.sh``. | core, lib:noctusai_lib | 2 |

### `noctusai_lib.config.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_credentials` | def | `(*, supabase_url: str, supabase_anon_key: str, supabase_serv…` | Configure credential resolution. Call once at product startup. | lib:noctusai_seed | 1 |
| `register_credential_override` | def | `(fn: Optional[Callable[[str, Optional[str]], Optional[str]]]…` | Install a product-local tier consulted BEFORE `org_settings`. | social-wiring | 1 |
| `resolve_credential` | def | `(key: str, org_id: Optional[str]=None) -> Optional[str]` | Resolve a credential value through the tier chain. | erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed, personal-finance, social-wiring | 15 |

### `noctusai_lib.config.csv_settings`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `parse_csv_setting` | def | `(raw: str, *, lower: bool=False) -> list[str]` | Split a comma-separated settings string into a clean list. | academia-de-reciclagem, agents | 2 |
| `reject_json_array` | def | `(value: str, env_name: str) -> str` | Fail loud on a `["a","b"]`-shaped raw value for a CSV-string setting. | academia-de-reciclagem, agents | 2 |

### `noctusai_lib.config.deploy_config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MissingProdConfigError` | class | `` | Required-in-prod config is absent in a deploy context. | igig | 1 |
| `baseline_required_prod_env` | def | `() -> list[str]` | The fleet-wide baseline required-in-prod env keys as a fresh list. | lib:noctusai_seed | 1 |
| `is_deploy_context` | def | `() -> bool` | Return ``True`` iff the process is running in a deploy context. | lib:noctusai_lib | 1 |
| `require_prod_config` | def | `(keys: list[str]) -> None` | Assert that every key in ``keys`` is present in a deploy context. | agents, lib:noctusai_seed | 2 |
| `resolve_config` | def | `(key: str, *, canonical_default: str | None=None, required_i…` | Resolve a single config value with deploy-aware required semantics. | — | 0 |

### `noctusai_lib.config.product_urls`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `resolve_product_url` | def | `(slug: str, *, db_url_base: str | None=None) -> str` | Return the deploy-aware URL for a product, given its slug. | agents, core, lib:noctusai_lib, p-studio, social-wiring | 8 |

### `noctusai_lib.config.settings`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BaseAppSettings` | class | `` | Shared settings base for all NoctusAI backends. | — | 0 |

### `noctusai_lib.domain.action_log`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `log_action` | def | `(db, table_name: str, user_id_column: str, user_id: str, tip…` | Insert a row into a product's action log table. | erp-imobiliario, therapy-platform | 2 |

### `noctusai_lib.domain.ai.consent`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AIConsentRequired` | class | `` | The calling user has not granted consent for this AI feature. | — | 0 |
| `ConsentFeature` | class | `` | One entry in the platform-wide consent catalog. | — | 0 |
| `MandatoryFeatureCannotBeToggled` | class | `` | The user attempted to toggle a feature whose `toggleable=False`. | — | 0 |
| `configure_consent_module` | def | `(*, get_current_user: Optional[Callable[..., Any]], admin_cl…` | Wire the FastAPI deps the consent guard uses to resolve user + db. | lib:noctusai_seed | 1 |
| `consent_required` | def | `(feature_key: str) -> Callable[..., Awaitable[None]]` | FastAPI dependency factory for router-level consent gating. | — | 0 |
| `fetch_user_decisions` | async def | `(db: Any, user_id: str) -> dict[str, dict[str, Any]]` | Pull every stored decision for a user. Keyed by `feature_key` for | — | 0 |
| `get_catalog` | def | `() -> list[ConsentFeature]` | Return all registered features sorted by `(product, key)` for stable UI ordering… | — | 0 |
| `get_feature` | def | `(key: str) -> Optional[ConsentFeature]` |  | core, erp-imobiliario | 2 |
| `is_consent_module_configured` | def | `() -> bool` |  | — | 0 |
| `is_granted` | async def | `(db: Any, user_id: str, feature_key: str) -> bool` | Resolve the effective grant state for `(user_id, feature_key)`. | — | 0 |
| `list_user_consent_view` | async def | `(db: Any, user_id: str) -> list[dict[str, Any]]` | Return one row per catalog entry, merged with the user's stored decisions. | core | 1 |
| `pending_count` | def | `(view: list[dict[str, Any]]) -> int` | Number of catalog entries the user hasn't decided on yet (i.e. | core | 1 |
| `register_feature` | def | `(key: str, *, title: str, rationale: str, default_granted: b…` | Register a feature in the platform catalog. Called at product startup. | core | 1 |
| `require` | async def | `(db: Any, user_id: str, feature_key: str) -> None` | Raise `AIConsentRequired` if the user hasn't granted consent. | — | 0 |
| `reset_catalog_for_test` | def | `() -> None` | Test-only — clears the catalog so isolated tests can register fresh sets. | core | 1 |
| `reset_consent_module_for_test` | def | `() -> None` | Test-only — clear wired factories so isolated tests can rewire. | — | 0 |
| `upsert_decision` | async def | `(db: Any, user_id: str, feature_key: str, *, granted: bool, …` | Upsert the decision row. Returns the persisted row. | core | 1 |

### `noctusai_lib.domain.ai.outputs`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AIOutput` | class | `` | One row of `<schema>.ai_outputs`. | — | 0 |
| `fetch_outputs_for` | def | `(db, schema: str, ref_type: str, ref_id: str, *, limit: int=…` | Fetch every `ai_outputs` row matching `(ref_type, ref_id)`, newest first. | — | 0 |
| `persist_output` | def | `(db, schema: str, output: AIOutput) -> dict[str, Any]` | Insert an `AIOutput` row and return the persisted dict (with id). | — | 0 |
| `safe_persist_indicator` | def | `(db, *, schema: Optional[str], ref_type: str, ref_id: str, o…` | Build an `AIOutput` from an AI-service dict + persist it; on failure, | — | 0 |

### `noctusai_lib.domain.ai.tool_audit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuditRecord` | class | `` | In-memory representation of one tool-call event. | core, daily-life, erp-imobiliario, personal-finance, social-wiring, therapy-platform | 18 |
| `apply_feature_redaction` | def | `(record: AuditRecord, *, redact_arguments: Optional[Callable…` | Return a new `AuditRecord` with arguments/result run through | social-wiring | 3 |
| `make_audit_writer` | def | `(db: 'Session', table_class: type) -> AuditWriter` | Build an audit writer closure bound to a session + ORM class. | core, daily-life, erp-imobiliario, personal-finance, social-wiring, therapy-platform | 12 |
| `now_utc` | def | `() -> datetime` | Convenience: timezone-aware UTC `datetime.now()`. Use as default for | core, daily-life, erp-imobiliario, personal-finance, social-wiring, therapy-platform | 15 |

### `noctusai_lib.domain.chatbot.buffer`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ConversationBufferService` | class | `` | Redis-backed conversation memory + debounce + idle queue. | lib:noctusai_lib, social-wiring | 2 |
| `QueuedConversationMessage` | class | `` | One message in a conversation. `direction` is `"inbound"` or | lib:noctusai_lib, social-wiring | 2 |
| `RedisBufferClient` | class | `` | The Redis surface the buffer uses. `redis.Redis` from `redis-py` | lib:noctusai_lib | 1 |
| `make_in_memory_buffer_client` | def | `() -> RedisBufferClient` | Return a Protocol-compatible in-memory buffer client (no network). | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.content_stats`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SchemaHint` | class | `` | A per-consumer, domain-specific code-pattern counter. | lib:noctusai_lib | 1 |
| `compute_content_stats` | def | `(text: str, *, rendered_as: str | None=None, schema_hints: l…` | Return deterministic aggregates the LLM can quote without counting. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.delivery`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `send_reply_parts` | async def | `(text: str, send_one: Callable[[str], Awaitable[Any]], *, sp…` | Send `text` via `send_one` as one message per part. Returns count sent. | lib:noctusai_lib, social-wiring | 2 |
| `send_reply_parts_sync` | def | `(text: str, send_one: Callable[[str], Any], *, split: bool=T…` | Sync sibling of `send_reply_parts` for sync worker processors. | lib:noctusai_lib | 1 |
| `split_reply` | def | `(text: str, *, enabled: bool=True) -> list[str]` | Return `text` split into one entry per paragraph (blank-line boundaries). | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.domain.chatbot.llm_dispatcher`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_FALLBACK_REPLY` | const | `` |  | — | 0 |
| `DEFAULT_MAX_TOOL_ITERATIONS` | const | `` |  | lib:noctusai_lib | 1 |
| `LLMDispatcher` | class | `` | Stateless OpenAI tool-loop dispatcher. Safe to share across | lib:noctusai_lib | 2 |
| `ToolCall` | class | `` | Normalized OpenAI tool-call from the model. | lib:noctusai_lib, social-wiring | 7 |
| `ToolResult` | class | `` | Tool-handler return value. `content` is sent back to the model | lib:noctusai_lib, social-wiring | 6 |

### `noctusai_lib.domain.chatbot.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `format_conversation_for_transcript` | def | `(memory: list[dict[str, Any]], *, assistant_label: str='ASSI…` | Render the conversation as a labeled transcript (one line per message). | lib:noctusai_lib | 2 |
| `memory_to_chat_messages` | def | `(memory: list[dict[str, Any]]) -> list[dict[str, str]]` | Convert buffer memory (list of dicts with `text` + `direction`) to | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.message_store`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DuplicateMessage` | class | `` | Raised when a record with the same ``provider_message_id`` already | lib:noctusai_lib | 1 |
| `FakeMessageStore` | class | `` | In-memory :class:`MessageStore` keyed on ``provider_message_id`` | lib:noctusai_lib | 1 |
| `MessageStore` | class | `` | The durable conversation-persistence surface. | lib:noctusai_lib | 1 |
| `StoredMessage` | class | `` | The persisted row, normalized. ``id`` is the row UUID. | lib:noctusai_lib | 1 |
| `SupabaseMessageStore` | class | `` | Real :class:`MessageStore` — persists to a Supabase/Postgres | lib:noctusai_lib | 1 |
| `make_message_store` | def | `(*, admin_supabase: Any | None=None, org_id: UUID | None=Non…` | Factory — returns a :class:`FakeMessageStore` when ``use_fake`` is | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.openai_orchestrator`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_FALLBACK_REPLY` | const | `` |  | — | 0 |
| `FakeToolOrchestrator` | class | `` | Scripted, network-free :class:`ToolOrchestrator` for tests + dev. | lib:noctusai_lib | 1 |
| `MAX_MEMORY_ITEMS` | const | `` |  | — | 0 |
| `MEMORY_PREFIX` | const | `` |  | — | 0 |
| `MEMORY_TTL_SECONDS` | const | `` |  | — | 0 |
| `OpenAIToolOrchestrator` | class | `` | Real orchestrator — composes :class:`LLMDispatcher` over an | lib:noctusai_lib | 1 |
| `OrchestratorTool` | class | `` | One tool the consumer exposes to the model. ``handler`` is an | lib:noctusai_lib | 1 |
| `ToolOrchestrator` | class | `` | The chatbot-orchestration surface. Real + Fake both satisfy it. | lib:noctusai_lib | 1 |
| `append_memory` | def | `(redis_client: Any, *, session_id: str, direction: str, text…` | Append an inbound/outbound text entry to a conversation's memory. | lib:noctusai_lib | 1 |
| `make_tool_orchestrator` | def | `(*, redis_client: Any | None=None, client: Any | None=None, …` | Factory — :class:`FakeToolOrchestrator` when ``use_fake`` (or no | lib:noctusai_lib | 1 |
| `memory_key_for` | def | `(session_id: str) -> str` | Canonical Redis key for a conversation's memory list. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.prompt_fragments`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `with_url_immutability` | def | `(system_prompt: str) -> str` | Return `system_prompt` with the URL-immutability fragment appended. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.response_registry`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeResponseRegistry` | class | `` | In-memory :class:`ResponseRegistry` — the default for tests + dev | lib:noctusai_lib | 1 |
| `ResponseRegistry` | class | `` | The connector-sample sink surface. A vendor module (e.g. | lib:noctusai_lib | 1 |
| `json_shape` | def | `(value: Any) -> Any` | Deterministic structural skeleton of a JSON value. | lib:noctusai_lib | 1 |
| `make_response_registry` | def | `(*, sink: ResponseRegistry | None=None) -> ResponseRegistry` | Factory — returns the provided vendor ``sink`` if given, else a | lib:noctusai_lib | 1 |
| `sample_key` | def | `(*, source: str, direction: str, fingerprint: str, event_typ…` | Composite dedup key — one stored sample per | lib:noctusai_lib | 1 |
| `shape_fingerprint` | def | `(shape: Any) -> str` | Stable 16-hex fingerprint of a :func:`json_shape` result. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.summary`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `summarize_conversation` | def | `(client: Any, model: str, memory: list[dict[str, Any]], outp…` | Run OpenAI structured-output (`client.responses.parse`) over the | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.chatbot.worker`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BufferReader` | class | `` | The buffer surface the worker consumes. `ConversationBufferService` | lib:noctusai_lib | 1 |
| `ConversationWorker` | class | `` | Poll loop + due/idle dispatch. Stop with `worker.stop()` (e.g. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.domain.digest.base`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BaseDigestService` | class | `` | Template-method orchestrator for narrative-using digest services. | — | 0 |

### `noctusai_lib.domain.digest.narrative`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `narrative` | async def | `(*, system: str, user_prompt: str, model: str, cache: bool, …` | Generate a PT digest narrative; return `fallback` on LLM failure. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.digest.orchestrate`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_and_send` | async def | `(digest: Digest, *, recipient: str, org_id: Optional[str], l…` | Send a built `Digest` and return the standardized 5-key result. | — | 0 |

### `noctusai_lib.domain.digest.render`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `email_template_dir` | def | `(service_file: str) -> Path` | Resolve the per-product `app/email_templates/` directory. | — | 0 |
| `render_digest_pair` | def | `(template_basename: str, *, narrative: str, context: dict[st…` | Render `(html, text)` from `<basename>.html.j2` + `<basename>.txt.j2`. | — | 0 |
| `render_with_narrative` | def | `(*, html_template: str, text_template: str, narrative: str, …` | Render `(html, text)` digest bodies with narrative scaffolding. | — | 0 |

### `noctusai_lib.domain.digest.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DigestResult` | class | `` | Output envelope from `BaseDigestService.run(...)`. | lib:noctusai_lib | 1 |
| `DigestWindow` | class | `` | Input envelope for `BaseDigestService.run(...)`. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.fleet_control`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ActResult` | class | `` | Result of a start/stop/restart action. | — | 0 |
| `CONTAINER_PREFIX` | const | `` |  | — | 0 |
| `ContainerController` | class | `` | Control-plane Protocol — read status + act on product containers. | core | 1 |
| `ContainerStatus` | class | `` | Live status of a single product container. | — | 0 |
| `DockerComposeController` | class | `` | Real controller — operates the docker host the process can reach | — | 0 |
| `FakeContainerController` | class | `` | In-memory controller — no docker. Seeds a running/stopped state per | core | 1 |
| `FleetControlError` | class | `` | Raised when a (verb, slug) pair fails the hard allowlist. | core | 1 |
| `get_fleet_controller` | def | `(*, use_real: Optional[bool]=None, runner: Optional[Callable…` | Return the controller for this host. | core | 1 |
| `validate_action` | def | `(slug: str, verb: str, registered_slugs: Optional[set[str]]=…` | Validate (slug, verb) against the hard allowlist and return the safe | — | 0 |

### `noctusai_lib.domain.invitations`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `accept_invitation` | def | `(db, table: str, invitation_id: str, *, accepted_by: Optiona…` | Mark an invitation as accepted. | core, lib:noctusai_seed, therapy-platform | 3 |
| `cancel_invitation` | def | `(db, table: str, invitation_id: str, org_id: str) -> None` | Cancel a pending invitation. Verifies it belongs to the org and is pending. | core, lib:noctusai_seed | 2 |
| `create_invitation` | def | `(db, table: str, org_id: str, email: str, role: str, invited…` | Create an invitation record with a unique token. | core, lib:noctusai_seed | 2 |
| `expire_old_invitations` | def | `(db, table: str) -> int` | Expire all invitations past their expires_at. Returns count expired. | — | 0 |
| `generate_invite_token` | def | `() -> str` | Generate a cryptographically secure invitation token. | therapy-platform | 1 |
| `list_pending_invitations` | def | `(db, table: str, org_id: str) -> list` | List all pending invitations for an organization. | core, lib:noctusai_seed | 2 |
| `validate_invitation` | def | `(db, table: str, token: str) -> dict` | Validate an invitation token. Returns the invitation record. | core, lib:noctusai_seed, therapy-platform | 3 |

### `noctusai_lib.domain.jobs.entity`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Job` | class | `` | Background job — payload + lifecycle state. | lib:noctusai_lib | 5 |
| `JobStatus` | class | `` | Lifecycle states for a Job. | lib:noctusai_lib | 2 |
| `next_status` | def | `(job: Job, outcome: JobOutcome) -> JobStatus` | Compute the next status for a RUNNING job given the worker outcome. | lib:noctusai_lib | 1 |
| `should_retry` | def | `(job: Job) -> bool` | True iff the job has retries remaining. | lib:noctusai_lib | 1 |
| `with_status_transition` | def | `(job: Job, new_status: JobStatus, *, error: str | None=None,…` | Return a new Job with `status = new_status` and `updated_at` bumped. | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.jobs.repo`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DeadLetterError` | class | `` | Raised by handlers that want to skip retries and land directly | lib:noctusai_lib | 3 |
| `FakeJobRepository` | class | `` | In-memory `JobRepository` for dev + tests. | lib:noctusai_lib | 1 |
| `JobRepository` | class | `` | Async repository surface every Job consumer depends on. | lib:noctusai_lib | 3 |
| `LeaseLostError` | class | `` | Raised by `extend_lease` when the caller no longer holds the | lib:noctusai_lib | 2 |
| `RealSupabaseJobRepository` | class | `` | Supabase-client backed `JobRepository`. | lib:noctusai_lib | 1 |
| `make_job_repository` | def | `(*, use_fake: bool=False, supabase_client: Any | None=None, …` | Construct a `JobRepository` for a consumer. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.jobs.retry_policy`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RetryPolicy` | class | `` | Exponential-backoff retry configuration. | lib:noctusai_lib, social-wiring | 6 |
| `next_retry_at` | def | `(retry_count: int, policy: RetryPolicy, now: datetime) -> da…` | Compute when the next retry should fire. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.domain.jobs.worker`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Worker` | class | `` | Async polling worker that drains a `JobRepository`. | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.metas.periods`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `count_business_days` | def | `(start: date, end: date) -> int` | Mon-Fri count between `start` and `end`, inclusive on both ends. | erp-imobiliario, lib:noctusai_lib | 2 |
| `period_bounds` | def | `(kind: PeriodKind, ref: date) -> tuple[date, date]` | Return (start, end) inclusive bounds of the period containing `ref`. | erp-imobiliario, lib:noctusai_lib | 3 |
| `proportional_target` | def | `(monthly_target: float, kind: PeriodKind, ref: date) -> int` | Translate a monthly target into a per-period target. | erp-imobiliario, lib:noctusai_lib | 2 |
| `working_days_remaining_in_month` | def | `(ref: date) -> int` | Mon-Fri count from `ref` through last day of the month. | erp-imobiliario, lib:noctusai_lib | 2 |
| `working_days_remaining_in_week` | def | `(ref: date) -> int` | Mon-Fri count from `ref` through Sunday of the same ISO week. | erp-imobiliario, lib:noctusai_lib | 2 |
| `working_days_remaining_in_year` | def | `(ref: date) -> int` | Mon-Fri count from `ref` through Dec 31 of the same year. | erp-imobiliario, lib:noctusai_lib | 2 |
| `working_days_total_in_month` | def | `(ref: date) -> int` | Total Mon-Fri count in the month of `ref`. | erp-imobiliario, lib:noctusai_lib | 2 |
| `working_days_total_in_year` | def | `(ref: date) -> int` | Total Mon-Fri count in the year of `ref`. | erp-imobiliario, lib:noctusai_lib | 2 |

### `noctusai_lib.domain.metas.progress`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `accumulate_contribution` | def | `(target: float, current: float, increment: float) -> Progres…` | Apply a single contribution. Returns the new value, whether the | daily-life, lib:noctusai_lib, personal-finance | 3 |
| `compute_progress` | def | `(target: Target, current: float, *, contributions: Iterable[…` | Derive a Progress view from inputs. None of these are persisted on | lib:noctusai_lib, personal-finance | 4 |
| `project_completion_date` | def | `(target: float, current: float, contributions: Iterable[Cont…` | Estimate when the goal will hit `target` if monthly cadence holds. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.metas.repository`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoalRepository` | class | `` | Storage seam for goals + contributions. | lib:noctusai_lib | 1 |
| `InMemoryGoalRepository` | class | `` | Reference / testing implementation. Not for production. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.metas.status`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `can_transition` | def | `(current: GoalStatus, target: GoalStatus) -> bool` | Whether `current → target` is an allowed direct transition. | lib:noctusai_lib | 1 |
| `from_pt_string` | def | `(s: str) -> GoalStatus` | Map a PT-BR string to `GoalStatus`. Unknown strings raise. | lib:noctusai_lib | 1 |
| `next_status` | def | `(current_status: GoalStatus, *, percent_complete: float, per…` | Compute the next status from current state + progress signals. | lib:noctusai_lib | 1 |
| `to_pt_string` | def | `(status: GoalStatus) -> str` | Map `GoalStatus` to the canonical PT-BR string. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.metas.value_objects`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Contribution` | class | `` | A single increment toward a goal. `amount` is the contribution value; | lib:noctusai_lib, personal-finance | 4 |
| `Goal` | class | `` | The goal itself. `current` mirrors what the product persists in its | lib:noctusai_lib | 2 |
| `GoalStatus` | class | `` | Status state machine. Products map their own status strings | lib:noctusai_lib | 4 |
| `Period` | class | `` | Time window the goal is tracked against. `kind=OPEN_ENDED` is valid | lib:noctusai_lib | 1 |
| `PeriodKind` | class | `` | Period flavor. `OPEN_ENDED` exists for goals without a recurring | erp-imobiliario, lib:noctusai_lib | 4 |
| `Progress` | class | `` | Derived view of (target, current, contributions). Always computed, | lib:noctusai_lib | 2 |
| `ProgressTransition` | class | `` | Result of `accumulate_contribution(...)` — the new `current` value | lib:noctusai_lib | 2 |
| `Target` | class | `` | The objective amount. `amount` is whatever the product measures | lib:noctusai_lib, personal-finance | 5 |

### `noctusai_lib.domain.notifications`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `map_notification_from_pt` | def | `(data: dict) -> dict` | Map Portuguese API fields back to core notification record (English). | — | 0 |
| `map_notification_to_pt` | def | `(record: dict) -> dict` | Map a core notification record (English fields) to Portuguese API fields. | lib:noctusai_seed | 1 |

### `noctusai_lib.domain.org`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_NAME_TEMPLATE` | const | `` |  | — | 0 |
| `attach_user_to_org` | def | `(db: Any, user_id: str, *, org_id: str, email: str, nome: Op…` | Make `user_id` a member of `org_id` via `public.noctus_users`. Idempotent. | lib:noctusai_seed | 1 |
| `ensure_personal_org` | async def | `(db: Any, user_id: str, *, email: str, nome: Optional[str]=N…` | Return the user's org_id; create a personal org if they don't have one. | personal-finance | 1 |
| `find_auth_user_id_by_email` | def | `(db: Any, email: str) -> Optional[str]` | Return the `auth.users.id` for `email`, or None. | — | 0 |
| `provision_invited_identity` | def | `(db: Any, *, email: str, password: str, nome: str, user_meta…` | Return `(user_id, created)` for an invitee's email. | lib:noctusai_seed | 1 |
| `sync_org_metadata` | def | `(db: Any, user_id: str, *, org_id: str, org_role: str, nome:…` | Mirror the membership into `user_metadata`. Returns True on success. | lib:noctusai_seed | 1 |

### `noctusai_lib.domain.page_status`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_visible_pages` | def | `(db, user_org_role: str | None=None) -> list[str]` | Return list of visible page route names for the given user role. | — | 0 |

### `noctusai_lib.domain.payments.event_inbox`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EventInbox` | class | `` | First-seen check for one `(gateway, event_id)` webhook delivery. | — | 0 |
| `FakeEventInbox` | class | `` | In-memory `EventInbox` for dev + tests. Single-process only — | — | 0 |
| `RealSupabaseEventInbox` | class | `` | Supabase-client backed `EventInbox`. | — | 0 |
| `make_event_inbox` | def | `(*, use_fake: bool=False, supabase_client: Any | None=None, …` | Construct an `EventInbox`. | — | 0 |

### `noctusai_lib.domain.payments.subscription`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Subscription` | class | `` | A subscription's lifecycle snapshot. Frozen: every transition | — | 0 |
| `SubscriptionState` | class | `` | Lifecycle states for a subscription. | — | 0 |
| `is_terminal` | def | `(state: SubscriptionState) -> bool` | True iff no legal transition leaves `state`. | — | 0 |
| `legal_next_states` | def | `(state: SubscriptionState) -> frozenset[SubscriptionState]` | Every state `state` may legally move to. Empty for a terminal state. | — | 0 |
| `transition` | def | `(subscription: Subscription, new_state: SubscriptionState, *…` | Return a new `Subscription` with `state = new_state`. | — | 0 |

### `noctusai_lib.domain.permissions.repo`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakePermissionGrantRepository` | class | `` | In-memory `PermissionGrantRepository` for dev + tests. | lib:noctusai_lib | 1 |
| `PermissionGrantRepository` | class | `` | Async repository surface every named-permission consumer depends on. | lib:noctusai_lib | 3 |
| `RealSupabasePermissionGrantRepository` | class | `` | Supabase-client backed `PermissionGrantRepository`. | lib:noctusai_lib | 1 |
| `make_permission_grant_repository` | def | `(*, use_fake: bool=False, supabase_client: Any | None=None, …` | Construct a `PermissionGrantRepository` for a consumer. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.photo_editing.access`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `compute_capabilities` | async def | `(*, actor: Actor, settings: OrgSettings | None, grants: Perm…` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.photo_editing.costs`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BackfillReport` | class | `` |  | lib:noctusai_lib | 1 |
| `CATEGORY_OPENAI_EDIT` | const | `` |  | lib:noctusai_lib | 1 |
| `CATEGORY_OPENAI_TEXT` | const | `` |  | lib:noctusai_lib | 1 |
| `CATEGORY_OPENAI_VISION` | const | `` |  | lib:noctusai_lib | 1 |
| `CURRENCY_BRL` | const | `` |  | — | 0 |
| `CURRENCY_USD` | const | `` |  | — | 0 |
| `RecordedCost` | class | `` |  | lib:noctusai_lib | 1 |
| `UnpricedModelError` | class | `` | The catalog cannot price this call — a configuration error (fatal). | lib:noctusai_lib | 2 |
| `backfill_fx` | async def | `(ports: PhotoEditingPorts, *, limit: int=200) -> BackfillRep…` | Resolve ``fx_pending`` ledger rows using the bulletin for each row's | lib:noctusai_lib | 2 |
| `build_cost_row` | def | `(*, org_id: str, category: str, step: str | None, reference_…` | The ONLY constructor for a ledger row — yields exactly one of the | lib:noctusai_lib | 1 |
| `catalog_entry` | def | `(provider: str, model: str, kind: ModelKind) -> ModelEntry` |  | lib:noctusai_lib | 1 |
| `local_call_date` | def | `(at: datetime, tz_name: str) -> date` |  | — | 0 |
| `price_usage_usd` | def | `(entry: ModelEntry, usage: TokenUsage) -> Decimal` | Catalog price of ``usage`` in USD, quantized to the ledger's scale. | lib:noctusai_lib | 1 |
| `record_ai_cost` | async def | `(ports: PhotoEditingPorts, *, org_id: str, step: str, catego…` |  | lib:noctusai_lib | 3 |

### `noctusai_lib.domain.photo_editing.dataset`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CommentRequiredError` | class | `` | ``rejeitar`` without a comment (HTTP 422). | lib:noctusai_lib | 1 |
| `DecisionOutcome` | class | `` |  | lib:noctusai_lib | 1 |
| `PhotoNotDecidableError` | class | `` | The photo has not reached review yet, or failed (HTTP 409). | lib:noctusai_lib | 1 |
| `build_dataset_record` | def | `(*, batch: Batch, photo: Photo, decision: ReviewDecision, ed…` |  | lib:noctusai_lib | 1 |
| `record_decision` | async def | `(ports: PhotoEditingPorts, *, foto_id: str, decisao: Decisio…` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.photo_editing.guide`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ComposedGuide` | class | `` |  | — | 0 |
| `GuideNotActiveError` | class | `` | No company guide is active — batches cannot be submitted. | lib:noctusai_lib | 2 |
| `GuideVersionNotFoundError` | class | `` |  | lib:noctusai_lib | 1 |
| `activate_version` | async def | `(ports: PhotoEditingPorts, versao: int, *, ativado_por: str)…` |  | lib:noctusai_lib | 1 |
| `compose_effective_guide` | def | `(guide: StyleGuide, rules: Sequence[OrgRule]) -> ComposedGui…` | Pure + deterministic. Only APPROVED rules are included. | lib:noctusai_lib | 1 |
| `create_draft` | async def | `(ports: PhotoEditingPorts, *, texto: str, gerado_de_versao: …` |  | lib:noctusai_lib | 1 |
| `generate_draft_from_pool` | async def | `(ports: PhotoEditingPorts) -> StyleGuide | None` | Style-guide builder: pool pairs → AI-written DRAFT. ``None`` when the | lib:noctusai_lib | 2 |
| `normalize_text` | def | `(text: str) -> str` | Line endings → ``\n``, trailing spaces stripped, one final newline. | lib:noctusai_lib | 1 |
| `order_rules` | def | `(rules: Sequence[OrgRule]) -> list[OrgRule]` | Canonical rule order: approval time, then id — stable across reads. | — | 0 |
| `resolve_effective_guide` | async def | `(ports: PhotoEditingPorts, org_id: str) -> EffectiveGuide` | Compose, version the org's rule set if it changed, persist (idempotent | lib:noctusai_lib | 3 |
| `restore_version` | async def | `(ports: PhotoEditingPorts, versao: int, *, criado_por: str) …` | Clone ``versao`` as a NEW draft (versions stay immutable). | lib:noctusai_lib | 1 |
| `rule_set_sha256` | def | `(regra_ids: Sequence[str]) -> str` |  | — | 0 |

### `noctusai_lib.domain.photo_editing.handlers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EditQuotaExceededError` | class | `` | The org's edit quota is exhausted — fatal for this attempt; a | lib:noctusai_lib | 1 |
| `PhotoEditingConfigError` | class | `` | The engine is not configured to run this step — fatal. | lib:noctusai_lib | 1 |
| `build_handlers` | def | `(ports: PhotoEditingPorts) -> dict[str, JobHandler]` |  | lib:noctusai_lib | 1 |
| `build_worker` | def | `(ports: PhotoEditingPorts, *, worker_id: str, poll_interval_…` |  | lib:noctusai_lib | 1 |
| `failure_reason` | def | `(exc: BaseException) -> str` |  | — | 0 |
| `handle_avaliar` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` |  | lib:noctusai_lib | 1 |
| `handle_edit` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` |  | lib:noctusai_lib | 1 |
| `handle_fx_backfill` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` |  | lib:noctusai_lib | 1 |
| `handle_ingest` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` | Normalize the upload (HEIC→JPEG, EXIF transpose, sRGB, GPS strip), | lib:noctusai_lib | 1 |
| `handle_lote_pronto` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` |  | lib:noctusai_lib | 1 |
| `handle_propor_regras` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` |  | lib:noctusai_lib | 1 |
| `handle_regen_guia` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` |  | lib:noctusai_lib | 1 |
| `handle_submit_lote` | async def | `(ports: PhotoEditingPorts, job: Job) -> None` | Move a submitted batch to ``processando`` and enqueue the edits of | lib:noctusai_lib | 1 |
| `is_retryable` | def | `(exc: BaseException) -> bool` | The engine's single retryable-vs-fatal classifier. | lib:noctusai_lib | 1 |
| `parse_evaluation` | def | `(data: dict[str, Any]) -> tuple[Decision, Decimal, str, bool…` | Validate the evaluator's JSON. Structural infidelity FORCES | — | 0 |

### `noctusai_lib.domain.photo_editing.learning`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Actor` | class | `` | Server-resolved identity of whoever is acting (never SSO metadata). | lib:noctusai_lib | 2 |
| `InvalidModelOutputError` | class | `` | The model answered outside its schema — retryable. | lib:noctusai_lib | 2 |
| `RuleDecisionForbiddenError` | class | `` |  | lib:noctusai_lib | 1 |
| `RuleNotFoundError` | class | `` |  | lib:noctusai_lib | 1 |
| `can_decide_rule` | def | `(actor: Actor, rule: OrgRule, target: RuleStatus) -> bool` |  | — | 0 |
| `decide_rule` | async def | `(ports: PhotoEditingPorts, regra_id: str, *, approve: bool, …` |  | lib:noctusai_lib | 1 |
| `propose_rules` | async def | `(ports: PhotoEditingPorts, org_id: str) -> list[OrgRule]` | Run the rule proposer over the org's rejections since the cursor. | lib:noctusai_lib | 2 |
| `rule_key` | def | `(texto: str) -> str` | Duplicate-detection key: whitespace- and case-insensitive. | — | 0 |

### `noctusai_lib.domain.photo_editing.naming`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EDITED_NAME` | const | `` |  | lib:noctusai_lib | 1 |
| `ORIGINAL_NAME` | const | `` |  | lib:noctusai_lib | 1 |
| `OUTPUT_EXTENSION` | const | `` |  | — | 0 |
| `STAGING_SUFFIX` | const | `` |  | lib:noctusai_lib | 1 |
| `STAGING_WATERMARK_TEXT` | const | `` |  | lib:noctusai_lib | 1 |
| `UPLOAD_NAME` | const | `` |  | — | 0 |
| `is_staged` | def | `(tipos: Iterable[EditType]) -> bool` |  | lib:noctusai_lib | 1 |
| `storage_path` | def | `(org_id: str, lote_id: str, foto_id: str, name: str) -> str` |  | lib:noctusai_lib | 2 |
| `upload_path` | def | `(org_id: str, lote_id: str, foto_id: str, extension: str) ->…` |  | lib:noctusai_lib | 1 |
| `zip_entry_name` | def | `(ordem: int, *, total_photos: int, tipos: Iterable[EditType]…` | ``"07.jpg"`` / ``"007.jpg"`` / ``"07_imagem-gerada-com-ia.jpg"``. | lib:noctusai_lib | 2 |
| `zip_file_name` | def | `(lote_nome: str) -> str` | Download name for the batch zip; path separators are neutralized. | lib:noctusai_lib | 1 |
| `zip_number_width` | def | `(total_photos: int) -> int` |  | — | 0 |

### `noctusai_lib.domain.photo_editing.pipeline`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ECONOMICO_IMPLEMENTED` | const | `` |  | lib:noctusai_lib | 2 |
| `NotFoundError` | class | `` |  | lib:noctusai_lib | 2 |
| `PhotoNotRetryableError` | class | `` |  | lib:noctusai_lib | 1 |
| `SubmissionError` | class | `` | A batch cannot be submitted / extended. ``code`` is the API code. | lib:noctusai_lib | 2 |
| `SubmissionPlan` | class | `` |  | — | 0 |
| `add_photo_bytes` | async def | `(ports: PhotoEditingPorts, *, lote_id: str, data: bytes, ext…` | Store one upload (or a Vista-pulled photo) and enqueue its ingest. | lib:noctusai_lib | 1 |
| `enqueue_batch_ready_check` | async def | `(ports: PhotoEditingPorts, lote_id: str) -> Job` |  | lib:noctusai_lib | 1 |
| `enqueue_edit` | async def | `(ports: PhotoEditingPorts, photo: Photo) -> Job` |  | lib:noctusai_lib | 1 |
| `enqueue_evaluation` | async def | `(ports: PhotoEditingPorts, foto_id: str, edicao_id: str) -> …` |  | lib:noctusai_lib | 1 |
| `enqueue_fx_backfill` | async def | `(ports: PhotoEditingPorts, day: date) -> Job` |  | lib:noctusai_lib | 1 |
| `enqueue_ingest` | async def | `(ports: PhotoEditingPorts, photo: Photo) -> Job` |  | — | 0 |
| `retry_photo` | async def | `(ports: PhotoEditingPorts, foto_id: str, *, requested_by: st…` | Re-run a ``falhou`` photo as a NEW attempt (fresh dedupe key). | lib:noctusai_lib | 1 |
| `schedule_guide_regen` | async def | `(ports: PhotoEditingPorts) -> Job` | Trailing debounce: one job per window, run at the window's end; the | lib:noctusai_lib | 2 |
| `schedule_rule_proposal` | async def | `(ports: PhotoEditingPorts, org_id: str) -> Job` |  | lib:noctusai_lib | 3 |
| `submit_batch` | async def | `(ports: PhotoEditingPorts, lote_id: str, *, submitted_by: st…` | Route-side submit: validate, SNAPSHOT the effective guide + editor | lib:noctusai_lib | 1 |
| `validate_submission` | async def | `(ports: PhotoEditingPorts, batch: Batch) -> SubmissionPlan` | Every precondition for running a batch. Raises ``SubmissionError``. | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.photo_editing.ports`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BatchReadyNotice` | class | `` |  | lib:noctusai_lib | 2 |
| `BatchReadyNotifier` | class | `` | Fan-out is the consumer's job (in-app + email + WhatsApp, opt-ins, | lib:noctusai_lib | 1 |
| `FakeStructuredLlm` | class | `` | Scripted ``StructuredLlm``. | lib:noctusai_lib | 1 |
| `InMemoryPhotoStorage` | class | `` |  | lib:noctusai_lib | 1 |
| `LlmStructuredAdapter` | class | `` | Real ``StructuredLlm`` over ``noctusai_lib.integrations.llm.analyze_images``. | lib:noctusai_lib | 1 |
| `PhotoEditingConfig` | class | `` | Engine tunables. Model defaults are the owner's plan §1 choices; the | lib:noctusai_lib | 1 |
| `PhotoEditingPorts` | class | `` |  | lib:noctusai_lib | 8 |
| `PhotoStorage` | class | `` | Bytes in / bytes out by path (``naming.storage_path`` layout). | lib:noctusai_lib | 1 |
| `RecordingNotifier` | class | `` |  | lib:noctusai_lib | 1 |
| `StructuredLlm` | class | `` |  | lib:noctusai_lib | 1 |
| `StructuredResult` | class | `` |  | lib:noctusai_lib | 1 |
| `TokenUsage` | class | `` |  | lib:noctusai_lib | 3 |
| `openai_image_edit_factory` | def | `(key_provider: Callable[..., str | None]) -> ImageEditFactor…` | Real factory: resolves the org's OpenAI key per call and REFUSES | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.photo_editing.prompts._base`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PromptTemplate` | class | `` |  | lib:noctusai_lib | 6 |
| `RenderedPrompt` | class | `` |  | lib:noctusai_lib | 6 |

### `noctusai_lib.domain.photo_editing.prompts.edit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EDIT_PROMPT` | const | `` |  | lib:noctusai_lib | 1 |
| `render_edit_prompt` | def | `(tipos: Iterable[EditType], *, guia_texto: str, guia_sha256:…` | Render the combined instruction. ``tipos`` must be non-empty; the | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.photo_editing.prompts.evaluator`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EVALUATOR_PROMPT` | const | `` |  | lib:noctusai_lib | 1 |
| `render_evaluator_prompt` | def | `(tipos: Iterable[EditType], *, guia_texto: str) -> RenderedP…` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.photo_editing.prompts.note_writer`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ModelMetrics` | class | `` | Mirror of the consumer's ``fotos_modelo_metricas`` RPC row. | lib:noctusai_lib | 1 |
| `NOTE_WRITER_PROMPT` | const | `` |  | lib:noctusai_lib | 1 |
| `render_note_writer_prompt` | def | `(m: ModelMetrics) -> RenderedPrompt` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.photo_editing.prompts.rule_proposer`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RULE_PROPOSER_PROMPT` | const | `` |  | lib:noctusai_lib | 1 |
| `render_rule_proposer_prompt` | def | `(comentarios: Sequence[str], regras_atuais: Sequence[str]) -…` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.photo_editing.prompts.style_guide`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `STYLE_GUIDE_PROMPT` | const | `` |  | lib:noctusai_lib | 1 |
| `render_style_guide_prompt` | def | `(pares: Sequence[ReferencePair]) -> RenderedPrompt` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.photo_editing.repository`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryPhotoEditingRepository` | class | `` | Deterministic in-memory repository for dev + tests. | lib:noctusai_lib | 1 |
| `PhotoEditingRepository` | class | `` |  | lib:noctusai_lib | 2 |
| `RepositoryError` | class | `` | A write the engine relies on did not return the row it wrote. | lib:noctusai_lib | 1 |
| `SupabasePhotoEditingRepository` | class | `` | Supabase-client backed repository. | lib:noctusai_lib | 1 |
| `make_photo_editing_repository` | def | `(*, use_fake: bool=False, supabase_client: Any | None=None, …` | Construct a repository. ``use_fake=True`` ⇒ in-memory; otherwise a | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.photo_editing.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Batch` | class | `` |  | lib:noctusai_lib | 5 |
| `BatchStatus` | class | `` | Per-batch (lote) state. | lib:noctusai_lib | 4 |
| `CostLedgerRow` | class | `` | One Core ``public.cost_ledger`` row (Core 046). | lib:noctusai_lib | 2 |
| `DatasetRecord` | class | `` | One append-only training-ready row (``fotos_dataset``). | lib:noctusai_lib | 2 |
| `Decision` | class | `` |  | lib:noctusai_lib | 5 |
| `EditAttempt` | class | `` |  | lib:noctusai_lib | 2 |
| `EditType` | class | `` | The fixed edit-type vocabulary the owner defined. | lib:noctusai_lib | 7 |
| `EffectiveGuide` | class | `` | Company guide + org rules, frozen (``fotos_guias_efetivos``). | lib:noctusai_lib | 3 |
| `Evaluation` | class | `` |  | lib:noctusai_lib | 2 |
| `GuideStatus` | class | `` |  | lib:noctusai_lib | 1 |
| `IllegalTransitionError` | class | `` | A photo transition not in the legal set was requested. | lib:noctusai_lib | 2 |
| `JobType` | class | `` | Job-type names the engine registers on `domain.jobs.Worker`. | lib:noctusai_lib | 4 |
| `LlmUsageRow` | class | `` | One ``llm_usage`` row (the 122 shape, incl. image tokens). | lib:noctusai_lib | 2 |
| `MAX_BYTES_PER_PHOTO` | const | `` |  | — | 0 |
| `MAX_PHOTOS_PER_BATCH` | const | `` |  | — | 0 |
| `OrgRule` | class | `` |  | lib:noctusai_lib | 3 |
| `OrgSettings` | class | `` |  | lib:noctusai_lib | 5 |
| `PHOTO_CURATOR_PERMISSION` | const | `` |  | lib:noctusai_lib | 1 |
| `Photo` | class | `` |  | lib:noctusai_lib | 6 |
| `PhotoEvent` | class | `` |  | lib:noctusai_lib | 3 |
| `PhotoStatus` | class | `` | Per-photo pipeline state (contract §3 state machine). | lib:noctusai_lib | 6 |
| `PlatformSettings` | class | `` |  | lib:noctusai_lib | 1 |
| `ProposalCursor` | class | `` |  | lib:noctusai_lib | 3 |
| `ReferencePair` | class | `` |  | lib:noctusai_lib | 2 |
| `ReviewDecision` | class | `` |  | lib:noctusai_lib | 3 |
| `Room` | class | `` | Fixed room/area tag list for reference pairs. | lib:noctusai_lib | 1 |
| `RuleSet` | class | `` | Versioned snapshot of an org's approved rules (``fotos_conjuntos_regras``). | lib:noctusai_lib | 1 |
| `RuleStatus` | class | `` |  | lib:noctusai_lib | 4 |
| `Speed` | class | `` |  | lib:noctusai_lib | 3 |
| `StyleGuide` | class | `` |  | lib:noctusai_lib | 2 |
| `batch_state_signature` | def | `(photos: list[Photo]) -> str` | Stable digest of every photo's (id, status, tentativas). | lib:noctusai_lib | 1 |
| `can_transition` | def | `(current: PhotoStatus, target: PhotoStatus) -> bool` | True iff ``current -> target`` is a legal photo transition. | lib:noctusai_lib | 1 |
| `debounce_bucket` | def | `(at: datetime, window_seconds: int) -> int` | Integer window index for a trailing debounce. | lib:noctusai_lib | 1 |
| `dedupe_avaliar` | def | `(foto_id: str, edicao_id: str) -> str` |  | lib:noctusai_lib | 1 |
| `dedupe_edit` | def | `(foto_id: str, tentativas: int) -> str` | One edit job per (photo, attempt round). | lib:noctusai_lib | 1 |
| `dedupe_fx_backfill` | def | `(day_iso: str) -> str` |  | lib:noctusai_lib | 1 |
| `dedupe_ingest` | def | `(foto_id: str, tentativas: int=0) -> str` |  | lib:noctusai_lib | 1 |
| `dedupe_lote_pronto` | def | `(lote_id: str, signature: str) -> str` |  | lib:noctusai_lib | 1 |
| `dedupe_propor_regras` | def | `(org_id: str, bucket: int) -> str` |  | lib:noctusai_lib | 1 |
| `dedupe_regen_guia` | def | `(bucket: int) -> str` |  | lib:noctusai_lib | 1 |
| `dedupe_submit` | def | `(lote_id: str) -> str` |  | lib:noctusai_lib | 1 |
| `sha256_text` | def | `(text: str) -> str` |  | lib:noctusai_lib | 1 |
| `sources_for` | def | `(target: PhotoStatus) -> frozenset[PhotoStatus]` | Every state a photo may legally enter ``target`` from. | — | 0 |

### `noctusai_lib.domain.photo_editing.zipper`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BatchNotDecidedError` | class | `` | At least one photo still awaits processing or a decision (HTTP 409). | lib:noctusai_lib | 1 |
| `NothingApprovedError` | class | `` | Every photo was decided but none approved — there is nothing to zip. | lib:noctusai_lib | 1 |
| `ZipEntry` | class | `` |  | — | 0 |
| `build_batch_zip` | async def | `(ports: 'PhotoEditingPorts', lote_id: str) -> bytes` | Read the batch, plan it, fetch the approved files, return zip bytes. | lib:noctusai_lib | 1 |
| `build_zip` | def | `(files: list[tuple[str, bytes]]) -> bytes` | Deterministic zip of ``(name, bytes)`` pairs. JPEGs are already | lib:noctusai_lib | 1 |
| `plan_zip` | def | `(photos: list[Photo], decisions: dict[str, ReviewDecision], …` | Pure: which stored files go into the zip, under which names. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.pipeline.board`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `group_into_colunas` | def | `(cfg: PipelineConfig, stages: list[dict[str, Any]], rows: li…` | One column per configured stage, cards bucketed by `etapa_id`. | — | 0 |
| `orphan_cards` | def | `(stages: list[dict[str, Any]], rows: list[dict[str, Any]]) -…` | Cards pointing at a stage this pipeline no longer offers. | — | 0 |
| `stage_to_dto` | def | `(stage: dict[str, Any]) -> dict[str, Any]` | Project a stage row to the shape the frontend renders columns from. | — | 0 |

### `noctusai_lib.domain.pipeline.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PipelineConfig` | class | `` | Declarative description of one kanban pipeline. | lib:noctusai_lib | 4 |

### `noctusai_lib.domain.pipeline.moves`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `move_card` | def | `(db, cfg: PipelineConfig, *, card_id: str, to_stage_id: str,…` | Move one card to `to_stage_id`, recording the transition. | — | 0 |
| `resolve_initial_stage` | def | `(db, cfg: PipelineConfig, *, org_id: str | None=None) -> dic…` | The stage a card enters the board at — the first in configured order. | — | 0 |

### `noctusai_lib.domain.pipeline.ordering`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `POSITION_FIELD` | const | `` |  | — | 0 |
| `position_for_index` | def | `(cards: Sequence[Any], index: int) -> Decimal` | The position that lands a card at `index` within `cards`. | — | 0 |
| `position_of` | def | `(card: Any) -> Decimal` | A card's position as `Decimal`, tolerating dict or object rows. | lib:noctusai_lib | 1 |
| `position_on_top` | def | `(cards: Sequence[Any]) -> Decimal` | A position strictly above every card in `cards`. | — | 0 |

### `noctusai_lib.domain.pipeline.router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PipelineContext` | class | `` | What every handler actually needs, however the product supplies it. | — | 0 |
| `StageCreate` | class | `` |  | — | 0 |
| `StageReorder` | class | `` |  | — | 0 |
| `StageUpdate` | class | `` |  | — | 0 |
| `pipeline_stages_router` | def | `(cfg: PipelineConfig, *, auth_dependency: Callable[..., Any]…` | Build a stage-CRUD router for one pipeline. | — | 0 |

### `noctusai_lib.domain.pipeline.stages`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `STAGE_ROLE_ACCEPT` | const | `` |  | — | 0 |
| `STAGE_ROLE_FINAL` | const | `` |  | — | 0 |
| `count_cards_in_stage` | def | `(db, cfg: PipelineConfig, stage_id: str, *, org_id: str | No…` |  | — | 0 |
| `create_stage` | def | `(db, cfg: PipelineConfig, payload: dict[str, Any], *, org_id…` |  | lib:noctusai_lib | 1 |
| `delete_stage` | def | `(db, cfg: PipelineConfig, stage_id: str, *, reassign_to: str…` | Delete a stage, refusing the two cases that would lose data or break a feature. | lib:noctusai_lib | 1 |
| `get_stage` | def | `(db, cfg: PipelineConfig, stage_id: str, *, org_id: str | No…` |  | lib:noctusai_lib | 1 |
| `list_stages` | def | `(db, cfg: PipelineConfig, *, incluir_inativas: bool=False, o…` | Ordered stages for this pipeline. | lib:noctusai_lib | 2 |
| `reorder_stages` | def | `(db, cfg: PipelineConfig, ordered_ids: list[str], *, org_id:…` | Rewrite `posicao` from an ordered id list. | lib:noctusai_lib | 1 |
| `slugify` | def | `(label: str) -> str` | Derive a stable machine key from a human label. | — | 0 |
| `stage_by_role` | def | `(db, cfg: PipelineConfig, papel: str, *, org_id: str | None=…` | The stage carrying a semantic role, or None. | — | 0 |
| `update_stage` | def | `(db, cfg: PipelineConfig, stage_id: str, payload: dict[str, …` | Edit a stage. Renaming is just this — no card is touched. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.real_estate.imovel`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Corretor` | class | `` | One broker assigned to an imóvel. | lib:noctusai_lib, social-wiring | 2 |
| `Imovel` | class | `` | A real-estate listing, coerced off the Vista wire. | lib:noctusai_lib, social-wiring | 11 |
| `ImovelFoto` | class | `` | One photo in an imóvel's gallery. | lib:noctusai_lib | 4 |
| `ImovelPage` | class | `` | One page of a catalog read. | lib:noctusai_lib | 4 |
| `caracteristica_slug` | def | `(key: str) -> str` | Normalize a Vista amenity key to a stable slug. | lib:noctusai_lib | 1 |
| `derive_finalidades` | def | `(*, finalidade_status: Any=None, status: Any=None, finalidad…` | Resolve what the imóvel is FOR: ``{"venda"}``, ``{"aluguel"}``, or both. | lib:noctusai_lib | 2 |
| `parse_caracteristicas` | def | `(raw: Any) -> frozenset[str]` | Return the slug set of amenities the imóvel actually HAS. | lib:noctusai_lib | 2 |
| `parse_corretores` | def | `(raw: Any) -> list[Corretor]` | Return EVERY assigned broker, not just the first. | lib:noctusai_lib | 2 |
| `parse_imovel_fotos` | def | `(raw: Any) -> list[ImovelFoto]` | Normalize Vista's ``Foto`` gallery — dict-keyed by photo code. | lib:noctusai_lib | 3 |

### `noctusai_lib.domain.real_estate.matching`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MIN_PRECO` | const | `` |  | erp-imobiliario | 1 |
| `MIN_REGIAO` | const | `` |  | erp-imobiliario | 1 |
| `MIN_SPECS` | const | `` |  | erp-imobiliario | 1 |
| `SCORE_MINIMO_PADRAO` | const | `` |  | erp-imobiliario, lib:noctusai_lib, social-wiring | 3 |
| `SIM_THRESHOLD` | const | `` |  | erp-imobiliario, social-wiring | 2 |
| `calcular_alinhamento_interesses` | def | `(imovel: dict, permuta: dict) -> int` | Does what the permuta offers answer what the imóvel's owner asked for? Max 15. | erp-imobiliario | 1 |
| `calcular_bilateral_similarity` | def | `(imovel: dict, permuta: dict) -> float` | Average of the two directional cosine similarities, or 0.0. | erp-imobiliario, social-wiring | 2 |
| `calcular_compatibilidade_preco` | def | `(imovel: dict, permuta: dict) -> int` | Price fit. Max 25. | erp-imobiliario | 1 |
| `calcular_compatibilidade_regiao` | def | `(imovel: dict, permuta: dict) -> int` | Location overlap. Max 30. | erp-imobiliario | 1 |
| `calcular_compatibilidade_specs` | def | `(imovel: dict, permuta: dict) -> int` | Property or vehicle specs. Max 20. | erp-imobiliario | 1 |
| `calcular_qualidade_anuncio` | def | `(imovel: dict) -> int` | How complete the listing is. Max 10. | erp-imobiliario | 1 |
| `calcular_score_total` | def | `(imovel: dict, permuta: dict) -> Optional[dict]` | Score one pair. ``None`` means the hard gate rejected it. | erp-imobiliario, lib:noctusai_lib, social-wiring | 3 |
| `falta_vetor_bilateral` | def | `(imovel: dict, permuta: dict) -> bool` | True when the composite cannot run because a vector is missing. | erp-imobiliario, lib:noctusai_lib, social-wiring | 4 |
| `gerar_matches_para_imovel` | def | `(imovel: dict, permutas: list[dict], score_minimo: float=SCO…` | Every permuta worth showing against one listing, best first. | erp-imobiliario, lib:noctusai_lib, social-wiring | 5 |
| `gerar_matches_para_permuta` | def | `(permuta: dict, imoveis: list[dict], score_minimo: float=SCO…` | Every listing worth showing against one permuta, best first. | erp-imobiliario, lib:noctusai_lib, social-wiring | 3 |
| `passa_filtros_minimos` | def | `(imovel: dict, permuta: dict, regiao: int, preco: int, specs…` | The hard gate. False discards the pair before it is ever scored. | erp-imobiliario | 1 |

### `noctusai_lib.domain.real_estate.metadata`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_youtube_metadata` | def | `(prop: PropertyData, product_code: str) -> dict[str, str | l…` | Build YouTube video metadata from CRM property data. | lib:noctusai_lib, social-wiring | 3 |
| `imovel_to_property_data` | def | `(imovel: Imovel) -> PropertyData` | Map the canonical `Imovel` listing to the narrower `PropertyData` | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.domain.real_estate.parcelamento`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CENTAVO` | const | `` |  | — | 0 |
| `dividir_em_parcelas_iguais` | def | `(valor_total: Decimal, num_parcelas: int) -> list[Decimal]` | Split `valor_total` into `num_parcelas` installments, largest first. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.domain.real_estate.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PropertyData` | class | `` | Structured property metadata from a real estate CRM. | lib:noctusai_lib, social-wiring | 10 |

### `noctusai_lib.domain.real_estate.validators`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PRODUCT_CODE_PATTERN` | const | `` |  | lib:noctusai_lib | 1 |
| `PRODUCT_CODE_SCAN_PATTERN` | const | `` |  | lib:noctusai_lib, social-wiring | 4 |
| `extract_product_code` | def | `(text: str) -> Optional[str]` | Return the first product code found in ``text``, upper-cased. | lib:noctusai_lib | 1 |
| `find_product_codes` | def | `(text: str) -> list[str]` | Return every product code found in ``text``, upper-cased, in order. | lib:noctusai_lib, social-wiring | 2 |
| `validate_product_code` | def | `(code: str) -> bool` | Check if a product code matches the expected format. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.domain.scheduling.engine`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BlockedInterval` | class | `` | A pre-existing scheduled interval that constrains slot selection. | lib:noctusai_lib, social-wiring, therapy-platform | 4 |
| `Conflict` | class | `` | Pluggable rule that decides whether a candidate slot is valid. | lib:noctusai_lib, social-wiring | 2 |
| `DefaultConflict` | class | `` | Mirrors sibling `_is_valid` logic, inverted to return True on conflict. | lib:noctusai_lib, social-wiring, therapy-platform | 3 |
| `DefaultScorer` | class | `` | Sums travel minutes from previous-interval and to next-interval. | lib:noctusai_lib, social-wiring | 2 |
| `SchedulingContext` | class | `` | Per-candidate evaluation context passed to Conflict + Scorer | lib:noctusai_lib, social-wiring, therapy-platform | 4 |
| `SchedulingEngine` | class | `` | Generate candidate slots for a date, filter by conflicts, score, sort. | lib:noctusai_lib, social-wiring, therapy-platform | 3 |
| `SchedulingRules` | class | `` | Engine configuration. All durations are minutes. | lib:noctusai_lib, social-wiring, therapy-platform | 4 |
| `Scorer` | class | `` | Pluggable scorer. Lower is better. Engine sorts by `(score, start_at)`. | lib:noctusai_lib, social-wiring | 2 |
| `Slot` | class | `` | Candidate slot returned by the engine. `score` is filled by the | lib:noctusai_lib, social-wiring, therapy-platform | 5 |
| `TravelLookup` | class | `` | Travel-minutes lookup between two locations. Same location → 0 | lib:noctusai_lib, social-wiring | 2 |
| `WorkingWindow` | class | `` | Named time-of-day window. Names enable per-call filtering | lib:noctusai_lib, social-wiring, therapy-platform | 3 |
| `ZeroTravelLookup` | class | `` | Travel-free lookup. Useful for scenarios where transition between | lib:noctusai_lib, social-wiring, therapy-platform | 4 |

### `noctusai_lib.domain.sql_templates`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `rls_subquery_policy` | def | `(schema: str, table: str, policy_name: str, command: str, us…` | Emit a ``CREATE POLICY`` that uses the ``(SELECT auth.uid())`` subquery shape. | — | 0 |
| `service_role_bypass` | def | `(table: str, schema: str='public') -> str` | Emit the canonical ``service_role_bypass`` policy for one table. | lib:noctusai_lib | 1 |
| `set_search_path` | def | `(*schemas: str) -> str` | Emit ``SET search_path = <schemas>, public`` — schema-lock prelude. | lib:noctusai_lib | 1 |
| `updated_at_function` | def | `(schema: str, function_name: str='set_updated_at') -> str` | Emit the canonical auto-touch helper function for ``<schema>``. | lib:noctusai_lib | 1 |
| `updated_at_trigger` | def | `(schema: str, table: str, function_name: str='set_updated_at…` | Emit a ``BEFORE UPDATE`` trigger that calls ``<schema>.<function_name>``. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.texto_ptbr`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CENTAVO` | const | `` |  | social-wiring | 1 |
| `brl_por_extenso` | def | `(valor: Decimal) -> str` | `Decimal("1234.56")` -> "R$ 1.234,56 (mil, duzentos e trinta e quatro | social-wiring | 2 |
| `data_por_extenso` | def | `(d: date) -> str` | `date(2026, 9, 5)` -> "05 de setembro de 2026". | social-wiring | 1 |
| `dias_por_extenso` | def | `(n: int, *, uteis: bool=False) -> str` | `90` -> "90 (noventa) dias corridos"; `5, uteis=True` -> "5 (cinco) dias | social-wiring | 3 |
| `formatar_brl` | def | `(valor: Decimal) -> str` | `Decimal("1234.5")` -> "R$ 1.234,50". | social-wiring | 1 |
| `formatar_data_br` | def | `(d: date) -> str` | `date(2026, 9, 5)` -> "05/09/2026" — four-digit year, always. | social-wiring | 1 |
| `formatar_inteiro_br` | def | `(n: int) -> str` | `1234567` -> "1.234.567". | social-wiring | 1 |
| `inteiro_por_extenso` | def | `(n: int, *, feminino: bool=False) -> str` | `1234` -> "mil, duzentos e trinta e quatro". | — | 0 |
| `numero_com_extenso` | def | `(n: int, *, feminino: bool=False, largura: int=0) -> str` | `2, feminino=True, largura=2` -> "02 (duas)". | social-wiring | 1 |
| `ordinal_por_extenso` | def | `(n: int, *, feminino: bool=False) -> str` | `11` -> "décimo primeiro" (or "décima primeira"). Lowercase; the caller | social-wiring | 2 |
| `parse_brl` | def | `(texto: str) -> Decimal` | `"R$ 1.234,56"` -> `Decimal("1234.56")`. The inverse of `formatar_brl`, | social-wiring | 2 |
| `percentual_por_extenso` | def | `(valor: Decimal) -> str` | `Decimal("1")` -> "1% (um por cento)"; `Decimal("1.25")` -> "1,25% (um | social-wiring | 1 |
| `reais_por_extenso` | def | `(valor: Decimal) -> str` | `Decimal("1234.56")` -> "mil, duzentos e trinta e quatro reais e | social-wiring | 2 |

### `noctusai_lib.graph.build`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_graph` | def | `(repo_root: Path, *, scope: str='repo', memory_root: Path | …` | Run extractors and return the assembled, deduplicated, clustered graph. | — | 0 |

### `noctusai_lib.graph.extract_cli`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `cli_flag_id` | def | `(flag: str) -> str` |  | — | 0 |
| `walk_cli` | def | `(graph: Graph, cli_path: Path, *, repo_root: Path) -> None` | Index every --flag declared in mcp/noctusai/cli.py. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_code`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BarrelResolver` | class | `` | Resolves named symbols imported from @noctusai barrel paths to canonical compone… | lib:noctusai_lib | 1 |
| `CodeRoot` | class | `` | One root the walker scans. Used to label nodes by product/seed. | lib:noctusai_lib | 1 |
| `code_id` | def | `(path: Path, symbol: str | None=None, *, repo_root: Path) ->…` | Stable id: ``code:<rel-path>[:symbol]``. | — | 0 |
| `walk` | def | `(graph: Graph, root: CodeRoot, *, repo_root: Path, only_path…` | Walk a root and emit nodes + edges into ``graph``. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_docs`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `kb_id` | def | `(rel_path: str) -> str` | Stable id: ``kb:<rel-from-KB-root>`` (e.g. ``kb:PATTERNS/ast.md``). | — | 0 |
| `walk_findings` | def | `(graph: Graph, repo_root: Path) -> None` | Index every `findings.md` in the active workspace (not archive). | lib:noctusai_lib | 1 |
| `walk_kb` | def | `(graph: Graph, kb_root: Path, *, repo_root: Path) -> None` | Index every `.md` under ``KNOWLEDGE-BASE/`` and link to code nodes. | lib:noctusai_lib | 1 |
| `walk_projects` | def | `(graph: Graph, projects_root: Path, *, repo_root: Path) -> N…` | Index `projects/**/PROJECT.md` and `products/*/projects/**/PROJECT.md`. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_harness`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `agent_id` | def | `(name: str) -> str` |  | — | 0 |
| `command_id` | def | `(name: str) -> str` |  | — | 0 |
| `skill_id` | def | `(name: str) -> str` |  | — | 0 |
| `walk_harness` | def | `(graph: Graph, claude_dir: Path, *, repo_root: Path) -> None` | Walk `.claude/{agents,skills,commands}` and emit harness nodes. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_history`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `walk_auto_improvement` | def | `(graph: Graph, ndjson_path: Path) -> None` | Aggregate auto-improvement.ndjson into per-target decorations. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_landscape`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `landscape_id` | def | `(rel: str) -> str` | Stable id: `landscape:<repo-rel-path>`. | — | 0 |
| `walk_kb_chapters` | def | `(graph: Graph, kb_root: Path, *, repo_root: Path) -> None` | Top-level `KNOWLEDGE-BASE/0X-NAME.md` chapters → KB_CHAPTER nodes. | lib:noctusai_lib | 1 |
| `walk_landscape` | def | `(graph: Graph, repo_root: Path) -> None` | Emit nodes for top-level methodology docs. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_memory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `memory_id` | def | `(slug: str) -> str` |  | — | 0 |
| `walk_memory` | def | `(graph: Graph, memory_root: Path, *, repo_root: Path) -> Non…` | Index ``MEMORY.md`` + every sibling ``*.md``. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.extract_mined`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ingest_guarded_by_edges` | def | `(graph: Graph, bindings: list[tuple[str, str]]) -> None` | Inject GUARDED_BY edges: guarded_node --GUARDED_BY--> keeper_node. | — | 0 |
| `ingest_mined_rows` | def | `(graph: Graph, rows_by_scanner: dict[str, list[dict]]) -> No…` | Idempotent ingestion of pre-collected mined rows. | lib:noctusai_lib | 1 |
| `ingest_semantic_neighbors` | def | `(graph: Graph, pairs: list[tuple[str, str, float]]) -> None` | Inject SEMANTIC_NEIGHBOR edges from pre-computed cosine pairs. | — | 0 |
| `walk_mined` | def | `(graph: Graph, repo_root: Path) -> None` | Run every available feeder and add MINED_RECURRENCE edges. | — | 0 |

### `noctusai_lib.graph.extract_products`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `walk_products` | def | `(graph: Graph, landscape_md: Path) -> None` | Parse `KNOWLEDGE-BASE/02-LANDSCAPE.md` and emit product anchors. | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.html_template`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `HTML_TEMPLATE` | const | `` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.graph.query`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GraphIndex` | class | `` | In-memory adjacency + label index for cheap query. | — | 0 |

### `noctusai_lib.graph.schema`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Confidence` | class | `` | Provenance-derived confidence. Free-form floats also allowed (mined edges). | lib:noctusai_lib | 9 |
| `Edge` | class | `` | Directed edge. ``confidence`` is the source's quality signal. | lib:noctusai_lib | 9 |
| `EdgeKind` | class | `` | Edge taxonomy. Open. | lib:noctusai_lib | 9 |
| `Graph` | class | `` | Whole graph. ``meta`` carries build-time provenance. | lib:noctusai_lib | 12 |
| `Node` | class | `` | One graph node. ``id`` is stable across rebuilds. | lib:noctusai_lib | 9 |
| `NodeKind` | class | `` | Node taxonomy. Open — extend when a new instance doesn't fit. | lib:noctusai_lib | 10 |

### `noctusai_lib.graph.serialize`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `write_graph_html` | def | `(graph: Graph, output_dir: Path) -> Path` | Write the interactive ``graph.html``. Inlines graph.json for file:// loads. | — | 0 |
| `write_graph_json` | def | `(graph: Graph, output_dir: Path) -> Path` | Write ``graph.json`` into ``output_dir``. Returns the path. | — | 0 |
| `write_graph_report` | def | `(graph: Graph, output_dir: Path) -> Path` | Write a plain-text REPORT.md summary. | — | 0 |

### `noctusai_lib.integrations.credential_resolvers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CALENDAR_PROVIDER` | const | `` |  | social-wiring | 2 |
| `CredentialStoreCalendarResolver` | class | `` | Satisfies `CalendarCredentialResolver` from a `CredentialStore`. | lib:noctusai_lib, social-wiring | 2 |
| `CredentialStoreDriveResolver` | class | `` | Build `google.oauth2.credentials.Credentials` for the seed | social-wiring | 1 |
| `CredentialStoreMetaResolver` | class | `` | Satisfies `MetaCredentialResolver` from a `CredentialStore`. | lib:noctusai_lib | 1 |
| `DRIVE_PROVIDER` | const | `` |  | — | 0 |
| `META_PROVIDER` | const | `` |  | social-wiring | 1 |
| `make_token_persisting_callback` | def | `(store: CredentialStore, *, org_id_from_state: Callable[[str…` | Build an `oauth_router(on_callback=)` hook that persists tokens. | — | 0 |

### `noctusai_lib.integrations.database`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `force_postgrest_http1` | def | `(client: Client) -> Client` | Replace PostgREST's HTTP/2 session with an HTTP/1.1 one. | — | 0 |
| `make_supabase_client` | def | `(url: str, anon_key: str, service_role_key: str, schema: Opt…` | Create a Supabase client with the given configuration. | lib:noctusai_lib, lib:noctusai_seed | 2 |

### `noctusai_lib.integrations.documents.abnt`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `UnsupportedGlyphError` | class | `` | `render_abnt_pdf` found a character the core Times font's | lib:noctusai_lib, social-wiring | 6 |
| `clip_ranges` | def | `(ranges: Sequence[FormatRange], start: int, end: int) -> lis…` | `ranges` overlapping `[start, end)`, clipped to it and re-based to | social-wiring | 2 |
| `paragraphs_from_docx` | def | `(docx: bytes, *, classify: Optional[Callable[[str, str], Par…` | A `.docx`'s paragraphs → `Paragraph`s. `classify(style_name, text)` | lib:noctusai_lib, social-wiring | 2 |
| `paragraphs_from_text` | def | `(text: str, formatting: Sequence[FormatRange]=(), *, kind: P…` | `text` (plain, as `Transcription.text`/`.formatting` produce it) → | lib:noctusai_lib, social-wiring | 4 |
| `render_abnt_pdf` | def | `(doc: FormattedDocument) -> bytes` | `FormattedDocument` → ABNT-formatted (NBR 14724) PDF bytes, via | lib:noctusai_lib, social-wiring | 4 |
| `render_word_html` | def | `(doc: FormattedDocument) -> str` | `FormattedDocument` → a self-contained HTML fragment, inline | lib:noctusai_lib, social-wiring | 3 |
| `runs_from_ranges` | def | `(paragraph_text: str, ranges: Sequence[FormatRange]) -> tupl…` | Split `paragraph_text` into `Run`s at every `FormatRange` boundary. | social-wiring | 1 |

### `noctusai_lib.integrations.documents.birthdate`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MAX_AGE` | const | `` |  | — | 0 |
| `MIN_AGE` | const | `` |  | — | 0 |
| `find_birthdate` | def | `(text: str, *, today: Optional[date]=None) -> tuple[Optional…` | Extract a birthdate. | lib:noctusai_lib | 2 |
| `normalize` | def | `(text: str) -> str` | Uppercase, strip accents, collapse whitespace. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.documents.civil_status`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `find_data_casamento` | def | `(text: str, *, today: Optional[date]=None) -> tuple[Optional…` | Extract the marriage CELEBRATION date off a certidão de casamento. | lib:noctusai_lib | 2 |
| `find_data_emissao` | def | `(text: str, *, today: Optional[date]=None) -> tuple[Optional…` | Extract the certidão's OWN issuance date — when the cartório closed | lib:noctusai_lib | 2 |
| `find_estado_civil` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract the holder's marital status. | lib:noctusai_lib | 2 |
| `find_regime_bens` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract the marital property regime. | lib:noctusai_lib | 2 |
| `normalize` | def | `(text: str) -> str` | Upper-case, accent-stripped, whitespace-collapsed. As every sibling | — | 0 |

### `noctusai_lib.integrations.documents.cnpj`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `format_cnpj` | def | `(value: Optional[str]) -> Optional[str]` | `11222333000181` → `11.222.333/0001-81`. None when it is not fourteen | — | 0 |
| `is_valid` | def | `(value: Optional[str]) -> bool` | Do this CNPJ's two check digits verify? Accepts numeric and | — | 0 |
| `normalize` | def | `(value: Optional[str]) -> str` | Uppercased, with the usual punctuation (`.`, `/`, `-`, spaces) removed. | — | 0 |

### `noctusai_lib.integrations.documents.cpf`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `find_cpf` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract the holder's CPF. | lib:noctusai_lib | 2 |
| `format_cpf` | def | `(value: str) -> Optional[str]` | `41295423898` → `412.954.238-98`. None when it is not eleven digits. | lib:noctusai_lib, social-wiring | 3 |
| `is_valid` | def | `(value: str) -> bool` | Do this CPF's two check digits verify? | lib:noctusai_lib, social-wiring | 3 |
| `normalize` | def | `(text: str) -> str` | Upper-case, accent-stripped, whitespace-collapsed. | — | 0 |
| `only_digits` | def | `(value: str) -> str` | The eleven digits, whatever punctuation they arrived in. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.documents.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_identity_extractor` | def | `(*, real: bool=False, org_id: Optional[str]=None, document_p…` | Return an identity extractor. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.documents.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeIdentityExtractor` | class | `` | Returns a canned result, honouring the Protocol exactly. | lib:noctusai_lib, social-wiring | 4 |
| `classify_kind` | def | `(mimetype: Optional[str]=None, filename: Optional[str]=None)…` | Best-effort document kind from the filename. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.documents.formatting`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FormatRange` | class | `` | Bold and/or underline over `text[start:end]` of the owning text. | lib:noctusai_lib, social-wiring | 9 |
| `FormattedDocument` | class | `` |  | lib:noctusai_lib, social-wiring | 6 |
| `Paragraph` | class | `` |  | lib:noctusai_lib, social-wiring | 4 |
| `ParagraphKind` | class | `` | The ABNT role of a paragraph. The renderer, not the source document, | lib:noctusai_lib, social-wiring | 5 |
| `Run` | class | `` | A stretch of text with one formatting. May contain `\n` (a line | lib:noctusai_lib, social-wiring | 7 |
| `ranges_from_json` | def | `(data: Optional[Iterable[dict[str, Any]]]) -> tuple[FormatRa…` | Inverse of `ranges_to_json`. `None` (a row written before formatting | lib:noctusai_lib, social-wiring | 7 |
| `ranges_to_json` | def | `(ranges: Iterable[FormatRange]) -> list[dict[str, Any]]` | The persisted form (a `jsonb` array), ordered by `start` then `end`. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.integrations.documents.gender`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FEMININO` | const | `` |  | — | 0 |
| `MASCULINO` | const | `` |  | — | 0 |
| `find_gender` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract the holder's sex. | lib:noctusai_lib | 2 |
| `normalize` | def | `(text: str) -> str` | Upper-case, accent-stripped, whitespace-collapsed. | — | 0 |

### `noctusai_lib.integrations.documents.labels`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Achado` | class | `` | The label bound to one value, and what it means for confidence. | lib:noctusai_lib | 4 |
| `LABEL_WINDOW` | const | `` |  | — | 0 |
| `label_before` | def | `(haystack: str, at: int, *, labels: Sequence[str], blocos: S…` | Classify the value found at `at` by the labels preceding it. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.documents.ladder`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DocumentTextLadder` | class | `` | Cheapest-rung text extraction, shared by every document extractor. | lib:noctusai_lib | 3 |
| `looks_like_pdf` | def | `(mimetype: Optional[str], filename: Optional[str]) -> bool` | Is this worth trying the text-layer rung on? | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.documents.matricula`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `find_matricula` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract this document's própria matrícula number. | lib:noctusai_lib | 2 |
| `normalize` | def | `(text: str) -> str` | Upper-case, accent-stripped, whitespace-collapsed. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.documents.matricula_ato_detalhes`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ALTA` | const | `` |  | social-wiring | 1 |
| `AtoDetalhes` | class | `` | Typed details of one act. See the module docstring for the contract. | lib:noctusai_lib, social-wiring | 2 |
| `AtoReferido` | class | `` | An earlier act this act cites (`cancelamento do R-3`). | lib:noctusai_lib | 1 |
| `BAIXA` | const | `` |  | — | 0 |
| `Instrumento` | class | `` | The document the act registers (`Escritura Pública de Venda e Compra`, | lib:noctusai_lib, social-wiring | 2 |
| `NENHUMA` | const | `` |  | social-wiring | 1 |
| `Parte` | class | `` | A party to an act. `nome` is a literal substring; `cpf_cnpj` is the | lib:noctusai_lib | 1 |
| `cpf_cnpj_valido` | def | `(valor: str) -> bool` | Do the check digits of this CPF (11 digits) or CNPJ (14) verify? | lib:noctusai_lib | 1 |
| `extrair_detalhes_ato` | def | `(texto_ato: str) -> AtoDetalhes` | Read one act's details. Pure and deterministic; see module docstring. | lib:noctusai_lib, social-wiring | 2 |
| `formatar_cpf_cnpj` | def | `(valor: str) -> Optional[str]` | `12345678909` -> `123.456.789-09`; 14 digits -> `11.222.333/0001-81`. | lib:noctusai_lib, social-wiring | 2 |
| `frase_titulo_aquisitivo` | def | `(instrumento: Optional[Instrumento], *, kind: str, numero: i…` | The paraphrased título aquisitivo a contract states, built ONLY from | lib:noctusai_lib, social-wiring | 2 |
| `parse_detalhes_json` | def | `(data: dict[str, Any]) -> AtoDetalhes` | Inverse of `AtoDetalhes.to_json` — for a caller holding stored rows. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.documents.matricula_atos`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MatriculaAto` | class | `` | One act of a matrícula, as offsets into the transcription. | lib:noctusai_lib, social-wiring | 2 |
| `ato_hint_span` | def | `(text: str, ato: MatriculaAto) -> tuple[int, int]` | Offsets of the act's first non-blank line, trimmed — a label for the | lib:noctusai_lib, social-wiring | 2 |
| `normalized_with_offsets` | def | `(text: str) -> tuple[str, list[int]]` | Per-char normalised text plus, for each normalised char, the offset of | lib:noctusai_lib | 1 |
| `segment_matricula_atos` | def | `(text: str) -> list[MatriculaAto]` | Split a literal matrícula transcription into ordered acts. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.documents.matricula_extractor`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeMatriculaExtractor` | class | `` | Deterministic extractor — the dev/test default. | lib:noctusai_lib, social-wiring | 3 |
| `LadderMatriculaExtractor` | class | `` | Text-layer-first, vision-second matrícula reader. | — | 0 |
| `MatriculaExtractor` | class | `` | Bytes + mimetype → the property's registry number. | lib:noctusai_lib, social-wiring | 2 |
| `MatriculaFields` | class | `` | What one certidão de matrícula yielded. | lib:noctusai_lib, social-wiring | 2 |
| `make_matricula_extractor` | def | `(*, real: bool=False, org_id: Optional[str]=None, document_p…` | Return a matrícula extractor. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.documents.name`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MAX_NAME_LEN` | const | `` |  | — | 0 |
| `MAX_WORDS` | const | `` |  | — | 0 |
| `MIN_NAME_LEN` | const | `` |  | — | 0 |
| `MIN_WORDS` | const | `` |  | — | 0 |
| `find_name` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract the document holder's full name. | lib:noctusai_lib | 2 |
| `looks_like_a_name` | def | `(candidate: str) -> bool` | Structural plausibility for a Brazilian personal name. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.documents.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LadderIdentityExtractor` | class | `` | Text-layer-first, vision-second identity extractor. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.documents.rg`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `find_rg` | def | `(text: str) -> tuple[Optional[str], str, Optional[str]]` | Extract the holder's RG number. | lib:noctusai_lib | 2 |
| `find_rg_orgao` | def | `(text: str) -> tuple[Optional[str], str]` | Extract the issuing body and UF — `SSP/SP`. | lib:noctusai_lib | 2 |
| `is_same_as_cpf` | def | `(rg: Optional[str], cpf: Optional[str]) -> bool` | Does this RG collapse onto this CPF once punctuation is dropped? | lib:noctusai_lib, social-wiring | 4 |
| `normalize` | def | `(text: str) -> str` | Upper-case, accent-stripped, whitespace-collapsed. As the siblings do. | — | 0 |
| `only_alnum` | def | `(value: str) -> str` | Digits and letters, punctuation dropped, upper-cased. | — | 0 |

### `noctusai_lib.integrations.documents.text`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `normalize_lines` | def | `(text: str) -> list[str]` | Normalised, non-empty lines with intra-line whitespace collapsed. | lib:noctusai_lib | 2 |
| `strip_accents_upper` | def | `(text: str) -> str` | NFKD-decompose, drop combining marks, uppercase. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.integrations.documents.transcription`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_VISION_PROVIDER` | const | `` |  | — | 0 |
| `DocumentTranscriber` | class | `` | Bytes → the document's full text. Never raises. | lib:noctusai_lib, social-wiring | 2 |
| `FakeDocumentTranscriber` | class | `` | Deterministic transcriber — the dev/test default. | lib:noctusai_lib | 1 |
| `LadderDocumentTranscriber` | class | `` | Text-layer-first, vision-second, decided PER PAGE. | — | 0 |
| `MAX_VISION_PAGES` | const | `` |  | — | 0 |
| `OCR_MODEL` | const | `` |  | — | 0 |
| `OCR_PROMPT` | const | `` |  | — | 0 |
| `RENDER_DPI` | const | `` |  | — | 0 |
| `TranscribedPage` | class | `` | One page, its text, and which rung produced it. | erp-imobiliario, lib:noctusai_lib, social-wiring | 5 |
| `Transcription` | class | `` | The whole document, or a truthful account of why not. | erp-imobiliario, lib:noctusai_lib, social-wiring | 5 |
| `make_document_transcriber` | def | `(*, real: bool=False, org_id: Optional[str]=None, provider: …` | Return a document transcriber. | erp-imobiliario, lib:noctusai_lib, social-wiring | 6 |
| `parse_markup` | def | `(markup: str) -> tuple[str, tuple[FormatRange, ...]]` | OCR markup (`**bold**`, `<u>underline</u>`, combined/nested freely) → | — | 0 |

### `noctusai_lib.integrations.documents.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ExtractionConfidence` | class | `` | How much the caller may trust a extracted field. | lib:noctusai_lib, social-wiring | 7 |
| `IdentityDocumentKind` | class | `` | Classified identity-document category. | lib:noctusai_lib | 2 |
| `IdentityExtractor` | class | `` | Bytes + mimetype → typed identity fields. | lib:noctusai_lib, social-wiring | 3 |
| `IdentityFields` | class | `` | Typed fields lifted from one identity document. | lib:noctusai_lib, social-wiring | 6 |
| `TextSource` | class | `` | Which rung of the extraction ladder produced the text. | erp-imobiliario, lib:noctusai_lib, social-wiring | 13 |

### `noctusai_lib.integrations.docx_render.docxtpl_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DocxtplRenderAdapter` | class | `` | Real DOCX template render adapter via `docxtpl` (Jinja-in-Word). | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.docx_render.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeDocxRenderAdapter` | class | `` | Deterministic in-memory DOCX render adapter. | lib:noctusai_lib | 1 |
| `FakeRichText` | class | `` | Fake-parity `rich_text()` return value — never imports `docxtpl`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.docx_render.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DocxRenderAdapter` | class | `` | DOCX-template render adapter contract. Both `FakeDocxRenderAdapter` | lib:noctusai_lib, social-wiring | 5 |
| `DocxRenderError` | class | `` | Base class for every error `docx_render` raises. | lib:noctusai_lib | 1 |
| `MissingPlaceholderError` | class | `` | A template variable was referenced by the template but absent from | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.email.digest`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Digest` | class | `` | The pre-rendered digest. Caller produces this from its domain data | core, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, social-wiring | 11 |
| `DigestSendResult` | class | `` | Outcome of `send_digest`. Always returned (never raises). | core, daily-life, lib:noctusai_lib, personal-finance | 4 |
| `render` | def | `(*, html_template: str, text_template: str, context: dict[st…` | Render `(html, text)` digest bodies from Jinja templates. | erp-imobiliario, lib:noctusai_lib | 2 |
| `send_digest` | async def | `(digest: Digest, *, recipient: str, org_id: Optional[str]=No…` | Send a pre-rendered digest via the org's configured backend, with | erp-imobiliario, lib:noctusai_lib | 2 |
| `send_to_many` | async def | `(digest: Digest, *, recipients: Sequence[dict[str, Any]], or…` | Send a digest to multiple recipients and return an aggregated dict. | — | 0 |
| `send_to_one` | async def | `(digest: Digest, *, recipient: str, org_id: Optional[str]=No…` | Send a digest to one recipient and return the standard endpoint dict. | — | 0 |

### `noctusai_lib.integrations.email.templates`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `send_password_reset_email` | def | `(to: str, product_name: str, reset_url: str) -> bool` | Send a password reset email with product branding. | — | 0 |
| `send_product_invitation_email` | def | `(to: str, product_name: str, org_name: str, role_label: str,…` | Send a product-level team invitation email. | lib:noctusai_seed, therapy-platform | 2 |

### `noctusai_lib.integrations.fx.bcb_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BcbPtaxAdapter` | class | `` | Real BCB Olinda PTAX adapter. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.fx.errors`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FxBulletinNotFoundError` | class | `` | No BCB PTAX fechamento bulletin was published within the lookback | lib:noctusai_lib | 3 |
| `FxError` | class | `` | Base for every FX/PTAX integration failure. | lib:noctusai_lib | 2 |
| `FxUpstreamError` | class | `` | BCB Olinda was unreachable, answered non-2xx, returned a non-JSON | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.fx.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeFxRateAdapter` | class | `` | In-memory PTAX fake. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.fx.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `format_bcb_date` | def | `(quote_date: date) -> str` | BCB Olinda's OData functions take dates as `MM-DD-YYYY` strings | lib:noctusai_lib | 2 |
| `parse_ptax_response` | def | `(payload: dict[str, Any]) -> PtaxRate | None` | Parse the OData JSON body of `CotacaoDolarPeriodo`/`CotacaoDolarDia`. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.fx.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FxRateAdapter` | class | `` | Surface every FX-rate connector implements. Both `FakeFxRateAdapter` | lib:noctusai_lib | 2 |
| `PtaxRate` | class | `` | One published BCB PTAX venda (sell) rate, fechamento (closing) bulletin. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.gmail.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GmailCredentialResolver` | class | `` | Product-injected per-tenant credential lookup. | lib:noctusai_lib | 1 |
| `OAuthGmailCredentials` | class | `` | OAuth user-delegated Gmail credentials. `refresh_token` MUST be | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.gmail.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_gmail_client` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Build a `GmailClient`. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.gmail.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeGmailClient` | class | `` | Deterministic in-memory `GmailClient` implementation. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.gmail.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GmailClient` | class | `` | Gmail API v1 client contract. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.gmail.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealGmailClient` | class | `` | Real Gmail API v1 client. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.gmail.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GMAIL_MODIFY_SCOPE` | const | `` |  | lib:noctusai_lib | 1 |
| `GMAIL_READONLY_SCOPE` | const | `` |  | lib:noctusai_lib, social-wiring | 2 |
| `GMAIL_SEND_SCOPE` | const | `` |  | lib:noctusai_lib, social-wiring | 4 |
| `GmailLabel` | class | `` | Gmail label — minimal projection of `users.labels.list`. | lib:noctusai_lib | 1 |
| `GmailListResult` | class | `` | Paginated list response. | lib:noctusai_lib | 4 |
| `GmailMessage` | class | `` | Gmail message — flattened projection of `users.messages.get`. | lib:noctusai_lib | 4 |
| `SUBJECT_MAX_LEN` | const | `` |  | lib:noctusai_lib | 3 |
| `SendResult` | class | `` | Result of `users.messages.send`. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.google_calendar.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CalendarCredentialResolver` | class | `` | Product-injected per-tenant credential lookup. | lib:noctusai_lib | 3 |
| `OAuthCalendarCredentials` | class | `` | OAuth user-delegated credentials. `refresh_token` MUST be | lib:noctusai_lib, therapy-platform | 5 |
| `ServiceAccountCalendarCredentials` | class | `` | Service-account credentials. `info` is the JSON keyfile dict | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.google_calendar.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeCalendarAdapter` | class | `` | In-memory fake. Use it for local development and tests until | lib:noctusai_lib, orbity, social-wiring, therapy-platform | 8 |

### `noctusai_lib.integrations.google_calendar.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `event_to_google_body` | def | `(event: EventInput) -> dict[str, Any]` |  | lib:noctusai_lib, social-wiring | 5 |
| `google_body_to_created_event` | def | `(body: dict[str, Any]) -> CreatedEvent` |  | lib:noctusai_lib, social-wiring | 5 |
| `parse_google_datetime` | def | `(value: str) -> datetime` |  | lib:noctusai_lib, social-wiring, therapy-platform | 4 |

### `noctusai_lib.integrations.google_calendar.oauth_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoogleCalendarOAuthAdapter` | class | `` | OAuth user-delegated Google Calendar adapter. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.google_calendar.service_account_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoogleCalendarServiceAccountAdapter` | class | `` | Service-account-backed Google Calendar adapter. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.google_calendar.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CalendarAdapter` | class | `` | Calendar adapter contract. Concrete implementations: | lib:noctusai_lib, orbity, social-wiring, therapy-platform | 5 |
| `CreatedEvent` | class | `` |  | lib:noctusai_lib, social-wiring | 6 |
| `EventAttendee` | class | `` |  | lib:noctusai_lib, social-wiring, therapy-platform | 3 |
| `EventInput` | class | `` | Calendar event payload. | lib:noctusai_lib, orbity, social-wiring, therapy-platform | 10 |

### `noctusai_lib.integrations.google_drive.content_stats`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `compute_content_stats` | def | `(text: str, *, rendered_as: str) -> dict` | Compute deterministic aggregates over text content. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.google_drive.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_drive_downloader` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Build a `DriveDownloader`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeDriveDownloader` | class | `` | Deterministic in-memory `DriveDownloader` implementation. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.google_drive.fake_reader`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeDriveReader` | class | `` | Deterministic in-memory `DriveReader`. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.google_drive.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `parse_drive_url` | def | `(url_or_id: str) -> str` | Extract a file id from a Drive URL or accept a bare id. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DriveDownloader` | class | `` | Google Drive v3 download contract. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.google_drive.reader_factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_drive_reader` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Build a `DriveReader`. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.google_drive.reader_types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DriveFileContent` | class | `` | The content of a Drive file as exported/streamed bytes. | lib:noctusai_lib, social-wiring | 5 |
| `DriveReader` | class | `` | Drive v3 read/inspection contract. | lib:noctusai_lib | 3 |
| `DriveSearchHit` | class | `` | One result row from a Drive search / list call. | lib:noctusai_lib, social-wiring | 5 |
| `DriveSearchResult` | class | `` |  | lib:noctusai_lib, social-wiring | 5 |
| `FOLDER_MIME` | const | `` |  | lib:noctusai_lib | 1 |
| `RENDERED_AS_BINARY` | const | `` |  | lib:noctusai_lib | 1 |
| `RENDERED_AS_CANONICAL` | const | `` |  | lib:noctusai_lib | 1 |
| `RENDERED_AS_CSV` | const | `` |  | lib:noctusai_lib | 1 |
| `RENDERED_AS_PASSTHROUGH` | const | `` |  | lib:noctusai_lib | 1 |
| `RENDERED_AS_PDF_TEXT` | const | `` |  | lib:noctusai_lib | 1 |
| `RENDERED_AS_TEXT` | const | `` |  | lib:noctusai_lib | 1 |
| `translate_rendered_as` | def | `(label: str, *, to: str='canonical') -> str` | Translate a `rendered_as` label between vocabularies. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.integrations.google_drive.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealDriveDownloader` | class | `` | googleapiclient-backed `DriveDownloader`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.real_reader`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealDriveReader` | class | `` | googleapiclient-backed `DriveReader`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.sync_facade`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SyncDriveReader` | class | `` | Sync wrapper over a `DriveReader`. | lib:noctusai_lib, social-wiring | 2 |
| `make_sync_drive_reader` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Convenience factory — `make_drive_reader(...)` + sync wrap. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.google_drive.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DriveFile` | class | `` | A Google Drive file's metadata projection. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.google_maps.google_maps_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoogleMapsRoutingAdapter` | class | `` | Google Maps Routes API adapter (v2:computeRoutes). | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.google_maps.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_routes_request` | def | `(origin: Coordinates, destination: Coordinates) -> dict[str,…` |  | lib:noctusai_lib, social-wiring | 3 |
| `parse_routes_response` | def | `(response: dict[str, Any]) -> TravelEstimate` |  | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.google_maps.static_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StaticRoutingAdapter` | class | `` | Returns `default_minutes` for any pair of distinct coordinates, | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.google_maps.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Coordinates` | class | `` |  | lib:noctusai_lib, social-wiring | 5 |
| `RoutingAdapter` | class | `` | Travel-estimate contract between two coordinates. Implementations | lib:noctusai_lib, social-wiring | 2 |
| `TravelEstimate` | class | `` |  | lib:noctusai_lib, social-wiring | 5 |

### `noctusai_lib.integrations.google_scopes`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GOOGLE_TOKENINFO_URL` | const | `` |  | — | 0 |
| `diagnose_consent_screen_gaps` | def | `(requested: list[str], granted: list[str]) -> dict` | Set-diff requested vs granted → operator-facing coverage report. | lib:noctusai_lib | 2 |
| `discover_granted_scopes` | def | `(access_token: str, *, http_client: httpx.Client | None=None…` | Probe Google's `oauth2/v3/tokeninfo` for the *actually-granted* | lib:noctusai_lib | 2 |
| `format_scopes_for_authorize` | def | `(scopes: list[str]) -> str` | Join scopes with single spaces — Google's authorize-endpoint | — | 0 |
| `resolve_google_scopes` | def | `(configured: str | None, *, kitchen_sink: list[str] | None=N…` | Resolve the configured scope env value to a concrete scope list. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.google_scopes_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `google_scopes_router` | def | `(*, configured_scopes: ConfiguredScopesProvider, access_toke…` | Build the `/api/google/scopes` introspection router. | — | 0 |

### `noctusai_lib.integrations.image_edit.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ImageEditContentPolicyViolation` | class | `` | OpenAI rejected the request or output on content-policy grounds. | lib:noctusai_lib | 2 |
| `ImageEditError` | class | `` | Base class for every `image_edit` adapter error. | lib:noctusai_lib | 2 |
| `ImageEditFatalError` | class | `` | Content-policy rejection, invalid size/shape, or a configuration | lib:noctusai_lib | 2 |
| `ImageEditInvalidSize` | class | `` | The requested/output size violates the provider's size contract. | lib:noctusai_lib | 2 |
| `ImageEditNotConfigured` | class | `` | The resolved API key for the requested provider is empty/missing. | lib:noctusai_lib | 3 |
| `ImageEditRateLimited` | class | `` | 429 — safe to retry with backoff. | lib:noctusai_lib | 2 |
| `ImageEditRetryableError` | class | `` | 429 / 5xx / timeout / connection failure — safe to retry per | lib:noctusai_lib | 1 |
| `ImageEditServerError` | class | `` | 5xx from the provider — safe to retry with backoff. | lib:noctusai_lib | 2 |
| `ImageEditTimeout` | class | `` | Request timed out / connection failed before a response arrived — | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.image_edit.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeImageEditAdapter` | class | `` | Deterministic in-memory image-edit adapter. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.image_edit.openai_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OpenAIImageEditAdapter` | class | `` | Real OpenAI image-edit adapter (`images.edit`). | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.image_edit.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EditedImage` | class | `` | One output image. ``format`` is whatever the provider actually | lib:noctusai_lib | 3 |
| `ImageEditAdapter` | class | `` | Image-edit adapter contract. Concrete implementations: | lib:noctusai_lib | 2 |
| `ImageEditCapabilities` | class | `` | Static per-model capability flags, driven ENTIRELY by the | lib:noctusai_lib | 3 |
| `ImageEditRequest` | class | `` | Image-edit request payload. | lib:noctusai_lib | 4 |
| `ImageEditResult` | class | `` | Result of ``ImageEditAdapter.edit``. | lib:noctusai_lib | 3 |
| `ImageEditUsage` | class | `` | Token accounting for one edit call — the SAME 4-field shape | lib:noctusai_lib | 3 |
| `capabilities_for_model` | def | `(model: str) -> ImageEditCapabilities` | Catalog-driven capability lookup — the ONLY implementation of | lib:noctusai_lib | 5 |

### `noctusai_lib.integrations.image_gen.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeImageGenAdapter` | class | `` | Deterministic in-memory image-gen adapter. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.image_gen.gemini_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GeminiImageGenAdapter` | class | `` | Real Gemini image-gen adapter. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.image_gen.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GeneratedImage` | class | `` |  | lib:noctusai_lib | 3 |
| `ImageGenAdapter` | class | `` | Image-generation adapter contract. Concrete implementations: | lib:noctusai_lib, social-wiring | 2 |
| `ImagePromptInput` | class | `` | Image-generation request payload. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.integrations.imaging.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeImagingAdapter` | class | `` | Deterministic in-memory imaging adapter — no Pillow work. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.imaging.real_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealImagingAdapter` | class | `` | Real imaging adapter backed by Pillow + pillow-heif. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.imaging.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_JPEG_QUALITY` | const | `` |  | lib:noctusai_lib | 2 |
| `DEFAULT_WATERMARK_TEXT` | const | `` |  | lib:noctusai_lib | 4 |
| `ImagingAdapter` | class | `` | Real-estate photo imaging adapter contract. Concrete | lib:noctusai_lib | 2 |
| `NormalizedImage` | class | `` | Result of `ImagingAdapter.normalize_for_edit`. | lib:noctusai_lib | 3 |
| `UnsupportedImageFormatError` | class | `` | Raised when input bytes cannot be decoded as an image, or a | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.imovelweb.auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AccessToken` | class | `` |  | — | 0 |
| `ImovelWebAuth` | class | `` | Fetches and caches the application token. | lib:noctusai_lib | 1 |
| `InMemoryTokenCache` | class | `` | Process-local cache. Keyed by `(base_url, client_id)` so a sandbox | — | 0 |
| `LOGIN_PATH` | const | `` |  | — | 0 |
| `LOGOUT_PATH` | const | `` |  | — | 0 |
| `REFRESH_SKEW_SECONDS` | const | `` |  | — | 0 |
| `TokenCache` | class | `` |  | — | 0 |
| `parse_expiry` | def | `(payload: dict[str, Any]) -> Optional[datetime]` | `OAuth2AccessToken` → an absolute UTC expiry, or `None`. | — | 0 |
| `token_from_payload` | def | `(payload: dict[str, Any]) -> AccessToken` | `OAuth2AccessToken` JSON → our value object. | — | 0 |

### `noctusai_lib.integrations.imovelweb.contract`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FieldSpec` | class | `` | One documented field of a callback body, for one language. | — | 0 |
| `contract_summary` | def | `(language: Optional[str]=None) -> dict[str, Any]` | What an agent should see before trusting anything here. | — | 0 |
| `diff_observed` | def | `(bodies: list[dict[str, Any]], *, language: str='EN2') -> di…` | Compare captured live bodies against the transcribed contract. | — | 0 |
| `has_blocking_violation` | def | `(result: dict[str, list[str]]) -> bool` |  | — | 0 |
| `imovelweb_json_schema` | def | `(language: str='EN2') -> dict[str, Any]` | JSON Schema for one language's body. | — | 0 |
| `validate_imovelweb_payload` | def | `(payload: Any, *, language: str='EN2') -> dict[str, list[str…` | Split complaints into blocking `error`s and non-blocking `warning`s. | — | 0 |

### `noctusai_lib.integrations.imovelweb.endpoints`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ENDPOINT_ABSENT` | const | `` |  | — | 0 |
| `ENDPOINT_INBOUND` | const | `` |  | — | 0 |
| `ENDPOINT_LIVE` | const | `` |  | — | 0 |
| `ENDPOINT_PERMISSION_GATED` | const | `` |  | — | 0 |
| `ENDPOINT_UNVERIFIED` | const | `` |  | — | 0 |
| `ENDPOINT_WRITE_ONLY` | const | `` |  | — | 0 |
| `IMOVELWEB_PROD_AR` | const | `` |  | — | 0 |
| `IMOVELWEB_PROD_BR` | const | `` |  | — | 0 |
| `IMOVELWEB_PROD_RELA` | const | `` |  | — | 0 |
| `IMOVELWEB_SANDBOX_BR` | const | `` |  | lib:noctusai_lib | 2 |
| `IMOVELWEB_SANDBOX_WINDOW` | const | `` |  | lib:noctusai_lib | 2 |
| `IMOVELWEB_SWAGGER_PATH` | const | `` |  | — | 0 |
| `base_url` | def | `(region: str='br', *, sandbox: bool=False) -> str` | Resolve a host. Raises rather than silently falling back to prod — | lib:noctusai_lib | 1 |
| `is_sandbox_host` | def | `(url: Optional[str]) -> bool` | True only for a known sandbox host. | lib:noctusai_lib | 2 |
| `preferred_path` | def | `(key: str) -> str` | The spelling to try first — the generated spec's. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.imovelweb.errors`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ImovelWebConfigError` | class | `` | We are not configured to talk to ImovelWeb. | lib:noctusai_lib | 3 |
| `ImovelWebError` | class | `` | Base for every ImovelWeb connector failure. | — | 0 |
| `ImovelWebUpstreamError` | class | `` | ImovelWeb returned an error, or was unreachable. | lib:noctusai_lib | 2 |
| `SECRET_REDACTION_PLACEHOLDER` | const | `` |  | — | 0 |
| `redact_secrets` | def | `(text: Optional[str], *secrets: Optional[str]) -> Optional[s…` | Strip every supplied secret out of `text`. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.imovelweb.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_imovelweb_client` | def | `(*, use_fake: bool=False, client_id: Optional[str]=None, cli…` | Build an OpenNavent client. | — | 0 |

### `noctusai_lib.integrations.imovelweb.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeImovelWebClient` | class | `` | In-memory adapter for tests and for driving a receiver locally. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.imovelweb.normalizers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `IMOVELWEB_DEFAULT_SOURCE_SLUG` | const | `` |  | — | 0 |
| `IMOVELWEB_PIPE` | const | `` |  | — | 0 |
| `imovelweb_lead_to_lead_payload` | def | `(lead: ImovelWebLead, *, origem_source_id: str, external_sou…` | One `ImovelWebLead` → the payload a product's `create_lead` expects. | — | 0 |
| `imovelweb_timestamp_to_date` | def | `(value: Any) -> Optional[date]` | Vendor timestamp → its LOCAL date; `None` when unparseable. | — | 0 |
| `render_observacoes` | def | `(lead: ImovelWebLead) -> Optional[str]` | The qualifying context, one `label: value` line each. | — | 0 |
| `resolve_source_slug` | def | `(lead_origin: Optional[str]) -> str` | `leadOrigin` → the `lead_sources` slug to attribute the lead to. | — | 0 |

### `noctusai_lib.integrations.imovelweb.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ImovelWebAdapter` | class | `` | OpenNavent client. Every method may raise `ImovelWebConfigError` | — | 0 |

### `noctusai_lib.integrations.imovelweb.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `ImovelWebClient` | class | `` | Real `ImovelWebAdapter`. | lib:noctusai_lib | 1 |
| `RATE_LIMIT_BUCKET` | const | `` |  | — | 0 |
| `describe_error_body` | def | `(response: Any) -> str` | Best-effort human description of a failed response. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.imovelweb.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CallbackConfig` | class | `` | The callback registration — `ConfiguracionCallback` on the wire. | lib:noctusai_lib | 3 |
| `IMOVELWEB_BASIC_USERNAME` | const | `` |  | — | 0 |
| `ImovelWebLead` | class | `` | One lead event as delivered by the ImovelWeb callback. | lib:noctusai_lib | 2 |
| `basic_credential` | def | `(secret: str, *, username: str=IMOVELWEB_BASIC_USERNAME) -> …` | Build the `authorizationHeaderValue` we register with the vendor. | — | 0 |
| `receiver_url_problems` | def | `(url: Optional[str]) -> tuple[str, ...]` | Reasons this URL must not be registered with the live vendor. | — | 0 |

### `noctusai_lib.integrations.imovelweb.webhook`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `detect_callback_language` | def | `(payload: Any) -> Optional[str]` | Guess which `lenguajeCallbackBody` a body was rendered in. | — | 0 |
| `parse_imovelweb_callback` | def | `(payload: Any, *, language: Optional[str]=None) -> Optional[…` | Parse a delivery into an `ImovelWebLead`, or `None` if unstorable. | — | 0 |

### `noctusai_lib.integrations.llm.audio`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `transcribe_audio` | async def | `(audio: bytes, *, model: Optional[str]=None, provider: Optio…` | Transcribe audio bytes to text via the configured provider. | — | 0 |

### `noctusai_lib.integrations.llm.backends.redis_backend`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RedisCacheBackend` | class | `` | `redis.asyncio`-backed cache for `noctusai_lib.llm.chat_completion`. | — | 0 |

### `noctusai_lib.integrations.llm.budget`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `compute_spend_usd` | async def | `(org_id: str, *, start_iso: Optional[str]=None, end_iso: Opt…` | Sum `cost_estimate_usd` across every product's `llm_usage` table for | — | 0 |
| `compute_status` | async def | `(org_id: str) -> dict[str, Any]` | Return `{spent_brl, budget_brl, used_pct, status, soft_pct, hard_pct}`. | core | 1 |
| `configure_budget_module` | def | `(*, admin_client_factory: Optional[Callable[[], Any]]) -> No…` | Wire the admin client factory the budget module uses for reads. | lib:noctusai_seed | 1 |
| `enforce_budget` | async def | `(org_id: Optional[str]) -> None` | Raise `LLMBudgetExceeded` if the org's hard threshold is crossed. | lib:noctusai_lib | 1 |
| `fetch_budget_brl` | async def | `(org_id: str) -> Optional[float]` | Return the org's monthly budget in BRL, or `None` when unset. | — | 0 |
| `is_configured` | def | `() -> bool` |  | — | 0 |

### `noctusai_lib.integrations.llm.cache`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CacheBackend` | class | `` | Minimal Redis-like interface we need. Production uses `redis.asyncio`; | — | 0 |
| `InMemoryCacheBackend` | class | `` | Simple dict-backed CacheBackend — for tests and dev environments | — | 0 |
| `build_cache_key` | def | `(*, product: str, provider: str, model: str, prompt_version:…` | Build a deterministic cache key from the request shape. | lib:noctusai_lib | 1 |
| `flush_for_model` | async def | `(backend: CacheBackend, *, product: str, provider: str, mode…` | Delete every cached entry for a given (product, provider, model). | core | 1 |
| `try_get` | async def | `(backend: CacheBackend, key: str) -> tuple[bool, Optional[An…` | Attempt a cache read. Returns (hit, value). Never raises — cache | lib:noctusai_lib | 1 |
| `try_set` | async def | `(backend: CacheBackend, key: str, value: Any, ttl_seconds: i…` | Attempt a cache write. Never raises — write failures are swallowed | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.llm.chat`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_cached_messages` | def | `(static_system: str, dynamic_user: str, *, provider: Optiona…` | Structure a message list for maximum prompt-cache hit rate. | — | 0 |
| `chat_completion` | async def | `(messages: list[dict], *, model: Optional[str]=None, provide…` | Route a chat completion through the configured provider. | — | 0 |
| `chat_completion_stream` | async def | `(messages: list[dict], *, model: Optional[str]=None, provide…` | Stream a chat completion as an async iterator of text deltas. | — | 0 |

### `noctusai_lib.integrations.llm.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_llm` | def | `(config: LLMConfig) -> None` | Install an LLMConfig as the process-wide active configuration. | lib:noctusai_seed | 2 |
| `get_llm_config` | def | `() -> LLMConfig` | Return the active LLMConfig. Raises if `configure_llm()` wasn't called. | lib:noctusai_lib, lib:noctusai_seed | 7 |
| `get_provider` | def | `(name: Optional[str]=None) -> LLMProvider` | Return a Provider instance by name (or the configured default). | lib:noctusai_lib | 4 |
| `resolve_api_key` | def | `(provider: str, org_id: Optional[str]=None) -> str` | Resolve an API key via the active config's key_provider. | lib:noctusai_lib | 4 |
| `shutdown_llm` | async def | `() -> None` | Close every cached provider and clear the active config. | lib:noctusai_seed | 2 |

### `noctusai_lib.integrations.llm.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMConfig` | class | `` | Product-level LLM configuration. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.llm.embeddings`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `generate_embedding` | async def | `(text: str, *, model: Optional[str]=None, provider: Optional…` | Generate an embedding vector via the configured provider. | — | 0 |
| `generate_embeddings_batch` | async def | `(texts: list[str], *, model: Optional[str]=None, provider: O…` | Generate embedding vectors for MANY texts in as few provider | — | 0 |

### `noctusai_lib.integrations.llm.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMAPIError` | class | `` | Downstream error from an LLM provider's API (rate-limit, timeout, etc.). | erp-imobiliario, lib:noctusai_lib | 6 |
| `LLMBudgetExceeded` | class | `` | The org's monthly LLM budget has been exhausted. | lib:noctusai_lib | 1 |
| `LLMNotConfigured` | class | `` | The resolved API key for the requested provider is empty/missing. | daily-life, erp-imobiliario, lib:noctusai_lib, social-wiring | 9 |
| `ProviderNotImplemented` | class | `` | A stub provider's method was called outside UI-development mode. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.llm.inputs`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `audio_bytes_to_named_buffer` | def | `(audio_bytes: bytes, filename: str) -> BytesIO` | Wrap audio bytes in a `BytesIO` with a `name` attribute, satisfying | — | 0 |
| `image_bytes_to_data_url` | def | `(image_bytes: bytes, mimetype: str) -> str` | Build a `data:` URL for OpenAI vision-input image payloads. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.llm.models`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ModelEntry` | class | `` | One row of the catalog. Immutable so it's safely shareable. | lib:noctusai_lib | 1 |
| `all_providers` | def | `() -> list[str]` | All distinct provider names present in the catalog (sorted). | core | 1 |
| `is_stub_model` | def | `(provider: str, model_id: str) -> bool` | True if the given (provider, model_id) pair is served by a stub. | — | 0 |
| `models_for` | def | `(provider: str, kind: Optional[ModelKind]=None) -> list[Mode…` | Return the catalog entries for a provider, optionally filtered by kind. | core, lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.llm.providers.anthropic_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AnthropicProvider` | class | `` | Real Anthropic provider — chat + vision via the official SDK. | — | 0 |

### `noctusai_lib.integrations.llm.providers.base`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMProvider` | class | `` | Protocol all providers implement. See module docstring for the rules. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.llm.providers.fake_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeProvider` | class | `` | Scripted test double. Not registered; tests use it via LLMConfig override. | — | 0 |

### `noctusai_lib.integrations.llm.providers.gemini_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GeminiProvider` | class | `` | Real Gemini provider — chat, embeddings, vision, audio. | — | 0 |

### `noctusai_lib.integrations.llm.providers.openai_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OpenAIProvider` | class | `` | Real OpenAI provider using the official `openai` SDK. | — | 0 |

### `noctusai_lib.integrations.llm.refusal`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `analyze_image_with_refusal_retry` | async def | `(image: Union[bytes, str], prompt: str, *, retry_prompt: Opt…` | `analyze_image` with a single broadened retry on detected refusal. | — | 0 |
| `looks_like_refusal` | def | `(text: Optional[str]) -> bool` | Heuristic: does `text` read like an LLM declining rather than answering? | — | 0 |

### `noctusai_lib.integrations.llm.registry`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_provider_class` | def | `(name: str) -> Type[LLMProvider]` | Look up a registered provider class by name. Raises KeyError if absent. | lib:noctusai_lib | 1 |
| `list_providers` | def | `() -> list[str]` | All currently registered provider names (sorted). | — | 0 |
| `register` | def | `(name: str, cls: Type[LLMProvider]) -> None` | Register a provider class under a name. | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.llm.usage`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryUsageSink` | class | `` | Dev/test sink — keeps events in a list in memory. Not thread-safe. | — | 0 |
| `SupabaseUsageSink` | class | `` | Production sink — inserts one row per `UsageEvent` into | lib:noctusai_seed | 1 |
| `UsageEvent` | class | `` | A single LLM-call usage observation. | — | 0 |
| `UsageSink` | class | `` | Where usage events get persisted. Production uses a Supabase-backed | — | 0 |
| `estimate_cost_usd` | def | `(*, provider: str, model: str, prompt_tokens: Optional[int],…` | Compute a rough cost estimate from the model catalog. | lib:noctusai_lib | 1 |
| `record_usage` | async def | `(*, provider: str, model: str, operation: str, prompt_tokens…` | Provider-side convenience — builds a `UsageEvent` and dispatches to | lib:noctusai_lib | 16 |

### `noctusai_lib.integrations.llm.vision`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `analyze_image` | async def | `(image: Union[bytes, str], prompt: str, *, model: Optional[s…` | Analyze an image against a text prompt via the configured provider. | lib:noctusai_lib | 1 |
| `analyze_images` | async def | `(images: list[Union[bytes, str]], prompt: str, *, response_s…` | Analyze MULTIPLE images together against a text prompt, constrained | — | 0 |

### `noctusai_lib.integrations.mailchimp.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `HttpxMailchimpClient` | class | `` | Real Mailchimp Marketing API v3 client backed by ``httpx.AsyncClient``. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.mailchimp.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeMailchimpClient` | class | `` | In-memory Mailchimp stand-in.  Records state in plain dicts; | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.mailchimp.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `parse_server_prefix` | def | `(api_key: str) -> str` | Extract the datacenter prefix from a Mailchimp API key. | lib:noctusai_lib | 2 |
| `raw_to_audience` | def | `(raw: dict[str, Any]) -> Audience` | Translate a Mailchimp /lists item dict into an ``Audience``. | lib:noctusai_lib | 2 |
| `raw_to_campaign` | def | `(raw: dict[str, Any]) -> Campaign` | Translate a Mailchimp /campaigns item into a ``Campaign``. | lib:noctusai_lib | 2 |
| `raw_to_member` | def | `(raw: dict[str, Any]) -> Member` | Translate a Mailchimp /lists/{id}/members item into a ``Member``. | lib:noctusai_lib | 2 |
| `raw_to_segment` | def | `(raw: dict[str, Any]) -> Segment` | Translate a Mailchimp /lists/{id}/segments item into a ``Segment``. | lib:noctusai_lib | 2 |
| `raw_to_template` | def | `(raw: dict[str, Any], *, server_prefix: str='') -> Template` | Translate a Mailchimp /templates item into a ``Template``. | lib:noctusai_lib | 2 |
| `subscriber_hash` | def | `(email: str) -> str` | Return the MD5 hex digest of the lowercase-stripped email. | lib:noctusai_lib | 3 |
| `template_edit_url` | def | `(server_prefix: str, template_id: int) -> str` | Build the Mailchimp admin deep-link to the template editor. | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.mailchimp.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Audience` | class | `` | Mailchimp audience (list) summary. | lib:noctusai_lib | 4 |
| `Campaign` | class | `` | Mailchimp campaign. | lib:noctusai_lib | 4 |
| `MailchimpAuthError` | class | `` | 401 / 403 — bad API key or insufficient permissions. | lib:noctusai_lib, social-wiring | 3 |
| `MailchimpClient` | class | `` | Async Mailchimp Marketing API v3 adapter. | lib:noctusai_lib, social-wiring | 2 |
| `MailchimpError` | class | `` | Base for all Mailchimp adapter errors. | lib:noctusai_lib, social-wiring | 3 |
| `MailchimpNotFoundError` | class | `` | 404 — resource does not exist. | lib:noctusai_lib, social-wiring | 4 |
| `MailchimpRateLimitedError` | class | `` | 429 — request rate exceeded. | lib:noctusai_lib, social-wiring | 3 |
| `MailchimpRejectedError` | class | `` | 400 / 422 — Mailchimp rejected the payload (validation failure). | lib:noctusai_lib, social-wiring | 4 |
| `MailchimpUnreachableError` | class | `` | Network / TLS / 5xx — transient infrastructure failure. | lib:noctusai_lib, social-wiring | 3 |
| `Member` | class | `` | Mailchimp audience member. | lib:noctusai_lib | 4 |
| `Page` | class | `` | Thin wrapper around a paginated Mailchimp list response. | lib:noctusai_lib | 3 |
| `Segment` | class | `` | Mailchimp static segment (saved segment). | lib:noctusai_lib | 4 |
| `Template` | class | `` | Mailchimp template. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.media.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeMediaResolver` | class | `` | In-memory `MediaResolver`. Records every resolved blob; serves a | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.media.pdf_text`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MIN_CHARS_PER_PAGE` | const | `` |  | — | 0 |
| `PdfPage` | class | `` | One page's text layer plus the verdict on whether to trust it. | lib:noctusai_lib | 1 |
| `PdfTextLayer` | class | `` | Per-page classification of a PDF's text layer. | lib:noctusai_lib | 1 |
| `SCAN_IMAGE_COVERAGE_RATIO` | const | `` |  | — | 0 |
| `TEXT_RICH_CHARS_PER_PAGE` | const | `` |  | — | 0 |
| `classify_pdf_text_layer` | def | `(pdf_bytes: bytes) -> PdfTextLayer` | Classify each page's text layer as content or scan-stamp noise. | lib:noctusai_lib | 4 |
| `extract_pdf_text` | def | `(pdf_bytes: bytes) -> str` | Extract text from a PDF using PyMuPDF, falling back to pdfminer. | lib:noctusai_lib | 2 |
| `pdf_text_tooling_available` | def | `() -> bool` | True iff at least one of PyMuPDF or pdfminer.six can be imported. | lib:noctusai_lib | 1 |
| `strip_provenance_stamps` | def | `(text: str) -> str` | Drop the registry provenance boilerplate, keep everything else. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.media.real_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OpenAIMediaResolver` | class | `` | Real media resolver. Composes seed LLM entry points + ffmpeg + | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.media.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InboundMedia` | class | `` | An inbound media blob to resolve. | lib:noctusai_lib | 4 |
| `MediaKind` | class | `` | Classified inbound media category (derived from mimetype). | lib:noctusai_lib | 3 |
| `MediaResolver` | class | `` | Resolve inbound media to enriched chatbot-readable text. | lib:noctusai_lib | 1 |
| `ResolvedMedia` | class | `` | The resolver output the chatbot consumes. | lib:noctusai_lib | 3 |
| `classify_media_kind` | def | `(mimetype: Optional[str], filename: Optional[str]=None) -> M…` | Map a mimetype (or filename extension fallback) to a `MediaKind`. | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.meta._meta_api`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_GRAPH_VERSION` | const | `` |  | lib:noctusai_lib | 1 |
| `DEFAULT_MAX_PAGES` | const | `` |  | — | 0 |
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | — | 0 |
| `GRAPH_BASE` | const | `` |  | — | 0 |
| `IG_AUTHORIZE_BASE` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_CODE_EXCHANGE_BASE` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_GRAPH_BASE` | const | `` |  | lib:noctusai_lib | 2 |
| `IgLongToken` | class | `` | Step 3 result: short-lived → long-lived (~60d) IG User token, via | lib:noctusai_lib, social-wiring | 2 |
| `IgShortToken` | class | `` | Step 2 result: authorization `code` → short-lived (~1h) IG User | lib:noctusai_lib, social-wiring | 2 |
| `META_KITCHEN_SINK_SCOPES` | const | `` |  | lib:noctusai_lib | 4 |
| `MetaGraphError` | class | `` | Typed wrapper around a Graph error envelope. | lib:noctusai_lib, social-wiring | 20 |
| `app_access_token` | def | `(app_id: str, app_secret: str) -> str` | The App Access Token is literally `{app_id}|{app_secret}` — no | — | 0 |
| `build_ig_authorize_url` | def | `(*, app_id: str, redirect_uri: str, scopes: list[str] | tupl…` | Pure builder for the Instagram Business Login consent dialog URL. | lib:noctusai_lib, social-wiring | 2 |
| `discover_app_permissions` | def | `(*, app_id: str, app_secret: str, version: str=DEFAULT_GRAPH…` | Query `GET /{app-id}/permissions` with the App Access Token to | lib:noctusai_lib | 2 |
| `exchange_code_for_token` | def | `(*, code: str, app_id: str, app_secret: str, redirect_uri: s…` | Step 2 of the token chain: authorization `code` → short-lived | lib:noctusai_lib, social-wiring | 2 |
| `exchange_code_for_token_bundle` | def | `(*, code: str, app_id: str, app_secret: str, redirect_uri: s…` | Step 2 of the token chain, full-metadata variant: authorization | lib:noctusai_lib | 1 |
| `exchange_for_long_lived` | def | `(*, short_token: str, app_id: str, app_secret: str, version:…` | Step 3 of the token chain: short-lived → long-lived (~60d) user | lib:noctusai_lib | 1 |
| `exchange_for_long_lived_bundle` | def | `(*, short_token: str, app_id: str, app_secret: str, version:…` | Step 3 of the token chain, full-metadata variant: short-lived → | lib:noctusai_lib, social-wiring | 2 |
| `exchange_ig_code_for_token` | def | `(*, code: str, app_id: str, app_secret: str, redirect_uri: s…` | Step 2: authorization `code` → short-lived (~1h) IG User token. | lib:noctusai_lib, social-wiring | 2 |
| `exchange_ig_for_long_lived` | def | `(*, short_token: str, app_secret: str, timeout: float=DEFAUL…` | Step 3: short-lived → long-lived (~60d) IG User token, via | lib:noctusai_lib, social-wiring | 2 |
| `graph_delete` | def | `(path: str, *, access_token: str, params: dict[str, Any] | N…` | DELETE `{GRAPH_BASE}/{version}/{path}` with the token appended. | — | 0 |
| `graph_get` | def | `(path: str, *, access_token: str, params: dict[str, Any] | N…` | GET `{base}/{version}/{path}` with the token appended. | — | 0 |
| `graph_paged` | def | `(path: str, *, access_token: str, params: dict[str, Any] | N…` | Follow `paging.next` and accumulate `data` rows, up to | — | 0 |
| `graph_post` | def | `(path: str, *, access_token: str, data: dict[str, Any] | Non…` | POST `{base}/{version}/{path}` with the token in the body. | — | 0 |
| `poll_media_status` | def | `(creation_id: str, *, access_token: str, version: str=DEFAUL…` | Poll a video / Reel media container until it is publish-ready. | lib:noctusai_lib | 2 |
| `resolve_oauth_scopes` | def | `(*, configured: str | None, app_id: str | None=None, app_sec…` | Resolve the OAuth scope request set. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.meta.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MetaCredentialResolver` | class | `` | Product-injected per-tenant Meta OAuth credential lookup. | lib:noctusai_lib | 2 |
| `OAuthMetaCredentials` | class | `` | A stored long-lived Meta user access token for one tenant. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.meta.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeMetaAdapter` | class | `` | In-memory `MetaAdapter`. Default when no creds are configured. | lib:noctusai_lib, orbity, social-wiring | 14 |

### `noctusai_lib.integrations.meta.instagram_login_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeInstagramLoginAdapter` | class | `` | Deterministic in-memory Instagram-Login adapter (dev/test default). | lib:noctusai_lib, social-wiring | 2 |
| `InstagramLoginMessagingAdapter` | class | `` | Read-only IG Direct contract for the Instagram-Login model. | lib:noctusai_lib | 1 |
| `InstagramLoginOAuthAdapter` | class | `` | Live Instagram-Login read adapter over ``graph.instagram.com``. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.meta.leadgen_webhook`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LeadgenEvent` | class | `` | One `leadgen` change entry from a Lead-Ads webhook delivery. | lib:noctusai_lib, social-wiring | 2 |
| `LeadgenUpdateEvent` | class | `` | One `leadgen_update` change entry — Meta's AI-agent qualification feed. | lib:noctusai_lib | 1 |
| `leadgen_challenge_response` | def | `(*, mode: str | None, verify_token: str | None, challenge: s…` | Meta's webhook-verification handshake (`GET /webhooks` with | erp-imobiliario, lib:noctusai_lib, social-wiring | 4 |
| `parse_leadgen_update_webhook` | def | `(payload: dict[str, Any]) -> list[LeadgenUpdateEvent]` | Parse `leadgen_update` changes out of a Page webhook delivery. | lib:noctusai_lib, social-wiring | 3 |
| `parse_leadgen_webhook` | def | `(payload: dict[str, Any]) -> list[LeadgenEvent]` | Parse a Meta Lead-Ads webhook `POST` body into `LeadgenEvent`s. | erp-imobiliario, lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.meta.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FB_COMMENT_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_ACCOUNT_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_ACCOUNT_INSIGHT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_COMMENT_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_CONVERSATION_FIELDS` | const | `` |  | lib:noctusai_lib | 2 |
| `IG_DM_FIELDS` | const | `` |  | lib:noctusai_lib | 2 |
| `IG_MEDIA_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_MEDIA_INSIGHT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_TOTAL_VALUE_ACCOUNT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `ME_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `PAGE_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `PAGE_IG_FIELD` | const | `` |  | lib:noctusai_lib | 1 |
| `PAGE_INSIGHT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `POST_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `POST_INSIGHT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `ad_account_from_body` | def | `(body: dict[str, Any]) -> AdAccount` | Map one row of `GET me/adaccounts` to `AdAccount`. | lib:noctusai_lib | 2 |
| `ad_activity_from_body` | def | `(body: dict[str, Any]) -> AdActivity` | Map one row of `GET act_{id}/activities` to `AdActivity`. | lib:noctusai_lib | 2 |
| `ad_from_body` | def | `(body: dict[str, Any]) -> Ad` | Map one row of `GET act_{id}/ads` to `Ad`. `creative` is the | lib:noctusai_lib | 2 |
| `ad_insights_row_from_body` | def | `(row: dict[str, Any], *, breakdown_keys: list[str] | None=No…` | Map ONE row of `GET /{object-id}/insights` `data` to | lib:noctusai_lib | 2 |
| `ad_set_from_body` | def | `(body: dict[str, Any]) -> AdSet` | Map one row of `GET act_{id}/adsets` to `AdSet`. `daily_budget` | lib:noctusai_lib | 2 |
| `campaign_from_body` | def | `(body: dict[str, Any]) -> AdCampaign` | Map one row of `GET act_{id}/campaigns` (or a single-campaign | lib:noctusai_lib | 1 |
| `conversation_from_body` | def | `(body: dict[str, Any]) -> Conversation` | Map one row of `GET /{ig-user}/conversations?platform=instagram` | lib:noctusai_lib | 3 |
| `direct_message_from_body` | def | `(body: dict[str, Any], *, conversation_id: str | None=None) …` | Map a per-message detail fetch (`GET /{message-id}`) to | lib:noctusai_lib | 3 |
| `facebook_comment_from_body` | def | `(body: dict[str, Any]) -> FacebookComment` | Map one row of `GET /{post}/comments` (or a comment read-back | lib:noctusai_lib | 2 |
| `ig_account_from_body` | def | `(body: dict[str, Any], *, page_id: str | None=None) -> Insta…` |  | lib:noctusai_lib | 2 |
| `ig_media_from_body` | def | `(body: dict[str, Any]) -> InstagramMedia` |  | lib:noctusai_lib | 2 |
| `insights_from_body` | def | `(object_id: str, body: dict[str, Any]) -> PostInsights` | Map `/{id}/insights` `{"data": [{name, period, values}]}`. | lib:noctusai_lib | 2 |
| `instagram_comment_from_body` | def | `(body: dict[str, Any]) -> InstagramComment` | Map one row of `GET /{ig-media}/comments` (or a comment | lib:noctusai_lib | 2 |
| `lead_from_body` | def | `(body: dict[str, Any]) -> Lead` | Map one row of `{form_id}/leads` (or `{ad_id}/leads`) to `Lead`. | lib:noctusai_lib | 1 |
| `leadgen_form_from_body` | def | `(body: dict[str, Any]) -> LeadgenForm` | Map one row of `{page_id}/leadgen_forms` (or a single-form read | lib:noctusai_lib | 1 |
| `leadgen_question_from_body` | def | `(body: dict[str, Any]) -> LeadgenQuestion` | Map one entry of a form's `questions` array to `LeadgenQuestion`. | — | 0 |
| `page_from_body` | def | `(body: dict[str, Any]) -> FacebookPage` |  | lib:noctusai_lib | 2 |
| `page_subscription_from_body` | def | `(body: dict[str, Any]) -> PageSubscription` | Map one row of `GET /{page_id}/subscribed_apps` to | lib:noctusai_lib | 2 |
| `parse_graph_datetime` | def | `(value: str | None) -> datetime | None` | Parse Graph's timestamp formats into an aware ``datetime``. | lib:noctusai_lib | 1 |
| `post_from_body` | def | `(body: dict[str, Any]) -> FacebookPost` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.meta.oauth_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MetaOAuthAdapter` | class | `` | Live Meta Graph adapter satisfying `MetaAdapter`. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.meta.router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_meta_router` | def | `(*, get_adapter: Callable[[str | None], MetaAdapter], app_id…` | Build the Meta introspection router. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.meta.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Ad` | class | `` | A Marketing-API ad — the leaf binding an ad set to a creative. | lib:noctusai_lib, social-wiring | 7 |
| `AdAccount` | class | `` | A Marketing-API ad account the authenticated identity can | lib:noctusai_lib, social-wiring | 7 |
| `AdActivity` | class | `` | One row of an ad account's change log (`act_{id}/activities`) | lib:noctusai_lib, social-wiring | 6 |
| `AdCampaign` | class | `` | A Marketing-API ad campaign under an ad account. | lib:noctusai_lib, orbity, social-wiring | 9 |
| `AdCreative` | class | `` | A Marketing-API ad creative (the rendered content an ad shows). | lib:noctusai_lib | 3 |
| `AdCreativeSpec` | class | `` | Input spec for `create_ad_creative`. | lib:noctusai_lib | 3 |
| `AdInsights` | class | `` | Flattened ad-insights metrics for an object (campaign / adset / | lib:noctusai_lib, orbity | 4 |
| `AdInsightsRow` | class | `` | One row of an ad-insights TIME SERIES (`AdInsightsSeries.rows`). | lib:noctusai_lib, social-wiring | 5 |
| `AdInsightsSeries` | class | `` | The full multi-row result of `ad_insights_series(...)` — EVERY | lib:noctusai_lib, social-wiring | 7 |
| `AdSet` | class | `` | A Marketing-API ad set (the targeting + budget + schedule layer | lib:noctusai_lib, social-wiring | 7 |
| `AdSetSpec` | class | `` | Input spec for `create_ad_set`. | lib:noctusai_lib | 3 |
| `AdSpec` | class | `` | Input spec for `create_ad`. | lib:noctusai_lib | 3 |
| `CampaignSpec` | class | `` | Input spec for `create_ad_campaign`. | lib:noctusai_lib | 3 |
| `Conversation` | class | `` | An Instagram Direct conversation thread | lib:noctusai_lib, social-wiring | 7 |
| `DirectMessage` | class | `` | One message inside an Instagram Direct conversation. | lib:noctusai_lib, social-wiring | 7 |
| `FacebookComment` | class | `` | A comment (or reply) on a Facebook Page post. | lib:noctusai_lib, social-wiring | 5 |
| `FacebookPage` | class | `` | A Facebook Page the authenticated identity manages. | lib:noctusai_lib, social-wiring | 9 |
| `FacebookPost` | class | `` | A post authored by a Page. | lib:noctusai_lib, social-wiring | 6 |
| `InstagramAccount` | class | `` | An Instagram Business/Creator account linked to a Page via the | lib:noctusai_lib, social-wiring | 10 |
| `InstagramComment` | class | `` | A comment (or reply) on an Instagram media item. | lib:noctusai_lib, social-wiring | 5 |
| `InstagramMedia` | class | `` | An Instagram media item (image, video, or carousel album). | lib:noctusai_lib, social-wiring | 6 |
| `Lead` | class | `` | One submitted lead record (`{form_id}/leads` or `{ad_id}/leads`). | lib:noctusai_lib, social-wiring | 6 |
| `LeadFieldEntry` | class | `` | One answered field on a lead — a `{name, values}` pair from a | lib:noctusai_lib, social-wiring | 4 |
| `LeadgenForm` | class | `` | A Page's lead-gen (Instant Form) form (`{page_id}/leadgen_forms`). | lib:noctusai_lib, social-wiring | 6 |
| `LeadgenQuestion` | class | `` | One question on a lead-gen (Instant Form) form — the FIELD SCHEMA | lib:noctusai_lib, social-wiring | 4 |
| `MediaProcessingStatus` | class | `` | One reading of a video / Reel media container's processing state. | lib:noctusai_lib | 2 |
| `MetaAdapter` | class | `` | Meta Graph read-only adapter contract. Concrete implementations: | lib:noctusai_lib, social-wiring | 7 |
| `MetaConnectionStatus` | class | `` | Adapter introspection surface for `/api/meta/status`. | lib:noctusai_lib, social-wiring | 4 |
| `PageSubscription` | class | `` | One app's webhook subscription on a Page (`GET | lib:noctusai_lib | 4 |
| `PostInsights` | class | `` | Flattened per-post / per-media insight metrics. | lib:noctusai_lib, social-wiring | 6 |
| `PublishedMedia` | class | `` | The result of publishing an Instagram media item. | lib:noctusai_lib | 3 |
| `PublishedPost` | class | `` | The result of publishing a Facebook Page post. | lib:noctusai_lib | 3 |
| `TokenBundle` | class | `` | The full Graph `oauth/access_token` response, metadata preserved. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.n8n.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeN8nClient` | class | `` | In-memory n8n stand-in. Records state as raw n8n-shaped dicts | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.n8n.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `WORKFLOW_PUT_ALLOWED_KEYS` | const | `` |  | lib:noctusai_lib | 1 |
| `extract_error_message` | def | `(body: Any) -> tuple[str, str]` | Best-effort ``(title, detail)`` extraction from an n8n error | lib:noctusai_lib | 1 |
| `extract_webhook_trigger` | def | `(nodes: Optional[List[dict[str, Any]]]) -> Optional[tuple[st…` | Find the first ``n8n-nodes-base.webhook`` node and return its | lib:noctusai_lib | 1 |
| `instance_root` | def | `(raw: str) -> str` | Return the bare instance root (no ``/api/v1`` suffix) — the base | lib:noctusai_lib, social-wiring | 3 |
| `normalize_base_url` | def | `(raw: str) -> str` | Return the API root ending in ``/api/v1``, no trailing slash. | lib:noctusai_lib | 2 |
| `raw_to_credential` | def | `(raw: dict[str, Any]) -> Credential` | Translate an n8n /credentials create-response into a | lib:noctusai_lib | 2 |
| `raw_to_execution` | def | `(raw: dict[str, Any]) -> Execution` | Translate an n8n /executions item (``includeData=false`` shape) | lib:noctusai_lib | 3 |
| `raw_to_tag` | def | `(raw: dict[str, Any]) -> Tag` | Translate an n8n /tags item into a ``Tag``. | lib:noctusai_lib | 2 |
| `raw_to_workflow` | def | `(raw: dict[str, Any]) -> Workflow` | Translate a full n8n /workflows item into a ``Workflow`` summary. | lib:noctusai_lib, social-wiring | 4 |
| `sanitize_workflow_put_body` | def | `(workflow: dict[str, Any]) -> dict[str, Any]` | Strip a workflow dict to the PUT/POST-accepted key-set. | lib:noctusai_lib | 3 |
| `tag_refs_body` | def | `(tag_ids: Sequence[str]) -> list[dict[str, str]]` | n8n ``PUT /workflows/{id}/tags`` body shape: ``[{"id": "<tagId>"}, ...]`` | lib:noctusai_lib | 2 |
| `webhook_url` | def | `(base_url: str, path: str) -> str` | Build the run-dispatch URL for a webhook-triggered workflow. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.n8n.n8n_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `HttpxN8nClient` | class | `` | Real n8n public API v1 client backed by ``httpx.AsyncClient``. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.n8n.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Credential` | class | `` | A created credential's public handle. n8n stores the secret | lib:noctusai_lib | 4 |
| `Execution` | class | `` | An execution summary (list item — ``includeData=false``). | lib:noctusai_lib | 4 |
| `N8nAuthError` | class | `` | 401 / 403 — bad API key or insufficient permissions. | lib:noctusai_lib | 2 |
| `N8nClient` | class | `` | Async n8n public API v1 adapter. | lib:noctusai_lib, social-wiring | 2 |
| `N8nError` | class | `` | Base for all n8n seed-adapter errors. | lib:noctusai_lib, social-wiring | 6 |
| `N8nNotFoundError` | class | `` | 404 — resource does not exist. | lib:noctusai_lib, social-wiring | 4 |
| `N8nRateLimitedError` | class | `` | 429 — request rate exceeded. | lib:noctusai_lib | 2 |
| `N8nRejectedError` | class | `` | 400 / 422 — n8n rejected the payload (e.g. PUT with additional | lib:noctusai_lib | 2 |
| `N8nUnreachableError` | class | `` | Network / TLS / 5xx — transient infrastructure failure. | lib:noctusai_lib | 2 |
| `N8nWorkflowNotRunnableError` | class | `` | ``run_via_webhook()`` called on a workflow that does not satisfy | lib:noctusai_lib, social-wiring | 4 |
| `RunResult` | class | `` | Result of ``run_via_webhook()``. Never fabricated — ``dispatched`` | lib:noctusai_lib | 3 |
| `Tag` | class | `` | An n8n workflow tag — the only viable multi-tenant scoping key | lib:noctusai_lib | 4 |
| `Workflow` | class | `` | A workflow list/summary value object. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.oauth_bundles`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `bundle_names` | def | `() -> list[str]` | Sorted list of valid bundle names (for config validation / docs). | — | 0 |
| `resolve_bundle` | def | `(name: str) -> list[str]` | Resolve a bundle name to its concrete scope list (a fresh copy). | — | 0 |

### `noctusai_lib.integrations.olx.contract`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ContractViolation` | class | `` | One way a payload departs from the documented contract. | — | 0 |
| `OlxFieldSpec` | class | `` | One documented field of the lead payload. | — | 0 |
| `contract_summary` | def | `() -> dict[str, Any]` | Everything an agent needs to understand the contract in one call. | — | 0 |
| `diff_observed` | def | `(bodies: list[dict[str, Any]]) -> dict[str, Any]` | Diff a corpus of REAL delivery bodies against this contract. | — | 0 |
| `has_blocking_violation` | def | `(violations: list[ContractViolation]) -> bool` | True when at least one violation is an `error`. | — | 0 |
| `missing_client_listing_id` | def | `(violations: list[ContractViolation]) -> bool` | True when the ONLY documented reason to answer 4xx applies. | — | 0 |
| `olx_lead_json_schema` | def | `() -> dict[str, Any]` | JSON Schema derived from `OLX_LEAD_FIELDS` — derived, not restated, | — | 0 |
| `validate_olx_lead_payload` | def | `(payload: Any) -> list[ContractViolation]` | Check a delivery body against the documented contract. | — | 0 |

### `noctusai_lib.integrations.olx.endpoints`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ENDPOINT_ABSENT` | const | `` |  | — | 0 |
| `ENDPOINT_INBOUND` | const | `` |  | — | 0 |
| `ENDPOINT_LIVE` | const | `` |  | — | 0 |
| `ENDPOINT_PERMISSION_GATED` | const | `` |  | — | 0 |
| `ENDPOINT_UNVERIFIED` | const | `` |  | — | 0 |
| `ENDPOINT_WRITE_ONLY` | const | `` |  | — | 0 |
| `OLX_LEAD_MANAGER_BASE_URL` | const | `` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.olx.errors`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OlxConfigError` | class | `` | Credentials or base URL absent. HTTP 424 — gated-capability | lib:noctusai_lib | 2 |
| `OlxError` | class | `` | Base for every OLX integration failure. | lib:noctusai_lib | 1 |
| `OlxUpstreamError` | class | `` | OLX answered non-2xx, or was unreachable / returned non-JSON. | lib:noctusai_lib | 2 |
| `redact_secret` | def | `(text: str, *secrets: Optional[str]) -> str` | Strip any of `secrets` out of `text` before it reaches a log, an | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.olx.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_olx_lead_manager_client` | def | `(*, use_fake: bool=False, api_key: Optional[str]=None, agent…` | Build an OLX Gestor de Leads client. | — | 0 |

### `noctusai_lib.integrations.olx.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeOlxLeadManagerClient` | class | `` | In-memory stand-in for `OlxLeadManagerClient`. | lib:noctusai_lib | 1 |
| `upstream_failure` | def | `(status: int=500, message: str='fake upstream failure') -> O…` | Convenience for `fail_with=` in tests. | — | 0 |

### `noctusai_lib.integrations.olx.normalizers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OLX_SOURCE_SLUG` | const | `` |  | lib:noctusai_lib | 1 |
| `olx_lead_to_lead_payload` | def | `(lead: OlxLead, *, origem_source_id: str, external_source: s…` | One `OlxLead` → the payload a product's `create_lead` expects. | — | 0 |
| `olx_timestamp_to_date` | def | `(value: Any) -> Optional[date]` | ISO-8601 `timestamp` → its DATE part; `None` when unparseable. | — | 0 |
| `render_observacoes` | def | `(lead: OlxLead) -> Optional[str]` | The qualifying context, one `label: value` line each. | — | 0 |

### `noctusai_lib.integrations.olx.portal_split`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PortalAttribution` | class | `` | The resolved slug plus WHY, so a surprising attribution is | — | 0 |
| `PortalRule` | class | `` | "When `field` looks like this, the lead came from `slug`." | — | 0 |
| `resolve_portal_source_slug` | def | `(lead: OlxLead, *, rules: tuple[PortalRule, ...]=OLX_PORTAL_…` | The `lead_sources` slug this lead should be attributed to. | — | 0 |

### `noctusai_lib.integrations.olx.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OlxLeadManagerAdapter` | class | `` | Outbound Gestor de Leads surface — async. | — | 0 |

### `noctusai_lib.integrations.olx.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `OlxLeadManagerClient` | class | `` | Real `OlxLeadManagerAdapter`. | lib:noctusai_lib | 1 |
| `RATE_LIMIT_BUCKET` | const | `` |  | — | 0 |

### `noctusai_lib.integrations.olx.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OLX_LEAD_ORIGIN_MCMV` | const | `` |  | lib:noctusai_lib | 1 |
| `OLX_LEAD_ORIGIN_STANDARD` | const | `` |  | lib:noctusai_lib | 1 |
| `OlxLead` | class | `` | One lead as delivered by the Grupo OLX webhook. | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.olx.webhook`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `parse_olx_lead_webhook` | def | `(payload: Any) -> Optional[OlxLead]` | One delivery body → one `OlxLead`, or `None` when unparseable. | — | 0 |

### `noctusai_lib.integrations.outbound_webhook.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_outbound_webhook_sender` | def | `(*, use_fake: bool=False, timeout_seconds: float=DEFAULT_TIM…` | Build a sender. Both branches satisfy `OutboundWebhookSender`, so a | — | 0 |

### `noctusai_lib.integrations.outbound_webhook.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeOutboundWebhookSender` | class | `` | Scriptable `OutboundWebhookSender`. | lib:noctusai_lib | 1 |
| `RecordedRequest` | class | `` | One captured delivery, for assertions. | — | 0 |
| `failure` | def | `(*, status_code: Optional[int]=None, kind: DeliveryFailureKi…` | Shorthand for scripting a failed attempt in a test. | — | 0 |
| `success` | def | `(status_code: int=200, body: Optional[str]='ok') -> Delivery…` | Shorthand for scripting a successful attempt in a test. | — | 0 |

### `noctusai_lib.integrations.outbound_webhook.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OutboundWebhookSender` | class | `` | POST one body to one URL and report what happened. | — | 0 |

### `noctusai_lib.integrations.outbound_webhook.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `DEFAULT_USER_AGENT` | const | `` |  | lib:noctusai_lib | 1 |
| `HttpxOutboundWebhookSender` | class | `` | Real `OutboundWebhookSender` over httpx. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.outbound_webhook.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DeliveryAttempt` | class | `` | The result of exactly one POST. Never a retry sequence. | lib:noctusai_lib | 3 |
| `DeliveryFailureKind` | class | `` | Why an attempt did not succeed. | lib:noctusai_lib | 2 |
| `RESPONSE_BODY_LIMIT` | const | `` |  | — | 0 |
| `truncate_body` | def | `(text: Optional[str], limit: int=RESPONSE_BODY_LIMIT) -> Opt…` | Clip a response body to a storable size, preserving `None`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.payments.errors`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PaymentGatewayError` | class | `` | A call to a payment gateway failed. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.payments.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_payment_gateway` | def | `(*, provider: Union[PaymentGatewayName, str, None]=None, use…` | Build a `PaymentGateway`. Every branch satisfies the same Protocol, | — | 0 |

### `noctusai_lib.integrations.payments.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakePaymentGateway` | class | `` | Deterministic, in-process `PaymentGateway`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.payments.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PaymentGateway` | class | `` | Customers, subscriptions, and their fees. One vocabulary, N vendors. | — | 0 |

### `noctusai_lib.integrations.payments.real_asaas`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AsaasPaymentGateway` | class | `` | Real `PaymentGateway` over the Asaas API v3. | lib:noctusai_lib | 1 |
| `DEFAULT_BASE_URL` | const | `` |  | lib:noctusai_lib | 1 |
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.payments.real_stripe`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StripePaymentGateway` | class | `` | Real `PaymentGateway` over the Stripe Python SDK. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.payments.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FeeBreakdown` | class | `` | One charge's economics, normalized across gateways. | lib:noctusai_lib | 4 |
| `GatewayCustomer` | class | `` | The payer, as the gateway knows them. | lib:noctusai_lib | 4 |
| `GatewaySubscription` | class | `` | A subscription as the gateway reports it, translated to our lexicon. | lib:noctusai_lib | 4 |
| `Money` | class | `` | An amount as INTEGER CENTS + an explicit ISO-4217 currency code. | lib:noctusai_lib | 3 |
| `PaymentGatewayName` | class | `` | Which vendor issued a `PaymentGateway`. Used for logging/metrics | lib:noctusai_lib | 5 |
| `SubscriptionRequest` | class | `` | What we want to start charging. Zero gateway vocabulary. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.persistence.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryRecordStore` | class | `` | In-memory :class:`~.types.RecordStore`. Satisfies the Protocol. | — | 0 |
| `matches` | def | `(record: Record, filters: tuple, /) -> bool` | True iff ``record`` satisfies every filter (AND). | — | 0 |

### `noctusai_lib.integrations.persistence.paging`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_MAX_PAGES` | const | `` |  | — | 0 |
| `DEFAULT_PAGE_SIZE` | const | `` |  | — | 0 |
| `PagerOverflowError` | class | `` | The result set exceeded ``page_size * max_pages`` rows. | — | 0 |
| `iter_paged_rows` | def | `(fetch_page: Callable[[int, int], Any], *, page_size: int=DE…` | Yield every row of an offset-paged read, exactly once. | academia-de-reciclagem, social-wiring | 2 |

### `noctusai_lib.integrations.persistence.sqlite_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SqliteRecordStore` | class | `` | A :class:`~.types.RecordStore` backed by a SQLite file (or ``:memory:``). | — | 0 |

### `noctusai_lib.integrations.persistence.supabase_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SupabaseLike` | class | `` | The slice of ``supabase.Client`` this adapter uses. | — | 0 |
| `SupabaseRecordStore` | class | `` | A :class:`~.types.RecordStore` over a Supabase client. | — | 0 |

### `noctusai_lib.integrations.persistence.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Filter` | class | `` | One column predicate. Combined with AND by :class:`QuerySpec`. | — | 0 |
| `Op` | class | `` | Comparison operators a :class:`Filter` may use. | lib:noctusai_lib | 3 |
| `Order` | class | `` | Sort directive. ``descending`` mirrors Postgres' default NULLS LAST. | — | 0 |
| `PersistenceError` | class | `` | Base for every error this seam raises. | lib:noctusai_lib | 2 |
| `QuerySpec` | class | `` | Everything a list query can express in this seam. | lib:noctusai_lib | 3 |
| `RecordNotFound` | class | `` | A single-record operation matched nothing. | lib:noctusai_lib | 3 |
| `RecordStore` | class | `` | The surface every persistence backend implements. | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.quota.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_quota_tracker` | def | `(*, kind: Literal['memory', 'redis']='memory', redis_client:…` | Build a `QuotaTracker`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.quota.in_memory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryQuotaTracker` | class | `` | Deque-per-key sliding-window quota tracker. Async-safe within a | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.quota.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `QuotaTracker` | class | `` | Pluggable quota / rate-limit tracker. | lib:noctusai_lib | 5 |

### `noctusai_lib.integrations.quota.redis_backend`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MAX_RETRIES` | const | `` |  | — | 0 |
| `RedisQuotaTracker` | class | `` | Redis-backed sliding-window quota tracker. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.quota.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `QuotaCheck` | class | `` | Result of `consume(...)` or `peek(...)`. | lib:noctusai_lib | 4 |
| `QuotaConfig` | class | `` | Quota declaration: how many units allowed within how big a window. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.rate_limit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BucketConfig` | class | `` | Per-provider pacing + backoff policy. | — | 0 |
| `Clock` | class | `` |  | — | 0 |
| `RateLimitedError` | class | `` | Structural type for a provider error that carries retry info. | — | 0 |
| `RateLimiter` | class | `` | Registry of named token buckets. One process-wide instance | — | 0 |
| `TokenBucket` | class | `` | Thread-safe token bucket. ``acquire`` removes one token, blocking | — | 0 |
| `VirtualClock` | class | `` | A clock whose ``sleep`` advances virtual time instead of the wall | — | 0 |
| `acquire` | def | `(bucket: str, tokens: float=1.0) -> float` | Pace one outbound request against ``bucket`` — blocks until a | — | 0 |
| `acquire_async` | async def | `(bucket: str, tokens: float=1.0) -> float` | Async twin of ``acquire`` — pace one outbound request without | lib:noctusai_lib | 2 |
| `paced_call` | def | `(fn: Callable[[], T], *, bucket: str, is_retryable: Callable…` | The full protection for one logical operation: acquire a pacing | — | 0 |
| `parse_retry_after` | def | `(value: Any) -> float | None` | Parse an HTTP ``Retry-After`` header value → seconds. Supports the | — | 0 |
| `reset_default_clock` | def | `() -> None` | Restore the real clock (test teardown). | — | 0 |
| `retry_with_backoff` | def | `(fn: Callable[[], T], *, bucket: str='default', is_retryable…` | Call ``fn``; on a *retryable* exception (per ``is_retryable`` — | — | 0 |
| `retry_with_backoff_async` | async def | `(fn: Callable[[], Any], *, bucket: str='default', is_retryab…` | Async twin of ``retry_with_backoff``. ``fn`` is an async callable | lib:noctusai_lib | 1 |
| `set_default_clock` | def | `(clock: Clock) -> None` | Swap the process-wide default clock (tests only). Call | — | 0 |

### `noctusai_lib.integrations.redis`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_fake_redis_client` | def | `(**kwargs: Any) -> 'Redis'` | In-memory Redis-compatible client for tests + dev (no network). | lib:noctusai_lib, social-wiring | 2 |
| `make_redis_client` | def | `(redis_url: str, **kwargs: Any) -> 'Redis'` | Construct a sync `redis.Redis` from a URL. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.storage.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_storage_backend` | def | `(*, kind: Literal['fake', 'local', 'supabase'], root_dir: Pa…` | Build a `StorageBackend`. | igig, lib:noctusai_lib, social-wiring | 6 |

### `noctusai_lib.integrations.storage.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeStorageBackend` | class | `` | Deterministic in-memory `StorageBackend` implementation. | adconnect, lib:noctusai_lib, social-wiring | 13 |

### `noctusai_lib.integrations.storage.local`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LocalFilesystemStorageBackend` | class | `` | Filesystem-backed `StorageBackend`. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.storage.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StorageBackend` | class | `` | Blob storage contract — Supabase Storage shape, abstracted. | adconnect, igig, lib:noctusai_lib, social-wiring | 18 |

### `noctusai_lib.integrations.storage.supabase`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SupabaseStorageBackend` | class | `` | Real Supabase Storage `StorageBackend`. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.storage.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `BlobMetadata` | class | `` | Description of a stored blob, without its bytes. | lib:noctusai_lib | 5 |
| `StoredBlob` | class | `` | A retrieved blob — metadata plus raw bytes. | lib:noctusai_lib | 5 |

### `noctusai_lib.integrations.supabase_identity`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `UserIdentity` | class | `` | Display-name + email + avatar for a Supabase auth user. | therapy-platform | 3 |
| `fetch_user_identities` | def | `(db: Any, user_ids: Iterable[str]) -> Dict[str, UserIdentity…` | Resolve a batch of Supabase auth.users → UserIdentity, keyed by user_id. | therapy-platform | 3 |
| `fetch_user_identity` | def | `(db: Any, user_id: str) -> UserIdentity` | Single-user variant of `fetch_user_identities`. | — | 0 |

### `noctusai_lib.integrations.svg_render.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeSvgRenderAdapter` | class | `` | Deterministic in-memory SVG→PNG adapter. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.svg_render.resvg_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ResvgRenderAdapter` | class | `` | Real SVG→PNG adapter via ``resvg-py`` with bundled fonts. | lib:noctusai_lib | 1 |
| `bundled_font_files` | def | `() -> list[str]` | Absolute paths of the bundled OFL ``.ttf`` faces (Cormorant + Inter). | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.svg_render.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RenderedImage` | class | `` | Rasterized PNG result. | lib:noctusai_lib | 3 |
| `SvgRenderAdapter` | class | `` | SVG→PNG render adapter contract. Concrete implementations: | lib:noctusai_lib, social-wiring | 2 |
| `SvgRenderInput` | class | `` | SVG→PNG render request payload. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.integrations.vista.adapter_factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_vista_adapter` | def | `(*, base_url: str | None=None, api_key: str | None=None, fak…` | Return a `VistaCRMAdapter` wired for the supplied credentials. | — | 0 |

### `noctusai_lib.integrations.vista.calibration`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CalibrationResult` | class | `` | The cached outcome of one calibration pass for one endpoint family. | — | 0 |
| `Calibrator` | class | `` | Per-process cache of per-tenant safe field sets. | — | 0 |

### `noctusai_lib.integrations.vista.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_PAGE_SIZE` | const | `` |  | lib:noctusai_lib | 1 |
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `ENDPOINT_ABSENT` | const | `` |  | — | 0 |
| `ENDPOINT_LIVE` | const | `` |  | — | 0 |
| `ENDPOINT_PERMISSION_GATED` | const | `` |  | — | 0 |
| `ENDPOINT_WRITE_ONLY` | const | `` |  | — | 0 |
| `KEY_REDACTION_PLACEHOLDER` | const | `` |  | — | 0 |
| `PAGINATION_KEYS` | const | `` |  | — | 0 |
| `VistaCallResult` | class | `` | Lightweight tuple-like carrier for a successful request. | lib:noctusai_lib | 1 |
| `VistaClient` | class | `` | Async HTTP client for the Vista REST API. | lib:noctusai_lib | 3 |
| `VistaConfigError` | class | `` | Vista base URL or API key is missing/empty. | lib:noctusai_lib | 3 |
| `VistaError` | class | `` | Base class for any Vista adapter failure. | lib:noctusai_lib | 2 |
| `VistaFieldNotAvailable` | class | `` | Vista refused one or more fields — `400 "Campo X não está disponível"`. | lib:noctusai_lib | 1 |
| `VistaNotFound` | class | `` | Endpoint not exposed on this tenant (HTTP 404). | lib:noctusai_lib | 1 |
| `VistaPermissionDenied` | class | `` | Endpoint exists but the API key has no permission (HTTP 401). | lib:noctusai_lib | 1 |
| `VistaTimeout` | class | `` | `httpx.TimeoutException` wrapper. | — | 0 |
| `VistaUpstreamError` | class | `` | Generic upstream non-2xx wrapper. | lib:noctusai_lib | 1 |
| `extract_items` | def | `(payload: dict) -> tuple[list[dict], dict]` | Split Vista's dict-keyed-by-id response into (items, pagination). | lib:noctusai_lib | 1 |
| `redact_api_key` | def | `(text: str, api_key: str) -> str` | Strip the tenant API key out of any text bound for an exception or log. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_vista_client` | def | `(*, use_fake: bool=False, base_url: Optional[str]=None, api_…` | Build a Vista client. | — | 0 |

### `noctusai_lib.integrations.vista.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeVistaClient` | class | `` | Deterministic in-memory `VistaClient` stand-in. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeVistaAdapter` | class | `` | In-memory ``VistaCRMAdapter`` stand-in. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.imovel_normalizer`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `merge_vista_payloads` | def | `(listing: Optional[dict]=None, detalhes: Optional[dict]=None…` | Merge a listar row and a detalhes payload into one dict. | — | 0 |
| `vista_to_imovel` | def | `(listing: Optional[dict]=None, detalhes: Optional[dict]=None…` | Build a canonical `Imovel` from either or both Vista payloads. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.normalizers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `vista_agencia_to_showcase` | def | `(payload: dict) -> ShowcaseAgencia` |  | — | 0 |
| `vista_cliente_detalhes_to_showcase` | def | `(payload: dict) -> ShowcaseClienteDetalhes` | DETAIL projection: the list fields plus the four demographic ones. | — | 0 |
| `vista_cliente_to_showcase` | def | `(payload: dict) -> ShowcaseCliente` | LIST projection of one client. | — | 0 |
| `vista_imovel_detalhes_to_showcase` | def | `(detalhes_payload: dict, *, listing_payload: Optional[dict]=…` | Compose detail view from /imoveis/detalhes + (optionally) the matching | — | 0 |
| `vista_imovel_to_showcase` | def | `(payload: dict) -> ShowcaseImovel` |  | — | 0 |
| `vista_usuario_to_showcase` | def | `(payload: dict) -> ShowcaseUsuario` |  | — | 0 |

### `noctusai_lib.integrations.vista.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `VistaCRMAdapter` | class | `` | Adapter contract for the domain-shape CRM facade — async. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `VistaRESTAdapter` | class | `` | Fetch property metadata from the Vista REST API by code. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ShowcaseAgencia` | class | `` |  | lib:noctusai_lib | 1 |
| `ShowcaseCliente` | class | `` | One CRM client, LIST view — deliberately the minimised projection. | lib:noctusai_lib | 1 |
| `ShowcaseClienteDetalhes` | class | `` | One CRM client, DETAIL view — the list projection PLUS the demographics. | lib:noctusai_lib | 1 |
| `ShowcaseImovel` | class | `` |  | lib:noctusai_lib | 1 |
| `ShowcaseImovelDetalhes` | class | `` |  | lib:noctusai_lib | 1 |
| `ShowcaseUsuario` | class | `` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RECOVER_READY_STATUSES` | const | `` |  | lib:noctusai_lib | 1 |
| `WahaClient` | class | `` | WAHA HTTP client with both sync and async send paths. | lib:noctusai_lib, social-wiring | 3 |
| `WahaSessionNotReady` | class | `` | Raised by ``get_qr`` when the session is not in ``SCAN_QR_CODE``. | lib:noctusai_lib, lib:noctusai_seed, social-wiring | 4 |
| `recovery_outcome` | def | `(state: dict[str, Any], stage: str) -> dict[str, Any]` | Shape a `get_session`-like state dict into `recover_session`'s | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.dedup`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryWebhookDedup` | class | `` | Deterministic in-process dedup (no network). | lib:noctusai_lib | 2 |
| `RedisWebhookDedup` | class | `` | Redis SETNX-backed first-seen check. | lib:noctusai_lib | 1 |
| `SetnxRedis` | class | `` | The minimal Redis surface the SETNX pre-filter needs. | lib:noctusai_lib | 1 |
| `WebhookDedup` | class | `` | First-seen check for a webhook ``provider_message_id``. | lib:noctusai_lib | 2 |
| `get_webhook_dedup` | def | `(*, redis_client: SetnxRedis | None=None, key_prefix: str=_D…` | Return `RedisWebhookDedup` when a Redis client is supplied; | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.whatsapp.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeWahaClient` | class | `` | In-memory WAHA stand-in. Records sent messages, serves | lib:noctusai_lib, social-wiring | 5 |

### `noctusai_lib.integrations.whatsapp.lid_auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryLidPhoneCache` | class | `` | Deterministic in-memory LID↔phone cache (no network). | lib:noctusai_lib | 1 |
| `LidPhoneCache` | class | `` | Bidirectional LID↔phone binding store. | lib:noctusai_lib | 1 |
| `RedisLidPhoneCache` | class | `` | Redis-backed LID↔phone cache. | lib:noctusai_lib | 1 |
| `extract_resolved_remote` | def | `(send_response: dict) -> str | None` | Pull the resolved remote JID from a WAHA send-text response. | lib:noctusai_lib | 1 |
| `get_lid_phone_cache` | def | `(*, redis_client: 'Redis | None'=None, key_prefix: str=_DEFA…` | Return `RedisLidPhoneCache` when a Redis client is supplied; | lib:noctusai_lib | 1 |
| `is_authorized` | def | `(chat_id: str, *, phone_whitelist: Iterable[str], raw_lid_wh…` | 3-tier whitelist authorization for an inbound WhatsApp chat_id. | lib:noctusai_lib | 1 |
| `is_lid` | def | `(chat_id: str) -> bool` | True when ``chat_id`` is a WhatsApp linked-identity address. | lib:noctusai_lib, social-wiring | 2 |
| `is_phone_jid` | def | `(chat_id: str) -> bool` | True when ``chat_id`` is a phone-bearing JID (``@c.us`` / ``@s.whatsapp.net``). | lib:noctusai_lib | 1 |
| `normalize_phone` | def | `(value: str) -> str` | Reduce a phone / JID local-part to bare digits (no ``+``, no suffix). | lib:noctusai_lib, social-wiring | 2 |
| `remember_lid_phone` | def | `(cache: LidPhoneCache, *, lid_chat_id: str, resolved_remote:…` | Opportunistically bind a LID to its phone from an outbound send response. | lib:noctusai_lib | 1 |
| `resolve_canonical_session` | def | `(chat_id: str, cache: LidPhoneCache) -> str` | Canonical, surface-agnostic session key for a WhatsApp chat_id. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_send_text_body` | def | `(session: str, chat_id: str, text: str) -> dict[str, Any]` | Build the WAHA `/api/sendText` request body. | lib:noctusai_lib | 2 |
| `chat_id_for_phone` | def | `(phone: str) -> str` | Convert an E.164-style phone (`+5511999...`) to a WAHA `chatId` | lib:noctusai_lib, social-wiring | 3 |
| `extract_from_name` | def | `(payload: dict[str, Any]) -> str | None` |  | — | 0 |
| `extract_media` | def | `(payload: dict[str, Any]) -> WhatsAppMedia | None` |  | — | 0 |
| `extract_message_id` | def | `(payload: dict[str, Any]) -> str | None` |  | — | 0 |
| `first_text` | def | `(payload: dict[str, Any], *keys: str) -> str` |  | — | 0 |
| `is_own_or_api_message` | def | `(payload: dict[str, Any]) -> bool` |  | — | 0 |
| `parse_waha_inbound_message` | def | `(payload: dict[str, Any]) -> WhatsAppInboundMessage` | Parse a WAHA webhook payload into an `WhatsAppInboundMessage`. | lib:noctusai_lib | 2 |
| `phone_from_chat_id` | def | `(chat_id: str) -> str` | Inverse of `chat_id_for_phone`. | lib:noctusai_lib | 1 |
| `rewrite_vendor_media_url` | def | `(url: str, *, external_base_url: str, internal_base_url: str…` | Rewrite a WAHA-emitted media URL from its external host to the | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.whatsapp.meta_cloud_client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_BASE_URL` | const | `` |  | lib:noctusai_lib | 1 |
| `FakeMetaCloudClient` | class | `` | Deterministic in-memory Meta Cloud API stand-in. | lib:noctusai_lib | 1 |
| `MetaCloudClient` | class | `` | Meta WhatsApp Cloud API HTTP client (async send_text only). | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.response_registry`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeResponseRegistry` | class | `` | In-memory registry (no persistence). The Fake half. | lib:noctusai_lib | 1 |
| `PersistentResponseRegistry` | class | `` | Persists distinct shapes through an injected sink. The Real half. | lib:noctusai_lib | 1 |
| `ResponseRegistry` | class | `` | Records every distinct WAHA response shape exactly once. | lib:noctusai_lib | 1 |
| `ResponseSample` | class | `` | One observed WAHA response shape. | lib:noctusai_lib | 1 |
| `ResponseSampleSink` | class | `` | Storage seam the Real registry persists samples through. | lib:noctusai_lib | 1 |
| `fingerprint_response` | def | `(payload: Any) -> str` | Stable, vendor-neutral structural fingerprint of a JSON value. | lib:noctusai_lib | 1 |
| `get_response_registry` | def | `(*, sink: ResponseSampleSink | None=None) -> ResponseRegistr…` | Return `PersistentResponseRegistry` when a sink is supplied; | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_whatsapp_webhook_router` | def | `(settings: WhatsAppSettings, on_message: InboundHandler, *, …` | Build a FastAPI APIRouter that accepts WAHA inbound webhooks. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.settings`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `WhatsAppSettings` | class | `` | Configuration the WhatsApp module needs. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.whatsapp.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `WhatsAppClient` | class | `` | Send / download surface every WhatsApp connector implements. | lib:noctusai_lib, social-wiring | 2 |
| `WhatsAppIgnoredEvent` | class | `` | Inbound payload is structurally valid but the event type / source | lib:noctusai_lib | 3 |
| `WhatsAppInboundMessage` | class | `` | Parsed WhatsApp inbound message (provider-agnostic shape). | lib:noctusai_lib | 4 |
| `WhatsAppMedia` | class | `` | Media attachment on an inbound WhatsApp message. | lib:noctusai_lib | 2 |
| `WhatsAppPayloadError` | class | `` | Inbound payload failed validation (missing chat_id / no text or media). | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.youtube.classification`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ShortClassification` | class | `` | Result of :func:`classify_short`. | lib:noctusai_lib, social-wiring | 2 |
| `classify_short` | def | `(video: VideoFull) -> ShortClassification` | Classify a :class:`VideoFull` as a Short or a regular video. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.integrations.youtube.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_youtube_client` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Build a `YoutubeClient`. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.youtube.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeYoutubeClient` | class | `` | Deterministic in-memory `YoutubeClient` implementation. | lib:noctusai_lib, social-wiring | 7 |

### `noctusai_lib.integrations.youtube.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `YoutubeClient` | class | `` | YouTube Data API v3 client contract. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.integrations.youtube.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CHUNK_RETRY_BASE_DELAY_S` | const | `` |  | — | 0 |
| `CHUNK_RETRY_MAX_ATTEMPTS` | const | `` |  | — | 0 |
| `CHUNK_RETRY_MAX_DELAY_S` | const | `` |  | — | 0 |
| `RealYoutubeClient` | class | `` | Real YouTube Data API v3 client. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.youtube.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Channel` | class | `` | YouTube channel (the "owner" of uploaded videos). | lib:noctusai_lib | 4 |
| `ChannelInfo` | class | `` | Authenticated-channel metadata — wraps `channels.list?mine=True& | lib:noctusai_lib, social-wiring | 10 |
| `DESCRIPTION_MAX_LEN` | const | `` |  | lib:noctusai_lib | 1 |
| `ListResult` | class | `` | Paginated list response. | lib:noctusai_lib, social-wiring | 5 |
| `Playlist` | class | `` | YouTube playlist — minimal projection (id + title). | lib:noctusai_lib | 2 |
| `ProcessingStatus` | class | `` | YouTube post-upload processing state, mirroring | lib:noctusai_lib | 4 |
| `SHORTS_MAX_DURATION_SECONDS` | const | `` |  | lib:noctusai_lib | 2 |
| `TITLE_MAX_LEN` | const | `` |  | lib:noctusai_lib | 3 |
| `UPLOAD_QUOTA_UNITS` | const | `` |  | lib:noctusai_lib | 3 |
| `Video` | class | `` | YouTube video — flattened projection of `videos.list`. | lib:noctusai_lib | 4 |
| `VideoFull` | class | `` | Richer YouTube video projection — wraps `videos.list?part=snippet, | lib:noctusai_lib, social-wiring | 10 |
| `VideoUpload` | class | `` | Result of a `videos.insert` (resumable upload). | lib:noctusai_lib | 4 |

### `noctusai_lib.logging_config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `auto_configure_for_cli` | def | `(app_name: str='noctusai-cli', *, use_stderr: bool=False) ->…` | Configure logging for CLI / MCP-server entry-points. | — | 0 |
| `configure_logging` | def | `(debug: bool=True, json_logs: bool=False, app_name: str='noc…` | Configure application logging. | lib:noctusai_seed, personal-finance, therapy-platform | 3 |
| `resolve_json_logs` | def | `(default: bool) -> bool` | Tri-state resolution of ``NOCTUSAI_JSON_LOGS``: set-true / set-false / unset. | lib:noctusai_seed | 1 |

### `noctusai_lib.primitives._correlation`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_correlation_id` | def | `() -> str` | Return the current request's correlation ID (or `""` if unset). | lib:noctusai_lib | 2 |

### `noctusai_lib.primitives.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AppException` | class | `` | Base application exception with standardized error response. | lib:noctusai_lib, social-wiring | 11 |
| `ConflictError` | class | `` | Resource conflict (e.g., duplicate). | social-wiring | 10 |
| `ForbiddenError` | class | `` | Access denied. | — | 0 |
| `InternalError` | class | `` | Internal server error. | — | 0 |
| `NotFoundError` | class | `` | Resource not found. | lib:noctusai_lib, social-wiring | 29 |
| `UnauthorizedError` | class | `` | Authentication required. | — | 0 |
| `ValidationError_` | class | `` | Validation error for business logic. | lib:noctusai_lib, social-wiring | 31 |
| `app_exception_handler` | async def | `(request: Request, exc: AppException) -> JSONResponse` | Handle AppException and return standardized error response. | lib:noctusai_lib | 1 |
| `format_error_response` | def | `(code: str, message: str, details: Optional[dict]=None) -> d…` | Format a standardized error response. | — | 0 |
| `generic_exception_handler` | async def | `(request: Request, exc: Exception) -> JSONResponse` | Handle unexpected exceptions. | lib:noctusai_lib | 1 |
| `http_exception_handler` | async def | `(request: Request, exc: HTTPException) -> JSONResponse` | Handle FastAPI HTTPException and return standardized error response. | lib:noctusai_lib | 1 |
| `postgrest_exception_handler` | async def | `(request: Request, exc: Exception) -> JSONResponse` | Handle PostgREST APIError with proper status codes for common PG errors. | lib:noctusai_lib | 1 |
| `validation_exception_handler` | async def | `(request: Request, exc: ValidationError) -> JSONResponse` | Handle Pydantic ValidationError and return standardized error response. | lib:noctusai_lib | 1 |

### `noctusai_lib.primitives.image_sizing`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `EDGE_MULTIPLE` | const | `` |  | — | 0 |
| `MAX_ASPECT_RATIO` | const | `` |  | — | 0 |
| `MAX_EDGE_PX` | const | `` |  | — | 0 |
| `MAX_TOTAL_PIXELS` | const | `` |  | — | 0 |
| `MIN_ASPECT_RATIO` | const | `` |  | — | 0 |
| `MIN_TOTAL_PIXELS` | const | `` |  | — | 0 |
| `NON_EXPERIMENTAL_MAX_TOTAL_PIXELS` | const | `` |  | — | 0 |
| `compute_edit_size` | def | `(width: int, height: int) -> tuple[int, int]` | Return the largest ``(width, height)`` an OpenAI image-edit call | lib:noctusai_lib | 1 |
| `validate_size` | def | `(width: int, height: int) -> None` | Raise ``ValueError`` unless ``(width, height)`` is a size an | — | 0 |

### `noctusai_lib.primitives.parsing`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `format_brl` | def | `(value: Optional[Union[float, int]], *, decimals: int=2, wit…` | Format a numeric value in Brazilian Real notation. | erp-imobiliario, personal-finance | 3 |
| `parse_iso_or_400` | def | `(value: Optional[str]) -> Optional[datetime]` | Parse an ISO-8601 datetime string, raising HTTP 400 on invalid input. | core, lib:noctusai_seed | 2 |
| `parse_iso_or_none` | def | `(value: Optional[str]) -> Optional[datetime]` | Same as `parse_iso_or_400` but returns `None` on invalid input. | — | 0 |
| `safe_float` | def | `(text: Any, default: float=0.0) -> float` | Extract a float from messy text; return `default` on failure. | erp-imobiliario, personal-finance | 2 |
| `safe_json_loads` | def | `(raw: str) -> Optional[Union[list, dict]]` | Parse JSON tolerating ` ```json ... ``` ` markdown fences. | daily-life, social-wiring | 2 |

### `noctusai_lib.primitives.phone`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_COUNTRY_CODE` | const | `` |  | — | 0 |
| `format_phone` | def | `(raw: str | None, *, fallback: str | None=None) -> str | Non…` | THE display seam. Every phone rendered anywhere goes through here. | — | 0 |
| `is_valid_phone` | def | `(raw: str | None) -> bool` | ``True`` when ``raw`` canonicalizes. Use to flag rows, not to reject | — | 0 |
| `normalize_phone` | def | `(raw: str | None, *, default_country_code: str=DEFAULT_COUNT…` | Canonicalize any phone spelling to E.164, or ``None`` if it isn't one. | social-wiring | 3 |
| `phone_digits` | def | `(raw: str | None) -> str | None` | Digits of a canonical number, no ``+``. | erp-imobiliario | 1 |
| `phone_search_digits` | def | `(raw: str | None) -> str | None` | The digit-run to COMPARE when searching for a phone. | social-wiring | 2 |

### `noctusai_lib.primitives.responses`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PaginatedResponse` | class | `` | Standardized paginated response. | — | 0 |
| `PaginationMeta` | class | `` | Pagination metadata. | — | 0 |
| `calculate_pagination` | def | `(page: int, page_size: int, max_page_size: int=200) -> tuple…` | Calculate pagination parameters with validation. | core | 1 |
| `deleted_response` | def | `(resource: str, resource_id: str) -> dict` | Create a standardized deletion response. | social-wiring | 3 |
| `ok_response` | def | `(message: str='Operação realizada com sucesso') -> dict` | Create a simple success acknowledgment response. | core, daily-life | 5 |
| `paginated_response` | def | `(data: list, total: int, page: int, page_size: int) -> dict` | Create a standardized paginated response. | core, daily-life, social-wiring | 9 |
| `success_response` | def | `(data: Any, total: Optional[int]=None) -> dict` | Create a standardized success response. | core, daily-life, dev-team, social-wiring | 32 |

### `noctusai_lib.primitives.roles`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ADMIN_ROLES` | const | `` |  | igig, lib:noctusai_seed | 2 |
| `DEV_ROLES` | const | `` |  | lib:noctusai_lib, lib:noctusai_seed | 2 |
| `MANAGE_TEAM_ROLES` | const | `` |  | lib:noctusai_lib | 1 |
| `ORG_ROLES` | const | `` |  | — | 0 |
| `ORG_ROLE_LABELS` | const | `` |  | lib:noctusai_seed | 1 |
| `PRODUCT_ADMIN_ROLES` | const | `` |  | — | 0 |
| `can_manage_billing` | def | `(org_role: str | None) -> bool` | Check if the user can manage billing/subscription. | — | 0 |
| `can_manage_team` | def | `(org_role: str | None) -> bool` | Check if the user can invite/remove team members. | — | 0 |
| `is_dev_or_owner` | def | `(org_role: str | None) -> bool` | Check if the user can see in-development pages. | — | 0 |

### `noctusai_lib.primitives.tasks`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `NoRunningLoopError` | class | `` | Raised when `schedule_coro` is called outside a running event loop. | core | 1 |
| `schedule_coro` | def | `(coro: Coroutine[Any, Any, Any], *, logger: Optional[logging…` | Schedule `coro` on the running event loop, fire-and-forget. | core, erp-imobiliario, social-wiring | 5 |

### `noctusai_lib.primitives.timeutil`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `current_day_ref` | def | `() -> str` | Return the current UTC day reference, formatted ``YYYY-MM-DD``. | erp-imobiliario | 4 |
| `current_month_ref` | def | `() -> str` | Return the current UTC month reference, formatted ``YYYY-MM``. | erp-imobiliario | 5 |
| `frozen_time` | def | `(value: datetime) -> Iterator[None]` | Freeze wallclock to ``value`` for the duration of the with-block. | — | 0 |
| `now_utc` | def | `() -> datetime` | Return the current wallclock as an aware UTC `datetime`. | erp-imobiliario, lib:noctusai_lib, personal-finance | 7 |
| `now_utc_iso` | def | `() -> str` | Return the current wallclock as an ISO 8601 string with UTC offset. | adconnect, core | 4 |
| `today_utc` | def | `() -> date` | Return the current wallclock as a UTC `date` (no time, no tz). | erp-imobiliario | 4 |

### `noctusai_lib.realtime.bus`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeRealtimeBus` | class | `` | In-memory `RealtimeBus` — the Fake half. Deterministic, no | agents, lib:noctusai_lib, social-wiring | 3 |
| `RealtimeBus` | class | `` | The provider-neutral realtime transport seam. Every live surface — | agents, lib:noctusai_lib, social-wiring | 5 |
| `RealtimeEvent` | class | `` | One event on the bus. `id` is monotonic + sortable within a scope, | lib:noctusai_lib | 2 |
| `RedisRealtimeBus` | class | `` | Redis-Streams-backed `RealtimeBus` — the Real half. | lib:noctusai_lib | 1 |
| `StreamRedis` | class | `` | The minimal (sync) redis-py surface `RedisRealtimeBus` needs — | lib:noctusai_lib | 1 |
| `get_realtime_bus` | def | `(redis_url: str | None=None, *, redis_client: StreamRedis | …` | Return `RedisRealtimeBus` when a Redis client/url is supplied; | agents, lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.realtime.sse`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_sse_router` | def | `(bus: RealtimeBus, *, scope_resolver: ScopeResolver, auth_de…` | Build a FastAPI `APIRouter` exposing `bus` as `text/event-stream`. | agents, lib:noctusai_lib, social-wiring | 4 |
| `sse_event_stream` | async def | `(bus: RealtimeBus, scope: str, *, last_event_id: str | None=…` | Turn a `bus.subscribe(scope, ...)` stream into SSE text frames. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.app_config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AppConfigDecryptError` | class | `` | Raised when a stored config row exists but cannot be decrypted. | lib:noctusai_lib | 1 |
| `AppConfigStore` | class | `` | App-wide encrypted key→value config persistence. | lib:noctusai_lib, social-wiring | 2 |
| `DEFAULT_TABLE` | const | `` |  | — | 0 |
| `FakeAppConfigStore` | class | `` | Process-memory app-config store keyed by ``key``. | lib:noctusai_lib, social-wiring | 4 |
| `META_APP_ID_KEY` | const | `` |  | social-wiring | 1 |
| `META_APP_SECRET_KEY` | const | `` |  | social-wiring | 1 |
| `RealAppConfigStore` | class | `` | Supabase-backed `AppConfigStore` — Fernet-encrypted rows at rest. | lib:noctusai_lib, social-wiring | 2 |
| `build_app_config_store` | def | `(*, client=None, fernet_key: Optional[bytes]=None, table: st…` | Real when ``client`` AND ``fernet_key`` are set; else Fake. | lib:noctusai_lib, social-wiring | 2 |
| `resolve_meta_app_credentials` | def | `(store: AppConfigStore, *, env_app_id: Optional[str], env_ap…` | Resolve the Meta App ID/Secret pair: DB value wins, env is fallback. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.security.encrypted_tokens`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MultiKeyDecryptor` | class | `` | Try a sequence of keys on decrypt, in order; first success wins. | lib:noctusai_lib | 2 |
| `decrypt` | def | `(ciphertext: str, key: bytes) -> str` | Decrypt `ciphertext` with `key`, returning the original plaintext. | igig, lib:noctusai_lib | 4 |
| `encrypt` | def | `(plaintext: str, key: bytes) -> str` | Encrypt `plaintext` with `key`, returning url-safe-base64 ciphertext. | igig, lib:noctusai_lib | 6 |
| `generate_key` | def | `() -> bytes` | Generate a fresh Fernet key. | lib:noctusai_lib | 1 |
| `rotate_key` | def | `(ciphertext: str, old_key: bytes, new_key: bytes) -> str` | Decrypt with `old_key` and re-encrypt with `new_key`. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_oauth_provider` | def | `(name: str, *, use_fake: bool=False, client_id: str | None=N…` | Resolve a vendor name to a concrete `OAuthProvider` instance. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeOAuthProvider` | class | `` | Deterministic OAuth provider for tests + FakeMode. | lib:noctusai_lib, social-wiring | 13 |

### `noctusai_lib.security.oauth.google_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GOOGLE_AUTH_URL` | const | `` |  | — | 0 |
| `GOOGLE_REVOKE_URL` | const | `` |  | — | 0 |
| `GOOGLE_TOKEN_URL` | const | `` |  | — | 0 |
| `GoogleProvider` | class | `` | Google OAuth 2.0 provider. | lib:noctusai_lib, social-wiring | 4 |

### `noctusai_lib.security.oauth.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OAuthProvider` | class | `` | The contract every OAuth provider satisfies. | lib:noctusai_lib | 3 |

### `noctusai_lib.security.oauth.router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `oauth_router` | def | `(*providers: OAuthProvider, on_callback: CallbackHook | None…` | Build an APIRouter exposing the OAuth dance for `providers`. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.scopes`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeScopeResolver` | class | `` | Deterministic `ScopeResolver` for tests + FakeMode. | lib:noctusai_lib | 1 |
| `GoogleScopeResolver` | class | `` | Google `ScopeResolver` — delegates to `integrations.google_scopes`. | lib:noctusai_lib | 1 |
| `MetaScopeResolver` | class | `` | Meta `ScopeResolver` — delegates to `integrations.meta._meta_api`. | lib:noctusai_lib | 1 |
| `ScopeResolver` | class | `` | One scope-resolution contract every OAuth provider satisfies. | lib:noctusai_lib | 1 |
| `make_scope_resolver` | def | `(provider: str, *, use_fake: bool=False, kitchen_sink: list[…` | Resolve a provider name to a concrete `ScopeResolver`. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthorizationURL` | class | `` | The URL to redirect the user to for provider consent. | lib:noctusai_lib | 4 |
| `OAuthCallbackResult` | class | `` | The outcome of an OAuth callback round-trip. | lib:noctusai_lib | 3 |
| `TokenSet` | class | `` | Tokens returned by an OAuth token-endpoint exchange. | lib:noctusai_lib | 4 |

### `noctusai_lib.security.secrets_scan`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `find_secret` | def | `(content: str) -> str | None` | Return the NAME of the first secret pattern ``content`` trips, or | lib:noctusai_lib | 1 |
| `has_secret` | def | `(content: str) -> bool` | Boolean convenience wrapper over :func:`find_secret`. | academia-de-reciclagem, lib:noctusai_lib | 2 |

### `noctusai_lib.security.token_store.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeCredentialStore` | class | `` | Process-memory credential store keyed by ``(org_id, provider)``. | lib:noctusai_lib, social-wiring | 5 |

### `noctusai_lib.security.token_store.supabase_store`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_TABLE` | const | `` |  | lib:noctusai_lib | 1 |
| `SupabaseCredentialStore` | class | `` | Encrypted-at-rest credential persistence over a Supabase client. | lib:noctusai_lib, social-wiring | 3 |

### `noctusai_lib.security.token_store.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CredentialDecryptError` | class | `` | Raised when a stored row exists but cannot be decrypted. | lib:noctusai_lib, p-studio, social-wiring | 5 |
| `CredentialStore` | class | `` | Per-(org, provider) encrypted credential persistence. | lib:noctusai_lib, p-studio, social-wiring | 8 |
| `StoredCredential` | class | `` | A decrypted credential bundle for one ``(org_id, provider)`` pair. | lib:noctusai_lib, p-studio, social-wiring | 7 |

### `noctusai_lib.security.webhook_signatures`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_MAX_AGE_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `GRUPO_OLX_BASIC_USERNAME` | const | `` |  | lib:noctusai_lib | 1 |
| `ResolvedSecret` | class | `` | Returned by a `SecretResolver`: the per-request secret plus optional context. | erp-imobiliario, igig, lib:noctusai_lib, orbity, seed, social-wiring | 12 |
| `VerifiedWebhook` | class | `` | Yielded by `webhook_endpoint` after the dependency runs. | erp-imobiliario, igig, lib:noctusai_lib, orbity, seed, social-wiring | 12 |
| `compute_hmac_sha256_hex` | def | `(body: bytes, secret: str) -> str` | Hex-encoded HMAC-SHA256 of `body` keyed with `secret`. | core, lib:noctusai_lib, social-wiring | 3 |
| `static_secret_resolver` | def | `(secret: Optional[str]) -> SecretResolver` | Resolver for the simple case where the secret is fixed at boot. | lib:noctusai_lib | 1 |
| `verify_basic_shared_secret` | def | `(header_value: str, secret: str, *, expected_username: Optio…` | Verify an `Authorization: Basic base64("<user>:<secret>")` header. | lib:noctusai_lib | 1 |
| `verify_hmac_sha256` | def | `(body: bytes, signature: str, secret: str, *, timestamp_valu…` | Verify a `sha256=<hex>`-style signature header. | lib:noctusai_lib | 1 |
| `verify_hmac_sha256_hex` | def | `(body: bytes, signature_hex: str, secret: str, *, timestamp_…` | Verify a bare-hex HMAC-SHA256 signature (no `sha256=` prefix). | lib:noctusai_lib | 2 |
| `verify_svix_signature` | def | `(*, svix_id: str, svix_timestamp: str, body: bytes, signatur…` | Verify a Svix-protocol webhook signature (Resend and similar). | lib:noctusai_lib | 1 |
| `webhook_endpoint` | def | `(*, secret_resolver: SecretResolver, scheme: WebhookScheme='…` | Build a FastAPI dependency that verifies an inbound webhook signature. | erp-imobiliario, igig, lib:noctusai_lib, orbity, seed, social-wiring | 12 |

### `noctusai_lib.sql.prelude`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `prelude` | def | `(schema: str) -> str` | Return the top-of-migration prelude string for ``schema``. | — | 0 |

### `noctusai_lib.sql.service_role_bypass`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `service_role_bypass` | def | `(table: str, schema: str='public') -> str` | Return the canonical ``service_role_bypass`` policy SQL for one table. | — | 0 |

### `noctusai_lib.sql.triggers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `updated_at_function` | def | `(schema: str, *, function_name: str='set_updated_at') -> str` | Emit ``CREATE OR REPLACE FUNCTION <schema>.<function_name>()``. | — | 0 |
| `updated_at_trigger` | def | `(table: str, *, schema: str | None=None, function_name: str=…` | Emit the BEFORE-UPDATE trigger (and optionally its function) for ``table``. | — | 0 |

### `noctusai_lib.testing._schema_cache`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_schema_map` | def | `() -> dict[str, set[str]]` | Return the cached `{qualified_table: {columns}}` map. Builds on first call. | lib:noctusai_lib | 2 |
| `reset_cache` | def | `() -> None` | Force the next get_schema_map() call to rebuild. Used by tests that | lib:noctusai_lib | 1 |
| `set_cache_for_tests` | def | `(mapping: dict[str, set[str]] | dict[str, Iterable[str]]) ->…` | Inject a cache directly. Used by unit tests for MockSupabaseClient | lib:noctusai_lib | 1 |

### `noctusai_lib.testing.assertions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `assert_error_contains` | def | `(response: Any, expected_substring: str) -> None` | Assert the response body's error message contains `expected_substring`. | lib:noctusai_lib, therapy-platform | 2 |

### `noctusai_lib.testing.clients`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthClient` | class | `` | Wraps FastAPI TestClient with automatic Authorization header. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, lib:noctusai_lib, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 18 |
| `MockUser` | class | `` | Simulates a Supabase auth user object. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, lib:noctusai_lib, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 38 |
| `MockUserResponse` | class | `` | Wraps MockUser to simulate supabase.auth.get_user() response. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, lib:noctusai_lib, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 37 |
| `TEST_ORG_ID` | const | `` |  | lib:noctusai_lib | 2 |
| `TEST_USER_ID` | const | `` |  | agents, lib:noctusai_lib | 3 |
| `bind_user_metadata` | def | `(mock_sb_or_client: Any, *, user: Optional[MockUser]=None, r…` | Re-bind ``mock_sb.auth.get_user`` to return a fresh ``MockUser``. | adconnect, lib:noctusai_lib | 2 |

### `noctusai_lib.testing.conftest_helpers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `own_test_env` | def | `(values: 'dict[str, str]', clear: 'tuple[str, ...] | list[st…` | Force the suite's environment to exactly what the suite declares. | — | 0 |
| `purge_shadowing_editable_finders` | def | `(local_lib_root: Path, package_names: Iterable[str]=_DEFAULT…` | Drop meta-path finders whose mapping for a guarded package points outside *that … | lib:noctusai_lib | 1 |
| `restore_real_llm_providers` | def | `() -> None` | Re-register the REAL LLM providers, discarding every test double. | — | 0 |

### `noctusai_lib.testing.consent`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `bind_consent_module_to_mock` | def | `(mock_sb: Any) -> None` | Wire the consent module's FastAPI deps to a mock Supabase client. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, lib:noctusai_lib, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 40 |

### `noctusai_lib.testing.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `patch_credentials_to_mock` | def | `(mock_sb: Any) -> _patch` | Return an unstarted patcher that points the credentials module's | erp-imobiliario, lib:noctusai_lib | 4 |

### `noctusai_lib.testing.fixtures`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `reset_rate_limiter` | def | `()` | Reset the slowapi limiter between tests. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, knowledge-extractor, lib:noctusai_lib, orbity, personal-finance, seed, social-wiring, therapy-platform | 15 |

### `noctusai_lib.testing.framework_test_suites`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthBoundarySuite` | class | `` | Every protected framework endpoint must return 401 without auth. | academia-de-reciclagem, adconnect, agents, igig, lib:noctusai_lib, orbity, p-studio, seed | 8 |
| `FrameworkEndpointsSuite` | class | `` | All framework-provided endpoints must exist and respond. | academia-de-reciclagem, adconnect, agents, igig, lib:noctusai_lib, orbity, p-studio, seed | 8 |
| `HealthCheckSuite` | class | `` | GET /api/health — public endpoint provided by the seed framework. | academia-de-reciclagem, adconnect, agents, daily-life, igig, lib:noctusai_lib, orbity, seed, social-wiring | 9 |
| `NotificationFlowSuite` | class | `` | Notification proxying through the framework's standard router. | academia-de-reciclagem, adconnect, agents, igig, lib:noctusai_lib, orbity, p-studio, seed | 8 |
| `TeamFlowSuite` | class | `` | Authenticated team-management flow through the framework router. | academia-de-reciclagem, adconnect, agents, daily-life, igig, lib:noctusai_lib, orbity, p-studio, seed | 9 |
| `TeamRouterInviteSuite` | class | `` | POST /api/team/invite — framework's team-invite endpoint. | academia-de-reciclagem, adconnect, agents, igig, lib:noctusai_lib, orbity, seed, social-wiring | 8 |
| `TeamRouterListMembersSuite` | class | `` | GET /api/team — framework's team-list endpoint. | academia-de-reciclagem, adconnect, agents, igig, lib:noctusai_lib, orbity, seed, social-wiring | 8 |
| `TeamRouterRemoveMemberSuite` | class | `` | DELETE /api/team/{user_id} — framework's team-remove endpoint. | academia-de-reciclagem, adconnect, agents, igig, lib:noctusai_lib, orbity, seed, social-wiring | 8 |

### `noctusai_lib.testing.migration_parser`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `parse_files` | def | `(paths: Iterable[Path]) -> dict[str, set[str]]` | Parse multiple migration files in order, merging into one schema map. | lib:noctusai_lib | 1 |
| `parse_sql` | def | `(sql: str, *, source_label: str='<unknown>', into: dict[str,…` | Parse a blob of SQL into a `{qualified_table: {columns}}` map. | social-wiring | 2 |

### `noctusai_lib.testing.mocks`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MockFilterBuilder` | class | `` | Mirrors SyncFilterRequestBuilder. | academia-de-reciclagem, adconnect, agents, core, daily-life, erp-imobiliario, igig, lib:noctusai_lib, orbity, personal-finance, seed, social-wiring, therapy-platform | 13 |
| `MockQueryBuilder` | class | `` | Mirrors SyncQueryRequestBuilder. | academia-de-reciclagem, adconnect, agents, core, daily-life, erp-imobiliario, igig, lib:noctusai_lib, orbity, personal-finance, seed, social-wiring, therapy-platform | 13 |
| `MockRequestBuilder` | class | `` | Mirrors SyncRequestBuilder — the object returned by .table(name). | academia-de-reciclagem, adconnect, agents, core, daily-life, erp-imobiliario, igig, lib:noctusai_lib, orbity, personal-finance, seed, social-wiring, therapy-platform | 15 |
| `MockSelectBuilder` | class | `` | Mirrors SyncSelectRequestBuilder. | academia-de-reciclagem, adconnect, agents, core, daily-life, erp-imobiliario, igig, lib:noctusai_lib, orbity, personal-finance, seed, social-wiring, therapy-platform | 14 |
| `MockSupabaseClient` | class | `` | Mocked Supabase client with per-table data control and response queues. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, lib:noctusai_lib, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 73 |
| `MockSupabaseResponse` | class | `` | Simulates a Supabase PostgREST response. | academia-de-reciclagem, adconnect, agents, core, daily-life, erp-imobiliario, igig, lib:noctusai_lib, orbity, personal-finance, seed, social-wiring, therapy-platform | 37 |

### `noctusai_lib.testing.pytest_plugin`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `pytest_configure` | def | `(config) -> None` | Probe for `app.main` and import it to load the consent catalog. | — | 0 |

### `noctusai_lib.testing.schema_errors`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MockCheckViolation` | class | `` | Raised when a mock INSERT/UPDATE writes a CHECK-violating literal. | lib:noctusai_lib | 2 |
| `MockSchemaError` | class | `` | Raised when a mock call references a column not in the schema cache. | lib:noctusai_lib | 2 |
| `MockUnknownTableError` | class | `` | Raised when a mock call references a table that does not appear in any | lib:noctusai_lib | 2 |

### `noctusai_lib.testing.seed_singleton_guard`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SingletonSpec` | class | `` | One leak-prone process-global the guard snapshots/restores. | lib:noctusai_lib | 1 |
| `guarded_seed_singletons` | def | `(specs: Sequence[SingletonSpec]=DEFAULT_SPECS) -> Iterator[_…` | Context manager: snapshot on enter, restore on exit. | lib:noctusai_lib | 1 |
| `make_seed_singleton_guard` | def | `(*, extra_specs: Iterable[SingletonSpec]=())` | Build an autouse ``seed_singleton_guard`` fixture. | lib:noctusai_lib | 1 |
| `restore_seed_singletons` | def | `(snap: _Snapshot, specs: Sequence[SingletonSpec]) -> None` | Restore state captured in *snap* for *specs*. | lib:noctusai_lib | 1 |
| `snapshot_seed_singletons` | def | `(specs: Sequence[SingletonSpec]) -> _Snapshot` | Capture current state for *specs*. | lib:noctusai_lib | 1 |

### `noctusai_seed.ai_feedback_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FeedbackBody` | class | `` |  | — | 0 |
| `create_ai_feedback_router` | def | `(deps) -> APIRouter` | Build the `/api/ai/feedback` router for a product. | lib:noctusai_seed | 1 |

### `noctusai_seed.ai_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_ai_outputs_router` | def | `(deps) -> APIRouter` | Build the `/api/ai/outputs` router for a product. | lib:noctusai_seed | 1 |

### `noctusai_seed.app`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_product_app` | def | `(name: str, schema: str, settings, routers: Optional[list]=N…` | Create a fully configured FastAPI app for a NoctusAI product. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, knowledge-extractor, lib:noctusai_seed, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 20 |

### `noctusai_seed.apply_sqlite_migrations`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `apply_sqlite_migrations` | def | `(settings, *, base_dir: Optional[Path]=None) -> Path` | Create (idempotently) the local-dev SQLite file + bootstrap rows. | lib:noctusai_seed | 2 |
| `resolve_sqlite_path` | def | `(settings, *, base_dir: Optional[Path]=None) -> Path` | Resolve the absolute SQLite file path from settings. | — | 0 |

### `noctusai_seed.auth_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ApiTokenCreateRequest` | class | `` |  | erp-imobiliario | 4 |
| `ApiTokenCreatedDTO` | class | `` | Returned ONCE at mint time — caller MUST persist the secret. | — | 0 |
| `ApiTokenListItem` | class | `` |  | — | 0 |
| `LoginOrgDTO` | class | `` |  | — | 0 |
| `LoginRequest` | class | `` |  | — | 0 |
| `LoginResponse` | class | `` |  | — | 0 |
| `LoginUserDTO` | class | `` |  | — | 0 |
| `MeResponse` | class | `` |  | — | 0 |
| `create_auth_router` | def | `(deps, settings, *, api_token_resolver: Optional[ApiTokenRes…` | Build the combined ``/api/auth`` + ``/api/settings/api-tokens`` router. | academia-de-reciclagem, agents, lib:noctusai_seed, social-wiring | 4 |
| `get_session_revoker` | def | `(settings) -> SessionRevoker` | Process-local ``SessionRevoker`` singleton for ``settings`` (SEC-4). | — | 0 |
| `get_session_store` | def | `(settings) -> SessionStore` | Process-local ``SessionStore`` singleton for ``settings``. | academia-de-reciclagem, agents, erp-imobiliario, social-wiring | 5 |

### `noctusai_seed.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductSettings` | class | `` | Base settings that every product inherits. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, knowledge-extractor, lib:noctusai_seed, orbity, p-studio, personal-finance, seed, social-wiring, therapy-platform | 16 |
| `make_get_settings` | def | `(settings_instance)` | Factory that creates a product-specific ``get_settings`` FastAPI dependency. | agents, lib:noctusai_seed, social-wiring | 3 |

### `noctusai_seed.database`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DatabaseModule` | class | `` | Encapsulates database client factories for a product schema. | — | 0 |
| `create_database_module` | def | `(settings, schema: str) -> DatabaseModule` | Factory to create database module for a product. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, knowledge-extractor, lib:noctusai_seed, orbity, personal-finance, seed, social-wiring, therapy-platform | 28 |

### `noctusai_seed.dependencies`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductDependencies` | class | `` | Encapsulates standard FastAPI dependencies for a product. | — | 0 |
| `create_dependencies` | def | `(db) -> ProductDependencies` | Factory to create standard dependencies for a product. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, knowledge-extractor, lib:noctusai_seed, orbity, personal-finance, seed, social-wiring, therapy-platform | 16 |

### `noctusai_seed.dev_auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEV_TOKEN` | const | `` |  | — | 0 |
| `DEV_USER_EMAIL` | const | `` |  | — | 0 |
| `dev_auth_enabled` | def | `(settings) -> bool` | True only when the explicit dev-auth flag is on AND debug is on. | lib:noctusai_seed | 1 |
| `make_dev_auth_get_current_user` | def | `(settings, *, user_id: Optional[str]=None, org_id: Optional[…` | Factory → a ``get_current_user``-shaped dependency for dev mode. | lib:noctusai_seed | 1 |
| `select_get_current_user` | def | `(settings, prod_get_current_user)` | Pick the dev-auth dependency over the prod one when the local | academia-de-reciclagem, agents, igig, knowledge-extractor, lib:noctusai_seed, orbity, seed | 7 |

### `noctusai_seed.health`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `HealthCheckHook` | class | `` | Async callable that reports whether one piece of infrastructure is healthy. | lib:noctusai_seed | 1 |
| `HealthEndpointConfig` | class | `` | Configuration for the seed-baked ``/_health`` + ``/_ready`` endpoints. | agents, dev-team, lib:noctusai_seed, personal-finance | 5 |
| `mount_health_endpoints` | def | `(app: FastAPI, config: HealthEndpointConfig) -> None` | Register ``/_health`` + ``/_ready`` on the given FastAPI app. | lib:noctusai_seed | 2 |

### `noctusai_seed.llm_defaults`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_LLM_CONFIG` | const | `` |  | lib:noctusai_seed | 1 |
| `default_llm_config` | def | `(*, redis_url: str | None=None, usage_tracking_db: Any=None,…` | Build an LLMConfig using platform defaults, with optional overrides. | lib:noctusai_seed | 2 |

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
| `create_product_limiter` | def | `(settings)` | Create a rate limiter using the product's settings. | academia-de-reciclagem, adconnect, agents, core, daily-life, dev-team, erp-imobiliario, igig, knowledge-extractor, orbity, personal-finance, seed, social-wiring, therapy-platform | 14 |

### `noctusai_seed.routers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_standard_routers` | def | `(deps, settings, product_name: str, version: str, names: Seq…` | Return the subset of standard routers named by `names`. | lib:noctusai_seed | 1 |

### `noctusai_seed.scheduler_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SchedulerJobDTO` | class | `` | Boundary DTO for an APScheduler job — leaks none of APScheduler's | — | 0 |
| `create_scheduler_router` | def | `(deps) -> APIRouter` | Build the `/api/scheduler` router for a product. | lib:noctusai_seed | 1 |

### `noctusai_seed.status_pagina_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StatusPaginaOut` | class | `` | Response shape for a ``status_pagina`` row. | — | 0 |
| `StatusPaginaUpdate` | class | `` | PATCH body — change the status only. | — | 0 |

### `noctusai_seed.upload_route_overrides`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `enforce_upload_route_overrides` | def | `(app: FastAPI, max_body_path_overrides: Optional[Mapping[str…` | Raise `RuntimeError` — refuse to finish booting — if any route | lib:noctusai_seed | 1 |
| `find_uncovered_upload_routes` | def | `(app: FastAPI, max_body_path_overrides: Optional[Mapping[str…` | Walk every route currently mounted on `app`; return one | — | 0 |

### `noctusai_seed.whatsapp_admin_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ConnectionStatusDTO` | class | `` | Boundary DTO for the WAHA session — no raw WAHA envelope leaks. | — | 0 |
| `QrDTO` | class | `` | QR pairing payload. | — | 0 |
| `WebhookConfigRequest` | class | `` |  | — | 0 |
| `WebhookResult` | class | `` |  | — | 0 |
| `create_whatsapp_admin_router` | def | `(deps, settings) -> APIRouter` | Build the `/api/whatsapp/connection` router. | lib:noctusai_seed | 1 |

## Orphans

Symbols defined in the lib but with **zero importers** across all products.
Candidates for deletion — but confirm first (may be staged for imminent use,
or intentionally-public for future consumers).

| Symbol | Kind | Location |
|---|---|---|
| `noctusai_lib.SSOSessionCache` | class | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:824` |
| `noctusai_lib.SSO_AUDIENCE` | const | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:77` |
| `noctusai_lib.SSO_ISSUER` | const | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:76` |
| `noctusai_lib.create_sso_token_factory` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:742` |
| `noctusai_lib.first_or_none` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:92` |
| `noctusai_lib.get_calendar_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/google_calendar/__init__.py:51` |
| `noctusai_lib.get_docx_render_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/docx_render/__init__.py:62` |
| `noctusai_lib.get_fx_rate_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/fx/__init__.py:35` |
| `noctusai_lib.get_image_edit_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/image_edit/__init__.py:100` |
| `noctusai_lib.get_image_gen_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/image_gen/__init__.py:56` |
| `noctusai_lib.get_imaging_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/imaging/__init__.py:61` |
| `noctusai_lib.get_mailchimp_client` | def | `seed/lib/backend/noctusai_lib/integrations/mailchimp/__init__.py:53` |
| `noctusai_lib.get_media_resolver` | def | `seed/lib/backend/noctusai_lib/integrations/media/__init__.py:55` |
| `noctusai_lib.get_meta_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/meta/__init__.py:181` |
| `noctusai_lib.get_meta_cloud_client` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/__init__.py:145` |
| `noctusai_lib.get_n8n_client` | def | `seed/lib/backend/noctusai_lib/integrations/n8n/__init__.py:72` |
| `noctusai_lib.get_record_store` | def | `seed/lib/backend/noctusai_lib/integrations/persistence/__init__.py:75` |
| `noctusai_lib.get_routing_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/google_maps/__init__.py:35` |
| `noctusai_lib.get_sso_context` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:237` |
| `noctusai_lib.get_svg_render_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/svg_render/__init__.py:58` |
| `noctusai_lib.get_whatsapp_client` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/__init__.py:116` |
| `noctusai_lib.make_credential_store` | def | `seed/lib/backend/noctusai_lib/security/token_store/__init__.py:56` |
| `noctusai_lib.make_get_current_user` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:170` |
| `noctusai_lib.make_get_current_user_org` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:507` |
| `noctusai_lib.make_require_role` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:260` |
| `noctusai_lib.make_resolve_platform_role` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:413` |
| `noctusai_lib.require_credential_or_422` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:671` |
| `noctusai_lib.resolve_sso_role` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:194` |
| `noctusai_lib.resvg_available` | def | `seed/lib/backend/noctusai_lib/integrations/svg_render/__init__.py:49` |
| `noctusai_lib.verify_sso_token_factory` | def | `seed/lib/backend/noctusai_lib/api/auth/__init__.py:788` |
| `noctusai_lib.api.auth.platform.require_org_admin` | def | `seed/lib/backend/noctusai_lib/api/auth/platform.py:133` |
| `noctusai_lib.api.auth.platform.require_permission` | def | `seed/lib/backend/noctusai_lib/api/auth/platform.py:223` |
| `noctusai_lib.api.auth.platform.require_platform_admin` | def | `seed/lib/backend/noctusai_lib/api/auth/platform.py:87` |
| `noctusai_lib.api.auth.platform.resolve_platform_admin_role` | def | `seed/lib/backend/noctusai_lib/api/auth/platform.py:45` |
| `noctusai_lib.api.scheduler.SCHEDULERS_ENABLED_ENV` | const | `seed/lib/backend/noctusai_lib/api/scheduler.py:200` |
| `noctusai_lib.api.scheduler.register` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:120` |
| `noctusai_lib.api.scheduler.reset_for_testing` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:299` |
| `noctusai_lib.api.scheduler.schedulers_enabled` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:205` |
| `noctusai_lib.api.scheduler.start_scheduler` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:221` |
| `noctusai_lib.api.scheduler.stop_scheduler` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:292` |
| `noctusai_lib.components.validation_signal.compute_signal_inputs` | def | `seed/lib/backend/noctusai_lib/components/validation_signal.py:157` |
| `noctusai_lib.components.validation_signal.derive_validation_status` | def | `seed/lib/backend/noctusai_lib/components/validation_signal.py:85` |
| `noctusai_lib.config.cors_registry.NATIVE_DEV_ENV` | const | `seed/lib/backend/noctusai_lib/config/cors_registry.py:174` |
| `noctusai_lib.config.cors_registry.ProductEntry` | class | `seed/lib/backend/noctusai_lib/config/cors_registry.py:77` |
| `noctusai_lib.config.deploy_config.resolve_config` | def | `seed/lib/backend/noctusai_lib/config/deploy_config.py:128` |
| `noctusai_lib.config.settings.BaseAppSettings` | class | `seed/lib/backend/noctusai_lib/config/settings.py:15` |
| `noctusai_lib.domain.ai.consent.AIConsentRequired` | class | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:51` |
| `noctusai_lib.domain.ai.consent.ConsentFeature` | class | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:102` |
| `noctusai_lib.domain.ai.consent.MandatoryFeatureCannotBeToggled` | class | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:72` |
| `noctusai_lib.domain.ai.consent.consent_required` | def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:428` |
| `noctusai_lib.domain.ai.consent.fetch_user_decisions` | async def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:200` |
| `noctusai_lib.domain.ai.consent.get_catalog` | def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:178` |
| `noctusai_lib.domain.ai.consent.is_consent_module_configured` | def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:417` |
| `noctusai_lib.domain.ai.consent.is_granted` | async def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:218` |
| `noctusai_lib.domain.ai.consent.require` | async def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:243` |
| `noctusai_lib.domain.ai.consent.reset_consent_module_for_test` | def | `seed/lib/backend/noctusai_lib/domain/ai/consent.py:421` |
| `noctusai_lib.domain.ai.outputs.AIOutput` | class | `seed/lib/backend/noctusai_lib/domain/ai/outputs.py:48` |
| `noctusai_lib.domain.ai.outputs.fetch_outputs_for` | def | `seed/lib/backend/noctusai_lib/domain/ai/outputs.py:123` |
| `noctusai_lib.domain.ai.outputs.persist_output` | def | `seed/lib/backend/noctusai_lib/domain/ai/outputs.py:97` |
| `noctusai_lib.domain.ai.outputs.safe_persist_indicator` | def | `seed/lib/backend/noctusai_lib/domain/ai/outputs.py:147` |
| `noctusai_lib.domain.chatbot.llm_dispatcher.DEFAULT_FALLBACK_REPLY` | const | `seed/lib/backend/noctusai_lib/domain/chatbot/llm_dispatcher.py:38` |
| `noctusai_lib.domain.chatbot.openai_orchestrator.DEFAULT_FALLBACK_REPLY` | const | `seed/lib/backend/noctusai_lib/domain/chatbot/openai_orchestrator.py:76` |
| `noctusai_lib.domain.chatbot.openai_orchestrator.MAX_MEMORY_ITEMS` | const | `seed/lib/backend/noctusai_lib/domain/chatbot/openai_orchestrator.py:75` |
| `noctusai_lib.domain.chatbot.openai_orchestrator.MEMORY_PREFIX` | const | `seed/lib/backend/noctusai_lib/domain/chatbot/openai_orchestrator.py:73` |
| `noctusai_lib.domain.chatbot.openai_orchestrator.MEMORY_TTL_SECONDS` | const | `seed/lib/backend/noctusai_lib/domain/chatbot/openai_orchestrator.py:74` |
| `noctusai_lib.domain.digest.base.BaseDigestService` | class | `seed/lib/backend/noctusai_lib/domain/digest/base.py:82` |
| `noctusai_lib.domain.digest.orchestrate.build_and_send` | async def | `seed/lib/backend/noctusai_lib/domain/digest/orchestrate.py:19` |
| `noctusai_lib.domain.digest.render.email_template_dir` | def | `seed/lib/backend/noctusai_lib/domain/digest/render.py:31` |
| `noctusai_lib.domain.digest.render.render_digest_pair` | def | `seed/lib/backend/noctusai_lib/domain/digest/render.py:84` |
| `noctusai_lib.domain.digest.render.render_with_narrative` | def | `seed/lib/backend/noctusai_lib/domain/digest/render.py:45` |
| `noctusai_lib.domain.fleet_control.ActResult` | class | `seed/lib/backend/noctusai_lib/domain/fleet_control.py:96` |
| `noctusai_lib.domain.fleet_control.CONTAINER_PREFIX` | const | `seed/lib/backend/noctusai_lib/domain/fleet_control.py:50` |
| `noctusai_lib.domain.fleet_control.ContainerStatus` | class | `seed/lib/backend/noctusai_lib/domain/fleet_control.py:76` |
| `noctusai_lib.domain.fleet_control.DockerComposeController` | class | `seed/lib/backend/noctusai_lib/domain/fleet_control.py:212` |
| `noctusai_lib.domain.fleet_control.validate_action` | def | `seed/lib/backend/noctusai_lib/domain/fleet_control.py:116` |
| `noctusai_lib.domain.invitations.expire_old_invitations` | def | `seed/lib/backend/noctusai_lib/domain/invitations.py:278` |
| `noctusai_lib.domain.notifications.map_notification_from_pt` | def | `seed/lib/backend/noctusai_lib/domain/notifications.py:26` |
| `noctusai_lib.domain.org.DEFAULT_NAME_TEMPLATE` | const | `seed/lib/backend/noctusai_lib/domain/org.py:38` |
| `noctusai_lib.domain.org.find_auth_user_id_by_email` | def | `seed/lib/backend/noctusai_lib/domain/org.py:139` |
| `noctusai_lib.domain.page_status.get_visible_pages` | def | `seed/lib/backend/noctusai_lib/domain/page_status.py:17` |
| `noctusai_lib.domain.payments.event_inbox.EventInbox` | class | `seed/lib/backend/noctusai_lib/domain/payments/event_inbox.py:27` |
| `noctusai_lib.domain.payments.event_inbox.FakeEventInbox` | class | `seed/lib/backend/noctusai_lib/domain/payments/event_inbox.py:45` |
| `noctusai_lib.domain.payments.event_inbox.RealSupabaseEventInbox` | class | `seed/lib/backend/noctusai_lib/domain/payments/event_inbox.py:70` |
| `noctusai_lib.domain.payments.event_inbox.make_event_inbox` | def | `seed/lib/backend/noctusai_lib/domain/payments/event_inbox.py:140` |
| `noctusai_lib.domain.payments.subscription.Subscription` | class | `seed/lib/backend/noctusai_lib/domain/payments/subscription.py:87` |
| `noctusai_lib.domain.payments.subscription.SubscriptionState` | class | `seed/lib/backend/noctusai_lib/domain/payments/subscription.py:26` |
| `noctusai_lib.domain.payments.subscription.is_terminal` | def | `seed/lib/backend/noctusai_lib/domain/payments/subscription.py:102` |
| `noctusai_lib.domain.payments.subscription.legal_next_states` | def | `seed/lib/backend/noctusai_lib/domain/payments/subscription.py:107` |
| `noctusai_lib.domain.payments.subscription.transition` | def | `seed/lib/backend/noctusai_lib/domain/payments/subscription.py:114` |
| `noctusai_lib.domain.photo_editing.costs.CURRENCY_BRL` | const | `seed/lib/backend/noctusai_lib/domain/photo_editing/costs.py:38` |
| `noctusai_lib.domain.photo_editing.costs.CURRENCY_USD` | const | `seed/lib/backend/noctusai_lib/domain/photo_editing/costs.py:37` |
| `noctusai_lib.domain.photo_editing.costs.local_call_date` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/costs.py:128` |
| `noctusai_lib.domain.photo_editing.guide.ComposedGuide` | class | `seed/lib/backend/noctusai_lib/domain/photo_editing/guide.py:65` |
| `noctusai_lib.domain.photo_editing.guide.order_rules` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/guide.py:49` |
| `noctusai_lib.domain.photo_editing.guide.rule_set_sha256` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/guide.py:60` |
| `noctusai_lib.domain.photo_editing.handlers.failure_reason` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/handlers.py:140` |
| `noctusai_lib.domain.photo_editing.handlers.parse_evaluation` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/handlers.py:483` |
| `noctusai_lib.domain.photo_editing.learning.can_decide_rule` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/learning.py:70` |
| `noctusai_lib.domain.photo_editing.learning.rule_key` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/learning.py:65` |
| `noctusai_lib.domain.photo_editing.naming.OUTPUT_EXTENSION` | const | `seed/lib/backend/noctusai_lib/domain/photo_editing/naming.py:25` |
| `noctusai_lib.domain.photo_editing.naming.UPLOAD_NAME` | const | `seed/lib/backend/noctusai_lib/domain/photo_editing/naming.py:27` |
| `noctusai_lib.domain.photo_editing.naming.zip_number_width` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/naming.py:36` |
| `noctusai_lib.domain.photo_editing.pipeline.SubmissionPlan` | class | `seed/lib/backend/noctusai_lib/domain/photo_editing/pipeline.py:242` |
| `noctusai_lib.domain.photo_editing.pipeline.enqueue_ingest` | async def | `seed/lib/backend/noctusai_lib/domain/photo_editing/pipeline.py:101` |
| `noctusai_lib.domain.photo_editing.types.MAX_BYTES_PER_PHOTO` | const | `seed/lib/backend/noctusai_lib/domain/photo_editing/types.py:138` |
| `noctusai_lib.domain.photo_editing.types.MAX_PHOTOS_PER_BATCH` | const | `seed/lib/backend/noctusai_lib/domain/photo_editing/types.py:137` |
| `noctusai_lib.domain.photo_editing.types.sources_for` | def | `seed/lib/backend/noctusai_lib/domain/photo_editing/types.py:202` |
| `noctusai_lib.domain.photo_editing.zipper.ZipEntry` | class | `seed/lib/backend/noctusai_lib/domain/photo_editing/zipper.py:50` |
| `noctusai_lib.domain.pipeline.board.group_into_colunas` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/board.py:36` |
| `noctusai_lib.domain.pipeline.board.orphan_cards` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/board.py:137` |
| `noctusai_lib.domain.pipeline.board.stage_to_dto` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/board.py:23` |
| `noctusai_lib.domain.pipeline.moves.move_card` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/moves.py:27` |
| `noctusai_lib.domain.pipeline.moves.resolve_initial_stage` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/moves.py:138` |
| `noctusai_lib.domain.pipeline.ordering.POSITION_FIELD` | const | `seed/lib/backend/noctusai_lib/domain/pipeline/ordering.py:46` |
| `noctusai_lib.domain.pipeline.ordering.position_for_index` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/ordering.py:82` |
| `noctusai_lib.domain.pipeline.ordering.position_on_top` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/ordering.py:68` |
| `noctusai_lib.domain.pipeline.router.PipelineContext` | class | `seed/lib/backend/noctusai_lib/domain/pipeline/router.py:64` |
| `noctusai_lib.domain.pipeline.router.StageCreate` | class | `seed/lib/backend/noctusai_lib/domain/pipeline/router.py:40` |
| `noctusai_lib.domain.pipeline.router.StageReorder` | class | `seed/lib/backend/noctusai_lib/domain/pipeline/router.py:59` |
| `noctusai_lib.domain.pipeline.router.StageUpdate` | class | `seed/lib/backend/noctusai_lib/domain/pipeline/router.py:48` |
| `noctusai_lib.domain.pipeline.router.pipeline_stages_router` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/router.py:90` |
| `noctusai_lib.domain.pipeline.stages.STAGE_ROLE_ACCEPT` | const | `seed/lib/backend/noctusai_lib/domain/pipeline/stages.py:51` |
| `noctusai_lib.domain.pipeline.stages.STAGE_ROLE_FINAL` | const | `seed/lib/backend/noctusai_lib/domain/pipeline/stages.py:52` |
| `noctusai_lib.domain.pipeline.stages.count_cards_in_stage` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/stages.py:290` |
| `noctusai_lib.domain.pipeline.stages.slugify` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/stages.py:63` |
| `noctusai_lib.domain.pipeline.stages.stage_by_role` | def | `seed/lib/backend/noctusai_lib/domain/pipeline/stages.py:143` |
| `noctusai_lib.domain.real_estate.parcelamento.CENTAVO` | const | `seed/lib/backend/noctusai_lib/domain/real_estate/parcelamento.py:30` |
| `noctusai_lib.domain.sql_templates.rls_subquery_policy` | def | `seed/lib/backend/noctusai_lib/domain/sql_templates.py:144` |
| `noctusai_lib.domain.texto_ptbr.inteiro_por_extenso` | def | `seed/lib/backend/noctusai_lib/domain/texto_ptbr.py:111` |
| `noctusai_lib.graph.build.build_graph` | def | `seed/lib/backend/noctusai_lib/graph/build.py:50` |
| `noctusai_lib.graph.extract_cli.cli_flag_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_cli.py:30` |
| `noctusai_lib.graph.extract_code.code_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_code.py:178` |
| `noctusai_lib.graph.extract_docs.kb_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_docs.py:40` |
| `noctusai_lib.graph.extract_harness.agent_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_harness.py:44` |
| `noctusai_lib.graph.extract_harness.command_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_harness.py:52` |
| `noctusai_lib.graph.extract_harness.skill_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_harness.py:48` |
| `noctusai_lib.graph.extract_landscape.landscape_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_landscape.py:40` |
| `noctusai_lib.graph.extract_memory.memory_id` | def | `seed/lib/backend/noctusai_lib/graph/extract_memory.py:25` |
| `noctusai_lib.graph.extract_mined.ingest_guarded_by_edges` | def | `seed/lib/backend/noctusai_lib/graph/extract_mined.py:215` |
| `noctusai_lib.graph.extract_mined.ingest_semantic_neighbors` | def | `seed/lib/backend/noctusai_lib/graph/extract_mined.py:171` |
| `noctusai_lib.graph.extract_mined.walk_mined` | def | `seed/lib/backend/noctusai_lib/graph/extract_mined.py:36` |
| `noctusai_lib.graph.query.GraphIndex` | class | `seed/lib/backend/noctusai_lib/graph/query.py:14` |
| `noctusai_lib.graph.serialize.write_graph_html` | def | `seed/lib/backend/noctusai_lib/graph/serialize.py:24` |
| `noctusai_lib.graph.serialize.write_graph_json` | def | `seed/lib/backend/noctusai_lib/graph/serialize.py:16` |
| `noctusai_lib.graph.serialize.write_graph_report` | def | `seed/lib/backend/noctusai_lib/graph/serialize.py:39` |
| `noctusai_lib.integrations.credential_resolvers.DRIVE_PROVIDER` | const | `seed/lib/backend/noctusai_lib/integrations/credential_resolvers.py:71` |
| `noctusai_lib.integrations.credential_resolvers.make_token_persisting_callback` | def | `seed/lib/backend/noctusai_lib/integrations/credential_resolvers.py:258` |
| `noctusai_lib.integrations.database.force_postgrest_http1` | def | `seed/lib/backend/noctusai_lib/integrations/database.py:26` |
| `noctusai_lib.integrations.documents.birthdate.MAX_AGE` | const | `seed/lib/backend/noctusai_lib/integrations/documents/birthdate.py:49` |
| `noctusai_lib.integrations.documents.birthdate.MIN_AGE` | const | `seed/lib/backend/noctusai_lib/integrations/documents/birthdate.py:48` |
| `noctusai_lib.integrations.documents.civil_status.normalize` | def | `seed/lib/backend/noctusai_lib/integrations/documents/civil_status.py:206` |
| `noctusai_lib.integrations.documents.cnpj.format_cnpj` | def | `seed/lib/backend/noctusai_lib/integrations/documents/cnpj.py:60` |
| `noctusai_lib.integrations.documents.cnpj.is_valid` | def | `seed/lib/backend/noctusai_lib/integrations/documents/cnpj.py:44` |
| `noctusai_lib.integrations.documents.cnpj.normalize` | def | `seed/lib/backend/noctusai_lib/integrations/documents/cnpj.py:28` |
| `noctusai_lib.integrations.documents.cpf.normalize` | def | `seed/lib/backend/noctusai_lib/integrations/documents/cpf.py:92` |
| `noctusai_lib.integrations.documents.gender.FEMININO` | const | `seed/lib/backend/noctusai_lib/integrations/documents/gender.py:40` |
| `noctusai_lib.integrations.documents.gender.MASCULINO` | const | `seed/lib/backend/noctusai_lib/integrations/documents/gender.py:39` |
| `noctusai_lib.integrations.documents.gender.normalize` | def | `seed/lib/backend/noctusai_lib/integrations/documents/gender.py:94` |
| `noctusai_lib.integrations.documents.labels.LABEL_WINDOW` | const | `seed/lib/backend/noctusai_lib/integrations/documents/labels.py:53` |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.BAIXA` | const | `seed/lib/backend/noctusai_lib/integrations/documents/matricula_ato_detalhes.py:59` |
| `noctusai_lib.integrations.documents.matricula_extractor.LadderMatriculaExtractor` | class | `seed/lib/backend/noctusai_lib/integrations/documents/matricula_extractor.py:159` |
| `noctusai_lib.integrations.documents.name.MAX_NAME_LEN` | const | `seed/lib/backend/noctusai_lib/integrations/documents/name.py:56` |
| `noctusai_lib.integrations.documents.name.MAX_WORDS` | const | `seed/lib/backend/noctusai_lib/integrations/documents/name.py:58` |
| `noctusai_lib.integrations.documents.name.MIN_NAME_LEN` | const | `seed/lib/backend/noctusai_lib/integrations/documents/name.py:55` |
| `noctusai_lib.integrations.documents.name.MIN_WORDS` | const | `seed/lib/backend/noctusai_lib/integrations/documents/name.py:57` |
| `noctusai_lib.integrations.documents.rg.normalize` | def | `seed/lib/backend/noctusai_lib/integrations/documents/rg.py:130` |
| `noctusai_lib.integrations.documents.rg.only_alnum` | def | `seed/lib/backend/noctusai_lib/integrations/documents/rg.py:139` |
| `noctusai_lib.integrations.documents.transcription.DEFAULT_VISION_PROVIDER` | const | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:63` |
| `noctusai_lib.integrations.documents.transcription.LadderDocumentTranscriber` | class | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:302` |
| `noctusai_lib.integrations.documents.transcription.MAX_VISION_PAGES` | const | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:127` |
| `noctusai_lib.integrations.documents.transcription.OCR_MODEL` | const | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:93` |
| `noctusai_lib.integrations.documents.transcription.OCR_PROMPT` | const | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:103` |
| `noctusai_lib.integrations.documents.transcription.RENDER_DPI` | const | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:58` |
| `noctusai_lib.integrations.documents.transcription.parse_markup` | def | `seed/lib/backend/noctusai_lib/integrations/documents/transcription.py:914` |
| `noctusai_lib.integrations.email.digest.send_to_many` | async def | `seed/lib/backend/noctusai_lib/integrations/email/digest.py:353` |
| `noctusai_lib.integrations.email.digest.send_to_one` | async def | `seed/lib/backend/noctusai_lib/integrations/email/digest.py:321` |
| `noctusai_lib.integrations.email.templates.send_password_reset_email` | def | `seed/lib/backend/noctusai_lib/integrations/email/templates.py:136` |
| `noctusai_lib.integrations.google_scopes.GOOGLE_TOKENINFO_URL` | const | `seed/lib/backend/noctusai_lib/integrations/google_scopes.py:64` |
| `noctusai_lib.integrations.google_scopes.format_scopes_for_authorize` | def | `seed/lib/backend/noctusai_lib/integrations/google_scopes.py:127` |
| `noctusai_lib.integrations.google_scopes_router.google_scopes_router` | def | `seed/lib/backend/noctusai_lib/integrations/google_scopes_router.py:61` |
| `noctusai_lib.integrations.imovelweb.auth.AccessToken` | class | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:35` |
| `noctusai_lib.integrations.imovelweb.auth.InMemoryTokenCache` | class | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:61` |
| `noctusai_lib.integrations.imovelweb.auth.LOGIN_PATH` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:30` |
| `noctusai_lib.integrations.imovelweb.auth.LOGOUT_PATH` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:31` |
| `noctusai_lib.integrations.imovelweb.auth.REFRESH_SKEW_SECONDS` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:28` |
| `noctusai_lib.integrations.imovelweb.auth.TokenCache` | class | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:55` |
| `noctusai_lib.integrations.imovelweb.auth.parse_expiry` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:78` |
| `noctusai_lib.integrations.imovelweb.auth.token_from_payload` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/auth.py:124` |
| `noctusai_lib.integrations.imovelweb.contract.FieldSpec` | class | `seed/lib/backend/noctusai_lib/integrations/imovelweb/contract.py:72` |
| `noctusai_lib.integrations.imovelweb.contract.contract_summary` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/contract.py:296` |
| `noctusai_lib.integrations.imovelweb.contract.diff_observed` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/contract.py:432` |
| `noctusai_lib.integrations.imovelweb.contract.has_blocking_violation` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/contract.py:428` |
| `noctusai_lib.integrations.imovelweb.contract.imovelweb_json_schema` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/contract.py:329` |
| `noctusai_lib.integrations.imovelweb.contract.validate_imovelweb_payload` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/contract.py:353` |
| `noctusai_lib.integrations.imovelweb.endpoints.ENDPOINT_ABSENT` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:25` |
| `noctusai_lib.integrations.imovelweb.endpoints.ENDPOINT_INBOUND` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:27` |
| `noctusai_lib.integrations.imovelweb.endpoints.ENDPOINT_LIVE` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:22` |
| `noctusai_lib.integrations.imovelweb.endpoints.ENDPOINT_PERMISSION_GATED` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:23` |
| `noctusai_lib.integrations.imovelweb.endpoints.ENDPOINT_UNVERIFIED` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:26` |
| `noctusai_lib.integrations.imovelweb.endpoints.ENDPOINT_WRITE_ONLY` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:24` |
| `noctusai_lib.integrations.imovelweb.endpoints.IMOVELWEB_PROD_AR` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:34` |
| `noctusai_lib.integrations.imovelweb.endpoints.IMOVELWEB_PROD_BR` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:32` |
| `noctusai_lib.integrations.imovelweb.endpoints.IMOVELWEB_PROD_RELA` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:35` |
| `noctusai_lib.integrations.imovelweb.endpoints.IMOVELWEB_SWAGGER_PATH` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/endpoints.py:51` |
| `noctusai_lib.integrations.imovelweb.errors.ImovelWebError` | class | `seed/lib/backend/noctusai_lib/integrations/imovelweb/errors.py:53` |
| `noctusai_lib.integrations.imovelweb.errors.SECRET_REDACTION_PLACEHOLDER` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/errors.py:15` |
| `noctusai_lib.integrations.imovelweb.factory.make_imovelweb_client` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/factory.py:12` |
| `noctusai_lib.integrations.imovelweb.normalizers.IMOVELWEB_DEFAULT_SOURCE_SLUG` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/normalizers.py:45` |
| `noctusai_lib.integrations.imovelweb.normalizers.IMOVELWEB_PIPE` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/normalizers.py:41` |
| `noctusai_lib.integrations.imovelweb.normalizers.imovelweb_lead_to_lead_payload` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/normalizers.py:163` |
| `noctusai_lib.integrations.imovelweb.normalizers.imovelweb_timestamp_to_date` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/normalizers.py:81` |
| `noctusai_lib.integrations.imovelweb.normalizers.render_observacoes` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/normalizers.py:134` |
| `noctusai_lib.integrations.imovelweb.normalizers.resolve_source_slug` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/normalizers.py:60` |
| `noctusai_lib.integrations.imovelweb.protocol.ImovelWebAdapter` | class | `seed/lib/backend/noctusai_lib/integrations/imovelweb/protocol.py:22` |
| `noctusai_lib.integrations.imovelweb.real.RATE_LIMIT_BUCKET` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/real.py:44` |
| `noctusai_lib.integrations.imovelweb.types.IMOVELWEB_BASIC_USERNAME` | const | `seed/lib/backend/noctusai_lib/integrations/imovelweb/types.py:278` |
| `noctusai_lib.integrations.imovelweb.types.basic_credential` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/types.py:281` |
| `noctusai_lib.integrations.imovelweb.types.receiver_url_problems` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/types.py:313` |
| `noctusai_lib.integrations.imovelweb.webhook.detect_callback_language` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/webhook.py:37` |
| `noctusai_lib.integrations.imovelweb.webhook.parse_imovelweb_callback` | def | `seed/lib/backend/noctusai_lib/integrations/imovelweb/webhook.py:96` |
| `noctusai_lib.integrations.llm.audio.transcribe_audio` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/audio.py:16` |
| `noctusai_lib.integrations.llm.backends.redis_backend.RedisCacheBackend` | class | `seed/lib/backend/noctusai_lib/integrations/llm/backends/redis_backend.py:29` |
| `noctusai_lib.integrations.llm.budget.compute_spend_usd` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/budget.py:168` |
| `noctusai_lib.integrations.llm.budget.fetch_budget_brl` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/budget.py:131` |
| `noctusai_lib.integrations.llm.budget.is_configured` | def | `seed/lib/backend/noctusai_lib/integrations/llm/budget.py:85` |
| `noctusai_lib.integrations.llm.cache.CacheBackend` | class | `seed/lib/backend/noctusai_lib/integrations/llm/cache.py:39` |
| `noctusai_lib.integrations.llm.cache.InMemoryCacheBackend` | class | `seed/lib/backend/noctusai_lib/integrations/llm/cache.py:106` |
| `noctusai_lib.integrations.llm.chat.build_cached_messages` | def | `seed/lib/backend/noctusai_lib/integrations/llm/chat.py:181` |
| `noctusai_lib.integrations.llm.chat.chat_completion` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/chat.py:31` |
| `noctusai_lib.integrations.llm.chat.chat_completion_stream` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/chat.py:123` |
| `noctusai_lib.integrations.llm.embeddings.generate_embedding` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/embeddings.py:15` |
| `noctusai_lib.integrations.llm.embeddings.generate_embeddings_batch` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/embeddings.py:58` |
| `noctusai_lib.integrations.llm.inputs.audio_bytes_to_named_buffer` | def | `seed/lib/backend/noctusai_lib/integrations/llm/inputs.py:20` |
| `noctusai_lib.integrations.llm.models.is_stub_model` | def | `seed/lib/backend/noctusai_lib/integrations/llm/models.py:412` |
| `noctusai_lib.integrations.llm.providers.anthropic_provider.AnthropicProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/anthropic_provider.py:60` |
| `noctusai_lib.integrations.llm.providers.fake_provider.FakeProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/fake_provider.py:30` |
| `noctusai_lib.integrations.llm.providers.gemini_provider.GeminiProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/gemini_provider.py:60` |
| `noctusai_lib.integrations.llm.providers.openai_provider.OpenAIProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/openai_provider.py:30` |
| `noctusai_lib.integrations.llm.refusal.analyze_image_with_refusal_retry` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/refusal.py:114` |
| `noctusai_lib.integrations.llm.refusal.looks_like_refusal` | def | `seed/lib/backend/noctusai_lib/integrations/llm/refusal.py:76` |
| `noctusai_lib.integrations.llm.registry.list_providers` | def | `seed/lib/backend/noctusai_lib/integrations/llm/registry.py:42` |
| `noctusai_lib.integrations.llm.usage.InMemoryUsageSink` | class | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:79` |
| `noctusai_lib.integrations.llm.usage.UsageEvent` | class | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:28` |
| `noctusai_lib.integrations.llm.usage.UsageSink` | class | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:72` |
| `noctusai_lib.integrations.llm.vision.analyze_images` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/vision.py:58` |
| `noctusai_lib.integrations.media.pdf_text.MIN_CHARS_PER_PAGE` | const | `seed/lib/backend/noctusai_lib/integrations/media/pdf_text.py:205` |
| `noctusai_lib.integrations.media.pdf_text.SCAN_IMAGE_COVERAGE_RATIO` | const | `seed/lib/backend/noctusai_lib/integrations/media/pdf_text.py:191` |
| `noctusai_lib.integrations.media.pdf_text.TEXT_RICH_CHARS_PER_PAGE` | const | `seed/lib/backend/noctusai_lib/integrations/media/pdf_text.py:199` |
| `noctusai_lib.integrations.meta._meta_api.DEFAULT_MAX_PAGES` | const | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:87` |
| `noctusai_lib.integrations.meta._meta_api.DEFAULT_TIMEOUT_SECONDS` | const | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:86` |
| `noctusai_lib.integrations.meta._meta_api.GRAPH_BASE` | const | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:68` |
| `noctusai_lib.integrations.meta._meta_api.app_access_token` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:815` |
| `noctusai_lib.integrations.meta._meta_api.graph_delete` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:402` |
| `noctusai_lib.integrations.meta._meta_api.graph_get` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:290` |
| `noctusai_lib.integrations.meta._meta_api.graph_paged` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:322` |
| `noctusai_lib.integrations.meta._meta_api.graph_post` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:361` |
| `noctusai_lib.integrations.meta.mappers.leadgen_question_from_body` | def | `seed/lib/backend/noctusai_lib/integrations/meta/mappers.py:525` |
| `noctusai_lib.integrations.oauth_bundles.bundle_names` | def | `seed/lib/backend/noctusai_lib/integrations/oauth_bundles.py:131` |
| `noctusai_lib.integrations.oauth_bundles.resolve_bundle` | def | `seed/lib/backend/noctusai_lib/integrations/oauth_bundles.py:108` |
| `noctusai_lib.integrations.olx.contract.ContractViolation` | class | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:155` |
| `noctusai_lib.integrations.olx.contract.OlxFieldSpec` | class | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:34` |
| `noctusai_lib.integrations.olx.contract.contract_summary` | def | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:252` |
| `noctusai_lib.integrations.olx.contract.diff_observed` | def | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:284` |
| `noctusai_lib.integrations.olx.contract.has_blocking_violation` | def | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:241` |
| `noctusai_lib.integrations.olx.contract.missing_client_listing_id` | def | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:246` |
| `noctusai_lib.integrations.olx.contract.olx_lead_json_schema` | def | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:131` |
| `noctusai_lib.integrations.olx.contract.validate_olx_lead_payload` | def | `seed/lib/backend/noctusai_lib/integrations/olx/contract.py:171` |
| `noctusai_lib.integrations.olx.endpoints.ENDPOINT_ABSENT` | const | `seed/lib/backend/noctusai_lib/integrations/olx/endpoints.py:30` |
| `noctusai_lib.integrations.olx.endpoints.ENDPOINT_INBOUND` | const | `seed/lib/backend/noctusai_lib/integrations/olx/endpoints.py:32` |
| `noctusai_lib.integrations.olx.endpoints.ENDPOINT_LIVE` | const | `seed/lib/backend/noctusai_lib/integrations/olx/endpoints.py:27` |
| `noctusai_lib.integrations.olx.endpoints.ENDPOINT_PERMISSION_GATED` | const | `seed/lib/backend/noctusai_lib/integrations/olx/endpoints.py:28` |
| `noctusai_lib.integrations.olx.endpoints.ENDPOINT_UNVERIFIED` | const | `seed/lib/backend/noctusai_lib/integrations/olx/endpoints.py:31` |
| `noctusai_lib.integrations.olx.endpoints.ENDPOINT_WRITE_ONLY` | const | `seed/lib/backend/noctusai_lib/integrations/olx/endpoints.py:29` |
| `noctusai_lib.integrations.olx.factory.make_olx_lead_manager_client` | def | `seed/lib/backend/noctusai_lib/integrations/olx/factory.py:12` |
| `noctusai_lib.integrations.olx.fake.upstream_failure` | def | `seed/lib/backend/noctusai_lib/integrations/olx/fake.py:88` |
| `noctusai_lib.integrations.olx.normalizers.olx_lead_to_lead_payload` | def | `seed/lib/backend/noctusai_lib/integrations/olx/normalizers.py:73` |
| `noctusai_lib.integrations.olx.normalizers.olx_timestamp_to_date` | def | `seed/lib/backend/noctusai_lib/integrations/olx/normalizers.py:22` |
| `noctusai_lib.integrations.olx.normalizers.render_observacoes` | def | `seed/lib/backend/noctusai_lib/integrations/olx/normalizers.py:45` |
| `noctusai_lib.integrations.olx.portal_split.PortalAttribution` | class | `seed/lib/backend/noctusai_lib/integrations/olx/portal_split.py:104` |
| `noctusai_lib.integrations.olx.portal_split.PortalRule` | class | `seed/lib/backend/noctusai_lib/integrations/olx/portal_split.py:60` |
| `noctusai_lib.integrations.olx.portal_split.resolve_portal_source_slug` | def | `seed/lib/backend/noctusai_lib/integrations/olx/portal_split.py:151` |
| `noctusai_lib.integrations.olx.protocol.OlxLeadManagerAdapter` | class | `seed/lib/backend/noctusai_lib/integrations/olx/protocol.py:23` |
| `noctusai_lib.integrations.olx.real.RATE_LIMIT_BUCKET` | const | `seed/lib/backend/noctusai_lib/integrations/olx/real.py:23` |
| `noctusai_lib.integrations.olx.webhook.parse_olx_lead_webhook` | def | `seed/lib/backend/noctusai_lib/integrations/olx/webhook.py:15` |
| `noctusai_lib.integrations.outbound_webhook.factory.make_outbound_webhook_sender` | def | `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/factory.py:10` |
| `noctusai_lib.integrations.outbound_webhook.fake.RecordedRequest` | class | `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/fake.py:16` |
| `noctusai_lib.integrations.outbound_webhook.fake.failure` | def | `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/fake.py:79` |
| `noctusai_lib.integrations.outbound_webhook.fake.success` | def | `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/fake.py:94` |
| `noctusai_lib.integrations.outbound_webhook.protocol.OutboundWebhookSender` | class | `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/protocol.py:9` |
| `noctusai_lib.integrations.outbound_webhook.types.RESPONSE_BODY_LIMIT` | const | `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/types.py:17` |
| `noctusai_lib.integrations.payments.factory.make_payment_gateway` | def | `seed/lib/backend/noctusai_lib/integrations/payments/factory.py:16` |
| `noctusai_lib.integrations.payments.protocol.PaymentGateway` | class | `seed/lib/backend/noctusai_lib/integrations/payments/protocol.py:16` |
| `noctusai_lib.integrations.persistence.fake_adapter.InMemoryRecordStore` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/fake_adapter.py:77` |
| `noctusai_lib.integrations.persistence.fake_adapter.matches` | def | `seed/lib/backend/noctusai_lib/integrations/persistence/fake_adapter.py:36` |
| `noctusai_lib.integrations.persistence.paging.DEFAULT_MAX_PAGES` | const | `seed/lib/backend/noctusai_lib/integrations/persistence/paging.py:80` |
| `noctusai_lib.integrations.persistence.paging.DEFAULT_PAGE_SIZE` | const | `seed/lib/backend/noctusai_lib/integrations/persistence/paging.py:75` |
| `noctusai_lib.integrations.persistence.paging.PagerOverflowError` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/paging.py:83` |
| `noctusai_lib.integrations.persistence.sqlite_adapter.SqliteRecordStore` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/sqlite_adapter.py:86` |
| `noctusai_lib.integrations.persistence.supabase_adapter.SupabaseLike` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/supabase_adapter.py:30` |
| `noctusai_lib.integrations.persistence.supabase_adapter.SupabaseRecordStore` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/supabase_adapter.py:54` |
| `noctusai_lib.integrations.persistence.types.Filter` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/types.py:86` |
| `noctusai_lib.integrations.persistence.types.Order` | class | `seed/lib/backend/noctusai_lib/integrations/persistence/types.py:106` |
| `noctusai_lib.integrations.quota.redis_backend.MAX_RETRIES` | const | `seed/lib/backend/noctusai_lib/integrations/quota/redis_backend.py:52` |
| `noctusai_lib.integrations.rate_limit.BucketConfig` | class | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:54` |
| `noctusai_lib.integrations.rate_limit.Clock` | class | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:118` |
| `noctusai_lib.integrations.rate_limit.RateLimitedError` | class | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:376` |
| `noctusai_lib.integrations.rate_limit.RateLimiter` | class | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:216` |
| `noctusai_lib.integrations.rate_limit.TokenBucket` | class | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:175` |
| `noctusai_lib.integrations.rate_limit.VirtualClock` | class | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:132` |
| `noctusai_lib.integrations.rate_limit.acquire` | def | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:248` |
| `noctusai_lib.integrations.rate_limit.paced_call` | def | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:442` |
| `noctusai_lib.integrations.rate_limit.parse_retry_after` | def | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:471` |
| `noctusai_lib.integrations.rate_limit.reset_default_clock` | def | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:166` |
| `noctusai_lib.integrations.rate_limit.retry_with_backoff` | def | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:391` |
| `noctusai_lib.integrations.rate_limit.set_default_clock` | def | `seed/lib/backend/noctusai_lib/integrations/rate_limit.py:159` |
| `noctusai_lib.integrations.supabase_identity.fetch_user_identity` | def | `seed/lib/backend/noctusai_lib/integrations/supabase_identity.py:105` |
| `noctusai_lib.integrations.vista.adapter_factory.get_vista_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/vista/adapter_factory.py:23` |
| `noctusai_lib.integrations.vista.calibration.CalibrationResult` | class | `seed/lib/backend/noctusai_lib/integrations/vista/calibration.py:191` |
| `noctusai_lib.integrations.vista.calibration.Calibrator` | class | `seed/lib/backend/noctusai_lib/integrations/vista/calibration.py:200` |
| `noctusai_lib.integrations.vista.client.ENDPOINT_ABSENT` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:62` |
| `noctusai_lib.integrations.vista.client.ENDPOINT_LIVE` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:59` |
| `noctusai_lib.integrations.vista.client.ENDPOINT_PERMISSION_GATED` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:60` |
| `noctusai_lib.integrations.vista.client.ENDPOINT_WRITE_ONLY` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:61` |
| `noctusai_lib.integrations.vista.client.KEY_REDACTION_PLACEHOLDER` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:29` |
| `noctusai_lib.integrations.vista.client.PAGINATION_KEYS` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:27` |
| `noctusai_lib.integrations.vista.client.VistaTimeout` | class | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:137` |
| `noctusai_lib.integrations.vista.factory.make_vista_client` | def | `seed/lib/backend/noctusai_lib/integrations/vista/factory.py:24` |
| `noctusai_lib.integrations.vista.imovel_normalizer.merge_vista_payloads` | def | `seed/lib/backend/noctusai_lib/integrations/vista/imovel_normalizer.py:45` |
| `noctusai_lib.integrations.vista.normalizers.vista_agencia_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:197` |
| `noctusai_lib.integrations.vista.normalizers.vista_cliente_detalhes_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:169` |
| `noctusai_lib.integrations.vista.normalizers.vista_cliente_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:143` |
| `noctusai_lib.integrations.vista.normalizers.vista_imovel_detalhes_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:116` |
| `noctusai_lib.integrations.vista.normalizers.vista_imovel_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:82` |
| `noctusai_lib.integrations.vista.normalizers.vista_usuario_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:186` |
| `noctusai_lib.integrations.whatsapp.mappers.extract_from_name` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:172` |
| `noctusai_lib.integrations.whatsapp.mappers.extract_media` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:153` |
| `noctusai_lib.integrations.whatsapp.mappers.extract_message_id` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:142` |
| `noctusai_lib.integrations.whatsapp.mappers.first_text` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:134` |
| `noctusai_lib.integrations.whatsapp.mappers.is_own_or_api_message` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:166` |
| `noctusai_lib.integrations.youtube.real.CHUNK_RETRY_BASE_DELAY_S` | const | `seed/lib/backend/noctusai_lib/integrations/youtube/real.py:185` |
| `noctusai_lib.integrations.youtube.real.CHUNK_RETRY_MAX_ATTEMPTS` | const | `seed/lib/backend/noctusai_lib/integrations/youtube/real.py:181` |
| `noctusai_lib.integrations.youtube.real.CHUNK_RETRY_MAX_DELAY_S` | const | `seed/lib/backend/noctusai_lib/integrations/youtube/real.py:188` |
| `noctusai_lib.logging_config.auto_configure_for_cli` | def | `seed/lib/backend/noctusai_lib/logging_config.py:215` |
| `noctusai_lib.primitives.exceptions.ForbiddenError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:81` |
| `noctusai_lib.primitives.exceptions.InternalError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:107` |
| `noctusai_lib.primitives.exceptions.UnauthorizedError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:70` |
| `noctusai_lib.primitives.exceptions.format_error_response` | def | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:122` |
| `noctusai_lib.primitives.image_sizing.EDGE_MULTIPLE` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:42` |
| `noctusai_lib.primitives.image_sizing.MAX_ASPECT_RATIO` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:53` |
| `noctusai_lib.primitives.image_sizing.MAX_EDGE_PX` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:45` |
| `noctusai_lib.primitives.image_sizing.MAX_TOTAL_PIXELS` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:49` |
| `noctusai_lib.primitives.image_sizing.MIN_ASPECT_RATIO` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:52` |
| `noctusai_lib.primitives.image_sizing.MIN_TOTAL_PIXELS` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:48` |
| `noctusai_lib.primitives.image_sizing.NON_EXPERIMENTAL_MAX_TOTAL_PIXELS` | const | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:60` |
| `noctusai_lib.primitives.image_sizing.validate_size` | def | `seed/lib/backend/noctusai_lib/primitives/image_sizing.py:88` |
| `noctusai_lib.primitives.parsing.parse_iso_or_none` | def | `seed/lib/backend/noctusai_lib/primitives/parsing.py:175` |
| `noctusai_lib.primitives.phone.DEFAULT_COUNTRY_CODE` | const | `seed/lib/backend/noctusai_lib/primitives/phone.py:61` |
| `noctusai_lib.primitives.phone.format_phone` | def | `seed/lib/backend/noctusai_lib/primitives/phone.py:224` |
| `noctusai_lib.primitives.phone.is_valid_phone` | def | `seed/lib/backend/noctusai_lib/primitives/phone.py:218` |
| `noctusai_lib.primitives.responses.PaginatedResponse` | class | `seed/lib/backend/noctusai_lib/primitives/responses.py:25` |
| `noctusai_lib.primitives.responses.PaginationMeta` | class | `seed/lib/backend/noctusai_lib/primitives/responses.py:17` |
| `noctusai_lib.primitives.roles.ORG_ROLES` | const | `seed/lib/backend/noctusai_lib/primitives/roles.py:20` |
| `noctusai_lib.primitives.roles.PRODUCT_ADMIN_ROLES` | const | `seed/lib/backend/noctusai_lib/primitives/roles.py:33` |
| `noctusai_lib.primitives.roles.can_manage_billing` | def | `seed/lib/backend/noctusai_lib/primitives/roles.py:58` |
| `noctusai_lib.primitives.roles.can_manage_team` | def | `seed/lib/backend/noctusai_lib/primitives/roles.py:53` |
| `noctusai_lib.primitives.roles.is_dev_or_owner` | def | `seed/lib/backend/noctusai_lib/primitives/roles.py:48` |
| `noctusai_lib.primitives.timeutil.frozen_time` | def | `seed/lib/backend/noctusai_lib/primitives/timeutil.py:90` |
| `noctusai_lib.security.app_config.DEFAULT_TABLE` | const | `seed/lib/backend/noctusai_lib/security/app_config.py:68` |
| `noctusai_lib.security.oauth.google_provider.GOOGLE_AUTH_URL` | const | `seed/lib/backend/noctusai_lib/security/oauth/google_provider.py:50` |
| `noctusai_lib.security.oauth.google_provider.GOOGLE_REVOKE_URL` | const | `seed/lib/backend/noctusai_lib/security/oauth/google_provider.py:52` |
| `noctusai_lib.security.oauth.google_provider.GOOGLE_TOKEN_URL` | const | `seed/lib/backend/noctusai_lib/security/oauth/google_provider.py:51` |
| `noctusai_lib.sql.prelude.prelude` | def | `seed/lib/backend/noctusai_lib/sql/prelude.py:34` |
| `noctusai_lib.sql.service_role_bypass.service_role_bypass` | def | `seed/lib/backend/noctusai_lib/sql/service_role_bypass.py:48` |
| `noctusai_lib.sql.triggers.updated_at_function` | def | `seed/lib/backend/noctusai_lib/sql/triggers.py:40` |
| `noctusai_lib.sql.triggers.updated_at_trigger` | def | `seed/lib/backend/noctusai_lib/sql/triggers.py:62` |
| `noctusai_lib.testing.conftest_helpers.own_test_env` | def | `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py:206` |
| `noctusai_lib.testing.conftest_helpers.restore_real_llm_providers` | def | `seed/lib/backend/noctusai_lib/testing/conftest_helpers.py:278` |
| `noctusai_lib.testing.pytest_plugin.pytest_configure` | def | `seed/lib/backend/noctusai_lib/testing/pytest_plugin.py:38` |
| `noctusai_seed.ai_feedback_router.FeedbackBody` | class | `seed/framework/backend/noctusai_seed/ai_feedback_router.py:35` |
| `noctusai_seed.apply_sqlite_migrations.resolve_sqlite_path` | def | `seed/framework/backend/noctusai_seed/apply_sqlite_migrations.py:110` |
| `noctusai_seed.auth_router.ApiTokenCreatedDTO` | class | `seed/framework/backend/noctusai_seed/auth_router.py:213` |
| `noctusai_seed.auth_router.ApiTokenListItem` | class | `seed/framework/backend/noctusai_seed/auth_router.py:227` |
| `noctusai_seed.auth_router.LoginOrgDTO` | class | `seed/framework/backend/noctusai_seed/auth_router.py:159` |
| `noctusai_seed.auth_router.LoginRequest` | class | `seed/framework/backend/noctusai_seed/auth_router.py:149` |
| `noctusai_seed.auth_router.LoginResponse` | class | `seed/framework/backend/noctusai_seed/auth_router.py:164` |
| `noctusai_seed.auth_router.LoginUserDTO` | class | `seed/framework/backend/noctusai_seed/auth_router.py:154` |
| `noctusai_seed.auth_router.MeResponse` | class | `seed/framework/backend/noctusai_seed/auth_router.py:169` |
| `noctusai_seed.auth_router.get_session_revoker` | def | `seed/framework/backend/noctusai_seed/auth_router.py:129` |
| `noctusai_seed.database.DatabaseModule` | class | `seed/framework/backend/noctusai_seed/database.py:25` |
| `noctusai_seed.dependencies.ProductDependencies` | class | `seed/framework/backend/noctusai_seed/dependencies.py:104` |
| `noctusai_seed.dev_auth.DEV_TOKEN` | const | `seed/framework/backend/noctusai_seed/dev_auth.py:60` |
| `noctusai_seed.dev_auth.DEV_USER_EMAIL` | const | `seed/framework/backend/noctusai_seed/dev_auth.py:59` |
| `noctusai_seed.llm_router.ModelInfo` | class | `seed/framework/backend/noctusai_seed/llm_router.py:45` |
| `noctusai_seed.llm_router.PreferencesBody` | class | `seed/framework/backend/noctusai_seed/llm_router.py:53` |
| `noctusai_seed.llm_router.ProviderInfo` | class | `seed/framework/backend/noctusai_seed/llm_router.py:39` |
| `noctusai_seed.scheduler_router.SchedulerJobDTO` | class | `seed/framework/backend/noctusai_seed/scheduler_router.py:50` |
| `noctusai_seed.status_pagina_router.StatusPaginaOut` | class | `seed/framework/backend/noctusai_seed/status_pagina_router.py:56` |
| `noctusai_seed.status_pagina_router.StatusPaginaUpdate` | class | `seed/framework/backend/noctusai_seed/status_pagina_router.py:71` |
| `noctusai_seed.upload_route_overrides.find_uncovered_upload_routes` | def | `seed/framework/backend/noctusai_seed/upload_route_overrides.py:112` |
| `noctusai_seed.whatsapp_admin_router.ConnectionStatusDTO` | class | `seed/framework/backend/noctusai_seed/whatsapp_admin_router.py:45` |
| `noctusai_seed.whatsapp_admin_router.QrDTO` | class | `seed/framework/backend/noctusai_seed/whatsapp_admin_router.py:70` |
| `noctusai_seed.whatsapp_admin_router.WebhookConfigRequest` | class | `seed/framework/backend/noctusai_seed/whatsapp_admin_router.py:91` |
| `noctusai_seed.whatsapp_admin_router.WebhookResult` | class | `seed/framework/backend/noctusai_seed/whatsapp_admin_router.py:98` |

## Single-consumer symbols

Lib symbols imported by exactly **one product**. Informational only —
a symbol may legitimately live in lib because it encodes a platform-wide
policy, even if currently only one product exercises it.

| Symbol | Used by | Imports |
|---|---|---|
| `noctusai_lib.api.app_factory.configure_app` | lib:noctusai_seed | 1 |
| `noctusai_lib.api.auth.session.audit.ApiTokenAuditWriter` | lib:noctusai_lib | 2 |
| `noctusai_lib.api.auth.session.audit.FakeApiTokenAuditWriter` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.audit.SupabaseApiTokenAuditWriter` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.redis_store.RedisSessionStore` | lib:noctusai_lib | 2 |
| `noctusai_lib.api.auth.session.session_revoke.FakeSessionRevoker` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.session_revoke.SupabaseSessionRevoker` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.session_revoke.make_default_revoke_fn` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.store.FakeSessionStore` | lib:noctusai_lib | 3 |
| `noctusai_lib.api.auth.session.token_exchange.RefreshResult` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.token_exchange.SupabaseTokenExchanger` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.token_exchange.TokenExchangeError` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.token_exchange.TokenExchanger` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.token_exchange.make_default_refresh_fn` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.auth.session.types.ExpiredSessionError` | lib:noctusai_lib | 2 |
| `noctusai_lib.api.auth.session.types.InvalidCredentialsError` | lib:noctusai_lib | 3 |
| `noctusai_lib.api.auth.session.types.RevokedApiTokenError` | lib:noctusai_lib | 2 |
| `noctusai_lib.api.auth.session.types.SessionTokens` | lib:noctusai_lib | 3 |
| `noctusai_lib.api.crud_safety.delete_with_existence_check` | erp-imobiliario | 4 |
| `noctusai_lib.api.middleware.CorrelationIdMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY` | lib:noctusai_seed | 1 |
| `noctusai_lib.api.middleware.RequestLoggingMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.middleware.path_is_covered_by_overrides` | lib:noctusai_seed | 1 |
| `noctusai_lib.api.middleware.to_wildcard_pattern` | lib:noctusai_seed | 1 |
| `noctusai_lib.api.rate_limit.create_limiter` | lib:noctusai_seed | 1 |
| `noctusai_lib.config.cors_registry.derive_cors_origins` | lib:noctusai_lib | 1 |
| `noctusai_lib.config.credentials.configure_credentials` | lib:noctusai_seed | 1 |
| `noctusai_lib.config.credentials.register_credential_override` | social-wiring | 1 |
| `noctusai_lib.config.deploy_config.MissingProdConfigError` | igig | 1 |
| `noctusai_lib.config.deploy_config.baseline_required_prod_env` | lib:noctusai_seed | 1 |
| `noctusai_lib.config.deploy_config.is_deploy_context` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.ai.consent.configure_consent_module` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.ai.consent.list_user_consent_view` | core | 1 |
| `noctusai_lib.domain.ai.consent.pending_count` | core | 1 |
| `noctusai_lib.domain.ai.consent.register_feature` | core | 1 |
| `noctusai_lib.domain.ai.consent.reset_catalog_for_test` | core | 1 |
| `noctusai_lib.domain.ai.consent.upsert_decision` | core | 1 |
| `noctusai_lib.domain.ai.tool_audit.apply_feature_redaction` | social-wiring | 3 |
| `noctusai_lib.domain.chatbot.buffer.RedisBufferClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.buffer.make_in_memory_buffer_client` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.content_stats.SchemaHint` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.content_stats.compute_content_stats` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.delivery.send_reply_parts_sync` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.llm_dispatcher.DEFAULT_MAX_TOOL_ITERATIONS` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.llm_dispatcher.LLMDispatcher` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.chatbot.mappers.format_conversation_for_transcript` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.chatbot.mappers.memory_to_chat_messages` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.message_store.DuplicateMessage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.message_store.FakeMessageStore` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.message_store.MessageStore` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.message_store.StoredMessage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.message_store.SupabaseMessageStore` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.message_store.make_message_store` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.FakeToolOrchestrator` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.OpenAIToolOrchestrator` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.OrchestratorTool` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.ToolOrchestrator` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.append_memory` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.make_tool_orchestrator` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.openai_orchestrator.memory_key_for` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.prompt_fragments.with_url_immutability` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.response_registry.FakeResponseRegistry` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.response_registry.ResponseRegistry` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.response_registry.json_shape` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.response_registry.make_response_registry` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.response_registry.sample_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.response_registry.shape_fingerprint` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.summary.summarize_conversation` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.worker.BufferReader` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.digest.narrative.narrative` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.digest.types.DigestResult` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.digest.types.DigestWindow` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.fleet_control.ContainerController` | core | 1 |
| `noctusai_lib.domain.fleet_control.FakeContainerController` | core | 1 |
| `noctusai_lib.domain.fleet_control.FleetControlError` | core | 1 |
| `noctusai_lib.domain.fleet_control.get_fleet_controller` | core | 1 |
| `noctusai_lib.domain.invitations.generate_invite_token` | therapy-platform | 1 |
| `noctusai_lib.domain.jobs.entity.Job` | lib:noctusai_lib | 5 |
| `noctusai_lib.domain.jobs.entity.JobStatus` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.entity.next_status` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.entity.should_retry` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.entity.with_status_transition` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.repo.DeadLetterError` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.jobs.repo.FakeJobRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.repo.JobRepository` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.jobs.repo.LeaseLostError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.repo.RealSupabaseJobRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.repo.make_job_repository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.worker.Worker` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.metas.progress.project_completion_date` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.repository.GoalRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.repository.InMemoryGoalRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.status.can_transition` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.status.from_pt_string` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.status.next_status` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.status.to_pt_string` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.value_objects.Goal` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.metas.value_objects.GoalStatus` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.metas.value_objects.Period` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.metas.value_objects.Progress` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.metas.value_objects.ProgressTransition` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.notifications.map_notification_to_pt` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.org.attach_user_to_org` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.org.ensure_personal_org` | personal-finance | 1 |
| `noctusai_lib.domain.org.provision_invited_identity` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.org.sync_org_metadata` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.permissions.repo.FakePermissionGrantRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.permissions.repo.PermissionGrantRepository` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.permissions.repo.RealSupabasePermissionGrantRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.permissions.repo.make_permission_grant_repository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.access.compute_capabilities` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.BackfillReport` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.CATEGORY_OPENAI_EDIT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.CATEGORY_OPENAI_TEXT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.CATEGORY_OPENAI_VISION` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.RecordedCost` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.UnpricedModelError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.costs.backfill_fx` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.costs.build_cost_row` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.catalog_entry` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.price_usage_usd` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.costs.record_ai_cost` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.dataset.CommentRequiredError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.dataset.DecisionOutcome` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.dataset.PhotoNotDecidableError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.dataset.build_dataset_record` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.dataset.record_decision` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.guide.GuideNotActiveError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.guide.GuideVersionNotFoundError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.guide.activate_version` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.guide.compose_effective_guide` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.guide.create_draft` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.guide.generate_draft_from_pool` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.guide.normalize_text` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.guide.resolve_effective_guide` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.guide.restore_version` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.EditQuotaExceededError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.PhotoEditingConfigError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.build_handlers` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.build_worker` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_avaliar` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_edit` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_fx_backfill` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_ingest` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_lote_pronto` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_propor_regras` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_regen_guia` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.handle_submit_lote` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.handlers.is_retryable` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.learning.Actor` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.learning.InvalidModelOutputError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.learning.RuleDecisionForbiddenError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.learning.RuleNotFoundError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.learning.decide_rule` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.learning.propose_rules` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.naming.EDITED_NAME` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.naming.ORIGINAL_NAME` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.naming.STAGING_SUFFIX` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.naming.STAGING_WATERMARK_TEXT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.naming.is_staged` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.naming.storage_path` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.naming.upload_path` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.naming.zip_entry_name` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.naming.zip_file_name` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.ECONOMICO_IMPLEMENTED` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.pipeline.NotFoundError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.pipeline.PhotoNotRetryableError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.SubmissionError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.pipeline.add_photo_bytes` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.enqueue_batch_ready_check` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.enqueue_edit` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.enqueue_evaluation` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.enqueue_fx_backfill` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.retry_photo` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.schedule_guide_regen` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.pipeline.schedule_rule_proposal` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.pipeline.submit_batch` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.pipeline.validate_submission` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.ports.BatchReadyNotice` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.ports.BatchReadyNotifier` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.FakeStructuredLlm` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.InMemoryPhotoStorage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.LlmStructuredAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.PhotoEditingConfig` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.PhotoEditingPorts` | lib:noctusai_lib | 8 |
| `noctusai_lib.domain.photo_editing.ports.PhotoStorage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.RecordingNotifier` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.StructuredLlm` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.StructuredResult` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.ports.TokenUsage` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.ports.openai_image_edit_factory` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts._base.PromptTemplate` | lib:noctusai_lib | 6 |
| `noctusai_lib.domain.photo_editing.prompts._base.RenderedPrompt` | lib:noctusai_lib | 6 |
| `noctusai_lib.domain.photo_editing.prompts.edit.EDIT_PROMPT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.edit.render_edit_prompt` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.prompts.evaluator.EVALUATOR_PROMPT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.evaluator.render_evaluator_prompt` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.prompts.note_writer.ModelMetrics` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.note_writer.NOTE_WRITER_PROMPT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.note_writer.render_note_writer_prompt` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.rule_proposer.RULE_PROPOSER_PROMPT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.rule_proposer.render_rule_proposer_prompt` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.prompts.style_guide.STYLE_GUIDE_PROMPT` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.prompts.style_guide.render_style_guide_prompt` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.repository.InMemoryPhotoEditingRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.repository.PhotoEditingRepository` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.repository.RepositoryError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.repository.SupabasePhotoEditingRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.repository.make_photo_editing_repository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.Batch` | lib:noctusai_lib | 5 |
| `noctusai_lib.domain.photo_editing.types.BatchStatus` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.photo_editing.types.CostLedgerRow` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.DatasetRecord` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.Decision` | lib:noctusai_lib | 5 |
| `noctusai_lib.domain.photo_editing.types.EditAttempt` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.EditType` | lib:noctusai_lib | 7 |
| `noctusai_lib.domain.photo_editing.types.EffectiveGuide` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.types.Evaluation` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.GuideStatus` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.IllegalTransitionError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.JobType` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.photo_editing.types.LlmUsageRow` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.OrgRule` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.types.OrgSettings` | lib:noctusai_lib | 5 |
| `noctusai_lib.domain.photo_editing.types.PHOTO_CURATOR_PERMISSION` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.Photo` | lib:noctusai_lib | 6 |
| `noctusai_lib.domain.photo_editing.types.PhotoEvent` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.types.PhotoStatus` | lib:noctusai_lib | 6 |
| `noctusai_lib.domain.photo_editing.types.PlatformSettings` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.ProposalCursor` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.types.ReferencePair` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.ReviewDecision` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.types.Room` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.RuleSet` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.RuleStatus` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.photo_editing.types.Speed` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.photo_editing.types.StyleGuide` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.photo_editing.types.batch_state_signature` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.can_transition` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.debounce_bucket` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_avaliar` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_edit` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_fx_backfill` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_ingest` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_lote_pronto` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_propor_regras` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_regen_guia` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.dedupe_submit` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.types.sha256_text` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.zipper.BatchNotDecidedError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.zipper.NothingApprovedError` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.zipper.build_batch_zip` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.zipper.build_zip` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.photo_editing.zipper.plan_zip` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.pipeline.config.PipelineConfig` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.pipeline.ordering.position_of` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.pipeline.stages.create_stage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.pipeline.stages.delete_stage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.pipeline.stages.get_stage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.pipeline.stages.list_stages` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.pipeline.stages.reorder_stages` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.pipeline.stages.update_stage` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.real_estate.imovel.ImovelFoto` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.real_estate.imovel.ImovelPage` | lib:noctusai_lib | 4 |
| `noctusai_lib.domain.real_estate.imovel.caracteristica_slug` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.real_estate.imovel.derive_finalidades` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.real_estate.imovel.parse_caracteristicas` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.real_estate.imovel.parse_corretores` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.real_estate.imovel.parse_imovel_fotos` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.real_estate.matching.MIN_PRECO` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.MIN_REGIAO` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.MIN_SPECS` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.calcular_alinhamento_interesses` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.calcular_compatibilidade_preco` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.calcular_compatibilidade_regiao` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.calcular_compatibilidade_specs` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.calcular_qualidade_anuncio` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.matching.passa_filtros_minimos` | erp-imobiliario | 1 |
| `noctusai_lib.domain.real_estate.validators.PRODUCT_CODE_PATTERN` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.real_estate.validators.extract_product_code` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.service_role_bypass` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.set_search_path` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.updated_at_function` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.updated_at_trigger` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.texto_ptbr.CENTAVO` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.brl_por_extenso` | social-wiring | 2 |
| `noctusai_lib.domain.texto_ptbr.data_por_extenso` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.dias_por_extenso` | social-wiring | 3 |
| `noctusai_lib.domain.texto_ptbr.formatar_brl` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.formatar_data_br` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.formatar_inteiro_br` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.numero_com_extenso` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.ordinal_por_extenso` | social-wiring | 2 |
| `noctusai_lib.domain.texto_ptbr.parse_brl` | social-wiring | 2 |
| `noctusai_lib.domain.texto_ptbr.percentual_por_extenso` | social-wiring | 1 |
| `noctusai_lib.domain.texto_ptbr.reais_por_extenso` | social-wiring | 2 |
| `noctusai_lib.graph.extract_cli.walk_cli` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_code.BarrelResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_code.CodeRoot` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_code.walk` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_docs.walk_findings` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_docs.walk_kb` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_docs.walk_projects` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_harness.walk_harness` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_history.walk_auto_improvement` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_landscape.walk_kb_chapters` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_landscape.walk_landscape` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_memory.walk_memory` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_mined.ingest_mined_rows` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.extract_products.walk_products` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.html_template.HTML_TEMPLATE` | lib:noctusai_lib | 1 |
| `noctusai_lib.graph.schema.Confidence` | lib:noctusai_lib | 9 |
| `noctusai_lib.graph.schema.Edge` | lib:noctusai_lib | 9 |
| `noctusai_lib.graph.schema.EdgeKind` | lib:noctusai_lib | 9 |
| `noctusai_lib.graph.schema.Graph` | lib:noctusai_lib | 12 |
| `noctusai_lib.graph.schema.Node` | lib:noctusai_lib | 9 |
| `noctusai_lib.graph.schema.NodeKind` | lib:noctusai_lib | 10 |
| `noctusai_lib.integrations.credential_resolvers.CALENDAR_PROVIDER` | social-wiring | 2 |
| `noctusai_lib.integrations.credential_resolvers.CredentialStoreDriveResolver` | social-wiring | 1 |
| `noctusai_lib.integrations.credential_resolvers.CredentialStoreMetaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.credential_resolvers.META_PROVIDER` | social-wiring | 1 |
| `noctusai_lib.integrations.documents.abnt.clip_ranges` | social-wiring | 2 |
| `noctusai_lib.integrations.documents.abnt.runs_from_ranges` | social-wiring | 1 |
| `noctusai_lib.integrations.documents.birthdate.find_birthdate` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.civil_status.find_data_casamento` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.civil_status.find_data_emissao` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.civil_status.find_estado_civil` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.civil_status.find_regime_bens` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.cpf.find_cpf` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.cpf.only_digits` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.fake.classify_kind` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.gender.find_gender` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.labels.Achado` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.documents.labels.label_before` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.documents.ladder.DocumentTextLadder` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.documents.ladder.looks_like_pdf` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.matricula.find_matricula` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.matricula.normalize` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.ALTA` | social-wiring | 1 |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.AtoReferido` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.NENHUMA` | social-wiring | 1 |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.Parte` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.cpf_cnpj_valido` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.matricula_ato_detalhes.parse_detalhes_json` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.matricula_atos.normalized_with_offsets` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.name.find_name` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.rg.find_rg` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.rg.find_rg_orgao` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.text.normalize_lines` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.documents.transcription.FakeDocumentTranscriber` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.documents.types.IdentityDocumentKind` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.docx_render.docxtpl_adapter.DocxtplRenderAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.docx_render.fake_adapter.FakeDocxRenderAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.docx_render.fake_adapter.FakeRichText` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.docx_render.types.DocxRenderError` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.docx_render.types.MissingPlaceholderError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.fx.bcb_adapter.BcbPtaxAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.fx.errors.FxBulletinNotFoundError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.fx.errors.FxError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.fx.errors.FxUpstreamError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.fx.fake_adapter.FakeFxRateAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.fx.mappers.format_bcb_date` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.fx.mappers.parse_ptax_response` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.fx.types.FxRateAdapter` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.fx.types.PtaxRate` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.gmail.credentials.GmailCredentialResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.gmail.fake.FakeGmailClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.gmail.protocol.GmailClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.gmail.real.RealGmailClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.gmail.types.GMAIL_MODIFY_SCOPE` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.gmail.types.GmailLabel` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.gmail.types.GmailListResult` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.gmail.types.GmailMessage` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.gmail.types.SUBJECT_MAX_LEN` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.gmail.types.SendResult` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_calendar.credentials.CalendarCredentialResolver` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.google_drive.factory.make_drive_downloader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.fake.FakeDriveDownloader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.mappers.parse_drive_url` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.protocol.DriveDownloader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.reader_factory.make_drive_reader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.reader_types.DriveReader` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.google_drive.reader_types.FOLDER_MIME` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.RENDERED_AS_BINARY` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.RENDERED_AS_CANONICAL` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.RENDERED_AS_CSV` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.RENDERED_AS_PASSTHROUGH` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.RENDERED_AS_PDF_TEXT` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.RENDERED_AS_TEXT` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.real.RealDriveDownloader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.real_reader.RealDriveReader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.types.DriveFile` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_scopes.diagnose_consent_screen_gaps` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_scopes.discover_granted_scopes` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_scopes.resolve_google_scopes` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditContentPolicyViolation` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditFatalError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditInvalidSize` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditNotConfigured` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditRateLimited` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditRetryableError` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditServerError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.exceptions.ImageEditTimeout` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.fake_adapter.FakeImageEditAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.image_edit.openai_adapter.OpenAIImageEditAdapter` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.types.EditedImage` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.image_edit.types.ImageEditAdapter` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.image_edit.types.ImageEditCapabilities` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.image_edit.types.ImageEditRequest` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.image_edit.types.ImageEditResult` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.image_edit.types.ImageEditUsage` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.image_edit.types.capabilities_for_model` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.image_gen.gemini_adapter.GeminiImageGenAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.image_gen.types.GeneratedImage` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.imaging.fake_adapter.FakeImagingAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imaging.real_adapter.RealImagingAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imaging.types.DEFAULT_JPEG_QUALITY` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imaging.types.DEFAULT_WATERMARK_TEXT` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.imaging.types.ImagingAdapter` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imaging.types.NormalizedImage` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.imaging.types.UnsupportedImageFormatError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.imovelweb.auth.ImovelWebAuth` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.endpoints.IMOVELWEB_SANDBOX_BR` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imovelweb.endpoints.IMOVELWEB_SANDBOX_WINDOW` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imovelweb.endpoints.base_url` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.endpoints.is_sandbox_host` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imovelweb.endpoints.preferred_path` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.errors.ImovelWebConfigError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.imovelweb.errors.ImovelWebUpstreamError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imovelweb.errors.redact_secrets` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.imovelweb.fake.FakeImovelWebClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.real.DEFAULT_TIMEOUT_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.real.ImovelWebClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.real.describe_error_body` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.imovelweb.types.CallbackConfig` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.imovelweb.types.ImovelWebLead` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.llm.budget.compute_status` | core | 1 |
| `noctusai_lib.integrations.llm.budget.configure_budget_module` | lib:noctusai_seed | 1 |
| `noctusai_lib.integrations.llm.budget.enforce_budget` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.cache.build_cache_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.cache.flush_for_model` | core | 1 |
| `noctusai_lib.integrations.llm.cache.try_get` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.cache.try_set` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.client.configure_llm` | lib:noctusai_seed | 2 |
| `noctusai_lib.integrations.llm.client.get_provider` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.llm.client.resolve_api_key` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.llm.client.shutdown_llm` | lib:noctusai_seed | 2 |
| `noctusai_lib.integrations.llm.config.LLMConfig` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.exceptions.LLMBudgetExceeded` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.exceptions.ProviderNotImplemented` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.inputs.image_bytes_to_data_url` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.models.ModelEntry` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.models.all_providers` | core | 1 |
| `noctusai_lib.integrations.llm.providers.base.LLMProvider` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.llm.registry.get_provider_class` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.registry.register` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.llm.usage.SupabaseUsageSink` | lib:noctusai_seed | 1 |
| `noctusai_lib.integrations.llm.usage.estimate_cost_usd` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.usage.record_usage` | lib:noctusai_lib | 16 |
| `noctusai_lib.integrations.llm.vision.analyze_image` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.mailchimp.fake_adapter.FakeMailchimpClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.mailchimp.mappers.parse_server_prefix` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.mailchimp.mappers.raw_to_audience` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.mailchimp.mappers.raw_to_campaign` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.mailchimp.mappers.raw_to_member` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.mailchimp.mappers.raw_to_segment` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.mailchimp.mappers.raw_to_template` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.mailchimp.mappers.subscriber_hash` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.mailchimp.mappers.template_edit_url` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.mailchimp.types.Audience` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.mailchimp.types.Campaign` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.mailchimp.types.Member` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.mailchimp.types.Page` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.mailchimp.types.Segment` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.mailchimp.types.Template` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.media.fake_adapter.FakeMediaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.pdf_text.PdfPage` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.pdf_text.PdfTextLayer` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.pdf_text.classify_pdf_text_layer` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.media.pdf_text.extract_pdf_text` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.media.pdf_text.pdf_text_tooling_available` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.real_adapter.OpenAIMediaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.types.InboundMedia` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.media.types.MediaKind` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.media.types.MediaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.types.ResolvedMedia` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.media.types.classify_media_kind` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta._meta_api.DEFAULT_GRAPH_VERSION` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.IG_AUTHORIZE_BASE` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.IG_CODE_EXCHANGE_BASE` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.IG_GRAPH_BASE` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta._meta_api.META_KITCHEN_SINK_SCOPES` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.meta._meta_api.discover_app_permissions` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta._meta_api.exchange_code_for_token_bundle` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.exchange_for_long_lived` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.poll_media_status` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta._meta_api.resolve_oauth_scopes` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.credentials.MetaCredentialResolver` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.credentials.OAuthMetaCredentials` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.instagram_login_adapter.InstagramLoginMessagingAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.leadgen_webhook.LeadgenUpdateEvent` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.FB_COMMENT_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_ACCOUNT_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_ACCOUNT_INSIGHT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_COMMENT_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_CONVERSATION_FIELDS` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.IG_DM_FIELDS` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.IG_MEDIA_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_MEDIA_INSIGHT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_TOTAL_VALUE_ACCOUNT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.ME_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.PAGE_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.PAGE_IG_FIELD` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.PAGE_INSIGHT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.POST_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.POST_INSIGHT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.ad_account_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ad_activity_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ad_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ad_insights_row_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ad_set_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.campaign_from_body` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.conversation_from_body` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.mappers.direct_message_from_body` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.mappers.facebook_comment_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ig_account_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ig_media_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.insights_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.instagram_comment_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.lead_from_body` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.leadgen_form_from_body` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.page_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.page_subscription_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.parse_graph_datetime` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.post_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.router.make_meta_router` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.types.AdCreative` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.AdCreativeSpec` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.AdSetSpec` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.AdSpec` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.CampaignSpec` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.MediaProcessingStatus` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.types.PageSubscription` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.meta.types.PublishedMedia` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.PublishedPost` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.n8n.mappers.WORKFLOW_PUT_ALLOWED_KEYS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.n8n.mappers.extract_error_message` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.n8n.mappers.extract_webhook_trigger` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.n8n.mappers.normalize_base_url` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.mappers.raw_to_credential` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.mappers.raw_to_execution` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.n8n.mappers.raw_to_tag` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.mappers.sanitize_workflow_put_body` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.n8n.mappers.tag_refs_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.mappers.webhook_url` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.n8n_adapter.HttpxN8nClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.n8n.types.Credential` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.n8n.types.Execution` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.n8n.types.N8nAuthError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.types.N8nRateLimitedError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.types.N8nRejectedError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.types.N8nUnreachableError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.n8n.types.RunResult` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.n8n.types.Tag` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.n8n.types.Workflow` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.olx.endpoints.OLX_LEAD_MANAGER_BASE_URL` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.olx.errors.OlxConfigError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.olx.errors.OlxError` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.errors.OlxUpstreamError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.olx.errors.redact_secret` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.fake.FakeOlxLeadManagerClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.normalizers.OLX_SOURCE_SLUG` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.real.DEFAULT_TIMEOUT_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.real.OlxLeadManagerClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.types.OLX_LEAD_ORIGIN_MCMV` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.types.OLX_LEAD_ORIGIN_STANDARD` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.olx.types.OlxLead` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.outbound_webhook.fake.FakeOutboundWebhookSender` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.outbound_webhook.real.DEFAULT_TIMEOUT_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.outbound_webhook.real.DEFAULT_USER_AGENT` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.outbound_webhook.real.HttpxOutboundWebhookSender` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.outbound_webhook.types.DeliveryAttempt` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.outbound_webhook.types.DeliveryFailureKind` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.outbound_webhook.types.truncate_body` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.payments.errors.PaymentGatewayError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.payments.fake.FakePaymentGateway` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.payments.real_asaas.AsaasPaymentGateway` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.payments.real_asaas.DEFAULT_BASE_URL` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.payments.real_asaas.DEFAULT_TIMEOUT_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.payments.real_stripe.StripePaymentGateway` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.payments.types.FeeBreakdown` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.payments.types.GatewayCustomer` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.payments.types.GatewaySubscription` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.payments.types.Money` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.payments.types.PaymentGatewayName` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.payments.types.SubscriptionRequest` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.persistence.types.Op` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.persistence.types.PersistenceError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.persistence.types.QuerySpec` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.persistence.types.RecordNotFound` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.persistence.types.RecordStore` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.quota.factory.make_quota_tracker` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.quota.in_memory.InMemoryQuotaTracker` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.quota.protocol.QuotaTracker` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.quota.redis_backend.RedisQuotaTracker` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.quota.types.QuotaCheck` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.quota.types.QuotaConfig` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.rate_limit.acquire_async` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.rate_limit.retry_with_backoff_async` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.storage.local.LocalFilesystemStorageBackend` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.storage.supabase.SupabaseStorageBackend` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.storage.types.BlobMetadata` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.storage.types.StoredBlob` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.supabase_identity.UserIdentity` | therapy-platform | 3 |
| `noctusai_lib.integrations.supabase_identity.fetch_user_identities` | therapy-platform | 3 |
| `noctusai_lib.integrations.svg_render.resvg_adapter.ResvgRenderAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.svg_render.resvg_adapter.bundled_font_files` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.svg_render.types.RenderedImage` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.vista.client.DEFAULT_PAGE_SIZE` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.DEFAULT_TIMEOUT_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaCallResult` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaClient` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.vista.client.VistaConfigError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.vista.client.VistaError` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.vista.client.VistaFieldNotAvailable` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaNotFound` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaPermissionDenied` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaUpstreamError` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.extract_items` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.redact_api_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.fake.FakeVistaClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.fake_adapter.FakeVistaAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.imovel_normalizer.vista_to_imovel` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.protocol.VistaCRMAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.real.VistaRESTAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseAgencia` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseCliente` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseClienteDetalhes` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseImovel` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseImovelDetalhes` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseUsuario` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.client.RECOVER_READY_STATUSES` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.client.recovery_outcome` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.dedup.InMemoryWebhookDedup` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.dedup.RedisWebhookDedup` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.dedup.SetnxRedis` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.dedup.WebhookDedup` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.lid_auth.InMemoryLidPhoneCache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.LidPhoneCache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.RedisLidPhoneCache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.extract_resolved_remote` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.get_lid_phone_cache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.is_authorized` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.is_phone_jid` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.remember_lid_phone` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.resolve_canonical_session` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.mappers.build_send_text_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.mappers.parse_waha_inbound_message` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.mappers.phone_from_chat_id` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.mappers.rewrite_vendor_media_url` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.meta_cloud_client.DEFAULT_BASE_URL` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.meta_cloud_client.FakeMetaCloudClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.meta_cloud_client.MetaCloudClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.FakeResponseRegistry` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.PersistentResponseRegistry` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.ResponseRegistry` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.ResponseSample` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.ResponseSampleSink` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.fingerprint_response` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.response_registry.get_response_registry` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.router.create_whatsapp_webhook_router` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.settings.WhatsAppSettings` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppIgnoredEvent` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppInboundMessage` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppMedia` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppPayloadError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.youtube.real.RealYoutubeClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.types.Channel` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.youtube.types.DESCRIPTION_MAX_LEN` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.youtube.types.Playlist` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.types.ProcessingStatus` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.youtube.types.SHORTS_MAX_DURATION_SECONDS` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.types.TITLE_MAX_LEN` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.youtube.types.UPLOAD_QUOTA_UNITS` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.youtube.types.Video` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.youtube.types.VideoUpload` | lib:noctusai_lib | 4 |
| `noctusai_lib.logging_config.resolve_json_logs` | lib:noctusai_seed | 1 |
| `noctusai_lib.primitives._correlation.get_correlation_id` | lib:noctusai_lib | 2 |
| `noctusai_lib.primitives.exceptions.ConflictError` | social-wiring | 10 |
| `noctusai_lib.primitives.exceptions.app_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.generic_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.http_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.postgrest_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.validation_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.image_sizing.compute_edit_size` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.phone.normalize_phone` | social-wiring | 3 |
| `noctusai_lib.primitives.phone.phone_digits` | erp-imobiliario | 1 |
| `noctusai_lib.primitives.phone.phone_search_digits` | social-wiring | 2 |
| `noctusai_lib.primitives.responses.calculate_pagination` | core | 1 |
| `noctusai_lib.primitives.responses.deleted_response` | social-wiring | 3 |
| `noctusai_lib.primitives.roles.MANAGE_TEAM_ROLES` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.roles.ORG_ROLE_LABELS` | lib:noctusai_seed | 1 |
| `noctusai_lib.primitives.tasks.NoRunningLoopError` | core | 1 |
| `noctusai_lib.primitives.timeutil.current_day_ref` | erp-imobiliario | 4 |
| `noctusai_lib.primitives.timeutil.current_month_ref` | erp-imobiliario | 5 |
| `noctusai_lib.primitives.timeutil.today_utc` | erp-imobiliario | 4 |
| `noctusai_lib.realtime.bus.RealtimeEvent` | lib:noctusai_lib | 2 |
| `noctusai_lib.realtime.bus.RedisRealtimeBus` | lib:noctusai_lib | 1 |
| `noctusai_lib.realtime.bus.StreamRedis` | lib:noctusai_lib | 1 |
| `noctusai_lib.realtime.sse.sse_event_stream` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.app_config.AppConfigDecryptError` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.app_config.META_APP_ID_KEY` | social-wiring | 1 |
| `noctusai_lib.security.app_config.META_APP_SECRET_KEY` | social-wiring | 1 |
| `noctusai_lib.security.encrypted_tokens.MultiKeyDecryptor` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.encrypted_tokens.generate_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.encrypted_tokens.rotate_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.factory.make_oauth_provider` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.protocol.OAuthProvider` | lib:noctusai_lib | 3 |
| `noctusai_lib.security.oauth.router.oauth_router` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.scopes.FakeScopeResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.scopes.GoogleScopeResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.scopes.MetaScopeResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.scopes.ScopeResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.scopes.make_scope_resolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.types.AuthorizationURL` | lib:noctusai_lib | 4 |
| `noctusai_lib.security.oauth.types.OAuthCallbackResult` | lib:noctusai_lib | 3 |
| `noctusai_lib.security.oauth.types.TokenSet` | lib:noctusai_lib | 4 |
| `noctusai_lib.security.secrets_scan.find_secret` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.token_store.supabase_store.DEFAULT_TABLE` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.DEFAULT_MAX_AGE_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.GRUPO_OLX_BASIC_USERNAME` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.static_secret_resolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.verify_basic_shared_secret` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.verify_hmac_sha256` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.verify_hmac_sha256_hex` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.webhook_signatures.verify_svix_signature` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing._schema_cache.get_schema_map` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing._schema_cache.reset_cache` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing._schema_cache.set_cache_for_tests` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.clients.TEST_ORG_ID` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing.conftest_helpers.purge_shadowing_editable_finders` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.migration_parser.parse_files` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.migration_parser.parse_sql` | social-wiring | 2 |
| `noctusai_lib.testing.schema_errors.MockCheckViolation` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing.schema_errors.MockSchemaError` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing.schema_errors.MockUnknownTableError` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing.seed_singleton_guard.SingletonSpec` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.seed_singleton_guard.guarded_seed_singletons` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.seed_singleton_guard.make_seed_singleton_guard` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.seed_singleton_guard.restore_seed_singletons` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.seed_singleton_guard.snapshot_seed_singletons` | lib:noctusai_lib | 1 |
| `noctusai_seed.ai_feedback_router.create_ai_feedback_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.ai_router.create_ai_outputs_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.apply_sqlite_migrations.apply_sqlite_migrations` | lib:noctusai_seed | 2 |
| `noctusai_seed.auth_router.ApiTokenCreateRequest` | erp-imobiliario | 4 |
| `noctusai_seed.dev_auth.dev_auth_enabled` | lib:noctusai_seed | 1 |
| `noctusai_seed.dev_auth.make_dev_auth_get_current_user` | lib:noctusai_seed | 1 |
| `noctusai_seed.health.HealthCheckHook` | lib:noctusai_seed | 1 |
| `noctusai_seed.health.mount_health_endpoints` | lib:noctusai_seed | 2 |
| `noctusai_seed.llm_defaults.DEFAULT_LLM_CONFIG` | lib:noctusai_seed | 1 |
| `noctusai_seed.llm_defaults.default_llm_config` | lib:noctusai_seed | 2 |
| `noctusai_seed.llm_router.create_llm_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.routers.build_standard_routers` | lib:noctusai_seed | 1 |
| `noctusai_seed.scheduler_router.create_scheduler_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.upload_route_overrides.enforce_upload_route_overrides` | lib:noctusai_seed | 1 |
| `noctusai_seed.whatsapp_admin_router.create_whatsapp_admin_router` | lib:noctusai_seed | 1 |

## Duplication candidates

Public top-level functions/classes with the **same name** in 2+ products,
and **not** already exported by the shared lib. Strong signal that they
belong in `noctusai_lib`. Name-based matching has false positives —
review occurrences before absorbing.

### `AtivosService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/ativos_service.py:15`
- `personal-finance` — `products/personal-finance/backend/app/services/ativos_service.py:10`

### `BIService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/bi_service.py:16`
- `igig` — `products/igig/backend/app/services/bi_service.py:49`

### `ClientesService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/clientes_service.py:62`
- `p-studio` — `products/p-studio/backend/app/services/cadastros_service.py:12`

### `DashboardService` (class)

- `p-studio` — `products/p-studio/backend/app/services/dashboard_service.py:39`
- `personal-finance` — `products/personal-finance/backend/app/services/dashboard_service.py:12`

### `EmailService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/email_service.py:69`
- `social-wiring` — `products/social-wiring/backend/app/services/email_service.py:46`

### `EncryptionNotConfigured` (class)

- `p-studio` — `products/p-studio/backend/app/services/credenciais.py:83`
- `social-wiring` — `products/social-wiring/backend/app/services/credential_vault.py:67`

### `FinanceiroService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/financeiro_service.py:54`
- `igig` — `products/igig/backend/app/services/financeiro_service.py:69`
- `p-studio` — `products/p-studio/backend/app/services/financeiro_service.py:83`

### `ImoveisService` (class)

- `p-studio` — `products/p-studio/backend/app/services/cadastros_service.py:42`
- `social-wiring` — `products/social-wiring/backend/app/services/imoveis_service.py:345`

### `TaskCreate` (class)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/routers/roadmap_router.py:53`
- `daily-life` — `products/daily-life/backend/app/routers/tasks.py:28`

### `TaskUpdate` (class)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/routers/roadmap_router.py:60`
- `daily-life` — `products/daily-life/backend/app/routers/tasks.py:36`

### `adicionar_item` (async def)

- `igig` — `products/igig/backend/app/routers/financeiro_router.py:107`
- `personal-finance` — `products/personal-finance/backend/app/routers/watchlist.py:51`

### `atualizar` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:108`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/meta_periodos.py:142`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_empresa.py:103`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/regras_pontuacao.py:119`
- `p-studio` — `products/p-studio/backend/app/routers/captacoes_router.py:48`
- `p-studio` — `products/p-studio/backend/app/routers/financeiro_router.py:73`
- `p-studio` — `products/p-studio/backend/app/routers/negocios_router.py:47`
- `p-studio` — `products/p-studio/backend/app/routers/producoes_router.py:51`

### `atualizar_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:266`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:57`

### `atualizar_cliente` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/clientes.py:161`
- `igig` — `products/igig/backend/app/routers/cliente_router.py:96`

### `atualizar_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:164`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:229`

### `atualizar_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:138`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:371`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:59`

### `build_audit_record` (def)

- `daily-life` — `products/daily-life/backend/app/services/audit_hook.py:125`
- `personal-finance` — `products/personal-finance/backend/app/services/audit_hook.py:126`

### `build_credential_store` (def)

- `p-studio` — `products/p-studio/backend/app/services/credenciais.py:149`
- `social-wiring` — `products/social-wiring/backend/app/services/account_credentials.py:200`
- `social-wiring` — `products/social-wiring/backend/app/services/credential_vault.py:102`

### `check_openai_configured` (def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/ai_service.py:123`
- `personal-finance` — `products/personal-finance/backend/app/services/ai_service.py:72`

### `coerce_org_uuid` (def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/dependencies.py:116`
- `agents` — `products/agents/backend/app/dependencies.py:94`
- `daily-life` — `products/daily-life/backend/app/dependencies.py:66`
- `igig` — `products/igig/backend/app/dependencies.py:89`
- `knowledge-extractor` — `products/knowledge-extractor/backend/app/dependencies.py:62`
- `orbity` — `products/orbity/backend/app/dependencies.py:79`
- `seed` — `products/seed/backend/app/dependencies.py:79`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:242`

### `create_task` (async def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/routers/roadmap_router.py:157`
- `orbity` — `products/orbity/backend/app/routers/tasks_router.py:93`

### `criar` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:74`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/meta_periodos.py:77`
- `p-studio` — `products/p-studio/backend/app/routers/captacoes_router.py:36`
- `p-studio` — `products/p-studio/backend/app/routers/financeiro_router.py:61`
- `p-studio` — `products/p-studio/backend/app/routers/negocios_router.py:35`
- `p-studio` — `products/p-studio/backend/app/routers/producoes_router.py:35`

### `criar_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:215`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:46`

### `criar_cliente` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/clientes.py:130`
- `igig` — `products/igig/backend/app/routers/cliente_router.py:66`

### `criar_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:120`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:151`

### `criar_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:90`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:352`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:48`

### `criar_orcamento` (async def)

- `igig` — `products/igig/backend/app/routers/comercial_router.py:169`
- `personal-finance` — `products/personal-finance/backend/app/routers/orcamentos.py:59`

### `criar_tarefa` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/tasks.py:80`
- `igig` — `products/igig/backend/app/routers/esteira_router.py:92`

### `dashboard` (def)

- `adconnect` — `products/adconnect/backend/app/routers/admin.py:102`
- `p-studio` — `products/p-studio/backend/app/routers/dashboard_router.py:13`

### `dashboard_resumo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/bi.py:127`
- `personal-finance` — `products/personal-finance/backend/app/routers/dashboard.py:22`

### `enviar_para_assinatura` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/signature_provider.py:49`
- `igig` — `products/igig/backend/app/services/contrato_documento.py:96`

### `example_webhook` (async def)

- `igig` — `products/igig/backend/app/routers/webhook_router.py:76`
- `orbity` — `products/orbity/backend/app/routers/webhook_router.py:76`
- `seed` — `products/seed/backend/app/routers/webhook_router.py:76`

### `excluir_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:313`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:71`

### `excluir_meta` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:386`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:73`

### `fluxo_caixa` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/financeiro.py:184`
- `personal-finance` — `products/personal-finance/backend/app/routers/relatorios.py:36`

### `gerar_pdf_contrato` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/pdf.py:21`
- `igig` — `products/igig/backend/app/services/contrato_documento.py:42`

### `get_admin_client` (def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/dependencies.py:100`
- `agents` — `products/agents/backend/app/dependencies.py:74`
- `core` — `products/core/backend/app/database.py:32`
- `daily-life` — `products/daily-life/backend/app/dependencies.py:62`
- `igig` — `products/igig/backend/app/dependencies.py:85`
- `knowledge-extractor` — `products/knowledge-extractor/backend/app/dependencies.py:58`
- `orbity` — `products/orbity/backend/app/dependencies.py:75`
- `p-studio` — `products/p-studio/backend/app/database.py:36`
- `seed` — `products/seed/backend/app/dependencies.py:75`
- `social-wiring` — `products/social-wiring/backend/app/database.py:29`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:129`

### `get_audit_writer` (def)

- `core` — `products/core/backend/app/services/audit_hook.py:93`
- `daily-life` — `products/daily-life/backend/app/services/audit_hook.py:97`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/audit_hook.py:93`
- `personal-finance` — `products/personal-finance/backend/app/services/audit_hook.py:98`
- `therapy-platform` — `products/therapy-platform/backend/app/services/audit_hook.py:353`

### `get_conversation` (async def)

- `agents` — `products/agents/backend/app/routers/conversations_router.py:198`
- `social-wiring` — `products/social-wiring/backend/app/routers/intake_monitor_router.py:131`

### `get_core_client` (def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/dependencies.py:104`
- `agents` — `products/agents/backend/app/dependencies.py:78`
- `social-wiring` — `products/social-wiring/backend/app/database.py:23`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:209`

### `get_current_user_org_unified` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/dependencies.py:392`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:467`

### `get_invoice` (def)

- `adconnect` — `products/adconnect/backend/app/routers/financial.py:174`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/invoices.py:73`
- `therapy-platform` — `products/therapy-platform/backend/app/services/invoice_service.py:83`

### `get_me` (async def)

- `core` — `products/core/backend/app/routers/auth.py:176`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/auth.py:120`

### `get_message_history` (def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:300`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:189`

### `get_org_id` (def)

- `adconnect` — `products/adconnect/backend/app/dependencies.py:67`
- `core` — `products/core/backend/app/dependencies.py:123`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/dependencies.py:80`

### `get_product` (def)

- `adconnect` — `products/adconnect/backend/app/routers/products.py:120`
- `adconnect` — `products/adconnect/backend/app/services/products_service.py:183`
- `core` — `products/core/backend/app/routers/products.py:110`

### `get_revenue` (async def)

- `core` — `products/core/backend/app/routers/analytics.py:81`
- `orbity` — `products/orbity/backend/app/routers/financial_router.py:335`

### `get_supabase_client` (def)

- `core` — `products/core/backend/app/database.py:23`
- `social-wiring` — `products/social-wiring/backend/app/database.py:17`
- `therapy-platform` — `products/therapy-platform/backend/app/dependencies.py:94`

### `get_user_client` (def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/dependencies.py:96`
- `adconnect` — `products/adconnect/backend/app/dependencies.py:132`
- `agents` — `products/agents/backend/app/dependencies.py:70`
- `daily-life` — `products/daily-life/backend/app/dependencies.py:58`
- `igig` — `products/igig/backend/app/dependencies.py:81`
- `knowledge-extractor` — `products/knowledge-extractor/backend/app/dependencies.py:54`
- `orbity` — `products/orbity/backend/app/dependencies.py:71`
- `p-studio` — `products/p-studio/backend/app/database.py:26`
- `personal-finance` — `products/personal-finance/backend/app/dependencies.py:62`
- `seed` — `products/seed/backend/app/dependencies.py:71`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:123`

### `list_approvals` (async def)

- `agents` — `products/agents/backend/app/routers/approvals_router.py:83`
- `orbity` — `products/orbity/backend/app/routers/social_content_router.py:359`

### `list_conversations` (async def)

- `agents` — `products/agents/backend/app/routers/conversations_router.py:175`
- `social-wiring` — `products/social-wiring/backend/app/routers/intake_monitor_router.py:101`
- `social-wiring` — `products/social-wiring/backend/app/routers/meta_dms_router.py:149`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/messaging.py:81`
- `therapy-platform` — `products/therapy-platform/backend/app/services/messaging_service.py:263`

### `list_invoices` (def)

- `adconnect` — `products/adconnect/backend/app/routers/admin.py:322`
- `adconnect` — `products/adconnect/backend/app/routers/financial.py:124`
- `core` — `products/core/backend/app/routers/billing.py:326`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/invoices.py:48`
- `therapy-platform` — `products/therapy-platform/backend/app/services/invoice_service.py:61`

### `list_messages` (async def)

- `agents` — `products/agents/backend/app/routers/conversations_router.py:208`
- `social-wiring` — `products/social-wiring/backend/app/routers/meta_dms_router.py:181`
- `social-wiring` — `products/social-wiring/backend/app/routers/whatsapp_connections_router.py:998`

### `list_reports` (def)

- `adconnect` — `products/adconnect/backend/app/routers/sellout.py:190`
- `orbity` — `products/orbity/backend/app/routers/reports_router.py:72`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/support.py:104`

### `list_tasks` (async def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/routers/roadmap_router.py:145`
- `orbity` — `products/orbity/backend/app/routers/tasks_router.py:63`

### `listar` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:63`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/meta_fechamentos.py:25`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/meta_periodos.py:66`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_empresa.py:48`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_equipe.py:34`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/regras_pontuacao.py:55`
- `p-studio` — `products/p-studio/backend/app/routers/captacoes_router.py:25`
- `p-studio` — `products/p-studio/backend/app/routers/financeiro_router.py:48`
- `p-studio` — `products/p-studio/backend/app/routers/negocios_router.py:30`
- `p-studio` — `products/p-studio/backend/app/routers/producoes_router.py:30`

### `listar_acessos` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/portal_cliente.py:119`
- `igig` — `products/igig/backend/app/routers/marca_router.py:282`

### `listar_ativos` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:140`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:15`

### `listar_checkins` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:198`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/campo.py:133`

### `listar_clientes` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/clientes.py:57`
- `igig` — `products/igig/backend/app/routers/cliente_router.py:39`

### `listar_eventos` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:76`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:98`
- `p-studio` — `products/p-studio/backend/app/routers/integracoes_router.py:149`

### `listar_itens` (async def)

- `igig` — `products/igig/backend/app/routers/financeiro_router.py:97`
- `personal-finance` — `products/personal-finance/backend/app/routers/orcamentos.py:47`

### `listar_leads` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/meta_api.py:151`
- `igig` — `products/igig/backend/app/routers/comercial_router.py:102`

### `listar_membros` (async def)

- `core` — `products/core/backend/app/routers/team.py:86`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:141`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/equipes_service.py:111`

### `listar_metas` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:63`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:319`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:15`

### `listar_metricas` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/metrics.py:93`
- `igig` — `products/igig/backend/app/routers/distribuicao_router.py:226`

### `listar_orcamentos` (async def)

- `igig` — `products/igig/backend/app/routers/comercial_router.py:203`
- `personal-finance` — `products/personal-finance/backend/app/routers/orcamentos.py:15`

### `login` (async def)

- `core` — `products/core/backend/app/routers/auth.py:134`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/auth.py:83`
- `therapy-platform` — `products/therapy-platform/backend/app/services/auth_service.py:234`

### `me` (def)

- `adconnect` — `products/adconnect/backend/app/routers/auth.py:58`
- `adconnect` — `products/adconnect/backend/app/routers/distributors.py:77`
- `p-studio` — `products/p-studio/backend/app/routers/me_router.py:11`

### `obter` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:98`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/meta_periodos.py:132`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_configuracao.py:37`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_empresa.py:93`
- `p-studio` — `products/p-studio/backend/app/routers/captacoes_router.py:43`
- `p-studio` — `products/p-studio/backend/app/routers/financeiro_router.py:68`
- `p-studio` — `products/p-studio/backend/app/routers/negocios_router.py:42`
- `p-studio` — `products/p-studio/backend/app/routers/producoes_router.py:46`

### `obter_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:204`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:35`

### `obter_cliente` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/clientes.py:117`
- `igig` — `products/igig/backend/app/routers/cliente_router.py:80`

### `obter_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:150`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:216`

### `obter_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:118`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:26`

### `registrar_checkin` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:180`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/campo.py:114`

### `remover_membro` (async def)

- `core` — `products/core/backend/app/routers/team.py:204`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:190`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/equipes_service.py:154`

### `resumo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_empresa.py:82`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas_equipe.py:68`
- `p-studio` — `products/p-studio/backend/app/routers/financeiro_router.py:37`

### `review` (async def)

- `adconnect` — `products/adconnect/backend/app/services/sellout_service.py:305`
- `therapy-platform` — `products/therapy-platform/backend/app/services/homework_service.py:79`

### `review_report` (async def)

- `adconnect` — `products/adconnect/backend/app/routers/sellout.py:215`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/support.py:127`
- `therapy-platform` — `products/therapy-platform/backend/app/services/messaging_service.py:686`

### `run_retention_sweep` (def)

- `core` — `products/core/backend/app/services/webhook_retention_service.py:51`
- `therapy-platform` — `products/therapy-platform/backend/app/services/audio_retention_service.py:147`

### `scan_text` (def)

- `knowledge-extractor` — `products/knowledge-extractor/backend/app/services/anonymization.py:212`
- `therapy-platform` — `products/therapy-platform/backend/app/services/crisis_service.py:75`

### `score_lead` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/ai_service.py:206`
- `orbity` — `products/orbity/backend/app/routers/crm_router.py:331`

### `search_kb` (async def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/routers/kb_router.py:134`
- `knowledge-extractor` — `products/knowledge-extractor/backend/app/routers/kb_router.py:44`

### `send_message` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:184`
- `social-wiring` — `products/social-wiring/backend/app/routers/meta_dms_router.py:202`
- `social-wiring` — `products/social-wiring/backend/app/routers/whatsapp_connections_router.py:1036`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/messaging.py:161`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/whatsapp_therapy.py:32`
- `therapy-platform` — `products/therapy-platform/backend/app/services/messaging_service.py:179`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:159`

### `send_via_waha` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:345`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:42`

### `stripe_webhook` (async def)

- `adconnect` — `products/adconnect/backend/app/routers/financial.py:272`
- `core` — `products/core/backend/app/routers/billing.py:92`

### `sync_campaigns` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/meta_api_service.py:81`
- `orbity` — `products/orbity/backend/app/routers/meta_ads_router.py:379`

### `update_task` (async def)

- `academia-de-reciclagem` — `products/academia-de-reciclagem/backend/app/routers/roadmap_router.py:173`
- `orbity` — `products/orbity/backend/app/routers/tasks_router.py:133`

