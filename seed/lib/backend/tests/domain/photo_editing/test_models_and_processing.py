"""W8 — per-step models, daily model notes, the processing gate, and the
catalog overlay reaching submission + capabilities.

DI only: ports are the in-memory set from ``conftest``; the catalog overlay
is set/cleared through its public API.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from noctusai_lib.domain.jobs import DeadLetterError
from noctusai_lib.domain.permissions import FakePermissionGrantRepository
from noctusai_lib.domain.photo_editing import (
    Actor,
    JobType,
    ProcessingGate,
    Speed,
    Step,
    StepModelError,
    SubmissionError,
    add_photo_bytes,
    build_worker,
    compute_capabilities,
    enqueue_model_notes,
    resolve_step_model,
    step_models_view,
    validate_step_model,
    validate_submission,
    write_model_notes,
)
from noctusai_lib.domain.photo_editing.costs import UnpricedModelError
from noctusai_lib.integrations.llm import (
    ModelOverride,
    base_models_for,
    clear_model_overrides,
    set_model_overrides,
)

from .conftest import EDIT_MODEL, ORG, T0, USER, activate_guide, run


@pytest.fixture(autouse=True)
def _clean_overlay():
    clear_model_overrides()
    yield
    clear_model_overrides()


def _static(model_id: str):
    return next(m for m in base_models_for("openai", "image_edit") if m.id == model_id)


# --- step models --------------------------------------------------------


def test_step_models_default_to_the_config_and_follow_the_setting(ports) -> None:
    async def scenario() -> None:
        assert await resolve_step_model(ports, Step.AVALIADOR) == "gpt-5.6-terra"
        await ports.repo.update_platform_settings(modelo_avaliador="gpt-6-astra")
        assert await resolve_step_model(ports, Step.AVALIADOR) == "gpt-6-astra"
        view = {v.step: v for v in step_models_view(await ports.repo.get_platform_settings(), ports.config)}
        assert view[Step.AVALIADOR].personalizado is True
        assert view[Step.AVALIADOR].padrao == "gpt-5.6-terra"
        assert view[Step.NOTAS].modelo == "gpt-5.6-luna" and not view[Step.NOTAS].personalizado

    run(scenario())


def test_evaluator_uses_the_configured_step_model(ports) -> None:
    async def scenario() -> None:
        await activate_guide(ports)
        await ports.repo.update_platform_settings(modelo_avaliador="gpt-6-astra")
        from noctusai_lib.domain.photo_editing import submit_batch

        batch = await ports.repo.create_batch(
            org_id=ORG, nome="n", criado_por=USER, origem="upload", velocidade=Speed.URGENTE
        )
        await add_photo_bytes(ports, lote_id=batch.id, data=b"\xff\xd8x", extension="jpg")
        await submit_batch(ports, batch.id, submitted_by=USER)
        worker = build_worker(ports, worker_id="w")
        while await worker.run_once():
            pass
        models = {c["model"] for c in ports.llm.calls if c["schema_name"] == "avaliacao_foto"}
        assert models == {"gpt-6-astra"}
        [evaluation] = ports.repo.evaluations
        assert evaluation.modelo_id == "gpt-6-astra"

    run(scenario())


def test_validate_step_model_refuses_wrong_kind_and_unpriced(ports) -> None:
    validate_step_model(ports.config, Step.REGRAS, "gpt-5.6-sol")
    with pytest.raises(StepModelError) as wrong_kind:
        validate_step_model(ports.config, Step.AVALIADOR, "text-embedding-3-small")
    assert wrong_kind.value.code == "modelo_desconhecido"
    with pytest.raises(StepModelError) as unpriced:
        validate_step_model(ports.config, Step.NOTAS, "whisper-1")
    assert unpriced.value.code == "modelo_desconhecido"  # audio is not a chat model
    set_model_overrides([
        ModelOverride(provider="openai", kind="chat", model_id="gpt-x", cost_per_1m_input_tokens=1.0)
    ])
    with pytest.raises(StepModelError) as gap:
        validate_step_model(ports.config, Step.NOTAS, "gpt-x")
    assert gap.value.code == "modelo_sem_preco"


# --- daily notes --------------------------------------------------------


async def _decided_photo(ports, *, decisao: str = "aprovar") -> None:
    """One edited + evaluated + decided photo for EDIT_MODEL."""
    from noctusai_lib.domain.photo_editing import Decision, EditType

    repo = ports.repo
    batch = await repo.create_batch(
        org_id=ORG, nome="n", criado_por=USER, origem="upload", velocidade=Speed.URGENTE
    )
    photo = await repo.add_photo(org_id=ORG, lote_id=batch.id, ordem=1, storage_path_original="x")
    edit = await repo.create_edit(
        org_id=ORG, lote_id=batch.id, foto_id=photo.id, tentativa=1,
        tipos_edicao=(EditType.COR_LUZ,), modelo_id=EDIT_MODEL, velocidade=Speed.URGENTE,
    )
    await repo.add_evaluation(
        org_id=ORG, lote_id=batch.id, foto_id=photo.id, edicao_id=edit.id,
        recomendacao=Decision.APROVAR, score=Decimal("8"), motivo="ok", modelo_id="gpt-5.6-terra",
        modelo_versao=None,
    )
    await repo.add_decision(
        org_id=ORG, lote_id=batch.id, foto_id=photo.id, decisao=Decision(decisao),
        decidido_por=USER, comentario=None if decisao == "aprovar" else "ruim",
    )


def test_notes_skip_models_without_data_and_store_the_basis(ports) -> None:
    ports.llm.responses["nota_modelo"] = {"nota": "  Boa taxa de aprovação.  "}

    async def scenario() -> None:
        await _decided_photo(ports)
        report = await write_model_notes(ports)
        assert report.written == (EDIT_MODEL,)
        assert "gpt-image-2.5-flare" in report.skipped_no_data
        assert report.writer_model == "gpt-5.6-luna"
        [note] = ports.repo.model_notes
        assert note.texto == "Boa taxa de aprovação."
        assert note.dados_base["total_fotos"] == 1
        assert note.dados_base["taxa_aprovacao"] == "1"
        assert note.dados_base["prompt"] == "fotos.nota_modelo@v1"
        call = next(c for c in ports.llm.calls if c["schema_name"] == "nota_modelo")
        assert call["org_id"] is None and call["model"] == "gpt-5.6-luna"

    run(scenario())


def test_notes_since_is_idempotent_for_a_retried_slot(ports, clock) -> None:
    ports.llm.responses["nota_modelo"] = {"nota": "x"}

    async def scenario() -> None:
        await _decided_photo(ports)
        slot = clock.now
        first = await write_model_notes(ports, since=slot)
        clock.advance(minutes=5)
        second = await write_model_notes(ports, since=slot)
        assert first.written == (EDIT_MODEL,)
        assert second.written == () and second.skipped_recent == (EDIT_MODEL,)
        assert len(ports.repo.model_notes) == 1

    run(scenario())


def test_notes_refuse_an_unpriced_writer_before_any_call(ports) -> None:
    async def scenario() -> None:
        await _decided_photo(ports)
        await ports.repo.update_platform_settings(modelo_notas="modelo-inexistente")
        with pytest.raises(UnpricedModelError):
            await write_model_notes(ports)
        assert not ports.llm.calls

    run(scenario())


def test_notes_handler_runs_through_the_worker_and_dedupes_the_slot(ports, clock) -> None:
    ports.llm.responses["nota_modelo"] = {"nota": "ok"}

    async def scenario() -> None:
        await _decided_photo(ports)
        a = await enqueue_model_notes(ports, slot=clock.now)
        b = await enqueue_model_notes(ports, slot=clock.now + timedelta(minutes=30))
        assert a.id == b.id  # same São Paulo day ⇒ one job
        assert a.type == JobType.NOTAS_MODELOS
        manual = await enqueue_model_notes(ports)
        assert manual.id != a.id and manual.payload == {"manual": True}
        worker = build_worker(ports, worker_id="w")
        while await worker.run_once():
            pass
        # scheduled run wrote; the manual run (no `desde`) rewrote.
        assert len(ports.repo.model_notes) == 2

    run(scenario())


def test_notes_handler_dead_letters_a_malformed_slot(ports) -> None:
    from noctusai_lib.domain.jobs import Job, JobStatus
    from noctusai_lib.domain.photo_editing import handle_notas_modelos

    job = Job(
        id="j", type=JobType.NOTAS_MODELOS, payload={"desde": "2026-09-16T00:05:00"},
        status=JobStatus.RUNNING, retry_count=0, max_retries=1, last_error=None,
        created_at=T0, updated_at=T0,
    )
    with pytest.raises(DeadLetterError, match="timezone"):
        run(handle_notas_modelos(ports, job))


def test_enqueue_model_notes_requires_an_aware_slot(ports) -> None:
    with pytest.raises(ValueError):
        run(enqueue_model_notes(ports, slot=T0.replace(tzinfo=None)))


# --- processing gate ----------------------------------------------------


class _Tick:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_processing_gate_pauses_and_resumes_a_live_worker(ports) -> None:
    tick = _Tick()
    gate = ProcessingGate(ports, ttl_seconds=10, monotonic=tick)

    async def scenario() -> None:
        await activate_guide(ports)
        batch = await ports.repo.create_batch(
            org_id=ORG, nome="n", criado_por=USER, origem="upload", velocidade=Speed.URGENTE
        )
        await add_photo_bytes(ports, lote_id=batch.id, data=b"\xff\xd8x", extension="jpg")
        worker = build_worker(ports, worker_id="w", claim_gate=gate)
        assert (await ports.repo.get_platform_settings()).processamento_ativo is False
        assert await worker.run_once() is False  # paused by default
        stats = await ports.jobs.queue_stats()
        assert stats.due == 1
        await ports.repo.update_platform_settings(processamento_ativo=True)
        assert await worker.run_once() is False  # cached answer, within TTL
        tick.t = 11
        assert await worker.run_once() is True  # TTL elapsed ⇒ re-read ⇒ open
        await ports.repo.update_platform_settings(processamento_ativo=False)
        gate.invalidate()
        assert await worker.run_once() is False

    run(scenario())


def test_a_failing_gate_is_closed(ports) -> None:
    class _BrokenRepo:
        async def get_platform_settings(self):
            raise ConnectionError("db down")

    class _Ports:
        repo = _BrokenRepo()

    gate = ProcessingGate(_Ports())

    async def scenario() -> None:
        worker = build_worker(ports, worker_id="w", claim_gate=gate)
        assert await worker.claim_allowed() is False
        assert "ConnectionError" in (worker.last_gate_error or "")

    run(scenario())


# --- overlay reaching submission + capabilities -------------------------


def test_submission_refuses_a_disabled_or_unpriced_model(ports) -> None:
    async def scenario() -> None:
        batch = await ports.repo.create_batch(
            org_id=ORG, nome="n", criado_por=USER, origem="upload", velocidade=Speed.URGENTE
        )
        await add_photo_bytes(ports, lote_id=batch.id, data=b"\xff\xd8x", extension="jpg")
        set_model_overrides([ModelOverride.from_entry(_static(EDIT_MODEL), enabled=False)])
        with pytest.raises(SubmissionError) as off:
            await validate_submission(ports, batch)
        assert off.value.code == "modelo_desconhecido"
        set_model_overrides([
            ModelOverride.from_entry(_static(EDIT_MODEL), cost_per_1m_image_output_tokens=None)
        ])
        with pytest.raises(SubmissionError) as gap:
            await validate_submission(ports, batch)
        assert gap.value.code == "modelo_sem_preco"
        clear_model_overrides()
        plan = await validate_submission(ports, batch)
        assert plan.model_id == EDIT_MODEL

    run(scenario())


def test_capabilities_report_why_the_model_is_blocked(ports) -> None:
    grants = FakePermissionGrantRepository([])
    admin = Actor(user_id=USER, org_id=ORG, org_role="owner", is_platform_admin=True)

    async def caps():
        return await compute_capabilities(
            actor=admin, settings=await ports.repo.get_org_settings(ORG), grants=grants
        )

    async def scenario() -> None:
        ok = await caps()
        assert ok["modelo_configurado"] is True and ok["modelo_bloqueado_motivo"] is None
        assert ok["pode_administrar_plataforma"] is True
        set_model_overrides([
            ModelOverride.from_entry(_static(EDIT_MODEL), cost_per_1m_image_input_tokens=None)
        ])
        gap = await caps()
        assert gap["modelo_bloqueado_motivo"] == "modelo_sem_preco"
        assert gap["pode_criar_lote"] is False and gap["modelo_configurado"] is False
        set_model_overrides([ModelOverride.from_entry(_static(EDIT_MODEL), enabled=False)])
        assert (await caps())["modelo_bloqueado_motivo"] == "modelo_desativado"
        # A batch-capable, priced override unlocks Econômico through the
        # default capabilities port (W4's single gate) — no parallel gate.
        set_model_overrides([ModelOverride.from_entry(_static(EDIT_MODEL), supports_batch=True)])
        econ = await caps()
        assert econ["economico_disponivel"] is True
        assert econ["economico_bloqueado_motivo"] is None

    run(scenario())


def test_repository_metrics_mirror_the_rpc(ports) -> None:
    async def scenario() -> None:
        await _decided_photo(ports, decisao="aprovar")
        await _decided_photo(ports, decisao="rejeitar")
        m = await ports.repo.model_metrics(EDIT_MODEL)
        assert m.total_fotos == 2
        assert m.taxa_aprovacao == Decimal("0.5")
        assert m.score_medio == Decimal("8")
        assert m.custo_por_foto_aprovada_usd == Decimal(0)  # no linked llm_usage
        empty = await ports.repo.model_metrics("gpt-image-2.5-flare")
        assert empty.total_fotos == 0

    run(scenario())


def test_supabase_repository_metrics_and_notes_use_the_real_shapes() -> None:
    from noctusai_lib.domain.photo_editing import SupabasePhotoEditingRepository

    from .test_repository import SchemaStableClient

    async def scenario() -> None:
        client = SchemaStableClient()
        client.schema("social_wiring").set_rpc_data(
            "fotos_modelo_metricas",
            [{"total_fotos": 4, "taxa_aprovacao": "0.75", "score_medio": "7.5",
              "custo_por_foto_aprovada_usd": "0.041"}],
        )
        repo = SupabasePhotoEditingRepository(client)
        m = await repo.model_metrics(EDIT_MODEL)
        assert (m.total_fotos, m.taxa_aprovacao, m.custo_por_foto_aprovada_usd) == (
            4, Decimal("0.75"), Decimal("0.041")
        )
        note = await repo.add_model_note(
            modelo_id=EDIT_MODEL, texto="ok", dados_base={"total_fotos": 4, "x": Decimal("1.5")}
        )
        assert note.modelo_id == EDIT_MODEL and note.dados_base["x"] == "1.5"
        latest = await repo.latest_model_notes([EDIT_MODEL, "outro"])
        assert set(latest) == {EDIT_MODEL}

    run(scenario())


def test_platform_settings_accept_the_w8_fields(ports) -> None:
    async def scenario() -> None:
        s = await ports.repo.update_platform_settings(
            modelo_guia="gpt-6-astra", modelo_regras="gpt-5.6-terra",
            modelo_notas="gpt-5.6-sol", processamento_ativo=True,
        )
        assert (s.modelo_guia, s.processamento_ativo) == ("gpt-6-astra", True)

    run(scenario())


def test_rule_proposer_tunables_follow_platform_settings(ports, clock) -> None:
    from noctusai_lib.domain.photo_editing import resolve_rule_proposer_tunables
    from noctusai_lib.domain.photo_editing.pipeline import schedule_rule_proposal

    async def scenario() -> None:
        assert await resolve_rule_proposer_tunables(ports) == (1800, 50)
        await ports.repo.update_platform_settings(
            rule_proposal_debounce_seconds=120, max_rejections_per_proposal=3
        )
        assert await resolve_rule_proposer_tunables(ports) == (120, 3)
        job = await schedule_rule_proposal(ports, ORG)
        assert job.scheduled_for is not None
        assert (job.scheduled_for - clock.now).total_seconds() <= 120
        # The proposer reads at most the configured number of rejections.
        for _ in range(5):
            await _decided_photo(ports, decisao="rejeitar")
        ports.llm.responses["propor_regras"] = {"regras": []}
        from noctusai_lib.domain.photo_editing.learning import propose_rules

        await propose_rules(ports, ORG)
        call = next(c for c in ports.llm.calls if c["schema_name"] == "propor_regras")
        assert call["prompt"].count("ruim") == 3

    run(scenario())
