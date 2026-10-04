"""``PUT /api/studio/agents/{key}/projects/{slug}/sources`` (Agent Packages
§G2/§G3/§J2) — idempotency, delete-absent, caps, hard excludes, secret scan,
reachability from `kb_buscar`/`kb_ler`."""
from __future__ import annotations

import hashlib

import pytest

from app.stores.errors import NotFound
from app.stores.studio_knowledge import source_sha_of
from tests.studio.pkg.conftest import OTHER_ORG

URL = "/api/studio/agents/mobile-dev/projects/limiar-app/sources"


def item(path: str, text: str, tipo: str = "doc") -> dict:
    return {"path": path, "sha256": source_sha_of(text), "tipo": tipo, "conteudo": text}


A = item("docs/visao.md", "# Visão\nO app acolhe quem está no limiar.")
B = item("src/App.tsx", "export const App = () => null;", "codigo")
Q = item("docs/design/decision-board.json", '{"abertas": [], "decididas": []}', "quadro")


@pytest.fixture
def advisor(pkg):
    pkg.advisor()
    return pkg


def put(pkg, items, *, token=("project-knowledge:write",), url=URL, wrap=False):
    body = {"fontes": items} if wrap else items
    if token is None:
        return pkg.put(url, json=body)
    with pkg.as_token(*token):
        return pkg.put(url, json=body)


class TestAuthBoundary:
    def test_no_credential_is_401(self, advisor):
        assert advisor.rt.client.raw().put(URL, json=[A]).status_code == 401

    @pytest.mark.parametrize("scopes", [(), ("packages:read",), ("learnings:write",), ("learnings:read",)])
    def test_token_without_project_knowledge_write_is_403(self, advisor, scopes):
        resp = put(advisor, [A], token=scopes)
        assert resp.status_code == 403
        assert resp.json()["code"] == "scope_missing"

    def test_an_admin_user_may_sync_without_a_token(self, advisor):
        assert put(advisor, [A], token=None).status_code == 200

    def test_a_token_of_another_org_gets_404_and_writes_nothing(self, advisor):
        with advisor.as_token("project-knowledge:write", org_id=OTHER_ORG):
            resp = advisor.put(URL, json=[A])
        assert resp.status_code == 404
        assert advisor.packages.list_sources(advisor.rt.org_id, advisor.rt.studio.get_agent(
            advisor.rt.org_id, "mobile-dev").id) == []

    def test_a_runtime_agent_is_404_even_for_a_scoped_token(self, pkg):
        pkg.rt.make_agent("isa")
        resp = put(pkg, [A], url="/api/studio/agents/isa/projects/limiar-app/sources")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"


class TestSync:
    def test_first_sync_stores_every_file_as_knowledge_in_projeto_collection(self, advisor):
        resp = put(advisor, [A, B, Q])
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert (out["total"], out["criados"], out["atualizados"], out["inalterados"], out["removidos"]) == (3, 3, 0, 0, 0)
        assert out["colecao_slug"] == "projeto-limiar-app"
        k = advisor.rt.knowledge
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        col = next(c for c in k.list_collections(advisor.rt.org_id, agent.id) if c.slug == "projeto-limiar-app")
        assert col.tag == "PRJ"
        assert k.count_documents(advisor.rt.org_id, agent.id, col.id) == 3
        ledger = {r.path: r for r in advisor.packages.list_sources(advisor.rt.org_id, agent.id)}
        assert set(ledger) == {A["path"], B["path"], Q["path"]}
        assert ledger[A["path"]].sha256 == A["sha256"] and ledger[Q["path"]].tipo == "quadro"
        assert all(r.document_id is not None for r in ledger.values())

    def test_object_form_of_the_body_is_accepted_too(self, advisor):
        resp = put(advisor, [A], wrap=True)
        assert resp.status_code == 200, resp.text
        assert resp.json()["criados"] == 1

    def test_synced_files_are_reachable_by_kb_buscar_and_kb_ler(self, advisor):
        put(advisor, [A, B])
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        hits = advisor.rt.knowledge.search(advisor.rt.org_id, agent.id, "limiar", colecao="projeto-limiar-app")
        assert [h.tag for h in hits] == ["PRJ"]
        led = {r.path: r for r in advisor.packages.list_sources(advisor.rt.org_id, agent.id)}
        doc = advisor.rt.knowledge.get_document(advisor.rt.org_id, agent.id, led[A["path"]].document_id)
        part = advisor.rt.knowledge.read_document_part(advisor.rt.org_id, agent.id, doc.slug)
        assert part.tag == "PRJ" and "limiar" in part.conteudo

    def test_resync_of_the_same_manifest_is_a_no_op_with_no_new_revisions(self, advisor):
        put(advisor, [A, B, Q])
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        led = advisor.packages.list_sources(advisor.rt.org_id, agent.id)
        revisions = {r.path: len(advisor.rt.knowledge.list_revisions(advisor.rt.org_id, agent.id, r.document_id)) for r in led}
        synced_at = {r.path: r.synced_at for r in led}
        out = put(advisor, [A, B, Q]).json()
        assert (out["criados"], out["atualizados"], out["inalterados"], out["removidos"]) == (0, 0, 3, 0)
        led2 = advisor.packages.list_sources(advisor.rt.org_id, agent.id)
        assert {r.path: len(advisor.rt.knowledge.list_revisions(advisor.rt.org_id, agent.id, r.document_id)) for r in led2} == revisions
        assert {r.path: r.synced_at for r in led2} == synced_at

    def test_changed_file_is_updated_in_place(self, advisor):
        put(advisor, [A, B])
        a2 = item(A["path"], "# Visão v2")
        out = put(advisor, [a2, B]).json()
        assert (out["atualizados"], out["inalterados"], out["criados"]) == (1, 1, 0)
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        led = {r.path: r for r in advisor.packages.list_sources(advisor.rt.org_id, agent.id)}
        assert led[A["path"]].sha256 == a2["sha256"]
        doc = advisor.rt.knowledge.get_document(advisor.rt.org_id, agent.id, led[A["path"]].document_id)
        assert doc.conteudo == "# Visão v2"
        assert advisor.rt.knowledge.count_documents(advisor.rt.org_id, agent.id, doc.collection_id) == 2

    def test_paths_absent_from_the_manifest_are_deleted_and_unreachable(self, advisor):
        put(advisor, [A, B, Q])
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        doc_b = next(r for r in advisor.packages.list_sources(advisor.rt.org_id, agent.id) if r.path == B["path"])
        doc_slug_b = advisor.rt.knowledge.get_document(advisor.rt.org_id, agent.id, doc_b.document_id).slug
        out = put(advisor, [A]).json()
        assert (out["total"], out["removidos"], out["inalterados"]) == (1, 2, 1)
        assert [r.path for r in advisor.packages.list_sources(advisor.rt.org_id, agent.id)] == [A["path"]]
        col = next(c for c in advisor.rt.knowledge.list_collections(advisor.rt.org_id, agent.id))
        assert advisor.rt.knowledge.count_documents(advisor.rt.org_id, agent.id, col.id) == 1
        assert advisor.rt.knowledge.search(advisor.rt.org_id, agent.id, "export", colecao="projeto-limiar-app") == []
        with pytest.raises(NotFound):  # kb_ler never serves an archived document
            advisor.rt.knowledge.read_document_part(advisor.rt.org_id, agent.id, doc_slug_b)

    def test_a_deleted_path_that_comes_back_is_reactivated(self, advisor):
        put(advisor, [A, B])
        put(advisor, [A])
        out = put(advisor, [A, B]).json()
        assert out["total"] == 2
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        col = advisor.rt.knowledge.list_collections(advisor.rt.org_id, agent.id)[0]
        assert advisor.rt.knowledge.count_documents(advisor.rt.org_id, agent.id, col.id) == 2

    def test_an_empty_manifest_removes_everything_for_the_project_only(self, advisor):
        put(advisor, [A])
        other = "/api/studio/agents/mobile-dev/projects/outro-app/sources"
        put(advisor, [B], url=other)
        out = put(advisor, []).json()
        assert (out["total"], out["removidos"]) == (0, 1)
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        assert [r.project_slug for r in advisor.packages.list_sources(advisor.rt.org_id, agent.id)] == ["outro-app"]

    def test_two_paths_that_slugify_alike_do_not_collide(self, advisor):
        x, y = item("docs/a-b.md", "um"), item("docs/a/b.md", "dois")
        out = put(advisor, [x, y]).json()
        assert out["criados"] == 2


class TestCapsAndSkips:
    def test_a_file_over_200kb_is_skipped_with_a_listed_warning_and_not_stored(self, advisor):
        big = item("docs/enorme.md", "x" * (200 * 1024 + 1))
        out = put(advisor, [A, big]).json()
        assert out["total"] == 1 and out["criados"] == 1
        assert [i["path"] for i in out["ignorados"]] == ["docs/enorme.md"]
        assert any("docs/enorme.md" in a for a in out["avisos"])

    def test_a_previously_synced_file_that_outgrows_the_cap_is_removed(self, advisor):
        put(advisor, [A])
        out = put(advisor, [item(A["path"], "x" * (200 * 1024 + 1))]).json()
        assert out["removidos"] == 1 and out["total"] == 0

    def test_an_empty_file_is_skipped_with_a_warning(self, advisor):
        out = put(advisor, [item("docs/vazio.md", "   \n")]).json()
        assert out["total"] == 0
        assert out["ignorados"][0]["motivo"] == "arquivo vazio"

    def test_exactly_200kb_is_kept(self, advisor):
        out = put(advisor, [item("docs/limite.md", "y" * (200 * 1024))]).json()
        assert out["total"] == 1 and out["ignorados"] == []

    def test_the_25mb_cap_is_registered_for_this_route_only(self):
        from app.main import app  # noqa: F401 — boot validates the override table
        from app.routers.studio_package_sync_router import SOURCES_BODY_LIMIT_PATTERN
        from app.schemas.packages import SOURCES_MAX_BYTES

        assert SOURCES_BODY_LIMIT_PATTERN == "/api/studio/agents/*/projects/*/sources"
        assert SOURCES_MAX_BYTES == 25 * 1024 * 1024


class TestRefusals:
    @pytest.mark.parametrize("path", [
        ".env", ".env.local", "apps/x/.env.production", "node_modules/pkg/index.js", "src/node_modules/x.js",
        "keys/server.pem", "secrets/id_rsa", "assets/logo.png", "build/app.apk", ".git/config",
    ])
    def test_forbidden_paths_refuse_the_whole_call_and_write_nothing(self, advisor, path):
        resp = put(advisor, [A, item(path, "conteudo qualquer")])
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "forbidden_path"
        assert [c["path"] for c in body["caminhos"]] == [path]
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        assert advisor.packages.list_sources(advisor.rt.org_id, agent.id) == []

    def test_a_secret_aborts_the_sync_naming_the_path_and_never_the_text(self, advisor):
        leaked = item("docs/chaves.md", "-----BEGIN RSA PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END RSA PRIVATE KEY-----")
        resp = put(advisor, [A, leaked])
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "secret_detected" and body["caminhos"] == ["docs/chaves.md"]
        assert "MIIEvQ" not in resp.text
        agent = advisor.rt.studio.get_agent(advisor.rt.org_id, "mobile-dev")
        assert advisor.packages.list_sources(advisor.rt.org_id, agent.id) == []

    def test_a_wrong_sha_is_refused(self, advisor):
        bad = dict(A, sha256=hashlib.sha256(b"outra coisa").hexdigest())
        resp = put(advisor, [bad])
        assert resp.status_code == 422 and resp.json()["code"] == "sha_mismatch"

    def test_duplicate_paths_are_refused(self, advisor):
        resp = put(advisor, [A, dict(A)])
        assert resp.status_code == 422 and resp.json()["code"] == "duplicate_path"

    @pytest.mark.parametrize("path", ["/etc/passwd", "../x.md", "a/../b.md", "a//b.md", "a\\b.md", ""])
    def test_unclean_paths_are_422(self, advisor, path):
        assert put(advisor, [dict(A, path=path)]).status_code == 422

    def test_unknown_item_key_is_422(self, advisor):
        assert put(advisor, [dict(A, extra=1)]).status_code == 422

    def test_bad_tipo_is_422(self, advisor):
        assert put(advisor, [dict(A, tipo="binario")]).status_code == 422

    @pytest.mark.parametrize("slug", ["Limiar_App", "a" * 57, "-x"])
    def test_bad_project_slug_is_422(self, advisor, slug):
        resp = put(advisor, [A], url=f"/api/studio/agents/mobile-dev/projects/{slug}/sources")
        assert resp.status_code == 422


class TestProjectsView:
    def test_lists_projects_with_last_sync_and_a_sources_sha_that_follows_the_content(self, advisor):
        put(advisor, [A, B])
        first = advisor.get("/api/studio/agents/mobile-dev/projects").json()["items"]
        assert [(p["slug"], p["total_fontes"]) for p in first] == [("limiar-app", 2)]
        assert first[0]["colecao_id"] and first[0]["ultima_sincronizacao"]
        put(advisor, [A])
        second = advisor.get("/api/studio/agents/mobile-dev/projects").json()["items"][0]
        assert second["total_fontes"] == 1 and second["sources_sha"] != first[0]["sources_sha"]

    def test_requires_a_user_a_token_is_403_user_required(self, advisor):
        with advisor.as_token("project-knowledge:write", "packages:read", "learnings:write", "learnings:read"):
            resp = advisor.get("/api/studio/agents/mobile-dev/projects")
        assert resp.status_code == 403
        assert resp.json()["code"] == "user_required"

    def test_no_credential_is_401(self, advisor):
        assert advisor.rt.client.raw().get("/api/studio/agents/mobile-dev/projects").status_code == 401
