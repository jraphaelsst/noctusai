"""UNI-1a -- the unified chat (``estruturas-contract.md`` 6.5, 8.5, 9.1-9.2 steps 1-3).

Mounted through the real ``register()`` seam on the MockSupabaseClient. The SQL RPCs (claim / lease, headline + usos,
the answer's propostas, the event ledger) run on PGlite in ``tests/test_migration_cs_unified_chat.py``; here a
recording stub stands in for ``client.rpc`` so the service's parameter names, its call ORDER, its refusals and its
read-back are pinned. Nothing of ours is patched: the model stream, the citation parser, the IA key check, the budget
pre-check and the config are the production DI seams, overridden. Auth tests assert STRICT ``== 401``.

The citation parser used here is a TEST-LOCAL fake of the pinned seam (``services/propostas.extrair_propostas``,
EST-4a): same signature, same result shape, duck-typed -- the service only reads ``.propostas[*].{ordem, headline,
gatilho, estrutura_ids}`` and ``.eventos[*].{tipo, contagem}``.
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from noctusai_lib.testing import TEST_ORG_ID, TEST_USER_ID

from app.modules.media_creation.prompts import chat_unificado
from app.modules.media_creation.routers import chat as chat_router
from app.modules.media_creation.services import chat_service
from app.modules.media_creation.services.chat_contexto import ChatContexto, ContextoMontado
from app.modules.media_creation.services.chat_service import (
    AGENTE_UNIFICADO,
    ChatService,
    get_chat_stream_fn,
    get_extrair_propostas,
    liberar_stream,
)
from app.modules.media_creation.services.fluxo_service import (
    FluxoService,
    get_fluxo_orcamento,
    get_fluxo_settings,
)
from app.modules.media_creation.services.roteiro_service import RoteiroError, get_roteiro_ia_check
from fastapi import HTTPException
from noctusai_lib.domain.jobs import FakeJobRepository

BASE = "/api/media-creation/chat"
MARCA = str(uuid.uuid4())
OUTRA_MARCA = str(uuid.uuid4())
OUTRO_USUARIO = "someone-else-456"
PERFIL = str(uuid.uuid4())
E1, E2, E3 = (str(uuid.uuid4()) for _ in range(3))
HEADLINE_SALVA = str(uuid.uuid4())


# ── doubles ──────────────────────────────────────────────────────────────────────────────────────────────


class FakeApiError(Exception):
    """A PostgREST ``APIError`` double (the attributes ``_rpc_detalhes`` reads)."""

    def __init__(self, message: str, details: str = "", code: str = "P0001"):
        super().__init__({"message": message, "details": details, "code": code})
        self.message, self.details, self.code = message, details, code


class _Exec:
    def __init__(self, data=None, exc=None):
        self.data, self._exc = data, exc

    def execute(self):
        if self._exc:
            raise self._exc
        return self

    count = None


class RpcStub:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.results: dict[str, object] = {}
        self.errors: dict[str, Exception] = {}

    def __call__(self, name, params=None):
        self.calls.append((name, dict(params or {})))
        if name in self.errors:
            return _Exec(exc=self.errors[name])
        res = self.results.get(name, {})
        return _Exec(data=res() if callable(res) else res)

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]

    def last(self, name):
        return [p for n, p in self.calls if n == name][-1]


class FakeStream:
    """A scripted ``ChatStreamFn``: one dict per round (``chunks`` / ``truncated``)."""

    def __init__(self, *rodadas: dict):
        self.rodadas = list(rodadas) or [{"chunks": ["ok"]}]
        self.calls: list[dict] = []

    def __call__(self, messages, *, model, provider, org_id, outcome):
        self.calls.append({"messages": messages, "model": model, "provider": provider, "org_id": org_id})
        return self._gen(self.rodadas[min(len(self.calls) - 1, len(self.rodadas) - 1)], outcome)

    async def _gen(self, rodada, outcome):
        for c in rodada.get("chunks", []):
            yield c
        outcome.truncated = rodada.get("truncated", False)


@dataclass(frozen=True)
class _Citavel:
    id: str
    codigo: str
    formato: str


@dataclass(frozen=True)
class _PropostaValidada:
    ordem: int
    headline: str
    gatilho: str | None
    estrutura_ids: tuple
    tipo: str = "headline"
    titulo: str | None = None
    formato: str | None = None


@dataclass(frozen=True)
class _Resultado:
    propostas: tuple
    eventos: tuple


_LINHA = re.compile(r"^\s*(\d+)[.)]\s+(.*?)\s*\(estrutura\s+((?:#\d+\s*\+?\s*)+)\)\s*$")


def fake_extrair(texto, codigos_permitidos):
    """Test-local stand-in for the pinned ``extrair_propostas`` seam: numbered lines ending ``(estrutura #N [+ #M])``;
    a code not in ``codigos_permitidos`` is dropped and counted as ``citacao_rejeitada``."""
    propostas, rejeitadas = [], 0
    for linha in texto.splitlines():
        m = _LINHA.match(linha)
        if not m:
            continue
        ids = []
        for codigo in re.findall(r"#(\d+)", m.group(3)):
            if codigo in codigos_permitidos:
                ids.append(codigos_permitidos[codigo].id)
            else:
                rejeitadas += 1
        if ids:
            propostas.append(_PropostaValidada(len(propostas) + 1, m.group(2), None, tuple(ids)))
    eventos = ({"tipo": "citacao_rejeitada", "contagem": rejeitadas},) if rejeitadas else ()
    return _Resultado(tuple(propostas), eventos)


class _ContextoComCatalogo(ChatContexto):
    """A context that carries the Estrutura catalogue (the ``{codigo: EstruturaCitavel}`` EST-4a puts on its result)."""

    def __init__(self, base: ChatContexto, mapa: dict, **extra):
        self.__dict__.update(base.__dict__)
        self._mapa, self._extra, self.textos = mapa, extra, []

    def montar(self, conversa, refs, texto=None):
        self.textos.append(texto)  # the service must pass the typed text: it turns on the name resolution
        return ContextoMontado(
            texto="<material/>", chars=11, truncado=False, codigos_permitidos=[int(k) for k in self._mapa],
            citaveis=self._mapa, **self._extra)


def _agora(minutos=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutos)).isoformat()


def _frames(texto: str) -> list[dict]:
    return [json.loads(b[len("data: "):]) for b in texto.split("\n\n") if b.startswith("data: ")]


def _ia_ok(org_id):
    return None


async def _orcamento_ok(org_id):
    return None


class State:
    def __init__(self, client, **cfg):
        self.client = client
        self.rpc = RpcStub()
        self.fake = FakeStream({"chunks": ["Olá."]})
        self.cfg = SimpleNamespace(
            roteiros_dia_usuario=20, headline_lotes_dia_usuario=30, geracao_worker_enabled=True,
            geracao_llm_model="claude-test", **cfg)
        # RP-3 wired steps 4-7 (`fluxo_continuacao`) behind the click: its queue is the seed's Fake here
        # (the saga itself is pinned in test_fluxo_saga.py).
        self.jobs = FakeJobRepository()
        self.ia = _ia_ok
        self.orcamento = _orcamento_ok
        client.mock_supabase.rpc = self.rpc
        ov = client._tc.app.dependency_overrides
        ov[get_chat_stream_fn] = lambda: self.fake
        ov[get_extrair_propostas] = lambda: fake_extrair
        ov[get_fluxo_settings] = lambda: self.cfg
        ov[get_roteiro_ia_check] = lambda: (lambda org_id: self.ia(org_id))
        ov[get_fluxo_orcamento] = lambda: (lambda org_id: self.orcamento(org_id))
        ov[chat_router.get_fluxo_jobs] = lambda: self.jobs

    @property
    def db(self):
        return self.client.mock_supabase

    def rows(self, tabela):
        return self.db.from_(tabela).select("*").execute().data


@pytest.fixture
def ch(client):
    st = State(client)
    db = st.db
    db.from_("marcas").insert({"id": MARCA, "org_id": TEST_ORG_ID, "name": "Marca A"}).execute()
    db.from_("marcas").insert({"id": OUTRA_MARCA, "org_id": "other-org", "name": "Marca B"}).execute()
    db.from_("cs_perfis_monitorados").insert(
        {"id": PERFIL, "org_id": TEST_ORG_ID, "handle": "psifernandosegredo", "nome": "Fernando Segredo"}
    ).execute()
    for i, (eid, codigo) in enumerate(((E1, 101), (E2, 102), (E3, 103)), start=1):
        db.from_("cs_estruturas").insert(
            {"id": eid, "codigo": codigo, "perfil_id": PERFIL, "formula_headline": f"Fórmula {i}  [x]  com   espaços",
             "formato": "reels", "status": "ativa"}
        ).execute()
    liberar_stream(TEST_USER_ID)
    st.client = client
    yield st
    liberar_stream(TEST_USER_ID)


def _conversa(st, *, user=TEST_USER_ID, agente="unificado", marca=MARCA) -> str:
    cid = str(uuid.uuid4())
    st.db.from_("cs_chat_conversas").insert({
        "id": cid, "org_id": TEST_ORG_ID, "marca_id": marca, "user_id": user, "agente": agente,
        "titulo": "Conversa", "last_message_at": _agora()}).execute()
    return cid


def _mensagem(st, cid, role="assistant", conteudo="texto", **extra) -> str:
    mid = str(uuid.uuid4())
    st.db.from_("cs_chat_mensagens").insert({
        "id": mid, "org_id": TEST_ORG_ID, "conversa_id": cid, "role": role, "conteudo": conteudo, "referencias": [],
        "status": "completa", "truncada": False, "created_at": _agora(), **extra}).execute()
    return mid


def _proposta(st, cid, mid, *, ordem=1, texto="Headline", estruturas=((E1, True), (E2, False)), **extra) -> str:
    pid = str(uuid.uuid4())
    st.db.from_("cs_chat_propostas").insert({
        "id": pid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "conversa_id": cid, "mensagem_id": mid, "ordem": ordem,
        "texto": texto, "gatilho_tag": None, "status": "proposta", "fluxo_etapa": None, "fluxo_erro_codigo": None,
        "fluxo_lease_ate": None, "headline_id": None, "created_at": _agora(), **extra}).execute()
    for i, (eid, principal) in enumerate(estruturas, start=1):
        st.db.from_("cs_chat_proposta_estruturas").insert(
            {"proposta_id": pid, "estrutura_id": eid, "ordem": i, "principal": principal}).execute()
    return pid


# ── auth: STRICT 401 on every chat route ─────────────────────────────────────────────────────────────────

ROTAS = [
    ("get", "/conversas", {"marca_id": MARCA}, None),
    ("post", "/conversas", None, {"marca_id": MARCA}),
    ("patch", f"/conversas/{uuid.uuid4()}", None, {"titulo": "x"}),
    ("delete", f"/conversas/{uuid.uuid4()}", None, None),
    ("get", f"/conversas/{uuid.uuid4()}/mensagens", None, None),
    ("post", f"/conversas/{uuid.uuid4()}/mensagens", None, {"conteudo": "oi", "referencias": []}),
    ("post", f"/conversas/{uuid.uuid4()}/escolher", None, {"proposta_id": str(uuid.uuid4())}),
    ("get", "/mencoes", {"marca_id": MARCA, "tipo": "pesquisa"}, None),
    ("get", "/memorias", {"marca_id": MARCA}, None),
    ("post", "/memorias", None, {"marca_id": MARCA, "texto": "x"}),
    ("delete", f"/memorias/{uuid.uuid4()}", None, None),
    ("get", "/contexto", {"conversa_id": str(uuid.uuid4())}, None),
]


@pytest.mark.parametrize("metodo,caminho,params,body", ROTAS)
def test_sem_sessao_e_exatamente_401(ch, metodo, caminho, params, body):
    r = getattr(ch.client._tc, metodo)(f"{BASE}{caminho}", params=params, **({"json": body} if body is not None else {}))
    assert r.status_code == 401
    assert ch.rpc.calls == []


def test_nenhuma_asserção_de_auth_aceita_status_alternativo():
    for node in ast.walk(ast.parse(Path(__file__).read_text())):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops):
            nums = [c.value for comp in node.comparators if isinstance(comp, (ast.Tuple, ast.List, ast.Set))
                    for c in comp.elts if isinstance(c, ast.Constant)]
            assert 401 not in nums


def test_a_rota_de_escolher_tem_default_ai_rl_e_202():
    arvore = ast.parse(Path(chat_router.__file__).read_text())
    fn = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "escolher")
    decorators = [ast.unparse(d) for d in fn.decorator_list]
    assert "limiter.limit(DEFAULT_AI_RL)" in decorators
    assert any("status_code=202" in d for d in decorators)


# ── ONE unified chat: agente accepted and ignored, legacy rows listed and readable as unified ────────────


def test_agente_e_aceito_e_ignorado_na_criacao_e_a_conversa_nasce_unificada(ch):
    for agente in ("headline", "roteiro", "unificado", None):
        body = {"marca_id": MARCA, **({"agente": agente} if agente else {})}
        r = ch.client.post(f"{BASE}/conversas", json=body)
        assert r.status_code == 201, r.text
        assert r.json()["data"]["agente"] == "unificado"
    assert {c["agente"] for c in ch.rows("cs_chat_conversas")} == {"unificado"}
    # still strict: an unknown field is refused, a bogus agente too
    assert ch.client.post(f"{BASE}/conversas", json={"marca_id": MARCA, "modo": "x"}).status_code == 422
    assert ch.client.post(f"{BASE}/conversas", json={"marca_id": MARCA, "agente": "outro"}).status_code == 422


def test_as_8_conversas_legadas_sao_listadas_e_lidas_como_unificadas(ch):
    """Prod today: 7 headline + 1 roteiro conversations. The N code lists them all, per (user, marca), whatever the
    deprecated ``agente`` filter says, and opens them as unified."""
    ids = [_conversa(ch, agente="headline") for _ in range(7)] + [_conversa(ch, agente="roteiro")]
    novas = _conversa(ch, agente="unificado")
    _conversa(ch, user=OUTRO_USUARIO, agente="headline")  # someone else's: never listed
    for filtro in ({}, {"agente": "headline"}, {"agente": "roteiro"}, {"agente": "unificado"}):
        r = ch.client.get(f"{BASE}/conversas", params={"marca_id": MARCA, "limit": 15, **filtro})
        assert r.status_code == 200, r.text
        itens = r.json()["data"]["items"]
        assert {i["id"] for i in itens} == {*ids, novas}, filtro
        assert {i["agente"] for i in itens} == {"unificado"}
        assert set(itens[0]) == {"id", "marca_id", "agente", "titulo", "last_message_at"}
    # a legacy conversation opens: messages carry the new fields with their truthful defaults
    antiga = ids[-1]
    _mensagem(ch, antiga, "user", "oi")
    _mensagem(ch, antiga, "assistant", "1. Headline (estrutura #5)")  # legacy text, no propostas recorded
    r = ch.client.get(f"{BASE}/conversas/{antiga}/mensagens")
    assert r.status_code == 200
    msgs = r.json()["data"]["items"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert all(m["tipo"] == "texto" and m["propostas"] == [] and m["fluxo"] is None for m in msgs)


def test_enviar_em_conversa_legada_responde_com_o_prompt_unificado(ch):
    cid = _conversa(ch, agente="roteiro")
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    assert r.status_code == 200
    system = ch.fake.calls[0]["messages"][0]["content"]
    system = system if isinstance(system, str) else "".join(b.get("text", "") for b in system)
    assert "assistente do Criação de Mídia" in system and chat_unificado.SYSTEM_PROMPT[:80] in system
    assert "agente ROTEIRO" not in system and "agente HEADLINE" not in system


# ── reads: Mensagem.propostas / Mensagem.fluxo ────────────────────────────────────────────────────────────


def test_mensagem_traz_propostas_no_formato_do_contrato(ch):
    cid = _conversa(ch)
    _mensagem(ch, cid, "user", "headlines?")
    mid = _mensagem(ch, cid, "assistant", "### Análise\n1. Headline")
    pid = _proposta(ch, cid, mid, texto="Headline um")
    outra_org = _proposta(ch, cid, _mensagem(ch, cid, "assistant", "x"), ordem=1)
    ch.db.from_("cs_chat_propostas").update({"org_id": "other-org"}).eq("id", outra_org).execute()
    r = ch.client.get(f"{BASE}/conversas/{cid}/mensagens")
    assert r.status_code == 200
    msgs = r.json()["data"]["items"]
    com = next(m for m in msgs if m["id"] == mid)
    assert com["propostas"] == [{
        "id": pid, "ordem": 1, "texto": "Headline um", "gatilho_tag": None, "status": "proposta", "headline_id": None,
        "tipo": "headline", "titulo": None, "formato": None, "roteiro_id": None,
        "estruturas": [
            {"id": E1, "codigo": 101, "perfil": {"id": PERFIL, "handle": "psifernandosegredo", "nome": "Fernando Segredo"}, "principal": True},
            {"id": E2, "codigo": 102, "perfil": {"id": PERFIL, "handle": "psifernandosegredo", "nome": "Fernando Segredo"}, "principal": False},
        ],
    }]
    assert all(m["propostas"] == [] for m in msgs if m["id"] != mid)  # the foreign org's proposta never shows
    corpo = json.dumps(r.json())
    for campo in ("org_id", "fluxo_lease_ate", "escolhida_por", "fluxo_erro_codigo", "user_id"):
        assert campo not in corpo


def _roteiro(st, cid, headline_id, *, status="processando", formato="carrossel", **extra) -> str:
    rid = str(uuid.uuid4())
    st.db.from_("cs_roteiros").insert({
        "id": rid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "created_by": TEST_USER_ID, "nome": "Roteiro 1",
        "headline_id": headline_id, "conversa_id": cid, "status": status, "formato": formato, "duracao": "auto",
        "estrutura": "cta_inicio", "versao": 1, "created_at": _agora(), **extra}).execute()
    return rid


def _fluxo_pronto(st, *, roteiro_status, formato="carrossel", legenda=None, etapa="card_criado", com_post=True):
    cid = _conversa(st)
    mid = _mensagem(st, cid, "assistant", "headlines")
    hid = str(uuid.uuid4())
    st.db.from_("cs_headlines").insert({"id": hid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "texto": "Headline um"}).execute()
    pid = _proposta(st, cid, mid, texto="Headline um", status="escolhida", fluxo_etapa=etapa, headline_id=hid)
    rid = _roteiro(st, cid, hid, status=roteiro_status, formato=formato)
    if com_post:
        etapa_id = str(uuid.uuid4())
        st.db.from_("pipeline_stages").insert({"id": etapa_id, "org_id": TEST_ORG_ID, "label": "Headline + roteiro"}).execute()
        st.db.from_("cs_posts").insert({
            "id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA, "titulo": "Headline um", "etapa_id": etapa_id,
            "roteiro_id": rid, "legenda": legenda}).execute()
    st.db.from_("cs_estrutura_usos").insert({
        "id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA, "estrutura_id": E1, "contexto": "chat",
        "papel": "principal", "ordem": 1, "bloco_ids": [], "headline_id": hid, "proposta_id": pid}).execute()
    st.db.from_("cs_estrutura_usos").insert({
        "id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA, "estrutura_id": E2, "contexto": "chat",
        "papel": "mistura", "ordem": 2, "bloco_ids": [], "headline_id": hid, "proposta_id": pid}).execute()
    return cid, pid, hid, rid


@pytest.mark.parametrize("roteiro_status,etapa", [
    ("criando", "roteiro_gerando"), ("processando", "roteiro_gerando"), ("completo", "roteiro_pronto"), ("falha", "falhou"),
])
def test_fluxo_e_composto_na_leitura_a_partir_das_tabelas_verdade(ch, roteiro_status, etapa):
    cid, pid, hid, rid = _fluxo_pronto(ch, roteiro_status=roteiro_status)
    mid = _mensagem(ch, cid, "assistant", "Criei o roteiro desta headline e o card na Esteira.",
                    tipo="roteiro_gerado", proposta_id=pid)
    msgs = ch.client.get(f"{BASE}/conversas/{cid}/mensagens").json()["data"]["items"]
    msg = next(m for m in msgs if m["id"] == mid)
    assert msg["tipo"] == "roteiro_gerado"
    f = msg["fluxo"]
    assert f["proposta_id"] == pid and f["etapa"] == etapa and f["direcao"] == "headline_primeiro"
    assert f["headline"] == {"id": hid, "texto": "Headline um"}
    assert f["roteiro"] == {"id": rid, "nome": "Roteiro 1", "status": roteiro_status, "formato": "carrossel",
                            "duracao": "auto", "ordem_cta": "cta_inicio", "versao": 1}
    assert f["post"]["titulo"] == "Headline um" and f["post"]["etapa_label"] == "Headline + roteiro"
    assert [(e["codigo"], e["papel"]) for e in f["estruturas"]] == [(101, "principal"), (102, "mistura")]
    assert f["estruturas"][0]["perfil"]["handle"] == "psifernandosegredo"
    assert f["estruturas"][0]["formula_trecho"] == "Fórmula 1 [x] com espaços"  # whitespace folded, never mid-markup
    assert f["legenda"] == "pendente" and f["erro_codigo"] is None
    assert [m["fluxo"] for m in msgs if m["id"] != mid] == [None] * (len(msgs) - 1)


def test_fluxo_legenda_gerada_so_quando_o_card_tem_legenda_e_indisponivel_quando_o_evento_diz(ch):
    cid, pid, hid, rid = _fluxo_pronto(ch, roteiro_status="completo", legenda="Legenda pronta")
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    assert svc.compor_fluxo(svc.get_proposta(pid))["legenda"] == "gerada"
    cid2, pid2, *_ = _fluxo_pronto(ch, roteiro_status="completo", legenda=None)
    assert svc.compor_fluxo(svc.get_proposta(pid2))["legenda"] == "pendente"
    ch.db.from_("cs_fluxo_eventos").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA,
                                            "conversa_id": cid2, "proposta_id": pid2, "tipo": "legenda_falhou"}).execute()
    assert svc.compor_fluxo(svc.get_proposta(pid2))["legenda"] == "indisponivel"


def test_fluxo_sem_roteiro_e_headline_salva_e_a_etapa_falhou_vence(ch):
    cid = _conversa(ch)
    mid = _mensagem(ch, cid)
    pid = _proposta(ch, cid, mid, status="escolhida", fluxo_etapa="headline_salva")
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["etapa"] == "headline_salva" and f["roteiro"] is None and f["post"] is None and f["legenda"] == "pendente"
    ch.db.from_("cs_chat_propostas").update({"fluxo_etapa": "falhou", "fluxo_erro_codigo": "demorou"}).eq("id", pid).execute()
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["etapa"] == "falhou" and f["erro_codigo"] == "demorou"


# ── roteiro-first (contract 16.5): the proposta's tipo decides the direction; the read side composes the states ──


def _fluxo_roteiro_primeiro(st, *, fluxo_etapa="roteiro_salvo", com_headline=False, com_post=False,
                            roteiro_status="completo", erro=None):
    cid = _conversa(st)
    mid = _mensagem(st, cid, "assistant", "### Roteiro 1: ...")
    rid = _roteiro(st, cid, None, status=roteiro_status, formato="carrossel", nome="O erro mais caro")
    hid = None
    if com_headline:
        hid = str(uuid.uuid4())
        st.db.from_("cs_headlines").insert(
            {"id": hid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "texto": "Headline gerada", "modo": "do_roteiro"}).execute()
    pid = _proposta(st, cid, mid, texto="**Slide 1 — Gancho**\nTexto", status="escolhida", fluxo_etapa=fluxo_etapa,
                    fluxo_erro_codigo=erro, tipo="roteiro", titulo="O erro mais caro", formato="carrossel",
                    roteiro_id=rid, headline_id=hid)
    if com_post:
        etapa_id = str(uuid.uuid4())
        st.db.from_("pipeline_stages").insert({"id": etapa_id, "org_id": TEST_ORG_ID, "label": "Headline + roteiro"}).execute()
        st.db.from_("cs_posts").insert({
            "id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA, "titulo": "Headline gerada",
            "etapa_id": etapa_id, "roteiro_id": rid, "legenda": None}).execute()
    return cid, pid, rid, hid


def _evento(st, cid, pid, tipo):
    st.db.from_("cs_fluxo_eventos").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA,
                                            "conversa_id": cid, "proposta_id": pid, "tipo": tipo}).execute()


def test_proposta_de_roteiro_e_apresentada_com_tipo_titulo_formato_e_roteiro_id(ch):
    cid, pid, rid, _ = _fluxo_roteiro_primeiro(ch)
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    (prop,) = svc.apresentar_propostas([svc.get_proposta(pid)])
    assert (prop["tipo"], prop["titulo"], prop["formato"], prop["roteiro_id"]) == ("roteiro", "O erro mais caro", "carrossel", rid)
    assert prop["texto"].startswith("**Slide 1") and prop["headline_id"] is None


def test_roteiro_primeiro_salvo_sem_job_e_roteiro_salvo_com_headline_nula(ch):
    cid, pid, rid, _ = _fluxo_roteiro_primeiro(ch)
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["direcao"] == "roteiro_primeiro" and f["etapa"] == "roteiro_salvo" and f["headline"] is None
    assert f["roteiro"]["id"] == rid and f["roteiro"]["status"] == "completo" and f["roteiro"]["nome"] == "O erro mais caro"
    assert f["post"] is None and f["legenda"] == "pendente"


def test_roteiro_primeiro_com_o_job_da_headline_pendente_e_headline_gerando(ch):
    cid, pid, *_ = _fluxo_roteiro_primeiro(ch)
    _evento(ch, cid, pid, "headline_gerando")
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["etapa"] == "headline_gerando" and f["headline"] is None


def test_roteiro_primeiro_com_headline_mas_sem_card_ainda_esta_em_andamento(ch):
    cid, pid, _, hid = _fluxo_roteiro_primeiro(ch, fluxo_etapa="headline_gerada", com_headline=True)
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["etapa"] == "headline_gerando" and f["headline"] == {"id": hid, "texto": "Headline gerada"}


def test_roteiro_primeiro_com_headline_e_card_e_roteiro_pronto(ch):
    cid, pid, _, hid = _fluxo_roteiro_primeiro(ch, fluxo_etapa="card_criado", com_headline=True, com_post=True)
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["etapa"] == "roteiro_pronto" and f["headline"]["texto"] == "Headline gerada"
    assert f["post"]["titulo"] == "Headline gerada"


def test_roteiro_primeiro_headline_invalida_e_falhou_com_o_codigo(ch):
    cid, pid, *_ = _fluxo_roteiro_primeiro(ch, fluxo_etapa="falhou", erro="headline_invalida")
    _evento(ch, cid, pid, "headline_gerando")
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    f = svc.compor_fluxo(svc.get_proposta(pid))
    assert f["etapa"] == "falhou" and f["erro_codigo"] == "headline_invalida" and f["headline"] is None


def test_uma_linha_legada_sem_tipo_e_headline_primeiro(ch):
    cid = _conversa(ch)
    pid = _proposta(ch, cid, _mensagem(ch, cid), status="escolhida", fluxo_etapa="headline_salva")
    ch.db.from_("cs_chat_propostas").update({"tipo": None}).eq("id", pid).execute()
    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg)
    linha = svc.get_proposta(pid)
    assert svc.apresentar_propostas([linha])[0]["tipo"] == "headline"
    assert svc.compor_fluxo(linha)["direcao"] == "headline_primeiro"


def test_clique_num_roteiro_antes_da_saga_do_rp3_e_409_codificado_nunca_500(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.rpc.results["cs_chat_proposta_reivindicar"] = _claimed(pid, cid)
    ch.rpc.errors["cs_chat_proposta_salvar_headline"] = FakeApiError("headline_texto_ausente")
    r = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid})
    assert r.status_code == 409 and r.json()["code"] == "roteiro_primeiro_indisponivel"


# ── the stream: meta / delta / done.propostas ─────────────────────────────────────────────────────────────

TEXTO_COM_HEADLINES = (
    "### Análise da Estrutura Escolhida\nTexto.\n\n"
    "1. Você erra isso no consultório (estrutura #101)\n"
    "2. O erro que custa clientes (estrutura #101 + #102)\n"
    "3. Citação inventada (estrutura #999)\n"
)


def _svc_com_catalogo(st, mapa=None, **extra):
    svc = ChatService(st.db, TEST_ORG_ID, TEST_USER_ID)
    mapa = mapa if mapa is not None else {
        "101": _Citavel(E1, "101", "reels"), "102": _Citavel(E2, "102", "reels"), "103": _Citavel(E3, "103", "reels")}
    svc.contexto = _ContextoComCatalogo(svc.contexto, mapa, **extra)
    return svc


async def _stream(svc, st, cid, texto, *, extrair=fake_extrair):
    st.fake = FakeStream({"chunks": [texto]})
    envio = await svc.preparar_envio(cid, "me dê headlines", [], st.fake, extrair)
    return [json.loads(f[len("data: "):]) async for f in svc.eventos(envio, "me dê headlines")]


def test_done_traz_as_propostas_validadas_gravadas_numa_transacao(ch):
    cid = _conversa(ch)
    mid_novo = str(uuid.uuid4())
    p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())

    def gravar():
        _mensagem_row = {"id": mid_novo, "org_id": TEST_ORG_ID, "conversa_id": cid, "role": "assistant",
                         "conteudo": TEXTO_COM_HEADLINES, "referencias": [], "status": "completa", "truncada": False,
                         "created_at": _agora(), "tipo": "texto"}
        ch.db.from_("cs_chat_mensagens").insert(_mensagem_row).execute()
        _proposta_rows(ch, cid, mid_novo, p1, p2)
        return {"mensagem_id": mid_novo, "propostas": [{"id": p1, "ordem": 1}, {"id": p2, "ordem": 2}]}

    ch.rpc.results["cs_chat_resposta_gravar"] = gravar
    svc = _svc_com_catalogo(ch)
    frames = asyncio.run(_stream(svc, ch, cid, TEXTO_COM_HEADLINES))
    assert [list(f)[0] for f in frames] == ["meta", "delta", "done"]
    assert frames[0]["meta"]["codigos_permitidos"] == [101, 102, 103]
    assert frames[0]["meta"]["modo_estrutura"] == "auto"
    assert frames[0]["meta"]["resolucao_perfis"] == {"resolvidos": [], "ambiguos": [], "nao_encontrados": []}
    done = frames[2]["done"]
    assert done["mensagem_id"] == mid_novo
    assert [(p["id"], p["ordem"], p["texto"]) for p in done["propostas"]] == [(p1, 1, "Você erra isso no consultório"), (p2, 2, "O erro que custa clientes")]
    assert [e["principal"] for e in done["propostas"][1]["estruturas"]] == [True, False]
    # ONE call wrote the whole answer; the parser's rejection came along as an event
    assert ch.rpc.names() == ["cs_chat_resposta_gravar"]
    p = ch.rpc.last("cs_chat_resposta_gravar")["p"]
    assert p["org_id"] == TEST_ORG_ID and p["user_id"] == TEST_USER_ID and p["conversa_id"] == cid
    assert p["conteudo"] == TEXTO_COM_HEADLINES and p["truncada"] is False and p["modelo"]
    assert p["propostas"] == [
        {"ordem": 1, "tipo": "headline", "texto": "Você erra isso no consultório", "titulo": None, "formato": None,
         "gatilho_tag": None, "estrutura_ids": [E1]},
        {"ordem": 2, "tipo": "headline", "texto": "O erro que custa clientes", "titulo": None, "formato": None,
         "gatilho_tag": None, "estrutura_ids": [E1, E2]},
    ]
    assert p["eventos"] == [{"tipo": "citacao_rejeitada", "contagem": 1}]
    # the assistant message was NOT inserted a second time by the plain path
    assert [m["id"] for m in ch.rows("cs_chat_mensagens") if m["role"] == "assistant"] == [mid_novo]


def test_um_roteiro_proposto_e_gravado_com_tipo_titulo_formato_e_o_script_inteiro_pelo_parser_real(ch):
    cid = _conversa(ch)
    corpo = "**Slide 1 — Gancho**\nVocê erra nisso.\n**Slide 2 — Virada**\nFaça assim."
    texto = (f"### Roteiro 1: O erro mais caro (estrutura #101)\n{corpo}\n\n"
             "### Roteiro 2: Sem slides (estrutura #101)\nTexto corrido.\n")
    ch.rpc.results["cs_chat_resposta_gravar"] = {"mensagem_id": str(uuid.uuid4()), "propostas": []}
    mapa = {"101": _Citavel(E1, "101", "carrossel")}
    asyncio.run(_stream(_svc_com_catalogo(ch, mapa), ch, cid, texto, extrair=chat_service.extrair_propostas_padrao))
    p = ch.rpc.last("cs_chat_resposta_gravar")["p"]
    assert p["propostas"] == [{"ordem": 1, "tipo": "roteiro", "texto": corpo, "titulo": "O erro mais caro",
                               "formato": "carrossel", "gatilho_tag": None, "estrutura_ids": [E1]}]
    assert p["eventos"] == [{"tipo": "roteiro_invalido", "contagem": 1}]


def _proposta_rows(st, cid, mid, p1, p2):
    for pid, ordem, texto, ests in ((p1, 1, "Você erra isso no consultório", (E1,)), (p2, 2, "O erro que custa clientes", (E1, E2))):
        st.db.from_("cs_chat_propostas").insert({
            "id": pid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "conversa_id": cid, "mensagem_id": mid, "ordem": ordem,
            "texto": texto, "gatilho_tag": None, "status": "proposta", "headline_id": None, "created_at": _agora()}).execute()
        for i, e in enumerate(ests, start=1):
            st.db.from_("cs_chat_proposta_estruturas").insert(
                {"proposta_id": pid, "estrutura_id": e, "ordem": i, "principal": i == 1}).execute()


def test_a_citacao_mais_de_tres_e_cortada_no_servidor_e_repetidas_somem(ch):
    cid = _conversa(ch)

    def extrair_muitas(texto, mapa):
        return _Resultado((_PropostaValidada(1, "H", "Curiosidade", (E1, E1, E2, E3, str(uuid.uuid4()))),), ())

    ch.rpc.results["cs_chat_resposta_gravar"] = {"mensagem_id": str(uuid.uuid4()), "propostas": []}
    asyncio.run(_stream(_svc_com_catalogo(ch), ch, cid, "x", extrair=extrair_muitas))
    item = ch.rpc.last("cs_chat_resposta_gravar")["p"]["propostas"][0]
    assert item["estrutura_ids"] == [E1, E2, E3] and item["gatilho_tag"] == "Curiosidade"


def test_so_rejeicoes_sem_nenhuma_proposta_ainda_gravam_os_eventos(ch):
    cid = _conversa(ch)

    def so_rejeita(texto, mapa):
        return _Resultado((), ({"tipo": "placeholder_remanescente", "contagem": 2}, {"tipo": "formato_misturado", "contagem": 1}))

    ch.rpc.results["cs_chat_resposta_gravar"] = {"mensagem_id": str(uuid.uuid4()), "propostas": []}
    frames = asyncio.run(_stream(_svc_com_catalogo(ch), ch, cid, "1. [x] (estrutura #101)", extrair=so_rejeita))
    assert frames[-1]["done"]["propostas"] == []
    p = ch.rpc.last("cs_chat_resposta_gravar")["p"]
    assert p["propostas"] == [] and p["eventos"] == [
        {"tipo": "placeholder_remanescente", "contagem": 2}, {"tipo": "formato_misturado", "contagem": 1}]


def test_texto_sem_headline_e_salvo_pelo_caminho_simples_sem_rpc(ch):
    cid = _conversa(ch)
    frames = asyncio.run(_stream(_svc_com_catalogo(ch), ch, cid, "Qual é o assunto do vídeo?"))
    assert frames[-1]["done"]["propostas"] == [] and ch.rpc.calls == []
    assert [m["conteudo"] for m in ch.rows("cs_chat_mensagens") if m["role"] == "assistant"] == ["Qual é o assunto do vídeo?"]


def test_evento_desconhecido_do_parser_e_descartado_com_log_nunca_gravado(ch, caplog):
    cid = _conversa(ch)

    def extrair(texto, mapa):
        return _Resultado((), ({"tipo": "evento_inventado", "contagem": 1},))

    with caplog.at_level("ERROR"):
        asyncio.run(_stream(_svc_com_catalogo(ch), ch, cid, "x", extrair=extrair))
    assert "evento desconhecido" in caplog.text
    assert ch.rpc.calls == []  # nothing valid left to record: the plain path saved the answer


def test_falha_do_parser_ou_do_rpc_nao_custa_a_resposta_ao_usuario_e_e_logada(ch, caplog):
    cid = _conversa(ch)

    def quebrado(texto, mapa):
        raise RuntimeError("parser bug")

    with caplog.at_level("ERROR"):
        frames = asyncio.run(_stream(_svc_com_catalogo(ch), ch, cid, "1. a (estrutura #101)", extrair=quebrado))
    assert frames[-1]["done"]["propostas"] == []
    assert "parser de propostas falhou" in caplog.text
    cid2 = _conversa(ch)
    ch.rpc.errors["cs_chat_resposta_gravar"] = RuntimeError("db down")
    caplog.clear()
    with caplog.at_level("ERROR"):
        frames = asyncio.run(_stream(_svc_com_catalogo(ch), ch, cid2, "1. a (estrutura #101)"))
    assert frames[-1]["done"]["propostas"] == [] and "falha ao gravar a resposta com propostas" in caplog.text
    salvos = [m["conteudo"] for m in ch.rows("cs_chat_mensagens") if m["role"] == "assistant"]
    assert salvos == ["1. a (estrutura #101)"] * 2  # the user kept both answers


def test_o_contexto_real_do_est_4a_alimenta_o_parser_e_o_meta(ch):
    """No fake context here: the REAL ``ChatContexto`` (EST-4a) offers the three seeded active Estruturas as the pool;
    the parser receives exactly that catalogue and ``meta.codigos_permitidos`` carries the same numbers."""
    cid = _conversa(ch)
    vistos = []

    def espia(texto, mapa):
        vistos.append({k: (str(v.id), v.formato) for k, v in mapa.items()})
        return _Resultado((), ())

    svc = ChatService(ch.db, TEST_ORG_ID, TEST_USER_ID)
    frames = asyncio.run(_stream(svc, ch, cid, "1. a (estrutura #101)", extrair=espia))
    assert vistos == [{"101": (E1, "reels"), "102": (E2, "reels"), "103": (E3, "reels")}]
    assert sorted(frames[0]["meta"]["codigos_permitidos"]) == [101, 102, 103]
    assert frames[0]["meta"]["modo_estrutura"] == "auto" and frames[-1]["done"]["propostas"] == []
    assert ch.rpc.calls == []


def test_resolucao_de_perfil_no_texto_vira_referencia_via_texto_eventos_e_meta(ch):
    """EST-4a's context resolves the typed profile name; the service passes the text, stores the resolved mentions on
    the user message (``via: "texto"``), writes the outcome events and puts mode + resolution in ``meta``."""
    from app.modules.media_creation.services.chat_contexto import ReferenciaResolvida
    from app.modules.media_creation.services.estruturas_retrieval import ResolucaoPerfis

    cid = _conversa(ch)
    via = ReferenciaResolvida("biblioteca", f"perfil:{PERFIL}", "@psifernandosegredo — Todos os vídeos", {}, via="texto")
    svc = _svc_com_catalogo(
        ch, modo_estrutura="mencoes", resolucao=ResolucaoPerfis(), referencias_via_texto=[via],
        eventos=[{"tipo": "perfil_resolvido", "contagem": 1}, {"tipo": "perfil_ambiguo", "contagem": 2}])
    frames = asyncio.run(_stream(svc, ch, cid, "ok"))
    assert svc.contexto.textos == ["me dê headlines"]
    assert frames[0]["meta"]["modo_estrutura"] == "mencoes"
    assert frames[0]["meta"]["resolucao_perfis"] == {"resolvidos": [], "ambiguos": [], "nao_encontrados": []}
    user = next(m for m in ch.rows("cs_chat_mensagens") if m["role"] == "user")
    assert user["referencias"] == [{"tipo": "biblioteca", "id": f"perfil:{PERFIL}",
                                    "rotulo": "@psifernandosegredo — Todos os vídeos", "via": "texto"}]
    ev = ch.rows("cs_fluxo_eventos")
    assert sorted((e["tipo"], e["contagem"]) for e in ev) == [("perfil_ambiguo", 2), ("perfil_resolvido", 1)]
    assert {e["mensagem_id"] for e in ev} == {user["id"]} and {e["ator_id"] for e in ev} == {TEST_USER_ID}
    assert {e["conversa_id"] for e in ev} == {cid} and {e["marca_id"] for e in ev} == {MARCA}


def test_envio_http_inclui_o_frame_meta_novo_e_done_com_propostas(ch):
    cid = _conversa(ch)
    r = ch.client.post(f"{BASE}/conversas/{cid}/mensagens", json={"conteudo": "oi", "referencias": []})
    assert r.status_code == 200
    frames = _frames(r.text)
    assert [list(f)[0] for f in frames] == ["meta", "delta", "done"]
    assert frames[2]["done"].keys() == {"mensagem_id", "propostas"}


def test_mencao_do_tipo_estrutura_e_aceita_pelo_esquema(ch):
    from app.modules.media_creation.schemas.chat import ReferenciaIn

    assert ReferenciaIn(tipo="estrutura", id=E1).tipo == "estrutura"


# ── escolher ──────────────────────────────────────────────────────────────────────────────────────────────


def _proposta_para_escolher(st, **extra):
    cid = _conversa(st)
    mid = _mensagem(st, cid)
    pid = _proposta(st, cid, mid, texto="Headline um", **extra)
    return cid, mid, pid


def _claimed(pid, cid, *, etapa=None, status="escolhida"):
    return {"claimed": True, "proposta": {"id": pid, "conversa_id": cid, "status": status, "fluxo_etapa": etapa}}


def _simular_headline_salva(st, cid, pid):
    """What the SQL does at step 2 (``cs_chat_proposta_salvar_headline``): used so the service's read-back sees it."""
    hid = str(uuid.uuid4())
    st.db.from_("cs_headlines").insert({"id": hid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "texto": "Headline um",
                                        "conversa_id": cid, "proposta_id": pid, "favorita": True}).execute()
    st.db.from_("cs_chat_propostas").update(
        {"status": "escolhida", "headline_id": hid, "fluxo_etapa": "headline_salva"}).eq("id", pid).execute()
    return {"headline_id": hid, "criada": True}


def test_escolher_primeira_vez_reivindica_salva_a_headline_e_responde_202(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.rpc.results["cs_chat_proposta_reivindicar"] = _claimed(pid, cid)
    ch.rpc.results["cs_chat_proposta_salvar_headline"] = lambda: _simular_headline_salva(ch, cid, pid)
    r = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid})
    assert r.status_code == 202, r.text
    # the saga's order: claim -> headline -> (pre-flight passed, lease NOT given back) -> steps 4-7 (RP-3)
    assert ch.rpc.names()[:2] == ["cs_chat_proposta_reivindicar", "cs_chat_proposta_salvar_headline"]
    assert "cs_chat_proposta_liberar" not in ch.rpc.names()
    assert ch.rpc.last("cs_chat_proposta_reivindicar") == {
        "p_proposta": pid, "p_org": TEST_ORG_ID, "p_conversa": cid, "p_user": TEST_USER_ID, "p_lease_s": 60}
    assert ch.rpc.last("cs_chat_proposta_salvar_headline") == {"p_proposta": pid, "p_org": TEST_ORG_ID, "p_user": TEST_USER_ID}
    d = r.json()["data"]
    assert set(d) == {"proposta", "fluxo", "mensagem_id", "ja_existia", "em_andamento"}
    assert d["ja_existia"] is False and d["em_andamento"] is False
    assert d["proposta"]["id"] == pid and d["proposta"]["status"] == "escolhida" and d["proposta"]["headline_id"]
    f = d["fluxo"]
    # the continuation ran (RP-3): step 4 created the roteiro. This file's RpcStub does not model the later RPCs;
    # steps 5-7 with their real RPC model are pinned in test_fluxo_saga.py.
    assert f["roteiro"] is not None and "cs_chat_fluxo_registrar" in ch.rpc.names()
    assert f["headline"] == {"id": d["proposta"]["headline_id"], "texto": "Headline um"}


def test_duplo_clique_perde_o_claim_e_recebe_o_estado_atual_sem_segunda_headline(ch):
    cid, mid, pid = _proposta_para_escolher(ch, status="escolhida", fluxo_etapa="headline_salva")
    ch.rpc.results["cs_chat_proposta_reivindicar"] = {
        "claimed": False, "proposta": {"id": pid, "status": "escolhida", "fluxo_etapa": "headline_salva"}}
    r = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["ja_existia"] is True and d["em_andamento"] is True
    assert ch.rpc.names() == ["cs_chat_proposta_reivindicar"]  # no headline, no pre-flight, no lease change
    assert d["fluxo"]["etapa"] == "headline_salva"


def test_fluxo_ja_concluido_responde_200_ja_existia_e_nao_em_andamento(ch):
    cid, mid, pid = _proposta_para_escolher(ch, status="escolhida", fluxo_etapa="concluido")
    ch.rpc.results["cs_chat_proposta_reivindicar"] = {
        "claimed": False, "proposta": {"id": pid, "status": "escolhida", "fluxo_etapa": "concluido"}}
    d = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid}).json()["data"]
    assert d["ja_existia"] is True and d["em_andamento"] is False


def test_escolher_uma_headline_ja_salva_sintetiza_a_proposta_antes_do_claim(ch):
    cid = _conversa(ch)
    mid = _mensagem(ch, cid)
    pid = _proposta(ch, cid, mid, texto="Headline salva", estruturas=())
    ch.db.from_("cs_headlines").insert({"id": HEADLINE_SALVA, "org_id": TEST_ORG_ID, "marca_id": MARCA, "texto": "Headline salva"}).execute()
    ch.rpc.results["cs_chat_proposta_sintetizar"] = {"proposta_id": pid, "sintetizada": True}
    ch.rpc.results["cs_chat_proposta_reivindicar"] = _claimed(pid, cid)

    def salvar():  # what the SQL does: the synthesized proposta points at the saved headline
        ch.db.from_("cs_chat_propostas").update(
            {"status": "escolhida", "headline_id": HEADLINE_SALVA, "fluxo_etapa": "headline_salva"}).eq("id", pid).execute()
        return {"headline_id": HEADLINE_SALVA, "criada": False}

    ch.rpc.results["cs_chat_proposta_salvar_headline"] = salvar
    r = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"headline_id": HEADLINE_SALVA})
    assert r.status_code == 202, r.text
    assert ch.rpc.names()[:3] == ["cs_chat_proposta_sintetizar", "cs_chat_proposta_reivindicar", "cs_chat_proposta_salvar_headline"]
    assert ch.rpc.last("cs_chat_proposta_sintetizar") == {
        "p_org": TEST_ORG_ID, "p_user": TEST_USER_ID, "p_conversa": cid, "p_headline": HEADLINE_SALVA}
    assert ch.rpc.last("cs_chat_proposta_reivindicar")["p_proposta"] == pid
    assert r.json()["data"]["proposta"]["estruturas"] == []  # no Estrutura link for a headline mentioned with @


@pytest.mark.parametrize("body", [
    {}, {"proposta_id": str(uuid.uuid4()), "headline_id": str(uuid.uuid4())}, {"proposta_id": "nao-e-uuid"},
    {"proposta_id": str(uuid.uuid4()), "duracao": "1"},  # the defaults are fixed: nothing else is accepted
    {"proposta_id": str(uuid.uuid4()), "estrutura": "cta_fim"},
])
def test_escolher_exige_exatamente_um_id_e_nenhum_outro_campo(ch, body):
    cid = _conversa(ch)
    assert ch.client.post(f"{BASE}/conversas/{cid}/escolher", json=body).status_code == 422
    assert ch.rpc.calls == []


def test_escolher_em_conversa_alheia_ou_inexistente_e_404_antes_de_qualquer_rpc(ch):
    alheia = _conversa(ch, user=OUTRO_USUARIO)
    for cid in (alheia, str(uuid.uuid4())):
        r = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": str(uuid.uuid4())})
        assert r.status_code == 404
        assert r.json()["code"] == "proposta_nao_encontrada"
    assert ch.rpc.calls == []


@pytest.mark.parametrize("mensagem_rpc", ["proposta_nao_encontrada", "headline_nao_encontrada", "conversa_nao_encontrada"])
def test_proposta_ou_headline_de_outro_usuario_org_ou_conversa_e_404_codificado(ch, mensagem_rpc):
    cid = _conversa(ch)
    nome = "cs_chat_proposta_sintetizar" if mensagem_rpc == "headline_nao_encontrada" else "cs_chat_proposta_reivindicar"
    ch.rpc.errors[nome] = FakeApiError(mensagem_rpc)
    body = {"headline_id": str(uuid.uuid4())} if nome == "cs_chat_proposta_sintetizar" else {"proposta_id": str(uuid.uuid4())}
    r = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json=body)
    assert r.status_code == 404 and r.json()["code"] == "proposta_nao_encontrada"
    assert r.json()["detail"] == "Headline não encontrada."


def _recusa(ch, cid, pid):
    ch.rpc.results["cs_chat_proposta_reivindicar"] = _claimed(pid, cid)
    ch.rpc.results["cs_chat_proposta_salvar_headline"] = lambda: _simular_headline_salva(ch, cid, pid)
    return ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid})


def _assert_headline_salva_e_lease_devolvida(ch, pid, codigo):
    # the headline stays saved, nothing after the pre-flight ran, and the lease went back with the refusal code
    assert ch.rpc.names() == ["cs_chat_proposta_reivindicar", "cs_chat_proposta_salvar_headline", "cs_chat_proposta_liberar"]
    assert ch.rpc.last("cs_chat_proposta_liberar") == {
        "p_proposta": pid, "p_org": TEST_ORG_ID, "p_user": TEST_USER_ID, "p_erro": codigo}
    assert len(ch.rows("cs_headlines")) == 1


def test_preflight_worker_desligado_e_503_geracao_indisponivel_com_a_headline_salva(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.cfg.geracao_worker_enabled = False
    r = _recusa(ch, cid, pid)
    assert r.status_code == 503 and r.json()["code"] == "geracao_indisponivel"
    _assert_headline_salva_e_lease_devolvida(ch, pid, "geracao_indisponivel")


def test_preflight_sem_chave_de_ia_e_503_ia_nao_configurada(ch):
    cid, mid, pid = _proposta_para_escolher(ch)

    def sem_chave(org_id):
        raise RoteiroError(503, {"code": "ia_nao_configurada", "detail": "A IA não está configurada para esta conta."})

    ch.ia = sem_chave
    r = _recusa(ch, cid, pid)
    assert r.status_code == 503 and r.json()["code"] == "ia_nao_configurada"
    assert r.json()["detail"] == "A IA não está configurada para esta conta."
    _assert_headline_salva_e_lease_devolvida(ch, pid, "ia_nao_configurada")


def test_preflight_orcamento_estourado_e_503_orcamento_ia_excedido(ch):
    cid, mid, pid = _proposta_para_escolher(ch)

    async def estourado(org_id):
        raise HTTPException(503, {"code": "orcamento_ia_excedido", "detail": "O orçamento de IA da organização foi excedido."})

    ch.orcamento = estourado
    r = _recusa(ch, cid, pid)
    assert r.status_code == 503 and r.json()["code"] == "orcamento_ia_excedido"
    _assert_headline_salva_e_lease_devolvida(ch, pid, "orcamento_ia_excedido")


def test_preflight_limite_diario_de_roteiros_e_429_com_retry_after(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.cfg.roteiros_dia_usuario = 2
    for i in range(2):  # this user's roteiros inside the rolling window ...
        ch.db.from_("cs_roteiros").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA,
                                           "created_by": TEST_USER_ID, "created_at": _agora(-5)}).execute()
    # ... while another user's, an old one and another org's do not count
    ch.db.from_("cs_roteiros").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA,
                                       "created_by": OUTRO_USUARIO, "created_at": _agora(-5)}).execute()
    ch.db.from_("cs_roteiros").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA,
                                       "created_by": TEST_USER_ID, "created_at": _agora(-60 * 30)}).execute()
    r = _recusa(ch, cid, pid)
    assert r.status_code == 429 and r.json()["code"] == "limite_diario_roteiros"
    assert r.headers["Retry-After"] == "3600"
    _assert_headline_salva_e_lease_devolvida(ch, pid, "limite_diario_roteiros")


def test_abaixo_do_limite_o_preflight_passa(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.cfg.roteiros_dia_usuario = 2
    ch.db.from_("cs_roteiros").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA,
                                       "created_by": TEST_USER_ID, "created_at": _agora(-5)}).execute()
    assert _recusa(ch, cid, pid).status_code == 202


def test_um_erro_nao_codificado_do_rpc_nao_e_engolido(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.rpc.errors["cs_chat_proposta_reivindicar"] = RuntimeError("conexão perdida")
    with pytest.raises(RuntimeError, match="conexão perdida"):
        ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid})


def test_a_continuacao_da_uni_1b_roda_depois_do_preflight_segurando_o_lease_e_nunca_apos_uma_recusa(ch):
    """The UNI-1b seam: steps 4-7 plug in as ``FluxoService.continuacao``; this slice leaves it ``None`` and says so."""
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.rpc.results["cs_chat_proposta_reivindicar"] = _claimed(pid, cid)
    ch.rpc.results["cs_chat_proposta_salvar_headline"] = lambda: _simular_headline_salva(ch, cid, pid)
    vistas = []

    async def continuacao(proposta):
        vistas.append(proposta["id"])

    svc = FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID, cfg=ch.cfg, ia_check=_ia_ok, orcamento=_orcamento_ok, continuacao=continuacao)
    res = asyncio.run(svc.escolher(cid, proposta_id=pid))
    assert vistas == [pid] and res.ja_existia is False
    assert "cs_chat_proposta_liberar" not in ch.rpc.names()  # the continuation owns the lease from here
    assert FluxoService(ch.db, TEST_ORG_ID, TEST_USER_ID).continuacao is None
    # a refused pre-flight never reaches it
    ch.cfg.geracao_worker_enabled = False
    vistas.clear()
    with pytest.raises(HTTPException):
        asyncio.run(svc.escolher(cid, proposta_id=pid))
    assert vistas == [] and ch.rpc.names()[-1] == "cs_chat_proposta_liberar"


def test_a_resposta_do_escolher_nao_vaza_campos_internos(ch):
    cid, mid, pid = _proposta_para_escolher(ch)
    ch.rpc.results["cs_chat_proposta_reivindicar"] = _claimed(pid, cid)
    ch.rpc.results["cs_chat_proposta_salvar_headline"] = lambda: _simular_headline_salva(ch, cid, pid)
    corpo = ch.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid}).text
    for campo in ("org_id", "user_id", "fluxo_lease_ate", "escolhida_por", "created_by", "marca_id"):
        assert campo not in corpo


# ── the prompt ────────────────────────────────────────────────────────────────────────────────────────────


def test_o_prompt_unificado_carrega_o_contrato_de_citacao_e_de_mistura():
    p = chat_unificado.SYSTEM_PROMPT
    assert chat_unificado.PROMPT_VERSAO == "chat-unificado-v2-draft"
    assert "(estrutura #<código>)" in p and "(estrutura #<código> + #<código>)" in p
    assert "MÁXIMO 3" in p and chat_unificado.MAX_CITACOES == 3
    assert "### Estruturas usadas" in p and "### Análise da Estrutura Escolhida" in p
    assert "mesmo formato" in p and "NUNCA deixe um [espaço] entre colchetes" in p
    assert "NÃO escreve o roteiro" not in p and "o roteiro é escrito quando" not in p
    assert "<material" in p and "nunca instrução" in p  # the prompt-injection fence is kept
    assert "{MAX_CITACOES}" not in p and "{METODO" not in p


def test_agente_unificado_e_a_unica_resposta_de_leitura():
    assert AGENTE_UNIFICADO == "unificado"
    for legado in ("headline", "roteiro", "unificado", "qualquer"):
        assert chat_service.conversa_out({"id": "1", "marca_id": "m", "agente": legado, "titulo": "t", "last_message_at": "x"})["agente"] == "unificado"
