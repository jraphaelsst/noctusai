"""W8 — model catalog admin, per-step models, notes trigger, processing
control + health, and the scheduler entry points.

Every edge goes through the module's DI seams (`app.dependency_overrides`
or kwarg seams on the scheduler); the catalog overlay is process-global and
is cleared through its public API around every test. Strict 401s and the
403 role matrix for these routes live in `test_edicao_fotos_auth_boundary.py`.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from noctusai_lib.domain.photo_editing import JobType
from noctusai_lib.integrations.image_edit import capabilities_for_model
from noctusai_lib.integrations.llm import (
    FakeCreditProbe,
    InMemoryModelCatalogStore,
    clear_model_overrides,
)

from app.modules.edicao_fotos.deps import (
    get_catalog_store,
    get_credit_probe,
    get_platform_openai_key,
    get_worker_control,
)
from app.modules.edicao_fotos.routers.processamento import ProbeMemory, get_probe_memory
from app.modules.edicao_fotos.services import scheduler as fotos_scheduler
from app.modules.edicao_fotos.services import worker as worker_service

from .conftest import EDIT_MODEL, USERS

BASE = "/api/edicao-fotos"
GPT_IMAGE_2 = {
    "kind": "image_edit",
    "nome": "GPT Image 2",
    "snapshot": None,
    "habilitado": True,
    "preco_entrada_texto_1m": "5",
    "preco_saida_texto_1m": None,
    "preco_entrada_imagem_1m": "10",
    "preco_saida_imagem_1m": "40",
    "suporta_batch": True,
    "tag_performance": "economico",
}


class FakeControl:
    """`get_worker_control` double: the real status shape, recorded gate
    invalidations, and the real catalog refresh."""

    def __init__(self) -> None:
        self.invalidations = 0
        self.refresh_catalog = worker_service.refresh_catalog

    def status(self) -> worker_service.WorkerStatus:
        return worker_service.WorkerStatus(
            rodando=True, worker_id="sw-edicao-fotos-test", iniciado_em=datetime(2026, 9, 16, tzinfo=timezone.utc)
        )

    def invalidate_gate(self) -> None:
        self.invalidations += 1


@pytest.fixture
def w8(edicao):
    clear_model_overrides()
    store = InMemoryModelCatalogStore()
    probe = FakeCreditProbe("sem_credito")
    control = FakeControl()
    memory = ProbeMemory()
    key = {"value": "sk-plataforma"}
    overrides = {
        get_catalog_store: lambda: store,
        get_credit_probe: lambda: probe,
        get_worker_control: lambda: control,
        get_probe_memory: lambda: memory,
        get_platform_openai_key: lambda: (lambda: key["value"]),
    }
    app = edicao.app
    previous = {k: app.dependency_overrides.get(k) for k in overrides}
    app.dependency_overrides.update(overrides)
    yield SimpleNamespace(h=edicao, store=store, probe=probe, control=control, key=key)
    for k, prev in previous.items():
        if prev is None:
            app.dependency_overrides.pop(k, None)
        else:
            app.dependency_overrides[k] = prev
    clear_model_overrides()


# --- catalog -------------------------------------------------------------------


def test_admin_catalog_lists_static_rows_with_prices(w8) -> None:
    resp = w8.h.as_user("plataforma").http.get(f"{BASE}/modelos/catalogo")
    assert resp.status_code == 200, resp.text
    rows = {(r["kind"], r["id"]): r for r in resp.json()["items"]}
    sunburst = rows[("image_edit", EDIT_MODEL)]
    assert sunburst["origem"] == "catalogo" and sunburst["habilitado"] is True
    assert sunburst["precos"] == {
        "entrada_texto": 5.0, "saida_texto": None, "entrada_imagem": 8.0, "saida_imagem": 30.0,
    }
    assert sunburst["com_preco"] is True and sunburst["revisao"] is None
    assert ("vision", "gpt-5.6-terra") in rows and ("chat", "gpt-5.6-luna") in rows


def test_owner_enters_gpt_image_2_pricing_and_batch_flag(w8) -> None:
    """C8: the platform admin adds the missing model in the UI."""
    http = w8.h.as_user("plataforma").http
    resp = http.put(f"{BASE}/modelos/catalogo/gpt-image-2", json=GPT_IMAGE_2)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["origem"] == "adicionado" and body["revisao"] == 1 and body["recarregado"] is True
    assert body["atualizado_por"] == USERS["plataforma"].id
    caps = capabilities_for_model("gpt-image-2")
    assert (caps.known, caps.supports_batch, caps.priced) == (True, True, True)
    catalog = http.get(f"{BASE}/modelos").json()
    added = next(m for m in catalog if m["id"] == "gpt-image-2")
    assert added["suporta_batch"] is True and added["tag_performance"] == "economico"
    # An org admin can now select it, and Econômico (W4) unlocks through
    # the one capabilities port — no parallel gate.
    w8.h.configure_org(modelo_editor_id="gpt-image-2")
    capacidades = w8.h.as_user("admin").http.get(f"{BASE}/capacidades").json()
    assert capacidades["modelo_configurado"] is True
    assert capacidades["economico_disponivel"] is True
    assert capacidades["economico_bloqueado_motivo"] is None


def test_every_save_is_a_version(w8) -> None:
    http = w8.h.as_user("plataforma").http
    http.put(f"{BASE}/modelos/catalogo/gpt-image-2", json=GPT_IMAGE_2)
    http.put(f"{BASE}/modelos/catalogo/gpt-image-2", json={**GPT_IMAGE_2, "preco_saida_imagem_1m": "45"})
    versions = http.get(f"{BASE}/modelos/catalogo/gpt-image-2/versoes", params={"kind": "image_edit"}).json()
    assert [v["revisao"] for v in versions["items"]] == [2, 1]
    assert [v["precos"]["saida_imagem"] for v in versions["items"]] == [45.0, 40.0]
    bad_kind = http.get(f"{BASE}/modelos/catalogo/gpt-image-2/versoes", params={"kind": "audio"})
    assert bad_kind.status_code == 422 and bad_kind.json()["code"] == "tipo_invalido"


def test_unpriced_model_is_refused_at_selection(w8) -> None:
    http = w8.h.as_user("plataforma").http
    http.put(f"{BASE}/modelos/catalogo/gpt-image-2", json={**GPT_IMAGE_2, "preco_saida_imagem_1m": None})
    listed = next(r for r in http.get(f"{BASE}/modelos/catalogo").json()["items"] if r["id"] == "gpt-image-2")
    assert listed["com_preco"] is False
    w8.h.configure_org()
    put = w8.h.as_user("admin").http.put(
        f"{BASE}/configuracoes",
        json={"tipos_edicao_ativos": ["cor_luz"], "modelo_editor_imagem": "gpt-image-2"},
    )
    assert put.status_code == 422 and put.json()["code"] == "modelo_sem_preco"


def test_disabling_a_model_hides_it_and_blocks_its_orgs(w8) -> None:
    w8.h.configure_org()
    http = w8.h.as_user("plataforma").http
    static = next(
        r for r in http.get(f"{BASE}/modelos/catalogo").json()["items"] if r["id"] == EDIT_MODEL
    )
    body = {
        "kind": "image_edit", "nome": static["nome"], "snapshot": static["snapshot"], "habilitado": False,
        "preco_entrada_texto_1m": "5", "preco_saida_texto_1m": None,
        "preco_entrada_imagem_1m": "8", "preco_saida_imagem_1m": "30",
        "suporta_batch": False, "tag_performance": "performance",
    }
    resp = http.put(f"{BASE}/modelos/catalogo/{EDIT_MODEL}", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["habilitado"] is False and resp.json()["origem"] == "personalizado"
    assert EDIT_MODEL not in {m["id"] for m in http.get(f"{BASE}/modelos").json()}
    caps = w8.h.as_user("corretor").http.get(f"{BASE}/capacidades").json()
    assert caps["pode_criar_lote"] is False
    assert caps["modelo_bloqueado_motivo"] == "modelo_desativado"


def test_a_step_model_cannot_be_disabled_while_in_use(w8) -> None:
    http = w8.h.as_user("plataforma").http
    resp = http.put(
        f"{BASE}/modelos/catalogo/gpt-5.6-terra",
        json={"kind": "vision", "habilitado": False, "preco_entrada_texto_1m": "2", "preco_saida_texto_1m": "12"},
    )
    assert resp.status_code == 409 and resp.json()["code"] == "modelo_em_uso"


def test_catalog_put_validates_the_id_and_body(w8) -> None:
    http = w8.h.as_user("plataforma").http
    assert http.put(f"{BASE}/modelos/catalogo/Bad Id", json=GPT_IMAGE_2).json()["code"] == "modelo_id_invalido"
    negative = http.put(f"{BASE}/modelos/catalogo/gpt-image-2", json={**GPT_IMAGE_2, "preco_saida_imagem_1m": "-1"})
    assert negative.status_code == 422
    extra = http.put(f"{BASE}/modelos/catalogo/gpt-image-2", json={**GPT_IMAGE_2, "provider": "x"})
    assert extra.status_code == 422


# --- metrics + notes -----------------------------------------------------------


def test_member_catalog_hides_metrics_from_corretores(w8) -> None:
    corretor = w8.h.as_user("corretor").http.get(f"{BASE}/modelos").json()
    assert all(m["metricas"] is None and m["nota_recomendacao"] is None for m in corretor)
    admin = w8.h.as_user("admin").http.get(f"{BASE}/modelos").json()
    sunburst = next(m for m in admin if m["id"] == EDIT_MODEL)
    assert sunburst["metricas"] == {
        "total_fotos": 0, "taxa_aprovacao": None, "score_medio_ia": None, "custo_por_foto_aprovada": None,
    }


def test_live_metrics_and_the_latest_note(w8) -> None:
    h = w8.h
    h.ports.llm.responses["nota_modelo"] = {"nota": "Sunburst: boa aprovação."}
    h.configure_org()
    h.activate_guide()
    lote = h.make_batch("corretor")
    h.add_photo(lote)
    h.as_user("corretor").http.post(f"{BASE}/lotes/{lote}/submeter", json={})
    h.drain()
    foto = h.http.get(f"{BASE}/revisao/{lote}").json()[0]["id"]
    h.http.post(f"{BASE}/revisao/{lote}/fotos/{foto}/decisao", json={"decisao": "aprovar"})

    queued = h.as_user("plataforma").http.post(f"{BASE}/modelos/notas/gerar")
    assert queued.status_code == 202, queued.text
    h.drain()
    item = next(m for m in h.as_user("admin").http.get(f"{BASE}/modelos").json() if m["id"] == EDIT_MODEL)
    assert item["metricas"]["total_fotos"] == 1
    assert item["metricas"]["taxa_aprovacao"] == 1.0
    assert item["metricas"]["score_medio_ia"] == 8.5
    assert item["nota_recomendacao"] == "Sunburst: boa aprovação."
    assert item["nota_gerada_em"] is not None


# --- per-step models -----------------------------------------------------------


def test_step_models_round_trip_and_validation(w8) -> None:
    http = w8.h.as_user("plataforma").http
    etapas = {e["etapa"]: e for e in http.get(f"{BASE}/modelos/etapas").json()["etapas"]}
    assert set(etapas) == {"guia", "avaliador", "regras", "notas"}
    assert etapas["avaliador"]["modelo"] == "gpt-5.6-terra" and not etapas["avaliador"]["personalizado"]
    put = http.put(f"{BASE}/modelos/etapas", json={"avaliador": "gpt-6-astra"})
    assert put.status_code == 200, put.text
    etapas = {e["etapa"]: e for e in put.json()["etapas"]}
    assert etapas["avaliador"]["modelo"] == "gpt-6-astra" and etapas["avaliador"]["personalizado"]
    assert etapas["regras"]["personalizado"] is False  # untouched key left alone
    wrong = http.put(f"{BASE}/modelos/etapas", json={"regras": EDIT_MODEL})
    assert wrong.status_code == 422 and wrong.json()["code"] == "modelo_desconhecido"
    reset = http.put(f"{BASE}/modelos/etapas", json={"avaliador": None})
    assert {e["etapa"]: e for e in reset.json()["etapas"]}["avaliador"]["personalizado"] is False


# --- processing ----------------------------------------------------------------


def test_processing_panel_defaults_to_paused(w8) -> None:
    resp = w8.h.as_user("plataforma").http.get(f"{BASE}/processamento")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ativo"] is False
    assert body["worker"]["rodando"] is True and body["worker"]["pausado"] is True
    assert body["worker"]["escopo"] == "este_processo"
    assert body["fila"]["pendentes"] == 0 and body["ultimo_erro"] is None
    assert body["sem_creditos"] is False and body["sonda"] is None


def test_toggle_pauses_and_resumes_live(w8) -> None:
    http = w8.h.as_user("plataforma").http
    on = http.put(f"{BASE}/processamento", json={"ativo": True})
    assert on.status_code == 200 and on.json()["ativo"] is True and on.json()["worker"]["pausado"] is False
    assert w8.control.invalidations == 1
    off = http.put(f"{BASE}/processamento", json={"ativo": False})
    assert off.json()["ativo"] is False and w8.control.invalidations == 2
    assert http.put(f"{BASE}/processamento", json={}).status_code == 422


def test_queue_depth_dead_jobs_and_no_credit_error_surface(w8) -> None:
    h = w8.h
    h.configure_org()
    h.activate_guide()
    lote = h.make_batch("corretor")
    h.add_photo(lote)

    async def kill_one() -> None:
        job = await h.ports.jobs.claim_next(worker_id="w-test", job_types=list(JobType.ALL))
        await h.ports.jobs.mark_failed(
            job.id, "Error code: 429 - {'error': {'code': 'insufficient_quota'}}", dead_letter=True
        )
        await h.ports.jobs.enqueue(type=JobType.EDIT, payload={"foto_id": "x"})

    asyncio.run(kill_one())
    body = h.as_user("plataforma").http.get(f"{BASE}/processamento").json()
    assert body["fila"]["mortos"] == 1 and body["fila"]["pendentes"] == 1
    assert body["ultimo_erro"]["tipo_job"] == JobType.INGEST
    assert body["sem_creditos"] is True


def test_probe_reports_no_credit_clearly(w8) -> None:
    http = w8.h.as_user("plataforma").http
    resp = http.post(f"{BASE}/processamento/sonda")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sem_credito"
    assert "Sem créditos" in resp.json()["mensagem"]
    assert w8.probe.calls == ["sk-plataforma"]
    panel = http.get(f"{BASE}/processamento").json()
    assert panel["sonda"]["status"] == "sem_credito" and panel["sem_creditos"] is True
    w8.key["value"] = None
    assert http.post(f"{BASE}/processamento/sonda").json()["status"] == "sem_chave"


# --- worker lifecycle ----------------------------------------------------------


def test_worker_starts_paused_and_stops(edicao) -> None:
    cfg = SimpleNamespace(
        edicao_fotos_worker_enabled=True,
        edicao_fotos_worker_poll_seconds=0.01,
        edicao_fotos_gate_ttl_seconds=0.0,
        edicao_fotos_catalog_refresh_seconds=0.01,
    )
    store = InMemoryModelCatalogStore()
    edicao.configure_org()
    edicao.add_photo(edicao.make_batch("corretor"))

    async def scenario() -> None:
        started = await worker_service.start_worker(
            cfg, ports_factory=lambda _cfg: edicao.ports, store_factory=lambda: store
        )
        try:
            assert started is True and worker_service.is_running()
            status = worker_service.status()
            assert status.rodando and status.catalogo_atualizado_em is not None
            await asyncio.sleep(0.05)
            # Paused by default: the queued ingest job is still waiting.
            assert (await edicao.ports.jobs.queue_stats()).pending == 1
        finally:
            await worker_service.stop_worker()
        assert worker_service.is_running() is False
        assert worker_service.status().rodando is False

    asyncio.run(scenario())


def test_worker_not_started_when_the_process_cannot_build_the_engine() -> None:
    from app.modules.edicao_fotos.services.ports import EdicaoFotosUnavailable

    def unavailable(_cfg):
        raise EdicaoFotosUnavailable("Edição de Fotos requer o Supabase.")

    cfg = SimpleNamespace(edicao_fotos_worker_enabled=True)
    assert asyncio.run(worker_service.start_worker(cfg, ports_factory=unavailable)) is False
    assert worker_service.status().motivo_parado == "Edição de Fotos requer o Supabase."


# --- scheduler -----------------------------------------------------------------


@contextlib.contextmanager
def _lease(granted: bool):
    calls: list[str] = []

    @contextlib.contextmanager
    def lease(_admin, name, *, ttl_seconds):
        calls.append(name)
        yield granted

    yield lease, calls


def test_last_expected_slot() -> None:
    before = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)  # 00:00 in São Paulo
    after = datetime(2026, 9, 16, 3, 10, tzinfo=timezone.utc)  # 00:10
    assert fotos_scheduler.last_expected_slot(before).date().isoformat() == "2026-09-15"
    assert fotos_scheduler.last_expected_slot(after).isoformat() == "2026-09-16T00:05:00-03:00"


def test_daily_notes_job_enqueues_one_job_per_slot(edicao) -> None:
    now = datetime(2026, 9, 16, 3, 10, tzinfo=timezone.utc)
    with _lease(True) as (lease, calls):
        seams = dict(ports_factory=lambda _s: edicao.ports, admin_factory=lambda: object(), lease_fn=lease)
        first = asyncio.run(fotos_scheduler.daily_notes_job(now=now, **seams))
        again = asyncio.run(fotos_scheduler.daily_notes_job(now=now, **seams))
    assert first is not None and first == again
    assert calls == [fotos_scheduler.LEASE_NAME] * 2


def test_fx_backfill_job_is_one_per_run(edicao) -> None:
    with _lease(True) as (lease, _calls):
        seams = dict(ports_factory=lambda _s: edicao.ports, admin_factory=lambda: object(), lease_fn=lease)
        early = asyncio.run(fotos_scheduler.fx_backfill_job(
            now=datetime(2026, 9, 16, 16, 30, tzinfo=timezone.utc), **seams))
        late = asyncio.run(fotos_scheduler.fx_backfill_job(
            now=datetime(2026, 9, 16, 21, 30, tzinfo=timezone.utc), **seams))
    assert early and late and early != late


def test_scheduler_skips_without_the_lease_or_the_engine(edicao) -> None:
    from app.modules.edicao_fotos.services.ports import EdicaoFotosUnavailable

    with _lease(False) as (lease, _calls):
        assert asyncio.run(fotos_scheduler.daily_notes_job(
            ports_factory=lambda _s: edicao.ports, admin_factory=lambda: object(), lease_fn=lease)) is None

    def unavailable(_s):
        raise EdicaoFotosUnavailable("sem supabase")

    assert asyncio.run(fotos_scheduler.fx_backfill_job(ports_factory=unavailable)) is None


def test_catch_up_respects_the_schedulers_guard(edicao) -> None:
    # The test process never carries NOCTUS_SCHEDULERS_ENABLED.
    assert asyncio.run(fotos_scheduler.catch_up(ports_factory=lambda _s: edicao.ports)) is None


def test_register_wires_both_jobs() -> None:
    from noctusai_lib.api import scheduler as seed_scheduler

    from app.modules.edicao_fotos import register

    register()
    names = {job.id for job in seed_scheduler.scheduler.get_jobs()}
    assert {fotos_scheduler.NOTES_JOB, fotos_scheduler.FX_JOB} <= names
