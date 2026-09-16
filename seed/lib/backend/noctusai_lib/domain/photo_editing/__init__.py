"""Photo-editing engine — AI real-estate photo editing as a seed organ.

Upload → normalize (GPS-stripped) → ONE combined AI edit per photo →
back to the input size (+ watermark for virtual staging) → AI evaluation
→ human review (✓ / ✗ with comment) → zip of the approved photos. Plus
the style-guide lifecycle, the per-agency learning loop, the training
dataset, and per-call cost recording in USD with the PTAX rate.

Product-agnostic by construction: no product import, no product name in
behaviour. The first consumer is social-wiring's ``edicao_fotos`` module;
Phase 2 rebuilds the engine elsewhere with this package as the reference.
Depth: ``KB § PATTERNS/backend/photo-editing-seed.md``.

**Consumes (never re-implements):** ``integrations.image_edit`` (edit +
catalog capabilities + retryable/fatal taxonomy), ``integrations.imaging``
+ ``primitives.image_sizing`` (normalize, GPS strip, Lanczos resize,
watermark, edit size), ``integrations.llm`` (``analyze_images``, model
catalog, ``estimate_cost_usd``), ``integrations.fx`` (PTAX),
``integrations.quota`` (optional per-org edit cap), ``domain.jobs``
(Worker, RetryPolicy, dedupe keys, leases), ``domain.permissions``
(curator grant).

**Wiring (consumer):**

    ports = PhotoEditingPorts(
        repo=make_photo_editing_repository(supabase_client=admin, schema="social_wiring"),
        jobs=make_job_repository(supabase_client=admin, schema_name="social_wiring"),
        storage=BucketPhotoStorage(make_storage_backend(kind="supabase", client=admin), bucket=...),
        imaging=get_imaging_adapter(),
        image_edit=openai_image_edit_factory(key_provider),
        llm=LlmStructuredAdapter(),
        fx=get_fx_rate_adapter(live=True),
        notifier=<BatchReadyNotifier fan-out>,
    )
    worker = build_worker(ports, worker_id="fotos-1")
    await worker.run_forever(stop_event=stop)

**Econômico (W4, resolves C8):** a batch with ``velocidade='economico'`` sends
its photos as ONE provider batch (``fotos.submit_openai_batch`` → photos
``em_lote_openai`` → ``fotos_lotes_openai`` row), polls it on the
5 / 15 / 30 min schedule (``fotos.poll_openai_batch``), then applies each
item like a synchronous edit with the cost at ``BATCH_API_DISCOUNT``. The
ONLY gate is ``PhotoEditingPorts.capabilities(model).supports_batch`` (the
catalog by default): ``submit_batch`` refuses with ``economico_indisponivel``
when it is false.
"""

from noctusai_lib.domain.photo_editing.access import compute_capabilities
from noctusai_lib.domain.photo_editing.costs import (
    BATCH_API_DISCOUNT,
    BackfillReport,
    RecordedCost,
    UnpricedModelError,
    backfill_fx,
    build_cost_row,
    price_usage_usd,
    record_ai_cost,
)
from noctusai_lib.domain.photo_editing.dataset import (
    CommentRequiredError,
    DecisionOutcome,
    PhotoNotDecidableError,
    build_dataset_record,
    record_decision,
)
from noctusai_lib.domain.photo_editing.guide import (
    GuideNotActiveError,
    GuideVersionNotFoundError,
    activate_version,
    compose_effective_guide,
    create_draft,
    generate_draft_from_pool,
    resolve_effective_guide,
    restore_version,
)
from noctusai_lib.domain.photo_editing.handlers import (
    HANDLERS,
    EditQuotaExceededError,
    PhotoEditingConfigError,
    ProcessingGate,
    build_handlers,
    build_worker,
    handle_avaliar,
    handle_edit,
    handle_fx_backfill,
    handle_ingest,
    handle_lote_pronto,
    handle_notas_modelos,
    handle_poll_openai_batch,
    handle_propor_regras,
    handle_regen_guia,
    handle_submit_lote,
    handle_submit_openai_batch,
    is_retryable,
)
from noctusai_lib.domain.photo_editing.learning import (
    Actor,
    DuplicateRuleError,
    InvalidModelOutputError,
    RuleArchivedError,
    RuleDecisionForbiddenError,
    RuleNotFoundError,
    can_decide_rule,
    can_manage_rule,
    create_manual_rule,
    decide_rule,
    edit_rule_text,
    propose_rules,
)
from noctusai_lib.domain.photo_editing.naming import (
    STAGING_SUFFIX,
    storage_path,
    zip_entry_name,
    zip_file_name,
)
from noctusai_lib.domain.photo_editing.pipeline import (
    ECONOMICO_IMPLEMENTED,
    NotFoundError,
    PhotoNotRetryableError,
    PoolEmptyError,
    SubmissionError,
    add_photo_bytes,
    enqueue_fx_backfill,
    enqueue_model_notes,
    enqueue_openai_batch_poll,
    enqueue_openai_batch_submit,
    request_guide_regen,
    request_rule_proposal,
    retry_photo,
    schedule_guide_regen,
    schedule_rule_proposal,
    submit_batch,
    validate_submission,
)
from noctusai_lib.domain.photo_editing.notes import (
    NotesReport,
    NoteWriterOutputError,
    write_model_notes,
)
from noctusai_lib.domain.photo_editing.pool import (
    PoolStatus,
    ReferenceImageError,
    ReferenceNotFoundError,
    ReferenceStorageNotConfigured,
    add_reference_pair,
    archive_reference_pair,
    pool_status,
)
from noctusai_lib.domain.photo_editing.ports import (
    BatchReadyNotice,
    BatchReadyNotifier,
    BucketPhotoStorage,
    FakeStructuredLlm,
    InMemoryPhotoStorage,
    LlmStructuredAdapter,
    PhotoEditingConfig,
    PhotoEditingPorts,
    PhotoStorage,
    RecordingNotifier,
    StructuredLlm,
    StructuredResult,
    TokenUsage,
    catalog_capabilities,
    openai_image_edit_factory,
)
from noctusai_lib.domain.photo_editing.repository import (
    InMemoryPhotoEditingRepository,
    PhotoEditingRepository,
    RepositoryError,
    SupabasePhotoEditingRepository,
    make_photo_editing_repository,
)
from noctusai_lib.domain.photo_editing.steps import (
    STEP_KIND,
    Step,
    StepModelError,
    StepModelView,
    resolve_rule_proposer_tunables,
    resolve_step_model,
    step_models_view,
    validate_step_model,
)
from noctusai_lib.domain.photo_editing.types import (
    Batch,
    BatchStatus,
    Decision,
    EditType,
    JobType,
    ModelNote,
    OpenAIBatchRecord,
    OpenAIBatchStatus,
    OrgSettings,
    GuideStatus,
    Photo,
    PhotoStatus,
    PlatformSettings,
    PoolFullError,
    ReferencePair,
    Room,
    RuleStatus,
    Speed,
    StyleGuide,
)
from noctusai_lib.domain.photo_editing.zipper import (
    BatchNotDecidedError,
    NothingApprovedError,
    build_batch_zip,
    build_zip,
    plan_zip,
)

__all__ = [
    "Actor",
    "BATCH_API_DISCOUNT",
    "BackfillReport",
    "Batch",
    "BatchNotDecidedError",
    "BatchReadyNotice",
    "BatchReadyNotifier",
    "BatchStatus",
    "BucketPhotoStorage",
    "CommentRequiredError",
    "Decision",
    "DecisionOutcome",
    "DuplicateRuleError",
    "ECONOMICO_IMPLEMENTED",
    "EditQuotaExceededError",
    "EditType",
    "FakeStructuredLlm",
    "GuideNotActiveError",
    "GuideStatus",
    "GuideVersionNotFoundError",
    "HANDLERS",
    "InMemoryPhotoEditingRepository",
    "InMemoryPhotoStorage",
    "InvalidModelOutputError",
    "JobType",
    "LlmStructuredAdapter",
    "NotFoundError",
    "NothingApprovedError",
    "OpenAIBatchRecord",
    "OpenAIBatchStatus",
    "OrgSettings",
    "Photo",
    "PhotoEditingConfig",
    "PhotoEditingConfigError",
    "PhotoEditingPorts",
    "PhotoEditingRepository",
    "PhotoNotDecidableError",
    "PhotoNotRetryableError",
    "PhotoStatus",
    "PhotoStorage",
    "PlatformSettings",
    "PoolEmptyError",
    "PoolFullError",
    "PoolStatus",
    "RecordedCost",
    "RecordingNotifier",
    "ReferenceImageError",
    "ReferenceNotFoundError",
    "ReferencePair",
    "ReferenceStorageNotConfigured",
    "RepositoryError",
    "Room",
    "RuleArchivedError",
    "RuleDecisionForbiddenError",
    "RuleNotFoundError",
    "RuleStatus",
    "STAGING_SUFFIX",
    "Speed",
    "StructuredLlm",
    "StructuredResult",
    "StyleGuide",
    "SubmissionError",
    "SupabasePhotoEditingRepository",
    "TokenUsage",
    "UnpricedModelError",
    "activate_version",
    "add_photo_bytes",
    "add_reference_pair",
    "archive_reference_pair",
    "backfill_fx",
    "build_batch_zip",
    "build_cost_row",
    "build_dataset_record",
    "build_handlers",
    "build_worker",
    "build_zip",
    "can_decide_rule",
    "can_manage_rule",
    "catalog_capabilities",
    "compose_effective_guide",
    "compute_capabilities",
    "create_draft",
    "create_manual_rule",
    "decide_rule",
    "edit_rule_text",
    "enqueue_fx_backfill",
    "enqueue_openai_batch_poll",
    "enqueue_openai_batch_submit",
    "generate_draft_from_pool",
    "handle_avaliar",
    "handle_edit",
    "handle_fx_backfill",
    "handle_ingest",
    "handle_lote_pronto",
    "handle_poll_openai_batch",
    "handle_propor_regras",
    "handle_regen_guia",
    "handle_submit_lote",
    "handle_submit_openai_batch",
    "is_retryable",
    "make_photo_editing_repository",
    "openai_image_edit_factory",
    "plan_zip",
    "pool_status",
    "price_usage_usd",
    "propose_rules",
    "record_ai_cost",
    "record_decision",
    "request_guide_regen",
    "request_rule_proposal",
    "resolve_effective_guide",
    "restore_version",
    "retry_photo",
    "schedule_guide_regen",
    "schedule_rule_proposal",
    "storage_path",
    "submit_batch",
    "validate_submission",
    "zip_entry_name",
    "zip_file_name",
    # W8 — model catalog steps, daily notes, processing gate
    "ModelNote",
    "NoteWriterOutputError",
    "NotesReport",
    "ProcessingGate",
    "STEP_KIND",
    "Step",
    "StepModelError",
    "StepModelView",
    "enqueue_model_notes",
    "handle_notas_modelos",
    "resolve_rule_proposer_tunables",
    "resolve_step_model",
    "step_models_view",
    "validate_step_model",
    "write_model_notes",
]
