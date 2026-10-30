"""``/api/studio`` Julia v2 content API (CONTRACT §2.4, §2.6): system texts, tool descriptions,
decisions, org-spec declarations, the per-org values, the compiled view per org, platform pieces.

One platform definition (``julia``, in the platform org) + an instance per org. Auth assertions are
strict (``== 403`` / ``== 404`` / ``== 409``).
"""
from __future__ import annotations

from tests.julia_body import JULIA_BODY

from uuid import NAMESPACE_OID, UUID, uuid5

import pytest

from app.dependencies import get_auth_context
from app.studio.textos_registry import TEXTOS as _TEXTOS_REGISTRO
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

# same ids as the suite conftest (its package is named `def`: not importable)
OTHER_ORG_ID = uuid5(NAMESPACE_OID, "studio-other-org")
OTHER_USER_ID = uuid5(NAMESPACE_OID, "studio-other-user")

BASE = "/api/studio/agents"
PLAT = "/api/studio/plataforma"

#: The compiler-owned strings a Julia-shaped version (no skills, no knowledge, no web) needs. Content
#: for the TEST only — app/ carries no prompt text.
TEXTOS = [
    {"chave": "compilador.titulo_ferramentas", "conteudo": "Ferramentas"},
    {"chave": "compilador.ferramenta_linha.web_desativada", "conteudo": "- Web: desligada."},
    {"chave": "compilador.ferramenta_linha.conhecimento_desativada", "conteudo": "- Conhecimento: desligado."},
    # the channel runtime's texts (A-RT): a channel agent publishes only with every required one filled
    *({"chave": c, "conteudo": "texto de teste"} for c, sp in _TEXTOS_REGISTRO.items()
      if sp.aplica_a == "canal" and sp.obrigatoria and not c.startswith("compilador.")),
]
#: The compiler headings of the qualification block (required once the studio compile covers the standard).
TEXTOS_REGISTRO_CHAVES_QUALIFICACAO = sorted(
    c for c, sp in _TEXTOS_REGISTRO.items() if c.startswith("compilador.") and "qualificacao" in c
)
FERRAMENTAS = [
    {"ferramenta": "handoff", "descricao": "Passa a conversa para uma pessoa da equipe.", "parametros": {"motivo": "Por quê."}},
]
SECOES = {"secoes": [
    {"chave": "persona", "titulo": "Quem você é", "ordem": 10,
     "conteudo": "Você atende leads da {{org.agencia}}.", "ativo": True},
]}
SPECS = [
    {"chave": "agencia", "rotulo": "Nome da imobiliária", "tipo": "texto", "obrigatoria": True},
    {"chave": "regioes", "rotulo": "Regiões atendidas", "tipo": "texto_longo", "obrigatoria": False},
]


def _platform_admin(studio, org_id=DEFAULT_ORG_ID, user_id=DEFAULT_USER_ID):
    studio.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(user_id), "org_id": str(org_id), "role": "admin", "org_role": "owner"}],
    )


@pytest.fixture
def plat(studio):
    """The platform org is the default org; ``julia``'s definition exists with its (empty) draft."""
    studio.store.mark_platform_org(DEFAULT_ORG_ID)
    _platform_admin(studio)
    resp = studio.post(f"{PLAT}/agents", json=JULIA_BODY)
    assert resp.status_code == 201, resp.text
    # 050: julia is product-owned (closed) -- the other org holds an instance only because it was granted
    studio.store.grant_definition_org(studio.store.get_platform_definition("julia").id, OTHER_ORG_ID)
    studio.as_role("owner")
    return studio


def _fill(studio, *, secoes=True, textos=True, ferramentas=True, specs=True):
    if secoes:
        assert studio.put(f"{BASE}/julia/draft/sections", json=SECOES).status_code == 200
    if textos:
        assert studio.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS}).status_code == 200
    if ferramentas:
        assert studio.put(f"{BASE}/julia/draft/ferramentas", json={"itens": FERRAMENTAS}).status_code == 200
    if specs:
        assert studio.put(f"{BASE}/julia/draft/specs", json={"itens": SPECS}).status_code == 200


def _draft_id(studio) -> UUID:
    return studio.store.get_draft(DEFAULT_ORG_ID, studio.store.get_agent(DEFAULT_ORG_ID, "julia").id).id


def _publish(studio):
    resp = studio.post(f"{BASE}/julia/draft/publish", json={"override_reason": "primeira publicação dos testes do conteúdo"})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestPlatformDefinition:
    def test_platform_admin_creates_it_once_in_the_platform_org(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        _platform_admin(studio)
        first = studio.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert first.status_code == 201
        assert first.json()["definition_scope"] == "plataforma" and first.json()["conteudo_modo"] == "linhas"
        dup = studio.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert dup.status_code == 409 and dup.json()["code"] == "agente_ja_existe"
        again = studio.post(f"{PLAT}/agents", json={**JULIA_BODY, "reutilizar": True})
        assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
        draft = studio.store.get_draft(DEFAULT_ORG_ID, UUID(first.json()["id"]))
        assert draft.versao == 1 and studio.store.list_sections(DEFAULT_ORG_ID, draft.id) == []

    def test_an_org_owner_is_not_a_platform_admin(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        studio.as_org_admin_only()
        resp = studio.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"
        assert studio.get(f"{PLAT}/textos").status_code == 403

    def test_any_valid_key_is_a_platform_definition_and_a_new_key_needs_a_name(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        _platform_admin(studio)
        sem_nome = studio.post(f"{PLAT}/agents", json={"key": "qualquer"})
        assert sem_nome.status_code == 422 and sem_nome.json()["code"] == "nome_obrigatorio"
        ok = studio.post(f"{PLAT}/agents", json={"key": "qualquer", "nome": "Qualquer"})
        assert ok.status_code == 201 and ok.json()["geracao"] is None
        assert studio.post(f"{PLAT}/agents", json={"key": "Chave Ruim", "nome": "x"}).status_code == 422

    def test_the_definition_carries_its_data_and_it_is_readable_and_writable(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        _platform_admin(studio)
        body = {
            "key": "sdr-teste", "nome": "SDR", "runtime": "llm", "owner_product": "social-wiring",
            "escopo_qualificacao": "sdr", "padrao_qualificacao": "imob-lead", "instanciavel": False,
            "rascunho_padrao": {"provider": "openai", "model": "gpt-5.6-terra", "max_turns": 8},
        }
        made = studio.post(f"{PLAT}/agents", json=body).json()
        assert (made["runtime"], made["owner_product"], made["usa_canais"]) == ("llm", "social-wiring", True)
        assert (made["escopo_qualificacao"], made["padrao_qualificacao"], made["instanciavel"]) == ("sdr", "imob-lead", False)
        draft = studio.store.get_draft(DEFAULT_ORG_ID, UUID(made["id"]))
        assert (draft.provider, draft.model, draft.max_turns) == ("openai", "gpt-5.6-terra", 8)
        got = studio.get(f"{PLAT}/agents/sdr-teste").json()
        assert got["padrao_qualificacao"] == "imob-lead"
        upd = studio.patch(f"{PLAT}/agents/sdr-teste", json={"padrao_qualificacao": None, "owner_product": None})
        assert upd.status_code == 200
        assert (upd.json()["padrao_qualificacao"], upd.json()["owner_product"], upd.json()["usa_canais"]) == (None, None, False)
        assert studio.patch(f"{PLAT}/agents/sdr-teste", json={"runtime": None}).json()["code"] == "invalid_field"
        assert studio.patch(f"{PLAT}/agents/nao-existe", json={"instanciavel": True}).status_code == 404

    def test_a_product_owned_definition_cannot_be_opened_and_is_granted_per_org(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        _platform_admin(studio)
        refused = studio.post(f"{PLAT}/agents", json={**JULIA_BODY, "key": "aberta", "instanciavel": True})
        assert refused.status_code == 422 and refused.json()["code"] == "invalid_field"
        assert studio.post(f"{PLAT}/agents", json={**JULIA_BODY, "key": "fechada"}).status_code == 201
        org = "11111111-2222-4333-8444-555555555555"
        first = studio.post(f"{PLAT}/agents/fechada/grants", json={"org_id": org})
        assert first.status_code == 201 and first.json()["created"] is True and first.json()["org_ids"] == [org]
        again = studio.post(f"{PLAT}/agents/fechada/grants", json={"org_id": org})
        assert again.json()["created"] is False and again.json()["org_ids"] == [org]
        assert studio.get(f"{PLAT}/agents/fechada/grants").json()["org_ids"] == [org]
        assert studio.post(f"{PLAT}/agents/nao-existe/grants", json={"org_id": org}).status_code == 404

    def test_there_is_at_most_one_generator(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        _platform_admin(studio)
        assert studio.post(f"{PLAT}/agents", json={"key": "gerador-a", "nome": "A", "papel": "gerador"}).status_code == 201
        dup = studio.post(f"{PLAT}/agents", json={"key": "gerador-b", "nome": "B", "papel": "gerador"})
        assert dup.status_code == 409 and dup.json()["code"] == "gerador_ja_existe"

    def test_a_non_platform_org_cannot_hold_the_definition(self, studio):
        _platform_admin(studio)  # not flagged as the platform org
        resp = studio.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert resp.status_code == 409 and resp.json()["code"] == "definition_not_platform"

    def test_platform_texts_round_trip(self, studio):
        _platform_admin(studio)
        put = studio.put(f"{PLAT}/textos", json={"itens": {"eval.juiz_sistema": "texto do juiz"}})
        assert put.status_code == 200
        got = studio.get(f"{PLAT}/textos").json()["itens"]
        assert [(i["chave"], i["conteudo"]) for i in got] == [("eval.juiz_sistema", "texto do juiz")]
        bad = studio.put(f"{PLAT}/textos", json={"itens": {"Chave Ruim": "x"}})
        assert bad.status_code == 422


class TestDraftOnlyWrites:
    def test_member_cannot_write_content(self, plat):
        plat.as_role("member")
        for part in ("textos", "ferramentas", "decisoes", "specs"):
            resp = plat.put(f"{BASE}/julia/draft/{part}", json={"itens": []})
            assert resp.status_code == 403, part

    def test_textos_replace_set_and_the_hash_follows(self, plat):
        before = plat.store.get_version(DEFAULT_ORG_ID, _draft_id(plat)).compiled_hash
        resp = plat.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS})
        assert resp.status_code == 200
        assert [i["chave"] for i in resp.json()["itens"]] == sorted(t["chave"] for t in TEXTOS)
        after = plat.store.get_version(DEFAULT_ORG_ID, _draft_id(plat)).compiled_hash
        assert after is not None and after != before  # re-stamped over the new content
        # replace-set: the body IS the whole set
        again = plat.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS[:1]})
        assert [i["chave"] for i in again.json()["itens"]] == [TEXTOS[0]["chave"]]

    def test_textos_chave_must_be_in_the_registry(self, plat):
        resp = plat.put(f"{BASE}/julia/draft/textos", json={"itens": [{"chave": "inventada.chave", "conteudo": "x"}]})
        assert resp.status_code == 422 and resp.json()["code"] == "invalid_field"

    def test_duplicate_chaves_are_a_409(self, plat):
        resp = plat.put(f"{BASE}/julia/draft/textos", json={"itens": [TEXTOS[0], TEXTOS[0]]})
        assert resp.status_code == 409 and resp.json()["code"] == "chave_conflict"

    def test_ferramentas_must_exist_in_the_code_registry(self, plat):
        bad = plat.put(f"{BASE}/julia/draft/ferramentas", json={"itens": [
            {"ferramenta": "nao_existe", "descricao": "x"},
        ]})
        assert bad.status_code == 422
        ok = plat.put(f"{BASE}/julia/draft/ferramentas", json={"itens": FERRAMENTAS})
        assert ok.status_code == 200 and ok.json()["itens"][0]["parametros"] == {"motivo": "Por quê."}

    def test_decisoes_need_exactly_one_default_option(self, plat):
        body = {"itens": [{"chave": "abordagem-meta", "titulo": "Abordagem", "regra": "r", "opcoes": [
            {"valor": "a", "rotulo": "A", "padrao": True}, {"valor": "b", "rotulo": "B", "padrao": True},
        ]}]}
        assert plat.put(f"{BASE}/julia/draft/decisoes", json=body).status_code == 422
        body["itens"][0]["opcoes"][1]["padrao"] = False
        ok = plat.put(f"{BASE}/julia/draft/decisoes", json=body)
        assert ok.status_code == 200 and [o["valor"] for o in ok.json()["itens"][0]["opcoes"]] == ["a", "b"]

    def test_a_published_version_is_immutable_and_has_no_draft_to_write(self, plat):
        _fill(plat)
        _publish(plat)
        resp = plat.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS})
        assert resp.status_code == 404 and resp.json()["code"] == "draft_not_found"

    def test_the_next_draft_carries_every_content_table(self, plat):
        plat.put(f"{BASE}/julia/draft/decisoes", json={"itens": [
            {"chave": "d", "titulo": "D", "regra": "r", "opcoes": [{"valor": "x", "rotulo": "X", "padrao": True}]},
        ]})
        _fill(plat)
        _publish(plat)
        draft = plat.post(f"{BASE}/julia/draft", json={}).json()
        vid = UUID(draft["id"])
        assert len(plat.store.list_textos(DEFAULT_ORG_ID, vid)) == len(TEXTOS)
        assert len(plat.store.list_ferramentas(DEFAULT_ORG_ID, vid)) == len(FERRAMENTAS)
        assert [d.chave for d in plat.store.list_decisoes(DEFAULT_ORG_ID, vid)] == ["d"]
        assert [s.chave for s in plat.store.list_spec_defs(DEFAULT_ORG_ID, vid)] == ["agencia", "regioes"]

    def test_a_legacy_agent_refuses_dead_content_rows(self, studio):
        studio.post(BASE, json={"key": "isa", "nome": "Isa"})
        resp = studio.put(f"{BASE}/isa/draft/textos", json={"itens": TEXTOS})
        assert resp.status_code == 409 and resp.json()["code"] == "conteudo_modo_legado"

    def test_reading_a_versions_tables(self, plat):
        _fill(plat)
        vid = _draft_id(plat)
        assert len(plat.get(f"{BASE}/julia/versions/{vid}/textos").json()["itens"]) == len(TEXTOS)
        assert plat.get(f"{BASE}/julia/versions/{vid}/ferramentas").json()["itens"][0]["ferramenta"] == "handoff"
        assert plat.get(f"{BASE}/julia/versions/{vid}/decisoes").json()["itens"] == []
        assert len(plat.get(f"{BASE}/julia/versions/{vid}/specs").json()["itens"]) == 2
        payload = plat.get(f"{BASE}/julia/versions/{vid}/payload").json()
        assert "{{org.agencia}}" in payload["texto"] and "`handoff`" in payload["texto"]
        origens = {m["origem"]["tipo"] for m in payload["manifest"]}
        assert {"secao", "auto", "texto", "ferramenta"} <= origens


class TestPublishCompleteness:
    def test_missing_content_is_conteudo_incompleto(self, plat):
        plat.put(f"{BASE}/julia/draft/sections", json=SECOES)  # no textos / ferramentas / specs
        resp = plat.post(f"{BASE}/julia/draft/publish", json={"override_reason": "tentativa com o conteúdo incompleto"})
        assert resp.status_code == 409 and resp.json()["code"] == "conteudo_incompleto"
        codes = {a["codigo"] for a in resp.json()["avisos"]}
        assert {"texto_ausente", "spec_nao_declarada"} <= codes

    def test_an_undeclared_placeholder_blocks(self, plat):
        _fill(plat, specs=False)
        resp = plat.post(f"{BASE}/julia/draft/publish", json={"override_reason": "placeholder sem declaração aqui"})
        assert resp.status_code == 409 and resp.json()["code"] == "conteudo_incompleto"
        assert any(a["codigo"] == "spec_nao_declarada" for a in resp.json()["avisos"])

    def test_a_decision_section_must_move_to_decisoes(self, plat):
        _fill(plat)
        plat.put(f"{BASE}/julia/draft/sections", json={"secoes": SECOES["secoes"] + [
            {"chave": "decisao-x", "titulo": "R", "ordem": 900, "conteudo": "regra", "ativo": True},
        ]})
        resp = plat.post(f"{BASE}/julia/draft/publish", json={"override_reason": "decisão ainda como seção do prompt"})
        assert resp.status_code == 409
        assert any(a["codigo"] == "decisao_em_secao" for a in resp.json()["avisos"])

    def test_a_tool_requiring_a_skill_that_is_not_there_blocks(self, plat):
        _fill(plat)
        plat.put(f"{BASE}/julia/draft/ferramentas", json={"itens": [
            {"ferramenta": "handoff", "descricao": "d", "obrigatoria_skill": "ausente"},
        ]})
        resp = plat.post(f"{BASE}/julia/draft/publish", json={"override_reason": "ferramenta exige skill ausente"})
        assert resp.status_code == 409
        assert any(a["codigo"] == "skill_exigida_inexistente" for a in resp.json()["avisos"])

    def test_complete_content_publishes(self, plat):
        _fill(plat)
        assert _publish(plat)["status"] == "ativa"


class TestOrgInstanceAndSpecs:
    def _published(self, plat):
        _fill(plat)
        _publish(plat)

    def _as_org(self, studio, role="owner", platform=False):
        """Another org's caller: by default an org admin that is NOT a platform admin."""
        studio.as_other_org(role=role, platform=platform)
        return studio

    def test_an_org_gets_an_instance_and_cannot_touch_the_definition(self, plat):
        self._published(plat)
        self._as_org(plat)
        listed = plat.get(BASE).json()["items"]
        assert [(a["key"], a["definition_scope"], a["versao_ativa"], a["tem_rascunho"]) for a in listed] == [
            ("julia", "instancia", 1, False),
        ]
        assert plat.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS}).status_code == 403  # not a platform admin
        for method, path, body in (
            ("post", f"{BASE}/julia/draft", {}),
            ("put", f"{BASE}/julia/draft/sections", SECOES),
            ("post", f"{BASE}/julia/draft/publish", {}),
        ):
            resp = getattr(plat, method)(path, json=body)
            assert resp.status_code == 409 and resp.json()["code"] == "definicao_na_plataforma", path
        detail = plat.get(f"{BASE}/julia").json()
        assert detail["versoes"] == [] and detail["versao_ativa"] == 1  # no version of the platform's definition

    def test_org_values_are_set_by_the_org_admin_for_declared_keys_only(self, plat):
        self._published(plat)
        self._as_org(plat)
        plat.get(BASE)  # first use -> instance
        assert plat.get(f"{BASE}/julia/specs").json()["faltando"] == ["agencia"]
        resp = plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "Imobiliária Aurora"}})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["faltando"] == [] and [(v["chave"], v["valor"]) for v in body["valores"]] == [
            ("agencia", "Imobiliária Aurora"),
        ]
        undeclared = plat.put(f"{BASE}/julia/specs", json={"valores": {"outra": "x"}})
        assert undeclared.status_code == 422 and undeclared.json()["code"] == "spec_nao_declarada"
        # texto is capped at 1 000 characters, texto_longo at 20 000
        assert plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "x" * 1001}}).status_code == 422
        assert plat.put(f"{BASE}/julia/specs", json={"valores": {"regioes": "x" * 5000}}).status_code == 200

    def test_a_member_sees_and_sets_nothing_of_the_specs(self, plat):
        self._published(plat)
        self._as_org(plat, role="member")
        plat.get(BASE)
        assert plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "X"}}).status_code == 403
        assert plat.get(f"{BASE}/julia/specs").status_code == 403
        assert plat.get(f"{BASE}/julia/status").status_code == 403

    def test_the_compiled_view_per_org_shows_the_values_in_place(self, plat):
        self._published(plat)
        self._as_org(plat)
        plat.get(BASE)
        self._as_org(plat, platform=True)  # a platform admin acting in the org (org picker)
        before = plat.get(f"{BASE}/julia/compilado").json()
        assert before["completo"] is False and before["specs_faltando"] == ["agencia"]
        assert any(a["codigo"] == "spec_org_faltando" and a["bloqueante"] for a in before["avisos"])
        plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "Imobiliária Aurora"}})
        after = plat.get(f"{BASE}/julia/compilado").json()
        assert after["completo"] is True and after["specs_faltando"] == []
        assert "Você atende leads da Imobiliária Aurora." in after["texto"]
        assert "{{org." not in after["texto"] and after["hash"] != before["hash"]

    def test_two_orgs_get_different_hashes_from_one_definition(self, plat):
        self._published(plat)
        self._as_org(plat, platform=True)
        plat.get(BASE)
        plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "Aurora"}})
        a = plat.get(f"{BASE}/julia/compilado").json()
        # a second org
        third = UUID(int=777001)
        plat.store.grant_definition_org(plat.store.get_platform_definition("julia").id, third)
        from tests.routers.conftest import bind_user, seed_org_role

        bind_user(plat, user_id=UUID(int=777002), org_id=third)
        seed_org_role(plat, user_id=UUID(int=777002), org_id=third, role="owner")  # also platform admin here
        plat.get(BASE)
        plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "Bússola"}})
        b = plat.get(f"{BASE}/julia/compilado").json()
        assert a["version_id"] == b["version_id"] and a["hash"] != b["hash"]
        assert "Aurora" in a["texto"] and "Bússola" in b["texto"] and "Aurora" not in b["texto"]

    def test_org_spec_edits_are_audited_with_keys_not_values(self, plat):
        self._published(plat)
        self._as_org(plat)
        plat.get(BASE)
        plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "Segredo Comercial"}})
        agent = plat.store.get_agent(OTHER_ORG_ID, "julia")
        rows = [a for a in plat.store.list_audit_log(OTHER_ORG_ID, agent.id) if a.acao == "specs_org_editadas"]
        assert len(rows) == 1 and rows[0].depois == {"chaves": ["agencia"]} and rows[0].actor == OTHER_USER_ID
        assert "Segredo" not in str(rows[0].antes) + str(rows[0].depois)

    def test_the_draft_preview_belongs_to_the_definitions_org(self, plat):
        self._published(plat)
        plat.post(f"{BASE}/julia/draft", json={})
        plat.put(f"{BASE}/julia/draft/sections", json={"secoes": [
            {"chave": "persona", "titulo": "P", "ordem": 1, "conteudo": "Rascunho da {{org.agencia}}.", "ativo": True},
        ]})
        # the platform org previews its own draft with ITS values ...
        plat.put(f"{BASE}/julia/specs", json={"valores": {"agencia": "Aurora"}})
        view = plat.get(f"{BASE}/julia/compilado?versao=rascunho").json()
        assert "Rascunho da Aurora." in view["texto"] and view["versao"] == 2
        # ... another org never reads the platform's unpublished draft
        self._as_org(plat, platform=True)
        plat.get(BASE)
        resp = plat.get(f"{BASE}/julia/compilado?versao=rascunho")
        assert resp.status_code == 409 and resp.json()["code"] == "rascunho_da_plataforma"


class TestMcpTokenPath:
    def test_a_product_token_with_the_scope_writes_and_is_audited(self, plat):
        from app.main import app  # noqa: F401 — import side effects only

        raw_app = plat.raw.app
        raw_app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["studio:content-write"],
            raw_token="tok", api_token_id=UUID(int=9), issuer="noctus-platform",
        )
        resp = plat.raw.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS[:1]})
        assert resp.status_code == 200, resp.text
        agent = plat.store.get_agent(DEFAULT_ORG_ID, "julia")
        rows = [a for a in plat.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "conteudo_editado_mcp"]
        assert len(rows) == 1 and rows[0].actor == UUID(int=9)
        assert rows[0].depois["kind"] == "texto" and rows[0].depois["chaves"] == [TEXTOS[0]["chave"]]

    def test_a_token_without_the_scope_is_403(self, plat):
        plat.raw.app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["studio:publish"],
            raw_token="tok", api_token_id=UUID(int=9),
        )
        resp = plat.raw.put(f"{BASE}/julia/draft/textos", json={"itens": []})
        assert resp.status_code == 403 and resp.json()["code"] == "scope_missing"

    def test_a_human_edit_is_not_an_mcp_audit_row(self, plat):
        plat.put(f"{BASE}/julia/draft/textos", json={"itens": TEXTOS[:1]})
        agent = plat.store.get_agent(DEFAULT_ORG_ID, "julia")
        assert not [a for a in plat.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "conteudo_editado_mcp"]


class TestVisibilityTiers:
    """Owner mandate 2026-10-19 (IP protection): the definition is readable by PLATFORM ADMINS only —
    strict 403 for an org admin and a member, 401 unauthenticated; org admins see only their own specs
    form + a readiness status; every definition read leaves an audit row; no body echoes content."""

    def _published(self, plat):
        _fill(plat)
        _publish(plat)
        return _draft_id_active(plat)

    def _definition_reads(self, vid):
        return [
            f"{BASE}/julia/versions/{vid}",
            f"{BASE}/julia/versions/{vid}/textos",
            f"{BASE}/julia/versions/{vid}/ferramentas",
            f"{BASE}/julia/versions/{vid}/decisoes",
            f"{BASE}/julia/versions/{vid}/specs",
            f"{BASE}/julia/versions/{vid}/payload",
            f"{BASE}/julia/versions/{vid}/compiled",
            f"{BASE}/julia/versions/{vid}/diff/{vid}",
            f"{BASE}/julia/compilado",
            "/api/studio/prompts/sha256:" + "0" * 64,
        ]

    def test_unauthenticated_is_401(self, plat):
        vid = self._published(plat)
        for url in self._definition_reads(vid):
            assert plat.raw.get(url).status_code == 401, url

    @pytest.mark.parametrize("who", ["org_admin", "member"])
    def test_org_admins_and_members_are_403_on_every_definition_read(self, plat, who):
        vid = self._published(plat)
        if who == "org_admin":
            plat.as_org_admin_only()
        else:
            plat.as_role("member")
        for url in self._definition_reads(vid):
            resp = plat.get(url)
            assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required", url
            assert "Você atende" not in resp.text  # a refusal never echoes content

    def test_org_admin_gets_the_form_and_a_status_but_no_prompt_or_hash(self, plat):
        self._published(plat)
        plat.as_other_org(role="owner")
        plat.get(BASE)
        specs = plat.get(f"{BASE}/julia/specs").json()
        assert {d["chave"] for d in specs["declaradas"]} == {"agencia", "regioes"}
        assert "texto" not in specs and "hash" not in str(specs).lower()
        status_ = plat.get(f"{BASE}/julia/status").json()
        assert status_ == {"agent_key": "julia", "completo": False, "sem_versao": False, "specs_faltando": ["agencia"]}
        summary = plat.get(f"{BASE}/julia").json()
        assert not any(k in str(summary) for k in ("compiled_hash", "secoes", "texto"))

    def test_every_definition_read_is_audited_without_content(self, plat):
        vid = self._published(plat)
        agent = plat.store.get_agent(DEFAULT_ORG_ID, "julia")
        before = len([a for a in plat.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "definicao_lida"])
        for url in self._definition_reads(vid)[:-1]:
            assert plat.get(url).status_code == 200, url
        rows = [a for a in plat.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "definicao_lida"]
        assert len(rows) - before == len(self._definition_reads(vid)) - 1
        assert all(r.actor == DEFAULT_USER_ID and "Você atende" not in str(r.depois) for r in rows)
        assert {r.depois["o_que"] for r in rows} >= {"textos", "payload", "compilado", "versao", "diff"}

    def test_the_content_write_routes_refuse_an_org_admin(self, plat):
        plat.as_org_admin_only()
        for part in ("textos", "ferramentas", "decisoes", "specs"):
            resp = plat.put(f"{BASE}/julia/draft/{part}", json={"itens": []})
            assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required", part


def _draft_id_active(studio) -> UUID:
    agent = studio.store.get_agent(DEFAULT_ORG_ID, "julia")
    return studio.store.get_active_version(DEFAULT_ORG_ID, agent.id).id


class TestContentTokenMint:
    """The content-write scope is a PLATFORM-ADMIN mint: server-stamped issuer, never in the org-admin set."""

    def test_the_scope_is_not_in_the_org_admin_mintable_set(self):
        from app.dependencies import MINTABLE_TOKEN_SCOPES

        assert "studio:content-write" not in MINTABLE_TOKEN_SCOPES

    def test_a_token_with_the_scope_but_not_the_platform_issuer_is_403(self, plat):
        for issuer in (None, "social-wiring"):
            plat.raw.app.dependency_overrides[get_auth_context] = lambda issuer=issuer: AuthContext(
                org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["studio:content-write"],
                raw_token="tok", api_token_id=UUID(int=9), issuer=issuer,
            )
            resp = plat.raw.put(f"{BASE}/julia/draft/textos", json={"itens": []})
            assert resp.status_code == 403 and resp.json()["code"] == "issuer_not_allowed"

    def test_only_a_platform_admin_mints_it(self, plat):
        from app.dependencies import get_product_token_admin_dep, get_token_audit_dep
        from app.channels.token_audit import FakeTokenAudit
        from noctusai_lib.api.auth.session import FakeProductTokenAdmin

        admin, audit = FakeProductTokenAdmin(), FakeTokenAudit()
        app = plat.raw.app
        app.dependency_overrides[get_product_token_admin_dep] = lambda: admin
        app.dependency_overrides[get_token_audit_dep] = lambda: audit
        plat.as_org_admin_only()
        denied = plat.post(f"{PLAT}/content-token", json={"label": "mcp"})
        assert denied.status_code == 403 and denied.json()["code"] == "platform_admin_required"
        plat.as_role("owner")
        ok = plat.post(f"{PLAT}/content-token", json={"label": "mcp"})
        assert ok.status_code == 201 and ok.headers["Cache-Control"] == "no-store"
        assert ok.json()["token"].startswith("pk_") and ok.json()["scopes"] == ["studio:content-write"]
        row = admin.rows["agents"][0]
        assert row["issuer"] == "noctus-platform" and row["scopes"] == ["studio:content-write"]
        assert row["org_id"] == str(DEFAULT_ORG_ID) and len(audit.rows) == 1


class _RowsClient:
    """supabase-py query-builder stand-in over ``FakeProductTokenAdmin.rows`` (external substrate double),
    so the REAL ``SupabaseApiTokenResolver`` can judge a minted/revoked token end to end."""

    def __init__(self, rows):
        self._rows = rows

    def schema(self, _name):
        return self

    def table(self, _name):
        self._f, self._upd = {}, None
        return self

    def select(self, _c):
        return self

    def update(self, payload):
        self._upd = payload
        return self

    def eq(self, col, val):
        self._f[col] = val
        return self

    def limit(self, _n):
        return self

    def execute(self):
        from types import SimpleNamespace

        match = [r for r in self._rows if all(r.get(c) == v for c, v in self._f.items())]
        for r in match:
            if self._upd:
                r.update(self._upd)
        return SimpleNamespace(data=match)


class TestContentTokenUi:
    """The platform-admin UI routes: mint with an expiry choice, list (never the secret), revoke."""

    @pytest.fixture
    def wired(self, plat):
        from app.channels.token_audit import FakeTokenAudit
        from app.dependencies import get_product_token_admin_dep, get_token_audit_dep
        from noctusai_lib.api.auth.session import FakeProductTokenAdmin

        admin, audit = FakeProductTokenAdmin(), FakeTokenAudit()
        plat.raw.app.dependency_overrides[get_product_token_admin_dep] = lambda: admin
        plat.raw.app.dependency_overrides[get_token_audit_dep] = lambda: audit
        plat.as_role("owner")
        return plat, admin, audit

    def test_unauthenticated_is_strict_401(self, plat):
        assert plat.raw.get(f"{PLAT}/content-tokens").status_code == 401
        assert plat.raw.post(f"{PLAT}/content-token", json={"label": "x"}).status_code == 401
        assert plat.raw.delete(f"{PLAT}/content-token/{UUID(int=1)}").status_code == 401

    def test_org_admin_who_is_not_platform_admin_is_403(self, wired):
        plat, _, _ = wired
        plat.as_org_admin_only()
        for resp in (
            plat.get(f"{PLAT}/content-tokens"),
            plat.post(f"{PLAT}/content-token", json={"label": "x", "expira_em_dias": None}),
            plat.delete(f"{PLAT}/content-token/{UUID(int=1)}"),
        ):
            assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"

    def test_default_is_30_days_and_days_are_honoured(self, wired):
        from datetime import datetime, timedelta, timezone

        plat, admin, _ = wired
        default = plat.post(f"{PLAT}/content-token", json={"label": "a"}).json()
        week = plat.post(f"{PLAT}/content-token", json={"label": "b", "expira_em_dias": 7}).json()
        now = datetime.now(timezone.utc)
        assert abs(datetime.fromisoformat(default["expires_at"]) - (now + timedelta(days=30))) < timedelta(minutes=5)
        assert abs(datetime.fromisoformat(week["expires_at"]) - (now + timedelta(days=7))) < timedelta(minutes=5)

    def test_never_expires_is_a_null_expiry_not_a_far_date(self, wired):
        plat, admin, audit = wired
        out = plat.post(f"{PLAT}/content-token", json={"label": "perm", "expira_em_dias": None})
        assert out.status_code == 201 and out.json()["expires_at"] is None
        assert admin.rows["agents"][0]["expires_at"] is None and len(audit.rows) == 1

    @pytest.mark.parametrize("dias", [0, -1, 366, 10_000, "x"])
    def test_out_of_range_days_are_422(self, wired, dias):
        plat, admin, _ = wired
        resp = plat.post(f"{PLAT}/content-token", json={"label": "a", "expira_em_dias": dias})
        assert resp.status_code == 422 and not admin.rows

    def test_list_never_returns_the_secret_and_only_content_tokens(self, wired):
        from datetime import datetime, timedelta, timezone

        plat, admin, _ = wired
        minted = plat.post(f"{PLAT}/content-token", json={"label": "mcp", "expira_em_dias": None}).json()
        # a same-org token of another scope/issuer must not appear
        admin.mint("agents", org_id=DEFAULT_ORG_ID, label="canal", scopes=["agents:ask"],
                   expires_at=datetime.now(timezone.utc) + timedelta(days=1), issuer="noctus-platform")
        resp = plat.get(f"{PLAT}/content-tokens")
        assert resp.status_code == 200 and resp.headers["Cache-Control"] == "no-store"
        assert minted["token"] not in resp.text and "token_hash" not in resp.text
        itens = resp.json()["itens"]
        assert len(itens) == 1
        item = itens[0]
        assert item["id"] == minted["id"] and item["prefix"] == minted["prefix"]
        assert item["status"] == "ativo" and item["expires_at"] is None and item["created_by"] == str(DEFAULT_USER_ID)

    def test_revoke_is_idempotent_audited_and_the_token_is_then_refused(self, wired):
        from noctusai_lib.api.auth.session import SupabaseApiTokenResolver

        plat, admin, audit = wired
        minted = plat.post(f"{PLAT}/content-token", json={"label": "mcp"}).json()
        resolver = SupabaseApiTokenResolver(_RowsClient(admin.rows["agents"]), schema="agents")

        # the freshly minted token is accepted by the REAL resolver ...
        import asyncio
        assert asyncio.run(resolver.resolve(minted["token"])) is not None

        first = plat.delete(f"{PLAT}/content-token/{minted['id']}")
        assert first.status_code == 200 and first.json()["status"] == "revogado"
        again = plat.delete(f"{PLAT}/content-token/{minted['id']}")
        assert again.status_code == 200 and again.json()["status"] == "revogado"
        assert [r.method for r in audit.rows] == ["MINT", "REVOKE"]  # no second REVOKE row
        # ... and refused once revoked (the resolver answers None -> 401 before require_content_write)
        assert asyncio.run(resolver.resolve(minted["token"])) is None
        listed = plat.get(f"{PLAT}/content-tokens").json()["itens"][0]
        assert listed["status"] == "revogado" and listed["revoked_at"]

    def test_revoke_unknown_or_foreign_token_is_404(self, wired):
        from datetime import datetime, timedelta, timezone

        plat, admin, _ = wired
        foreign = admin.mint("agents", org_id=OTHER_ORG_ID, label="x", scopes=["studio:content-write"],
                             expires_at=datetime.now(timezone.utc) + timedelta(days=1), issuer="noctus-platform")
        for tid in (UUID(int=7), foreign.info.id):
            resp = plat.delete(f"{PLAT}/content-token/{tid}")
            assert resp.status_code == 404 and resp.json()["code"] == "token_not_found"
        assert admin.list_tokens("agents", org_id=OTHER_ORG_ID)[0].revoked_at is None

    def test_expired_token_lists_as_expirado(self, wired):
        from datetime import datetime, timedelta, timezone

        plat, admin, _ = wired
        admin.mint("agents", org_id=DEFAULT_ORG_ID, label="old", scopes=["studio:content-write"],
                   expires_at=datetime.now(timezone.utc) - timedelta(days=1), issuer="noctus-platform")
        assert plat.get(f"{PLAT}/content-tokens").json()["itens"][0]["status"] == "expirado"
