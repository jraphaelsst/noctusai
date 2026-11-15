"""Estruturas load endpoints (estruturas-contract.md section 6.3, tier ``platform``) + the ``estruturas.importar`` job.

Mounted through the real ``register()`` seam on the MockSupabaseClient. The platform-admin check is the production DI
seam (``get_platform_admin_check``) overridden, never patched; the library I/O seam (``get_importacao_store``), storage
and job queue are DI overrides too. Auth tests assert STRICT ``== 401`` / ``== 403``. Synthetic corpora only.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.jobs import DeadLetterError
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import get_platform_admin_check
from app.modules.media_creation.deps import BIBLIOTECA_BUCKET
from app.modules.media_creation.routers.estruturas_importacao import get_importacao_jobs, get_importacao_storage, get_importacao_store
from app.modules.media_creation.services import estruturas_import as imp

from ._estruturas_import_fake_store import FakeStore
from ._estruturas_import_fixtures import SENTINELA, corpus_maquina, corpus_ref

BASE = "/api/media-creation/estruturas/importacoes"
_ID = str(uuid.uuid4())


class FakeJobs:
    def __init__(self):
        self.enqueued: list[dict] = []
        self.fail = False

    async def enqueue(self, **kw):
        if self.fail:
            raise RuntimeError("queue down")
        self.enqueued.append(kw)
        return type("Q", (), {"id": str(uuid.uuid4())})()


class State:
    def __init__(self, client):
        self.client = client
        self.storage = FakeStorageBackend()
        self.jobs = FakeJobs()
        self.store = FakeStore()
        self.admin = True
        app = client._tc.app
        app.dependency_overrides[get_importacao_storage] = lambda: self.storage
        app.dependency_overrides[get_importacao_jobs] = lambda: self.jobs
        app.dependency_overrides[get_importacao_store] = lambda: self.store
        app.dependency_overrides[get_platform_admin_check] = lambda: (lambda uid: self.admin)

    @property
    def db(self):
        return self.client.mock_supabase

    def lotes(self):
        return self.db.from_("cs_estrutura_importacoes").select("*").execute().data


@pytest.fixture
def est(client):
    return State(client)


def body(fonte="referencia", conteudo=None, **kw):
    return {"fonte": fonte, "conteudo": conteudo if conteudo is not None else corpus_ref(6), "arquivo_nome": "sintetico.json", **kw}


# ── auth: strict 401 / 403 on EVERY route ─────────────────────────────────────────────────────────────────

ROUTES = [("post", "", {"json": body()}), ("get", f"/{_ID}", {}), ("get", "", {})]


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", ROUTES)
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)

    @pytest.mark.parametrize("method,path,kw", ROUTES)
    def test_an_org_member_who_is_not_a_platform_admin_is_403_before_any_read_or_write(self, est, client, method, path, kw):
        est.admin = False
        r = getattr(client, method)(BASE + path, **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        assert r.json()["error"]["code"] == "FORBIDDEN"
        assert est.store.calls == [] and est.lotes() == [] and est.jobs.enqueued == []

    def test_the_router_is_declared_platform_and_precedes_the_estrutura_id_route(self):
        from app.modules.media_creation import register

        routers = register().routers
        tiers = [getattr(r, "access_tier", None) for r in routers]
        ours = next(i for i, r in enumerate(routers) if any(getattr(x, "path", "").startswith(BASE) for x in r.routes))
        swallow = next(i for i, r in enumerate(routers) if any(getattr(x, "path", "") == "/api/media-creation/estruturas/{estrutura_id}" for x in r.routes))
        assert tiers[ours] == "platform" and ours < swallow


# ── dry-run ──────────────────────────────────────────────────────────────────────────────────────────────


class TestSimulacao:
    def test_dry_run_is_the_default_returns_200_and_writes_only_the_simulada_lote(self, est, client):
        r = client.post(BASE, json=body())
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "simulada" and d["dry_run"] is True and d["finished_at"]
        assert (d["linhas_total"], d["estruturas_criadas"], d["estruturas_ignoradas"], d["perfis_criados"]) == (6, 6, 0, 4)
        assert d["arquivo_sha256"] == imp.sha256_documento(corpus_ref(6)) and d["campos_nao_importados"] == []
        assert est.store.calls == [] and est.store.estruturas == {}  # nothing written to the library
        (lote,) = est.lotes()
        assert lote["status"] == "simulada" and lote["dry_run"] is True and est.jobs.enqueued == []

    def test_the_report_carries_counts_and_codes_only_never_row_text(self, est, client):
        conteudo = corpus_ref(6)
        conteudo[0]["perfil"] = "inválido!"
        r = client.post(BASE, json=body(conteudo=conteudo))
        assert r.status_code == 200
        assert SENTINELA not in r.text and SENTINELA not in json.dumps(est.lotes(), default=str)
        assert r.json()["data"]["ignoradas_motivos"] == {"handle_invalido": 1}

    def test_the_maquina_plan_lists_the_fields_the_owner_left_out(self, est, client):
        r = client.post(BASE, json=body("maquina_de_roteiros", corpus_maquina(4)))
        d = r.json()["data"]
        assert r.status_code == 200 and "quandoUsar" in d["campos_nao_importados"] and d["linhas_total"] == 4

    @pytest.mark.parametrize("fonte,conteudo,motivo", [
        ("referencia", {"colecoes": {}}, "esperado_array"),
        ("maquina_de_roteiros", [1, 2], "esperado_colecoes_perfis_moldes"),
    ])
    def test_a_file_of_the_wrong_shape_is_422_arquivo_invalido_flat(self, est, client, fonte, conteudo, motivo):
        r = client.post(BASE, json=body(fonte, conteudo))
        assert r.status_code == 422 and r.json()["code"] == "arquivo_invalido" and r.json()["motivo"] == motivo
        assert est.lotes() == []

    def test_unknown_fields_and_an_unknown_fonte_are_422(self, est, client):
        assert client.post(BASE, json={**body(), "extra": 1}).status_code == 422
        assert client.post(BASE, json=body(fonte="outra")).status_code == 422


# ── apply ────────────────────────────────────────────────────────────────────────────────────────────────


class TestAplicacao:
    def test_apply_without_a_simulation_is_409_simulacao_obrigatoria(self, est, client):
        r = client.post(BASE, json=body(dry_run=False))
        assert r.status_code == 409 and r.json()["code"] == "simulacao_obrigatoria"
        assert est.lotes() == [] and est.jobs.enqueued == []

    def test_a_simulation_of_another_file_does_not_authorise_the_apply(self, est, client):
        assert client.post(BASE, json=body()).status_code == 200
        r = client.post(BASE, json=body(conteudo=corpus_ref(7), dry_run=False))
        assert r.status_code == 409 and r.json()["code"] == "simulacao_obrigatoria"

    def test_a_simulation_of_the_other_fonte_does_not_authorise_the_apply(self, est, client):
        assert client.post(BASE, json=body("maquina_de_roteiros", corpus_maquina(3))).status_code == 200
        assert client.post(BASE, json=body("referencia", corpus_maquina(3), dry_run=False)).status_code == 422  # shape first

    def test_a_simulation_older_than_24_hours_does_not_authorise_the_apply(self, est, client):
        assert client.post(BASE, json=body()).status_code == 200
        velho = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        est.db.from_("cs_estrutura_importacoes").update({"created_at": velho}).eq("status", "simulada").execute()
        r = client.post(BASE, json=body(dry_run=False))
        assert r.status_code == 409 and r.json()["code"] == "simulacao_obrigatoria"

    def test_apply_after_the_same_sha_simulation_is_202_stores_the_document_privately_and_enqueues_the_job(self, est, client):
        assert client.post(BASE, json=body()).status_code == 200
        r = client.post(BASE, json=body(dry_run=False))
        assert r.status_code == 202, r.text
        lote_id = r.json()["data"]["id"]
        assert r.json()["data"]["status"] == "em_andamento"
        (job,) = est.jobs.enqueued
        assert job["type"] == "estruturas.importar" and job["payload"] == {"importacao_id": lote_id}
        assert job["dedupe_key"] == f"estruturas.importar:{lote_id}"
        blob = asyncio.run(est.storage.get(bucket=BIBLIOTECA_BUCKET, key=f"importacoes/{lote_id}.json"))
        assert json.loads(blob.data) == corpus_ref(6)
        assert est.store.calls == []  # the request path writes nothing to the library; the job does
        em = [l for l in est.lotes() if l["status"] == "em_andamento"]
        assert len(em) == 1 and em[0]["dry_run"] is False and em[0]["linhas_total"] == 6

    def test_a_second_apply_while_one_runs_is_409_importacao_em_andamento(self, est, client):
        assert client.post(BASE, json=body()).status_code == 200
        assert client.post(BASE, json=body(dry_run=False)).status_code == 202
        r = client.post(BASE, json=body(dry_run=False))
        assert r.status_code == 409 and r.json()["code"] == "importacao_em_andamento" and len(est.jobs.enqueued) == 1

    def test_a_queue_failure_settles_the_lote_as_failed_removes_the_document_and_is_503(self, est, client):
        assert client.post(BASE, json=body()).status_code == 200
        est.jobs.fail = True
        r = client.post(BASE, json=body(dry_run=False))
        assert r.status_code == 503 and r.json()["code"] == "geracao_indisponivel"
        falhou = [l for l in est.lotes() if l["status"] == "falhou"]
        assert len(falhou) == 1 and falhou[0]["erro"] == "falha_ao_iniciar"
        assert asyncio.run(est.storage.list_keys(bucket=BIBLIOTECA_BUCKET, prefix="importacoes/")) == []
        est.jobs.fail = False  # and the lock is free again
        assert client.post(BASE, json=body(dry_run=False)).status_code == 202


# ── poll / list ──────────────────────────────────────────────────────────────────────────────────────────


class TestLeitura:
    def test_get_returns_the_report_and_a_foreign_id_is_404(self, est, client):
        lote = client.post(BASE, json=body()).json()["data"]
        r = client.get(f"{BASE}/{lote['id']}")
        assert r.status_code == 200 and r.json()["data"] == lote
        r = client.get(f"{BASE}/{_ID}")
        assert r.status_code == 404 and r.json()["code"] == "importacao_nao_encontrada"

    def test_list_is_newest_first_bounded_to_20(self, est, client):
        for _ in range(3):
            client.post(BASE, json=body())
        r = client.get(BASE, params={"limit": 2})
        d = r.json()["data"]
        assert r.status_code == 200 and len(d["items"]) == 2 and d["total"] == 3
        assert client.get(BASE, params={"limit": 21}).status_code == 422


# ── the job ──────────────────────────────────────────────────────────────────────────────────────────────


def _lote_pronto(est, conteudo, fonte="referencia"):
    lote_id = str(uuid.uuid4())
    est.db.from_("cs_estrutura_importacoes").insert({
        "id": lote_id, "fonte": fonte, "arquivo_sha256": imp.sha256_documento(conteudo), "status": "em_andamento", "dry_run": False,
        "linhas_total": len(conteudo) if isinstance(conteudo, list) else len(conteudo["colecoes"]["moldes"]), "iniciada_por": str(uuid.uuid4()),
    }).execute()
    asyncio.run(est.storage.put(bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(lote_id), data=json.dumps(conteudo).encode()))
    return lote_id


def _rodar(est, lote_id, *, ultima=False):
    return asyncio.run(imp.executar_job(est.db, est.storage, lote_id, limite_perfis=1000, ultima_tentativa=ultima, store=est.store))


class TestJob:
    def test_the_job_applies_the_document_settles_the_lote_concluida_and_deletes_the_document(self, est):
        conteudo = corpus_ref(6)
        lote_id = _lote_pronto(est, conteudo)
        _rodar(est, lote_id)
        (lote,) = [l for l in est.lotes() if l["id"] == lote_id]
        assert lote["status"] == "concluida" and lote["finished_at"] and lote["estruturas_criadas"] == 6 and lote["erro"] is None
        assert lote["estruturas_criadas"] + lote["estruturas_atualizadas"] + lote["estruturas_inalteradas"] + lote["estruturas_ignoradas"] == lote["linhas_total"]
        assert len(est.store.estruturas) == 6
        assert asyncio.run(est.storage.get(bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(lote_id))) is None

    def test_a_redelivered_job_for_a_finished_lote_is_a_noop(self, est):
        lote_id = _lote_pronto(est, corpus_ref(3))
        _rodar(est, lote_id)
        n = len(est.store.calls)
        _rodar(est, lote_id)
        assert len(est.store.calls) == n

    def test_a_missing_document_fails_the_lote_with_a_code_and_dead_letters(self, est):
        lote_id = _lote_pronto(est, corpus_ref(3))
        asyncio.run(est.storage.delete(bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(lote_id)))
        with pytest.raises(DeadLetterError):
            _rodar(est, lote_id)
        (lote,) = [l for l in est.lotes() if l["id"] == lote_id]
        assert lote["status"] == "falhou" and lote["erro"] == "arquivo_indisponivel"

    def test_an_unexpected_failure_keeps_the_lote_running_for_the_retry_and_the_document_stays(self, est):
        lote_id = _lote_pronto(est, corpus_ref(3))
        est.store.fail_with["cs_estrutura_criar"] = ConnectionError(f"{SENTINELA} boom")
        with pytest.raises(ConnectionError):
            _rodar(est, lote_id, ultima=False)
        (lote,) = [l for l in est.lotes() if l["id"] == lote_id]
        assert lote["status"] == "em_andamento"
        assert asyncio.run(est.storage.get(bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(lote_id))) is not None

    def test_on_the_last_attempt_the_lote_fails_with_the_exception_class_only_and_the_document_is_deleted(self, est):
        lote_id = _lote_pronto(est, corpus_ref(3))
        est.store.fail_with["cs_estrutura_criar"] = ConnectionError(f"{SENTINELA} boom")
        with pytest.raises(ConnectionError):
            _rodar(est, lote_id, ultima=True)
        (lote,) = [l for l in est.lotes() if l["id"] == lote_id]
        assert lote["status"] == "falhou" and lote["erro"] == "erro:ConnectionError" and SENTINELA not in json.dumps(lote, default=str)
        assert asyncio.run(est.storage.get(bucket=BIBLIOTECA_BUCKET, key=imp.chave_blob(lote_id))) is None

    def test_the_dead_letter_reconciler_settles_a_running_lote_and_leaves_a_finished_one(self, est):
        a, b = _lote_pronto(est, corpus_ref(2)), _lote_pronto(est, corpus_ref(2))
        est.db.from_("cs_estrutura_importacoes").update({"status": "concluida"}).eq("id", b).execute()
        # one at a time is a DB unique in prod; the mock does not enforce the partial index, which is fine here
        for lote_id in (a, b):
            imp.reconciliar_dead_letter(est.db, type("J", (), {"payload": {"importacao_id": lote_id}})())
        by_id = {l["id"]: l for l in est.lotes()}
        assert by_id[a]["status"] == "falhou" and by_id[a]["erro"] == "job_falhou" and by_id[b]["status"] == "concluida"

    def test_the_handler_is_registered_for_the_declared_job_type(self):
        from app.modules.media_creation.services import geracao_jobs

        assert "estruturas.importar" in geracao_jobs.GERACAO_JOB_TYPES
        imp.register()
        assert geracao_jobs.get_handler("estruturas.importar") is imp.handle_importar
        assert geracao_jobs.get_reconciler("estruturas.importar") is imp.reconciliar_dead_letter
