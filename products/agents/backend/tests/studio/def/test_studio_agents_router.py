"""``/api/studio/agents`` + ``/api/studio/prompts`` (contract §D1, §H, §J2.1).

Auth assertions are strict (``== 401`` / ``== 403`` / ``== 404``, §H6).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.studio.models import CollectionSummary, GateRun

BASE = "/api/studio/agents"


def _create(studio, key="isa", nome="Isa", **extra):
    resp = studio.post(BASE, json={"key": key, "nome": nome, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _draft(studio, key="isa"):
    detail = studio.get(f"{BASE}/{key}").json()
    draft = next(v for v in detail["versoes"] if v["status"] == "rascunho")
    resp = studio.get(f"{BASE}/{key}/versions/{draft['id']}")
    assert resp.status_code == 200, resp.text
    return resp.json()


SECTIONS = {"secoes": [
    {"chave": "identidade", "titulo": "Identidade", "ordem": 10, "conteudo": "Você é estrategista.", "ativo": True},
    {"chave": "regras", "titulo": "Regras", "ordem": 20, "conteudo": "Seja direta.", "ativo": True},
]}


def _publishable(studio, key="isa"):
    """Agent with a compilable draft; returns the draft VersionDetail."""
    _create(studio, key=key)
    resp = studio.put(f"{BASE}/{key}/draft/sections", json=SECTIONS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _pass_gate(studio, draft, score=0.9, *, completa=True, total=3):
    """A concluded run visible to BOTH gate layers: the Python gate seam and
    the DB-side re-check ``publish_agent_version`` does (the Fake store's
    registered ``eval_runs``)."""
    run = GateRun(
        id=uuid4(), score=score, limiar=0.8, compiled_hash=draft["compiled_hash"], status="concluida",
        completa=completa, total=total,
    )
    studio.gate.set_run(studio.org_id, UUID(draft["id"]), run)
    studio.store.register_eval_run(
        studio.org_id, UUID(draft["id"]), run_id=run.id, score=score,
        compiled_hash=draft["compiled_hash"], completa=completa, total=total,
    )
    return run


class TestAuthBoundary:
    @pytest.mark.parametrize(
        "method, path",
        [
            ("get", BASE),
            ("post", BASE),
            ("get", f"{BASE}/isa"),
            ("patch", f"{BASE}/isa"),
            ("post", f"{BASE}/isa/draft"),
            ("delete", f"{BASE}/isa/draft"),
            ("put", f"{BASE}/isa/draft/sections"),
            ("post", f"{BASE}/isa/draft/publish"),
            ("get", f"/api/studio/prompts/sha256:{'0' * 64}"),
        ],
    )
    def test_unauthenticated_is_401(self, studio, method, path):
        resp = getattr(studio.raw, method)(path, **({} if method in ("get", "delete") else {"json": {}}))
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "method, path, body",
        [
            ("post", BASE, {"key": "novo", "nome": "Novo"}),
            ("patch", f"{BASE}/isa", {"nome": "X"}),
            ("post", f"{BASE}/isa/draft", {}),
            ("delete", f"{BASE}/isa/draft", None),
            ("patch", f"{BASE}/isa/draft", {"notas": "x"}),
            ("put", f"{BASE}/isa/draft/sections", SECTIONS),
            ("post", f"{BASE}/isa/draft/skills", {"nome": "s", "descricao": "d", "corpo": "c"}),
            ("post", f"{BASE}/isa/draft/publish", {}),
        ],
    )
    def test_member_cannot_write(self, studio, method, path, body):
        _create(studio)
        studio.as_role("member")
        resp = getattr(studio, method)(path, **({"json": body} if body is not None else {}))
        assert resp.status_code == 403
        assert resp.json()["code"] == "role_missing"

    def test_member_can_read(self, studio):
        _create(studio)
        studio.as_role("member")
        assert studio.get(BASE).status_code == 200
        assert studio.get(f"{BASE}/isa").status_code == 200

    def test_other_org_gets_404_never_403(self, studio):
        _create(studio)
        draft = _draft(studio)
        studio.as_other_org(role="owner")
        resp = studio.get(f"{BASE}/isa")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"
        assert studio.get(BASE).json()["items"] == []
        assert studio.patch(f"{BASE}/isa", json={"nome": "hijack"}).status_code == 404
        # Their own agent with the same key cannot reach our version id.
        _create(studio)
        resp = studio.get(f"{BASE}/isa/versions/{draft['id']}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "version_not_found"


class TestAgents:
    def test_create_returns_summary_with_draft(self, studio):
        body = _create(studio, descricao="Estrategista")
        assert body["definition_mode"] == "studio"
        assert body["ativo"] is False
        assert body["versao_ativa"] is None
        assert body["tem_rascunho"] is True
        assert body["publicacao_limiar"] == pytest.approx(0.8)
        draft = _draft(studio)
        assert draft["versao"] == 1 and draft["model"] == "claude-opus-5"
        assert draft["compiled_hash"].startswith("sha256:")

    def test_key_taken(self, studio):
        _create(studio)
        resp = studio.post(BASE, json={"key": "isa", "nome": "Dup"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "key_taken"

    @pytest.mark.parametrize("key", ["julia", "one-chat"])
    def test_legacy_default_keys_are_reserved(self, studio, key):
        resp = studio.post(BASE, json={"key": key, "nome": "X"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "key_taken"

    @pytest.mark.parametrize("body", [{"key": "Isa", "nome": "x"}, {"key": "isa", "nome": "x", "extra": 1}, {"key": "isa"}])
    def test_invalid_create_body_422(self, studio, body):
        assert studio.post(BASE, json=body).status_code == 422

    def test_list_includes_legacy_agents(self, studio):
        studio.store.add_legacy_agent(studio.org_id, "julia", "Julia")
        _create(studio)
        items = {i["key"]: i for i in studio.get(BASE).json()["items"]}
        assert items["julia"]["definition_mode"] == "legacy"
        assert items["julia"]["tem_rascunho"] is False
        assert items["isa"]["tem_rascunho"] is True

    def test_legacy_agent_on_studio_route_409(self, studio):
        studio.store.add_legacy_agent(studio.org_id, "julia", "Julia")
        for resp in (
            studio.get(f"{BASE}/julia"),
            studio.patch(f"{BASE}/julia", json={"nome": "X"}),
            studio.post(f"{BASE}/julia/draft", json={}),
            studio.get(f"{BASE}/julia/clients"),
        ):
            assert resp.status_code == 409
            assert resp.json()["code"] == "not_studio_agent"

    def test_patch_agent(self, studio):
        _create(studio)
        body = studio.patch(f"{BASE}/isa", json={"publicacao_limiar": 0.95, "ativo": True, "descricao": None}).json()
        assert body["publicacao_limiar"] == pytest.approx(0.95) and body["ativo"] is True
        assert body["descricao"] is None
        assert studio.patch(f"{BASE}/isa", json={"publicacao_limiar": 1.2}).status_code == 422
        resp = studio.patch(f"{BASE}/isa", json={"nome": None})
        assert resp.status_code == 422
        assert resp.json()["code"] == "invalid_field"

    def test_unknown_agent_404(self, studio):
        resp = studio.get(f"{BASE}/nope")
        assert resp.status_code == 404
        assert resp.json()["code"] == "agent_not_found"


class TestDraftEditing:
    def test_sections_full_replace_refreshes_hash(self, studio):
        _create(studio)
        before = _draft(studio)["compiled_hash"]
        detail = studio.put(f"{BASE}/isa/draft/sections", json=SECTIONS).json()
        assert [s["chave"] for s in detail["secoes"]] == ["identidade", "regras"]
        assert detail["compiled_hash"] != before
        # id round-trip keeps the row; omitted rows are removed.
        keep = detail["secoes"][0]
        detail2 = studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [
            {**{k: keep[k] for k in ("id", "chave", "titulo", "ordem", "ativo")}, "conteudo": "Novo."},
        ]}).json()
        assert [(s["id"], s["conteudo"]) for s in detail2["secoes"]] == [(keep["id"], "Novo.")]

    def test_sections_duplicate_chave_422(self, studio):
        _create(studio)
        s = SECTIONS["secoes"][0]
        resp = studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [s, s]})
        assert resp.status_code == 422
        assert resp.json()["code"] == "duplicate_chave"

    def test_sections_bad_chave_422(self, studio):
        _create(studio)
        bad = {**SECTIONS["secoes"][0], "chave": "Com Espaco"}
        assert studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [bad]}).status_code == 422

    def test_patch_settings_and_allowlist(self, studio):
        _create(studio)
        body = studio.patch(f"{BASE}/isa/draft", json={
            "model": "claude-sonnet-5", "max_turns": 10, "tool_policy": {"web_search": False, "knowledge": True},
        }).json()
        assert (body["model"], body["max_turns"]) == ("claude-sonnet-5", 10)
        assert body["tool_policy"] == {"web_search": False, "knowledge": True}
        for bad in ({"model": "gpt-4o"}, {"effort": "extreme"}, {"max_turns": 0}):
            resp = studio.patch(f"{BASE}/isa/draft", json=bad)
            assert resp.status_code == 422
            assert resp.json()["code"] == "invalid_field"
        assert studio.patch(f"{BASE}/isa/draft", json={"status": "ativa"}).status_code == 422
        assert studio.patch(f"{BASE}/isa/draft", json={"tool_policy": {"web_search": True}}).status_code == 422

    def test_skills_and_files_crud(self, studio):
        _create(studio)
        resp = studio.post(f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "Roteiros.", "corpo": "Passos"})
        assert resp.status_code == 201, resp.text
        skill = resp.json()
        dup = studio.post(f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "d", "corpo": "c"})
        assert dup.status_code == 409 and dup.json()["code"] == "skill_exists"
        assert studio.post(f"{BASE}/isa/draft/skills", json={"nome": "x", "descricao": "d" * 1025, "corpo": ""}).status_code == 422

        patched = studio.patch(f"{BASE}/isa/draft/skills/{skill['id']}", json={"corpo": "Novo corpo"}).json()
        assert patched["corpo"] == "Novo corpo"

        f = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files", json={"caminho": "references/a.md", "conteudo": "abc"})
        assert f.status_code == 200, f.text
        assert f.json()["chars"] == 3
        for bad in ("../etc/passwd", "a/../b.md", "/abs.md"):
            assert studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files", json={"caminho": bad, "conteudo": "x"}).status_code == 422
        got = studio.get(f"{BASE}/isa/skills/{skill['id']}/files/{f.json()['id']}").json()
        assert got["conteudo"] == "abc"

        detail = _draft(studio)
        assert detail["skills"][0]["arquivos"][0]["caminho"] == "references/a.md"

        assert studio.delete(f"{BASE}/isa/draft/skills/{skill['id']}/files/{f.json()['id']}").status_code == 204
        assert studio.get(f"{BASE}/isa/skills/{skill['id']}/files/{f.json()['id']}").status_code == 404
        assert studio.delete(f"{BASE}/isa/draft/skills/{skill['id']}").status_code == 204
        assert _draft(studio)["skills"] == []

    def test_skill_files_batch(self, studio):
        _create(studio)
        skill = studio.post(
            f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "Roteiros.", "corpo": "Passos"},
        ).json()

        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": [
            {"caminho": "references/a.md", "conteudo": "abc"},
            {"caminho": "references/b.md", "titulo": "B", "conteudo": "defg"},
        ]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["criados"] == 2 and body["atualizados"] == 0 and body["erros"] == 0
        by_caminho = {r["caminho"]: r for r in body["resultados"]}
        assert by_caminho["references/a.md"]["status"] == "criado"
        assert by_caminho["references/a.md"]["chars"] == 3
        assert by_caminho["references/b.md"]["titulo"] == "B"

        detail = _draft(studio)
        caminhos = {f["caminho"] for f in detail["skills"][0]["arquivos"]}
        assert caminhos == {"references/a.md", "references/b.md"}

        # Re-upserting one existing + one new path in the same call.
        again = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": [
            {"caminho": "references/a.md", "conteudo": "abc novo"},
            {"caminho": "references/c.md", "conteudo": "c"},
        ]}).json()
        assert again["criados"] == 1 and again["atualizados"] == 1 and again["erros"] == 0
        by_caminho = {r["caminho"]: r for r in again["resultados"]}
        assert by_caminho["references/a.md"]["status"] == "atualizado"
        assert by_caminho["references/c.md"]["status"] == "criado"

    def test_skill_files_batch_bad_caminho_422s(self, studio):
        _create(studio)
        skill = studio.post(
            f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "d", "corpo": "c"},
        ).json()
        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": [
            {"caminho": "../etc/passwd", "conteudo": "x"},
        ]})
        assert resp.status_code == 422

    def test_skill_files_batch_over_limit_422s(self, studio):
        _create(studio)
        skill = studio.post(
            f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "d", "corpo": "c"},
        ).json()
        arquivos = [{"caminho": f"references/f{i}.md", "conteudo": "x"} for i in range(51)]
        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": arquivos})
        assert resp.status_code == 422

    def test_skill_files_batch_of_published_version_is_immutable(self, studio):
        draft = _publishable(studio)
        skill = studio.post(
            f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "d", "corpo": "c"},
        ).json()
        _pass_gate(studio, _draft(studio))
        published = studio.post(f"{BASE}/isa/draft/publish", json={}).json()
        assert published["status"] == "ativa"

        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": [
            {"caminho": "references/a.md", "conteudo": "x"},
        ]})
        assert resp.status_code == 409
        assert resp.json()["code"] == "version_immutable"

    def test_skill_files_batch_requires_auth(self, studio):
        resp = studio.raw.put(
            f"{BASE}/isa/draft/skills/00000000-0000-0000-0000-000000000000/files/batch",
            json={"arquivos": [{"caminho": "a.md", "conteudo": "x"}]},
        )
        assert resp.status_code == 401

    def test_skill_files_batch_member_forbidden(self, studio):
        _create(studio)
        skill = studio.post(
            f"{BASE}/isa/draft/skills", json={"nome": "roteiro", "descricao": "d", "corpo": "c"},
        ).json()
        studio.as_role("member")
        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": [
            {"caminho": "references/a.md", "conteudo": "x"},
        ]})
        assert resp.status_code == 403

    def test_skill_files_batch_of_other_agent_is_404(self, studio):
        _create(studio)
        _create(studio, key="outro")
        skill = studio.post(f"{BASE}/outro/draft/skills", json={"nome": "s", "descricao": "d", "corpo": "c"}).json()
        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files/batch", json={"arquivos": [
            {"caminho": "a.md", "conteudo": "x"},
        ]})
        assert resp.status_code == 404
        assert resp.json()["code"] == "skill_not_found"

    def test_skill_of_other_agent_is_404(self, studio):
        _create(studio)
        _create(studio, key="outro")
        skill = studio.post(f"{BASE}/outro/draft/skills", json={"nome": "s", "descricao": "d", "corpo": "c"}).json()
        resp = studio.patch(f"{BASE}/isa/draft/skills/{skill['id']}", json={"corpo": "x"})
        assert resp.status_code == 404
        assert resp.json()["code"] == "skill_not_found"

    def test_draft_create_conflict_and_discard(self, studio):
        _create(studio)
        resp = studio.post(f"{BASE}/isa/draft", json={})
        assert resp.status_code == 409 and resp.json()["code"] == "draft_exists"
        assert studio.delete(f"{BASE}/isa/draft").status_code == 204
        resp = studio.delete(f"{BASE}/isa/draft")
        assert resp.status_code == 404 and resp.json()["code"] == "draft_not_found"
        assert studio.patch(f"{BASE}/isa/draft", json={"notas": "x"}).status_code == 404


class TestCompiled:
    def test_compiled_matches_manifest_and_includes_knowledge(self, studio):
        _publishable(studio)
        agent_id = studio.store.get_agent(studio.org_id, "isa").id
        studio.catalog.set(studio.org_id, agent_id, [
            CollectionSummary(slug="publico", nome="Público", tag="AU", descricao="", doc_count=3),
        ])
        draft = _draft(studio)
        body = studio.get(f"{BASE}/isa/versions/{draft['id']}/compiled").json()
        assert "# Base de conhecimento" in body["texto"]
        for m in body["manifest"]:
            assert body["texto"][m["inicio"]:m["fim"]].startswith("# ")
        assert body["avisos"] == []
        assert body["version_id"] == draft["id"] and body["client_id"] is None
        # L7: a read never writes — the stored hash is only re-stamped by an
        # admin write or at publish, even though knowledge changed the text.
        assert body["hash"] != draft["compiled_hash"]
        assert _draft(studio)["compiled_hash"] == draft["compiled_hash"]

    def test_compiled_with_client(self, studio):
        _publishable(studio)
        client = studio.post(f"{BASE}/isa/clients", json={"slug": "marca-x", "nome": "Marca X", "resumo": "Resumo."}).json()
        studio.post(f"{BASE}/isa/clients/{client['id']}/entries", json={"tipo": "trava", "titulo": "Nunca", "conteudo": "preço"})
        draft = _draft(studio)
        body = studio.get(f"{BASE}/isa/versions/{draft['id']}/compiled", params={"client_id": client["id"]}).json()
        assert body["texto"].endswith("# Cliente em foco: Marca X\n\nResumo.\n\n## Travas\n- **Nunca** — preço")
        assert body["client_id"] == client["id"]
        # The stored draft hash stays the NO-client hash.
        assert _draft(studio)["compiled_hash"] != body["hash"]

    def test_compiled_foreign_client_404(self, studio):
        _publishable(studio)
        _create(studio, key="outro")
        foreign = studio.post(f"{BASE}/outro/clients", json={"slug": "c", "nome": "C"}).json()
        draft = _draft(studio)
        resp = studio.get(f"{BASE}/isa/versions/{draft['id']}/compiled", params={"client_id": foreign["id"]})
        assert resp.status_code == 404
        assert resp.json()["code"] == "client_not_found"

    def test_compiled_reports_blocking_warnings(self, studio):
        _create(studio)
        studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [
            {"chave": "vazia", "titulo": "Vazia", "ordem": 1, "conteudo": "", "ativo": True},
        ]})
        draft = _draft(studio)
        avisos = studio.get(f"{BASE}/isa/versions/{draft['id']}/compiled").json()["avisos"]
        assert {"codigo": "secao_vazia", "bloqueante": True}.items() <= avisos[0].items()


class TestPublishGate:
    def test_blocking_warning_409_compile_blocked_even_with_override(self, studio):
        _create(studio)  # empty draft: zero sections ⇒ blocking
        resp = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 30})
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "compile_blocked"
        assert any(a["codigo"] == "sem_secoes" for a in body["avisos"])

    def test_no_run_409_eval_required(self, studio):
        draft = _publishable(studio)
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "eval_required"
        assert body["hash_atual"] == draft["compiled_hash"]
        assert body["ultima_execucao"] is None

    def test_stale_hash_run_fails_the_gate(self, studio):
        draft = _publishable(studio)
        run = _pass_gate(studio, draft)
        studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [SECTIONS["secoes"][0]]})
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "eval_required"
        assert body["ultima_execucao"]["id"] == str(run.id)
        assert body["ultima_execucao"]["compiled_hash"] != body["hash_atual"]

    def test_score_below_limiar_fails(self, studio):
        draft = _publishable(studio)
        _pass_gate(studio, draft, score=0.79)
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409 and resp.json()["code"] == "eval_required"

    def test_passing_run_publishes_and_records_it(self, studio):
        draft = _publishable(studio)
        run = _pass_gate(studio, draft)
        resp = studio.post(f"{BASE}/isa/draft/publish", json={"notas": "primeira"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ativa"
        assert body["eval_run_id"] == str(run.id)
        assert body["publish_override_reason"] is None
        assert body["notas"] == "primeira"
        assert body["eval_score"] == pytest.approx(0.9)
        summary = studio.get(f"{BASE}/isa").json()
        assert summary["versao_ativa"] == 1 and summary["tem_rascunho"] is False
        # proof of use: the exact published text is retrievable by hash
        prompt = studio.get(f"/api/studio/prompts/{body['compiled_hash']}")
        assert prompt.status_code == 200
        assert prompt.json()["texto"].startswith("# Identidade")
        assert prompt.json()["version_id"] == body["id"]

    def test_override_publishes_with_reason(self, studio):
        _publishable(studio)
        reason = "Publicação urgente aprovada pela coordenação."
        body = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": reason}).json()
        assert body["status"] == "ativa"
        assert body["publish_override_reason"] == reason
        assert body["eval_run_id"] is None

    def test_short_override_422(self, studio):
        _publishable(studio)
        assert studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "curto"}).status_code == 422

    def test_published_version_is_immutable_over_http(self, studio):
        _publishable(studio)
        skill = studio.post(f"{BASE}/isa/draft/skills", json={"nome": "s", "descricao": "d", "corpo": "c"}).json()
        studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 25})
        resp = studio.patch(f"{BASE}/isa/draft/skills/{skill['id']}", json={"corpo": "mudado"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "version_immutable"
        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files", json={"caminho": "a.md", "conteudo": "x"})
        assert resp.status_code == 409 and resp.json()["code"] == "version_immutable"
        assert studio.patch(f"{BASE}/isa/draft", json={"notas": "x"}).status_code == 404

    def test_restore_clones_old_version_and_republish_supersedes(self, studio):
        _publishable(studio)
        v1 = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 25}).json()
        v2 = studio.post(f"{BASE}/isa/draft", json={}).json()
        assert v2["versao"] == 2 and v2["based_on_version_id"] == v1["id"]
        assert [s["chave"] for s in v2["secoes"]] == ["identidade", "regras"]
        assert v2["compiled_hash"] == v1["compiled_hash"]
        studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 25})
        statuses = {v["versao"]: v["status"] for v in studio.get(f"{BASE}/isa").json()["versoes"]}
        assert statuses == {2: "ativa", 1: "substituida"}
        # explicit restore of v1
        v3 = studio.post(f"{BASE}/isa/draft", json={"from_version_id": v1["id"]}).json()
        assert v3["versao"] == 3 and v3["based_on_version_id"] == v1["id"]


class TestDiffAndPrompts:
    def test_diff(self, studio):
        _publishable(studio)
        v1 = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 25}).json()
        studio.post(f"{BASE}/isa/draft", json={})
        studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [
            {**SECTIONS["secoes"][0], "conteudo": "Mudou."},
            {"chave": "nova", "titulo": "Nova", "ordem": 30, "conteudo": "n", "ativo": True},
        ]})
        studio.patch(f"{BASE}/isa/draft", json={"model": "claude-sonnet-5"})
        v2 = _draft(studio)
        body = studio.get(f"{BASE}/isa/versions/{v1['id']}/diff/{v2['id']}").json()
        assert {s["chave"]: s["estado"] for s in body["secoes"]} == {
            "identidade": "alterada", "nova": "nova", "regras": "removida",
        }
        assert body["configuracoes"] == [{"campo": "model", "a": "claude-opus-5", "b": "claude-sonnet-5"}]
        assert body["a"]["hash"] == v1["compiled_hash"]
        assert "Mudou." in body["texto_b"] and "Mudou." not in body["texto_a"]

    def test_prompt_not_found_and_org_scoped(self, studio):
        _publishable(studio)
        v1 = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 25}).json()
        resp = studio.get(f"/api/studio/prompts/sha256:{'f' * 64}")
        assert resp.status_code == 404 and resp.json()["code"] == "prompt_not_found"
        studio.as_other_org()
        assert studio.get(f"/api/studio/prompts/{v1['compiled_hash']}").status_code == 404


class TestFailClosedSeams:
    def test_publish_without_bound_gate_is_503(self, bare_studio_app):
        client, store = bare_studio_app
        from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

        agent = store.create_studio_agent(DEFAULT_ORG_ID, "isa", "Isa", None)
        store.create_draft(DEFAULT_ORG_ID, agent.id, None, DEFAULT_USER_ID)
        resp = client.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 25})
        assert resp.status_code == 503
        # FastAPI resolves dependencies in declaration order: the gate first.
        assert resp.json()["code"] == "eval_gate_unavailable"

    def test_compile_without_bound_catalog_is_503(self, bare_studio_app):
        client, store = bare_studio_app
        from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

        agent = store.create_studio_agent(DEFAULT_ORG_ID, "isa", "Isa", None)
        draft = store.create_draft(DEFAULT_ORG_ID, agent.id, None, DEFAULT_USER_ID)
        resp = client.get(f"{BASE}/isa/versions/{draft.id}/compiled")
        assert resp.status_code == 503
        assert resp.json()["code"] == "knowledge_catalog_unavailable"
