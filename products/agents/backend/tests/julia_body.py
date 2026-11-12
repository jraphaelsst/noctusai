"""TEST DATA: the body a platform admin / the content token sends to create the SDR-style platform definition.

Not a code registry -- every attribute is data on the definition row (049), exactly what the UI would send."""
JULIA_BODY = {
    "key": "julia", "nome": "Julia", "runtime": "llm", "owner_product": "social-wiring",
    "escopo_qualificacao": "sdr", "padrao_qualificacao": "imob-lead", "instanciavel": False,
    "rascunho_padrao": {
        "provider": "openai", "model": "gpt-5.6-terra", "effort": "medium", "max_turns": 8,
        "tool_policy": {"web_search": False, "knowledge": False},
    },
}


def com_pai(studio, body=None, *, chave="agente-base"):
    """``body`` (default :data:`JULIA_BODY`) with a ``pai_agent_id`` -- creating a non-template agent requires a parent
    template. The first call seeds the root template ``chave`` straight in the store (the platform org must already be
    marked) and VALIDATES it (one critical case, consolidated on its current content) so the chain gate lets a child
    publish: tests that are not about the chain get a parent that is simply fine."""
    from uuid import uuid4

    from app.routers.studio_agents_router import get_consolidacao_store_dep, get_eval_store_dep
    from app.stores.studio_eval_consolidacao import FakeConsolidacaoStore
    from app.stores.studio_evals import EvalCaseInput, FakeEvalStore
    from app.studio.bundles import compile_version
    from app.studio.consolidacao_service import registrar_resultados
    from tests.routers.conftest import DEFAULT_ORG_ID

    pai = studio.store.get_platform_definition(chave)
    if pai is None:
        if getattr(studio, "evals", None) is None:
            studio.evals = FakeEvalStore()
        if getattr(studio, "consolidacao", None) is None:
            studio.consolidacao = FakeConsolidacaoStore(studio.evals)
        studio.raw.app.dependency_overrides[get_eval_store_dep] = lambda: studio.evals
        studio.raw.app.dependency_overrides[get_consolidacao_store_dep] = lambda: studio.consolidacao
        pai = studio.store.create_studio_agent(DEFAULT_ORG_ID, chave, "Agente base", None, runtime="llm", definition_scope="plataforma")
        studio.store.update_definicao(DEFAULT_ORG_ID, chave, {"modelo": True})
        draft = studio.store.create_draft(DEFAULT_ORG_ID, pai.id, None, pai.id)
        pai = studio.store.get_platform_definition(chave)
        caso = studio.evals.create_case(DEFAULT_ORG_ID, pai.id, EvalCaseInput(
            slug="base-1", titulo="t", entrada="e", criterios={"deve": ["x"], "nao_deve": []}))
        studio.consolidacao.set_caso(DEFAULT_ORG_ID, pai.id, caso.id, criticidade="critico", depende_de=None,
                                     depende_de_origem="declarada")
        c = compile_version(studio.store, studio.catalog, DEFAULT_ORG_ID, pai, studio.store.get_version(DEFAULT_ORG_ID, draft.id))
        studio.store.set_compiled_hash(DEFAULT_ORG_ID, draft.id, c.hash)
        studio.store.publish_version(DEFAULT_ORG_ID, draft.id, pai.id, None, "motivo suficientemente longo aqui",
                                     expected_hash=c.hash, texto="T", manifest=[])
        for _ in range(10):
            registrar_resultados(studio.consolidacao, org_id=DEFAULT_ORG_ID, agent_id=pai.id, suite="comportamento",
                                 run_id=uuid4(), run_tipo="comportamento", hash_atual=c.hash, partes=c.partes,
                                 resultados=[(caso.id, ["aprovado"])])
    return {**(JULIA_BODY if body is None else body), "pai_agent_id": str(pai.id)}
