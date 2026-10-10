"""Pesquisa Extrair — submit / caps / handler / reconcile / worker tests
(pesquisa-wave2-contract.md section 5).

Real seams only, nothing of ours patched: the queue is a ``FakeJobRepository``
and the settings a ``model_copy`` of the real ones (both through the router's
DI seams), the LLM is the injected ``PesquisaLlm`` callable, and the handler's
source registry is a ``FONTES``-shaped dict holding a fake source.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

import pytest

from noctusai_lib.domain.jobs import DeadLetterError, FakeJobRepository

from app.config import settings
from app.modules.media_creation.pesquisa_fontes import PostFonte
from app.modules.media_creation.prompts.assuntos_virais_extractor import ASSUNTOS_VIRAIS_SYSTEM_PROMPT
from app.modules.media_creation.prompts.pesquisa_extractor import PESQUISA_EXTRACTOR_SYSTEM_PROMPT
from app.modules.media_creation.routers.pesquisa import classify_items
from app.modules.media_creation.routers.pesquisa_extracao import (
    get_extracao_jobs,
    get_extracao_settings,
    submit_extracao,
)
from app.modules.media_creation.services.pesquisa_extracao_service import (
    JOB_TYPE,
    executar_extracao,
)
from app.modules.media_creation.services.pesquisa_extracao_worker import build_worker
from app.rate_limit import limiter

BASE = "/api/media-creation/pesquisa"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_ORG_MARCA = str(uuid.uuid4())
KIT = "kit-ext-1"
SLUG = "DORES-TANGIVEIS-DO-AVATAR"
TEXTO = "Eu não aguento mais acordar cansado todo dia. Minha rotina de sono virou um caos total."
SPAN = "acordar cansado todo dia"
PESQUISA_REPLY = f"{{{{{SLUG}}}}}\n[{SPAN}]"
ASSUNTOS_REPLY = "sono e ansiedade\ndieta low carb"


def _cfg(**over):
    return settings.model_copy(update=over)


class FakeJobsBroken:
    """Queue double whose enqueue always fails (the 503 path)."""

    async def enqueue(self, **_kw):
        raise RuntimeError("queue down")


class FakeFonte:
    """A ``FonteExtracao`` over a fixed set of posts (the handler seam)."""

    kind = "instagram_media"

    def __init__(self, posts: dict[tuple[Optional[str], str], PostFonte]):
        self._posts = posts

    def obter(self, org_id, marca_id, refs):
        return {r: self._posts[r] for r in refs if r in self._posts}


def _post(pid: str, *, texto: str = TEXTO, plays: Optional[int] = 1000, account="acc-1") -> PostFonte:
    return PostFonte(
        kind="instagram_media", account_id=account, id=pid, url=f"https://ig/{pid}",
        thumbnail_url=f"https://ig/{pid}.jpg", published_at="2026-10-01T10:00:00+00:00",
        texto=texto, analisavel=len(texto.strip()) >= 20, plays=plays, likes=5, comments=2,
        extra={"media_product_type": "REELS"},
    )


def _registry(*posts: PostFonte):
    fake = FakeFonte({(p.account_id, p.id): p for p in posts})
    return {"instagram_media": lambda db, texto_max_chars=6000: fake}


class Llm:
    """Scripted ``PesquisaLlm``. ``replies`` maps tipo -> a reply, an Exception
    (raised), or a list consumed one entry per call (entries may be Exceptions)."""

    def __init__(self, replies=None, on_call=None):
        self.replies = dict(replies or {"pesquisa": PESQUISA_REPLY, "assuntos_virais": ASSUNTOS_REPLY})
        self.calls: list[tuple[str, str]] = []
        self.on_call = on_call

    async def __call__(self, system, user, org_id):
        tipo = "pesquisa" if system == PESQUISA_EXTRACTOR_SYSTEM_PROMPT else "assuntos_virais"
        assert system in (PESQUISA_EXTRACTOR_SYSTEM_PROMPT, ASSUNTOS_VIRAIS_SYSTEM_PROMPT)
        self.calls.append((tipo, user))
        if self.on_call:
            self.on_call(len(self.calls))
        out = self.replies[tipo]
        if isinstance(out, list):
            out = out.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture
def ec(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_ORG_MARCA, "org_id": "other-org", "name": "B"}).execute()
    sb.from_("mc_brand_kits").insert({"id": KIT, "org_id": ORG, "marca_id": MARCA, "name": "Kit"}).execute()
    for i, texto in enumerate([TEXTO, TEXTO + " Segundo.", "curto"], start=1):
        sb.from_("mc_posts").insert({
            "id": f"mc-{i}", "org_id": ORG, "brand_kit_id": KIT, "title": texto, "idea": None,
            "key_message": None, "copy_caption": None, "published_media_id": None,
            "published_permalink": None, "published_at": None,
            "created_at": f"2026-10-0{i}T10:00:00+00:00",
        }).execute()
    client.jobs = FakeJobRepository()
    client._tc.app.dependency_overrides[get_extracao_jobs] = lambda: client.jobs
    client._tc.app.dependency_overrides[get_extracao_settings] = lambda: _cfg()
    return client


def _use_cfg(ec, **over):
    ec._tc.app.dependency_overrides[get_extracao_settings] = lambda: _cfg(**over)


def _submit(ec, posts=None, tipos=("pesquisa",), marca=MARCA, **extra):
    posts = posts if posts is not None else [{"kind": "mc_post", "id": "mc-1"}]
    return ec.post(f"{BASE}/extracoes", json={
        "marca_id": marca, "tipos": list(tipos), "posts": posts, **extra,
    })


def _jobs(ec):
    return ec.mock_supabase.from_("cs_extraction_jobs").select("*").execute().data


def _insert_run(ec, extracao_id, tipo, pid, status="done", kind="mc_post", account_id=None):
    ec.mock_supabase.from_("cs_extraction_post_runs").insert({
        "id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "extracao_id": extracao_id,
        "tipo": tipo, "source_kind": kind, "account_id": account_id, "source_id": pid,
        "status": status, "created_at": "2026-10-05T10:00:00+00:00",
    }).execute()


JOB_KEYS = {
    "id", "marca_id", "tipos", "status", "step", "progress", "total_tarefas", "tarefas_processadas",
    "tarefas_com_erro", "itens_salvos", "itens_ignorados", "itens_descartados", "assuntos_salvos",
    "assuntos_ignorados", "ja_extraidos_pulados", "erro", "created_at", "started_at", "finished_at",
}


class TestSubmit:
    def test_202_queues_row_and_job(self, ec):
        r = _submit(ec, tipos=("pesquisa", "assuntos_virais"))
        assert r.status_code == 202, r.text
        data = r.json()["data"]
        assert set(data) == JOB_KEYS
        assert data["status"] == "queued" and data["total_tarefas"] == 2 and data["progress"] == 0
        row = _jobs(ec)[0]
        assert row["tipos"] == ["pesquisa", "assuntos_virais"]
        assert row["posts"] == [
            {"kind": "mc_post", "account_id": None, "id": "mc-1", "tipos": ["pesquisa", "assuntos_virais"]}
        ]
        job = next(iter(ec.jobs._jobs.values()))
        assert job.type == JOB_TYPE and job.payload == {"extracao_id": data["id"]}
        assert job.dedupe_key == f"{JOB_TYPE}:{data['id']}" and job.max_retries == 2
        assert row["queue_job_id"] == job.id

    def test_second_active_job_is_409(self, ec):
        assert _submit(ec).status_code == 202
        r = _submit(ec, posts=[{"kind": "mc_post", "id": "mc-2"}])
        assert r.status_code == 409 and r.json()["error"]["message"] == "Já existe uma extração em andamento"

    def test_daily_user_cap_is_429(self, ec):
        _use_cfg(ec, pesquisa_extracao_jobs_por_dia_usuario=0)
        r = _submit(ec)
        assert r.status_code == 429 and r.json()["error"]["message"] == "Limite diário de extrações atingido"

    def test_daily_org_cap_counts_posts_times_tipos(self, ec):
        _use_cfg(ec, pesquisa_extracao_posts_por_dia_org=3)
        two = [{"kind": "mc_post", "id": "mc-1"}, {"kind": "mc_post", "id": "mc-2"}]
        assert _submit(ec, posts=two, tipos=("pesquisa", "assuntos_virais")).status_code == 429
        assert _submit(ec, posts=two[:1], tipos=("pesquisa", "assuntos_virais")).status_code == 202

    def test_too_many_posts_is_422(self, ec):
        _use_cfg(ec, pesquisa_extracao_max_posts_por_job=1)
        two = [{"kind": "mc_post", "id": "mc-1"}, {"kind": "mc_post", "id": "mc-2"}]
        assert _submit(ec, posts=two).status_code == 422
        assert _jobs(ec) == []

    def test_foreign_or_unknown_post_is_422(self, ec):
        r = _submit(ec, posts=[{"kind": "mc_post", "id": "not-mine"}])
        assert r.status_code == 422 and r.json()["error"]["message"] == "Post não encontrado para esta marca"
        assert _jobs(ec) == [] and ec.jobs._jobs == {}

    def test_ig_post_without_account_is_422(self, ec):
        assert _submit(ec, posts=[{"kind": "instagram_media", "id": "x"}]).status_code == 422

    def test_all_already_extracted_is_422_and_reextrair_overrides(self, ec):
        _insert_run(ec, "old", "pesquisa", "mc-1")
        r = _submit(ec)
        assert r.status_code == 422 and r.json()["error"]["message"] == "Todos os posts selecionados já foram extraídos"
        r = _submit(ec, reextrair=True)
        assert r.status_code == 202 and r.json()["data"]["ja_extraidos_pulados"] == 0

    def test_already_extracted_pair_is_skipped_per_tipo(self, ec):
        _insert_run(ec, "old", "pesquisa", "mc-1")
        r = _submit(ec, tipos=("pesquisa", "assuntos_virais"))
        data = r.json()["data"]
        assert r.status_code == 202 and data["total_tarefas"] == 1 and data["ja_extraidos_pulados"] == 1
        assert _jobs(ec)[0]["posts"][0]["tipos"] == ["assuntos_virais"]

    def test_worker_disabled_is_503(self, ec):
        _use_cfg(ec, pesquisa_extracao_worker_enabled=False)
        r = _submit(ec)
        assert r.status_code == 503 and r.json()["error"]["message"] == "Extração indisponível no momento"
        assert _jobs(ec) == []

    def test_enqueue_failure_is_503_and_row_failed(self, ec):
        ec._tc.app.dependency_overrides[get_extracao_jobs] = lambda: FakeJobsBroken()
        r = _submit(ec)
        assert r.status_code == 503 and r.json()["error"]["message"] == "Falha ao iniciar a extração"
        row = _jobs(ec)[0]
        assert row["status"] == "failed" and row["erro"] == "Falha ao iniciar a extração"
        # the failed row frees the user's slot
        ec._tc.app.dependency_overrides[get_extracao_jobs] = lambda: ec.jobs
        assert _submit(ec).status_code == 202

    def test_cross_org_marca_is_404(self, ec):
        assert _submit(ec, marca=OTHER_ORG_MARCA).status_code == 404


class TestReadsAndLifecycle:
    def test_fontes_lists_mc_post_source(self, ec):
        data = ec.get(f"{BASE}/fontes", params={"marca_id": MARCA}).json()["data"]
        assert [f["kind"] for f in data] == ["mc_post"] or "mc_post" in [f["kind"] for f in data]
        mc = next(f for f in data if f["kind"] == "mc_post")
        assert mc["account_id"] is None and mc["total_posts"] == 3

    def test_posts_carry_extraido_timestamps(self, ec):
        _insert_run(ec, "old", "pesquisa", "mc-1")
        r = ec.get(f"{BASE}/fontes/posts", params={"marca_id": MARCA, "kind": "mc_post"})
        assert r.status_code == 200, r.text
        posts = {p["id"]: p for p in r.json()["data"]["posts"]}
        assert posts["mc-1"]["extraido"]["pesquisa"] == "2026-10-05T10:00:00+00:00"
        assert posts["mc-1"]["extraido"]["assuntos_virais"] is None
        assert posts["mc-2"]["extraido"] == {"pesquisa": None, "assuntos_virais": None}

    def test_posts_ig_without_account_is_422_and_foreign_marca_404(self, ec):
        assert ec.get(f"{BASE}/fontes/posts", params={"marca_id": MARCA, "kind": "instagram_media"}).status_code == 422
        assert ec.get(f"{BASE}/fontes/posts", params={"marca_id": OTHER_ORG_MARCA, "kind": "mc_post"}).status_code == 404

    def test_limits(self, ec):
        d = ec.get(f"{BASE}/extracoes/limites", params={"marca_id": MARCA}).json()["data"]
        assert d == {
            "worker_ativo": True, "max_posts_por_job": 30, "extracoes_restantes_hoje": 10,
            "tarefas_restantes_hoje_org": 300, "extracao_ativa_id": None,
        }
        eid = _submit(ec).json()["data"]["id"]
        d = ec.get(f"{BASE}/extracoes/limites", params={"marca_id": MARCA}).json()["data"]
        assert d["extracao_ativa_id"] == eid and d["extracoes_restantes_hoje"] == 9
        assert d["tarefas_restantes_hoje_org"] == 299

    def test_list_and_get(self, ec):
        eid = _submit(ec).json()["data"]["id"]
        lst = ec.get(f"{BASE}/extracoes", params={"marca_id": MARCA}).json()["data"]
        assert [j["id"] for j in lst] == [eid] and set(lst[0]) == JOB_KEYS
        assert ec.get(f"{BASE}/extracoes/{eid}").json()["data"]["id"] == eid
        assert ec.get(f"{BASE}/extracoes/{uuid.uuid4()}").status_code == 404

    def test_cancel_queued_then_409(self, ec):
        eid = _submit(ec).json()["data"]["id"]
        r = ec.post(f"{BASE}/extracoes/{eid}/cancel")
        assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
        assert ec.post(f"{BASE}/extracoes/{eid}/cancel").status_code == 409
        assert _submit(ec).status_code == 202  # slot freed

    def test_dead_lettered_queue_row_fails_the_extraction(self, ec):
        eid = _submit(ec).json()["data"]["id"]
        qid = _jobs(ec)[0]["queue_job_id"]
        ec.mock_supabase.from_("jobs").insert({"id": qid, "status": "dead_letter"}).execute()
        got = ec.get(f"{BASE}/extracoes/{eid}").json()["data"]
        assert got["status"] == "failed" and got["erro"] == "Falha interna na extração"
        assert ec.get(f"{BASE}/extracoes", params={"marca_id": MARCA}).json()["data"][0]["status"] == "failed"

    def test_retrying_queue_row_is_not_reconciled(self, ec):
        eid = _submit(ec).json()["data"]["id"]
        qid = _jobs(ec)[0]["queue_job_id"]
        ec.mock_supabase.from_("jobs").insert({"id": qid, "status": "failed"}).execute()
        assert ec.get(f"{BASE}/extracoes/{eid}").json()["data"]["status"] == "queued"


def _job_row(ec, selection, tipos=("pesquisa",), **over):
    eid = str(uuid.uuid4())
    row = {
        "id": eid, "org_id": ORG, "marca_id": MARCA, "created_by": "u1", "tipos": list(tipos),
        "status": "queued", "cancel_requested": False, "posts": selection,
        "total_tarefas": sum(len(s["tipos"]) for s in selection), "tarefas_processadas": 0,
        "created_at": datetime.now(timezone.utc).isoformat(), **over,
    }
    ec.mock_supabase.from_("cs_extraction_jobs").insert(row).execute()
    return eid


def _sel(pid, *tipos, account="acc-1"):
    return {"kind": "instagram_media", "account_id": account, "id": pid, "tipos": list(tipos)}


def _run(ec, eid, llm, *posts):
    asyncio.run(executar_extracao(
        ec.mock_supabase, llm, eid, texto_max_chars=6000, fontes=_registry(*posts),
    ))
    return next(j for j in _jobs(ec) if j["id"] == eid)


def _items(ec):
    return ec.mock_supabase.from_("cs_research_items").select("*").execute().data


def _runs(ec, eid):
    return [r for r in ec.mock_supabase.from_("cs_extraction_post_runs").select("*").execute().data
            if r["extracao_id"] == eid]


class TestHandler:
    def test_saves_pending_items_with_source_ref_and_plays(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa")])
        job = _run(ec, eid, Llm(), _post("p1", plays=4200))
        assert job["status"] == "completed" and job["itens_salvos"] == 1
        assert job["tarefas_processadas"] == 1 and job["step"] is None and job["finished_at"]
        [item] = _items(ec)
        assert item["status"] == "pending" and item["origin"] == "extraction"
        assert item["variable_slug"] == SLUG and item["content"] == SPAN and item["plays"] == 4200
        ref = item["source_ref"]
        assert ref["kind"] == "instagram_media" and ref["id"] == "p1" and ref["account_id"] == "acc-1"
        assert ref["url"] == "https://ig/p1" and ref["plays"] == 4200 and ref["likes"] == 5
        assert ref["extracao_id"] == eid and SPAN in ref["excerpt"]
        [run] = _runs(ec, eid)
        assert run["status"] == "done" and run["itens_salvos"] == 1

    def test_duplicate_item_is_ignored_first_source_wins(self, ec):
        e1 = _job_row(ec, [_sel("p1", "pesquisa")])
        _run(ec, e1, Llm(), _post("p1", plays=10))
        e2 = _job_row(ec, [_sel("p2", "pesquisa")])
        job = _run(ec, e2, Llm(), _post("p2", plays=99))
        assert job["itens_salvos"] == 0 and job["itens_ignorados"] == 1
        [item] = _items(ec)
        assert item["source_ref"]["id"] == "p1" and item["plays"] == 10

    def test_non_literal_span_is_discarded_and_counted(self, ec):
        llm = Llm({"pesquisa": f"{{{{{SLUG}}}}}\n[algo que o post nunca disse]"})
        job = _run(ec, _job_row(ec, [_sel("p1", "pesquisa")]), llm, _post("p1"))
        assert job["itens_salvos"] == 0 and job["itens_descartados"] == 1 and job["status"] == "completed"

    def test_topics_saved_with_sources(self, ec):
        eid = _job_row(ec, [_sel("p1", "assuntos_virais")], tipos=("assuntos_virais",))
        job = _run(ec, eid, Llm(), _post("p1", plays=700))
        assert job["status"] == "completed" and job["assuntos_salvos"] == 2
        topics = ec.mock_supabase.from_("cs_viral_topics").select("*").execute().data
        assert {t["topic"] for t in topics} == {"sono e ansiedade", "dieta low carb"}
        assert {t["status"] for t in topics} == {"pending"} and {t["total_plays"] for t in topics} == {700}
        srcs = ec.mock_supabase.from_("cs_viral_topic_sources").select("*").execute().data
        assert len(srcs) == 2 and {s["source_id"] for s in srcs} == {"p1"}
        assert {s["extracao_id"] for s in srcs} == {eid}

    def test_combined_job_runs_both_tipos_per_post(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa", "assuntos_virais")], tipos=("pesquisa", "assuntos_virais"))
        llm = Llm()
        job = _run(ec, eid, llm, _post("p1"))
        assert [c[0] for c in llm.calls] == ["pesquisa", "assuntos_virais"]
        assert job["tarefas_processadas"] == 2 and job["itens_salvos"] == 1 and job["assuntos_salvos"] == 2
        assert {r["tipo"] for r in _runs(ec, eid)} == {"pesquisa", "assuntos_virais"}

    def test_one_llm_error_is_completed_with_errors(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa"), _sel("p2", "pesquisa")])
        llm = Llm({"pesquisa": [RuntimeError("boom"), PESQUISA_REPLY]})
        job = _run(ec, eid, llm, _post("p1"), _post("p2", texto=TEXTO + " Outro."))
        assert job["status"] == "completed_with_errors"
        assert job["tarefas_com_erro"] == 1 and job["itens_salvos"] == 1 and job["tarefas_processadas"] == 2
        statuses = {r["source_id"]: (r["status"], r["motivo"]) for r in _runs(ec, eid)}
        assert statuses == {"p1": ("failed", "llm_erro"), "p2": ("done", None)}

    def test_all_posts_failing_is_failed(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa"), _sel("p2", "pesquisa")])
        job = _run(ec, eid, Llm({"pesquisa": RuntimeError("down")}), _post("p1"), _post("p2"))
        assert job["status"] == "failed" and job["tarefas_com_erro"] == 2 and job["erro"]
        assert _items(ec) == []

    def test_sem_texto_makes_no_llm_call(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa")])
        llm = Llm()
        job = _run(ec, eid, llm, _post("p1", texto="curto"))
        assert llm.calls == [] and job["status"] == "completed" and job["tarefas_processadas"] == 1
        [run] = _runs(ec, eid)
        assert (run["status"], run["motivo"]) == ("skipped", "sem_texto")

    def test_cancel_between_tasks(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa"), _sel("p2", "pesquisa")])

        def cancel_after_first(n):
            if n == 1:
                ec.mock_supabase.from_("cs_extraction_jobs").update({"cancel_requested": True}).eq("id", eid).execute()

        llm = Llm(on_call=cancel_after_first)
        job = _run(ec, eid, llm, _post("p1"), _post("p2", texto=TEXTO + " Outro."))
        assert job["status"] == "cancelled" and job["tarefas_processadas"] == 1 and len(llm.calls) == 1

    def test_cancel_requested_before_start(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa")], cancel_requested=True)
        llm = Llm()
        assert _run(ec, eid, llm, _post("p1"))["status"] == "cancelled" and llm.calls == []

    def test_retry_resumes_skipping_posts_with_a_run(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa"), _sel("p2", "pesquisa")], tarefas_processadas=1, itens_salvos=1)
        _insert_run(ec, eid, "pesquisa", "p1", kind="instagram_media", account_id="acc-1")
        llm = Llm()
        job = _run(ec, eid, llm, _post("p1"), _post("p2", texto=TEXTO + " Outro."))
        assert len(llm.calls) == 1 and "Outro." in llm.calls[0][1]
        assert job["status"] == "completed" and job["tarefas_processadas"] == 2 and job["itens_salvos"] == 2

    def test_already_settled_job_is_a_noop(self, ec):
        eid = _job_row(ec, [_sel("p1", "pesquisa")], status="cancelled")
        llm = Llm()
        assert _run(ec, eid, llm, _post("p1"))["status"] == "cancelled" and llm.calls == []

    def test_missing_row_is_dead_letter(self, ec):
        with pytest.raises(DeadLetterError):
            asyncio.run(executar_extracao(
                ec.mock_supabase, Llm(), str(uuid.uuid4()), texto_max_chars=6000, fontes=_registry(),
            ))


class TestWorkerEndToEnd:
    def test_submit_then_worker_run_once_completes_the_extraction(self, ec):
        r = _submit(ec)
        eid = r.json()["data"]["id"]
        worker = build_worker(ec.jobs, ec.mock_supabase, _cfg(), Llm())
        assert asyncio.run(worker.run_once()) is True
        got = ec.get(f"{BASE}/extracoes/{eid}").json()["data"]
        assert got["status"] == "completed" and got["itens_salvos"] == 1 and got["progress"] == 100
        [item] = _items(ec)
        assert item["source_ref"]["kind"] == "mc_post" and item["source_ref"]["id"] == "mc-1"
        assert item["plays"] is None  # mc_post has no views: NULL, never 0
        assert asyncio.run(worker.run_once()) is False  # queue drained

    def test_worker_only_claims_its_own_type(self, ec):
        asyncio.run(ec.jobs.enqueue(type="edicao_fotos.process", payload={}))
        worker = build_worker(ec.jobs, ec.mock_supabase, _cfg(), Llm())
        assert asyncio.run(worker.run_once()) is False


class TestAssuntosSourceRefresher:
    def test_source_urls_refreshed_from_the_live_post(self, ec):
        sb = ec.mock_supabase
        sb.from_("mc_posts").update(
            {"published_permalink": "https://ig/live"}
        ).eq("id", "mc-1").execute()
        topic_id = str(uuid.uuid4())
        sb.from_("cs_viral_topics").insert({
            "id": topic_id, "org_id": ORG, "marca_id": MARCA, "topic": "Tema", "status": "approved",
            "origin": "extraction", "total_plays": 5,
        }).execute()
        sb.from_("cs_viral_topic_sources").insert({
            "id": str(uuid.uuid4()), "org_id": ORG, "topic_id": topic_id, "source_kind": "mc_post",
            "account_id": None, "source_id": "mc-1", "url": "https://ig/stale", "thumbnail_url": None,
            "plays": 5,
        }).execute()
        r = ec.get(f"{BASE}/assuntos-virais/{topic_id}/fontes")
        assert r.status_code == 200, r.text
        [src] = r.json()["data"]
        assert src["url"] == "https://ig/live" and src["plays"] == 5


class TestRateLimitAndAuth:
    @pytest.mark.parametrize("fn", [classify_items, submit_extracao])
    def test_default_ai_rl_is_applied(self, fn):
        from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL

        key = f"{fn.__module__}.{fn.__name__}"
        limits = limiter._route_limits.get(key) or []
        assert limits, f"{key} carries no @limiter.limit"
        assert DEFAULT_AI_RL.split("/")[0] in {str(lim.limit.amount) for lim in limits}

    @pytest.mark.parametrize("method,path,kw", [
        ("get", "/fontes", {"params": {"marca_id": MARCA}}),
        ("get", "/fontes/posts", {"params": {"marca_id": MARCA, "kind": "mc_post"}}),
        ("get", "/extracoes/limites", {"params": {"marca_id": MARCA}}),
        ("post", "/extracoes", {"json": {"marca_id": MARCA, "tipos": ["pesquisa"], "posts": [{"kind": "mc_post", "id": "x"}]}}),
        ("get", "/extracoes", {"params": {"marca_id": MARCA}}),
        ("get", f"/extracoes/{uuid.uuid4()}", {}),
        ("post", f"/extracoes/{uuid.uuid4()}/cancel", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)

