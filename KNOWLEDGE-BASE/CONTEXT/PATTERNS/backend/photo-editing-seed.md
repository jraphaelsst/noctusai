# Photo-editing engine (seed-lib)

> `noctusai_lib.domain.photo_editing` — the AI real-estate photo-editing
> pipeline as a product-agnostic seed organ: upload, normalize, one
> combined AI edit per photo, AI evaluation, human review, zip of the
> approved photos, plus the style-guide lifecycle, the per-agency learning
> loop, the training dataset and per-call cost recording. Built 2026-09-16
> as `edicao-fotos` Slice S8 (release R1: engine + review + zip; billing is
> R2; Econômico deferred per `projects/edicao-fotos/PROJECT.md` C8).
> First consumer: social-wiring `app/modules/edicao_fotos/` (W2/W3).
> Phase 2 rebuilds the engine in an external app with this package as the
> reference, so it carries NO product coupling.

---

## 1. When to use it

Any product that runs a batch of images through an AI edit and a human
review. The engine owns the pipeline; the consumer owns routes, auth,
storage bucket, notification fan-out and the scheduler.

Do NOT use it for single-shot image generation (`integrations.image_gen`)
or for a raw edit call without review (`integrations.image_edit` directly).

---

## 2. What it consumes (never re-implements)

| Need | Seed organ |
|---|---|
| Edit call, per-model capabilities, retryable-vs-fatal taxonomy | `integrations.image_edit` → `KB § INTEGRATIONS/image-edit.md` |
| Normalize (HEIC, EXIF transpose, sRGB, GPS strip), Lanczos resize, watermark | `integrations.imaging` |
| Largest non-experimental edit size (edges multiple of 16) | `primitives.image_sizing.compute_edit_size` |
| Structured multi-image calls, model catalog, cost estimate | `integrations.llm` (`analyze_images`, `models_for`, `estimate_cost_usd`) |
| PTAX venda/fechamento | `integrations.fx` → `KB § INTEGRATIONS/fx-ptax.md` |
| Worker, `RetryPolicy`, dedupe keys, leases | `domain.jobs` |
| Curator grant (`photo_curator`) | `domain.permissions` |
| Optional per-org edit cap | `integrations.quota` (`DefaultingQuotaTracker` — per-org keys need no registration step) |
| Photo bytes in a bucket | `integrations.storage` (via `BucketPhotoStorage`) |

---

## 3. Module map

| Module | Owns |
|---|---|
| `types.py` | pt-BR literals == the SQL CHECKs · photo state machine (`can_transition`, `sources_for`) · records (field names == column names) · `JobType` · `dedupe_*` keys |
| `prompts/` | 5 versioned `PromptTemplate`s (edit · evaluator · style guide · rule proposer · note writer), pt-BR; a sha pin test forces a version bump on any wording change |
| `guide.py` | effective guide = active company guide + org's APPROVED rules → deterministic text + sha256 · rule-set versioning · drafts, restore-as-new-version, activation · style-guide builder |
| `naming.py` | zip `NN` = upload position (`ordem`), 2 digits, 3 when the batch has more than 99 photos · `_imagem-gerada-com-ia` suffix · `{org}/{lote}/{foto}/<name>` storage layout |
| `zipper.py` | approved photos only · `BatchNotDecidedError` (409) until every non-failed photo is decided · `falhou` excluded, never blocking · byte-deterministic archive |
| `dataset.py` | `record_decision`: append decision + append training record; a rejection bumps the proposal cursor and schedules the rule proposer |
| `costs.py` | usage priced from the catalog at call time → `llm_usage` + `cost_ledger` (USD native, PTAX rate + quote date, BRL) · `fx_pending` when no bulletin · `backfill_fx` |
| `learning.py` | rule proposer (cursor watermark, case-insensitive dedupe) · `decide_rule` authority (agency admin decides a proposal; only platform admin flips a decided rule) · `create_manual_rule` / `edit_rule_text` (W7 — manual create is auto-APROVADA, sharing authority via `can_manage_rule`; edit refuses once REJEITADA) |
| `pool.py` | reference pool entry points: `add_reference_pair` (normalize both sides, GPS strip, store under `referencias/<token>/{antes,depois}.jpg`, pair limit, cleanup on a refused insert) · `archive_reference_pair` (idempotent) · `pool_status` (active count + limit, `None`/`0` = unlimited) |
| `access.py` | `compute_capabilities` → contract §2 `/capacidades` (server-computed, never SSO metadata) |
| `pipeline.py` | route entry points: `add_photo_bytes`, `submit_batch`, `retry_photo`, debounced `schedule_*`, `request_guide_regen` (manual, runs now), `enqueue_*` |
| `handlers.py` | one idempotent handler per job type · `build_handlers` · `build_worker` |
| `ports.py` | `PhotoEditingPorts` (the one DI seam) + `PhotoStorage` (`InMemoryPhotoStorage` / `BucketPhotoStorage` over `integrations.storage`, with `signed_url`), `StructuredLlm`, `BatchReadyNotifier` ports with in-memory fakes + real adapters |
| `repository.py` | `PhotoEditingRepository` Protocol + `InMemoryPhotoEditingRepository` + `SupabasePhotoEditingRepository` + `make_photo_editing_repository` |

---

## 4. Public API the consumer wires against

### 4.1 `PhotoEditingPorts`

```python
@dataclass(frozen=True)
class PhotoEditingPorts:
    repo: PhotoEditingRepository          # make_photo_editing_repository(supabase_client=<PUBLIC-default service role>, schema="social_wiring")
    jobs: JobRepository                   # make_job_repository(supabase_client=<product-schema-default admin>, schema_name="social_wiring")
    storage: PhotoStorage                 # BucketPhotoStorage(make_storage_backend(kind="supabase", client=admin), bucket="edicao-fotos")
    imaging: ImagingAdapter               # get_imaging_adapter()
    image_edit: ImageEditFactory          # (org_id, model_id) -> ImageEditAdapter; openai_image_edit_factory(key_provider)
    llm: StructuredLlm                    # LlmStructuredAdapter()
    fx: FxRateAdapter                     # get_fx_rate_adapter(live=True)
    notifier: BatchReadyNotifier          # consumer fan-out (in-app + email + WhatsApp)
    config: PhotoEditingConfig = PhotoEditingConfig()
    clock: Callable[[], datetime] = utcnow
    edit_quota: QuotaTracker | None = None  # key f"fotos.edit:{org_id}", registered by the consumer
    reference_storage: PhotoStorage | None = None  # BucketPhotoStorage(..., bucket="edicao-fotos-referencias")
    capabilities: Callable[[str], ImageEditCapabilities] = catalog_capabilities  # the Econômico gate
```

**`capabilities` is the ONLY Econômico gate** (W4). `submit_batch`,
`compute_capabilities(..., capabilities=ports.capabilities)`, the batch
handlers and the consumer's routes all read it. The default resolves
`image_edit.capabilities_for_model` at CALL time, so a catalog seam
installed after import is honoured. A consumer that injects a different
lookup passes the same callable to `openai_image_edit_factory(...,
capabilities=)` so the adapter's own batch refusal agrees.

**Reference pairs store KEYS, not URLs.** With `reference_storage` wired,
`ReferencePair.antes_url` / `depois_url` hold keys in that (private) bucket;
the style-guide builder reads the BYTES (`guide.reference_images`) and a
missing object raises — a guide is never built from a partial pool. Routes
sign the keys for display; a key never reaches the wire. Without the port the
columns are treated as fetchable URLs (legacy/test shape) and
`add_reference_pair` refuses (`ReferenceStorageNotConfigured`).

🔴 **Two clients, not one.** The repository reaches pipeline tables with
`.schema(schema)` but `cost_ledger` (`cost_schema="public"`) with the bare
`client.table(...)` — so it needs a client whose DEFAULT schema is `public`
(a product's `get_core_client()`); a product-schema-default admin client
sends every cost row to `<product>.cost_ledger`. The job repository is the
opposite: its RPCs are bare calls, so it needs the client whose default IS
the schema hosting `claim_next_job` & co. Social-wiring's
`services/ports.py` is the reference wiring.

`openai_image_edit_factory` REFUSES (`ImageEditNotConfigured`, fatal) when
no key resolves — unlike `get_image_edit_adapter`, which falls back to the
Fake and would let a production batch "succeed" with placeholder bytes.

### 4.2 Handlers — `async def handle_x(ports, job) -> None`

| Job type | Payload | Does |
|---|---|---|
| `fotos.ingest` | `foto_id` | `recebida → normalizando → pronta`; stores the GPS-stripped JPEG as `original.jpg`, deletes the raw upload; enqueues the edit if the batch is already submitted |
| `fotos.submit_lote` | `lote_id` | `submetido → processando`; re-validates; Urgente ⇒ enqueues edits for `pronta` photos · Econômico ⇒ enqueues ONE `fotos.submit_openai_batch` |
| `fotos.edit` | `foto_id` | Urgente only · `pronta → editando → editada`; one combined edit at `compute_edit_size`, Lanczos back to the input size, watermark when staging; cost recorded; enqueues evaluation |
| `fotos.submit_openai_batch` | `lote_id` | Econômico · waits while any photo is still ingesting (the last ingest re-enqueues it) · gate + price + guide checked before spend · one edit attempt per photo, a `preparando` `fotos_lotes_openai` row, `pronta → em_lote_openai`, then `adapter.submit_batch` → `enviado` + poll #0 in 5 min. A `preparando` row (crash / transient error before the provider confirmed) is RESUMED, never duplicated. Final failure ⇒ every involved photo `falhou`, row `falhou` |
| `fotos.poll_openai_batch` | `lote_openai_id`, `consulta` | Econômico · self-rescheduling poll: 5 → 15 → 30 → 30… min (`PhotoEditingConfig.openai_batch_poll_schedule_seconds`). A transient POLL error reschedules instead of failing; past `openai_batch_max_wait_seconds` (26 h) every waiting photo fails. Terminal ⇒ `fetch_batch_results` and each item goes through the SAME output path as `fotos.edit` (`em_lote_openai → editada`, cost with `batch=True` at `BATCH_API_DISCOUNT`) → evaluation. Transient item failure (incl. missing / expired) ⇒ back to `pronta` for ONE more provider batch (counted per `(foto_id, tentativas)` across `itens`); a second or fatal one ⇒ `falhou` |
| `fotos.avaliar` | `foto_id`, `edicao_id` | `editada → avaliando → aguardando_decisao`; `[original, edited]` → strict JSON; structural infidelity FORCES `rejeitar` |
| `fotos.lote_pronto` | `lote_id` | all photos done → notify, then `processando → pronto` (at-least-once) |
| `fotos.regen_guia` | — | trailing debounce on pool changes → AI-written DRAFT |
| `fotos.propor_regras` | `org_id` | trailing debounce on rejections → proposed rules |
| `fotos.fx_backfill` | `dia` | resolves `fx_pending` ledger rows |

Run them with `build_worker(ports, worker_id=...)` — it binds
`ports.config.retry_policy()` (one automatic retry), which the handlers'
own last-attempt check assumes.

### 4.3 Route entry points (`pipeline.py`, `dataset.py`, `learning.py`, `guide.py`, `zipper.py`)

`add_photo_bytes` · `submit_batch` · `retry_photo` · `record_decision` ·
`build_batch_zip` · `decide_rule` · `create_manual_rule` · `edit_rule_text` ·
`create_draft` / `restore_version` / `activate_version` ·
`schedule_guide_regen` · `request_guide_regen` · `schedule_rule_proposal` /
`request_rule_proposal` (W7 — the manual "propor agora" run-now twin,
mirrors `request_guide_regen`; `handle_propor_regras` skips the
rejection-settling debounce for `manual` payloads) ·
`add_reference_pair` / `archive_reference_pair` / `pool_status` ·
`compute_capabilities`.

**Pool limit — two halves.** `add_reference_pair` checks
`PlatformSettings.limite_pares_referencia` first (friendly `PoolFullError`,
code `pool_cheio`); the repository WRITE refuses too (in-memory mirrors it;
Supabase maps social-wiring migration 129's `BEFORE INSERT` trigger — which
row-locks the settings singleton, so concurrent uploads serialize — to the
same error via `POOL_FULL_DB_MARKER`). A pre-check alone races.

**Manual vs automatic rebuild.** Every pool change calls
`schedule_guide_regen` (trailing debounce; the handler re-schedules while the
pool is still changing). The "regenerate" button calls
`request_guide_regen`: payload `{"manual": true}`, unscheduled, a 60 s
dedupe window (double click = one job), refused with `PoolEmptyError`
(`pool_vazio`) on an empty pool; the handler skips the settle check for it.
Both produce a DRAFT — only `activate_version` makes a guide active.
A hand-written draft is just `create_draft(..., gerado_de_versao=None,
criado_por=<user>)` — the no-AI path.
Every validation error carries a `code` for the contract's error envelope
(`SubmissionError.code` ∈ `modelo_nao_configurado`, `modelo_desconhecido`,
`sem_tipos_edicao`, `economico_indisponivel`, `lote_vazio`, `lote_cheio`,
`arquivo_grande_demais`, …).

### 4.4 Repository

`PhotoEditingRepository` groups: settings (`get_*`, `save_org_settings`,
`update_platform_settings`) · batches (incl. `list_batches(org_id=,
criado_por=, limit=, offset=) -> (page, total)`, newest first, explicit
range) · photos (`transition_photo`
is the ONLY status writer: read, legality check, compare-and-set on the read
status, event append; `None` ⇒ lost race) · edits / evaluations / decisions /
dataset · pool (`add_reference`, `get_reference`, `archive_reference` CAS,
`count_active_references`, paged `list_references(include_archived=)`) ·
guides (paged `list_guides`, highest version first) · rules / rule sets /
effective guides / proposal cursor · costs (`add_llm_usage`, `add_cost`, `list_fx_pending`, `resolve_fx`) ·
Econômico provider batches (`create_openai_batch`, `get_openai_batch`,
`update_openai_batch`, `list_openai_batches` → `fotos_lotes_openai`, SW 132;
`OpenAIBatchRecord.itens` = `{foto_id, edicao_id, custom_id, tentativas, prompt}`).
The Supabase implementation targets social-wiring migrations 123-126 and 132 (plus
121 jobs and 122 `llm_usage`) in `schema`, and Core 046 `public.cost_ledger`
in `cost_schema`.

---

### 4.5 First consumer — social-wiring (W2, 2026-09-16)

`products/social-wiring/backend/app/modules/edicao_fotos/`: routes under
`/api/edicao-fotos` (capacidades · configuracoes · curadores · modelos ·
lotes · revisao), authorization + org scoping in `deps.py` (the engine's service-role
client bypasses RLS, so visibility is enforced there), the worker behind
`EDICAO_FOTOS_WORKER_ENABLED` (default OFF), and the in-app batch-ready
notifier. Curator grants use `domain.permissions`' `list_grants` /
`add_grant` / `remove_grant`. Tests drive the routes and the real seed
Worker on `InMemoryPhotoEditingRepository(id_factory=...)` (UUID ids for
UUID path params). List views read `photo_states_for_batches` (one paged
read per page, not one per batch).

W6 (2026-09-16) added `/referencias` (multipart `antes` + `depois` +
`comodo` + repeated `tipos_edicao` + `nota`; `DELETE` archives) and `/guias`
(list · manual `POST` draft · `regenerar` · `{versao}/ativar` ·
`{versao}/restaurar`), both behind `deps.require_pool_manager` (platform
admin ∨ `photo_curator` grant — never an agency admin; the pool is platform
scope). The pair limit is `PUT /configuracoes/plataforma`
`limite_pares_referencia` (only written when sent, so an older client never
resets it). The pool bucket is wired as `reference_storage`.

W7 (2026-09-16) added `/regras` (list · manual create/edit · `aprovar` /
`rejeitar` · `propor-agora` · `guia-efetivo`), behind `deps.require_org_admin`
(agency admin ∨ platform admin — never a corretor) plus `deps.load_visible_rule`
(a rule from another org 404s for EVERY caller including the platform admin —
same "stay inside your own org" shape `load_visible_batch` already has).
"Archive" an approved rule reuses `POST /{id}/rejeitar` — no new status;
`decide_rule`'s existing only-platform-admin-may-override authority applies
unchanged whether the rule came from the AI proposer or a manual entry.
`GET /regras/guia-efetivo` calls `resolve_effective_guide` on a GET
(idempotent by `(org_id, sha256)`, so safe) and returns `atual: null` rather
than raising when no company guide is active yet. 🔴
`rule_proposal_debounce_seconds` / `max_rejections_per_proposal` stayed
`PhotoEditingConfig` engine tunables, NOT new `fotos_platform_settings`
columns — this slice was told not to add a migration; `GET
/configuracoes/plataforma` surfaces them READ-ONLY, `PUT` refuses them.

**Wire shapes are the seed FE's.** Responses match the types in
`seed/lib/frontend/src/photo-editing/hooks.ts` (`LoteResumo`,
`LoteDetalhe`, `FotoRevisao`, `OrgConfiguracoes`, `ModeloCatalogoItem`),
pinned by `seed/lib/frontend/src/photo-editing/contract.fixture.json`, which
the backend replays against its live routes. `compute_capabilities` emits
`dashboard ∈ {"platform", "org", None}` — the FE's literal set. Errors use
the seed's flat `{"detail", "code"}` shape.

## 5. Invariants

- 🔴 **Failure policy** — retryable (429 · 5xx · timeout · malformed model
  output · unknown) ⇒ one automatic retry, then `falhou`; fatal (content
  policy · invalid size · unsupported file · missing config · unpriced model
  · quota) ⇒ `falhou` at once. `falhou` never blocks the batch and is never
  zipped; `retry_photo` starts a new attempt under a fresh dedupe key.
- 🔴 **The verdict never reaches a corretor** — it lives in its own record;
  `fotos_eventos` details carry ids only, never score / recommendation / cost.
- 🔴 **No silent money** — an unknown or unpriced model raises
  `UnpricedModelError` before the provider is called; a missing bulletin ⇒
  `fx_pending` (never `LLM_USD_TO_BRL`); a call without usage ⇒ a
  `custo_nao_registrado` event, never a fabricated $0.
- **Snapshot at submit** — guide sha + editor model are frozen on the batch;
  activating a new guide never changes an in-flight batch.
- **Idempotent everywhere** — dedupe key per enqueue, state check before work,
  compare-and-set per transition. `fotos.lote_pronto` keys on a digest of
  every photo's state, so the last completion of a round always fires.
- **Econômico** (W4) — allowed exactly when `ports.capabilities(model).supports_batch`;
  otherwise `submit_batch` refuses `economico_indisponivel` and
  `compute_capabilities` reports `modelo_sem_batch`. Never silently
  downgraded to Urgente. Dedupe: `fotos.submit_openai_batch` keys on the
  photo-state digest + the number of provider batches already opened (an
  automatic retry returns photos to the SAME `pronta` state).
- **`ImageEditRequest.extra` reaches the provider verbatim** — engine
  metadata (prompt refs, ids) goes on events / rows, never there.

---

## 6. Known gaps (named destinations)

- `NOC-REMEDIATE[llm-analyze-images-usage]` (`ports.py`) — `analyze_images`
  returns no usage, so evaluator / rule-proposer calls through
  `LlmStructuredAdapter` record no `cost_ledger` row (only the llm organ's
  process-wide sink sees them). Fix at the organ.
- Econômico is at-least-once at the provider edge: a crash AFTER the
  provider accepted a batch but BEFORE the row turned `enviado` resubmits
  the same photos on resume (double spend for that batch). Closing it needs
  a provider-side lookup by `metadata.lote_openai_id` — not built.
- A fatal `fotos.submit_lote` (e.g. the model vanished from the catalog
  between submit and the job) dead-letters the job but leaves the batch
  `submetido` with `pronta` photos — pre-existing, speed-independent.
- Style-guide regeneration is platform scope: no `org_id`, so no
  `cost_ledger` row (the column is NOT NULL).
- The pool limit's write-time half lives in social-wiring migration 129 —
  until that file is applied (owner consent), setting the limit fails at
  PostgREST (missing column) and only the pre-check guards the pool.
- No live OpenAI verification was possible (no credits, PROJECT.md § 4c):
  the suite runs on fakes only.
- `NOC-REMEDIATE[fotos-rule-proposer-settings-migration]` (W7) — making
  `rule_proposal_debounce_seconds` / `max_rejections_per_proposal` genuinely
  editable in the UI needs a new `fotos_platform_settings` column (no spare
  capacity today); this slice was told not to add a migration (SW 130-132
  claimed by parallel slices), so they stay `PhotoEditingConfig` engine
  tunables, surfaced READ-ONLY on `GET /configuracoes/plataforma`.
- `NOC-REMEDIATE[mock-count-exact-ignores-predicates]` (seed
  `noctusai_lib.testing.MockSupabaseClient`) — `select(..., count="exact")`
  snapshots `len(table)` at `.select()` time, before any `.eq()` narrows it,
  so a filtered Supabase-repo test cannot assert `total` against the mock
  (assert on the returned rows instead — see
  `test_repository.py::test_supabase_rule_edit_and_effective_guide_listing`).

---

## 7. Tests

`seed/lib/backend/tests/domain/photo_editing/` — a full upload-to-zip run
driven by the real `domain.jobs.Worker` on in-memory ports; real-pixel runs
(720x1080, 1620x1080) proving JPEG output at the input size; retry-once,
fatal, manual retry, quota, debounce, cost and fx paths; the Econômico
run (`test_economico.py`: submit → poll pending → poll done → evaluate →
ready, auto-retry, expiry, overdue, resume, discount); the Supabase
repository against `MockSupabaseClient(validate_schema=True)`, which checks
every column against the real migrations. DI only — no monkeypatching.

Composes with: `KB § PATTERNS/backend/seed-fake-real-adapter.md` ·
`KB § PATTERNS/backend/di-test-seam.md` · `KB § PATTERNS/backend/llm-usage.md` ·
`KB § INTEGRATIONS/image-edit.md` · `KB § INTEGRATIONS/fx-ptax.md`.
