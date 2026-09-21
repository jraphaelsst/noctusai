"""Router tests for `/api/studio/agents/{key}/knowledge` + `.../documents`
(contract §D3)."""
from __future__ import annotations

from tests.studio.ke.conftest import DEFAULT_ORG_ID, seed_org_role, seed_studio_agent


class TestAuthBoundary:
    def test_list_collections_requires_auth(self, ke_client):
        resp = ke_client.raw().get("/api/studio/agents/isaia/knowledge")
        assert resp.status_code == 401

    def test_create_collection_requires_auth(self, ke_client):
        resp = ke_client.raw().post(
            "/api/studio/agents/isaia/knowledge", json={"slug": "audience", "nome": "Audience"},
        )
        assert resp.status_code == 401

    def test_member_forbidden_from_create(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/knowledge", json={"slug": "audience", "nome": "Audience"},
        )
        assert resp.status_code == 403


class TestAgentResolution:
    def test_unknown_agent_key_404s(self, ke_client):
        seed_org_role(ke_client, role="member")
        resp = ke_client.get("/api/studio/agents/nope/knowledge")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"

    def test_legacy_agent_409s(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client, key="julia", definition_mode="legacy")
        resp = ke_client.get("/api/studio/agents/julia/knowledge")
        assert resp.status_code == 409
        assert resp.json()["code"] == "not_studio_agent"

    def test_another_orgs_agent_is_invisible(self, ke_client):
        from uuid import uuid4

        other_org = uuid4()
        seed_studio_agent(ke_client, key="isaia", org_id=other_org)
        seed_org_role(ke_client, role="member")  # seeds DEFAULT_ORG_ID's role
        resp = ke_client.get("/api/studio/agents/isaia/knowledge")
        assert resp.status_code == 404


class TestCollectionsCrud:
    def test_create_list_and_update(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        create = ke_client.post(
            "/api/studio/agents/isaia/knowledge",
            json={"slug": "audience", "nome": "Audience", "tag": "AU"},
        )
        assert create.status_code == 201, create.text
        col_id = create.json()["id"]
        assert create.json()["total_documentos"] == 0

        listed = ke_client.get("/api/studio/agents/isaia/knowledge")
        assert listed.status_code == 200
        assert [c["slug"] for c in listed.json()["colecoes"]] == ["audience"]

        updated = ke_client.patch(
            f"/api/studio/agents/isaia/knowledge/{col_id}", json={"nome": "Audiência"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["nome"] == "Audiência"
        assert updated.json()["tag"] == "AU"  # untouched field survives

    def test_duplicate_slug_422s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        ke_client.post("/api/studio/agents/isaia/knowledge", json={"slug": "audience", "nome": "Audience"})
        resp = ke_client.post("/api/studio/agents/isaia/knowledge", json={"slug": "audience", "nome": "Dup"})
        assert resp.status_code == 422, resp.text

    def test_unknown_field_rejected_422(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        resp = ke_client.post(
            "/api/studio/agents/isaia/knowledge",
            json={"slug": "audience", "nome": "Audience", "campo_desconhecido": True},
        )
        assert resp.status_code == 422

    def test_update_unknown_collection_404s(self, ke_client):
        import uuid

        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        resp = ke_client.patch(
            f"/api/studio/agents/isaia/knowledge/{uuid.uuid4()}", json={"nome": "x"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "collection_not_found"


class TestDocumentsCrud:
    def _create_collection(self, ke_client) -> str:
        resp = ke_client.post(
            "/api/studio/agents/isaia/knowledge", json={"slug": "audience", "nome": "Audience"},
        )
        return resp.json()["id"]

    def test_create_get_and_list(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col_id = self._create_collection(ke_client)

        created = ke_client.post(
            f"/api/studio/agents/isaia/knowledge/{col_id}/documents",
            json={"slug": "doc-1", "titulo": "Doc 1", "tipo": "fonte", "conteudo": "conteudo do documento"},
        )
        assert created.status_code == 201, created.text
        doc_id = created.json()["id"]
        assert created.json()["chars"] == len("conteudo do documento")

        fetched = ke_client.get(f"/api/studio/agents/isaia/documents/{doc_id}")
        assert fetched.status_code == 200
        assert fetched.json()["slug"] == "doc-1"

        listed = ke_client.get(f"/api/studio/agents/isaia/knowledge/{col_id}/documents")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        # Collection listing now reflects the new active document.
        collections = ke_client.get("/api/studio/agents/isaia/knowledge")
        assert collections.json()["colecoes"][0]["total_documentos"] == 1

    def test_create_in_unknown_collection_404s(self, ke_client):
        import uuid

        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        resp = ke_client.post(
            f"/api/studio/agents/isaia/knowledge/{uuid.uuid4()}/documents",
            json={"slug": "doc-1", "titulo": "Doc 1", "tipo": "fonte", "conteudo": "x"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "collection_not_found"

    def test_invalid_tipo_422s(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col_id = self._create_collection(ke_client)
        resp = ke_client.post(
            f"/api/studio/agents/isaia/knowledge/{col_id}/documents",
            json={"slug": "doc-1", "titulo": "Doc 1", "tipo": "nao-existe", "conteudo": "x"},
        )
        assert resp.status_code == 422

    def test_update_writes_a_revision_and_supports_motivo(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col_id = self._create_collection(ke_client)
        doc_id = ke_client.post(
            f"/api/studio/agents/isaia/knowledge/{col_id}/documents",
            json={"slug": "doc-1", "titulo": "Doc 1", "tipo": "fonte", "conteudo": "v1"},
        ).json()["id"]

        updated = ke_client.patch(
            f"/api/studio/agents/isaia/documents/{doc_id}",
            json={"conteudo": "v2", "motivo": "atualização de dados"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["conteudo"] == "v2"

        revisions = ke_client.get(f"/api/studio/agents/isaia/documents/{doc_id}/revisions")
        assert revisions.status_code == 200
        items = revisions.json()["items"]
        assert len(items) == 2
        assert items[0]["op"] == "update"
        assert items[0]["motivo"] == "atualização de dados"

    def test_unknown_document_404s(self, ke_client):
        import uuid

        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        resp = ke_client.get(f"/api/studio/agents/isaia/documents/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "document_not_found"


class TestSearchRoute:
    def test_search_returns_ranked_matches(self, ke_client):
        seed_org_role(ke_client, role="owner")
        seed_studio_agent(ke_client)
        col_id = self._create_collection_for_search(ke_client)
        ke_client.post(
            f"/api/studio/agents/isaia/knowledge/{col_id}/documents",
            json={"slug": "doc-1", "titulo": "Roteiro sobre reels", "tipo": "fonte", "conteudo": "conteudo neutro"},
        )
        resp = ke_client.get("/api/studio/agents/isaia/knowledge/search", params={"q": "reels"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["slug"] == "doc-1"
        assert items[0]["colecao"] == "audience"

    def test_search_requires_q(self, ke_client):
        seed_org_role(ke_client, role="member")
        seed_studio_agent(ke_client)
        resp = ke_client.get("/api/studio/agents/isaia/knowledge/search")
        assert resp.status_code == 422

    def _create_collection_for_search(self, ke_client) -> str:
        resp = ke_client.post(
            "/api/studio/agents/isaia/knowledge", json={"slug": "audience", "nome": "Audience"},
        )
        return resp.json()["id"]
