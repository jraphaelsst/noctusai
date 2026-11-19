"""S9 -- the chat answered by the Diretor de Criação, the multi-select pick and the Publicação on the card
(``criacao-pipeline-contract.md`` 2.3 / 4 / 10).

Mounted through the real ``register()`` seam on the MockSupabaseClient. The Diretor is the Fake behind its DI seam
(``get_diretor_factory``); the parser (``propostas`` + ``publicacoes``), the service writes and the saga are production
code. The SQL (table 367, CHECKs, RPCs) runs on PGlite in the migration replay; the saga's RPC model is the one of
``test_fluxo_saga.py``. Auth tests assert STRICT ``== 401``.
"""
from __future__ import annotations

import ast
import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.agents_channel import (
    AgentsTimeout,
    FakeAgentsClient,
    TurnResult,
)
from noctusai_lib.testing import TEST_ORG_ID, TEST_USER_ID

from app.modules.media_creation.routers import chat as chat_router
from app.modules.media_creation.services.diretor_criacao import (
    AGENT_KEY,
    AgentsDiretorCriacao,
    DiretorIndisponivel,
    FakeDiretorCriacao,
    TurnoDiretor,
    diretor_ativo,
    get_diretor_factory,
    make_diretor_criacao,
)
from app.modules.media_creation.services.publicacao_service import PublicacaoService

from .test_chat_unificado import (  # noqa: F401 - `ch` is the shared fixture
    BASE,
    E1,
    E2,
    MARCA,
    _agora,
    _conversa,
    ch,
)
from .test_fluxo_saga import E1 as E1_SAGA
from .test_fluxo_saga import LEGENDA_JSON, Llm, _completar_roteiro
from .test_fluxo_saga import MARCA as MARCA_SAGA
from .test_fluxo_saga import _conversa as _conversa_saga
from .test_fluxo_saga import _proposta as _proposta_saga
from .test_fluxo_saga import sg  # noqa: F401 - the saga fixture

REPLY = (
    "### Opções\n"
    "1. Você dorme mal e acha normal (estrutura #101)\n"
    "2. O hábito que rouba o seu sono (estrutura #102)\n\n"
    "### Publicação 1\n"
    "- Objetivo do post: salvamentos\n- CTA: Salve este vídeo\n- Justificativa do CTA: salvar sustenta o objetivo do post de consulta\n"
    "- Legenda: Legenda da opção 1.\n- Hashtags: #sono #rotina #saude #bemestar #habitos\n"
    "- Primeiro comentário: Qual hábito você mudaria?\n- Link:\n- Fontes: nenhuma\n- Voz: sem amostras\n\n"
    "### Publicação 2\n"
    "- Objetivo do post: conversa\n- CTA: nenhum\n- Justificativa do CTA: a marca não pede CTA\n"
    "- Legenda: Legenda da opção 2.\n- Hashtags: #sono #rotina #saude #bemestar #corpo\n"
    "- Primeiro comentário: E você?\n- Link:\n- Fontes: nenhuma\n- Voz: sem amostras\n"
)


def _frames(texto: str) -> list[dict]:
    return [json.loads(b[len("data: "):]) for b in texto.split("\n\n") if b.startswith("data: ")]


def _ligar_diretor(st, *script):
    st.diretor = FakeDiretorCriacao(*script)
    st.client._tc.app.dependency_overrides[get_diretor_factory] = lambda: (lambda org_id: st.diretor)
    st.cfg.chat_diretor_criacao = True
    st.client._tc.app.dependency_overrides[chat_router.get_chat_settings] = lambda: st.cfg
    return st.diretor


def _gravar_rpc(st, cid, mid, ids):
    def gravar():
        st.db.from_("cs_chat_mensagens").insert({
            "id": mid, "org_id": TEST_ORG_ID, "conversa_id": cid, "role": "assistant", "conteudo": REPLY,
            "referencias": [], "status": "completa", "truncada": False, "created_at": _agora(), "tipo": "texto"}).execute()
        for ordem, pid in enumerate(ids, start=1):
            st.db.from_("cs_chat_propostas").insert({
                "id": pid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "conversa_id": cid, "mensagem_id": mid, "ordem": ordem,
                "texto": f"h{ordem}", "tipo": "headline", "status": "proposta", "created_at": _agora()}).execute()
            st.db.from_("cs_chat_proposta_estruturas").insert(
                {"proposta_id": pid, "estrutura_id": E1, "ordem": 1, "principal": True}).execute()
        return {"mensagem_id": mid, "propostas": [{"id": pid, "ordem": i} for i, pid in enumerate(ids, start=1)]}

    st.rpc.results["cs_chat_resposta_gravar"] = gravar


# ── the flag + the seam ──────────────────────────────────────────────────────────────────────────────────


def test_the_switch_is_off_by_default_and_the_org_tier_wins():
    cfg = SimpleNamespace(chat_diretor_criacao=False)
    assert diretor_ativo("org-a", cfg, ler=lambda k, o: None) is False
    assert diretor_ativo("org-a", SimpleNamespace(chat_diretor_criacao=True), ler=lambda k, o: None) is True
    assert diretor_ativo("org-a", cfg, ler=lambda k, o: "true" if o == "org-a" else "off") is True
    assert diretor_ativo("org-b", cfg, ler=lambda k, o: "true" if o == "org-a" else "off") is False


def test_the_factory_gives_nothing_without_a_client_and_the_real_adapter_with_one():
    assert make_diretor_criacao(None) is None
    assert isinstance(make_diretor_criacao(FakeAgentsClient()), AgentsDiretorCriacao)


def test_the_real_adapter_asks_the_diretor_on_the_app_channel_keyed_by_marca_and_conversa():
    fake = FakeAgentsClient(script=[TurnResult(conversation_id="c1", partes=("parte um", "parte dois"), status="respondido")])
    r = asyncio.run(AgentsDiretorCriacao(fake).responder(TurnoDiretor("org", "marca-1", "conv-1", "msg-1", "me dê opções")))
    assert r.texto == "parte um\nparte dois"
    req = fake.turns[0]
    assert (req.agent_key, req.channel, req.connection_id, req.chat_id) == (AGENT_KEY, "app", "marca-1", "conv-1")
    assert req.messages[0].provider_message_id == "msg-1" and req.messages[0].texto == "me dê opções"
    assert req.contexto is None  # the closed Julia schema is never abused to smuggle tenant data


@pytest.mark.parametrize("erro,codigo", [(AgentsTimeout("x"), "timeout")])
def test_an_agents_failure_is_a_coded_refusal_never_its_text(erro, codigo):
    with pytest.raises(DiretorIndisponivel) as exc:
        asyncio.run(AgentsDiretorCriacao(FakeAgentsClient(script=[erro])).responder(TurnoDiretor("o", "m", "c", "i", "t")))
    assert exc.value.codigo == codigo and "x" not in str(exc.value)


def test_a_silent_turn_is_sem_resposta():
    fake = FakeAgentsClient(script=[TurnResult(conversation_id="c", partes=(), status="silencio")])
    with pytest.raises(DiretorIndisponivel) as exc:
        asyncio.run(AgentsDiretorCriacao(fake).responder(TurnoDiretor("o", "m", "c", "i", "t")))
    assert exc.value.codigo == "sem_resposta"


# ── the chat through the Diretor ─────────────────────────────────────────────────────────────────────────


def test_with_the_switch_on_the_turn_goes_to_the_diretor_not_to_the_legacy_stream(ch):
    diretor = _ligar_diretor(ch, REPLY)
    cid = _conversa(ch)
    mid, p1, p2 = (str(uuid.uuid4()) for _ in range(3))
    _gravar_rpc(ch, cid, mid, [p1, p2])
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "me dê opções", "referencias": []})
    assert r.status_code == 200, r.text
    frames = _frames(r.text)
    assert [list(f)[0] for f in frames] == ["meta", "status", "delta", "done"]
    assert frames[0]["meta"]["via"] == "diretor" and frames[1]["status"]["codigo"] == "diretor_trabalhando"
    assert len(diretor.turnos) == 1 and diretor.turnos[0].conversa_id == cid and diretor.turnos[0].marca_id == MARCA
    assert ch.fake.calls == []  # exactly ONE live path per turn: the legacy stream was never opened
    assert frames[3]["done"]["mensagem_id"] == mid


def test_with_the_switch_on_and_no_diretor_the_refusal_is_coded_and_nothing_is_persisted(ch):
    _ligar_diretor(ch, REPLY)
    ch.client._tc.app.dependency_overrides[get_diretor_factory] = lambda: (lambda org_id: None)
    cid = _conversa(ch)
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    assert r.status_code == 503 and r.json()["code"] == "diretor_indisponivel"
    assert ch.fake.calls == [] and [m for m in ch.rows("cs_chat_mensagens") if m["role"] == "user"] == []


def test_with_the_switch_off_the_legacy_stream_answers_and_the_diretor_is_never_asked(ch):
    ch.cfg.chat_diretor_criacao = False
    ch.client._tc.app.dependency_overrides[chat_router.get_chat_settings] = lambda: ch.cfg
    diretor = FakeDiretorCriacao("nunca")
    ch.client._tc.app.dependency_overrides[get_diretor_factory] = lambda: (lambda org_id: diretor)
    cid = _conversa(ch)
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    assert r.status_code == 200 and diretor.turnos == [] and len(ch.fake.calls) == 1
    assert "via" not in _frames(r.text)[0]["meta"]  # the legacy frame is unchanged


def test_a_failing_diretor_is_an_error_frame_never_a_silent_legacy_fallback(ch):
    _ligar_diretor(ch, DiretorIndisponivel("timeout"))
    cid = _conversa(ch)
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    frames = _frames(r.text)
    assert frames[-1]["error"]["code"] == "diretor_indisponivel" and "timeout" not in json.dumps(frames[-1])
    assert ch.fake.calls == []
    assert [m["status"] for m in ch.rows("cs_chat_mensagens") if m["role"] == "assistant"] == ["erro"]


def test_the_codes_the_diretor_cites_are_resolved_from_the_library_not_only_the_pool(ch):
    """The Director cites the codes its tools returned: the parser validates them against the library, not a pool."""
    _ligar_diretor(ch, REPLY)
    cid = _conversa(ch)
    mid, p1, p2 = (str(uuid.uuid4()) for _ in range(3))
    _gravar_rpc(ch, cid, mid, [p1, p2])
    ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    payload = ch.rpc.last("cs_chat_resposta_gravar")["p"]
    assert [p["texto"] for p in payload["propostas"]] == ["Você dorme mal e acha normal", "O hábito que rouba o seu sono"]
    assert payload["propostas"][0]["estrutura_ids"] == [E1] and payload["propostas"][1]["estrutura_ids"] == [E2]
    assert payload["modelo"] == AGENT_KEY


def test_the_publicacao_blocks_are_stored_per_option_with_their_events(ch):
    _ligar_diretor(ch, REPLY)
    cid = _conversa(ch)
    mid, p1, p2 = (str(uuid.uuid4()) for _ in range(3))
    _gravar_rpc(ch, cid, mid, [p1, p2])
    ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    linhas = {r["proposta_id"]: r for r in ch.rows("cs_chat_proposta_publicacoes")}
    assert set(linhas) == {p1, p2}
    assert linhas[p1]["legenda"] == "Legenda da opção 1." and linhas[p1]["cta_objetivo"] == "salvamentos"
    assert len(linhas[p1]["hashtags"]) == 5 and linhas[p1]["primeiro_comentario"] == "Qual hábito você mudaria?"
    assert linhas[p2]["cta"] is None and linhas[p2]["cta_objetivo"] == "nenhum"
    gerados = [e for e in ch.rows("cs_fluxo_eventos") if e["tipo"] == "publicacao_gerada"]
    assert sorted(e["proposta_id"] for e in gerados) == sorted([p1, p2])
    assert all(e["org_id"] == TEST_ORG_ID and e["ator_id"] == TEST_USER_ID for e in gerados)
    assert not [e for e in ch.rows("cs_fluxo_eventos") if e["tipo"] == "publicacao_invalida"]


def test_an_invalid_block_is_counted_and_the_option_keeps_no_publicacao(ch):
    ruim = REPLY.replace("#sono #rotina #saude #bemestar #habitos", "#sono #rotina")
    _ligar_diretor(ch, ruim)
    cid = _conversa(ch)
    mid, p1, p2 = (str(uuid.uuid4()) for _ in range(3))
    _gravar_rpc(ch, cid, mid, [p1, p2])
    ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    assert [r["proposta_id"] for r in ch.rows("cs_chat_proposta_publicacoes")] == [p2]
    invalidas = [e for e in ch.rows("cs_fluxo_eventos") if e["tipo"] == "publicacao_invalida"]
    assert [e["contagem"] for e in invalidas] == [1]


def test_the_answer_survives_a_failure_to_store_the_publicacoes(ch):
    _ligar_diretor(ch, REPLY)
    cid = _conversa(ch)
    mid, p1, p2 = (str(uuid.uuid4()) for _ in range(3))
    _gravar_rpc(ch, cid, mid, [p1, p2])
    tabela = ch.db.table

    def quebrado(nome):  # the transport of the DOUBLE fails for the publicacoes table only
        if nome == "cs_chat_proposta_publicacoes":
            raise RuntimeError("db down")
        return tabela(nome)

    ch.db.table = quebrado
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    done = _frames(r.text)[-1]["done"]
    assert done["mensagem_id"] == mid and len(done["propostas"]) == 2


# ── the card receives the Publicação ─────────────────────────────────────────────────────────────────────


def _publicacao_row(pid, **kw):
    return {
        "proposta_id": pid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "numero": 1, "legenda": "Legenda do Diretor.",
        "hashtags": ["#a", "#b", "#c", "#d", "#e"], "primeiro_comentario": "Primeiro!", "cta": "Salve", "cta_objetivo": "salvamentos",
        "cta_justificativa": "porque sim e basta", "fontes": [], **kw}


def test_picking_an_option_puts_legenda_hashtags_and_first_comment_on_the_card_not_the_link(sg):
    cid, pid = _proposta_saga(sg)
    sg.db.from_("cs_chat_proposta_publicacoes").insert(_publicacao_row(pid)).execute()
    assert sg.escolher(cid, pid).status_code == 202
    post = sg.rows("cs_posts")[0]
    assert post["legenda"] == "Legenda do Diretor." and post["hashtags"] == ["#a", "#b", "#c", "#d", "#e"]
    assert post["primeiro_comentario"] == "Primeiro!" and not post.get("permalink")


def test_the_finalizer_does_not_generate_a_caption_over_the_diretors(sg):
    cid, pid = _proposta_saga(sg)
    sg.db.from_("cs_chat_proposta_publicacoes").insert(_publicacao_row(pid)).execute()
    sg.escolher(cid, pid)
    roteiro = sg.rows("cs_roteiros")[0]
    _completar_roteiro(sg, roteiro["id"])
    llm = Llm(LEGENDA_JSON)
    asyncio.run(sg.rodar("fluxo.finalizar_card", llm))
    assert llm.calls == 0 and sg.rows("cs_posts")[0]["legenda"] == "Legenda do Diretor."


def test_a_caption_a_person_already_wrote_is_never_overwritten(sg):
    cid, pid = _proposta_saga(sg)
    sg.db.from_("cs_chat_proposta_publicacoes").insert(_publicacao_row(pid)).execute()
    assert sg.escolher(cid, pid).status_code == 202
    post = sg.rows("cs_posts")[0]
    sg.db.from_("cs_posts").update({"legenda": "Minha legenda"}).eq("id", post["id"]).execute()
    proposta = sg.proposta(pid)
    assert PublicacaoService(sg.db, TEST_ORG_ID, TEST_USER_ID).aplicar_no_card(proposta, post["id"]) is False
    assert sg.rows("cs_posts")[0]["legenda"] == "Minha legenda"


def test_an_option_without_a_publicacao_keeps_the_old_flow(sg):
    cid, pid = _proposta_saga(sg)
    assert sg.escolher(cid, pid).status_code == 202
    assert not (sg.rows("cs_posts")[0].get("legenda") or "")


# ── multi-select ─────────────────────────────────────────────────────────────────────────────────────────

SEL = f"{BASE}/propostas/selecionar"


def _duas_propostas(sg):
    cid = _conversa_saga(sg)
    ids = []
    for ordem in (1, 2):
        mid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        sg.db.from_("cs_chat_mensagens").insert({
            "id": mid, "org_id": TEST_ORG_ID, "conversa_id": cid, "role": "assistant", "conteudo": "x", "referencias": [],
            "status": "completa", "truncada": False, "created_at": _agora()}).execute()
        sg.db.from_("cs_chat_propostas").insert({
            "id": pid, "org_id": TEST_ORG_ID, "marca_id": MARCA_SAGA, "conversa_id": cid, "mensagem_id": mid, "ordem": ordem,
            "tipo": "headline", "texto": f"Você erra isso {ordem}", "gatilho_tag": None, "status": "proposta", "fluxo_etapa": None,
            "fluxo_erro_codigo": None, "fluxo_lease_ate": None, "headline_id": None, "roteiro_id": None,
            "created_at": _agora()}).execute()
        sg.db.from_("cs_chat_proposta_estruturas").insert(
            {"proposta_id": pid, "estrutura_id": E1_SAGA, "ordem": 1, "principal": True}).execute()
        ids.append(pid)
    return cid, ids


def test_selecting_n_proposals_makes_n_cards_each_with_its_counterpart(sg):
    cid, ids = _duas_propostas(sg)
    r = sg.client.post(SEL, json={"ids": ids})
    assert r.status_code == 202, r.text
    d = r.json()["data"]
    assert [i["proposta_id"] for i in d["itens"]] == ids and all(i["ok"] for i in d["itens"])
    assert (d["criados"], d["ja_existiam"], d["falhas"]) == (ids, [], [])
    assert len(sg.rows("cs_posts")) == 2 and len(sg.rows("cs_roteiros")) == 2 and len(sg.rows("cs_headlines")) == 2
    assert all(i["fluxo"]["post"] is not None and i["fluxo"]["roteiro"] is not None for i in d["itens"])
    assert len(sg.jobs.do_tipo("fluxo.finalizar_card")) == 2


def test_selecting_the_same_proposals_again_is_idempotent_per_proposal(sg):
    cid, ids = _duas_propostas(sg)
    assert sg.client.post(SEL, json={"ids": ids}).status_code == 202
    r = sg.client.post(SEL, json={"ids": ids})
    d = r.json()["data"]
    assert r.status_code == 200 and (d["criados"], d["ja_existiam"]) == ([], ids)
    assert len(sg.rows("cs_posts")) == 2 and len(sg.rows("cs_roteiros")) == 2
    assert [i["ja_existia"] for i in d["itens"]] == [True, True]


def test_one_refused_item_does_not_stop_the_others_and_is_reported_with_its_code(sg):
    cid, ids = _duas_propostas(sg)
    sg.cfg.roteiros_dia_usuario = 1  # the daily roteiro cap lets ONE through
    d = sg.client.post(SEL, json={"ids": ids}).json()["data"]
    assert [i["ok"] for i in d["itens"]] == [True, False]
    assert d["itens"][1]["erro"]["code"] == "limite_diario_roteiros"
    assert d["criados"] == [ids[0]] and [(f["id"], f["code"]) for f in d["falhas"]] == [(ids[1], "limite_diario_roteiros")]
    assert len(sg.rows("cs_posts")) == 1


def test_a_foreign_or_unknown_id_is_a_404_before_any_claim(sg):
    cid, ids = _duas_propostas(sg)
    r = sg.client.post(SEL, json={"ids": [ids[0], str(uuid.uuid4())]})
    assert r.status_code == 404 and r.json()["code"] == "proposta_nao_encontrada"
    assert sg.rpc.names() == [] and sg.rows("cs_posts") == []


def test_the_screen_shape_conversa_id_is_accepted_and_scopes_the_ids(sg):
    cid, ids = _duas_propostas(sg)
    assert sg.client.post(SEL, json={"ids": ids, "conversa_id": cid}).status_code == 202
    outra = _conversa_saga(sg)
    r = sg.client.post(SEL, json={"ids": ids, "conversa_id": outra})
    assert r.status_code == 404 and r.json()["code"] == "proposta_nao_encontrada"


def test_the_batch_writes_one_opcoes_selecionadas_event_per_conversation_with_the_count(sg):
    cid, ids = _duas_propostas(sg)
    sg.client.post(SEL, json={"ids": ids})
    ev = [e for e in sg.rows("cs_fluxo_eventos") if e["tipo"] == "opcoes_selecionadas"]
    assert [(e["conversa_id"], e["contagem"], e["ator_id"]) for e in ev] == [(cid, 2, TEST_USER_ID)]


def test_the_body_is_strict_bounded_and_unique(sg):
    cid, ids = _duas_propostas(sg)
    assert sg.client.post(SEL, json={"ids": []}).status_code == 422
    assert sg.client.post(SEL, json={"ids": [ids[0], ids[0]]}).status_code == 422
    assert sg.client.post(SEL, json={"ids": [str(uuid.uuid4()) for _ in range(11)]}).status_code == 422
    assert sg.client.post(SEL, json={"ids": ids, "extra": 1}).status_code == 422


def test_selecting_without_a_session_is_exactly_401(sg):
    r = sg.client._tc.post(SEL, json={"ids": [str(uuid.uuid4())]})
    assert r.status_code == 401
    assert sg.rpc.calls == []


def test_the_new_route_has_the_ai_rate_limit_and_202():
    arvore = ast.parse(Path(chat_router.__file__).read_text())
    fn = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "selecionar")
    decorators = [ast.unparse(d) for d in fn.decorator_list]
    assert "limiter.limit(DEFAULT_AI_RL)" in decorators and any("status_code=202" in d for d in decorators)


def test_no_auth_assertion_in_this_module_accepts_an_alternative_status():
    for node in ast.walk(ast.parse(Path(__file__).read_text())):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops):
            nums = [c.value for comp in node.comparators if isinstance(comp, (ast.Tuple, ast.List, ast.Set))
                    for c in comp.elts if isinstance(c, ast.Constant)]
            assert 401 not in nums
