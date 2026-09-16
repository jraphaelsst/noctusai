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

**Not in R1 (C8):** the Econômico / Batch-API path (``em_lote_openai``,
``fotos.poll_openai_batch``). ``submit_batch`` refuses Econômico with
``economico_indisponivel``.
"""

from noctusai_lib.domain.photo_editing.access import compute_capabilities
from noctusai_lib.domain.photo_editing.costs import (
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
    build_handlers,
    build_worker,
    handle_avaliar,
    handle_edit,
    handle_fx_backfill,
    handle_ingest,
    handle_lote_pronto,
    handle_propor_regras,
    handle_regen_guia,
    handle_submit_lote,
    is_retryable,
)
from noctusai_lib.domain.photo_editing.learning import (
    Actor,
    InvalidModelOutputError,
    RuleDecisionForbiddenError,
    RuleNotFoundError,
    decide_rule,
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
    SubmissionError,
    add_photo_bytes,
    enqueue_fx_backfill,
    retry_photo,
    schedule_guide_regen,
    schedule_rule_proposal,
    submit_batch,
    validate_submission,
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
    openai_image_edit_factory,
)
from noctusai_lib.domain.photo_editing.repository import (
    InMemoryPhotoEditingRepository,
    PhotoEditingRepository,
    RepositoryError,
    SupabasePhotoEditingRepository,
    make_photo_editing_repository,
)
from noctusai_lib.domain.photo_editing.types import (
    Batch,
    BatchStatus,
    Decision,
    EditType,
    JobType,
    OrgSettings,
    Photo,
    PhotoStatus,
    RuleStatus,
    Speed,
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
    "ECONOMICO_IMPLEMENTED",
    "EditQuotaExceededError",
    "EditType",
    "FakeStructuredLlm",
    "GuideNotActiveError",
    "GuideVersionNotFoundError",
    "HANDLERS",
    "InMemoryPhotoEditingRepository",
    "InMemoryPhotoStorage",
    "InvalidModelOutputError",
    "JobType",
    "LlmStructuredAdapter",
    "NotFoundError",
    "NothingApprovedError",
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
    "RecordedCost",
    "RecordingNotifier",
    "RepositoryError",
    "RuleDecisionForbiddenError",
    "RuleNotFoundError",
    "RuleStatus",
    "STAGING_SUFFIX",
    "Speed",
    "StructuredLlm",
    "StructuredResult",
    "SubmissionError",
    "SupabasePhotoEditingRepository",
    "TokenUsage",
    "UnpricedModelError",
    "activate_version",
    "add_photo_bytes",
    "backfill_fx",
    "build_batch_zip",
    "build_cost_row",
    "build_dataset_record",
    "build_handlers",
    "build_worker",
    "build_zip",
    "compose_effective_guide",
    "compute_capabilities",
    "create_draft",
    "decide_rule",
    "enqueue_fx_backfill",
    "generate_draft_from_pool",
    "handle_avaliar",
    "handle_edit",
    "handle_fx_backfill",
    "handle_ingest",
    "handle_lote_pronto",
    "handle_propor_regras",
    "handle_regen_guia",
    "handle_submit_lote",
    "is_retryable",
    "make_photo_editing_repository",
    "openai_image_edit_factory",
    "plan_zip",
    "price_usage_usd",
    "propose_rules",
    "record_ai_cost",
    "record_decision",
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
]
