"""Wave-1 security review (H1, M3, M4, L4, L5, L6, import revisions) and
compliance review (#1 typed 23505/23503, #2 case_in_use, #3 current-hash
seam, #4 embedded results, #5 gate factory, #8 find_document_by_slug, #9
typed schemas) for the knowledge + evals slice — plus the parametrized auth
boundary over EVERY write route and the foreign-id 404s (strict ``==``).

Real-store tests use a recording double of the *Supabase client* (an
external service) that can RAISE the ``APIError`` shape supabase-py raises —
never a patch of our own code.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.routers.studio_evals_router import get_current_hash_dep, get_eval_scheduler_dep
from app.schemas.studio_ke import CollectionCreateRequest, DocumentCreateRequest
from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_evals import (
    EvalCaseInput,
    FakeEvalStore,
    SupabaseEvalGate,
    SupabaseEvalStore,
    get_eval_gate,
)
from app.stores.studio_knowledge import (
    CollectionInput,
    DocumentInput,
    FakeStudioKnowledgeStore,
    SupabaseStudioKnowledgeStore,
)
from app.studio.models import LIMITS, FakeEvalGate
from tests.studio.ke.conftest import DEFAULT_ORG_ID, seed_draft, seed_org_role, seed_studio_agent

ORG = uuid4()
AGENT = uuid4()
USER = uuid4()
BASE = "/api/studio/agents/isaia"
CASE = {"slug": "c1", "titulo": "C1", "entrada": "e", "criterios": {"deve": ["x"], "nao_deve": []}}


# ── recording Supabase-client double ────────────────────────────────────────


class _APIError(Exception):
    """Shape of ``postgrest.exceptions.APIError`` — supabase-py RAISES this
    on a constraint violation; it never returns empty ``data``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data
        self.count = None


class _Query:
    def __init__(self, rec, table, rpc=None):
        self._rec, self._table, self._rpc, self.calls = rec, table, rpc, []

    def __getattr__(self, name):
        def _chain(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return _chain

    def execute(self):
        self._rec.executed.append((self._table, self._rpc, list(self.calls)))
        out = self._rec.outcomes.pop(0) if self._rec.outcomes else []
        if isinstance(out, Exception):
            raise out
        return _Resp(out)


class _Client:
    def __init__(self, outcomes):
        self.outcomes, self.executed = list(outcomes), []

    def schema(self, name):
        return self

    def table(self, name):
        return _Query(self, name)

    def rpc(self, fn, params):
        return _Query(self, None, (fn, params))


def _doc_row(**over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": str(ORG), "collection_id": str(uuid4()), "agent_id": str(AGENT),
        "slug": "d", "titulo": "D", "tipo": "fonte", "proveniencia": {}, "resumo": None, "conteudo": "x",
        "source_sha": "s", "ativo": True, "created_at": "t", "updated_at": "t",
    }
    row.update(over)
    return row


def _run_row(**over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": str(ORG), "agent_id": str(AGENT), "version_id": str(uuid4()),
        "compiled_hash": "sha256:x", "status": "pendente", "total": 1, "aprovados": 0, "score": None,
        "limiar": 0.8, "started_by": str(USER), "started_at": None, "finished_at": None, "erro": None,
        "created_at": "t", "updated_at": "t", "completa": True,
    }
    row.update(over)
    return row


# ── H1 — complete vs subset runs ────────────────────────────────────────────


class TestCompleteRuns:
    def test_omitted_case_ids_is_complete_subset_is_not(self):
        store = FakeEvalStore()
        c1 = store.create_case(ORG, AGENT, EvalCaseInput(slug="a", titulo="A", entrada="e", criterios={"deve": ["x"]}))
        store.create_case(ORG, AGENT, EvalCaseInput(slug="b", titulo="B", entrada="e", criterios={"deve": ["x"]}))
        v1, v2 = uuid4(), uuid4()
        full = store.create_run(ORG, AGENT, v1, compiled_hash="h", limiar=0.8, case_ids=None, started_by=USER)
        sub = store.create_run(ORG, AGENT, v2, compiled_hash="h", limiar=0.8, case_ids=[c1.id], started_by=USER)
        assert (full.completa, full.total) == (True, 2)
        assert (sub.completa, sub.total) == (False, 1)

    def test_router_exposes_completa(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        vid = seed_draft(ke_client, agent).id
        case = ke_client.post(f"{BASE}/evals/cases", json=CASE).json()
        app = ke_client.raw().app
        app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
        try:
            sub = ke_client.post(f"{BASE}/evals/runs", json={"version_id": str(vid), "case_ids": [case["id"]]})
        finally:
            app.dependency_overrides.pop(get_eval_scheduler_dep, None)
        assert sub.status_code == 202, sub.text
        assert sub.json()["completa"] is False

    def test_gate_reads_only_complete_runs(self):
        client = _Client([[]])
        assert SupabaseEvalGate(client).latest_concluded_run(ORG, uuid4()) is None
        calls = client.executed[0][2]
        assert ("eq", ("completa", True), {}) in calls
        assert ("eq", ("status", "concluida"), {}) in calls


# ── L6 — run creation: dedupe, cap, atomic RPC, 23505 ───────────────────────


class TestRunCreation:
    def test_duplicates_are_deduped(self):
        store = FakeEvalStore()
        c = store.create_case(ORG, AGENT, EvalCaseInput(slug="a", titulo="A", entrada="e", criterios={"deve": ["x"]}))
        run = store.create_run(ORG, AGENT, uuid4(), compiled_hash="h", limiar=0.8, case_ids=[c.id, c.id, c.id], started_by=USER)
        assert run.total == 1

    def test_more_than_200_ids_is_refused(self):
        with pytest.raises(ValueError):
            FakeEvalStore().create_run(
                ORG, AGENT, uuid4(), compiled_hash="h", limiar=0.8, case_ids=[uuid4() for _ in range(201)], started_by=USER,
            )

    def test_http_cap_422(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        vid = seed_draft(ke_client, agent).id
        resp = ke_client.post(f"{BASE}/evals/runs", json={"version_id": str(vid), "case_ids": [str(uuid4()) for _ in range(201)]})
        assert resp.status_code == 422

    def test_real_store_creates_run_and_results_in_one_rpc(self):
        vid, c = uuid4(), uuid4()
        run = _run_row(version_id=str(vid), completa=False)
        client = _Client([run["id"], [run]])
        rec = SupabaseEvalStore(client).create_run(
            ORG, AGENT, vid, compiled_hash="sha256:x", limiar=0.8, case_ids=[c, c], started_by=USER,
        )
        fn, params = client.executed[0][1]
        assert fn == "create_eval_run"
        assert params["p_case_ids"] == [str(c)]  # deduped before the call
        assert rec.completa is False
        # No separate insert into eval_runs / eval_results — the RPC did both.
        assert not [t for t, rpc, _ in client.executed if t in ("eval_runs", "eval_results") and rpc is None
                    and any(call[0] == "insert" for call in _)]

    def test_concurrent_run_unique_violation_is_run_in_progress(self):
        client = _Client([_APIError("23505", 'duplicate key value violates unique constraint "eval_runs_one_active_per_version_idx"')])
        with pytest.raises(StudioConflict) as exc:
            SupabaseEvalStore(client).create_run(
                ORG, AGENT, uuid4(), compiled_hash="h", limiar=0.8, case_ids=None, started_by=USER,
            )
        assert exc.value.code == "run_in_progress"

    def test_current_hash_seam_fails_closed(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        vid = seed_draft(ke_client, agent).id
        app = ke_client.raw().app
        saved = app.dependency_overrides.pop(get_current_hash_dep)
        try:
            resp = ke_client.post(f"{BASE}/evals/runs", json={"version_id": str(vid)})
        finally:
            app.dependency_overrides[get_current_hash_dep] = saved
        assert resp.status_code == 503
        assert resp.json()["code"] == "compile_unavailable"


# ── compliance #1/#2 — typed unique / FK violations ─────────────────────────


class TestTypedConstraintErrors:
    def test_real_collection_duplicate_is_slug_taken_not_500(self):
        client = _Client([_APIError("23505", "duplicate key value violates unique constraint")])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioKnowledgeStore(client).create_collection(ORG, AGENT, CollectionInput(slug="a", nome="A"))
        assert exc.value.code == "slug_taken"

    def test_real_document_duplicate_is_slug_taken(self):
        client = _Client([_APIError("23505", "duplicate key value violates unique constraint")])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioKnowledgeStore(client).create_document(
                ORG, AGENT, uuid4(), DocumentInput(slug="d", titulo="D", tipo="fonte", conteudo="x"), author_id=USER,
            )
        assert exc.value.code == "slug_taken"

    def test_real_case_duplicate_is_slug_taken(self):
        client = _Client([_APIError("23505", "duplicate key value violates unique constraint")])
        with pytest.raises(StudioConflict) as exc:
            SupabaseEvalStore(client).create_case(ORG, AGENT, EvalCaseInput(slug="a", titulo="A", entrada="e", criterios={"deve": ["x"]}))
        assert exc.value.code == "slug_taken"

    def test_real_case_delete_with_results_is_case_in_use(self):
        client = _Client([_APIError("23503", "update or delete violates foreign key constraint")])
        with pytest.raises(StudioConflict) as exc:
            SupabaseEvalStore(client).delete_case(ORG, AGENT, uuid4())
        assert exc.value.code == "case_in_use"

    def test_router_delete_case_with_results_409(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        vid = seed_draft(ke_client, agent).id
        case = ke_client.post(f"{BASE}/evals/cases", json=CASE).json()
        ke_client.stores.evals.create_run(
            DEFAULT_ORG_ID, agent.id, vid, compiled_hash="h", limiar=0.8, case_ids=None, started_by=uuid4(),
        )
        resp = ke_client.delete(f"{BASE}/evals/cases/{case['id']}")
        assert resp.status_code == 409
        assert resp.json()["code"] == "case_in_use"
        # deactivating is the supported path
        assert ke_client.patch(f"{BASE}/evals/cases/{case['id']}", json={"ativo": False}).status_code == 200

    def test_router_duplicate_case_slug_409(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        ke_client.post(f"{BASE}/evals/cases", json=CASE)
        resp = ke_client.post(f"{BASE}/evals/cases", json=CASE)
        assert resp.status_code == 409
        assert resp.json()["code"] == "slug_taken"


# ── compliance #4 — results in one embedded read, loud on a missing case ────


class TestResultsEmbedded:
    def test_single_embedded_select(self):
        run = _run_row()
        result = {
            "id": str(uuid4()), "org_id": str(ORG), "run_id": run["id"], "case_id": str(uuid4()),
            "status": "aprovado", "saida": "s", "score": 1.0,
            "veredito": [{"criterio": "x", "tipo": "deve", "ok": True, "motivo": "m"}],
            "notas_juiz": None, "duracao_ms": 5, "created_at": "t", "updated_at": "t",
            "eval_cases": {"slug": "c1", "titulo": "C1"},
        }
        client = _Client([[run], [result]])
        out = SupabaseEvalStore(client).list_results_with_cases(ORG, AGENT, UUID(run["id"]))
        assert (out[0].case_slug, out[0].case_titulo) == ("c1", "C1")
        table, _, calls = client.executed[1]
        assert table == "eval_results"
        assert ("select", ("*, eval_cases(slug, titulo)",), {}) in calls
        assert len(client.executed) == 2  # no per-result case lookups

    def test_missing_case_fails_loudly(self):
        run = _run_row()
        result = {
            "id": str(uuid4()), "org_id": str(ORG), "run_id": run["id"], "case_id": str(uuid4()),
            "status": "pendente", "created_at": "t", "updated_at": "t", "eval_cases": None,
        }
        client = _Client([[run], [result]])
        with pytest.raises(RuntimeError):
            SupabaseEvalStore(client).list_results_with_cases(ORG, AGENT, UUID(run["id"]))


# ── compliance #5 — gate factory ────────────────────────────────────────────


class TestGateFactory:
    def test_no_service_key_returns_the_fake_gate(self):
        class S:
            supabase_service_role_key = ""

        assert isinstance(get_eval_gate(S()), FakeEvalGate)


# ── M3 — caps ───────────────────────────────────────────────────────────────


class TestCaps:
    @pytest.mark.parametrize(
        "body",
        [
            {"slug": "a", "nome": "x" * (LIMITS["collection.nome"] + 1)},
            {"slug": "a", "nome": "A", "tag": "x" * (LIMITS["collection.tag"] + 1)},
            {"slug": "a", "nome": "A", "descricao": "x" * (LIMITS["collection.descricao"] + 1)},
        ],
    )
    def test_collection_caps_422(self, ke_client, body):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        assert ke_client.post(f"{BASE}/knowledge", json=body).status_code == 422

    def test_collection_cap_on_patch_422(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col = ke_client.post(f"{BASE}/knowledge", json={"slug": "a", "nome": "A"}).json()
        assert ke_client.patch(f"{BASE}/knowledge/{col['id']}", json={"tag": "x" * 13}).status_code == 422

    def test_schema_caps(self):
        with pytest.raises(ValueError):
            CollectionCreateRequest(slug="a", nome="x" * 121)
        with pytest.raises(ValueError):
            DocumentCreateRequest(slug="d", titulo="D", tipo="fonte", conteudo="x" * (LIMITS["document.conteudo"] + 1))

    def test_store_caps_without_http(self):
        store = FakeStudioKnowledgeStore()
        with pytest.raises(ValueError):
            store.create_collection(ORG, AGENT, CollectionInput(slug="a", nome="A", tag="x" * 13))
        col = store.create_collection(ORG, AGENT, CollectionInput(slug="a", nome="A"))
        with pytest.raises(ValueError):
            store.upsert_document_by_source_sha(
                ORG, AGENT, col.id, slug="d", titulo="D", tipo="fonte", resumo=None, proveniencia=None,
                conteudo="x" * (LIMITS["document.conteudo"] + 1),
            )


# ── M4 — archived documents never reach the runtime ─────────────────────────


class TestArchivedDocuments:
    def _archived(self):
        store = FakeStudioKnowledgeStore()
        col = store.create_collection(ORG, AGENT, CollectionInput(slug="a", nome="A"))
        doc = store.create_document(ORG, AGENT, col.id, DocumentInput(slug="d", titulo="D", tipo="fonte", conteudo="x"), author_id=USER)
        store.update_document(ORG, AGENT, doc.id, author_id=USER, ativo=False)
        return store, doc

    def test_by_slug_hides_archived_by_default(self):
        store, doc = self._archived()
        with pytest.raises(NotFound):
            store.get_document_by_slug(ORG, AGENT, "d")
        assert store.find_document_by_slug(ORG, AGENT, "d") is None
        assert store.get_document_by_slug(ORG, AGENT, "d", include_inactive=True).id == doc.id

    def test_kb_ler_hides_archived(self):
        store, _ = self._archived()
        with pytest.raises(NotFound):
            store.read_document_part(ORG, AGENT, "d")
        assert store.read_document_part(ORG, AGENT, "d", include_inactive=True).conteudo == "x"

    def test_real_by_slug_filters_ativo(self):
        client = _Client([[]])
        assert SupabaseStudioKnowledgeStore(client).find_document_by_slug(ORG, AGENT, "d") is None
        assert ("eq", ("ativo", True), {}) in client.executed[0][2]
        client2 = _Client([[]])
        SupabaseStudioKnowledgeStore(client2).find_document_by_slug(ORG, AGENT, "d", include_inactive=True)
        assert ("eq", ("ativo", True), {}) not in client2.executed[0][2]

    def test_admin_get_by_id_still_sees_archived(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col = ke_client.post(f"{BASE}/knowledge", json={"slug": "a", "nome": "A"}).json()
        doc = ke_client.post(
            f"{BASE}/knowledge/{col['id']}/documents", json={"slug": "d", "titulo": "D", "tipo": "fonte", "conteudo": "x"},
        ).json()
        ke_client.patch(f"{BASE}/documents/{doc['id']}", json={"ativo": False})
        resp = ke_client.get(f"{BASE}/documents/{doc['id']}")
        assert resp.status_code == 200
        assert resp.json()["ativo"] is False


# ── L4 / L5 — query handling ────────────────────────────────────────────────


class TestQueries:
    def test_list_goes_through_the_rpc_never_or_filter(self):
        client = _Client([{"total": 1, "items": [_doc_row()]}])
        docs, total = SupabaseStudioKnowledgeStore(client).list_documents(
            ORG, AGENT, uuid4(), q="a,b),titulo.eq.x", page=2, page_size=10,
        )
        assert total == 1 and len(docs) == 1
        _, rpc, calls = client.executed[0]
        assert rpc[0] == "list_knowledge_documents"
        assert rpc[1]["p_q"] == "a,b),titulo.eq.x"  # passed verbatim as a bound parameter
        assert (rpc[1]["p_limit"], rpc[1]["p_offset"]) == (10, 10)
        assert not [c for c in calls if c[0] == "or_"]

    def test_list_q_cap(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col = ke_client.post(f"{BASE}/knowledge", json={"slug": "a", "nome": "A"}).json()
        assert ke_client.get(f"{BASE}/knowledge/{col['id']}/documents", params={"q": "x" * 201}).status_code == 422
        with pytest.raises(ValueError):
            FakeStudioKnowledgeStore().list_documents(ORG, AGENT, uuid4(), q="x" * 201)

    def test_search_q_cap(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        assert ke_client.get(f"{BASE}/knowledge/search", params={"q": "x" * 513}).status_code == 422
        with pytest.raises(ValueError):
            FakeStudioKnowledgeStore().search(ORG, AGENT, "x" * 513)
        client = _Client([])
        with pytest.raises(ValueError):
            SupabaseStudioKnowledgeStore(client).search(ORG, AGENT, "x" * 513)
        assert client.executed == []  # refused before the RPC


# ── Import semantics ────────────────────────────────────────────────────────


class TestImportRevisions:
    def test_real_created_writes_an_import_revision(self):
        col = uuid4()
        row = _doc_row(collection_id=str(col))
        client = _Client([[], [row], [{}]])  # find (none) → insert doc → insert revision
        _, action = SupabaseStudioKnowledgeStore(client).upsert_document_by_source_sha(
            ORG, AGENT, col, slug="d", titulo="D", tipo="fonte", resumo=None, proveniencia=None, conteudo="x",
        )
        assert action == "created"
        table, _, calls = client.executed[2]
        assert table == "knowledge_revisions"
        payload = next(c[1][0] for c in calls if c[0] == "insert")
        assert payload["op"] == "import"

    def test_real_updated_writes_an_import_revision(self):
        col = uuid4()
        existing = _doc_row(collection_id=str(col), source_sha="old")
        client = _Client([[existing], [existing], [existing], [{}]])  # find → get → update → revision
        _, action = SupabaseStudioKnowledgeStore(client).upsert_document_by_source_sha(
            ORG, AGENT, col, slug="d", titulo="D", tipo="fonte", resumo=None, proveniencia=None, conteudo="new",
        )
        assert action == "updated"
        payload = next(c[1][0] for c in client.executed[3][2] if c[0] == "insert")
        assert payload["op"] == "import"

    def test_slug_in_other_collection_is_refused_not_moved(self):
        store = FakeStudioKnowledgeStore()
        a = store.create_collection(ORG, AGENT, CollectionInput(slug="a", nome="A"))
        b = store.create_collection(ORG, AGENT, CollectionInput(slug="b", nome="B"))
        store.upsert_document_by_source_sha(ORG, AGENT, a.id, slug="d", titulo="D", tipo="fonte", resumo=None, proveniencia=None, conteudo="1")
        with pytest.raises(StudioConflict) as exc:
            store.upsert_document_by_source_sha(ORG, AGENT, b.id, slug="d", titulo="D", tipo="fonte", resumo=None, proveniencia=None, conteudo="2")
        assert exc.value.code == "slug_in_other_collection"
        assert store.get_document_by_slug(ORG, AGENT, "d").collection_id == a.id

    def test_real_slug_in_other_collection(self):
        client = _Client([[_doc_row(collection_id=str(uuid4()))]])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioKnowledgeStore(client).upsert_document_by_source_sha(
                ORG, AGENT, uuid4(), slug="d", titulo="D", tipo="fonte", resumo=None, proveniencia=None, conteudo="x",
            )
        assert exc.value.code == "slug_in_other_collection"


# ── compliance #9 — typed response schemas ──────────────────────────────────


class TestTypedSchemas:
    def test_criterios_and_veredito_are_typed(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        vid = seed_draft(ke_client, agent).id
        case = ke_client.post(f"{BASE}/evals/cases", json={**CASE, "criterios": {"deve": ["x"]}}).json()
        assert case["criterios"] == {"deve": ["x"], "nao_deve": []}
        run = ke_client.stores.evals.create_run(
            DEFAULT_ORG_ID, agent.id, vid, compiled_hash="h", limiar=0.8, case_ids=None, started_by=uuid4(),
        )
        ke_client.stores.evals._results[run.id][0]["veredito"] = [
            {"criterio": "x", "tipo": "deve", "ok": True, "motivo": "citou"},
        ]
        body = ke_client.get(f"{BASE}/evals/runs/{run.id}").json()
        assert body["resultados"][0]["veredito"] == [{"criterio": "x", "tipo": "deve", "ok": True, "motivo": "citou"}]
        assert body["completa"] is True


# ── auth boundary over EVERY write route + foreign-id 404s ──────────────────

_U = "00000000-0000-0000-0000-000000000001"
WRITE_ROUTES = [
    ("post", f"{BASE}/knowledge", {"slug": "a", "nome": "A"}),
    ("patch", f"{BASE}/knowledge/{_U}", {"nome": "A"}),
    ("post", f"{BASE}/knowledge/{_U}/documents", {"slug": "d", "titulo": "D", "tipo": "fonte", "conteudo": "x"}),
    ("patch", f"{BASE}/documents/{_U}", {"titulo": "D"}),
    ("post", f"{BASE}/evals/cases", CASE),
    ("patch", f"{BASE}/evals/cases/{_U}", {"titulo": "x"}),
    ("delete", f"{BASE}/evals/cases/{_U}", None),
    ("post", f"{BASE}/evals/runs", {"version_id": _U}),
    ("post", f"{BASE}/evals/runs/{_U}/cancel", None),
]


class TestWriteAuthBoundary:
    @pytest.mark.parametrize("method, path, body", WRITE_ROUTES)
    def test_unauthenticated_is_401(self, ke_client, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(ke_client.raw(), method)(path, **kwargs)
        assert resp.status_code == 401

    @pytest.mark.parametrize("method, path, body", WRITE_ROUTES)
    def test_member_is_403(self, ke_client, method, path, body):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(ke_client, method)(path, **kwargs)
        assert resp.status_code == 403


class TestForeignIds:
    """Ids of ANOTHER agent of the same org, and of another org, are 404 —
    never 403, never a write."""

    def _two_agents(self, ke_client):
        seed_org_role(ke_client, role="owner")
        mine = seed_studio_agent(ke_client, key="isaia")
        other = seed_studio_agent(ke_client, key="outro")
        col = ke_client.post("/api/studio/agents/outro/knowledge", json={"slug": "a", "nome": "A"}).json()
        doc = ke_client.post(
            f"/api/studio/agents/outro/knowledge/{col['id']}/documents",
            json={"slug": "d", "titulo": "D", "tipo": "fonte", "conteudo": "x"},
        ).json()
        case = ke_client.post("/api/studio/agents/outro/evals/cases", json=CASE).json()
        vid = seed_draft(ke_client, other).id
        run = ke_client.stores.evals.create_run(
            DEFAULT_ORG_ID, other.id, vid, compiled_hash="h", limiar=0.8, case_ids=None, started_by=uuid4(),
        )
        return mine, {"col": col["id"], "doc": doc["id"], "case": case["id"], "version": str(vid), "run": str(run.id)}

    def test_other_agents_ids_404(self, ke_client):
        _, ids = self._two_agents(ke_client)
        cases = [
            ("patch", f"{BASE}/knowledge/{ids['col']}", {"nome": "hijack"}, "collection_not_found"),
            ("get", f"{BASE}/knowledge/{ids['col']}/documents", None, "collection_not_found"),
            ("post", f"{BASE}/knowledge/{ids['col']}/documents",
             {"slug": "z", "titulo": "Z", "tipo": "fonte", "conteudo": "z"}, "collection_not_found"),
            ("get", f"{BASE}/documents/{ids['doc']}", None, "document_not_found"),
            ("patch", f"{BASE}/documents/{ids['doc']}", {"titulo": "hijack"}, "document_not_found"),
            ("get", f"{BASE}/documents/{ids['doc']}/revisions", None, "document_not_found"),
            ("patch", f"{BASE}/evals/cases/{ids['case']}", {"titulo": "hijack"}, "eval_case_not_found"),
            ("delete", f"{BASE}/evals/cases/{ids['case']}", None, "eval_case_not_found"),
            ("post", f"{BASE}/evals/runs", {"version_id": ids["version"]}, "version_not_found"),
            ("get", f"{BASE}/evals/runs/{ids['run']}", None, "eval_run_not_found"),
            ("post", f"{BASE}/evals/runs/{ids['run']}/cancel", None, "eval_run_not_found"),
        ]
        for method, path, body, code in cases:
            kwargs = {"json": body} if body is not None else {}
            resp = getattr(ke_client, method)(path, **kwargs)
            assert resp.status_code == 404, (method, path, resp.text)
            assert resp.json()["code"] == code, (method, path)

    def test_foreign_case_id_in_a_run_404(self, ke_client):
        mine, ids = self._two_agents(ke_client)
        my_vid = seed_draft(ke_client, mine).id
        resp = ke_client.post(f"{BASE}/evals/runs", json={"version_id": str(my_vid), "case_ids": [ids["case"]]})
        assert resp.status_code == 404
        assert resp.json()["code"] == "eval_case_not_found"

    def test_other_org_sees_nothing(self, ke_client):
        from tests.studio.ke.conftest import bind_user

        _, ids = self._two_agents(ke_client)
        other_org, other_user = uuid4(), uuid4()
        bind_user(ke_client, user_id=other_user, org_id=other_org)
        seed_org_role(ke_client, user_id=other_user, org_id=other_org, role="owner")
        seed_studio_agent(ke_client, key="outro", org_id=other_org)
        resp = ke_client.get(f"/api/studio/agents/outro/documents/{ids['doc']}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "document_not_found"
        resp = ke_client.patch(f"/api/studio/agents/outro/evals/cases/{ids['case']}", json={"titulo": "x"})
        assert resp.status_code == 404
