# NoctusAI Shared Library Catalog

> **Auto-generated** by `python mcp/noctusai/cli.py --catalog`. Do not edit by hand.
> This artifact replaces the drift-prone handwritten catalog. It answers:
> *what's in the lib, who uses it, and what's duplicated across products that probably shouldn't be.*

- **Lib roots scanned**: `noctusai_lib` (seed/lib/backend/noctusai_lib), `noctusai_seed` (seed/framework/backend/noctusai_seed)
- **Products scanned**: `adconnect`, `core`, `daily-life`, `dev-team`, `erp-imobiliario`, `personal-finance`, `seed`, `social-wiring`, `therapy-platform`
- **Totals**: 559 symbols · 139 orphans · 308 single-consumer · 45 duplicate candidates

## Symbols

### `noctusai_lib`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_calendar_adapter` | def | `(resolver: CalendarCredentialResolver | None=None, *, tenant…` | Return a calendar adapter wired for the supplied resolver, or | — | 0 |
| `get_media_resolver` | def | `(*, real: bool=False, document_prompt: str | None=None, scen…` | Return a media resolver. | — | 0 |
| `get_meta_adapter` | def | `(*, system_user_token: str | None=None, resolver: MetaCreden…` | Return a Meta adapter wired per the auth-resolution priority. | — | 0 |
| `get_meta_cloud_client` | def | `(*, phone_number_id: str | None=None, api_key: str | None=No…` | Return a real `MetaCloudClient` when `api_key` is set; `FakeMetaCloudClient` oth… | — | 0 |
| `get_routing_adapter` | def | `(api_key: str | None=None) -> RoutingAdapter` | Routes API → Static fallback. Returns `GoogleMapsRoutingAdapter` | — | 0 |
| `get_whatsapp_client` | def | `(*, base_url: str | None=None, api_key: str | None=None, ses…` | Return a real WAHA client when `base_url` is set; `FakeWahaClient` otherwise. | — | 0 |
| `make_credential_store` | def | `(*, client=None, fernet_key: Optional[bytes]=None, table: st…` | Real when ``client`` AND ``fernet_key`` are set; else Fake. | — | 0 |

### `noctusai_lib.api.app_factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_app` | def | `(app: FastAPI, settings, *, limiter=None, cors_allow_headers…` | Apply shared configuration to a FastAPI app instance. | lib:noctusai_seed | 1 |

### `noctusai_lib.api.auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SSOSessionCache` | class | `` | Thread-safe in-memory SSO session cache with TTL + per-key locking. | core | 1 |
| `create_sso_token_factory` | def | `(settings) -> Callable[..., str]` | Return a `create_sso_token` callable bound to `settings`. | core | 1 |
| `first_or_none` | def | `(result) -> Optional[dict]` | Extract first record from a Supabase list response, or None. | adconnect, daily-life, erp-imobiliario, personal-finance, seed, social-wiring, therapy-platform | 13 |
| `get_sso_context` | def | `(user) -> dict` | Extract all SSO-synced context from user_metadata. | — | 0 |
| `make_get_current_user` | def | `(get_supabase_client_fn)` | Factory that creates a product-specific get_current_user dependency. | adconnect, daily-life, erp-imobiliario, personal-finance, seed, social-wiring | 6 |
| `make_get_current_user_org` | def | `(get_current_user_fn, get_org_id_fn, *, required: bool=True,…` | Factory that creates a product-specific ``get_current_user_org`` dependency. | adconnect, daily-life, erp-imobiliario, personal-finance, seed, social-wiring | 6 |
| `make_require_role` | def | `(get_current_user_fn, get_user_role_fn)` | Factory that creates a product-specific ``require_role`` dependency factory. | adconnect, erp-imobiliario, therapy-platform | 3 |
| `require_credential_or_422` | def | `(key: str, org_id: Optional[str]=None, *, detail: Optional[s…` | Resolve a credential through `noctusai_lib.config.credentials.resolve_credential… | erp-imobiliario | 2 |
| `resolve_sso_role` | def | `(user) -> Optional[str]` | Check SSO metadata for product-level admin access. | adconnect, daily-life, erp-imobiliario, lib:noctusai_seed, personal-finance, seed, social-wiring, therapy-platform | 8 |
| `verify_sso_token_factory` | def | `(settings) -> Callable[[str], dict]` | Return a `verify_sso_token(token) -> payload` callable bound to `settings`. | core | 1 |

### `noctusai_lib.api.crud_safety`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `delete_or_404` | def | `(db, table: str, *predicates: tuple[str, Any], message: str=…` | HTTPException-flavored convenience wrapper around `delete_with_existence_check`. | core, daily-life, erp-imobiliario, personal-finance, social-wiring | 24 |
| `delete_with_existence_check` | def | `(db, table: str, *predicates: tuple[str, Any], not_found_exc…` | Pre-check existence via SELECT; raise if absent; DELETE on success. | erp-imobiliario | 4 |

### `noctusai_lib.api.middleware`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CorrelationIdMiddleware` | class | `` | Middleware that generates or extracts correlation IDs for request tracking. | lib:noctusai_lib | 1 |
| `DEFAULT_MAX_BODY_BYTES` | const | `` |  | lib:noctusai_lib | 1 |
| `MaxBodySizeMiddleware` | class | `` | Reject requests whose body exceeds `max_bytes` with 413 before any | lib:noctusai_lib | 1 |
| `RequestLoggingMiddleware` | class | `` | Middleware that logs request/response details with timing. | lib:noctusai_lib | 1 |

### `noctusai_lib.api.product_urls`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `resolve_product_url` | def | `(slug: str, *, db_url_base: str | None=None) -> str` | Return the deploy-aware URL for a product, given its slug. | core | 2 |

### `noctusai_lib.api.rate_limit`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `create_limiter` | def | `(redis_url: Optional[str]=None, default_limits: Optional[lis…` | Create a slowapi Limiter with optional Redis backing. | lib:noctusai_seed | 1 |

### `noctusai_lib.api.scheduler`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `register` | def | `(name: str, fn: Callable[..., Awaitable[None]], *, hours: Op…` | Register an async job on the module-level scheduler. | — | 0 |
| `reset_for_testing` | def | `() -> None` | Clear all registered jobs + replace the singleton — TEST USE ONLY. | — | 0 |
| `start_scheduler` | def | `() -> None` | Start the module-level scheduler. Idempotent — re-calling on a | — | 0 |
| `stop_scheduler` | def | `() -> None` | Shut down the scheduler gracefully. | — | 0 |

### `noctusai_lib.api.schemas`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StrictHttpModel` | class | `` | Pydantic base for HTTP-boundary schemas. Rejects unknown keys (422). | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_lib, personal-finance, social-wiring, therapy-platform | 119 |

### `noctusai_lib.config.cors_registry`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductEntry` | class | `` | Parsed row from ``start.sh PRODUCTS``. | — | 0 |
| `derive_cors_origins` | def | `(start_sh: Optional[Path]=None, include_localhost_alts: bool…` | Return the canonical CORS origins list derivable from ``start.sh``. | lib:noctusai_lib | 1 |
| `parse_products_registry` | def | `(start_sh: Optional[Path]=None) -> List[ProductEntry]` | Parse the ``PRODUCTS=(...)`` array out of ``start.sh``. | — | 0 |

### `noctusai_lib.config.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `configure_credentials` | def | `(*, supabase_url: str, supabase_anon_key: str, supabase_serv…` | Configure credential resolution. Call once at product startup. | lib:noctusai_seed | 1 |
| `resolve_credential` | def | `(key: str, org_id: Optional[str]=None) -> Optional[str]` | Resolve a credential value through the 3-tier chain. | erp-imobiliario, lib:noctusai_lib, lib:noctusai_seed, personal-finance | 11 |

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
| `AuditRecord` | class | `` | In-memory representation of one tool-call event. | core, daily-life, erp-imobiliario, personal-finance, social-wiring, therapy-platform | 17 |
| `apply_feature_redaction` | def | `(record: AuditRecord, *, redact_arguments: Optional[Callable…` | Return a new `AuditRecord` with arguments/result run through | social-wiring | 2 |
| `make_audit_writer` | def | `(db: 'Session', table_class: type) -> AuditWriter` | Build an audit writer closure bound to a session + ORM class. | core, daily-life, erp-imobiliario, personal-finance, social-wiring, therapy-platform | 11 |
| `now_utc` | def | `() -> datetime` | Convenience: timezone-aware UTC `datetime.now()`. Use as default for | core, daily-life, erp-imobiliario, personal-finance, social-wiring, therapy-platform | 14 |

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
| `Job` | class | `` | Background job — payload + lifecycle state. | lib:noctusai_lib | 3 |
| `JobStatus` | class | `` | Lifecycle states for a Job. | lib:noctusai_lib | 2 |
| `next_status` | def | `(job: Job, outcome: JobOutcome) -> JobStatus` | Compute the next status for a RUNNING job given the worker outcome. | lib:noctusai_lib | 2 |
| `should_retry` | def | `(job: Job) -> bool` | True iff the job has retries remaining. | lib:noctusai_lib | 1 |
| `with_status_transition` | def | `(job: Job, new_status: JobStatus, *, error: str | None=None,…` | Return a new Job with `status = new_status` and `updated_at` bumped. | lib:noctusai_lib | 2 |

### `noctusai_lib.domain.jobs.repo`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DeadLetterError` | class | `` | Raised by handlers that want to skip retries and land directly | lib:noctusai_lib | 2 |
| `FakeJobRepository` | class | `` | In-memory `JobRepository` for dev + tests. | lib:noctusai_lib | 1 |
| `JobRepository` | class | `` | Async repository surface every Job consumer depends on. | lib:noctusai_lib | 2 |
| `RealSupabaseJobRepository` | class | `` | Supabase-client backed `JobRepository`. | lib:noctusai_lib | 1 |
| `make_job_repository` | def | `(*, use_fake: bool=False, supabase_client: Any | None=None, …` | Construct a `JobRepository` for a consumer. | lib:noctusai_lib | 1 |

### `noctusai_lib.domain.jobs.retry_policy`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RetryPolicy` | class | `` | Exponential-backoff retry configuration. | lib:noctusai_lib, social-wiring | 3 |
| `next_retry_at` | def | `(retry_count: int, policy: RetryPolicy, now: datetime) -> da…` | Compute when the next retry should fire. | lib:noctusai_lib, social-wiring | 2 |

### `noctusai_lib.domain.jobs.worker`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Worker` | class | `` | Async polling worker that drains a `JobRepository`. | lib:noctusai_lib | 1 |

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
| `ensure_personal_org` | async def | `(db: Any, user_id: str, *, email: str, nome: Optional[str]=N…` | Return the user's org_id; create a personal org if they don't have one. | personal-finance | 1 |

### `noctusai_lib.domain.page_status`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_visible_pages` | def | `(db, user_org_role: str | None=None) -> list[str]` | Return list of visible page route names for the given user role. | — | 0 |

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

### `noctusai_lib.integrations.database`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_supabase_client` | def | `(url: str, anon_key: str, service_role_key: str, schema: Opt…` | Create a Supabase client with the given configuration. | lib:noctusai_lib, lib:noctusai_seed | 2 |

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

### `noctusai_lib.integrations.google_calendar.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CalendarCredentialResolver` | class | `` | Product-injected per-tenant credential lookup. | lib:noctusai_lib | 3 |
| `OAuthCalendarCredentials` | class | `` | OAuth user-delegated credentials. `refresh_token` MUST be | lib:noctusai_lib, therapy-platform | 4 |
| `ServiceAccountCalendarCredentials` | class | `` | Service-account credentials. `info` is the JSON keyfile dict | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.google_calendar.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeCalendarAdapter` | class | `` | In-memory fake. Use it for local development and tests until | lib:noctusai_lib, therapy-platform | 4 |

### `noctusai_lib.integrations.google_calendar.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `event_to_google_body` | def | `(event: EventInput) -> dict[str, Any]` |  | lib:noctusai_lib | 4 |
| `google_body_to_created_event` | def | `(body: dict[str, Any]) -> CreatedEvent` |  | lib:noctusai_lib | 4 |
| `parse_google_datetime` | def | `(value: str) -> datetime` |  | lib:noctusai_lib, therapy-platform | 3 |

### `noctusai_lib.integrations.google_calendar.oauth_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoogleCalendarOAuthAdapter` | class | `` | OAuth user-delegated Google Calendar adapter. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_calendar.service_account_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoogleCalendarServiceAccountAdapter` | class | `` | Service-account-backed Google Calendar adapter. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_calendar.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CalendarAdapter` | class | `` | Calendar adapter contract. Concrete implementations: | lib:noctusai_lib, therapy-platform | 3 |
| `CreatedEvent` | class | `` |  | lib:noctusai_lib | 5 |
| `EventAttendee` | class | `` |  | lib:noctusai_lib, therapy-platform | 2 |
| `EventInput` | class | `` | Calendar event payload. | lib:noctusai_lib, therapy-platform | 7 |

### `noctusai_lib.integrations.google_drive.content_stats`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `compute_content_stats` | def | `(text: str, *, rendered_as: str) -> dict` | Compute deterministic aggregates over text content. | lib:noctusai_lib | 1 |

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
| `FakeDriveReader` | class | `` | Deterministic in-memory `DriveReader`. | lib:noctusai_lib | 2 |

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
| `make_drive_reader` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Build a `DriveReader`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.reader_types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DriveFileContent` | class | `` | The content of a Drive file as exported/streamed bytes. | lib:noctusai_lib | 3 |
| `DriveReader` | class | `` | Drive v3 read/inspection contract. | lib:noctusai_lib | 2 |
| `DriveSearchHit` | class | `` | One result row from a Drive search / list call. | lib:noctusai_lib | 3 |
| `DriveSearchResult` | class | `` |  | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.google_drive.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealDriveDownloader` | class | `` | googleapiclient-backed `DriveDownloader`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.real_reader`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealDriveReader` | class | `` | googleapiclient-backed `DriveReader`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_drive.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DriveFile` | class | `` | A Google Drive file's metadata projection. | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.google_maps.google_maps_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GoogleMapsRoutingAdapter` | class | `` | Google Maps Routes API adapter (v2:computeRoutes). | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_maps.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_routes_request` | def | `(origin: Coordinates, destination: Coordinates) -> dict[str,…` |  | lib:noctusai_lib | 2 |
| `parse_routes_response` | def | `(response: dict[str, Any]) -> TravelEstimate` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.google_maps.static_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StaticRoutingAdapter` | class | `` | Returns `default_minutes` for any pair of distinct coordinates, | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_maps.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Coordinates` | class | `` |  | lib:noctusai_lib | 4 |
| `RoutingAdapter` | class | `` | Travel-estimate contract between two coordinates. Implementations | lib:noctusai_lib | 1 |
| `TravelEstimate` | class | `` |  | lib:noctusai_lib | 4 |

### `noctusai_lib.integrations.google_scopes`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GOOGLE_TOKENINFO_URL` | const | `` |  | — | 0 |
| `diagnose_consent_screen_gaps` | def | `(requested: list[str], granted: list[str]) -> dict` | Set-diff requested vs granted → operator-facing coverage report. | lib:noctusai_lib | 1 |
| `discover_granted_scopes` | def | `(access_token: str, *, http_client: httpx.Client | None=None…` | Probe Google's `oauth2/v3/tokeninfo` for the *actually-granted* | lib:noctusai_lib | 1 |
| `format_scopes_for_authorize` | def | `(scopes: list[str]) -> str` | Join scopes with single spaces — Google's authorize-endpoint | — | 0 |
| `resolve_google_scopes` | def | `(configured: str | None, *, kitchen_sink: list[str] | None=N…` | Resolve the configured scope env value to a concrete scope list. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.google_scopes_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `google_scopes_router` | def | `(*, configured_scopes: ConfiguredScopesProvider, access_toke…` | Build the `/api/google/scopes` introspection router. | — | 0 |

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

### `noctusai_lib.integrations.llm.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LLMAPIError` | class | `` | Downstream error from an LLM provider's API (rate-limit, timeout, etc.). | erp-imobiliario, lib:noctusai_lib | 4 |
| `LLMBudgetExceeded` | class | `` | The org's monthly LLM budget has been exhausted. | lib:noctusai_lib | 1 |
| `LLMNotConfigured` | class | `` | The resolved API key for the requested provider is empty/missing. | daily-life, erp-imobiliario, lib:noctusai_lib, social-wiring | 7 |
| `ProviderNotImplemented` | class | `` | A stub provider's method was called outside UI-development mode. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.llm.inputs`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `audio_bytes_to_named_buffer` | def | `(audio_bytes: bytes, filename: str) -> BytesIO` | Wrap audio bytes in a `BytesIO` with a `name` attribute, satisfying | — | 0 |
| `image_bytes_to_data_url` | def | `(image_bytes: bytes, mimetype: str) -> str` | Build a `data:` URL for OpenAI vision-input image payloads. | — | 0 |

### `noctusai_lib.integrations.llm.models`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ModelEntry` | class | `` | One row of the catalog. Immutable so it's safely shareable. | — | 0 |
| `all_providers` | def | `() -> list[str]` | All distinct provider names present in the catalog (sorted). | core | 1 |
| `is_stub_model` | def | `(provider: str, model_id: str) -> bool` | True if the given (provider, model_id) pair is served by a stub. | — | 0 |
| `models_for` | def | `(provider: str, kind: Optional[ModelKind]=None) -> list[Mode…` | Return the catalog entries for a provider, optionally filtered by kind. | core, lib:noctusai_lib | 2 |

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
| `estimate_cost_usd` | def | `(*, provider: str, model: str, prompt_tokens: Optional[int],…` | Compute a rough cost estimate from the model catalog. | — | 0 |
| `record_usage` | async def | `(*, provider: str, model: str, operation: str, prompt_tokens…` | Provider-side convenience — builds a `UsageEvent` and dispatches to | lib:noctusai_lib | 13 |

### `noctusai_lib.integrations.llm.vision`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `analyze_image` | async def | `(image: Union[bytes, str], prompt: str, *, model: Optional[s…` | Analyze an image against a text prompt via the configured provider. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.media.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeMediaResolver` | class | `` | In-memory `MediaResolver`. Records every resolved blob; serves a | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.media.real_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OpenAIMediaResolver` | class | `` | Real media resolver. Composes seed LLM entry points + ffmpeg + | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.media.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InboundMedia` | class | `` | An inbound media blob to resolve. | lib:noctusai_lib | 3 |
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
| `META_KITCHEN_SINK_SCOPES` | const | `` |  | lib:noctusai_lib | 2 |
| `MetaGraphError` | class | `` | Typed wrapper around a Graph error envelope. | lib:noctusai_lib | 3 |
| `app_access_token` | def | `(app_id: str, app_secret: str) -> str` | The App Access Token is literally `{app_id}|{app_secret}` — no | — | 0 |
| `discover_app_permissions` | def | `(*, app_id: str, app_secret: str, version: str=DEFAULT_GRAPH…` | Query `GET /{app-id}/permissions` with the App Access Token to | lib:noctusai_lib | 1 |
| `exchange_code_for_token` | def | `(*, code: str, app_id: str, app_secret: str, redirect_uri: s…` | Step 2 of the token chain: authorization `code` → short-lived | lib:noctusai_lib | 1 |
| `exchange_for_long_lived` | def | `(*, short_token: str, app_id: str, app_secret: str, version:…` | Step 3 of the token chain: short-lived → long-lived (~60d) user | lib:noctusai_lib | 1 |
| `graph_get` | def | `(path: str, *, access_token: str, params: dict[str, Any] | N…` | GET `{GRAPH_BASE}/{version}/{path}` with the token appended. | — | 0 |
| `graph_paged` | def | `(path: str, *, access_token: str, params: dict[str, Any] | N…` | Follow `paging.next` and accumulate `data` rows, up to | — | 0 |
| `resolve_oauth_scopes` | def | `(*, configured: str | None, app_id: str | None=None, app_sec…` | Resolve the OAuth scope request set. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.meta.credentials`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MetaCredentialResolver` | class | `` | Product-injected per-tenant Meta OAuth credential lookup. | lib:noctusai_lib | 2 |
| `OAuthMetaCredentials` | class | `` | A stored long-lived Meta user access token for one tenant. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.meta.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeMetaAdapter` | class | `` | In-memory `MetaAdapter`. Default when no creds are configured. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.meta.mappers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `IG_ACCOUNT_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_MEDIA_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `IG_MEDIA_INSIGHT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `ME_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `PAGE_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `PAGE_IG_FIELD` | const | `` |  | lib:noctusai_lib | 1 |
| `POST_FIELDS` | const | `` |  | lib:noctusai_lib | 1 |
| `POST_INSIGHT_METRICS` | const | `` |  | lib:noctusai_lib | 1 |
| `ig_account_from_body` | def | `(body: dict[str, Any], *, page_id: str | None=None) -> Insta…` |  | lib:noctusai_lib | 2 |
| `ig_media_from_body` | def | `(body: dict[str, Any]) -> InstagramMedia` |  | lib:noctusai_lib | 2 |
| `insights_from_body` | def | `(object_id: str, body: dict[str, Any]) -> PostInsights` | Map `/{id}/insights` `{"data": [{name, period, values}]}`. | lib:noctusai_lib | 2 |
| `page_from_body` | def | `(body: dict[str, Any]) -> FacebookPage` |  | lib:noctusai_lib | 2 |
| `parse_graph_datetime` | def | `(value: str | None) -> datetime | None` | Parse Graph's timestamp formats into an aware ``datetime``. | lib:noctusai_lib | 1 |
| `post_from_body` | def | `(body: dict[str, Any]) -> FacebookPost` |  | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.meta.oauth_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MetaOAuthAdapter` | class | `` | Live Meta Graph adapter satisfying `MetaAdapter`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.meta.router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_meta_router` | def | `(*, get_adapter: Callable[[str | None], MetaAdapter], app_id…` | Build the Meta introspection router. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.meta.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FacebookPage` | class | `` | A Facebook Page the authenticated identity manages. | lib:noctusai_lib | 4 |
| `FacebookPost` | class | `` | A post authored by a Page. | lib:noctusai_lib | 4 |
| `InstagramAccount` | class | `` | An Instagram Business/Creator account linked to a Page via the | lib:noctusai_lib | 4 |
| `InstagramMedia` | class | `` | An Instagram media item (image, video, or carousel album). | lib:noctusai_lib | 4 |
| `MetaAdapter` | class | `` | Meta Graph read-only adapter contract. Concrete implementations: | lib:noctusai_lib | 2 |
| `MetaConnectionStatus` | class | `` | Adapter introspection surface for `/api/meta/status`. | lib:noctusai_lib | 3 |
| `PostInsights` | class | `` | Flattened per-post / per-media insight metrics. | lib:noctusai_lib | 4 |

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
| `QuotaTracker` | class | `` | Pluggable quota / rate-limit tracker. | lib:noctusai_lib | 4 |

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

### `noctusai_lib.integrations.redis`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_fake_redis_client` | def | `(**kwargs: Any) -> 'Redis'` | In-memory Redis-compatible client for tests + dev (no network). | lib:noctusai_lib, social-wiring | 2 |
| `make_redis_client` | def | `(redis_url: str, **kwargs: Any) -> 'Redis'` | Construct a sync `redis.Redis` from a URL. | social-wiring | 1 |

### `noctusai_lib.integrations.storage.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_storage_backend` | def | `(*, kind: Literal['fake', 'local', 'supabase'], root_dir: Pa…` | Build a `StorageBackend`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.storage.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeStorageBackend` | class | `` | Deterministic in-memory `StorageBackend` implementation. | adconnect, lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.storage.local`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `LocalFilesystemStorageBackend` | class | `` | Filesystem-backed `StorageBackend`. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.storage.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `StorageBackend` | class | `` | Blob storage contract — Supabase Storage shape, abstracted. | adconnect, lib:noctusai_lib | 3 |

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

### `noctusai_lib.integrations.vista.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_PAGE_SIZE` | const | `` |  | lib:noctusai_lib | 1 |
| `DEFAULT_TIMEOUT_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `PAGINATION_KEYS` | const | `` |  | — | 0 |
| `VistaCallResult` | class | `` | Lightweight tuple-like carrier for a successful request. | lib:noctusai_lib | 1 |
| `VistaClient` | class | `` | Async HTTP client for the Vista REST API. | lib:noctusai_lib | 1 |
| `VistaConfigError` | class | `` | Vista base URL or API key is missing/empty. | lib:noctusai_lib | 1 |
| `VistaError` | class | `` | Base class for any Vista adapter failure. | lib:noctusai_lib | 1 |
| `VistaFieldNotAvailable` | class | `` | Vista refused a field — `400 "Campo X não está disponível"`. | — | 0 |
| `VistaNotFound` | class | `` | Endpoint not exposed on this tenant (HTTP 404). | — | 0 |
| `VistaPermissionDenied` | class | `` | Endpoint exists but the API key has no permission (HTTP 401). | — | 0 |
| `VistaTimeout` | class | `` | `httpx.TimeoutException` wrapper. | — | 0 |
| `VistaUpstreamError` | class | `` | Generic upstream non-2xx wrapper. | — | 0 |
| `extract_items` | def | `(payload: dict) -> tuple[list[dict], dict]` | Split Vista's dict-keyed-by-id response into (items, pagination). | — | 0 |

### `noctusai_lib.integrations.vista.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_vista_client` | def | `(*, use_fake: bool=False, base_url: Optional[str]=None, api_…` | Build a Vista client. | — | 0 |

### `noctusai_lib.integrations.vista.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeVistaClient` | class | `` | Deterministic in-memory `VistaClient` stand-in. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.vista.normalizers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `vista_agencia_to_showcase` | def | `(payload: dict) -> ShowcaseAgencia` |  | — | 0 |
| `vista_imovel_detalhes_to_showcase` | def | `(detalhes_payload: dict, *, listing_payload: Optional[dict]=…` | Compose detail view from /imoveis/detalhes + (optionally) the matching | — | 0 |
| `vista_imovel_to_showcase` | def | `(payload: dict) -> ShowcaseImovel` |  | — | 0 |
| `vista_usuario_to_showcase` | def | `(payload: dict) -> ShowcaseUsuario` |  | — | 0 |

### `noctusai_lib.integrations.vista.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ShowcaseAgencia` | class | `` |  | lib:noctusai_lib | 1 |
| `ShowcaseImovel` | class | `` |  | lib:noctusai_lib | 1 |
| `ShowcaseImovelDetalhes` | class | `` |  | lib:noctusai_lib | 1 |
| `ShowcaseUsuario` | class | `` |  | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.client`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `WahaClient` | class | `` | WAHA HTTP client with both sync and async send paths. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.dedup`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryWebhookDedup` | class | `` | Deterministic in-process dedup (no network). | lib:noctusai_lib | 2 |
| `RedisWebhookDedup` | class | `` | Redis SETNX-backed first-seen check. | lib:noctusai_lib | 1 |
| `SetnxRedis` | class | `` | The minimal Redis surface the SETNX pre-filter needs. | lib:noctusai_lib | 1 |
| `WebhookDedup` | class | `` | First-seen check for a webhook ``provider_message_id``. | lib:noctusai_lib | 2 |
| `get_webhook_dedup` | def | `(*, redis_client: SetnxRedis | None=None, key_prefix: str=_D…` | Return `RedisWebhookDedup` when a Redis client is supplied; | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.fake_adapter`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeWahaClient` | class | `` | In-memory WAHA stand-in. Records sent messages, serves | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.whatsapp.lid_auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `InMemoryLidPhoneCache` | class | `` | Deterministic in-memory LID↔phone cache (no network). | lib:noctusai_lib | 1 |
| `LidPhoneCache` | class | `` | Bidirectional LID↔phone binding store. | lib:noctusai_lib | 1 |
| `RedisLidPhoneCache` | class | `` | Redis-backed LID↔phone cache. | lib:noctusai_lib | 1 |
| `extract_resolved_remote` | def | `(send_response: dict) -> str | None` | Pull the resolved remote JID from a WAHA send-text response. | lib:noctusai_lib | 1 |
| `get_lid_phone_cache` | def | `(*, redis_client: 'Redis | None'=None, key_prefix: str=_DEFA…` | Return `RedisLidPhoneCache` when a Redis client is supplied; | lib:noctusai_lib | 1 |
| `is_authorized` | def | `(chat_id: str, *, phone_whitelist: Iterable[str], raw_lid_wh…` | 3-tier whitelist authorization for an inbound WhatsApp chat_id. | lib:noctusai_lib | 1 |
| `is_lid` | def | `(chat_id: str) -> bool` | True when ``chat_id`` is a WhatsApp linked-identity address. | lib:noctusai_lib | 1 |
| `is_phone_jid` | def | `(chat_id: str) -> bool` | True when ``chat_id`` is a phone-bearing JID (``@c.us`` / ``@s.whatsapp.net``). | lib:noctusai_lib | 1 |
| `normalize_phone` | def | `(value: str) -> str` | Reduce a phone / JID local-part to bare digits (no ``+``, no suffix). | lib:noctusai_lib | 1 |
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
| `WhatsAppClient` | class | `` | Send / download surface every WhatsApp connector implements. | lib:noctusai_lib | 1 |
| `WhatsAppIgnoredEvent` | class | `` | Inbound payload is structurally valid but the event type / source | lib:noctusai_lib | 3 |
| `WhatsAppInboundMessage` | class | `` | Parsed WhatsApp inbound message (provider-agnostic shape). | lib:noctusai_lib | 4 |
| `WhatsAppMedia` | class | `` | Media attachment on an inbound WhatsApp message. | lib:noctusai_lib | 2 |
| `WhatsAppPayloadError` | class | `` | Inbound payload failed validation (missing chat_id / no text or media). | lib:noctusai_lib | 3 |

### `noctusai_lib.integrations.youtube.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_youtube_client` | def | `(*, use_fake: bool=False, api_key: str | None=None, oauth_cr…` | Build a `YoutubeClient`. | lib:noctusai_lib | 1 |

### `noctusai_lib.integrations.youtube.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeYoutubeClient` | class | `` | Deterministic in-memory `YoutubeClient` implementation. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.youtube.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `YoutubeClient` | class | `` | YouTube Data API v3 client contract. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.youtube.real`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `RealYoutubeClient` | class | `` | Real YouTube Data API v3 client. | lib:noctusai_lib | 2 |

### `noctusai_lib.integrations.youtube.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `Channel` | class | `` | YouTube channel (the "owner" of uploaded videos). | lib:noctusai_lib | 4 |
| `DESCRIPTION_MAX_LEN` | const | `` |  | lib:noctusai_lib | 1 |
| `ListResult` | class | `` | Paginated list response. | lib:noctusai_lib | 4 |
| `Playlist` | class | `` | YouTube playlist — minimal projection (id + title). | lib:noctusai_lib | 2 |
| `TITLE_MAX_LEN` | const | `` |  | lib:noctusai_lib | 3 |
| `UPLOAD_QUOTA_UNITS` | const | `` |  | lib:noctusai_lib | 3 |
| `Video` | class | `` | YouTube video — flattened projection of `videos.list`. | lib:noctusai_lib | 4 |
| `VideoUpload` | class | `` | Result of a `videos.insert` (resumable upload). | lib:noctusai_lib | 4 |

### `noctusai_lib.logging_config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `auto_configure_for_cli` | def | `(app_name: str='noctusai-cli', *, use_stderr: bool=False) ->…` | Configure logging for CLI / MCP-server entry-points. | — | 0 |
| `configure_logging` | def | `(debug: bool=True, json_logs: bool=False, app_name: str='noc…` | Configure application logging. | lib:noctusai_seed, personal-finance, therapy-platform | 3 |

### `noctusai_lib.primitives._correlation`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `get_correlation_id` | def | `() -> str` | Return the current request's correlation ID (or `""` if unset). | lib:noctusai_lib | 2 |

### `noctusai_lib.primitives.exceptions`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AppException` | class | `` | Base application exception with standardized error response. | lib:noctusai_lib | 3 |
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

### `noctusai_lib.primitives.parsing`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `format_brl` | def | `(value: Optional[Union[float, int]], *, decimals: int=2, wit…` | Format a numeric value in Brazilian Real notation. | erp-imobiliario, personal-finance | 3 |
| `parse_iso_or_400` | def | `(value: Optional[str]) -> Optional[datetime]` | Parse an ISO-8601 datetime string, raising HTTP 400 on invalid input. | core, lib:noctusai_seed | 2 |
| `parse_iso_or_none` | def | `(value: Optional[str]) -> Optional[datetime]` | Same as `parse_iso_or_400` but returns `None` on invalid input. | — | 0 |
| `safe_float` | def | `(text: Any, default: float=0.0) -> float` | Extract a float from messy text; return `default` on failure. | erp-imobiliario, personal-finance | 2 |
| `safe_json_loads` | def | `(raw: str) -> Optional[Union[list, dict]]` | Parse JSON tolerating ` ```json ... ``` ` markdown fences. | daily-life, social-wiring | 2 |

### `noctusai_lib.primitives.responses`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `PaginatedResponse` | class | `` | Standardized paginated response. | — | 0 |
| `PaginationMeta` | class | `` | Pagination metadata. | — | 0 |
| `calculate_pagination` | def | `(page: int, page_size: int, max_page_size: int=200) -> tuple…` | Calculate pagination parameters with validation. | core | 1 |
| `deleted_response` | def | `(resource: str, resource_id: str) -> dict` | Create a standardized deletion response. | — | 0 |
| `ok_response` | def | `(message: str='Operação realizada com sucesso') -> dict` | Create a simple success acknowledgment response. | core, daily-life | 5 |
| `paginated_response` | def | `(data: list, total: int, page: int, page_size: int) -> dict` | Create a standardized paginated response. | core, daily-life, social-wiring | 7 |
| `success_response` | def | `(data: Any, total: Optional[int]=None) -> dict` | Create a standardized success response. | core, daily-life, dev-team, social-wiring | 19 |

### `noctusai_lib.primitives.roles`

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

### `noctusai_lib.primitives.tasks`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `NoRunningLoopError` | class | `` | Raised when `schedule_coro` is called outside a running event loop. | core | 1 |
| `schedule_coro` | def | `(coro: Coroutine[Any, Any, Any], *, logger: Optional[logging…` | Schedule `coro` on the running event loop, fire-and-forget. | core, erp-imobiliario, social-wiring | 4 |

### `noctusai_lib.primitives.timeutil`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `current_day_ref` | def | `() -> str` | Return the current UTC day reference, formatted ``YYYY-MM-DD``. | erp-imobiliario | 4 |
| `current_month_ref` | def | `() -> str` | Return the current UTC month reference, formatted ``YYYY-MM``. | erp-imobiliario | 5 |
| `frozen_time` | def | `(value: datetime) -> Iterator[None]` | Freeze wallclock to ``value`` for the duration of the with-block. | — | 0 |
| `now_utc` | def | `() -> datetime` | Return the current wallclock as an aware UTC `datetime`. | erp-imobiliario, lib:noctusai_lib, personal-finance | 7 |
| `now_utc_iso` | def | `() -> str` | Return the current wallclock as an ISO 8601 string with UTC offset. | adconnect, core | 4 |
| `today_utc` | def | `() -> date` | Return the current wallclock as a UTC `date` (no time, no tz). | erp-imobiliario | 4 |

### `noctusai_lib.security.encrypted_tokens`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MultiKeyDecryptor` | class | `` | Try a sequence of keys on decrypt, in order; first success wins. | lib:noctusai_lib | 1 |
| `decrypt` | def | `(ciphertext: str, key: bytes) -> str` | Decrypt `ciphertext` with `key`, returning the original plaintext. | lib:noctusai_lib | 2 |
| `encrypt` | def | `(plaintext: str, key: bytes) -> str` | Encrypt `plaintext` with `key`, returning url-safe-base64 ciphertext. | lib:noctusai_lib | 2 |
| `generate_key` | def | `() -> bytes` | Generate a fresh Fernet key. | lib:noctusai_lib | 1 |
| `rotate_key` | def | `(ciphertext: str, old_key: bytes, new_key: bytes) -> str` | Decrypt with `old_key` and re-encrypt with `new_key`. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.factory`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `make_oauth_provider` | def | `(name: str, *, use_fake: bool=False, client_id: str | None=N…` | Resolve a vendor name to a concrete `OAuthProvider` instance. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeOAuthProvider` | class | `` | Deterministic OAuth provider for tests + FakeMode. | lib:noctusai_lib | 2 |

### `noctusai_lib.security.oauth.google_provider`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `GOOGLE_AUTH_URL` | const | `` |  | — | 0 |
| `GOOGLE_REVOKE_URL` | const | `` |  | — | 0 |
| `GOOGLE_TOKEN_URL` | const | `` |  | — | 0 |
| `GoogleProvider` | class | `` | Google OAuth 2.0 provider. | lib:noctusai_lib | 2 |

### `noctusai_lib.security.oauth.protocol`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `OAuthProvider` | class | `` | The contract every OAuth provider satisfies. | lib:noctusai_lib | 3 |

### `noctusai_lib.security.oauth.router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `oauth_router` | def | `(*providers: OAuthProvider, on_callback: CallbackHook | None…` | Build an APIRouter exposing the OAuth dance for `providers`. | lib:noctusai_lib | 1 |

### `noctusai_lib.security.oauth.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthorizationURL` | class | `` | The URL to redirect the user to for provider consent. | lib:noctusai_lib | 4 |
| `OAuthCallbackResult` | class | `` | The outcome of an OAuth callback round-trip. | lib:noctusai_lib | 2 |
| `TokenSet` | class | `` | Tokens returned by an OAuth token-endpoint exchange. | lib:noctusai_lib | 4 |

### `noctusai_lib.security.token_store.fake`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `FakeCredentialStore` | class | `` | Process-memory credential store keyed by ``(org_id, provider)``. | lib:noctusai_lib | 2 |

### `noctusai_lib.security.token_store.supabase_store`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_TABLE` | const | `` |  | lib:noctusai_lib | 1 |
| `SupabaseCredentialStore` | class | `` | Encrypted-at-rest credential persistence over a Supabase client. | lib:noctusai_lib | 2 |

### `noctusai_lib.security.token_store.types`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `CredentialDecryptError` | class | `` | Raised when a stored row exists but cannot be decrypted. | lib:noctusai_lib | 3 |
| `CredentialStore` | class | `` | Per-(org, provider) encrypted credential persistence. | lib:noctusai_lib | 4 |
| `StoredCredential` | class | `` | A decrypted credential bundle for one ``(org_id, provider)`` pair. | lib:noctusai_lib | 4 |

### `noctusai_lib.security.webhook_signatures`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEFAULT_MAX_AGE_SECONDS` | const | `` |  | lib:noctusai_lib | 1 |
| `ResolvedSecret` | class | `` | Returned by a `SecretResolver`: the per-request secret plus optional context. | erp-imobiliario, lib:noctusai_lib, seed, social-wiring | 6 |
| `VerifiedWebhook` | class | `` | Yielded by `webhook_endpoint` after the dependency runs. | erp-imobiliario, lib:noctusai_lib, seed, social-wiring | 6 |
| `compute_hmac_sha256_hex` | def | `(body: bytes, secret: str) -> str` | Hex-encoded HMAC-SHA256 of `body` keyed with `secret`. | core, lib:noctusai_lib | 2 |
| `static_secret_resolver` | def | `(secret: Optional[str]) -> SecretResolver` | Resolver for the simple case where the secret is fixed at boot. | lib:noctusai_lib | 1 |
| `verify_hmac_sha256` | def | `(body: bytes, signature: str, secret: str, *, timestamp_valu…` | Verify a `sha256=<hex>`-style signature header. | lib:noctusai_lib | 1 |
| `verify_hmac_sha256_hex` | def | `(body: bytes, signature_hex: str, secret: str, *, timestamp_…` | Verify a bare-hex HMAC-SHA256 signature (no `sha256=` prefix). | lib:noctusai_lib | 2 |
| `verify_svix_signature` | def | `(*, svix_id: str, svix_timestamp: str, body: bytes, signatur…` | Verify a Svix-protocol webhook signature (Resend and similar). | lib:noctusai_lib | 1 |
| `webhook_endpoint` | def | `(*, secret_resolver: SecretResolver, scheme: WebhookScheme='…` | Build a FastAPI dependency that verifies an inbound webhook signature. | erp-imobiliario, lib:noctusai_lib, seed, social-wiring | 6 |

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
| `AuthClient` | class | `` | Wraps FastAPI TestClient with automatic Authorization header. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 12 |
| `MockUser` | class | `` | Simulates a Supabase auth user object. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 16 |
| `MockUserResponse` | class | `` | Wraps MockUser to simulate supabase.auth.get_user() response. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 15 |
| `bind_user_metadata` | def | `(mock_sb_or_client: Any, *, user: Optional[MockUser]=None, r…` | Re-bind ``mock_sb.auth.get_user`` to return a fresh ``MockUser``. | adconnect, lib:noctusai_lib | 2 |

### `noctusai_lib.testing.conftest_helpers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `purge_shadowing_editable_finders` | def | `(local_lib_root: Path, package_names: Iterable[str]=_DEFAULT…` | Drop meta-path finders whose mapping for a guarded package points outside *that … | lib:noctusai_lib | 1 |

### `noctusai_lib.testing.consent`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `bind_consent_module_to_mock` | def | `(mock_sb: Any) -> None` | Wire the consent module's FastAPI deps to a mock Supabase client. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 13 |

### `noctusai_lib.testing.fixtures`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `reset_rate_limiter` | def | `()` | Reset the slowapi limiter between tests. | core, daily-life, lib:noctusai_lib, therapy-platform | 4 |

### `noctusai_lib.testing.framework_test_suites`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `AuthBoundarySuite` | class | `` | Every protected framework endpoint must return 401 without auth. | adconnect, lib:noctusai_lib, seed | 3 |
| `FrameworkEndpointsSuite` | class | `` | All framework-provided endpoints must exist and respond. | adconnect, lib:noctusai_lib, seed | 3 |
| `HealthCheckSuite` | class | `` | GET /api/health — public endpoint provided by the seed framework. | adconnect, daily-life, lib:noctusai_lib, seed, social-wiring | 5 |
| `NotificationFlowSuite` | class | `` | Notification proxying through the framework's standard router. | adconnect, lib:noctusai_lib, seed | 3 |
| `TeamFlowSuite` | class | `` | Authenticated team-management flow through the framework router. | adconnect, daily-life, lib:noctusai_lib, seed | 4 |
| `TeamRouterInviteSuite` | class | `` | POST /api/team/invite — framework's team-invite endpoint. | adconnect, lib:noctusai_lib, seed, social-wiring | 4 |
| `TeamRouterListMembersSuite` | class | `` | GET /api/team — framework's team-list endpoint. | adconnect, lib:noctusai_lib, seed, social-wiring | 4 |
| `TeamRouterRemoveMemberSuite` | class | `` | DELETE /api/team/{user_id} — framework's team-remove endpoint. | adconnect, lib:noctusai_lib, seed, social-wiring | 4 |

### `noctusai_lib.testing.migration_parser`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `parse_files` | def | `(paths: Iterable[Path]) -> dict[str, set[str]]` | Parse multiple migration files in order, merging into one schema map. | lib:noctusai_lib | 1 |
| `parse_sql` | def | `(sql: str, *, source_label: str='<unknown>') -> dict[str, se…` | Parse a blob of SQL into a `{qualified_table: {columns}}` map. | — | 0 |

### `noctusai_lib.testing.mocks`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `MockFilterBuilder` | class | `` | Mirrors SyncFilterRequestBuilder. | adconnect, core, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 9 |
| `MockQueryBuilder` | class | `` | Mirrors SyncQueryRequestBuilder. | adconnect, core, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 9 |
| `MockRequestBuilder` | class | `` | Mirrors SyncRequestBuilder — the object returned by .table(name). | adconnect, core, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 9 |
| `MockSelectBuilder` | class | `` | Mirrors SyncSelectRequestBuilder. | adconnect, core, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 9 |
| `MockSupabaseClient` | class | `` | Mocked Supabase client with per-table data control and response queues. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 22 |
| `MockSupabaseResponse` | class | `` | Simulates a Supabase PostgREST response. | adconnect, core, daily-life, erp-imobiliario, lib:noctusai_lib, personal-finance, seed, social-wiring, therapy-platform | 21 |

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
| `create_product_app` | def | `(name: str, schema: str, settings, routers: Optional[list]=N…` | Create a fully configured FastAPI app for a NoctusAI product. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_seed, personal-finance, seed, social-wiring, therapy-platform | 12 |

### `noctusai_seed.config`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductSettings` | class | `` | Base settings that every product inherits. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_seed, personal-finance, seed, social-wiring, therapy-platform | 10 |

### `noctusai_seed.database`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DatabaseModule` | class | `` | Encapsulates database client factories for a product schema. | — | 0 |
| `create_database_module` | def | `(settings, schema: str) -> DatabaseModule` | Factory to create database module for a product. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_seed, personal-finance, seed, social-wiring, therapy-platform | 18 |

### `noctusai_seed.dependencies`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `ProductDependencies` | class | `` | Encapsulates standard FastAPI dependencies for a product. | — | 0 |
| `create_dependencies` | def | `(db) -> ProductDependencies` | Factory to create standard dependencies for a product. | adconnect, core, daily-life, dev-team, erp-imobiliario, lib:noctusai_seed, personal-finance, seed, social-wiring, therapy-platform | 11 |

### `noctusai_seed.dev_auth`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `DEV_TOKEN` | const | `` |  | — | 0 |
| `DEV_USER_EMAIL` | const | `` |  | — | 0 |
| `dev_auth_enabled` | def | `(settings) -> bool` | True only when the explicit dev-auth flag is on AND debug is on. | lib:noctusai_seed | 1 |
| `make_dev_auth_get_current_user` | def | `(settings, *, user_id: Optional[str]=None, org_id: Optional[…` | Factory → a ``get_current_user``-shaped dependency for dev mode. | lib:noctusai_seed | 1 |

### `noctusai_seed.health`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `HealthCheckHook` | class | `` | Async callable that reports whether one piece of infrastructure is healthy. | lib:noctusai_seed | 1 |
| `HealthEndpointConfig` | class | `` | Configuration for the seed-baked ``/_health`` + ``/_ready`` endpoints. | dev-team, lib:noctusai_seed, personal-finance | 4 |
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
| `create_product_limiter` | def | `(settings)` | Create a rate limiter using the product's settings. | adconnect, core, daily-life, dev-team, erp-imobiliario, personal-finance, seed, social-wiring, therapy-platform | 9 |

### `noctusai_seed.routers`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `build_standard_routers` | def | `(deps, settings, product_name: str, version: str, names: Seq…` | Return the subset of standard routers named by `names`. | lib:noctusai_seed | 1 |

### `noctusai_seed.scheduler_router`

| Symbol | Kind | Signature | Doc | Used by | Imports |
|---|---|---|---|---|---|
| `SchedulerJobDTO` | class | `` | Boundary DTO for an APScheduler job — leaks none of APScheduler's | — | 0 |
| `create_scheduler_router` | def | `(deps) -> APIRouter` | Build the `/api/scheduler` router for a product. | lib:noctusai_seed | 1 |

## Orphans

Symbols defined in the lib but with **zero importers** across all products.
Candidates for deletion — but confirm first (may be staged for imminent use,
or intentionally-public for future consumers).

| Symbol | Kind | Location |
|---|---|---|
| `noctusai_lib.get_calendar_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/google_calendar/__init__.py:51` |
| `noctusai_lib.get_media_resolver` | def | `seed/lib/backend/noctusai_lib/integrations/media/__init__.py:47` |
| `noctusai_lib.get_meta_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/meta/__init__.py:80` |
| `noctusai_lib.get_meta_cloud_client` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/__init__.py:135` |
| `noctusai_lib.get_routing_adapter` | def | `seed/lib/backend/noctusai_lib/integrations/google_maps/__init__.py:35` |
| `noctusai_lib.get_whatsapp_client` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/__init__.py:106` |
| `noctusai_lib.make_credential_store` | def | `seed/lib/backend/noctusai_lib/security/token_store/__init__.py:56` |
| `noctusai_lib.api.auth.get_sso_context` | def | `seed/lib/backend/noctusai_lib/api/auth.py:149` |
| `noctusai_lib.api.scheduler.register` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:90` |
| `noctusai_lib.api.scheduler.reset_for_testing` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:159` |
| `noctusai_lib.api.scheduler.start_scheduler` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:138` |
| `noctusai_lib.api.scheduler.stop_scheduler` | def | `seed/lib/backend/noctusai_lib/api/scheduler.py:152` |
| `noctusai_lib.config.cors_registry.ProductEntry` | class | `seed/lib/backend/noctusai_lib/config/cors_registry.py:64` |
| `noctusai_lib.config.cors_registry.parse_products_registry` | def | `seed/lib/backend/noctusai_lib/config/cors_registry.py:93` |
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
| `noctusai_lib.domain.invitations.expire_old_invitations` | def | `seed/lib/backend/noctusai_lib/domain/invitations.py:230` |
| `noctusai_lib.domain.notifications.map_notification_from_pt` | def | `seed/lib/backend/noctusai_lib/domain/notifications.py:26` |
| `noctusai_lib.domain.org.DEFAULT_NAME_TEMPLATE` | const | `seed/lib/backend/noctusai_lib/domain/org.py:23` |
| `noctusai_lib.domain.page_status.get_visible_pages` | def | `seed/lib/backend/noctusai_lib/domain/page_status.py:17` |
| `noctusai_lib.domain.sql_templates.rls_subquery_policy` | def | `seed/lib/backend/noctusai_lib/domain/sql_templates.py:144` |
| `noctusai_lib.integrations.email.digest.send_to_many` | async def | `seed/lib/backend/noctusai_lib/integrations/email/digest.py:353` |
| `noctusai_lib.integrations.email.digest.send_to_one` | async def | `seed/lib/backend/noctusai_lib/integrations/email/digest.py:321` |
| `noctusai_lib.integrations.email.templates.send_password_reset_email` | def | `seed/lib/backend/noctusai_lib/integrations/email/templates.py:136` |
| `noctusai_lib.integrations.google_scopes.GOOGLE_TOKENINFO_URL` | const | `seed/lib/backend/noctusai_lib/integrations/google_scopes.py:64` |
| `noctusai_lib.integrations.google_scopes.format_scopes_for_authorize` | def | `seed/lib/backend/noctusai_lib/integrations/google_scopes.py:127` |
| `noctusai_lib.integrations.google_scopes_router.google_scopes_router` | def | `seed/lib/backend/noctusai_lib/integrations/google_scopes_router.py:61` |
| `noctusai_lib.integrations.llm.audio.transcribe_audio` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/audio.py:16` |
| `noctusai_lib.integrations.llm.backends.redis_backend.RedisCacheBackend` | class | `seed/lib/backend/noctusai_lib/integrations/llm/backends/redis_backend.py:29` |
| `noctusai_lib.integrations.llm.budget.compute_spend_usd` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/budget.py:167` |
| `noctusai_lib.integrations.llm.budget.fetch_budget_brl` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/budget.py:130` |
| `noctusai_lib.integrations.llm.budget.is_configured` | def | `seed/lib/backend/noctusai_lib/integrations/llm/budget.py:84` |
| `noctusai_lib.integrations.llm.cache.CacheBackend` | class | `seed/lib/backend/noctusai_lib/integrations/llm/cache.py:39` |
| `noctusai_lib.integrations.llm.cache.InMemoryCacheBackend` | class | `seed/lib/backend/noctusai_lib/integrations/llm/cache.py:106` |
| `noctusai_lib.integrations.llm.chat.build_cached_messages` | def | `seed/lib/backend/noctusai_lib/integrations/llm/chat.py:181` |
| `noctusai_lib.integrations.llm.chat.chat_completion` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/chat.py:31` |
| `noctusai_lib.integrations.llm.chat.chat_completion_stream` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/chat.py:123` |
| `noctusai_lib.integrations.llm.embeddings.generate_embedding` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/embeddings.py:15` |
| `noctusai_lib.integrations.llm.inputs.audio_bytes_to_named_buffer` | def | `seed/lib/backend/noctusai_lib/integrations/llm/inputs.py:20` |
| `noctusai_lib.integrations.llm.inputs.image_bytes_to_data_url` | def | `seed/lib/backend/noctusai_lib/integrations/llm/inputs.py:14` |
| `noctusai_lib.integrations.llm.models.ModelEntry` | class | `seed/lib/backend/noctusai_lib/integrations/llm/models.py:26` |
| `noctusai_lib.integrations.llm.models.is_stub_model` | def | `seed/lib/backend/noctusai_lib/integrations/llm/models.py:190` |
| `noctusai_lib.integrations.llm.providers.anthropic_provider.AnthropicProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/anthropic_provider.py:60` |
| `noctusai_lib.integrations.llm.providers.fake_provider.FakeProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/fake_provider.py:30` |
| `noctusai_lib.integrations.llm.providers.gemini_provider.GeminiProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/gemini_provider.py:60` |
| `noctusai_lib.integrations.llm.providers.openai_provider.OpenAIProvider` | class | `seed/lib/backend/noctusai_lib/integrations/llm/providers/openai_provider.py:30` |
| `noctusai_lib.integrations.llm.refusal.analyze_image_with_refusal_retry` | async def | `seed/lib/backend/noctusai_lib/integrations/llm/refusal.py:114` |
| `noctusai_lib.integrations.llm.refusal.looks_like_refusal` | def | `seed/lib/backend/noctusai_lib/integrations/llm/refusal.py:76` |
| `noctusai_lib.integrations.llm.registry.list_providers` | def | `seed/lib/backend/noctusai_lib/integrations/llm/registry.py:42` |
| `noctusai_lib.integrations.llm.usage.InMemoryUsageSink` | class | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:60` |
| `noctusai_lib.integrations.llm.usage.UsageEvent` | class | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:28` |
| `noctusai_lib.integrations.llm.usage.UsageSink` | class | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:53` |
| `noctusai_lib.integrations.llm.usage.estimate_cost_usd` | def | `seed/lib/backend/noctusai_lib/integrations/llm/usage.py:151` |
| `noctusai_lib.integrations.meta._meta_api.DEFAULT_MAX_PAGES` | const | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:35` |
| `noctusai_lib.integrations.meta._meta_api.DEFAULT_TIMEOUT_SECONDS` | const | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:34` |
| `noctusai_lib.integrations.meta._meta_api.GRAPH_BASE` | const | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:33` |
| `noctusai_lib.integrations.meta._meta_api.app_access_token` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:259` |
| `noctusai_lib.integrations.meta._meta_api.graph_get` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:136` |
| `noctusai_lib.integrations.meta._meta_api.graph_paged` | def | `seed/lib/backend/noctusai_lib/integrations/meta/_meta_api.py:164` |
| `noctusai_lib.integrations.quota.redis_backend.MAX_RETRIES` | const | `seed/lib/backend/noctusai_lib/integrations/quota/redis_backend.py:52` |
| `noctusai_lib.integrations.supabase_identity.fetch_user_identity` | def | `seed/lib/backend/noctusai_lib/integrations/supabase_identity.py:105` |
| `noctusai_lib.integrations.vista.client.PAGINATION_KEYS` | const | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:26` |
| `noctusai_lib.integrations.vista.client.VistaFieldNotAvailable` | class | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:58` |
| `noctusai_lib.integrations.vista.client.VistaNotFound` | class | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:54` |
| `noctusai_lib.integrations.vista.client.VistaPermissionDenied` | class | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:50` |
| `noctusai_lib.integrations.vista.client.VistaTimeout` | class | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:66` |
| `noctusai_lib.integrations.vista.client.VistaUpstreamError` | class | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:40` |
| `noctusai_lib.integrations.vista.client.extract_items` | def | `seed/lib/backend/noctusai_lib/integrations/vista/client.py:348` |
| `noctusai_lib.integrations.vista.factory.make_vista_client` | def | `seed/lib/backend/noctusai_lib/integrations/vista/factory.py:24` |
| `noctusai_lib.integrations.vista.normalizers.vista_agencia_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:152` |
| `noctusai_lib.integrations.vista.normalizers.vista_imovel_detalhes_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:114` |
| `noctusai_lib.integrations.vista.normalizers.vista_imovel_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:80` |
| `noctusai_lib.integrations.vista.normalizers.vista_usuario_to_showcase` | def | `seed/lib/backend/noctusai_lib/integrations/vista/normalizers.py:141` |
| `noctusai_lib.integrations.whatsapp.mappers.extract_from_name` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:172` |
| `noctusai_lib.integrations.whatsapp.mappers.extract_media` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:153` |
| `noctusai_lib.integrations.whatsapp.mappers.extract_message_id` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:142` |
| `noctusai_lib.integrations.whatsapp.mappers.first_text` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:134` |
| `noctusai_lib.integrations.whatsapp.mappers.is_own_or_api_message` | def | `seed/lib/backend/noctusai_lib/integrations/whatsapp/mappers.py:166` |
| `noctusai_lib.logging_config.auto_configure_for_cli` | def | `seed/lib/backend/noctusai_lib/logging_config.py:182` |
| `noctusai_lib.primitives.exceptions.ConflictError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:92` |
| `noctusai_lib.primitives.exceptions.ForbiddenError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:81` |
| `noctusai_lib.primitives.exceptions.InternalError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:107` |
| `noctusai_lib.primitives.exceptions.NotFoundError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:40` |
| `noctusai_lib.primitives.exceptions.UnauthorizedError` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:70` |
| `noctusai_lib.primitives.exceptions.ValidationError_` | class | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:55` |
| `noctusai_lib.primitives.exceptions.format_error_response` | def | `seed/lib/backend/noctusai_lib/primitives/exceptions.py:122` |
| `noctusai_lib.primitives.parsing.parse_iso_or_none` | def | `seed/lib/backend/noctusai_lib/primitives/parsing.py:175` |
| `noctusai_lib.primitives.responses.PaginatedResponse` | class | `seed/lib/backend/noctusai_lib/primitives/responses.py:25` |
| `noctusai_lib.primitives.responses.PaginationMeta` | class | `seed/lib/backend/noctusai_lib/primitives/responses.py:17` |
| `noctusai_lib.primitives.responses.deleted_response` | def | `seed/lib/backend/noctusai_lib/primitives/responses.py:92` |
| `noctusai_lib.primitives.roles.ADMIN_ROLES` | const | `seed/lib/backend/noctusai_lib/primitives/roles.py:13` |
| `noctusai_lib.primitives.roles.MANAGE_TEAM_ROLES` | const | `seed/lib/backend/noctusai_lib/primitives/roles.py:16` |
| `noctusai_lib.primitives.roles.ORG_ROLES` | const | `seed/lib/backend/noctusai_lib/primitives/roles.py:10` |
| `noctusai_lib.primitives.roles.PRODUCT_ADMIN_ROLES` | const | `seed/lib/backend/noctusai_lib/primitives/roles.py:23` |
| `noctusai_lib.primitives.roles.can_manage_billing` | def | `seed/lib/backend/noctusai_lib/primitives/roles.py:47` |
| `noctusai_lib.primitives.roles.can_manage_team` | def | `seed/lib/backend/noctusai_lib/primitives/roles.py:42` |
| `noctusai_lib.primitives.roles.is_dev_or_owner` | def | `seed/lib/backend/noctusai_lib/primitives/roles.py:37` |
| `noctusai_lib.primitives.timeutil.frozen_time` | def | `seed/lib/backend/noctusai_lib/primitives/timeutil.py:90` |
| `noctusai_lib.security.oauth.google_provider.GOOGLE_AUTH_URL` | const | `seed/lib/backend/noctusai_lib/security/oauth/google_provider.py:47` |
| `noctusai_lib.security.oauth.google_provider.GOOGLE_REVOKE_URL` | const | `seed/lib/backend/noctusai_lib/security/oauth/google_provider.py:49` |
| `noctusai_lib.security.oauth.google_provider.GOOGLE_TOKEN_URL` | const | `seed/lib/backend/noctusai_lib/security/oauth/google_provider.py:48` |
| `noctusai_lib.sql.prelude.prelude` | def | `seed/lib/backend/noctusai_lib/sql/prelude.py:34` |
| `noctusai_lib.sql.service_role_bypass.service_role_bypass` | def | `seed/lib/backend/noctusai_lib/sql/service_role_bypass.py:48` |
| `noctusai_lib.sql.triggers.updated_at_function` | def | `seed/lib/backend/noctusai_lib/sql/triggers.py:40` |
| `noctusai_lib.sql.triggers.updated_at_trigger` | def | `seed/lib/backend/noctusai_lib/sql/triggers.py:62` |
| `noctusai_lib.testing.migration_parser.parse_sql` | def | `seed/lib/backend/noctusai_lib/testing/migration_parser.py:281` |
| `noctusai_lib.testing.pytest_plugin.pytest_configure` | def | `seed/lib/backend/noctusai_lib/testing/pytest_plugin.py:38` |
| `noctusai_seed.ai_feedback_router.FeedbackBody` | class | `seed/framework/backend/noctusai_seed/ai_feedback_router.py:35` |
| `noctusai_seed.database.DatabaseModule` | class | `seed/framework/backend/noctusai_seed/database.py:25` |
| `noctusai_seed.dependencies.ProductDependencies` | class | `seed/framework/backend/noctusai_seed/dependencies.py:104` |
| `noctusai_seed.dev_auth.DEV_TOKEN` | const | `seed/framework/backend/noctusai_seed/dev_auth.py:58` |
| `noctusai_seed.dev_auth.DEV_USER_EMAIL` | const | `seed/framework/backend/noctusai_seed/dev_auth.py:57` |
| `noctusai_seed.llm_router.ModelInfo` | class | `seed/framework/backend/noctusai_seed/llm_router.py:45` |
| `noctusai_seed.llm_router.PreferencesBody` | class | `seed/framework/backend/noctusai_seed/llm_router.py:53` |
| `noctusai_seed.llm_router.ProviderInfo` | class | `seed/framework/backend/noctusai_seed/llm_router.py:39` |
| `noctusai_seed.scheduler_router.SchedulerJobDTO` | class | `seed/framework/backend/noctusai_seed/scheduler_router.py:50` |

## Single-consumer symbols

Lib symbols imported by exactly **one product**. Informational only —
a symbol may legitimately live in lib because it encodes a platform-wide
policy, even if currently only one product exercises it.

| Symbol | Used by | Imports |
|---|---|---|
| `noctusai_lib.api.app_factory.configure_app` | lib:noctusai_seed | 1 |
| `noctusai_lib.api.auth.SSOSessionCache` | core | 1 |
| `noctusai_lib.api.auth.create_sso_token_factory` | core | 1 |
| `noctusai_lib.api.auth.require_credential_or_422` | erp-imobiliario | 2 |
| `noctusai_lib.api.auth.verify_sso_token_factory` | core | 1 |
| `noctusai_lib.api.crud_safety.delete_with_existence_check` | erp-imobiliario | 4 |
| `noctusai_lib.api.middleware.CorrelationIdMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.middleware.DEFAULT_MAX_BODY_BYTES` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.middleware.MaxBodySizeMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.middleware.RequestLoggingMiddleware` | lib:noctusai_lib | 1 |
| `noctusai_lib.api.product_urls.resolve_product_url` | core | 2 |
| `noctusai_lib.api.rate_limit.create_limiter` | lib:noctusai_seed | 1 |
| `noctusai_lib.config.cors_registry.derive_cors_origins` | lib:noctusai_lib | 1 |
| `noctusai_lib.config.credentials.configure_credentials` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.ai.consent.configure_consent_module` | lib:noctusai_seed | 1 |
| `noctusai_lib.domain.ai.consent.list_user_consent_view` | core | 1 |
| `noctusai_lib.domain.ai.consent.pending_count` | core | 1 |
| `noctusai_lib.domain.ai.consent.register_feature` | core | 1 |
| `noctusai_lib.domain.ai.consent.reset_catalog_for_test` | core | 1 |
| `noctusai_lib.domain.ai.consent.upsert_decision` | core | 1 |
| `noctusai_lib.domain.ai.tool_audit.apply_feature_redaction` | social-wiring | 2 |
| `noctusai_lib.domain.chatbot.buffer.RedisBufferClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.buffer.make_in_memory_buffer_client` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.content_stats.SchemaHint` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.chatbot.content_stats.compute_content_stats` | lib:noctusai_lib | 1 |
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
| `noctusai_lib.domain.invitations.generate_invite_token` | therapy-platform | 1 |
| `noctusai_lib.domain.jobs.entity.Job` | lib:noctusai_lib | 3 |
| `noctusai_lib.domain.jobs.entity.JobStatus` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.entity.next_status` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.entity.should_retry` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.entity.with_status_transition` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.repo.DeadLetterError` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.repo.FakeJobRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.repo.JobRepository` | lib:noctusai_lib | 2 |
| `noctusai_lib.domain.jobs.repo.RealSupabaseJobRepository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.repo.make_job_repository` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.jobs.worker.Worker` | lib:noctusai_lib | 1 |
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
| `noctusai_lib.domain.org.ensure_personal_org` | personal-finance | 1 |
| `noctusai_lib.domain.sql_templates.service_role_bypass` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.set_search_path` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.updated_at_function` | lib:noctusai_lib | 1 |
| `noctusai_lib.domain.sql_templates.updated_at_trigger` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_calendar.credentials.CalendarCredentialResolver` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.google_calendar.credentials.ServiceAccountCalendarCredentials` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_calendar.mappers.event_to_google_body` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_calendar.mappers.google_body_to_created_event` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_calendar.oauth_adapter.GoogleCalendarOAuthAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_calendar.service_account_adapter.GoogleCalendarServiceAccountAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_calendar.types.CreatedEvent` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.google_drive.content_stats.compute_content_stats` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.factory.make_drive_downloader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.fake.FakeDriveDownloader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.fake_reader.FakeDriveReader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.mappers.parse_drive_url` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.protocol.DriveDownloader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.reader_factory.make_drive_reader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.reader_types.DriveFileContent` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.google_drive.reader_types.DriveReader` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_drive.reader_types.DriveSearchHit` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.google_drive.reader_types.DriveSearchResult` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.google_drive.real.RealDriveDownloader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.real_reader.RealDriveReader` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_drive.types.DriveFile` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_maps.google_maps_adapter.GoogleMapsRoutingAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_maps.mappers.build_routes_request` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_maps.mappers.parse_routes_response` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.google_maps.static_adapter.StaticRoutingAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_maps.types.Coordinates` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_maps.types.RoutingAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_maps.types.TravelEstimate` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.google_scopes.diagnose_consent_screen_gaps` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_scopes.discover_granted_scopes` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.google_scopes.resolve_google_scopes` | lib:noctusai_lib | 1 |
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
| `noctusai_lib.integrations.llm.models.all_providers` | core | 1 |
| `noctusai_lib.integrations.llm.providers.base.LLMProvider` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.llm.registry.get_provider_class` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.llm.registry.register` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.llm.usage.SupabaseUsageSink` | lib:noctusai_seed | 1 |
| `noctusai_lib.integrations.llm.usage.record_usage` | lib:noctusai_lib | 13 |
| `noctusai_lib.integrations.llm.vision.analyze_image` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.fake_adapter.FakeMediaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.real_adapter.OpenAIMediaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.types.InboundMedia` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.media.types.MediaKind` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.media.types.MediaResolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.media.types.ResolvedMedia` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.media.types.classify_media_kind` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta._meta_api.DEFAULT_GRAPH_VERSION` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.META_KITCHEN_SINK_SCOPES` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta._meta_api.MetaGraphError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta._meta_api.discover_app_permissions` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.exchange_code_for_token` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.exchange_for_long_lived` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta._meta_api.resolve_oauth_scopes` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.credentials.MetaCredentialResolver` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.credentials.OAuthMetaCredentials` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.fake_adapter.FakeMetaAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_ACCOUNT_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_MEDIA_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.IG_MEDIA_INSIGHT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.ME_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.PAGE_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.PAGE_IG_FIELD` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.POST_FIELDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.POST_INSIGHT_METRICS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.ig_account_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.ig_media_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.insights_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.page_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.mappers.parse_graph_datetime` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.mappers.post_from_body` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.oauth_adapter.MetaOAuthAdapter` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.router.make_meta_router` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.meta.types.FacebookPage` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.meta.types.FacebookPost` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.meta.types.InstagramAccount` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.meta.types.InstagramMedia` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.meta.types.MetaAdapter` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.meta.types.MetaConnectionStatus` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.meta.types.PostInsights` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.quota.factory.make_quota_tracker` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.quota.in_memory.InMemoryQuotaTracker` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.quota.protocol.QuotaTracker` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.quota.redis_backend.RedisQuotaTracker` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.quota.types.QuotaCheck` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.quota.types.QuotaConfig` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.redis.make_redis_client` | social-wiring | 1 |
| `noctusai_lib.integrations.storage.factory.make_storage_backend` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.storage.local.LocalFilesystemStorageBackend` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.storage.supabase.SupabaseStorageBackend` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.storage.types.BlobMetadata` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.storage.types.StoredBlob` | lib:noctusai_lib | 5 |
| `noctusai_lib.integrations.supabase_identity.UserIdentity` | therapy-platform | 3 |
| `noctusai_lib.integrations.supabase_identity.fetch_user_identities` | therapy-platform | 3 |
| `noctusai_lib.integrations.vista.client.DEFAULT_PAGE_SIZE` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.DEFAULT_TIMEOUT_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaCallResult` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaConfigError` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.client.VistaError` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.fake.FakeVistaClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseAgencia` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseImovel` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseImovelDetalhes` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.vista.types.ShowcaseUsuario` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.client.WahaClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.dedup.InMemoryWebhookDedup` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.dedup.RedisWebhookDedup` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.dedup.SetnxRedis` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.dedup.WebhookDedup` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.dedup.get_webhook_dedup` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.fake_adapter.FakeWahaClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.InMemoryLidPhoneCache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.LidPhoneCache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.RedisLidPhoneCache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.extract_resolved_remote` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.get_lid_phone_cache` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.is_authorized` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.is_lid` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.is_phone_jid` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.lid_auth.normalize_phone` | lib:noctusai_lib | 1 |
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
| `noctusai_lib.integrations.whatsapp.types.WhatsAppClient` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppIgnoredEvent` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppInboundMessage` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppMedia` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.whatsapp.types.WhatsAppPayloadError` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.youtube.factory.make_youtube_client` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.youtube.fake.FakeYoutubeClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.protocol.YoutubeClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.real.RealYoutubeClient` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.types.Channel` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.youtube.types.DESCRIPTION_MAX_LEN` | lib:noctusai_lib | 1 |
| `noctusai_lib.integrations.youtube.types.ListResult` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.youtube.types.Playlist` | lib:noctusai_lib | 2 |
| `noctusai_lib.integrations.youtube.types.TITLE_MAX_LEN` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.youtube.types.UPLOAD_QUOTA_UNITS` | lib:noctusai_lib | 3 |
| `noctusai_lib.integrations.youtube.types.Video` | lib:noctusai_lib | 4 |
| `noctusai_lib.integrations.youtube.types.VideoUpload` | lib:noctusai_lib | 4 |
| `noctusai_lib.primitives._correlation.get_correlation_id` | lib:noctusai_lib | 2 |
| `noctusai_lib.primitives.exceptions.AppException` | lib:noctusai_lib | 3 |
| `noctusai_lib.primitives.exceptions.app_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.generic_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.http_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.postgrest_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.exceptions.validation_exception_handler` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.responses.calculate_pagination` | core | 1 |
| `noctusai_lib.primitives.roles.DEV_ROLES` | lib:noctusai_lib | 1 |
| `noctusai_lib.primitives.roles.ORG_ROLE_LABELS` | lib:noctusai_seed | 1 |
| `noctusai_lib.primitives.tasks.NoRunningLoopError` | core | 1 |
| `noctusai_lib.primitives.timeutil.current_day_ref` | erp-imobiliario | 4 |
| `noctusai_lib.primitives.timeutil.current_month_ref` | erp-imobiliario | 5 |
| `noctusai_lib.primitives.timeutil.today_utc` | erp-imobiliario | 4 |
| `noctusai_lib.security.encrypted_tokens.MultiKeyDecryptor` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.encrypted_tokens.decrypt` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.encrypted_tokens.encrypt` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.encrypted_tokens.generate_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.encrypted_tokens.rotate_key` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.factory.make_oauth_provider` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.fake.FakeOAuthProvider` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.oauth.google_provider.GoogleProvider` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.oauth.protocol.OAuthProvider` | lib:noctusai_lib | 3 |
| `noctusai_lib.security.oauth.router.oauth_router` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.oauth.types.AuthorizationURL` | lib:noctusai_lib | 4 |
| `noctusai_lib.security.oauth.types.OAuthCallbackResult` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.oauth.types.TokenSet` | lib:noctusai_lib | 4 |
| `noctusai_lib.security.token_store.fake.FakeCredentialStore` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.token_store.supabase_store.DEFAULT_TABLE` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.token_store.supabase_store.SupabaseCredentialStore` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.token_store.types.CredentialDecryptError` | lib:noctusai_lib | 3 |
| `noctusai_lib.security.token_store.types.CredentialStore` | lib:noctusai_lib | 4 |
| `noctusai_lib.security.token_store.types.StoredCredential` | lib:noctusai_lib | 4 |
| `noctusai_lib.security.webhook_signatures.DEFAULT_MAX_AGE_SECONDS` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.static_secret_resolver` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.verify_hmac_sha256` | lib:noctusai_lib | 1 |
| `noctusai_lib.security.webhook_signatures.verify_hmac_sha256_hex` | lib:noctusai_lib | 2 |
| `noctusai_lib.security.webhook_signatures.verify_svix_signature` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing._schema_cache.get_schema_map` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing._schema_cache.reset_cache` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing._schema_cache.set_cache_for_tests` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.conftest_helpers.purge_shadowing_editable_finders` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.migration_parser.parse_files` | lib:noctusai_lib | 1 |
| `noctusai_lib.testing.schema_errors.MockCheckViolation` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing.schema_errors.MockSchemaError` | lib:noctusai_lib | 2 |
| `noctusai_lib.testing.schema_errors.MockUnknownTableError` | lib:noctusai_lib | 2 |
| `noctusai_seed.ai_feedback_router.create_ai_feedback_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.ai_router.create_ai_outputs_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.dev_auth.dev_auth_enabled` | lib:noctusai_seed | 1 |
| `noctusai_seed.dev_auth.make_dev_auth_get_current_user` | lib:noctusai_seed | 1 |
| `noctusai_seed.health.HealthCheckHook` | lib:noctusai_seed | 1 |
| `noctusai_seed.health.mount_health_endpoints` | lib:noctusai_seed | 2 |
| `noctusai_seed.llm_defaults.DEFAULT_LLM_CONFIG` | lib:noctusai_seed | 1 |
| `noctusai_seed.llm_defaults.default_llm_config` | lib:noctusai_seed | 2 |
| `noctusai_seed.llm_router.create_llm_router` | lib:noctusai_seed | 1 |
| `noctusai_seed.routers.build_standard_routers` | lib:noctusai_seed | 1 |
| `noctusai_seed.scheduler_router.create_scheduler_router` | lib:noctusai_seed | 1 |

## Duplication candidates

Public top-level functions/classes with the **same name** in 2+ products,
and **not** already exported by the shared lib. Strong signal that they
belong in `noctusai_lib`. Name-based matching has false positives —
review occurrences before absorbing.

### `AtivosService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/ativos_service.py:15`
- `personal-finance` — `products/personal-finance/backend/app/services/ativos_service.py:10`

### `DashboardService` (class)

- `personal-finance` — `products/personal-finance/backend/app/services/dashboard_service.py:12`
- `social-wiring` — `products/social-wiring/backend/app/services/dashboard_service.py:26`

### `EmailService` (class)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/email_service.py:69`
- `social-wiring` — `products/social-wiring/backend/app/services/email_service.py:46`

### `atualizar_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:266`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:57`

### `atualizar_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:136`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:229`

### `atualizar_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:138`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:371`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:59`

### `build_audit_record` (def)

- `daily-life` — `products/daily-life/backend/app/services/audit_hook.py:125`
- `personal-finance` — `products/personal-finance/backend/app/services/audit_hook.py:126`

### `check_openai_configured` (def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/ai_service.py:123`
- `personal-finance` — `products/personal-finance/backend/app/services/ai_service.py:72`

### `coerce_org_uuid` (def)

- `daily-life` — `products/daily-life/backend/app/dependencies.py:60`
- `seed` — `products/seed/backend/app/dependencies.py:61`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:90`

### `criar_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:215`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:46`

### `criar_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:92`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:151`

### `criar_meta` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:90`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:352`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:48`

### `dashboard_resumo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/bi.py:127`
- `personal-finance` — `products/personal-finance/backend/app/routers/dashboard.py:22`

### `excluir_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:313`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:71`

### `excluir_meta` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:386`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:73`

### `fluxo_caixa` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/financeiro.py:176`
- `personal-finance` — `products/personal-finance/backend/app/routers/relatorios.py:36`

### `get_admin_client` (def)

- `core` — `products/core/backend/app/database.py:32`
- `daily-life` — `products/daily-life/backend/app/dependencies.py:56`
- `seed` — `products/seed/backend/app/dependencies.py:57`
- `social-wiring` — `products/social-wiring/backend/app/database.py:29`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:77`

### `get_audit_writer` (def)

- `core` — `products/core/backend/app/services/audit_hook.py:93`
- `daily-life` — `products/daily-life/backend/app/services/audit_hook.py:97`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/audit_hook.py:93`
- `personal-finance` — `products/personal-finance/backend/app/services/audit_hook.py:98`
- `therapy-platform` — `products/therapy-platform/backend/app/services/audit_hook.py:353`

### `get_invoice` (def)

- `adconnect` — `products/adconnect/backend/app/routers/financial.py:174`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/invoices.py:73`
- `therapy-platform` — `products/therapy-platform/backend/app/services/invoice_service.py:83`

### `get_me` (async def)

- `core` — `products/core/backend/app/routers/auth.py:153`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/auth.py:120`

### `get_message_history` (def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:263`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:189`

### `get_org_id` (def)

- `adconnect` — `products/adconnect/backend/app/dependencies.py:59`
- `core` — `products/core/backend/app/dependencies.py:123`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/dependencies.py:42`

### `get_product` (def)

- `adconnect` — `products/adconnect/backend/app/routers/products.py:120`
- `adconnect` — `products/adconnect/backend/app/services/products_service.py:183`
- `core` — `products/core/backend/app/routers/products.py:33`

### `get_supabase_client` (def)

- `core` — `products/core/backend/app/database.py:23`
- `social-wiring` — `products/social-wiring/backend/app/database.py:17`
- `therapy-platform` — `products/therapy-platform/backend/app/dependencies.py:84`

### `get_user_client` (def)

- `adconnect` — `products/adconnect/backend/app/dependencies.py:113`
- `daily-life` — `products/daily-life/backend/app/dependencies.py:52`
- `personal-finance` — `products/personal-finance/backend/app/dependencies.py:56`
- `seed` — `products/seed/backend/app/dependencies.py:53`
- `social-wiring` — `products/social-wiring/backend/app/dependencies.py:71`

### `list_conversations` (def)

- `social-wiring` — `products/social-wiring/backend/app/routers/intake_monitor_router.py:92`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/messaging.py:81`
- `therapy-platform` — `products/therapy-platform/backend/app/services/messaging_service.py:263`

### `list_invoices` (def)

- `adconnect` — `products/adconnect/backend/app/routers/admin.py:322`
- `adconnect` — `products/adconnect/backend/app/routers/financial.py:124`
- `core` — `products/core/backend/app/routers/billing.py:326`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/invoices.py:48`
- `therapy-platform` — `products/therapy-platform/backend/app/services/invoice_service.py:61`

### `list_reports` (def)

- `adconnect` — `products/adconnect/backend/app/routers/sellout.py:190`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/support.py:104`

### `listar_ativos` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:140`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:15`

### `listar_checkins` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:198`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/campo.py:133`

### `listar_eventos` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:62`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/agenda.py:98`

### `listar_membros` (async def)

- `core` — `products/core/backend/app/routers/team.py:86`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/equipes.py:141`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/equipes_service.py:111`

### `listar_metas` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/goals.py:63`
- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/metas.py:319`
- `personal-finance` — `products/personal-finance/backend/app/routers/metas.py:15`

### `login` (async def)

- `core` — `products/core/backend/app/routers/auth.py:111`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/auth.py:83`
- `therapy-platform` — `products/therapy-platform/backend/app/services/auth_service.py:234`

### `obter_ativo` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/routers/ativos.py:204`
- `personal-finance` — `products/personal-finance/backend/app/routers/ativos.py:35`

### `obter_evento` (async def)

- `daily-life` — `products/daily-life/backend/app/routers/schedule.py:122`
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

### `send_message` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:164`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/messaging.py:161`
- `therapy-platform` — `products/therapy-platform/backend/app/routers/whatsapp_therapy.py:32`
- `therapy-platform` — `products/therapy-platform/backend/app/services/messaging_service.py:179`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:159`

### `send_via_waha` (async def)

- `erp-imobiliario` — `products/erp-imobiliario/backend/app/services/whatsapp_service.py:303`
- `therapy-platform` — `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:42`

### `stripe_webhook` (async def)

- `adconnect` — `products/adconnect/backend/app/routers/financial.py:272`
- `core` — `products/core/backend/app/routers/billing.py:92`

