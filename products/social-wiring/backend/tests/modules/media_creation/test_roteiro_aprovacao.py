"""CoreStudio S3: roteiro approval -- any org member decides, approval is always required, editing invalidates it.

Real seams only: the approvals organ's own `FakeApprovalLedger` (the Fake the organ ships, same refusals as the
`apr_record` RPC) over the mock Supabase table, injected through the router's `get_roteiro_approvals` DI seam; the LLM
is the injected `RoteiroLlm` callable. Nothing of ours is patched. The event rows the Real RPC writes are asserted on
the migration SQL (the Fake cannot prove a trigger).
"""
from __future__ import annotations

import asyncio
import dataclasses
import uuid

import pytest
from noctusai_lib.domain._organ_common import make_org_table_store
from noctusai_lib.domain.approvals import ApprovalStore, FakeApprovalLedger, table_specs
from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.testing.migrations import migration_path

from app.config import settings
from app.modules.media_creation.routers.roteiros import get_roteiro_approvals, get_roteiro_jobs, get_roteiro_settings
from app.modules.media_creation.services import roteiro_aprovacao as apr
from app.modules.media_creation.services.roteiro_service import (
    RoteiroError,
    RoteiroService,
    executar_geracao,
    get_roteiro_ia_check,
)
from pathlib import Path

BASE = "/api/media-creation/roteiros"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
_BACKEND = Path(__file__).resolve().parents[3]
SQL = migration_path(_BACKEND, "approvals").read_text(encoding="utf-8")
SQL_PAPEL = migration_path(_BACKEND, "cs_esteira_papel_agendado").read_text(encoding="utf-8")


class Llm:
    def __init__(self, reply):
        self.reply = reply

    async def __call__(self, system, user, org_id):
        return self.reply


@pytest.fixture
def ra(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    tables = make_org_table_store(table_specs(apr.CFG), supabase_client=sb)
    client.store = ApprovalStore(tables, FakeApprovalLedger(tables))
    client.jobs = FakeJobRepository()
    ov = client._tc.app.dependency_overrides
    ov[get_roteiro_approvals] = lambda: apr.make_approvals(sb, store=client.store)
    ov[get_roteiro_jobs] = lambda: client.jobs
    ov[get_roteiro_settings] = lambda: settings
    ov[get_roteiro_ia_check] = lambda: (lambda org_id: None)
    return client


def _roteiro(ra, status="completo", versao=1, org=ORG, conteudo="## Capa\nTexto do roteiro") -> str:
    rid = str(uuid.uuid4())
    ra.mock_supabase.from_("cs_roteiros").insert({
        "id": rid, "org_id": org, "marca_id": MARCA, "nome": "R", "headline_texto": "Headline", "status": status,
        "versao": versao, "conteudo": conteudo,
    }).execute()
    return rid


def _events(ra, rid):
    """The ledger's events in insertion order (the mock table keeps it; the DB stamps `created_at`)."""
    return [(e["event"], e["versao"]) for e in ra.mock_supabase.from_("apr_events").select("*").eq("subject_id", rid).execute().data]


class TestAprovar:
    def test_nobody_submitted_is_not_approved(self, ra):
        rid = _roteiro(ra)
        assert ra.get(f"{BASE}/{rid}/aprovacao").json()["data"]["status"] == "none"
        assert apr.roteiro_aprovado(ra.mock_supabase, ORG, rid, approvals=apr.make_approvals(ra.mock_supabase, store=ra.store)) is False

    def test_solicitar_is_idempotent_and_pending(self, ra):
        rid = _roteiro(ra)
        for _ in range(2):
            d = ra.post(f"{BASE}/{rid}/aprovacao/solicitar").json()["data"]
            assert d["status"] == "pending" and d["versao"] == 1
        assert _events(ra, rid) == [("submitted", 1)]

    def test_any_member_approves_and_the_decision_is_recorded_with_the_actor(self, ra):
        rid = _roteiro(ra)
        r = ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["status"] == "approved" and d["versao"] == 1 and d["decidido_por"]  # decidido_em is stamped by the DB default
        assert _events(ra, rid) == [("submitted", 1), ("approved", 1)]
        assert ra.get(f"{BASE}/{rid}").json()["data"]["aprovacao"]["status"] == "approved"

    def test_second_decision_is_409_ja_decidido(self, ra):
        rid = _roteiro(ra)
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1}).status_code == 200
        r = ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1})
        assert r.status_code == 409 and "ja_decidido" in r.text
        assert ra.post(f"{BASE}/{rid}/reprovar", json={"versao": 1, "motivo": "x"}).status_code == 409

    def test_stale_versao_is_refused(self, ra):
        rid = _roteiro(ra, versao=3)
        r = ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 2})
        assert r.status_code == 409 and "versao_obsoleta" in r.text
        assert apr.estado_aprovacao_roteiro(ra.mock_supabase, ORG, rid, approvals=apr.make_approvals(ra.mock_supabase, store=ra.store))["status"] == "pending"

    def test_reprovar_requires_motivo(self, ra):
        rid = _roteiro(ra)
        assert ra.post(f"{BASE}/{rid}/reprovar", json={"versao": 1}).status_code == 422
        assert ra.post(f"{BASE}/{rid}/reprovar", json={"versao": 1, "motivo": "   "}).status_code == 422
        r = ra.post(f"{BASE}/{rid}/reprovar", json={"versao": 1, "motivo": "Falta o gancho"})
        d = r.json()["data"]
        assert r.status_code == 200 and d["status"] == "rejected" and d["motivo"] == "Falta o gancho"
        assert _events(ra, rid) == [("submitted", 1), ("rejected", 1)]

    def test_only_a_completo_roteiro_can_be_decided(self, ra):
        rid = _roteiro(ra, status="processando")
        for path, body in ((f"{BASE}/{rid}/aprovar", {"versao": 1}), (f"{BASE}/{rid}/reprovar", {"versao": 1, "motivo": "m"}),
                           (f"{BASE}/{rid}/aprovacao/solicitar", None)):
            r = ra.post(path, json=body) if body is not None else ra.post(path)
            assert r.status_code == 409 and "roteiro_incompleto" in r.text, path
        assert _events(ra, rid) == []

    def test_foreign_org_roteiro_is_404(self, ra):
        rid = _roteiro(ra, org="other-org")
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1}).status_code == 404
        assert ra.get(f"{BASE}/{rid}/aprovacao").status_code == 404
        assert ra.post(f"{BASE}/{rid}/aprovacao/solicitar").status_code == 404

    def test_strict_bodies(self, ra):
        rid = _roteiro(ra)
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1, "extra": 1}).status_code == 422
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 0}).status_code == 422


class TestEdicaoInvalida:
    def test_editing_after_approval_resubmits_and_invalidates(self, ra):
        rid = _roteiro(ra)
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1}).status_code == 200
        r = ra.put(f"{BASE}/{rid}", json={"conteudo": "novo texto", "expected_versao": 1})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["versao"] == 2 and d["aprovacao"]["status"] == "pending" and d["aprovacao"]["versao"] == 2
        assert _events(ra, rid) == [("submitted", 1), ("approved", 1), ("submitted", 2)]
        svc = apr.make_approvals(ra.mock_supabase, store=ra.store)
        assert apr.roteiro_aprovado(ra.mock_supabase, ORG, rid, approvals=svc) is False
        # the old versao can no longer be approved
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 1}).status_code == 409
        assert ra.post(f"{BASE}/{rid}/aprovar", json={"versao": 2}).status_code == 200
        assert apr.roteiro_aprovado(ra.mock_supabase, ORG, rid, approvals=svc) is True


class TestGeracao:
    def _processando(self, ra) -> str:
        rid = _roteiro(ra, status="processando", versao=1, conteudo="")
        return rid

    def _run(self, ra, rid, reply):
        job = asyncio.run(ra.jobs.enqueue(type="roteiro.gerar", payload={"roteiro_id": rid}, max_retries=2))
        asyncio.run(executar_geracao(dataclasses.replace(job), db=ra.mock_supabase, llm=Llm(reply), cfg=settings))

    def test_url_in_ai_output_is_a_coded_falha(self, ra):
        rid = self._processando(ra)
        self._run(ra, rid, "veja https://evil.example/x")
        row = ra.mock_supabase.from_("cs_roteiros").select("*").eq("id", rid).execute().data[0]
        assert row["status"] == "falha" and "saida_conteudo_proibido" in row["erro"]
        assert _events(ra, rid) == []

    def test_a_good_output_completes_without_trimming(self, ra):
        rid = self._processando(ra)
        self._run(ra, rid, "## Capa\nTexto bom")
        row = ra.mock_supabase.from_("cs_roteiros").select("*").eq("id", rid).execute().data[0]
        assert row["status"] == "completo" and row["conteudo"] == "## Capa\nTexto bom"


class TestSeamParaOChat:
    def test_solicitar_aprovacao_roteiro_service_function(self, ra):
        rid = _roteiro(ra)
        svc = apr.make_approvals(ra.mock_supabase, store=ra.store)
        d = apr.solicitar_aprovacao_roteiro(ra.mock_supabase, ORG, rid, actor_id=None, approvals=svc)
        assert d["status"] == "pending" and d["versao"] == 1
        with pytest.raises(apr.AprovacaoRoteiroError) as e:
            apr.solicitar_aprovacao_roteiro(ra.mock_supabase, ORG, _roteiro(ra, status="falha"), approvals=svc)
        assert e.value.codigo == "roteiro_incompleto" and e.value.status == 409

    def test_service_decision_maps_organ_errors(self, ra):
        rid = _roteiro(ra)
        svc = RoteiroService(ra.mock_supabase, ORG, str(uuid.uuid4()), cfg=settings, approvals=apr.make_approvals(ra.mock_supabase, store=ra.store))
        asyncio.run(svc.aprovar(rid, 1))
        with pytest.raises(RoteiroError) as e:
            asyncio.run(svc.aprovar(rid, 1))
        assert e.value.status == 409 and e.value.detail["code"] == "ja_decidido"


class TestMigration:
    def test_events_are_append_only_and_service_only(self):
        assert "apr_events_append_only" in SQL and "COMMENT ON TABLE social_wiring.apr_events IS 'tier:org'" in SQL
        assert "REVOKE EXECUTE ON FUNCTION social_wiring.apr_record(UUID, JSONB) FROM PUBLIC, anon, authenticated" in SQL
        assert "REVOKE ALL ON social_wiring.apr_events FROM PUBLIC, anon, authenticated" in SQL

    def test_papel_agendado_is_admitted_and_nothing_is_dropped(self):
        assert "'gravacao', 'agendado', 'postado', 'cancelado'" in SQL_PAPEL and "'proposta_aceite', 'final'" in SQL_PAPEL


class TestAuth:
    @pytest.mark.parametrize(
        "method,path,kw",
        [
            ("get", f"{BASE}/{uuid.uuid4()}/aprovacao", {}),
            ("post", f"{BASE}/{uuid.uuid4()}/aprovacao/solicitar", {}),
            ("post", f"{BASE}/{uuid.uuid4()}/aprovar", {"json": {"versao": 1}}),
            ("post", f"{BASE}/{uuid.uuid4()}/reprovar", {"json": {"versao": 1, "motivo": "m"}}),
        ],
    )
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)
