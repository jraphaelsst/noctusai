"""Editorial governance of knowledge collections (project seed-editorial-workflow, E5).

Store-level (Fake knowledge store over the Fake editorial store — the SQL side is
proven by the ``agents-editorial-*`` ``verify_db_guards`` probes) plus the HTTP
surface: strict 401s, org + grant enforcement, and the publish round-trip through
``/api/studio/editorial``.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.stores._db_errors import StudioConflict
from app.stores.knowledge_editorial import CLAUDE_DRAFT_AUTHOR_ID
from app.stores.studio_knowledge import CollectionInput, DocumentInput, FakeStudioKnowledgeStore
from noctusai_lib.domain.editorial import FakeEditorialStore
from tests.studio.ke.conftest import (  # noqa: F401
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    ke_client,
    seed_org_role,
    seed_studio_agent,
)

ORG, AGENT, USER = uuid4(), uuid4(), uuid4()
EDITOR, SECURITY, PUBLISHER = uuid4(), uuid4(), uuid4()
BASE = "/api/studio/agents/isaia"


def _upsert(store, col, slug="d", conteudo="texto de referencia", *, author=USER, **kw):
    return store.upsert_document_by_source_sha(
        ORG, AGENT, col, slug=slug, titulo=slug.upper(), tipo="fonte", resumo=None, proveniencia=None,
        conteudo=conteudo, author_id=author, **kw,
    )


def _store_with_corpus():
    """A collection with three live documents and one archived one."""
    store = FakeStudioKnowledgeStore()
    col = store.create_collection(ORG, AGENT, CollectionInput(slug="nnl", nome="NnL"))
    for slug, text in (("a", "limiar alfa"), ("b", "limiar beta"), ("c", "outra coisa")):
        store.create_document(ORG, AGENT, col.id, DocumentInput(slug=slug, titulo=slug, tipo="fonte", conteudo=text), USER)
    old = store.create_document(ORG, AGENT, col.id, DocumentInput(slug="z", titulo="z", tipo="fonte", conteudo="limiar velho"), USER)
    store.update_document(ORG, AGENT, old.id, author_id=USER, ativo=False)
    return store, col


def _visible(store, col):
    hits = sorted(r.slug for r in store.search(ORG, AGENT, "limiar"))
    live = store.count_documents(ORG, AGENT, col.id)
    listed = sorted((d.slug, d.ativo, d.conteudo) for d in store.list_documents(ORG, AGENT, col.id)[0])
    return hits, live, listed


class TestBackfill:
    def test_governing_a_collection_changes_nothing_retrieval_returns(self):
        store, col = _store_with_corpus()
        before = _visible(store, col)
        assert before[0] == ["a", "b"] and before[1] == 3

        store.update_collection(ORG, AGENT, col.id, requer_revisao=True, author_id=USER)

        assert _visible(store, col) == before  # search, live count and the admin list: identical
        assert store.get_collection(ORG, AGENT, col.id).requer_revisao is True
        doc = store.get_document_by_slug(ORG, AGENT, "a")
        assert doc.editorial_state == "publicado" and doc.editorial_item_id is not None
        assert store.read_document_part(ORG, AGENT, "a").conteudo == "limiar alfa"
        archived = store.get_document_by_slug(ORG, AGENT, "z", include_inactive=True)
        assert archived.editorial_state == "arquivado" and archived.ativo is False

    def test_governing_is_idempotent_and_needs_an_actor(self):
        store, col = _store_with_corpus()
        with pytest.raises(StudioConflict) as exc:
            store.update_collection(ORG, AGENT, col.id, requer_revisao=True)
        assert exc.value.code == "editorial_actor_required"
        store.update_collection(ORG, AGENT, col.id, requer_revisao=True, author_id=USER)
        before = _visible(store, col)
        store.update_collection(ORG, AGENT, col.id, requer_revisao=True, author_id=USER)
        assert _visible(store, col) == before

    def test_a_governed_collection_cannot_be_freed(self):
        store, col = _store_with_corpus()
        store.update_collection(ORG, AGENT, col.id, requer_revisao=True, author_id=USER)
        with pytest.raises(StudioConflict) as exc:
            store.update_collection(ORG, AGENT, col.id, requer_revisao=False, author_id=USER)
        assert exc.value.code == "cannot_ungovern"


class TestGovernedWrites:
    def _governed(self):
        store = FakeStudioKnowledgeStore()
        col = store.create_collection(ORG, AGENT, CollectionInput(slug="nnl", nome="NnL"))
        store.update_collection(ORG, AGENT, col.id, requer_revisao=True, author_id=USER)
        return store, col

    def test_import_into_a_governed_collection_is_a_hidden_draft(self):
        store, col = self._governed()
        record, outcome = _upsert(store, col.id, author=None)
        assert outcome == "created"
        assert record.ativo is False and record.editorial_state == "rascunho"
        assert store.search(ORG, AGENT, "referencia") == []
        assert store.find_document_by_slug(ORG, AGENT, "d") is None
        # authored by the machine identity, so a human can approve it
        v = store._editorial.list_versions(ORG, record.editorial_item_id)[0]
        assert v.author_id == CLAUDE_DRAFT_AUTHOR_ID

    def test_reimport_of_identical_content_is_unchanged(self):
        store, col = self._governed()
        _upsert(store, col.id)
        assert _upsert(store, col.id)[1] == "unchanged"

    def test_published_version_keeps_serving_while_a_new_draft_waits(self):
        store, col = self._governed()
        doc, _ = _upsert(store, col.id, conteudo="versao um referencia")
        self._publish(store, doc.editorial_item_id)
        assert [r.slug for r in store.search(ORG, AGENT, "referencia")] == ["d"]

        record, outcome = _upsert(store, col.id, conteudo="versao dois referencia")
        assert outcome == "updated"
        assert record.editorial_state == "rascunho" and record.conteudo == "versao um referencia"
        assert store.read_document_part(ORG, AGENT, "d").conteudo == "versao um referencia"

        self._publish(store, doc.editorial_item_id)
        assert store.read_document_part(ORG, AGENT, "d").conteudo == "versao dois referencia"

    def test_a_document_in_review_refuses_a_new_version(self):
        store, col = self._governed()
        doc, _ = _upsert(store, col.id, conteudo="um")
        store._editorial.apply(
            org_id=ORG, item_id=doc.editorial_item_id, action="submit", actor_id=USER, grants=["editorial:editar"],
        )
        with pytest.raises(StudioConflict) as exc:
            _upsert(store, col.id, conteudo="dois")
        assert exc.value.code == "editorial_in_review"

    def test_admin_patch_of_a_governed_document_is_refused(self):
        store, col = self._governed()
        doc, _ = _upsert(store, col.id)
        for kwargs in ({"conteudo": "outro"}, {"ativo": True}, {"titulo": "T"}):
            with pytest.raises(StudioConflict) as exc:
                store.update_document(ORG, AGENT, doc.id, author_id=USER, **kwargs)
            assert exc.value.code == "editorial_governed"
        assert store.search(ORG, AGENT, "referencia") == []  # activation was NOT possible

    def test_package_sync_boundary_never_drafts_and_never_bypasses(self):
        store, col = self._governed()
        # governed collection: refused, nothing created
        with pytest.raises(StudioConflict) as exc:
            _upsert(store, col.id, editorial=False)
        assert exc.value.code == "editorial_governed"
        assert store.find_document_by_slug(ORG, AGENT, "d", include_inactive=True) is None
        # ungoverned (package) collection: live immediately, exactly as before
        free = store.create_collection(ORG, AGENT, CollectionInput(slug="projeto-x", nome="X"))
        record, outcome = _upsert(store, free.id, slug="pkg", editorial=False)
        assert outcome == "created" and record.ativo is True and record.editorial_item_id is None
        assert _upsert(store, free.id, slug="pkg", editorial=False)[1] == "unchanged"

    def test_package_sync_refuses_a_governed_document_even_in_another_flagged_state(self):
        store, col = self._governed()
        doc, _ = _upsert(store, col.id)
        with pytest.raises(StudioConflict) as exc:
            _upsert(store, col.id, conteudo="mudou", editorial=False)
        assert exc.value.code == "editorial_governed"
        assert store.get_document(ORG, AGENT, doc.id).editorial_state == "rascunho"

    @staticmethod
    def _publish(store, item_id):
        e = store._editorial
        state = e.get_item(ORG, item_id).state
        if state == "rascunho":
            e.apply(org_id=ORG, item_id=item_id, action="submit", actor_id=USER, grants=["editorial:editar"])
        e.apply(org_id=ORG, item_id=item_id, action="approve_editorial", actor_id=EDITOR, grants=["editorial:revisar"])
        e.apply(org_id=ORG, item_id=item_id, action="approve_security", actor_id=SECURITY, grants=["editorial:revisar_seguranca"])
        e.apply(org_id=ORG, item_id=item_id, action="publish", actor_id=PUBLISHER, grants=["editorial:publicar"])


class TestEditorialHttp:
    EP = "/api/studio/editorial"

    def test_unauthenticated_is_strictly_401(self, ke_client):
        for method, path in (("get", ""), ("get", f"/{uuid4()}"), ("post", ""), ("post", f"/{uuid4()}/transitions")):
            r = getattr(ke_client.raw(), method)(f"{self.EP}{path}", **({"json": {}} if method == "post" else {}))
            assert r.status_code == 401, (method, path, r.status_code)

    def test_non_admin_member_is_403_and_never_reaches_the_store(self, ke_client):
        seed_org_role(ke_client, role="member")
        assert ke_client.get(self.EP).status_code == 403

    def test_a_governed_draft_goes_live_only_through_the_workflow(self, ke_client):
        seed_org_role(ke_client, role="owner")
        agent = seed_studio_agent(ke_client)
        k = ke_client.stores.knowledge
        col = ke_client.post(f"{BASE}/knowledge", json={"slug": "nnl", "nome": "NnL"}).json()
        assert ke_client.patch(f"{BASE}/knowledge/{col['id']}", json={"requer_revisao": True}).status_code == 200
        assert ke_client.get(f"{BASE}/knowledge").json()["colecoes"][0]["requer_revisao"] is True

        r = ke_client.post(
            f"{BASE}/knowledge/{col['id']}/documents/batch",
            json={"documentos": [{"slug": "d", "titulo": "D", "tipo": "fonte", "conteudo": "limiar referencia"}]},
        )
        assert r.status_code == 200 and r.json()["criados"] == 1
        assert k.search(DEFAULT_ORG_ID, agent.id, "limiar") == []

        item_id = next(i.id for i in ke_client.stores.editorial.list_items(DEFAULT_ORG_ID, kind="knowledge_document"))
        # no grants yet: the router derives them server-side and refuses
        r = ke_client.post(f"{self.EP}/{item_id}/transitions", json={"action": "submit"})
        assert r.status_code == 403
        # PATCH of the governed document through the Studio route is refused too
        doc_id = ke_client.get(f"{BASE}/knowledge/{col['id']}/documents").json()["items"][0]["id"]
        assert ke_client.patch(f"{BASE}/documents/{doc_id}", json={"ativo": True}).status_code == 409

    def test_grants_are_org_scoped_by_membership_not_body(self, ke_client):
        seed_org_role(ke_client, role="owner")
        ke_client.stores.permissions._grants.add((str(DEFAULT_USER_ID), "editorial:editar"))
        # an extra `grants` field in the body can never grant anything
        r = ke_client.post(self.EP + "/", json={"kind": "x", "ref": "r", "content": {"a": 1}, "grants": ["editorial:publicar"]})
        assert r.status_code == 422
