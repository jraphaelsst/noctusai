"""``FakeStudioKnowledgeStore`` behaviour: search ordering, paging
boundaries, revisions, source_sha idempotency (contract §B2/§D3/§E3)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores.errors import NotFound
from app.stores.studio_knowledge import (
    CollectionInput,
    DocumentInput,
    FakeStudioKnowledgeStore,
    source_sha_of,
)

ORG = uuid4()
AGENT = uuid4()
USER = uuid4()


@pytest.fixture
def store() -> FakeStudioKnowledgeStore:
    return FakeStudioKnowledgeStore()


@pytest.fixture
def collection(store: FakeStudioKnowledgeStore):
    return store.create_collection(ORG, AGENT, CollectionInput(slug="audience", nome="Audience", tag="AU"))


class TestCollections:
    def test_create_and_list(self, store, collection):
        items = store.list_collections(ORG, AGENT)
        assert [c.slug for c in items] == ["audience"]

    def test_duplicate_slug_rejected(self, store, collection):
        with pytest.raises(ValueError):
            store.create_collection(ORG, AGENT, CollectionInput(slug="audience", nome="Dup"))

    def test_foreign_collection_id_not_found(self, store, collection):
        with pytest.raises(NotFound):
            store.get_collection(ORG, AGENT, uuid4())
        other_org = uuid4()
        with pytest.raises(NotFound):
            store.get_collection(other_org, AGENT, collection.id)

    def test_update_clears_tag_when_explicitly_none(self, store, collection):
        updated = store.update_collection(ORG, AGENT, collection.id, tag=None)
        assert updated.tag is None
        assert updated.nome == "Audience"  # untouched field survives

    def test_count_documents_defaults_to_active_only(self, store, collection):
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="doc-1", titulo="Doc 1", tipo="fonte", conteudo="conteudo um"),
            author_id=USER,
        )
        inactive = store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="doc-2", titulo="Doc 2", tipo="fonte", conteudo="conteudo dois"),
            author_id=USER,
        )
        store.update_document(ORG, AGENT, inactive.id, author_id=USER, ativo=False)
        assert store.count_documents(ORG, AGENT, collection.id) == 1
        assert store.count_documents(ORG, AGENT, collection.id, ativo_only=False) == 2


class TestDocumentsAndRevisions:
    def test_create_writes_a_create_revision(self, store, collection):
        doc = store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="doc-1", titulo="Doc 1", tipo="fonte", conteudo="hello"),
            author_id=USER,
        )
        revs = store.list_revisions(ORG, AGENT, doc.id)
        assert len(revs) == 1
        assert revs[0].op == "create"
        assert revs[0].author_id == USER

    def test_update_writes_an_update_revision_newest_first(self, store, collection):
        doc = store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="doc-1", titulo="Doc 1", tipo="fonte", conteudo="hello"),
            author_id=USER,
        )
        store.update_document(ORG, AGENT, doc.id, author_id=USER, titulo="Doc 1 v2", motivo="fix typo")
        revs = store.list_revisions(ORG, AGENT, doc.id)
        assert [r.op for r in revs] == ["update", "create"]
        assert revs[0].motivo == "fix typo"

    def test_archiving_writes_an_archive_revision(self, store, collection):
        doc = store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="doc-1", titulo="Doc 1", tipo="fonte", conteudo="hello"),
            author_id=USER,
        )
        store.update_document(ORG, AGENT, doc.id, author_id=USER, ativo=False)
        revs = store.list_revisions(ORG, AGENT, doc.id)
        assert revs[0].op == "archive"

    def test_invalid_tipo_rejected(self, store, collection):
        with pytest.raises(ValueError):
            store.create_document(
                ORG, AGENT, collection.id,
                DocumentInput(slug="doc-1", titulo="Doc 1", tipo="invalido", conteudo="x"),
                author_id=USER,
            )

    def test_foreign_document_id_not_found(self, store, collection):
        with pytest.raises(NotFound):
            store.get_document(ORG, AGENT, uuid4())

    def test_list_documents_pagination_boundaries(self, store, collection):
        for i in range(5):
            store.create_document(
                ORG, AGENT, collection.id,
                DocumentInput(slug=f"doc-{i}", titulo=f"Doc {i}", tipo="fonte", conteudo="conteudo"),
                author_id=USER,
            )
        page1, total = store.list_documents(ORG, AGENT, collection.id, page=1, page_size=2)
        page2, _ = store.list_documents(ORG, AGENT, collection.id, page=2, page_size=2)
        page3, _ = store.list_documents(ORG, AGENT, collection.id, page=3, page_size=2)
        page4, _ = store.list_documents(ORG, AGENT, collection.id, page=4, page_size=2)
        assert total == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
        assert len(page4) == 0  # past the end — empty, not an error

    def test_list_documents_filters_by_tipo_and_q(self, store, collection):
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="a", titulo="Persona Alpha", tipo="fonte", conteudo="x"),
            author_id=USER,
        )
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="b", titulo="Outro documento", tipo="card", conteudo="x"),
            author_id=USER,
        )
        by_tipo, _ = store.list_documents(ORG, AGENT, collection.id, tipo="card")
        assert [d.slug for d in by_tipo] == ["b"]
        by_q, _ = store.list_documents(ORG, AGENT, collection.id, q="alpha")
        assert [d.slug for d in by_q] == ["a"]


class TestSourceShaIdempotency:
    def test_upsert_created_then_unchanged_then_updated(self, store, collection):
        record, action = store.upsert_document_by_source_sha(
            ORG, AGENT, collection.id, slug="imported", titulo="Imported", tipo="fonte",
            resumo=None, proveniencia={}, conteudo="body v1", author_id=USER,
        )
        assert action == "created"
        assert record.source_sha == source_sha_of("body v1")
        revs_after_create = store.list_revisions(ORG, AGENT, record.id)
        assert len(revs_after_create) == 1
        assert revs_after_create[0].op == "import"

        record2, action2 = store.upsert_document_by_source_sha(
            ORG, AGENT, collection.id, slug="imported", titulo="Imported", tipo="fonte",
            resumo=None, proveniencia={}, conteudo="body v1", author_id=USER,
        )
        assert action2 == "unchanged"
        assert record2.id == record.id
        # No new revision written for an unchanged re-import.
        assert len(store.list_revisions(ORG, AGENT, record.id)) == 1

        record3, action3 = store.upsert_document_by_source_sha(
            ORG, AGENT, collection.id, slug="imported", titulo="Imported v2", tipo="fonte",
            resumo=None, proveniencia={}, conteudo="body v2", author_id=USER,
        )
        assert action3 == "updated"
        assert record3.id == record.id
        assert record3.source_sha == source_sha_of("body v2")
        revs_after_update = store.list_revisions(ORG, AGENT, record.id)
        assert len(revs_after_update) == 2
        assert revs_after_update[0].op == "import"


class TestSearch:
    def test_ranks_title_matches_above_body_matches(self, store, collection):
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="a", titulo="Reels sobre reciclagem", tipo="fonte", conteudo="conteudo neutro"),
            author_id=USER,
        )
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="b", titulo="Outro assunto", tipo="fonte", conteudo="falamos sobre reels aqui"),
            author_id=USER,
        )
        results = store.search(ORG, AGENT, "reels")
        assert [r.slug for r in results] == ["a", "b"]

    def test_inactive_documents_excluded(self, store, collection):
        doc = store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="a", titulo="Reels tutorial", tipo="fonte", conteudo="x"),
            author_id=USER,
        )
        store.update_document(ORG, AGENT, doc.id, author_id=USER, ativo=False)
        assert store.search(ORG, AGENT, "reels") == []

    def test_colecao_filter_scopes_by_collection_slug(self, store, collection):
        other = store.create_collection(ORG, AGENT, CollectionInput(slug="knowledge", nome="Knowledge"))
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="a", titulo="Reels tutorial", tipo="fonte", conteudo="x"),
            author_id=USER,
        )
        store.create_document(
            ORG, AGENT, other.id,
            DocumentInput(slug="b", titulo="Reels avancado", tipo="fonte", conteudo="x"),
            author_id=USER,
        )
        results = store.search(ORG, AGENT, "reels", colecao="knowledge")
        assert [r.slug for r in results] == ["b"]

    def test_no_match_returns_empty(self, store, collection):
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="a", titulo="Reels tutorial", tipo="fonte", conteudo="x"),
            author_id=USER,
        )
        assert store.search(ORG, AGENT, "inexistente") == []


class TestReadDocumentPart:
    def test_short_document_is_a_single_page(self, store, collection):
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="short", titulo="Short", tipo="fonte", conteudo="paragrafo unico"),
            author_id=USER,
        )
        part = store.read_document_part(ORG, AGENT, "short")
        assert part.parte == 1
        assert part.total_partes == 1
        assert part.conteudo == "paragrafo unico"

    def test_splits_on_paragraph_boundaries_and_pages_are_within_max_chars(self, store, collection):
        paragraphs = [f"Paragrafo numero {i} " + ("x" * 40) for i in range(20)]
        conteudo = "\n\n".join(paragraphs)
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="long", titulo="Long", tipo="fonte", conteudo=conteudo),
            author_id=USER,
        )
        first = store.read_document_part(ORG, AGENT, "long", parte=1, max_chars=200)
        assert len(first.conteudo) <= 200
        assert first.total_partes > 1
        # Reassembling every page (joined back with the same separator)
        # loses no content.
        all_pages = [
            store.read_document_part(ORG, AGENT, "long", parte=p, max_chars=200).conteudo
            for p in range(1, first.total_partes + 1)
        ]
        assert "\n\n".join(all_pages) == conteudo

    def test_out_of_range_parte_raises_not_found(self, store, collection):
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="short", titulo="Short", tipo="fonte", conteudo="paragrafo unico"),
            author_id=USER,
        )
        with pytest.raises(NotFound):
            store.read_document_part(ORG, AGENT, "short", parte=2)
        with pytest.raises(NotFound):
            store.read_document_part(ORG, AGENT, "short", parte=0)

    def test_unknown_slug_raises_not_found(self, store, collection):
        with pytest.raises(NotFound):
            store.read_document_part(ORG, AGENT, "nope")

    def test_a_single_paragraph_larger_than_max_chars_is_hard_split_never_dropped(self, store, collection):
        huge_paragraph = "y" * 500
        store.create_document(
            ORG, AGENT, collection.id,
            DocumentInput(slug="huge", titulo="Huge", tipo="fonte", conteudo=huge_paragraph),
            author_id=USER,
        )
        first = store.read_document_part(ORG, AGENT, "huge", parte=1, max_chars=200)
        assert len(first.conteudo) == 200
        assert first.total_partes == 3
        reassembled = "".join(
            store.read_document_part(ORG, AGENT, "huge", parte=p, max_chars=200).conteudo
            for p in range(1, first.total_partes + 1)
        )
        assert reassembled == huge_paragraph
