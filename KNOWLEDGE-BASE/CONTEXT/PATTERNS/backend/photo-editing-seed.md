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
| Optional per-org edit cap | `integrations.quota` |

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
| `learning.py` | rule proposer (cursor watermark, case-insensitive dedupe) · `decide_rule` authority (agency admin decides a proposal; only platform admin flips a decided rule) |
| `access.py` | `compute_capabilities` → contract §2 `/capacidades` (server-computed, never SSO metadata) |
| `pipeline.py` | route entry points: `add_photo_bytes`, `submit_batch`, `retry_photo`, debounced `schedule_*`, `enqueue_*` |
| `handlers.py` | one idempotent handler per job type · `build_handlers` · `build_worker` |
| `ports.py` | `PhotoEditingPorts` (the one DI seam) + `PhotoStorage`, `StructuredLlm`, `BatchReadyNotifier` ports with in-memory fakes + real adapters |
| `repository.py` | `PhotoEditingRepository` Protocol + `InMemoryPhotoEditingRepository` + `SupabasePhotoEditingRepository` + `make_photo_editing_repository` |

---

## 4. Public API the consumer wires against

### 4.1 `PhotoEditingPorts`

```python
@dataclass(frozen=True)
class PhotoEditingPorts:
    repo: PhotoEditingRepository          # make_photo_editing_repository(supabase_client=admin, schema="social_wiring")
    jobs: JobRepository                   # make_job_repository(supabase_client=admin, schema_name="social_wiring")
    storage: PhotoStorage                 # consumer adapter over the private bucket
    imaging: ImagingAdapter               # get_imaging_adapter()
    image_edit: ImageEditFactory          # (org_id, model_id) -> ImageEditAdapter; openai_image_edit_factory(key_provider)
    llm: StructuredLlm                    # LlmStructuredAdapter()
    fx: FxRateAdapter                     # get_fx_rate_adapter(live=True)
    notifier: BatchReadyNotifier          # consumer fan-out (in-app + email + WhatsApp)
    config: PhotoEditingConfig = PhotoEditingConfig()
    clock: Callable[[], datetime] = utcnow
    edit_quota: QuotaTracker | None = None  # key f"fotos.edit:{org_id}", registered by the consumer
```

`openai_image_edit_factory` REFUSES (`ImageEditNotConfigured`, fatal) when
no key resolves — unlike `get_image_edit_adapter`, which falls back to the
Fake and would let a production batch "succeed" with placeholder bytes.

### 4.2 Handlers — `async def handle_x(ports, job) -> None`

| Job type | Payload | Does |
|---|---|---|
| `fotos.ingest` | `foto_id` | `recebida → normalizando → pronta`; stores the GPS-stripped JPEG as `original.jpg`, deletes the raw upload; enqueues the edit if the batch is already submitted |
| `fotos.submit_lote` | `lote_id` | `submetido → processando`; re-validates; enqueues edits for `pronta` photos |
| `fotos.edit` | `foto_id` | Urgente only · `pronta → editando → editada`; one combined edit at `compute_edit_size`, Lanczos back to the input size, watermark when staging; cost recorded; enqueues evaluation |
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
`build_batch_zip` · `decide_rule` · `create_draft` / `restore_version` /
`activate_version` · `schedule_guide_regen` · `compute_capabilities`.
Every validation error carries a `code` for the contract's error envelope
(`SubmissionError.code` ∈ `modelo_nao_configurado`, `modelo_desconhecido`,
`sem_tipos_edicao`, `economico_indisponivel`, `lote_vazio`, `lote_cheio`,
`arquivo_grande_demais`, …).

### 4.4 Repository

`PhotoEditingRepository` groups: settings · batches · photos (`transition_photo`
is the ONLY status writer: read, legality check, compare-and-set on the read
status, event append; `None` ⇒ lost race) · edits / evaluations / decisions /
dataset · pool / guides / rules / rule sets / effective guides / proposal
cursor · costs (`add_llm_usage`, `add_cost`, `list_fx_pending`, `resolve_fx`).
The Supabase implementation targets social-wiring migrations 123-126 (plus
121 jobs and 122 `llm_usage`) in `schema`, and Core 046 `public.cost_ledger`
in `cost_schema`.

---

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
- **Econômico** — `submit_batch` refuses it (`ECONOMICO_IMPLEMENTED = False`);
  `compute_capabilities` reports `modelo_sem_batch` / `nao_implementado`.

---

## 6. Known gaps (named destinations)

- `NOC-REMEDIATE[llm-analyze-images-usage]` (`ports.py`) — `analyze_images`
  returns no usage, so evaluator / rule-proposer calls through
  `LlmStructuredAdapter` record no `cost_ledger` row (only the llm organ's
  process-wide sink sees them). Fix at the organ.
- `NOC-REMEDIATE[image-edit-batch-c8]` (`integrations.image_edit`) — the
  Econômico path.
- Style-guide regeneration is platform scope: no `org_id`, so no
  `cost_ledger` row (the column is NOT NULL).
- No live OpenAI verification was possible (no credits, PROJECT.md § 4c):
  the suite runs on fakes only.

---

## 7. Tests

`seed/lib/backend/tests/domain/photo_editing/` — a full upload-to-zip run
driven by the real `domain.jobs.Worker` on in-memory ports; real-pixel runs
(720x1080, 1620x1080) proving JPEG output at the input size; retry-once,
fatal, manual retry, quota, debounce, cost and fx paths; the Supabase
repository against `MockSupabaseClient(validate_schema=True)`, which checks
every column against the real migrations. DI only — no monkeypatching.

Composes with: `KB § PATTERNS/backend/seed-fake-real-adapter.md` ·
`KB § PATTERNS/backend/di-test-seam.md` · `KB § PATTERNS/backend/llm-usage.md` ·
`KB § INTEGRATIONS/image-edit.md` · `KB § INTEGRATIONS/fx-ptax.md`.
