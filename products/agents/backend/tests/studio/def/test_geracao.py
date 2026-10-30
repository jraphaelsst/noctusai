"""AI-generated first drafts (S3a): the routes, the pipeline, the cap, the retry, the cancel, the sweep, the leak check.

The LLM is the seed's ``FakeProvider`` end to end (``chat_completion_with_usage`` -> the scoped usage collector -> the
catalog price): :class:`ScriptedChat` picks the scripted answer by the area INSTRUCTION in the request (calls run two at
a time, so call ORDER is not deterministic). Auth assertions are strict. No instruction text is real: the generator's
sections are ``INSTR:<chave>`` markers (the words are data, written by the platform admin).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.dependencies import get_auth_context, get_geracao_chat_dep, get_geracao_store_dep, get_skills_store_dep
from app.routers.studio_geracoes_router import get_geracao_agendador_dep
from app.stores.skills_biblioteca import FakeSkillsBibliotecaStore
from app.stores.studio_definitions import SectionInput
from app.stores.studio_geracoes import FakeGeracaoStore
from app.studio import geracao as engine
from app.studio.geracao_itens import hashes_atuais
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.integrations.llm import LLMConfig, chat_completion_with_usage, configure_llm, register
from noctusai_lib.integrations.llm import client as llm_client
from noctusai_lib.integrations.llm.providers import FakeProvider
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, bind_user
from tests.studio.rt.fakes import publish

PLAT = "/api/studio/plataforma"
AGENTS = "/api/studio/agents"
AREAS = ("secoes", "textos", "ferramentas", "decisoes", "specs", "skills", "configuracoes")
BRIEFING = {
    "nome": "Atendente Teste", "objetivo": "Atender clientes de uma loja de bicicletas.", "publico": "Ciclistas urbanos",
    "canal": "web",
}
PLANO = {"persona": "P", "objetivos": ["o1"], "diretrizes": {}}
SAIDAS: dict[str, Any] = {
    "secoes": {"secoes": [
        {"chave": "persona", "titulo": "Persona", "conteudo": "conteudo gerado 1"},
        {"chave": "limites", "titulo": "Limites", "conteudo": "conteudo gerado 2"},
    ]},
    "textos": {"textos": [
        {"chave": "compilador.titulo_ferramentas", "conteudo": "Ferramentas"},
        {"chave": "chave.que.nao.existe", "conteudo": "x"},
    ]},
    "ferramentas": {"ferramentas": [
        {"ferramenta": "handoff", "descricao": "d1", "parametros": {}},
        {"ferramenta": "ferramenta_inventada", "descricao": "d2"},
    ]},
    "decisoes": {"decisoes": [{"chave": "abordagem", "titulo": "Abordagem", "opcoes": [
        {"valor": "a", "rotulo": "A", "padrao": True}, {"valor": "b", "rotulo": "B", "padrao": False}]}]},
    "specs": {"specs": [{"chave": "agencia", "rotulo": "Agência"}]},
    "skills": {"skills": [
        {"chave": "qualificar", "obrigatoria_para": [], "racional": "r"}, {"chave": "faltante", "racional": "r2"}]},
    "configuracoes": {"effort": "low", "max_turns": 12, "idioma": "pt-BR"},
}


def instr(area: str) -> str:
    return "INSTR:planejamento" if area == "planejamento" else f"INSTR:area-{area}"


class ScriptedChat:
    """The ``chat`` seam: answers by instruction through the seed ``FakeProvider`` (priced as Opus)."""

    def __init__(self) -> None:
        self.respostas: dict[str, Any] = {instr("planejamento"): PLANO, **{instr(a): SAIDAS[a] for a in AREAS}}
        self.calls: list[tuple[str, dict]] = []
        self.uso = (1000, 500)
        self._n = 0

    async def __call__(self, messages, **kw):
        user = json.loads(messages[-1]["content"])
        self.calls.append((user["instrucao"], user))
        resp = self.respostas[user["instrucao"]]
        if callable(resp):
            resp = resp(user)
        if isinstance(resp, Exception):
            raise resp
        self._n += 1
        name = f"fake-gen-{self._n}"
        fake = FakeProvider(
            chat_responses=[resp if isinstance(resp, str) else json.dumps(resp)], chat_usage=[self.uso],
            usage_provider="anthropic")
        register(name, lambda: fake)
        return await chat_completion_with_usage(messages, **{**kw, "provider": name})

    def chamadas(self, area: str) -> int:
        return sum(1 for i, _ in self.calls if i == instr(area))


def _platform_admin(studio, org_id=DEFAULT_ORG_ID, user_id=DEFAULT_USER_ID):
    studio.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(user_id), "org_id": str(org_id), "role": "admin", "org_role": "owner"}])


@pytest.fixture
def gen(studio):
    """A platform world: a PUBLISHED generator (role ``gerador``, Opus), a published exemplar, one library skill, a
    target definition, and every seam bound to doubles. ``gen.rodar()`` runs the scheduled job."""
    studio.store.mark_platform_org(DEFAULT_ORG_ID)
    _platform_admin(studio)
    saved_cfg = llm_client._active_config
    configure_llm(LLMConfig(key_provider=lambda *_a, **_k: "test-key"))
    geracoes, skills, chat, pending = FakeGeracaoStore(), FakeSkillsBibliotecaStore(), ScriptedChat(), []
    app = studio.raw.app
    app.dependency_overrides[get_geracao_store_dep] = lambda: geracoes
    app.dependency_overrides[get_skills_store_dep] = lambda: skills
    app.dependency_overrides[get_geracao_chat_dep] = lambda: chat
    app.dependency_overrides[get_geracao_agendador_dep] = lambda: pending.append
    w = SimpleNamespace(studio=studio, geracoes=geracoes, skills=skills, chat=chat, pending=pending)

    def rodar() -> None:
        jobs, pending[:] = list(pending), []
        for coro in jobs:
            asyncio.run(coro)

    w.rodar = rodar
    w.deps = engine.Dependencias(studio=studio.store, geracoes=geracoes, skills=skills, catalog=studio.catalog, chat=chat)
    _gerador(w)
    _exemplar(w)
    sk = skills.criar_skill("qualificar", "Qualificar", None)
    v = skills.criar_rascunho(sk.id, None, None)
    skills.salvar_rascunho(v, {"descricao_modelo": "quando qualificar", "corpo": "corpo"})
    skills.publicar(v, DEFAULT_USER_ID)
    assert studio.post(f"{PLAT}/agents", json={"key": "alvo", "nome": "Alvo"}).status_code == 201
    try:
        yield w
    finally:
        for coro in pending:  # jobs a test deliberately never ran
            coro.close()
        llm_client._active_config = saved_cfg
        app.dependency_overrides.clear()


def _gerador(w, *, sem: tuple[str, ...] = (), publicar: bool = True, key: str = "criador"):
    s = w.studio
    made = s.post(f"{PLAT}/agents", json={
        "key": key, "nome": "Criador", "papel": "gerador",
        "rascunho_padrao": {"provider": "anthropic", "model": "claude-opus-5", "effort": "high"}})
    assert made.status_code == 201, made.text
    agent = s.store.get_agent(DEFAULT_ORG_ID, key)
    draft = s.store.get_draft(DEFAULT_ORG_ID, agent.id)
    chaves = ["planejamento", *(f"area-{a}" for a in AREAS)]
    secoes = [SectionInput("persona", "Persona", 1, "SISTEMA: gere JSON")]
    secoes += [SectionInput(c, c, 10 + i, f"INSTR:{c}") for i, c in enumerate(chaves) if c not in sem]
    s.store.replace_sections(DEFAULT_ORG_ID, draft.id, secoes)
    if publicar:
        publish(s.store, DEFAULT_ORG_ID, agent, draft.id, DEFAULT_USER_ID, catalog=s.catalog)
    return agent


def _exemplar(w):
    s = w.studio
    s.post(f"{PLAT}/agents", json={"key": "modelo", "nome": "Modelo", "papel": "exemplar"})
    agent = s.store.get_agent(DEFAULT_ORG_ID, "modelo")
    draft = s.store.get_draft(DEFAULT_ORG_ID, agent.id)
    s.store.replace_sections(DEFAULT_ORG_ID, draft.id, [SectionInput("persona", "Persona", 1, "texto do exemplar " * 40)])
    publish(s.store, DEFAULT_ORG_ID, agent, draft.id, DEFAULT_USER_ID, catalog=s.catalog)


def _post(w, areas=None, **kw):
    body = {"briefing": BRIEFING, **({"areas": areas} if areas else {}), **kw}
    return w.studio.post(f"{AGENTS}/alvo/geracoes", json=body)


def _get(w, gid):
    return w.studio.get(f"{AGENTS}/alvo/geracoes/{gid}").json()


def _area(body, nome):
    return next(a for a in body["areas"] if a["area"] == nome)


def _tudo(w, **kw):
    r = _post(w, **kw)
    assert r.status_code == 202, r.text
    w.rodar()
    return _get(w, r.json()["id"])


# ── auth ────────────────────────────────────────────────────────────────────


class TestAuth:
    ROTAS = [
        ("POST", f"{AGENTS}/alvo/geracoes", {"briefing": BRIEFING}),
        ("GET", f"{AGENTS}/alvo/geracoes", None),
        ("GET", f"{AGENTS}/alvo/geracoes/{UUID(int=1)}", None),
        ("POST", f"{AGENTS}/alvo/geracoes/{UUID(int=1)}/areas/textos/repetir", {}),
        ("POST", f"{AGENTS}/alvo/geracoes/{UUID(int=1)}/cancelar", None),
        ("GET", f"{PLAT}/agents/alvo", None),
        ("PATCH", f"{PLAT}/agents/alvo", {}),
    ]

    @pytest.mark.parametrize("method,url,body", ROTAS)
    def test_unauthenticated_is_strict_401(self, gen, method, url, body):
        assert gen.studio.raw.request(method, url, json=body).status_code == 401

    @pytest.mark.parametrize("method,url,body", ROTAS)
    def test_an_org_admin_that_is_not_a_platform_admin_is_403(self, gen, method, url, body):
        gen.studio.as_org_admin_only()
        call = getattr(gen.studio.client, method.lower())
        r = call(url) if body is None else call(url, json=body)
        assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"

    def test_a_token_needs_the_content_scope_and_the_platform_issuer(self, gen):
        app = gen.studio.raw.app

        def as_token(scopes, issuer="noctus-platform"):
            app.dependency_overrides[get_auth_context] = lambda: AuthContext(
                org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=list(scopes), raw_token="t",
                api_token_id=UUID(int=9), issuer=issuer)

        as_token(["studio:publish"])
        r = gen.studio.raw.post(f"{AGENTS}/alvo/geracoes", json={"briefing": BRIEFING})
        assert r.status_code == 403 and r.json()["code"] == "scope_missing"
        as_token(["studio:content-write"], issuer="outro")
        r = gen.studio.raw.post(f"{AGENTS}/alvo/geracoes", json={"briefing": BRIEFING})
        assert r.status_code == 403 and r.json()["code"] == "issuer_not_allowed"
        as_token(["studio:content-write"])
        assert gen.studio.raw.post(f"{AGENTS}/alvo/geracoes", json={"briefing": BRIEFING}).status_code == 202


# ── the happy path ──────────────────────────────────────────────────────────


class TestHappyPath:
    def test_post_books_the_run_and_the_job_fills_every_area_as_a_draft(self, gen):
        r = _post(gen)
        assert r.status_code == 202
        b = r.json()
        assert b["status"] == "pendente" and b["agent_key"] == "alvo" and b["limite_usd"] == 5.0
        assert [a["area"] for a in b["areas"]] == list(AREAS) and {a["status"] for a in b["areas"]} == {"pendente"}
        assert len(gen.pending) == 1
        gen.rodar()
        done = _get(gen, b["id"])
        assert done["status"] == "concluida" and done["versao_gerador"] == 1 and done["modelo"] == "claude-opus-5"
        assert done["iniciado_em"] and done["concluido_em"] and done["erro"] is None
        assert {a["status"] for a in done["areas"]} == {"concluida"}
        assert _area(done, "secoes")["itens_escritos"] == 2
        assert {i["chave"] for i in _area(done, "secoes")["itens"]} == {"persona", "limites"}
        assert {i["estado"] for a in done["areas"] for i in a["itens"]} == {"gerado"}

        alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
        assert {s.chave for s in gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id)} == {"persona", "limites"}
        assert [t.chave for t in gen.studio.store.list_textos(DEFAULT_ORG_ID, draft.id)] == ["compilador.titulo_ferramentas"]
        assert [f.ferramenta for f in gen.studio.store.list_ferramentas(DEFAULT_ORG_ID, draft.id)] == ["handoff"]
        assert [d.chave for d in gen.studio.store.list_decisoes(DEFAULT_ORG_ID, draft.id)] == ["abordagem"]
        assert [s.chave for s in gen.studio.store.list_spec_defs(DEFAULT_ORG_ID, draft.id)] == ["agencia"]
        assert [x.skill_chave for x in gen.skills.listar_refs(draft.id)] == ["qualificar"]
        assert (draft.effort, draft.max_turns) == ("low", 12)
        # drafts only: nothing is published, the audit says who/what
        assert gen.studio.store.get_active_version(DEFAULT_ORG_ID, alvo.id) is None
        assert [a.acao for a in gen.studio.store.list_audit_log(DEFAULT_ORG_ID, alvo.id)].count("agente_gerado") == 1

    def test_lacunas_report_what_could_not_be_covered(self, gen):
        done = _tudo(gen)
        assert "skill_inexistente:faltante" in _area(done, "skills")["lacunas"]
        assert "ferramenta_desconhecida:ferramenta_inventada" in _area(done, "ferramentas")["lacunas"]
        textos = _area(done, "textos")["lacunas"]
        assert "chave_desconhecida:chave.que.nao.existe" in textos
        assert any(x.startswith("texto_obrigatorio_ausente:") for x in textos)

    def test_cost_is_the_priced_usage_per_area_and_per_run(self, gen):
        done = _tudo(gen)
        por_chamada = (1000 * 5.0 + 500 * 25.0) / 1_000_000  # opus 5: 5/1M in, 25/1M out
        assert _area(done, "secoes")["custo_usd"] == pytest.approx(por_chamada, abs=1e-4)
        assert done["custo_usd"] == pytest.approx(8 * por_chamada, abs=1e-3)  # planning + 7 areas

    def test_an_area_replaces_only_its_own_rows_and_keeps_the_authors(self, gen):
        alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
        gen.studio.store.replace_sections(DEFAULT_ORG_ID, draft.id, [SectionInput("minha", "Minha", 5, "do autor")])
        done = _tudo(gen, areas=["secoes"])
        assert _area(done, "secoes")["status"] == "concluida"
        assert {s.chave for s in gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id)} == {"minha", "persona", "limites"}

    def test_only_requested_areas_run_and_the_exemplar_text_is_verbatim_for_the_platform_org(self, gen):
        done = _tudo(gen, areas=["specs"])
        assert [a["area"] for a in done["areas"]] == ["specs"]
        assert gen.chat.chamadas("specs") == 1 and gen.chat.chamadas("textos") == 0
        _, entrada = next(c for c in gen.chat.calls if c[0] == instr("specs"))
        persona = entrada["exemplar"][0]["secoes"][0]
        assert persona["tamanho"] > 0 and persona["conteudo"].startswith("texto do exemplar")
        assert set(entrada) >= {"briefing", "plano", "contexto", "exemplar", "schema_saida", "instrucao"}

    def test_the_get_list_is_newest_first(self, gen):
        a = _tudo(gen, areas=["specs"])
        b = _tudo(gen, areas=["specs"], forcar=True)
        ids = [g["id"] for g in gen.studio.get(f"{AGENTS}/alvo/geracoes").json()["items"]]
        assert ids == [b["id"], a["id"]]


# ── validation + refusals ───────────────────────────────────────────────────


class TestRefusals:
    def test_unknown_agent_and_unknown_run_are_404_with_the_flat_body(self, gen):
        r = gen.studio.post(f"{AGENTS}/nao-existe/geracoes", json={"briefing": BRIEFING})
        assert r.status_code == 404 and set(r.json()) == {"code", "message", "detail"}
        assert r.json()["code"] == "agente_nao_encontrado"
        r = gen.studio.get(f"{AGENTS}/alvo/geracoes/{uuid4()}")
        assert r.status_code == 404 and r.json()["code"] == "geracao_nao_encontrada"

    def test_a_legacy_agent_is_409(self, gen):
        gen.studio.store.create_studio_agent(DEFAULT_ORG_ID, "velho", "Velho", None)
        r = gen.studio.post(f"{AGENTS}/velho/geracoes", json={"briefing": BRIEFING})
        assert r.status_code == 409 and r.json()["code"] == "conteudo_modo_legado"

    def test_validation_is_422_and_extra_fields_are_refused(self, gen):
        assert gen.studio.post(f"{AGENTS}/alvo/geracoes", json={"briefing": {**BRIEFING, "objetivo": "curto"}}).status_code == 422
        assert gen.studio.post(f"{AGENTS}/alvo/geracoes", json={"briefing": {**BRIEFING, "extra": 1}}).status_code == 422
        assert _post(gen, limite_usd=5.01).status_code == 422
        assert _post(gen, limite_usd=0).status_code == 422
        assert _post(gen, areas=["nao-existe"]).status_code == 422
        r = gen.studio.post(f"{AGENTS}/alvo/geracoes/{UUID(int=1)}/areas/nao-existe/repetir", json={})
        assert r.status_code == 422 and r.json()["code"] == "area_invalida"

    def test_pii_in_the_examples_is_refused_before_any_llm_call(self, gen):
        r = _post(gen, briefing={**BRIEFING, "exemplos": "fale com maria@exemplo.com"})
        assert r.status_code == 422 and r.json()["code"] == "exemplos_com_pii"
        assert gen.chat.calls == [] and gen.geracoes.list_geracoes(DEFAULT_ORG_ID, UUID(int=0)) == []

    def test_no_published_generator_is_409(self, gen):
        gen.studio.store.update_definicao(DEFAULT_ORG_ID, "criador", {"papel": None})
        r = _post(gen)
        assert r.status_code == 409 and r.json()["code"] == "gerador_indisponivel"

    def test_a_generator_whose_model_has_no_price_is_unavailable(self):
        """The cap could not be computed, so there is no cap: refuse rather than run unbounded."""
        definicao = SimpleNamespace(papel="gerador", org_id=DEFAULT_ORG_ID, id=uuid4())
        versao = SimpleNamespace(id=uuid4(), provider="anthropic", model="modelo-sem-preco", versao=1)
        studio = SimpleNamespace(
            list_platform_definitions=lambda: [definicao], get_active_version=lambda *_a: versao,
            list_sections=lambda *_a: [])
        with pytest.raises(engine.GeracaoErro) as exc:
            engine.carregar_gerador(studio)
        assert exc.value.code == "gerador_indisponivel" and exc.value.status == 409

    def test_one_run_in_flight_per_agent(self, gen):
        assert _post(gen).status_code == 202
        r = _post(gen)
        assert r.status_code == 409 and r.json()["code"] == "geracao_em_andamento"

    def test_a_missing_area_instruction_fails_that_area_only(self, gen):
        _gerador_novo(gen, sem=("area-specs",))
        done = _tudo(gen, areas=["specs", "secoes"])
        assert _area(done, "specs")["status"] == "falhou" and _area(done, "specs")["erro"] == "instrucao_ausente"
        assert _area(done, "secoes")["status"] == "concluida" and done["status"] == "parcial"


def _gerador_novo(w, *, sem):
    w.studio.store.update_definicao(DEFAULT_ORG_ID, "criador", {"papel": None})
    _gerador(w, sem=sem, key="criador-2")


# ── status rules ────────────────────────────────────────────────────────────


class TestStatusRules:
    def test_parcial_when_some_area_fails(self, gen):
        gen.chat.respostas[instr("specs")] = "isto nao e json"
        done = _tudo(gen, areas=["secoes", "specs"])
        assert _area(done, "specs")["status"] == "falhou" and _area(done, "specs")["erro"] == "saida_invalida"
        assert done["status"] == "parcial"

    def test_falhou_when_no_area_concludes(self, gen):
        gen.chat.respostas[instr("specs")] = {"specs": [{"chave": "Invalida!", "rotulo": "x"}]}
        done = _tudo(gen, areas=["specs"])
        assert done["status"] == "falhou" and _area(done, "specs")["erro"] == "saida_invalida"

    def test_a_provider_error_fails_the_area_with_a_fixed_code(self, gen):
        gen.chat.respostas[instr("decisoes")] = RuntimeError("segredo-do-provedor")
        done = _tudo(gen, areas=["decisoes"])
        assert _area(done, "decisoes")["erro"] == "llm_erro" and "segredo" not in json.dumps(done)

    def test_a_failed_planning_fails_every_area(self, gen):
        gen.chat.respostas[instr("planejamento")] = "lixo"
        done = _tudo(gen, areas=["secoes", "specs"])
        assert done["status"] == "falhou" and done["erro"] == "plano_invalido"
        assert {a["status"] for a in done["areas"]} == {"falhou"}
        assert gen.chat.chamadas("secoes") == 0

    def test_a_store_refusal_is_a_fixed_code_not_the_row(self, gen):
        gen.chat.respostas[instr("decisoes")] = {"decisoes": [{"chave": "sem-padrao", "titulo": "T", "opcoes": [
            {"valor": "a", "rotulo": "A", "padrao": False}]}]}
        done = _tudo(gen, areas=["decisoes"])
        assert _area(done, "decisoes")["status"] == "falhou" and _area(done, "decisoes")["erro"] == "escrita_recusada"


# ── the cap ─────────────────────────────────────────────────────────────────


class TestCap:
    def test_a_call_that_could_exceed_the_remaining_budget_is_not_made(self, gen):
        done = _tudo(gen, areas=["secoes", "textos"], limite_usd=0.5)
        assert _area(done, "secoes")["status"] == "concluida"
        textos = _area(done, "textos")
        assert textos["status"] == "pulado" and textos["erro"] == "limite_de_custo"
        assert gen.chat.chamadas("textos") == 0
        assert done["status"] == "parcial" and done["custo_usd"] <= done["limite_usd"]

    def test_a_cap_below_the_planning_estimate_skips_everything(self, gen):
        done = _tudo(gen, areas=["secoes"], limite_usd=0.01)
        assert done["status"] == "falhou" and _area(done, "secoes")["status"] == "pulado"
        assert gen.chat.calls == [] and done["custo_usd"] == 0

    def test_the_cap_is_bounded_by_the_database_too(self):
        with pytest.raises(ValueError):
            FakeGeracaoStore().create_geracao(
                DEFAULT_ORG_ID, uuid4(), briefing={}, areas=["secoes"], forcar=False, modelo="m", provider="p",
                limite_usd=5.01, versao_gerador=1, criado_por=uuid4())


# ── edited content + force ──────────────────────────────────────────────────


class TestEditedContent:
    def test_an_edited_item_is_flagged_and_blocks_a_new_run_until_forced(self, gen):
        first = _tudo(gen, areas=["secoes"])
        alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
        atuais = gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id)
        gen.studio.store.replace_sections(DEFAULT_ORG_ID, draft.id, [
            SectionInput(id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, ativo=s.ativo,
                         conteudo=("EDITADO" if s.chave == "persona" else s.conteudo)) for s in atuais])
        estados = {i["chave"]: i["estado"] for i in _area(_get(gen, first["id"]), "secoes")["itens"]}
        assert estados == {"persona": "editado", "limites": "gerado"}
        r = _post(gen, areas=["secoes", "specs"])
        assert r.status_code == 409 and r.json()["code"] == "conteudo_editado" and r.json()["detail"] == ["secoes"]
        assert _post(gen, areas=["specs"]).status_code == 202  # an area with nothing edited is fine
        gen.rodar()
        forced = _post(gen, areas=["secoes"], forcar=True)
        assert forced.status_code == 202
        gen.rodar()
        assert {s.chave: s.conteudo for s in gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id)}["persona"] == "conteudo gerado 1"

    def test_a_deleted_row_is_omitted(self, gen):
        first = _tudo(gen, areas=["secoes"])
        alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
        gen.studio.store.replace_sections(DEFAULT_ORG_ID, draft.id, [])
        assert _area(_get(gen, first["id"]), "secoes")["itens"] == []


# ── retry ───────────────────────────────────────────────────────────────────


class TestRetry:
    def test_a_failed_area_runs_again_and_the_run_becomes_concluida(self, gen):
        gen.chat.respostas[instr("specs")] = "nao e json"
        done = _tudo(gen, areas=["secoes", "specs"])
        assert done["status"] == "parcial"
        gen.chat.respostas[instr("specs")] = SAIDAS["specs"]
        url = f"{AGENTS}/alvo/geracoes/{done['id']}/areas/specs/repetir"
        r = gen.studio.post(url, json={})
        assert r.status_code == 202 and r.json()["status"] == "executando"
        assert _area(r.json(), "specs")["status"] == "pendente"
        gen.rodar()
        again = _get(gen, done["id"])
        assert again["status"] == "concluida" and _area(again, "specs")["status"] == "concluida"
        assert gen.chat.chamadas("secoes") == 1, "only the retried area ran again"
        assert gen.chat.chamadas("planejamento") == 1, "the stored plan is reused"

    def test_a_concluded_area_needs_force(self, gen):
        done = _tudo(gen, areas=["specs"])
        url = f"{AGENTS}/alvo/geracoes/{done['id']}/areas/specs/repetir"
        r = gen.studio.post(url, json={})
        assert r.status_code == 409 and r.json()["code"] == "area_concluida"
        assert gen.studio.post(url, json={"forcar": True}).status_code == 202

    def test_a_retry_while_another_run_executes_is_409(self, gen):
        done = _tudo(gen, areas=["specs"])
        assert _post(gen, areas=["secoes"]).status_code == 202  # in flight now
        r = gen.studio.post(f"{AGENTS}/alvo/geracoes/{done['id']}/areas/specs/repetir", json={"forcar": True})
        assert r.status_code == 409 and r.json()["code"] == "geracao_em_andamento"


# ── cancel ──────────────────────────────────────────────────────────────────


class TestCancel:
    def test_cancel_marks_the_run_and_its_pending_areas(self, gen):
        r = _post(gen, areas=["secoes", "specs"])
        c = gen.studio.post(f"{AGENTS}/alvo/geracoes/{r.json()['id']}/cancelar")
        assert c.status_code == 200 and c.json()["status"] == "cancelada"
        assert {a["status"] for a in c.json()["areas"]} == {"cancelada"}
        gen.rodar()  # the job finds nothing to do
        assert gen.chat.calls == []
        assert _get(gen, r.json()["id"])["status"] == "cancelada"

    def test_an_in_flight_call_finishes_but_its_output_is_discarded(self, gen):
        r = _post(gen, areas=["secoes"])
        gid = UUID(r.json()["id"])

        def cancela_no_meio(_user):
            engine.cancelar(gen.deps, org_id=DEFAULT_ORG_ID, key="alvo", geracao_id=gid)
            return SAIDAS["secoes"]

        gen.chat.respostas[instr("secoes")] = cancela_no_meio
        gen.rodar()
        done = _get(gen, str(gid))
        assert done["status"] == "cancelada" and _area(done, "secoes")["itens_escritos"] == 0
        alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
        assert gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id) == []
        assert done["custo_usd"] > 0, "the discarded call is still paid for"

    def test_cancelling_a_finished_run_is_409(self, gen):
        done = _tudo(gen, areas=["specs"])
        r = gen.studio.post(f"{AGENTS}/alvo/geracoes/{done['id']}/cancelar")
        assert r.status_code == 409 and r.json()["code"] == "geracao_finalizada"


# ── orphan sweep ────────────────────────────────────────────────────────────


def test_the_startup_sweep_fails_stale_runs_and_their_unfinished_areas(gen):
    r = _post(gen, areas=["secoes", "specs"])
    gid = UUID(r.json()["id"])
    gen.geracoes.update_area(DEFAULT_ORG_ID, gid, "secoes", {"status": "executando"})
    assert engine.varrer_geracoes_orfas(gen.geracoes) == 1
    done = _get(gen, str(gid))
    assert done["status"] == "falhou" and done["erro"] == "interrompida"
    assert {a["status"] for a in done["areas"]} == {"falhou"}
    assert engine.varrer_geracoes_orfas(gen.geracoes) == 0
    # a failed area can be retried afterwards
    assert gen.studio.post(f"{AGENTS}/alvo/geracoes/{gid}/areas/secoes/repetir", json={}).status_code == 202


# ── leak check (a target outside the platform org) ──────────────────────────


class TestLeakCheck:
    def test_non_platform_target_gets_structure_only_and_a_reproduced_exemplar_is_blocked(self, gen):
        outra = UUID(int=777)
        alvo = gen.studio.store.seed_agent(
            outra, "externo", conteudo_modo="linhas", definition_scope="plataforma", definition_mode="studio")
        gen.studio.store.create_draft(outra, alvo.id, None, DEFAULT_USER_ID)
        rec = gen.geracoes.create_geracao(
            outra, alvo.id, briefing=BRIEFING, areas=["secoes"], forcar=False, modelo="claude-opus-5",
            provider="anthropic", limite_usd=5.0, versao_gerador=1, criado_por=DEFAULT_USER_ID)
        copiado = "texto do exemplar " * 40
        gen.chat.respostas[instr("secoes")] = {"secoes": [{"chave": "vazou", "titulo": "V", "conteudo": copiado}]}
        asyncio.run(engine.executar(gen.deps, org_id=outra, geracao_id=rec.id, agent_id=alvo.id, areas=["secoes"]))
        area = gen.geracoes.list_areas(outra, rec.id)[0]
        assert area.status == "falhou" and area.erro == "vazamento_detectado"
        _, entrada = next(c for c in gen.chat.calls if c[0] == instr("secoes"))
        assert "conteudo" not in entrada["exemplar"][0]["secoes"][0], "no verbatim exemplar text outside the platform org"
        assert entrada["exemplar"][0]["secoes"][0]["tamanho"] > 0, "the STRUCTURE is always shared"
        draft = gen.studio.store.get_draft(outra, alvo.id)
        assert gen.studio.store.list_sections(outra, draft.id) == []


# ── completeness + learning ─────────────────────────────────────────────────


class TestCompletenessAndLearning:
    def test_the_agent_page_carries_the_completeness_signal(self, gen):
        before = gen.studio.get(f"{AGENTS}/alvo").json()["conteudo_status"]
        assert before["textos_preenchidos"] == 0 and before["textos_total"] > 0
        assert "compilador.titulo_ferramentas" in before["obrigatorios_faltando"]
        _tudo(gen, areas=["textos"])
        after = gen.studio.get(f"{AGENTS}/alvo").json()["conteudo_status"]
        assert after["textos_preenchidos"] == 1 and after["textos_total"] == before["textos_total"]
        assert "compilador.titulo_ferramentas" not in after["obrigatorios_faltando"]

    def test_legacy_agents_have_no_completeness_signal(self, gen):
        gen.studio.store.create_studio_agent(DEFAULT_ORG_ID, "velho", "Velho", None)
        assert gen.studio.get(f"{AGENTS}/velho").json()["conteudo_status"] is None

    def test_the_first_publish_after_a_generation_stores_generated_vs_published(self, gen):
        first = _tudo(gen, areas=["secoes"])
        alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
        atuais = gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id)
        gen.studio.store.replace_sections(DEFAULT_ORG_ID, draft.id, [
            SectionInput(id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, ativo=s.ativo,
                         conteudo=("EDITADO" if s.chave == "persona" else s.conteudo)) for s in atuais
            if s.chave != "limites"] + [SectionInput("nova", "Nova", 99, "do autor")])
        published = publish(gen.studio.store, DEFAULT_ORG_ID, alvo, draft.id, DEFAULT_USER_ID, catalog=gen.studio.catalog)
        assert engine.registrar_aprendizado(gen.deps, alvo, published) == 1
        ap = gen.geracoes.get_geracao(DEFAULT_ORG_ID, UUID(first["id"])).aprendizado
        assert ap["versao_publicada"] == published.versao
        assert ap["areas"]["secoes"] == {
            "gerados": ["limites", "persona"], "mantidos": [], "editados": ["persona"], "removidos": ["limites"],
            "adicionados_pelo_autor": ["nova"],
        }
        assert engine.registrar_aprendizado(gen.deps, alvo, published) == 0, "only the FIRST publish after a generation"


# ── platform create + briefing, and the data-driven definition ──────────────


class TestCreateWithBriefing:
    def test_a_new_definition_with_a_briefing_starts_a_generation(self, gen):
        r = gen.studio.post(f"{PLAT}/agents", json={"key": "novo-agente", "nome": "Novo", "briefing": BRIEFING})
        assert r.status_code == 201, r.text
        g = r.json()["geracao"]
        assert g["status"] == "pendente" and g["agent_key"] == "novo-agente" and len(g["areas"]) == 7
        gen.rodar()
        novo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "novo-agente")
        draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, novo.id)
        assert len(gen.studio.store.list_sections(DEFAULT_ORG_ID, draft.id)) == 2

    def test_an_existing_key_without_a_briefing_starts_nothing(self, gen):
        r = gen.studio.post(f"{PLAT}/agents", json={"key": "alvo", "reutilizar": True})
        assert r.status_code == 201 and r.json()["geracao"] is None and gen.pending == []

    def test_an_existing_key_is_409_and_starts_no_generation(self, gen):
        r = gen.studio.post(f"{PLAT}/agents", json={"key": "alvo", "nome": "Alvo", "briefing": BRIEFING})
        assert r.status_code == 409 and r.json()["code"] == "agente_ja_existe" and gen.pending == []

    def test_without_a_briefing_the_response_has_no_generation(self, gen):
        assert gen.studio.post(f"{PLAT}/agents", json={"key": "so-casca", "nome": "Casca"}).json()["geracao"] is None


def test_hashes_are_the_single_identity_of_an_item(gen):
    _tudo(gen, areas=["specs"])
    alvo = gen.studio.store.get_agent(DEFAULT_ORG_ID, "alvo")
    draft = gen.studio.store.get_draft(DEFAULT_ORG_ID, alvo.id)
    h = hashes_atuais("specs", store=gen.studio.store, skills=gen.skills, org_id=DEFAULT_ORG_ID, version=draft)
    assert set(h) == {"agencia"} and len(h["agencia"]) == 32
