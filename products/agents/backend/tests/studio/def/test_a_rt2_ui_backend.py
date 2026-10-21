"""Julia v2 A-RT2 for the Studio UI (FE-A): server-provided capabilities, conformance routes, registries,
``ponto_cache``, the mechanism-run summary and the replace-set optimistic lock. Strict 401/403 on each."""
from __future__ import annotations

import importlib
from uuid import UUID, uuid4

import pytest

from app.dependencies import get_auth_context
from app.routers.studio_agents_router import get_mecanismo_resumo_dep
from app.schemas.studio import MecanismoResumoOut
from app.stores.conformidade import Violacao
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

_base = importlib.import_module("tests.studio.def.test_studio_conteudo_router")
BASE, PLAT = _base.BASE, _base.PLAT
UI = "/api/studio"


def _julia(studio):
    studio.store.mark_platform_org(DEFAULT_ORG_ID)
    _base._platform_admin(studio)
    assert studio.post(f"{PLAT}/agents", json={"key": "julia"}).status_code == 201
    studio.as_role("owner")
    _base._fill(studio)
    return studio.store.get_agent(DEFAULT_ORG_ID, "julia")


def _as(studio, *, org_role: str, platform: bool):
    studio.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": org_role,
        "role": "admin" if platform else "user"}])


class TestCapacidades:
    URL = f"{UI}/agents/julia/capacidades"

    def test_401_and_product_token_403(self, studio):
        _julia(studio)
        assert studio.raw.get(self.URL).status_code == 401
        app = studio.raw.app
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["x"], raw_token="t",
            api_token_id=uuid4(), principal_agent_id=None, issuer="social-wiring")
        try:
            r = studio.raw.get(self.URL)
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert r.status_code == 403 and r.json()["code"] == "user_required"

    @pytest.mark.parametrize("org_role,platform,tier", [
        ("owner", True, "plataforma"), ("owner", False, "org_admin"), ("admin", False, "org_admin"),
        ("member", False, "org_member"), ("viewer", False, "org_member"),
    ])
    def test_the_server_names_the_tier_and_its_tabs(self, studio, org_role, platform, tier):
        _julia(studio)
        _as(studio, org_role=org_role, platform=platform)
        r = studio.get(self.URL)
        assert r.status_code == 200, r.text
        body = r.json()
        from app.routers.studio_ui_router import ABAS_POR_TIER

        assert body == {"agent_key": "julia", "tier": tier, "abas": list(ABAS_POR_TIER[tier])}

    def test_only_the_platform_tier_sees_definition_tabs(self):
        from app.routers.studio_ui_router import ABAS_POR_TIER

        definicao = {"secoes", "skills", "textos", "ferramentas", "decisoes", "qualificacao", "compilado"}
        assert definicao <= set(ABAS_POR_TIER["plataforma"])
        assert not definicao & set(ABAS_POR_TIER["org_admin"]) and not definicao & set(ABAS_POR_TIER["org_member"])

    def test_unknown_agent_is_404(self, studio):
        assert studio.get(f"{UI}/agents/nao-existe/capacidades").status_code == 404


class TestConformidade:
    def _url(self, regra="vazamento_prompt"):
        return f"{UI}/agents/julia/conformidade/regras/{regra}"

    def test_boundaries_are_strict(self, studio):
        _julia(studio)
        for m, u in (("get", self._url()), ("put", self._url()), ("get", f"{UI}/agents/julia/conformidade/violacoes")):
            assert getattr(studio.raw, m)(u, **({"json": {}} if m == "put" else {})).status_code == 401
        _as(studio, org_role="owner", platform=False)
        for m, u in (("get", self._url()), ("put", self._url()), ("get", f"{UI}/agents/julia/conformidade/violacoes")):
            r = getattr(studio, m)(u, **({"json": {}} if m == "put" else {}))
            assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"
        _as(studio, org_role="member", platform=False)
        assert studio.get(f"{UI}/agents/julia/conformidade/resumo").status_code == 403
        assert studio.raw.get(f"{UI}/agents/julia/conformidade/resumo").status_code == 401

    def test_read_and_write_a_rule(self, studio):
        agent = _julia(studio)
        r = studio.get(self._url()).json()
        assert r["regra"] == "vazamento_prompt" and r["ativo"] is True and r["politica"] == "bloquear"
        put = studio.put(self._url(), json={"politica": "registrar", "parametros": {"shingle_tokens": 24}})
        assert put.status_code == 200, put.text
        assert put.json()["politica"] == "registrar" and put.json()["parametros"] == {"shingle_tokens": 24}
        assert studio.conformidade.regras(DEFAULT_ORG_ID, agent.id)["vazamento_prompt"].parametros == {"shingle_tokens": 24}
        assert any(a.acao == "definicao_lida" for a in studio.store.list_audit_log(DEFAULT_ORG_ID, agent.id))

    @pytest.mark.parametrize("body", [
        {"politica": "ignorar"}, {"parametros": {"shingle_tokens": 3}}, {"parametros": {"shingle_tokens": "20"}},
        {"parametros": {"x": "y" * 9000}}, {"extra": 1},
    ])
    def test_invalid_input_is_422(self, studio, body):
        _julia(studio)
        assert studio.put(self._url(), json=body).status_code == 422

    @pytest.mark.parametrize("parametros", [
        {"limiar_suspeito": 0}, {"limiar_handoff": 21}, {"limiar_suspeito": "3"}, {"limiar_handoff": True},
        {"limiar_suspeito": 3, "limiar_handoff": 3}, {"limiar_suspeito": 5, "limiar_handoff": 4},
    ])
    def test_escalation_thresholds_outside_the_db_check_are_422(self, studio, parametros):
        # mirrors conformidade_regras_escala_limiares_check (044): refused here, never a 500 from the DB
        _julia(studio)
        assert studio.put(self._url("escala_seguranca"), json={"parametros": parametros}).status_code == 422

    def test_valid_escalation_thresholds_are_stored(self, studio):
        agent = _julia(studio)
        put = studio.put(self._url("escala_seguranca"), json={"parametros": {"limiar_suspeito": 2, "limiar_handoff": 20}})
        assert put.status_code == 200, put.text
        assert studio.conformidade.regras(DEFAULT_ORG_ID, agent.id)["escala_seguranca"].parametros == {
            "limiar_suspeito": 2, "limiar_handoff": 20}

    def test_unknown_rule_is_404(self, studio):
        _julia(studio)
        assert studio.get(self._url("inventada")).status_code == 404

    def _violacoes(self, studio, agent, n):
        for i in range(n):
            studio.conformidade.registrar_violacao(
                DEFAULT_ORG_ID, agent.id,
                Violacao("termina_sem_pergunta" if i % 2 else "vazamento_prompt", "registrar", {"janelas": i}, bloqueada=i % 2 == 0))

    def test_violations_are_paged_codes_only(self, studio):
        agent = _julia(studio)
        self._violacoes(studio, agent, 5)
        r = studio.get(f"{UI}/agents/julia/conformidade/violacoes?tamanho=2&pagina=1").json()
        assert len(r["items"]) == 2 and r["tem_mais"] is True
        assert set(r["items"][0]) == {"id", "regra", "politica", "bloqueada", "criada_em", "detalhe"}
        p3 = studio.get(f"{UI}/agents/julia/conformidade/violacoes?tamanho=2&pagina=3").json()
        assert len(p3["items"]) == 1 and p3["tem_mais"] is False

    def test_org_admin_gets_counts_only(self, studio):
        agent = _julia(studio)
        self._violacoes(studio, agent, 5)
        _as(studio, org_role="owner", platform=False)
        r = studio.get(f"{UI}/agents/julia/conformidade/resumo")
        assert r.status_code == 200
        assert r.json() == {"total": 5, "bloqueadas": 3, "por_regra": {"vazamento_prompt": 3, "termina_sem_pergunta": 2}}


class TestRegistries:
    def test_textos_registro_is_platform_admin_structure_only(self, studio):
        assert studio.raw.get(f"{UI}/textos/registro").status_code == 401
        _as(studio, org_role="owner", platform=False)
        assert studio.get(f"{UI}/textos/registro").status_code == 403
        _as(studio, org_role="owner", platform=True)
        r = studio.get(f"{UI}/textos/registro")
        assert r.status_code == 200
        itens = {i["chave"]: i for i in r.json()}
        assert set(next(iter(itens.values()))) == {
            "chave", "categoria", "obrigatoria", "placeholders_permitidos", "aplica_a", "condicao", "fixo_plataforma",
            "aparece_quando"}
        assert itens["compilador.titulo_skills"]["aparece_quando"] == "todas:skills"
        assert any(i["aplica_a"] == "canal" and i["placeholders_permitidos"] for i in itens.values())

    def test_ferramentas_registro_lists_schema_and_enum_values_only(self, studio):
        assert studio.raw.get(f"{UI}/ferramentas/registro").status_code == 401
        _as(studio, org_role="admin", platform=False)
        assert studio.get(f"{UI}/ferramentas/registro").status_code == 403
        _as(studio, org_role="owner", platform=True)
        itens = {i["ferramenta"]: i for i in studio.get(f"{UI}/ferramentas/registro").json()}
        h = itens["handoff"]
        motivo = next(p for p in h["parametros"] if p["nome"] == "motivo_codigo")
        assert "pedido_humano" in motivo["valores"] and "motivo_codigo.pedido_humano" in h["chaves_rotulo_enum"]
        rp = itens["registrar_perfil"]
        assert {"itens", "itens.criterio", "itens.trecho"} <= {p["nome"] for p in rp["parametros"]}
        assert itens["kb_buscar"]["parametros"] == []
        assert "descricao" not in h and all("descricao" not in p for p in h["parametros"])


class TestPontoCache:
    def test_compiled_and_payload_carry_it(self, studio):
        agent = _julia(studio)
        draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
        c = studio.get(f"{BASE}/julia/versions/{draft.id}/compiled").json()
        assert isinstance(c["ponto_cache"], int) and c["ponto_cache"] >= 0
        p = studio.get(f"{BASE}/julia/versions/{draft.id}/payload").json()
        assert p["ponto_cache"] == c["ponto_cache"]
        _base._publish(studio)
        org = studio.get(f"{BASE}/julia/compilado").json()
        assert isinstance(org["ponto_cache"], int)


class TestMecanismoSummary:
    def test_null_without_a_gate_and_the_bound_summary_when_there_is_one(self, studio):
        agent = _julia(studio)
        draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
        # a fresh draft has no stamped hash yet -> no run to speak of
        assert studio.get(f"{BASE}/julia/versions/{draft.id}").json()["mecanismo"] is None
        studio.store.set_compiled_hash(DEFAULT_ORG_ID, draft.id, "sha256:" + "a" * 64)
        app = studio.raw.app
        visto = {}

        def _reader(org_id, version_id, compiled_hash):
            visto["args"] = (org_id, version_id, compiled_hash)
            return MecanismoResumoOut(
                run_id=UUID(int=5), driver="live", aprovado=True, completo=True, casos_total=3, casos_aprovados=3)

        app.dependency_overrides[get_mecanismo_resumo_dep] = lambda: _reader
        body = studio.get(f"{BASE}/julia/versions/{draft.id}").json()
        assert body["mecanismo"]["driver"] == "live" and body["mecanismo"]["casos_aprovados"] == 3
        assert visto["args"][2] == body["compiled_hash"] == "sha256:" + "a" * 64

    def test_a_failing_reader_never_fails_the_read(self, studio):
        agent = _julia(studio)
        draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
        studio.store.set_compiled_hash(DEFAULT_ORG_ID, draft.id, "sha256:" + "b" * 64)

        def _boom(*_a):
            raise RuntimeError("down")

        studio.raw.app.dependency_overrides[get_mecanismo_resumo_dep] = lambda: _boom
        r = studio.get(f"{BASE}/julia/versions/{draft.id}")
        assert r.status_code == 200 and r.json()["mecanismo"] is None


class TestOptimisticLock:
    @pytest.mark.parametrize("campo,corpo", [
        ("textos", {"itens": _base.TEXTOS}),
        ("ferramentas", {"itens": _base.FERRAMENTAS}),
        ("decisoes", {"itens": []}),
        ("specs", {"itens": _base.SPECS}),
    ])
    def test_stale_expected_hash_is_409_and_the_current_one_passes(self, studio, campo, corpo):
        agent = _julia(studio)
        url = f"{BASE}/julia/draft/{campo}"
        antes = studio.store.get_draft(DEFAULT_ORG_ID, agent.id).compiled_hash
        stale = studio.put(url, json={**corpo, "expected_hash": "sha256:" + "0" * 64})
        assert stale.status_code == 409 and stale.json()["code"] == "conflito_de_versao"
        assert studio.store.get_draft(DEFAULT_ORG_ID, agent.id).compiled_hash == antes  # nothing was written
        ok = studio.put(url, json={**corpo, "expected_hash": antes})
        assert ok.status_code == 200, ok.text
        assert studio.put(url, json=corpo).status_code == 200  # no expected_hash -> no check

    def test_two_editors_the_second_loses(self, studio):
        agent = _julia(studio)
        lido = studio.store.get_draft(DEFAULT_ORG_ID, agent.id).compiled_hash
        assert studio.put(f"{BASE}/julia/draft/textos", json={"itens": _base.TEXTOS, "expected_hash": lido}).status_code == 200
        # the first write re-stamped the hash only if it changed the compile; force a visible change
        studio.put(f"{BASE}/julia/draft/ferramentas", json={"itens": [
            {"ferramenta": "handoff", "descricao": "Outra descrição.", "parametros": {}}]})
        r = studio.put(f"{BASE}/julia/draft/textos", json={"itens": _base.TEXTOS, "expected_hash": lido})
        assert r.status_code == 409 and r.json()["code"] == "conflito_de_versao"


class TestSkillsInTheHashAndTheLock:
    """A-polish #9 + #11: a version's own skill body is hashed (it is on-demand, never in ``texto``), so editing it
    moves the draft hash and breaks a stale CAS; and the skill PATCH itself takes ``expected_hash``."""

    def _skill(self, studio):
        agent = _julia(studio)
        r = studio.post(f"{BASE}/julia/draft/skills", json={"nome": "ofertar", "descricao": "Quando ofertar.",
                                                            "corpo": "Passo 1."})
        assert r.status_code == 201, r.text
        return agent, r.json()["id"]

    def _hash(self, studio, agent):
        return studio.store.get_draft(DEFAULT_ORG_ID, agent.id).compiled_hash

    def test_a_skill_body_edit_moves_the_hash_and_a_stale_writer_loses(self, studio):
        agent, sid = self._skill(studio)
        lido = self._hash(studio, agent)
        assert lido is not None
        assert studio.patch(f"{BASE}/julia/draft/skills/{sid}", json={"corpo": "Passo 2."}).status_code == 200
        depois = self._hash(studio, agent)
        assert depois is not None and depois != lido
        r = studio.put(f"{BASE}/julia/draft/textos", json={"itens": _base.TEXTOS, "expected_hash": lido})
        assert r.status_code == 409 and r.json()["code"] == "conflito_de_versao"

    def test_the_skill_patch_has_the_same_optimistic_lock(self, studio):
        agent, sid = self._skill(studio)
        url = f"{BASE}/julia/draft/skills/{sid}"
        lido = self._hash(studio, agent)
        stale = studio.patch(url, json={"corpo": "Outro.", "expected_hash": "sha256:" + "0" * 64})
        assert stale.status_code == 409 and stale.json()["code"] == "conflito_de_versao"
        assert studio.store.get_skill(DEFAULT_ORG_ID, UUID(sid)).corpo == "Passo 1."  # nothing was written
        ok = studio.patch(url, json={"corpo": "Outro.", "expected_hash": lido})
        assert ok.status_code == 200 and ok.json()["corpo"] == "Outro."
        # the edit moved the hash: the same (now stale) token is refused the second time
        again = studio.patch(url, json={"corpo": "Mais um.", "expected_hash": lido})
        assert again.status_code == 409 and again.json()["code"] == "conflito_de_versao"
        assert studio.patch(url, json={"corpo": "Sem trava."}).status_code == 200  # no expected_hash -> no check


def _content_token(studio, *, issuer="noctus-platform", scopes=("studio:content-write",)):
    studio.raw.app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=list(scopes), raw_token="tok",
        api_token_id=UUID(int=9), principal_agent_id=None, issuer=issuer)


class TestMcpContentKindsBackend:
    """A-polish #3: the ``noctus.agents.content`` kinds ``evals_mecanismo`` / ``conformidade_regras`` ride the same
    platform content token as the other kinds -- platform-issued only, audited, the definition's own row only."""

    CASE = {"slug": "m1", "titulo": "Oferta só com o mínimo", "entrada": "roteiro", "suite": "mecanismo", "k": 2,
            "roteiro": {"turnos": [{"lead": "oi, quero comprar"}, {"lead": "cpf [[cpf_sintetico_valido]]"}]},
            "asserts": {"sem_violacoes": True}}

    @pytest.fixture(autouse=True)
    def _one_eval_store(self, studio):
        """Every request reads the SAME in-memory eval store (the production dep builds one per call for a Fake)."""
        from app.routers.studio_evals_router import get_eval_store_dep
        from app.stores.studio_evals import FakeEvalStore

        store = FakeEvalStore()
        studio.raw.app.dependency_overrides[get_eval_store_dep] = lambda: store
        yield
        studio.raw.app.dependency_overrides.pop(get_eval_store_dep, None)

    def test_the_token_creates_lists_and_edits_a_mechanism_case_and_is_audited(self, studio):
        agent = _julia(studio)
        _content_token(studio)
        try:
            r = studio.raw.post(f"{BASE}/julia/evals/cases", json=self.CASE)
            assert r.status_code == 201, r.text
            body = r.json()
            assert (body["suite"], body["k"], body["asserts"]) == ("mecanismo", 2, {"sem_violacoes": True})
            listed = studio.raw.get(f"{BASE}/julia/evals/cases").json()["items"]
            assert [c["slug"] for c in listed] == ["m1"] and listed[0]["roteiro"] == self.CASE["roteiro"]
            p = studio.raw.patch(f"{BASE}/julia/evals/cases/{body['id']}", json={"k": 3})
            assert p.status_code == 200 and p.json()["k"] == 3
            # deleting stays a human platform-admin act
            assert studio.raw.delete(f"{BASE}/julia/evals/cases/{body['id']}").status_code == 403
        finally:
            studio.raw.app.dependency_overrides.pop(get_auth_context, None)
        rows = [a for a in studio.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "conteudo_editado_mcp"]
        assert [a.depois["kind"] for a in rows] == ["eval_caso", "eval_caso"] and rows[0].actor == UUID(int=9)
        assert "roteiro" not in str([a.depois for a in rows])  # the audit names the case, never its content

    def test_a_mechanism_case_with_personal_data_or_an_unknown_token_is_refused(self, studio):
        _julia(studio)
        com_cpf = {**self.CASE, "slug": "m2", "roteiro": {"turnos": [{"lead": "meu cpf 529.982.247-25"}]}}
        assert studio.post(f"{BASE}/julia/evals/cases", json=com_cpf).status_code == 422
        token = {**self.CASE, "slug": "m3", "roteiro": {"turnos": [{"lead": "[[rg_real]]"}]}}
        assert studio.post(f"{BASE}/julia/evals/cases", json=token).status_code == 422
        sem_juiz = {k: v for k, v in self.CASE.items() if k not in ("suite", "roteiro", "asserts")}
        assert studio.post(f"{BASE}/julia/evals/cases", json={**sem_juiz, "slug": "c1"}).status_code == 422

    def test_the_token_lists_and_writes_conformance_rules_of_the_definition_only(self, studio):
        agent = _julia(studio)
        _content_token(studio)
        try:
            lista = studio.raw.get(f"{UI}/agents/julia/conformidade/regras")
            assert lista.status_code == 200
            assert "vazamento_prompt" in [i["regra"] for i in lista.json()["items"]]
            put = studio.raw.put(f"{UI}/agents/julia/conformidade/regras/termina_sem_pergunta", json={"ativo": False})
            assert put.status_code == 200 and put.json()["ativo"] is False
            outra = studio.raw.put(f"{UI}/agents/julia/conformidade/regras/termina_sem_pergunta?org_id={uuid4()}",
                                   json={"ativo": True})
            assert outra.status_code == 403 and outra.json()["code"] == "org_id_nao_permitido"
        finally:
            studio.raw.app.dependency_overrides.pop(get_auth_context, None)
        [row] = [a for a in studio.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "conteudo_editado_mcp"]
        assert row.actor == UUID(int=9) and row.depois["regra"] == "termina_sem_pergunta"

    @pytest.mark.parametrize("issuer,scopes,code", [
        ("social-wiring", ("studio:content-write",), "issuer_not_allowed"),
        ("noctus-platform", ("studio:publish",), "scope_missing"),
    ])
    def test_any_other_product_token_is_403(self, studio, issuer, scopes, code):
        _julia(studio)
        _content_token(studio, issuer=issuer, scopes=scopes)
        try:
            for r in (studio.raw.get(f"{BASE}/julia/evals/cases"), studio.raw.get(f"{UI}/agents/julia/conformidade/regras"),
                      studio.raw.post(f"{BASE}/julia/evals/cases", json=self.CASE)):
                assert r.status_code == 403 and r.json()["code"] == code
        finally:
            studio.raw.app.dependency_overrides.pop(get_auth_context, None)

    def test_the_rule_list_is_strict_401_and_403_for_an_org_admin(self, studio):
        _julia(studio)
        assert studio.raw.get(f"{UI}/agents/julia/conformidade/regras").status_code == 401
        _as(studio, org_role="owner", platform=False)
        r = studio.get(f"{UI}/agents/julia/conformidade/regras")
        assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"
