"""``app.main`` exposes every studio router and binds the three fail-closed
seams (Agent Studio §J2) — proven through the real app, end to end."""
from __future__ import annotations

from uuid import UUID

from app.routers.studio_agents_router import get_eval_gate_dep, get_knowledge_catalog_dep
from app.routers.studio_agents_router import get_compiled_hash_provider
from app.routers.studio_evals_router import get_current_hash_dep, get_eval_scheduler_dep
from app.studio.wiring import studio_eval_gate, studio_eval_scheduler, studio_knowledge_catalog
from tests.routers.conftest import install_runtime, wait_until


def test_main_app_exposes_the_studio_routes():
    from app.main import app

    paths = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ()) or ()}
    for expected in [
        ("GET", "/api/studio/agents"),
        ("POST", "/api/studio/agents/{key}/draft/publish"),
        ("GET", "/api/studio/agents/{key}/versions/{version_id}/compiled"),
        ("GET", "/api/studio/prompts/{prompt_hash}"),
        ("GET", "/api/studio/agents/{key}/clients"),
        ("GET", "/api/studio/agents/{key}/knowledge"),
        ("GET", "/api/studio/agents/{key}/knowledge/search"),
        ("POST", "/api/studio/agents/{key}/evals/runs"),
        ("POST", "/api/studio/agents/{key}/import"),
    ]:
        assert expected in paths, expected


def test_the_four_seams_are_bound_in_production():
    from app.main import app

    assert app.dependency_overrides[get_eval_gate_dep] is studio_eval_gate
    assert app.dependency_overrides[get_knowledge_catalog_dep] is studio_knowledge_catalog
    assert app.dependency_overrides[get_eval_scheduler_dep] is studio_eval_scheduler
    assert app.dependency_overrides[get_current_hash_dep] is get_compiled_hash_provider


class TestThroughTheRealBindings:
    def test_compile_and_publish_gate_no_longer_503(self, rt):
        assert rt.post("/api/studio/agents", json={"key": "isa", "nome": "Isa"}).status_code == 201
        rt.put("/api/studio/agents/isa/draft/sections", json={"secoes": [
            {"chave": "id", "titulo": "Id", "ordem": 1, "conteudo": "Você é a Isa.", "ativo": True}]})
        agent = rt.studio.get_agent(rt.org_id, "isa")
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        compiled = rt.get(f"/api/studio/agents/isa/versions/{draft.id}/compiled")
        assert compiled.status_code == 200 and compiled.json()["texto"].startswith("# Id")
        publish = rt.post("/api/studio/agents/isa/draft/publish", json={})
        assert publish.status_code == 409
        assert publish.json()["code"] == "eval_required"

    def test_eval_run_is_scheduled_and_concluded_by_the_runner(self, rt):
        install_runtime(rt.client, [])
        assert rt.post("/api/studio/agents", json={"key": "isa", "nome": "Isa"}).status_code == 201
        rt.put("/api/studio/agents/isa/draft/sections", json={"secoes": [
            {"chave": "id", "titulo": "Id", "ordem": 1, "conteudo": "Você é a Isa.", "ativo": True}]})
        agent = rt.studio.get_agent(rt.org_id, "isa")
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        case = rt.post("/api/studio/agents/isa/evals/cases", json={
            "slug": "reels", "titulo": "Reels", "entrada": "Crie um roteiro",
            "criterios": {"deve": ["ter gancho"], "nao_deve": []}})
        assert case.status_code == 201, case.text

        run = rt.post("/api/studio/agents/isa/evals/runs", json={"version_id": str(draft.id)})
        assert run.status_code == 202, run.text
        run_id = run.json()["id"]
        assert wait_until(lambda: rt.evals.get_run(rt.org_id, agent.id, UUID(run_id)).status == "concluida")
        detail = rt.get(f"/api/studio/agents/isa/evals/runs/{run_id}").json()
        assert (detail["aprovados"], detail["score"]) == (1, 1.0)
        assert detail["resultados"][0]["status"] == "aprovado"

    def test_knowledge_search_route_is_the_kb_buscar_function(self, rt):
        assert rt.post("/api/studio/agents", json={"key": "isa", "nome": "Isa"}).status_code == 201
        col = rt.post("/api/studio/agents/isa/knowledge", json={"slug": "audience", "nome": "Audiência", "tag": "AU"})
        assert col.status_code == 201, col.text
        doc = rt.post(f"/api/studio/agents/isa/knowledge/{col.json()['id']}/documents", json={
            "slug": "ganchos", "titulo": "Ganchos", "tipo": "fonte", "conteudo": "ganchos fortes"})
        assert doc.status_code == 201, doc.text
        hits = rt.get("/api/studio/agents/isa/knowledge/search", params={"q": "ganchos"}).json()["items"]
        assert [h["slug"] for h in hits] == ["ganchos"]
