"""Agent Packages stores (017) — the Fake's contract, and the Real store's
query shapes through a recording client double (the Supabase mock neither
fills server defaults nor mints UUID ids, so it cannot stand in for Postgres
on an INSERT)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from datetime import datetime, timezone
from typing import Any

from app.stores.agent_packages import (
    FakeAgentPackageStore,
    LearningInput,
    SupabaseAgentPackageStore,
    learning_row_sha,
)
from app.stores.errors import NotFound
from app.stores._db_errors import StudioConflict
from app.stores.studio_definitions import SupabaseStudioDefinitionStore, VersionImmutable

ORG, AGENT = uuid4(), uuid4()


def _learning(texto="Texto", data="2026-10-03", **kw) -> LearningInput:
    return LearningInput(data=data, tipo=kw.pop("tipo", "pitfall"), texto=texto, evidencia="ev", **kw)


@pytest.fixture
def store():
    return FakeAgentPackageStore()


class TestRowSha:
    def test_is_whitespace_normalised_and_order_sensitive(self):
        assert learning_row_sha("d", "a  b\nc") == learning_row_sha(" d ", "a b c")
        assert learning_row_sha("d", "x") != learning_row_sha("e", "x")

    def test_matches_the_build_tool_formula(self):
        import hashlib

        assert learning_row_sha("2026-10-03", "um dois") == hashlib.sha256(b"2026-10-03\num dois").hexdigest()


class TestSources:
    def test_upsert_is_keyed_on_agent_project_path(self, store):
        doc = uuid4()
        a = store.upsert_source(ORG, AGENT, "limiar-app", path="docs/a.md", sha256="a" * 64, tipo="doc", document_id=doc)
        b = store.upsert_source(ORG, AGENT, "limiar-app", path="docs/a.md", sha256="b" * 64, tipo="doc", document_id=doc)
        assert a.id == b.id or a.path == b.path
        rows = store.list_sources(ORG, AGENT, "limiar-app")
        assert [(r.path, r.sha256) for r in rows] == [("docs/a.md", "b" * 64)]

    def test_projects_are_isolated_and_deletion_is_scoped(self, store):
        for project in ("limiar-app", "outro"):
            store.upsert_source(ORG, AGENT, project, path="docs/a.md", sha256="a" * 64, tipo="doc", document_id=None)
        store.upsert_source(ORG, AGENT, "limiar-app", path="src/b.ts", sha256="c" * 64, tipo="codigo", document_id=None)
        assert store.delete_sources(ORG, AGENT, "limiar-app", ["docs/a.md", "nao-existe.md"]) == 1
        left = {(r.project_slug, r.path) for r in store.list_sources(ORG, AGENT)}
        assert left == {("outro", "docs/a.md"), ("limiar-app", "src/b.ts")}

    def test_delete_batches_a_large_path_list(self, store):
        for i in range(120):
            store.upsert_source(ORG, AGENT, "p", path=f"f{i}.md", sha256="a" * 64, tipo="doc", document_id=None)
        assert store.delete_sources(ORG, AGENT, "p", [f"f{i}.md" for i in range(120)]) == 120
        assert store.list_sources(ORG, AGENT, "p") == []

    def test_a_bad_tipo_is_a_value_error(self, store):
        with pytest.raises(ValueError):
            store.upsert_source(ORG, AGENT, "p", path="a", sha256="a" * 64, tipo="binario", document_id=None)

    def test_org_isolation(self, store):
        store.upsert_source(ORG, AGENT, "p", path="a.md", sha256="a" * 64, tipo="doc", document_id=None)
        assert store.list_sources(uuid4(), AGENT) == []


class TestLearnings:
    def test_insert_dedupes_across_calls_and_within_a_batch(self, store):
        inserted, dup = store.insert_learnings(ORG, AGENT, "limiar-app", [_learning("a"), _learning("a"), _learning("b")])
        assert (len(inserted), dup) == (2, 1)
        inserted2, dup2 = store.insert_learnings(ORG, AGENT, "limiar-app", [_learning("a"), _learning("c")])
        assert ([r.texto for r in inserted2], dup2) == (["c"], 1)
        assert len(store.list_learnings(ORG, AGENT)) == 3

    def test_dedupe_is_per_agent(self, store):
        store.insert_learnings(ORG, AGENT, "p", [_learning("a")])
        inserted, dup = store.insert_learnings(ORG, uuid4(), "p", [_learning("a")])
        assert (len(inserted), dup) == (1, 0)

    def test_new_rows_start_in_novo_review_state(self, store):
        (rec,), _ = store.insert_learnings(ORG, AGENT, "p", [_learning("a", row_status="absorvido")])
        assert (rec.status, rec.row_status, rec.reviewed_by, rec.review_note) == ("novo", "absorvido", None, None)

    def test_review_sets_status_note_reviewer_and_filters_work(self, store):
        (rec,), _ = store.insert_learnings(ORG, AGENT, "p", [_learning("a")])
        reviewer = uuid4()
        out = store.review_learning(ORG, AGENT, rec.id, status="aceito", note="ok", reviewer=reviewer)
        assert (out.status, out.review_note, out.reviewed_by) == ("aceito", "ok", reviewer)
        assert out.reviewed_at is not None and out.texto == "a"
        assert [r.id for r in store.list_learnings(ORG, AGENT, status="aceito")] == [rec.id]
        assert store.list_learnings(ORG, AGENT, status="descartado") == []
        assert store.list_learnings(ORG, AGENT, project_slug="outro") == []

    def test_review_of_a_foreign_row_is_not_found(self, store):
        (rec,), _ = store.insert_learnings(ORG, AGENT, "p", [_learning("a")])
        for org, agent in ((uuid4(), AGENT), (ORG, uuid4())):
            with pytest.raises(NotFound):
                store.review_learning(org, agent, rec.id, status="aceito", note=None, reviewer=None)
            with pytest.raises(NotFound):
                store.get_learning(org, agent, rec.id)

    @pytest.mark.parametrize("bad", [
        {"tipo": "opinion"}, {"row_status": "aceito"}, {"texto": ""}, {"texto": "x" * 8001}, {"data": "d" * 41},
    ])
    def test_validation_mirrors_the_017_checks(self, store, bad):
        kw = {"data": "2026-10-03", "tipo": "pitfall", "texto": "t", "evidencia": "", "row_status": "novo", **bad}
        with pytest.raises(ValueError):
            store.insert_learnings(ORG, AGENT, "p", [LearningInput(**kw)])

    def test_review_rejects_an_unknown_status(self, store):
        (rec,), _ = store.insert_learnings(ORG, AGENT, "p", [_learning("a")])
        with pytest.raises(ValueError):
            store.review_learning(ORG, AGENT, rec.id, status="publicado", note=None, reviewer=None)


# ── Real store: query shapes ────────────────────────────────────────────────


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, rec: "_Recorder", table: str) -> None:
        self._rec, self._table, self.calls = rec, table, []

    def __getattr__(self, name):
        def _chain(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return _chain

    def execute(self):
        self._rec.executed.append((self._table, list(self.calls)))
        out = self._rec.outcomes.pop(0) if self._rec.outcomes else []
        if isinstance(out, Exception):
            raise out
        return _Resp(out)


class _Recorder:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes, self.executed = list(outcomes), []

    def schema(self, name: str):
        assert name == "agents"
        return self

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def ops(self, table: str) -> list[list[tuple]]:
        return [calls for t, calls in self.executed if t == table]


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc).isoformat()


def _learning_row(sha: str, **kw) -> dict:
    return {
        "id": str(uuid4()), "org_id": str(ORG), "agent_id": str(AGENT), "project_slug": "p", "row_sha": sha,
        "data": "2026-10-03", "tipo": "pitfall", "texto": "t", "evidencia": "", "row_status": "novo",
        "status": "novo", "review_note": None, "reviewed_by": None, "reviewed_at": None, "created_at": NOW, **kw,
    }


class TestRealStoreShapes:
    def test_insert_learnings_is_an_ignore_duplicates_upsert_on_agent_row_sha(self):
        a, b = _learning("a"), _learning("b")
        sha_a, sha_b = learning_row_sha(a.data, a.texto), learning_row_sha(b.data, b.texto)
        client = _Recorder([_learning_row(sha_a)])  # the DB returns ONLY the rows it inserted
        inserted, dup = SupabaseAgentPackageStore(client).insert_learnings(ORG, AGENT, "p", [a, b, a])
        (calls,) = client.ops("agent_learnings")
        (name, args, kwargs), = calls
        assert name == "upsert"
        assert kwargs == {"on_conflict": "agent_id,row_sha", "ignore_duplicates": True}
        assert [r["row_sha"] for r in args[0]] == [sha_a, sha_b]  # in-batch duplicate dropped client-side
        assert all(r["org_id"] == str(ORG) and r["agent_id"] == str(AGENT) for r in args[0])
        assert ([r.row_sha for r in inserted], dup) == ([sha_a], 2)

    def test_insert_learnings_chunks_large_pushes(self):
        items = [_learning(f"t{i}") for i in range(250)]
        client = _Recorder([], [], [])
        SupabaseAgentPackageStore(client).insert_learnings(ORG, AGENT, "p", items)
        assert [len(calls[0][1][0]) for calls in client.ops("agent_learnings")] == [100, 100, 50]

    def test_upsert_source_conflicts_on_the_ledger_key_and_never_writes_foreign_columns(self):
        doc = uuid4()
        row = {"id": str(uuid4()), "org_id": str(ORG), "agent_id": str(AGENT), "project_slug": "p", "path": "a.md",
               "sha256": "a" * 64, "tipo": "doc", "document_id": str(doc), "synced_at": NOW}
        client = _Recorder([row])
        rec = SupabaseAgentPackageStore(client).upsert_source(
            ORG, AGENT, "p", path="a.md", sha256="a" * 64, tipo="doc", document_id=doc)
        (name, args, kwargs), = client.ops("agent_project_sources")[0]
        assert (name, kwargs) == ("upsert", {"on_conflict": "agent_id,project_slug,path"})
        assert set(args[0]) == {"org_id", "agent_id", "project_slug", "path", "sha256", "tipo", "document_id", "synced_at"}
        assert rec.document_id == doc

    def test_delete_sources_filters_org_agent_project_and_batches_the_in_list(self):
        paths = [f"f{i}.md" for i in range(120)]
        client = _Recorder([{"id": "x"}] * 50, [{"id": "x"}] * 50, [{"id": "x"}] * 20)
        removed = SupabaseAgentPackageStore(client).delete_sources(ORG, AGENT, "p", paths)
        assert removed == 120
        for calls in client.ops("agent_project_sources"):
            names = [c[0] for c in calls]
            assert names[0] == "delete" and names.count("eq") == 3 and names[-1] == "in_"
            assert len(calls[-1][1][1]) <= 50

    def test_review_scopes_the_update_by_org_agent_and_id(self):
        sha = "a" * 64
        client = _Recorder([_learning_row(sha, status="aceito", review_note="ok")])
        out = SupabaseAgentPackageStore(client).review_learning(
            ORG, AGENT, uuid4(), status="aceito", note="ok", reviewer=uuid4())
        calls = client.ops("agent_learnings")[0]
        assert calls[0][0] == "update" and [c[0] for c in calls].count("eq") == 3
        assert set(calls[0][1][0]) == {"status", "review_note", "reviewed_by", "reviewed_at"}
        assert out.status == "aceito"

    def test_review_of_nothing_is_not_found(self):
        with pytest.raises(NotFound):
            SupabaseAgentPackageStore(_Recorder([])).review_learning(
                ORG, AGENT, uuid4(), status="aceito", note=None, reviewer=None)

    def test_a_db_check_violation_maps_to_value_error_not_a_500(self):
        class _Api(Exception):
            code, message = "23514", "violates check constraint"

        client = _Recorder(_Api())
        with pytest.raises(ValueError):
            SupabaseAgentPackageStore(client).insert_learnings(ORG, AGENT, "p", [_learning("a")])

    def test_the_kind_immutability_trigger_maps_to_a_409_code(self):
        class _Api(Exception):
            code, message = "P0001", "kind_immutable"

        with pytest.raises(StudioConflict) as exc:
            from app.stores._db_errors import exec_query

            class _Q:
                def execute(self):
                    raise _Api()

            exec_query(_Q())
        assert exc.value.code == "kind_immutable"


class TestRealDefinitionStorePackageShapes:
    def test_set_package_tree_upserts_on_version_id(self):
        client = _Recorder([{"id": "x"}])
        vid = uuid4()
        SupabaseStudioDefinitionStore(client).set_package_tree(
            ORG, AGENT, vid, [{"caminho": "a.md", "conteudo": "x", "extra": "dropped"}])
        (name, args, kwargs), = client.ops("agent_package_trees")[0]
        assert (name, kwargs) == ("upsert", {"on_conflict": "version_id"})
        assert args[0] == {"org_id": str(ORG), "agent_id": str(AGENT), "version_id": str(vid),
                           "files": [{"caminho": "a.md", "conteudo": "x"}]}

    def test_set_package_tree_on_a_published_version_is_version_immutable(self):
        class _Api(Exception):
            code, message = "P0001", "version_immutable"

        with pytest.raises(VersionImmutable):
            SupabaseStudioDefinitionStore(_Recorder(_Api())).set_package_tree(ORG, AGENT, uuid4(), [])

    def test_get_package_tree_none_when_absent_and_scoped_by_org(self):
        client = _Recorder([], [{"files": [{"caminho": "a", "conteudo": "b"}]}])
        store = SupabaseStudioDefinitionStore(client)
        assert store.get_package_tree(ORG, uuid4()) is None
        assert store.get_package_tree(ORG, uuid4()) == [{"caminho": "a", "conteudo": "b"}]
        assert [c[0] for c in client.ops("agent_package_trees")[0]].count("eq") == 2

    def test_create_studio_agent_writes_kind_and_rejects_an_unknown_one(self):
        client = _Recorder([{
            "id": str(uuid4()), "org_id": str(ORG), "key": "k", "nome": "n", "descricao": None,
            "definition_mode": "studio", "runtime": "claude_sdk", "ativo": False, "publicacao_limiar": 0.8,
            "created_at": NOW, "updated_at": NOW, "kind": "dev-advisor",
        }])
        store = SupabaseStudioDefinitionStore(client)
        rec = store.create_studio_agent(ORG, "k", "n", None, kind="dev-advisor")
        assert client.ops("agents")[0][0][1][0]["kind"] == "dev-advisor" and rec.kind == "dev-advisor"
        with pytest.raises(ValueError):
            store.create_studio_agent(ORG, "k2", "n", None, kind="advisor")

    def test_update_draft_accepts_package_identity_and_validates_it(self):
        store = SupabaseStudioDefinitionStore(_Recorder([]))
        with pytest.raises(ValueError):
            store.update_draft(ORG, uuid4(), {"versao_semver": "v1"})
        with pytest.raises(ValueError):
            store.update_draft(ORG, uuid4(), {"package_sha": "XYZ"})
