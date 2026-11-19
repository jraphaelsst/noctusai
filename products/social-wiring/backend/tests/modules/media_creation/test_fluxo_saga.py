"""RP-3 -- the chat saga's steps 4-7 in BOTH directions (``estruturas-contract.md`` 9.2-9.3, 16.6) + minimal EST-RO.

Mounted through the real ``register()`` seam on the MockSupabaseClient: ``RoteiroService``, ``EsteiraService``,
``LegendaService``, the approvals organ and the job handlers are the production code. The SQL RPCs run on PGlite in
``tests/test_migration_cs_fluxo_saga.py`` / ``test_migration_cs_roteiro_primeiro.py``; here ``SagaRpc`` is a stateful
model of them over the same mock tables (claim + lease, save headline / roteiro, the forward-only registrar with its
once-only event), so the saga's ORDER, its idempotency and its crash-resume are pinned end to end. Crashes are injected
at the DI seams (the RPC transport and the queue), never by patching our own code.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from noctusai_lib.domain._organ_common import make_org_table_store
from noctusai_lib.domain.approvals import ApprovalStore, FakeApprovalLedger, table_specs
from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.testing import TEST_ORG_ID, TEST_USER_ID

from app.modules.media_creation.routers import chat as chat_router
from app.modules.media_creation.services import fluxo_finalizar as fin
from app.modules.media_creation.services import roteiro_aprovacao as apr
from app.modules.media_creation.services.chat_service import liberar_stream
from app.modules.media_creation.services.fluxo_continuacao import MSG_HEADLINE_PRIMEIRO, MSG_ROTEIRO_PRIMEIRO
from app.modules.media_creation.services.fluxo_service import get_fluxo_orcamento, get_fluxo_settings
from app.modules.media_creation.services.roteiro_service import (
    RoteiroError,
    RoteiroService,
    executar_geracao,
    get_roteiro_ia_check,
)
from app.modules.media_creation.schemas.roteiros import RoteiroCreate

BASE = "/api/media-creation/chat"
MARCA = str(uuid.uuid4())
PERFIL = str(uuid.uuid4())
E1, E2, E3, E_REELS, E_INATIVA = (str(uuid.uuid4()) for _ in range(5))
TIPO_BLOCO = str(uuid.uuid4())
BLOCO_GANCHO = str(uuid.uuid4())
HEADLINE_OK = "O erro que ninguém te conta"
LEGENDA_JSON = '{"legenda": "Legenda pronta para o card.", "hashtags": []}'


def _agora(minutos: float = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutos)).isoformat()


# ── doubles at the seams ─────────────────────────────────────────────────────────────────────────────────


class FakeApiError(Exception):
    def __init__(self, message: str):
        super().__init__({"message": message, "details": "", "code": "P0001"})
        self.message, self.details, self.code = message, "", "P0001"


class _Exec:
    def __init__(self, data=None, exc=None):
        self.data, self._exc = data, exc

    count = None

    def execute(self):
        if self._exc:
            raise self._exc
        return self


class Crash(RuntimeError):
    """A process dying mid-saga (the transport / queue raised): nothing after it ran."""


RANK = {None: 0, "headline_salva": 1, "roteiro_salvo": 1, "roteiro_criado": 2, "headline_gerada": 2, "card_criado": 3,
        "concluido": 4}


class SagaRpc:
    """A model of the definer RPCs of migrations 352/358/cs_fluxo_saga over the mock tables (PGlite pins the SQL)."""

    def __init__(self, db):
        self.db = db
        self.calls: list[tuple[str, dict]] = []
        self.crashes: list[tuple[str, object]] = []  # (rpc name, predicate(params) | None): raise ONCE before running
        self._seq = 0

    def crash_once(self, nome, quando=None):
        self.crashes.append((nome, quando))

    def __call__(self, name, params=None):
        params = dict(params or {})
        self.calls.append((name, params))
        for i, (nome, quando) in enumerate(self.crashes):
            if nome == name and (quando is None or quando(params)):
                del self.crashes[i]
                return _Exec(exc=Crash(f"crash em {name}"))
        try:
            return _Exec(data=getattr(self, name)(**params))
        except FakeApiError as exc:
            return _Exec(exc=exc)

    def names(self):
        return [n for n, _ in self.calls]

    # helpers
    def _p(self, pid):
        rows = self.db.from_("cs_chat_propostas").select("*").eq("id", pid).execute().data
        return rows[0] if rows else None

    def _upd(self, pid, patch):
        self.db.from_("cs_chat_propostas").update(patch).eq("id", pid).execute()
        return self._p(pid)

    def _evento(self, p, tipo, **kw):
        self._seq += 1
        self.db.from_("cs_fluxo_eventos").insert({
            "id": str(uuid.uuid4()), "org_id": p["org_id"], "marca_id": p["marca_id"], "conversa_id": p["conversa_id"],
            "proposta_id": p["id"], "tipo": tipo, "created_at": (datetime(2026, 1, 1, tzinfo=timezone.utc)
                                                                + timedelta(seconds=self._seq)).isoformat(), **kw}).execute()

    def _usos(self, p, **link):
        ests = sorted(self.db.from_("cs_chat_proposta_estruturas").select("*").eq("proposta_id", p["id"]).execute().data,
                      key=lambda r: r["ordem"])
        for e in ests:
            self.db.from_("cs_estrutura_usos").insert({
                "id": str(uuid.uuid4()), "org_id": p["org_id"], "marca_id": p["marca_id"], "estrutura_id": e["estrutura_id"],
                "contexto": "chat", "papel": "principal" if e["principal"] else "mistura", "ordem": e["ordem"],
                "proposta_id": p["id"], **link}).execute()

    # 352
    def cs_chat_proposta_reivindicar(self, p_proposta, p_org, p_conversa, p_user, p_lease_s):
        p = self._p(p_proposta)
        if p is None or p["org_id"] != p_org or p["conversa_id"] != p_conversa:
            raise FakeApiError("proposta_nao_encontrada")
        lease = p.get("fluxo_lease_ate")
        livre = lease is None or datetime.fromisoformat(lease) < datetime.now(timezone.utc)
        if not (p["status"] == "proposta" or (p.get("fluxo_etapa") != "concluido" and livre)):
            return {"claimed": False, "proposta": p}
        antes = p["status"]
        p = self._upd(p_proposta, {"status": "escolhida", "escolhida_por": p.get("escolhida_por") or p_user,
                                   "fluxo_lease_ate": _agora(p_lease_s / 60)})
        self._evento(p, "proposta_escolhida" if antes == "proposta" else "fluxo_retomado", ator_id=p_user)
        return {"claimed": True, "proposta": p}

    def cs_chat_proposta_liberar(self, p_proposta, p_org, p_user, p_erro):
        self._upd(p_proposta, {"fluxo_lease_ate": None, "fluxo_erro_codigo": p_erro})
        return {"liberada": True}

    # 358
    def cs_chat_proposta_salvar_headline(self, p_proposta, p_org, p_user, p_texto=None):
        p = self._p(p_proposta)
        if p.get("headline_id"):
            return {"headline_id": p["headline_id"], "criada": False}
        roteiro = (p.get("tipo") or "headline") == "roteiro"
        if roteiro and not p.get("roteiro_id"):
            raise FakeApiError("roteiro_nao_salvo")
        if roteiro and not (p_texto or "").strip():
            raise FakeApiError("headline_texto_ausente")
        hid = str(uuid.uuid4())
        self.db.from_("cs_headlines").insert({
            "id": hid, "org_id": p_org, "marca_id": p["marca_id"], "texto": (p_texto or p["texto"]).strip(),
            "modo": "do_roteiro" if roteiro else "manual", "favorita": True, "conversa_id": p["conversa_id"],
            "proposta_id": p["id"], "created_by": p_user, "created_at": _agora()}).execute()
        if roteiro:
            self.db.from_("cs_roteiros").update({"headline_id": hid, "headline_texto": p_texto.strip()}).eq("id", p["roteiro_id"]).execute()
            etapa = "headline_gerada" if RANK.get(p.get("fluxo_etapa"), -1) < 2 else p["fluxo_etapa"]
            p = self._upd(p_proposta, {"headline_id": hid, "fluxo_etapa": etapa, "fluxo_erro_codigo": None})
            self._evento(p, "headline_gerada", headline_id=hid, roteiro_id=p["roteiro_id"])
        else:
            p = self._upd(p_proposta, {"headline_id": hid, "fluxo_etapa": p.get("fluxo_etapa") or "headline_salva"})
            self._usos(p, headline_id=hid)
            self._evento(p, "headline_salva", headline_id=hid)
        return {"headline_id": hid, "criada": True}

    def cs_chat_proposta_salvar_roteiro(self, p_proposta, p_org, p_user):
        p = self._p(p_proposta)
        if (p.get("tipo") or "headline") != "roteiro":
            raise FakeApiError("proposta_nao_e_roteiro")
        if p.get("roteiro_id"):
            return {"roteiro_id": p["roteiro_id"], "criado": False}
        rid = str(uuid.uuid4())
        self.db.from_("cs_roteiros").insert({
            "id": rid, "org_id": p_org, "marca_id": p["marca_id"], "nome": p["titulo"], "headline_texto": p["titulo"],
            "status": "completo", "conteudo": p["texto"], "formato": p["formato"], "conversa_id": p["conversa_id"],
            "proposta_id": p["id"], "created_by": p_user, "versao": 1, "fonte": "ia", "created_at": _agora()}).execute()
        p = self._upd(p_proposta, {"roteiro_id": rid, "fluxo_etapa": p.get("fluxo_etapa") or "roteiro_salvo"})
        self._usos(p, roteiro_id=rid)
        self._evento(p, "roteiro_salvo", roteiro_id=rid)
        return {"roteiro_id": rid, "criado": True}

    # cs_fluxo_saga
    def cs_chat_fluxo_registrar(self, p_proposta, p_org, p_user, p_tipo, p_etapa, p_erro, p_headline, p_roteiro, p_post, p_codigo):
        p = self._p(p_proposta)
        if p is None or p["org_id"] != p_org:
            raise FakeApiError("proposta_nao_encontrada")
        atual, mudou = p.get("fluxo_etapa"), False
        if atual != "concluido" and p_etapa:
            if p_etapa == "falhou":
                if atual != "falhou":
                    self._upd(p_proposta, {"fluxo_etapa": "falhou", "fluxo_erro_codigo": p_erro})
                    mudou = True
            elif atual == "falhou" or RANK[p_etapa] > RANK.get(atual, 0):
                self._upd(p_proposta, {"fluxo_etapa": p_etapa, "fluxo_erro_codigo": None})
                mudou = True
        existe = any(
            (e.get("codigo") or "") == (p_codigo or "")
            for e in self.db.from_("cs_fluxo_eventos").select("*").eq("proposta_id", p_proposta).eq("tipo", p_tipo).execute().data
        )
        if mudou or not existe:
            self._evento(p, p_tipo, headline_id=p_headline or p.get("headline_id"), roteiro_id=p_roteiro or p.get("roteiro_id"),
                         post_id=p_post, ator_id=p_user, codigo=p_codigo)
        return {"etapa": self._p(p_proposta)["fluxo_etapa"], "mudou": mudou, "registrado": mudou or not existe}

    # 241 (the Esteira's atomic rebind)
    def cs_rebind_roteiro(self, p_org, p_post, p_old, p_new):
        self.db.from_("cs_posts").update({"roteiro_id": p_new}).eq("id", p_post).execute()
        return True


class Jobs(FakeJobRepository):
    """The seed's Fake queue + a record of every enqueue and a one-shot crash."""

    def __init__(self):
        super().__init__()
        self.enfileirados: dict[str, object] = {}
        self.crash_tipo: str | None = None

    async def enqueue(self, **kw):
        if self.crash_tipo and kw["type"] == self.crash_tipo:
            self.crash_tipo = None
            raise Crash(f"crash ao enfileirar {kw['type']}")
        job = await super().enqueue(**kw)
        self.enfileirados[job.id] = job
        return job

    def do_tipo(self, tipo):
        return [j for j in self.enfileirados.values() if j.type == tipo]


class Llm:
    def __init__(self, *respostas):
        self.respostas, self.calls = list(respostas), 0

    async def __call__(self, system, user, org_id):
        self.calls += 1
        return self.respostas[min(self.calls - 1, len(self.respostas) - 1)]


async def _ok(org_id):
    return None


class Saga:
    def __init__(self, client):
        self.client = client
        self.db = client.mock_supabase
        self.rpc = SagaRpc(self.db)
        self.db.rpc = self.rpc
        self.jobs = Jobs()
        self.cfg = SimpleNamespace(
            roteiros_dia_usuario=20, headline_lotes_dia_usuario=30, legendas_dia_usuario=40, geracao_worker_enabled=True,
            geracao_llm_model="claude-test")
        tables = make_org_table_store(table_specs(apr.CFG), supabase_client=self.db)
        self.store = ApprovalStore(tables, FakeApprovalLedger(tables))
        ov = client._tc.app.dependency_overrides
        ov[get_fluxo_settings] = lambda: self.cfg
        ov[get_roteiro_ia_check] = lambda: (lambda org_id: None)
        ov[get_fluxo_orcamento] = lambda: _ok
        ov[chat_router.get_fluxo_jobs] = lambda: self.jobs
        ov[chat_router.get_fluxo_approvals] = lambda: self.approvals()

    def approvals(self):
        return apr.make_approvals(self.db, store=self.store)

    def rows(self, tabela, **eq):
        q = self.db.from_(tabela).select("*")
        for k, v in eq.items():
            q = q.eq(k, v)
        return q.execute().data

    def proposta(self, pid):
        return self.rows("cs_chat_propostas", id=pid)[0]

    def eventos(self, tipo, pid):
        return [e for e in self.rows("cs_fluxo_eventos", proposta_id=pid) if e["tipo"] == tipo]

    def escolher(self, cid, pid):
        return self.client.post(f"{BASE}/conversas/{cid}/escolher", json={"proposta_id": pid})

    def expirar_lease(self, pid):
        self.db.from_("cs_chat_propostas").update({"fluxo_lease_ate": _agora(-5)}).eq("id", pid).execute()

    async def rodar(self, tipo, llm, *, agora=None):
        job = self.jobs.do_tipo(tipo)[-1]
        if tipo == "fluxo.finalizar_card":
            kw = {"agora": agora} if agora else {}
            await fin.executar_finalizar(job, db=self.db, llm=llm, cfg=self.cfg, ia_check=lambda o: None, orcamento=_ok,
                                         approvals=self.approvals(), **kw)
        else:
            await fin.executar_headline(job, db=self.db, llm=llm, jobs=self.jobs)
        return job


@pytest.fixture
def sg(client):
    s = Saga(client)
    db = s.db
    db.from_("marcas").insert({"id": MARCA, "org_id": TEST_ORG_ID, "name": "Marca A"}).execute()
    db.from_("cs_perfis_monitorados").insert({"id": PERFIL, "org_id": TEST_ORG_ID, "handle": "perfil", "nome": "Perfil"}).execute()
    for eid, codigo, formato, status in ((E1, 101, "carrossel", "ativa"), (E2, 102, "carrossel", "ativa"),
                                         (E3, 103, "carrossel", "ativa"), (E_REELS, 104, "reels", "ativa"),
                                         (E_INATIVA, 105, "carrossel", "rascunho")):
        db.from_("cs_estruturas").insert({"id": eid, "codigo": codigo, "perfil_id": PERFIL, "formula_headline": f"Fórmula {codigo}",
                                          "formato": formato, "status": status}).execute()
    db.from_("cs_estrutura_tipos_bloco").insert({"id": TIPO_BLOCO, "nome": "Gancho"}).execute()
    db.from_("cs_estrutura_blocos").insert({"id": BLOCO_GANCHO, "estrutura_id": E1, "ordem": 1, "tipo_id": TIPO_BLOCO,
                                            "nome": "Gancho forte"}).execute()
    liberar_stream(TEST_USER_ID)
    yield s
    liberar_stream(TEST_USER_ID)


def _conversa(s) -> str:
    cid = str(uuid.uuid4())
    s.db.from_("cs_chat_conversas").insert({"id": cid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "user_id": TEST_USER_ID,
                                            "agente": "unificado", "titulo": "C", "last_message_at": _agora()}).execute()
    return cid


ROTEIRO_TEXTO = "**Slide 1 — Gancho**\nVocê erra isso.\n**Slide 2 — Virada**\nFaça assim."


def _proposta(s, *, tipo="headline", estruturas=((E1, True), (E2, False))):
    cid = _conversa(s)
    mid = str(uuid.uuid4())
    s.db.from_("cs_chat_mensagens").insert({"id": mid, "org_id": TEST_ORG_ID, "conversa_id": cid, "role": "assistant",
                                            "conteudo": "x", "referencias": [], "status": "completa", "truncada": False,
                                            "created_at": _agora()}).execute()
    pid = str(uuid.uuid4())
    extra = ({"tipo": "roteiro", "titulo": "O erro que custa caro", "formato": "carrossel", "texto": ROTEIRO_TEXTO}
             if tipo == "roteiro" else {"tipo": "headline", "texto": "Você erra isso no consultório"})
    s.db.from_("cs_chat_propostas").insert({
        "id": pid, "org_id": TEST_ORG_ID, "marca_id": MARCA, "conversa_id": cid, "mensagem_id": mid, "ordem": 1,
        "gatilho_tag": None, "status": "proposta", "fluxo_etapa": None, "fluxo_erro_codigo": None, "fluxo_lease_ate": None,
        "headline_id": None, "roteiro_id": None, "created_at": _agora(), **extra}).execute()
    for i, (eid, principal) in enumerate(estruturas, start=1):
        s.db.from_("cs_chat_proposta_estruturas").insert({"proposta_id": pid, "estrutura_id": eid, "ordem": i,
                                                          "principal": principal}).execute()
    return cid, pid


def _completar_roteiro(s, rid, conteudo=ROTEIRO_TEXTO):
    s.db.from_("cs_roteiros").update({"status": "completo", "conteudo": conteudo}).eq("id", rid).execute()


def _sem_duplicatas(s, pid):
    """Exactly one of everything the saga creates, whatever the crash history."""
    p = s.proposta(pid)
    roteiros = [r for r in s.rows("cs_roteiros") if r.get("conversa_id") == p["conversa_id"]]
    assert len(roteiros) == 1
    assert len([x for x in s.rows("cs_posts") if x.get("roteiro_id") == roteiros[0]["id"]]) == 1
    assert len(s.rows("cs_posts")) == 1
    assert len(s.rows("cs_headlines", proposta_id=pid)) == 1
    assert len(s.jobs.do_tipo("fluxo.finalizar_card")) == 1
    assert len(s.rows("cs_chat_mensagens", proposta_id=pid)) == 1
    for tipo in ("card_criado",):
        assert len(s.eventos(tipo, pid)) == 1, tipo
    return roteiros[0]


# ── headline-first ──────────────────────────────────────────────────────────────────────────────────────


def test_headline_primeiro_caminho_feliz_roteiro_card_finalizador_mensagem_e_legenda(sg):
    cid, pid = _proposta(sg)
    r = sg.escolher(cid, pid)
    assert r.status_code == 202, r.text
    f = r.json()["data"]["fluxo"]
    assert f["direcao"] == "headline_primeiro" and f["etapa"] == "roteiro_gerando"
    assert f["roteiro"]["formato"] == "carrossel" and f["post"] is not None
    # step 4: the roteiro through RoteiroService (formato from the principal Estrutura, the cited Estruturas, the chat)
    roteiro = _sem_duplicatas(sg, pid)
    assert roteiro["formato"] == "carrossel" and roteiro["estrutura_ids"] == [E1, E2]
    assert roteiro["conversa_id"] == cid and roteiro["headline_id"] == sg.proposta(pid)["headline_id"]
    assert [j.dedupe_key for j in sg.jobs.do_tipo("roteiro.gerar")] == [f"roteiro.gerar:{roteiro['id']}"]
    # step 5: the card, formato mapped to the cs_posts vocabulary, title = the headline, bound to the roteiro
    post = sg.rows("cs_posts")[0]
    assert post["formato"] == "carrossel" and post["titulo"] == "Você erra isso no consultório"
    assert post["roteiro_id"] == roteiro["id"] and post["headline_id"] == sg.proposta(pid)["headline_id"]
    # step 6 + 7
    assert [j.dedupe_key for j in sg.jobs.do_tipo("fluxo.finalizar_card")] == [f"fluxo:{pid}"]
    msg = sg.rows("cs_chat_mensagens", proposta_id=pid)[0]
    assert msg["tipo"] == "roteiro_gerado" and msg["role"] == "assistant" and msg["conteudo"] == MSG_HEADLINE_PRIMEIRO
    assert r.json()["data"]["mensagem_id"] == msg["id"]
    assert sg.proposta(pid)["fluxo_etapa"] == "card_criado"
    assert [len(sg.eventos(t, pid)) for t in ("roteiro_criado", "card_criado")] == [1, 1]

    # the finalizer: pending -> reschedule; completo -> approval submitted, caption saved, concluido
    with pytest.raises(RescheduleLater):
        asyncio.run(sg.rodar("fluxo.finalizar_card", Llm(LEGENDA_JSON)))
    _completar_roteiro(sg, roteiro["id"])
    llm = Llm(LEGENDA_JSON)
    asyncio.run(sg.rodar("fluxo.finalizar_card", llm))
    post = sg.rows("cs_posts")[0]
    assert post["legenda"] == "Legenda pronta para o card." and llm.calls == 1
    gerada = sg.eventos("legenda_gerada", pid)
    assert len(gerada) == 1 and gerada[0]["codigo"] == hashlib.sha256(post["legenda"].encode()).hexdigest()
    assert [len(sg.eventos(t, pid)) for t in ("roteiro_gerado", "fluxo_concluido")] == [1, 1]
    assert sg.proposta(pid)["fluxo_etapa"] == "concluido"
    assert apr.make_approvals(sg.db, store=sg.store).state(TEST_ORG_ID, "roteiro", roteiro["id"]).status == "pending"
    # a later click: the flow exists and is finished
    d = sg.escolher(cid, pid).json()["data"]
    assert d["ja_existia"] is True and d["em_andamento"] is False


def test_duplo_clique_durante_o_fluxo_e_ja_existia_sem_segundo_roteiro(sg):
    cid, pid = _proposta(sg)
    assert sg.escolher(cid, pid).status_code == 202
    r = sg.escolher(cid, pid)  # the lease is held
    assert r.status_code == 200 and r.json()["data"]["ja_existia"] is True
    _sem_duplicatas(sg, pid)


@pytest.mark.parametrize("ponto", [
    "registrar:roteiro_criado",   # after RoteiroService.create, before step 4 is recorded
    "rpc:cs_rebind_roteiro",      # after the card insert, before it is bound to the roteiro
    "registrar:card_criado",      # after the card is bound, before step 5 is recorded
    "fila:fluxo.finalizar_card",  # step 6 never enqueued
])
def test_headline_primeiro_crash_em_cada_passo_e_retomado_pelo_proximo_clique_sem_duplicatas(sg, ponto):
    cid, pid = _proposta(sg)
    tipo, alvo = ponto.split(":")
    if tipo == "registrar":
        sg.rpc.crash_once("cs_chat_fluxo_registrar", lambda p: p["p_tipo"] == alvo)
    elif tipo == "rpc":
        sg.rpc.crash_once(alvo)
    else:
        sg.jobs.crash_tipo = alvo
    with pytest.raises(Crash):
        sg.escolher(cid, pid)
    sg.expirar_lease(pid)
    r = sg.escolher(cid, pid)
    assert r.status_code == 202, r.text
    assert r.json()["data"]["fluxo"]["etapa"] == "roteiro_gerando"
    roteiro = _sem_duplicatas(sg, pid)
    assert len(sg.jobs.do_tipo("roteiro.gerar")) == 1
    assert len(sg.eventos("roteiro_criado", pid)) == 1
    assert len(sg.eventos("fluxo_retomado", pid)) == 1
    assert sg.rows("cs_posts")[0]["roteiro_id"] == roteiro["id"]


def test_a_mensagem_e_um_card_existentes_sao_adotados_nunca_duplicados(sg):
    cid, pid = _proposta(sg)
    assert sg.escolher(cid, pid).status_code == 202
    from app.modules.media_creation.services.fluxo_continuacao import SagaFluxo

    saga = SagaFluxo(sg.db, TEST_ORG_ID, TEST_USER_ID, jobs=sg.jobs)
    p = saga.proposta(pid)
    roteiro = saga.roteiro_do_fluxo(p)
    for _ in range(2):
        asyncio.run(saga.concluir(p, roteiro))
    _sem_duplicatas(sg, pid)


def test_uma_recusa_do_card_e_registrada_como_falhou_com_o_codigo_e_nao_vira_500(sg):
    """The org's board has only an INACTIVE stage: the Esteira refuses (409 ``sem_etapas``) -- a real refusal from data."""
    from app.modules.media_creation.esteira_config import PIPELINE_ESTEIRA

    sg.db.from_(PIPELINE_ESTEIRA.stages_table).insert({
        "id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "pipeline": "esteira", "slug": "ideia", "label": "Ideia",
        "posicao": 1, "ativo": False}).execute()
    cid, pid = _proposta(sg)
    r = sg.escolher(cid, pid)
    assert r.status_code == 202, r.text
    p = sg.proposta(pid)
    assert p["fluxo_etapa"] == "falhou" and p["fluxo_erro_codigo"] == "sem_etapas"
    assert len(sg.eventos("card_falhou", pid)) == 1 and sg.rows("cs_posts") == []
    assert sg.jobs.do_tipo("fluxo.finalizar_card") == [] and sg.rows("cs_chat_mensagens", proposta_id=pid) == []
    assert len(sg.rows("cs_roteiros")) == 1  # the roteiro stays


# ── roteiro-first ───────────────────────────────────────────────────────────────────────────────────────


def test_roteiro_primeiro_caminho_feliz_headline_card_finalizador_e_mensagem(sg):
    cid, pid = _proposta(sg, tipo="roteiro")
    r = sg.escolher(cid, pid)
    assert r.status_code == 202, r.text
    assert sg.rpc.names()[:3] == ["cs_chat_proposta_reivindicar", "cs_chat_proposta_salvar_roteiro", "cs_chat_fluxo_registrar"]
    assert "cs_chat_proposta_salvar_headline" not in sg.rpc.names()
    f = r.json()["data"]["fluxo"]
    assert f["direcao"] == "roteiro_primeiro" and f["etapa"] == "headline_gerando" and f["headline"] is None
    assert [j.dedupe_key for j in sg.jobs.do_tipo("fluxo.headline_do_roteiro")] == [f"fluxo-h:{pid}"]
    assert sg.rows("cs_posts") == [] and len(sg.eventos("headline_gerando", pid)) == 1

    llm = Llm(HEADLINE_OK)
    asyncio.run(sg.rodar("fluxo.headline_do_roteiro", llm))
    assert llm.calls == 1
    p = sg.proposta(pid)
    h = sg.rows("cs_headlines", proposta_id=pid)[0]
    assert h["texto"] == HEADLINE_OK and h["modo"] == "do_roteiro" and p["headline_id"] == h["id"]
    post = sg.rows("cs_posts")[0]
    assert post["titulo"] == HEADLINE_OK and post["formato"] == "carrossel" and post["roteiro_id"] == p["roteiro_id"]
    assert sg.rows("cs_chat_mensagens", proposta_id=pid)[0]["conteudo"] == MSG_ROTEIRO_PRIMEIRO
    assert p["fluxo_etapa"] == "card_criado"
    # the roteiro is born completo: the finalizer goes straight to the caption
    asyncio.run(sg.rodar("fluxo.finalizar_card", Llm(LEGENDA_JSON)))
    assert sg.proposta(pid)["fluxo_etapa"] == "concluido" and sg.rows("cs_posts")[0]["legenda"]
    _sem_duplicatas(sg, pid)


def test_roteiro_primeiro_crash_entre_enfileirar_e_registrar_reusa_o_mesmo_job(sg):
    cid, pid = _proposta(sg, tipo="roteiro")
    sg.rpc.crash_once("cs_chat_fluxo_registrar", lambda p: p["p_tipo"] == "headline_gerando")
    with pytest.raises(Crash):
        sg.escolher(cid, pid)
    sg.expirar_lease(pid)
    assert sg.escolher(cid, pid).status_code == 202
    assert len(sg.jobs.do_tipo("fluxo.headline_do_roteiro")) == 1
    assert len(sg.eventos("headline_gerando", pid)) == 1
    assert len(sg.rows("cs_roteiros")) == 1


@pytest.mark.parametrize("ponto", ["registrar:card_criado", "rpc:cs_rebind_roteiro", "fila:fluxo.finalizar_card"])
def test_roteiro_primeiro_crash_no_job_da_headline_e_retomado_pelo_retry_do_job_sem_duplicatas(sg, ponto):
    cid, pid = _proposta(sg, tipo="roteiro")
    assert sg.escolher(cid, pid).status_code == 202
    tipo, alvo = ponto.split(":")
    if tipo == "registrar":
        sg.rpc.crash_once("cs_chat_fluxo_registrar", lambda p: p["p_tipo"] == alvo)
    elif tipo == "rpc":
        sg.rpc.crash_once(alvo)
    else:
        sg.jobs.crash_tipo = alvo
    llm = Llm(HEADLINE_OK)
    with pytest.raises(Crash):
        asyncio.run(sg.rodar("fluxo.headline_do_roteiro", llm))
    asyncio.run(sg.rodar("fluxo.headline_do_roteiro", llm))  # the worker's retry
    assert llm.calls == 1  # the headline was saved before the crash: the retry never asks the model again
    _sem_duplicatas(sg, pid)
    assert sg.proposta(pid)["fluxo_etapa"] == "card_criado"


def test_roteiro_primeiro_um_clique_com_a_headline_ja_salva_retoma_direto_no_card(sg):
    cid, pid = _proposta(sg, tipo="roteiro")
    assert sg.escolher(cid, pid).status_code == 202
    sg.jobs.crash_tipo = "fluxo.finalizar_card"
    with pytest.raises(Crash):
        asyncio.run(sg.rodar("fluxo.headline_do_roteiro", Llm(HEADLINE_OK)))
    sg.expirar_lease(pid)
    r = sg.escolher(cid, pid)
    assert r.status_code == 202 and r.json()["data"]["fluxo"]["etapa"] == "roteiro_pronto"
    assert len(sg.jobs.do_tipo("fluxo.headline_do_roteiro")) == 1
    _sem_duplicatas(sg, pid)


def test_headline_invalida_uma_tentativa_extra_depois_falhou_sem_card_e_o_clique_tenta_de_novo(sg):
    cid, pid = _proposta(sg, tipo="roteiro")
    assert sg.escolher(cid, pid).status_code == 202
    llm = Llm("Uma headline com [placeholder] aqui", " ".join(["palavra"] * 13))
    asyncio.run(sg.rodar("fluxo.headline_do_roteiro", llm))
    assert llm.calls == 2  # the call + ONE retry
    p = sg.proposta(pid)
    assert p["fluxo_etapa"] == "falhou" and p["fluxo_erro_codigo"] == "headline_invalida" and p["headline_id"] is None
    assert len(sg.eventos("headline_falhou", pid)) == 1
    assert sg.rows("cs_posts") == [] and sg.rows("cs_headlines") == []
    assert len(sg.rows("cs_roteiros")) == 1  # the roteiro stays
    assert sg.jobs.do_tipo("fluxo.finalizar_card") == []
    r = sg.client.get(f"{BASE}/conversas/{cid}/mensagens")
    assert r.status_code == 200
    # the same click retries with the NEXT attempt key (the first job is finished; its key is spent forever)
    sg.expirar_lease(pid)
    assert sg.escolher(cid, pid).status_code == 202
    assert [j.dedupe_key for j in sg.jobs.do_tipo("fluxo.headline_do_roteiro")] == [f"fluxo-h:{pid}", f"fluxo-h:{pid}:1"]
    asyncio.run(sg.rodar("fluxo.headline_do_roteiro", Llm(HEADLINE_OK)))
    p = sg.proposta(pid)
    assert p["fluxo_etapa"] == "card_criado" and p["fluxo_erro_codigo"] is None
    _sem_duplicatas(sg, pid)


def test_headline_invalida_e_depois_valida_na_tentativa_extra_segue_o_fluxo(sg):
    cid, pid = _proposta(sg, tipo="roteiro")
    sg.escolher(cid, pid)
    llm = Llm("linha um\nlinha dois", HEADLINE_OK)
    asyncio.run(sg.rodar("fluxo.headline_do_roteiro", llm))
    assert llm.calls == 2 and sg.rows("cs_headlines", proposta_id=pid)[0]["texto"] == HEADLINE_OK
    assert sg.eventos("headline_falhou", pid) == []


@pytest.mark.parametrize("texto,ok", [
    (HEADLINE_OK, True), ('  "Entre aspas e espaços"  ', True), ("", False), ("a\nb", False),
    (" ".join(["p"] * 12), True), (" ".join(["p"] * 13), False), ("Veja [nome] agora", False),
    ("Acesse https://exemplo.com hoje", False), (None, False),
])
def test_o_validador_da_headline(texto, ok):
    assert (fin.validar_headline(texto) is not None) is ok


def test_preflight_do_roteiro_primeiro_e_o_limite_de_headlines_mantem_o_roteiro_e_devolve_o_lease(sg):
    cid, pid = _proposta(sg, tipo="roteiro")
    sg.cfg.headline_lotes_dia_usuario = 1
    sg.db.from_("cs_headlines").insert({"id": str(uuid.uuid4()), "org_id": TEST_ORG_ID, "marca_id": MARCA, "texto": "h",
                                        "modo": "do_roteiro", "created_by": TEST_USER_ID, "created_at": _agora(-5)}).execute()
    sg.cfg.roteiros_dia_usuario = 0  # the roteiro cap does NOT apply to roteiro-first
    r = sg.escolher(cid, pid)
    assert r.status_code == 429 and r.json()["code"] == "limite_diario_headlines"
    assert sg.rpc.names() == ["cs_chat_proposta_reivindicar", "cs_chat_proposta_salvar_roteiro", "cs_chat_proposta_liberar"]
    assert len(sg.rows("cs_roteiros")) == 1 and sg.jobs.enfileirados == {}
    assert sg.proposta(pid)["fluxo_lease_ate"] is None


# ── the finalizer ───────────────────────────────────────────────────────────────────────────────────────


def _ate_o_card(sg):
    cid, pid = _proposta(sg)
    assert sg.escolher(cid, pid).status_code == 202
    return pid, sg.rows("cs_roteiros")[0]


def test_a_legenda_so_e_gravada_quando_o_card_nao_tem_legenda(sg):
    pid, roteiro = _ate_o_card(sg)
    _completar_roteiro(sg, roteiro["id"])
    sg.db.from_("cs_posts").update({"legenda": "Minha legenda"}).eq("id", sg.rows("cs_posts")[0]["id"]).execute()
    llm = Llm(LEGENDA_JSON)
    asyncio.run(sg.rodar("fluxo.finalizar_card", llm))
    assert llm.calls == 0 and sg.rows("cs_posts")[0]["legenda"] == "Minha legenda"
    assert sg.eventos("legenda_gerada", pid) == [] and len(sg.eventos("fluxo_concluido", pid)) == 1
    assert sg.proposta(pid)["fluxo_etapa"] == "concluido"


def test_uma_falha_da_legenda_e_registrada_com_o_codigo_e_o_fluxo_conclui_sem_legenda(sg):
    pid, roteiro = _ate_o_card(sg)
    _completar_roteiro(sg, roteiro["id"])
    asyncio.run(sg.rodar("fluxo.finalizar_card", Llm("isto não é json")))
    falhou = sg.eventos("legenda_falhou", pid)
    assert len(falhou) == 1 and falhou[0]["codigo"] == "ia_resposta_invalida"
    assert sg.rows("cs_posts")[0].get("legenda") is None and sg.proposta(pid)["fluxo_etapa"] == "concluido"


def test_roteiro_em_falha_registra_roteiro_falhou_e_fluxo_concluido(sg):
    pid, roteiro = _ate_o_card(sg)
    sg.db.from_("cs_roteiros").update({"status": "falha"}).eq("id", roteiro["id"]).execute()
    asyncio.run(sg.rodar("fluxo.finalizar_card", Llm(LEGENDA_JSON)))
    assert len(sg.eventos("roteiro_falhou", pid)) == 1 and len(sg.eventos("fluxo_concluido", pid)) == 1
    p = sg.proposta(pid)
    assert p["fluxo_etapa"] == "falhou" and p["fluxo_erro_codigo"] == "roteiro_falhou"


def test_o_finalizador_desiste_depois_do_prazo_com_demorou(sg):
    pid, roteiro = _ate_o_card(sg)
    job = sg.jobs.do_tipo("fluxo.finalizar_card")[0]
    depois = job.created_at + fin.PRAZO_FINALIZADOR + timedelta(seconds=1)
    asyncio.run(sg.rodar("fluxo.finalizar_card", Llm(LEGENDA_JSON), agora=lambda: depois))
    ev = sg.eventos("roteiro_falhou", pid)
    assert len(ev) == 1 and ev[0]["codigo"] == "demorou"
    assert sg.proposta(pid)["fluxo_erro_codigo"] == "demorou"


def test_os_dois_jobs_estao_registrados_no_worker_de_geracao(sg):
    from app.modules.media_creation.services import geracao_jobs as gj

    fin.register()
    assert gj.get_handler("fluxo.finalizar_card") is fin._handle_finalizar
    assert gj.get_handler("fluxo.headline_do_roteiro") is fin._handle_headline


# ── minimal EST-RO (6.7) ────────────────────────────────────────────────────────────────────────────────


def _svc(sg):
    return RoteiroService(sg.db, TEST_ORG_ID, TEST_USER_ID, cfg=sg.cfg, jobs=sg.jobs, ia_check=lambda o: None,
                          approvals=sg.approvals())


def _body(**kw):
    return RoteiroCreate(marca_id=MARCA, headline_texto="Você erra isso", gerar_perguntas=False, **kw)


def test_est_ro_o_formato_vem_da_estrutura_principal_e_e_gravado_com_as_estruturas_e_a_conversa(sg):
    cid = _conversa(sg)
    out = asyncio.run(_svc(sg).create(_body(estrutura_ids=[E1, E2], conversa_id=cid)))
    row = sg.rows("cs_roteiros", id=out["id"])[0]
    assert (row["formato"], row["estrutura_ids"], row["conversa_id"]) == ("carrossel", [E1, E2], cid)
    sem = asyncio.run(_svc(sg).create(_body()))
    assert sg.rows("cs_roteiros", id=sem["id"])[0]["formato"] == "reels"
    post = asyncio.run(_svc(sg).create(_body(formato="post")))
    assert sg.rows("cs_roteiros", id=post["id"])[0]["formato"] == "post"


@pytest.mark.parametrize("kw,status,code", [
    ({"estrutura_ids": [E1, E2, E3, E1]}, 422, "muitas_estruturas"),
    ({"estrutura_ids": [E1, E_REELS]}, 422, "formatos_misturados"),
    ({"estrutura_ids": [E1], "formato": "reels"}, 422, "formato_diferente_da_estrutura"),
    ({"estrutura_ids": [E_INATIVA]}, 422, "estrutura_obrigatoria_invalida"),
    ({"estrutura_ids": [str(uuid.uuid4())]}, 422, "estrutura_obrigatoria_invalida"),
    ({"estrutura_ids": [E1, E1]}, 422, "estrutura_obrigatoria_invalida"),
])
def test_est_ro_recusas_codificadas_antes_de_gravar(sg, kw, status, code):
    with pytest.raises(RoteiroError) as exc:
        asyncio.run(_svc(sg).create(_body(**kw)))
    assert exc.value.status == status and exc.value.detail["code"] == code
    assert sg.rows("cs_roteiros") == [] and sg.jobs.enfileirados == {}


def test_est_ro_conversa_alheia_e_404(sg):
    with pytest.raises(RoteiroError) as exc:
        asyncio.run(_svc(sg).create(_body(conversa_id=str(uuid.uuid4()))))
    assert exc.value.status == 404


def test_est_ro_a_geracao_segue_o_formato_e_grava_os_usos_com_os_blocos_atribuidos(sg):
    cid = _conversa(sg)
    out = asyncio.run(_svc(sg).create(_body(estrutura_ids=[E1, E2], conversa_id=cid)))
    job = sg.jobs.do_tipo("roteiro.gerar")[0]
    resposta = ("**Slide 1 — Gancho**\nVocê erra isso agora.\n**Slide 2 — Virada**\nFaça assim.\n"
                "=== ESTRUTURAS_USADAS ===\n#101: Gancho forte; Bloco inventado\n#999: X")
    vistos = []

    async def llm(system, user, org_id):
        vistos.append((system, user))
        return resposta

    asyncio.run(executar_geracao(job, db=sg.db, llm=llm, cfg=sg.cfg))
    row = sg.rows("cs_roteiros", id=out["id"])[0]
    assert row["status"] == "completo" and "ESTRUTURAS_USADAS" not in row["conteudo"]
    assert "estrutura #101" in vistos[0][1]
    usos = sorted(sg.rows("cs_estrutura_usos", roteiro_id=out["id"]), key=lambda u: u["ordem"])
    assert [(u["estrutura_id"], u["papel"], u["bloco_ids"], u["contexto"]) for u in usos] == [
        (E1, "principal", [BLOCO_GANCHO], "chat"), (E2, "mistura", [], "chat")]
    rej = [e for e in sg.rows("cs_fluxo_eventos") if e["tipo"] == "citacao_rejeitada"]
    assert len(rej) == 1 and rej[0]["contagem"] == 2


def test_est_ro_um_roteiro_reels_sem_estruturas_segue_o_caminho_legado_intacto(sg):
    out = asyncio.run(_svc(sg).create(_body()))
    row = sg.rows("cs_roteiros", id=out["id"])[0]
    assert row["formato"] == "reels" and row["estrutura_ids"] == []


def test_postcreate_aceita_o_formato_do_card_com_reel_por_padrao():
    from app.modules.media_creation.schemas.esteira import PostCreate

    assert PostCreate(marca_id=MARCA, titulo="x").formato == "reel"
    assert PostCreate(marca_id=MARCA, titulo="x", formato="carrossel").formato == "carrossel"
    with pytest.raises(ValueError):
        PostCreate(marca_id=MARCA, titulo="x", formato="reels")

