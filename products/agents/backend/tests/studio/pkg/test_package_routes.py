"""``GET /api/agent-packages/...`` (Agent Packages §I) — serving a published
dev-advisor tree, scope + org + kind enforcement. Auth assertions are strict
(`==`), never `in (...)` (CLAUDE.md §1)."""
from __future__ import annotations

from tests.studio.pkg.conftest import OTHER_ORG, SHA, TREE, make_bundle


class TestAuthBoundary:
    def test_versions_without_credential_is_401(self, pkg):
        assert pkg.rt.client.raw().get("/api/agent-packages/mobile-dev/versions").status_code == 401

    def test_version_without_credential_is_401(self, pkg):
        assert pkg.rt.client.raw().get("/api/agent-packages/mobile-dev/0.1.0").status_code == 401

    def test_token_without_the_scope_is_403_scope_missing(self, pkg):
        pkg.advisor()
        with pkg.as_token("learnings:write", "project-knowledge:write"):
            resp = pkg.get("/api/agent-packages/mobile-dev/versions")
        assert resp.status_code == 403
        assert resp.json()["code"] == "scope_missing"

    def test_token_with_no_scopes_at_all_is_403(self, pkg):
        pkg.advisor()
        with pkg.as_token():
            assert pkg.get("/api/agent-packages/mobile-dev/0.1.0").status_code == 403

    def test_a_member_user_may_read(self, pkg):
        pkg.advisor()
        assert pkg.get("/api/agent-packages/mobile-dev/versions").status_code == 200

    def test_token_of_another_org_cannot_see_the_agent_404(self, pkg):
        pkg.advisor()
        with pkg.as_token("packages:read", org_id=OTHER_ORG):
            assert pkg.get("/api/agent-packages/mobile-dev/versions").status_code == 404
            assert pkg.get("/api/agent-packages/mobile-dev/0.1.0").status_code == 404


class TestVersions:
    def test_lists_published_semvers_with_sha_newest_first(self, pkg):
        agent, v1 = pkg.advisor()
        pkg.import_bundle(make_bundle(versao__versao_semver="0.2.0", versao__package_sha="b" * 64))
        pkg.publish_imported()
        with pkg.as_token("packages:read"):
            resp = pkg.get("/api/agent-packages/mobile-dev/versions")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["key"] == "mobile-dev"
        assert [(i["versao"], i["sha"], i["status"], i["tem_arvore"]) for i in body["items"]] == [
            ("0.2.0", "b" * 64, "ativa", True),
            ("0.1.0", SHA, "substituida", True),
        ]

    def test_an_unpublished_draft_is_not_listed(self, pkg):
        pkg.advisor(publish=False)
        with pkg.as_token("packages:read"):
            assert pkg.get("/api/agent-packages/mobile-dev/versions").json()["items"] == []

    def test_unknown_agent_is_404(self, pkg):
        with pkg.as_token("packages:read"):
            resp = pkg.get("/api/agent-packages/nope/versions")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"

    def test_a_runtime_agent_is_not_a_package_404(self, pkg):
        pkg.rt.make_agent("isa")
        with pkg.as_token("packages:read"):
            resp = pkg.get("/api/agent-packages/isa/versions")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"


class TestTree:
    def test_serves_the_stored_tree_and_the_package_record(self, pkg):
        pkg.advisor()
        with pkg.as_token("packages:read"):
            resp = pkg.get("/api/agent-packages/mobile-dev/0.1.0")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["files"] == [{"path": f["caminho"], "conteudo": f["conteudo"]} for f in TREE]
        assert body["package"]["key"] == "mobile-dev"
        assert body["package"]["versao"] == "0.1.0"
        assert body["package"]["sha"] == SHA
        assert body["package"]["compiled_hash"] == "h1"  # the build's own PACKAGE.json record

    def test_latest_is_the_active_version(self, pkg):
        pkg.advisor()
        v2 = [{"caminho": ".claude/agents/mobile-dev.md", "conteudo": "segunda versão"}]
        pkg.import_bundle(make_bundle(versao__versao_semver="0.2.0", versao__package_sha="b" * 64, claude=v2))
        pkg.publish_imported()
        with pkg.as_token("packages:read"):
            body = pkg.get("/api/agent-packages/mobile-dev/latest").json()
            old = pkg.get("/api/agent-packages/mobile-dev/0.1.0").json()
        assert body["files"] == [{"path": ".claude/agents/mobile-dev.md", "conteudo": "segunda versão"}]
        assert body["package"]["versao"] == "0.2.0" and body["package"]["sha"] == "b" * 64
        assert old["files"] == [{"path": f["caminho"], "conteudo": f["conteudo"]} for f in TREE]

    def test_unknown_or_unpublished_semver_is_404(self, pkg):
        pkg.advisor()
        pkg.import_bundle(make_bundle(versao__versao_semver="0.2.0", versao__package_sha="b" * 64))  # draft only
        with pkg.as_token("packages:read"):
            for versao in ("9.9.9", "0.2.0", "nonsense"):
                resp = pkg.get(f"/api/agent-packages/mobile-dev/{versao}")
                assert resp.status_code == 404, versao
                assert resp.json()["code"] == "package_version_not_found"

    def test_published_version_without_a_tree_is_404_package_tree_not_found(self, pkg):
        pkg.import_bundle(make_bundle(claude=[]))
        pkg.publish_imported()
        with pkg.as_token("packages:read"):
            resp = pkg.get("/api/agent-packages/mobile-dev/0.1.0")
        assert resp.status_code == 404
        assert resp.json()["code"] == "package_tree_not_found"

    def test_package_record_is_rebuilt_when_the_tree_has_no_package_json(self, pkg):
        tree = [f for f in make_bundle()["claude"] if not f["caminho"].endswith("PACKAGE.json")]
        pkg.import_bundle(make_bundle(claude=tree))
        pkg.publish_imported()
        with pkg.as_token("packages:read"):
            body = pkg.get("/api/agent-packages/mobile-dev/0.1.0").json()
        assert (body["package"]["key"], body["package"]["versao"], body["package"]["sha"]) == ("mobile-dev", "0.1.0", SHA)
