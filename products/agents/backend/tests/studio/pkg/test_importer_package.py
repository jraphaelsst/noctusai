"""Importer additions of Agent Packages §C4/§D2 — `agente.kind`,
`versao.versao_semver`, `versao.package_sha` (+ the optional `claude` tree)."""
from __future__ import annotations

import pytest

from app.studio.importer import AgentBundle
from tests.studio.pkg.conftest import BUNDLE, SHA, TREE, _MISSING, make_bundle


class TestAcceptsC4Keys:
    def test_dev_advisor_import_records_kind_semver_sha_and_tree(self, pkg):
        resp = pkg.import_bundle()
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["agente"] == {"criado": True}
        assert out["pacote"] == {"kind": "dev-advisor", "versao_semver": "0.1.0", "package_sha": SHA, "arquivos_claude": 3}
        studio = pkg.rt.studio
        agent = studio.get_agent(pkg.rt.org_id, "mobile-dev")
        assert agent.kind == "dev-advisor"
        draft = studio.get_draft(pkg.rt.org_id, agent.id)
        assert (draft.versao_semver, draft.package_sha) == ("0.1.0", SHA)
        assert studio.get_package_tree(pkg.rt.org_id, draft.id) == TREE
        assert studio.get_active_version(pkg.rt.org_id, agent.id) is None  # never publishes

    def test_agent_summary_and_version_summary_expose_the_new_fields(self, pkg):
        pkg.import_bundle()
        listed = {a["key"]: a for a in pkg.get("/api/studio/agents").json()["items"]}
        assert listed["mobile-dev"]["kind"] == "dev-advisor"
        detail = pkg.get("/api/studio/agents/mobile-dev").json()
        assert detail["kind"] == "dev-advisor"
        assert detail["versoes"][0]["versao_semver"] == "0.1.0"
        assert detail["versoes"][0]["package_sha"] == SHA

    def test_runtime_agent_summary_keeps_kind_runtime(self, pkg):
        pkg.rt.make_agent("isa")
        listed = {a["key"]: a for a in pkg.get("/api/studio/agents").json()["items"]}
        assert listed["isa"]["kind"] == "runtime"

    def test_reimport_of_an_unpublished_draft_is_idempotent_and_replaces_the_tree(self, pkg):
        first = pkg.import_bundle().json()
        tree2 = [{"caminho": ".claude/agents/mobile-dev.md", "conteudo": "novo"}]
        second = pkg.import_bundle(make_bundle(claude=tree2)).json()
        assert second["agente"] == {"criado": False}
        assert second["rascunho"]["version_id"] == first["rascunho"]["version_id"]
        agent = pkg.rt.studio.get_agent(pkg.rt.org_id, "mobile-dev")
        draft = pkg.rt.studio.get_draft(pkg.rt.org_id, agent.id)
        assert pkg.rt.studio.get_package_tree(pkg.rt.org_id, draft.id) == tree2

    def test_dry_run_validates_identity_and_writes_nothing(self, pkg):
        resp = pkg.rt.post("/api/studio/agents/mobile-dev/import", params={"dry_run": "true"}, json=BUNDLE)
        assert resp.status_code == 200, resp.text
        assert resp.json()["pacote"]["versao_semver"] == "0.1.0"
        with pytest.raises(Exception):
            pkg.rt.studio.get_agent(pkg.rt.org_id, "mobile-dev")

    def test_a_tree_less_dev_advisor_import_warns(self, pkg):
        out = pkg.import_bundle(make_bundle(claude=[])).json()
        assert out["pacote"]["arquivos_claude"] == 0
        assert any("árvore" in a for a in out["avisos"])


class TestStillStrict:
    @pytest.mark.parametrize("where", ["agente", "versao", "top"])
    def test_unknown_keys_are_rejected_with_a_json_path(self, pkg, where):
        body = make_bundle()
        target = body if where == "top" else body[where]
        target["extra_key"] = 1
        resp = pkg.import_bundle(body)
        assert resp.status_code == 422
        assert "extra_key" in resp.text

    def test_unknown_key_inside_a_claude_file_is_rejected(self, pkg):
        body = make_bundle()
        body["claude"][0]["modo"] = "0755"
        assert pkg.import_bundle(body).status_code == 422

    @pytest.mark.parametrize("bad", ["v1", "1.2", "1.2.3.4", "../1.0.0", ""])
    def test_semver_must_be_semver(self, pkg, bad):
        assert pkg.import_bundle(make_bundle(versao__versao_semver=bad)).status_code == 422

    @pytest.mark.parametrize("bad", ["abc", "A" * 64, "a" * 63])
    def test_package_sha_must_be_lowercase_sha256(self, pkg, bad):
        assert pkg.import_bundle(make_bundle(versao__package_sha=bad)).status_code == 422

    @pytest.mark.parametrize("bad", ["../x.md", "/abs.md", "a//b.md", "a/../b.md", "a b.md", "dir/"])
    def test_claude_paths_must_be_clean_relative(self, pkg, bad):
        body = make_bundle()
        body["claude"][0]["caminho"] = bad
        assert pkg.import_bundle(body).status_code == 422

    def test_duplicate_claude_paths_are_rejected(self, pkg):
        body = make_bundle()
        body["claude"].append(dict(body["claude"][0]))
        assert pkg.import_bundle(body).status_code == 422

    def test_unknown_kind_value_is_rejected(self, pkg):
        assert pkg.import_bundle(make_bundle(agente__kind="advisor")).status_code == 422

    def test_model_validates_bundle_without_new_keys_unchanged(self):
        legacy = make_bundle(agente__kind=_MISSING, versao__versao_semver=_MISSING, versao__package_sha=_MISSING,
                             claude=[])
        legacy["claude"] = []
        AgentBundle.model_validate({k: v for k, v in legacy.items() if k != "claude"})


class TestDevAdvisorIdentityRules:
    @pytest.mark.parametrize("drop", ["versao__versao_semver", "versao__package_sha"])
    def test_dev_advisor_requires_semver_and_sha(self, pkg, drop):
        resp = pkg.import_bundle(make_bundle(**{drop: _MISSING}))
        assert resp.status_code == 422
        assert resp.json()["code"] == "package_identity_required"

    def test_new_agent_without_kind_is_runtime_and_refuses_package_fields(self, pkg):
        resp = pkg.import_bundle(make_bundle(agente__kind=_MISSING))
        assert resp.status_code == 422
        assert resp.json()["code"] == "package_fields_require_dev_advisor"

    def test_new_agent_without_kind_and_package_fields_is_runtime(self, pkg):
        body = make_bundle(agente__kind=_MISSING, versao__versao_semver=_MISSING, versao__package_sha=_MISSING)
        body.pop("claude")
        resp = pkg.import_bundle(body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["pacote"] is None
        assert pkg.rt.studio.get_agent(pkg.rt.org_id, "mobile-dev").kind == "runtime"

    def test_runtime_agent_is_never_flipped_to_dev_advisor(self, pkg):
        pkg.rt.make_agent("isa")
        resp = pkg.import_bundle(make_bundle(agente__key="isa"), key="isa")
        assert resp.status_code == 409
        assert resp.json()["code"] == "kind_change_refused"
        assert pkg.rt.studio.get_agent(pkg.rt.org_id, "isa").kind == "runtime"
        isa = pkg.rt.studio.get_agent(pkg.rt.org_id, "isa")
        assert all(
            v.versao_semver is None and pkg.rt.studio.get_package_tree(pkg.rt.org_id, v.id) is None
            for v in pkg.rt.studio.list_versions(pkg.rt.org_id, isa.id)
        )

    def test_dev_advisor_is_never_flipped_back_to_runtime(self, pkg):
        pkg.import_bundle()
        resp = pkg.import_bundle(make_bundle(agente__kind="runtime", versao__versao_semver=_MISSING,
                                             versao__package_sha=_MISSING))
        assert resp.status_code == 409
        assert resp.json()["code"] == "kind_change_refused"

    def test_existing_dev_advisor_accepts_an_import_that_omits_kind(self, pkg):
        pkg.import_bundle()
        resp = pkg.import_bundle(make_bundle(agente__kind=_MISSING, versao__versao_semver="0.2.0"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["pacote"]["versao_semver"] == "0.2.0"

    def test_default_agent_keys_are_still_refused(self, pkg):
        resp = pkg.import_bundle(make_bundle(agente__key="julia"), key="julia")
        assert resp.status_code == 409
        assert resp.json()["code"] == "not_studio_agent"


class TestPublishedSemverIsNotReimported:
    def test_same_semver_after_publish_is_409_semver_published(self, pkg):
        pkg.advisor()
        resp = pkg.import_bundle(make_bundle(versao__package_sha="b" * 64))
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "semver_published"
        assert "aumente" in body["detail"]

    def test_same_semver_same_sha_is_also_refused(self, pkg):
        pkg.advisor()
        resp = pkg.import_bundle()
        assert resp.status_code == 409
        assert resp.json()["code"] == "semver_published"

    def test_a_bumped_semver_after_publish_makes_a_new_draft_and_keeps_the_active_version(self, pkg):
        agent, v1 = pkg.advisor()
        resp = pkg.import_bundle(make_bundle(versao__versao_semver="0.2.0", versao__package_sha="b" * 64))
        assert resp.status_code == 200, resp.text
        studio = pkg.rt.studio
        assert studio.get_active_version(pkg.rt.org_id, agent.id).id == v1.id
        draft = studio.get_draft(pkg.rt.org_id, agent.id)
        assert (draft.versao_semver, draft.package_sha) == ("0.2.0", "b" * 64)
        # the published version's tree is untouched
        assert studio.get_package_tree(pkg.rt.org_id, v1.id) == TREE

    def test_a_published_versions_tree_is_write_once(self, pkg):
        agent, v1 = pkg.advisor()
        from app.stores._db_errors import VersionImmutable

        with pytest.raises(VersionImmutable):
            pkg.rt.studio.set_package_tree(pkg.rt.org_id, agent.id, v1.id, [])
