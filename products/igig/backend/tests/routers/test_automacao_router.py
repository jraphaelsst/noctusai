"""Automações v1 (roadmap R11, contract §E2) — the rules CRUD, the stage-entry
engine hooked into both boards, and the SLA sweep.

The properties that carry the weight:
* ONE execution per stage ENTRY: a within-column reorder does not re-fire, a
  card that leaves and comes back does;
* failures are RECORDED (`automacao_execucao.status='erro'` + why), never
  swallowed — and never turn the successful move into an error response;
* a rule that could never run is refused at save time (422), not at 3 a.m.

Everything runs on the shared `igig` mock (`crm_api` in conftest). The
e-mail / WhatsApp transports are the seed Fakes, injected through the engine's
ports (a dependency override), never patched.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.email import EmailSendError, FakeEmailSender
from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.security.encrypted_tokens import encrypt
from noctusai_lib.testing.clients import TEST_USER_ID

from app.config import get_settings, settings
from app.dependencies import coerce_org_uuid
from app.services.automacoes import PortasAutomacao, varrer_sla

ORG = str(coerce_org_uuid("test-org-123"))
CHAVE = Fernet.generate_key().decode()


@pytest.fixture
def cfg():
    return settings.model_copy(update={
        "igig_cofre_key": CHAVE,
        "smtp_host": "", "smtp_user": "", "smtp_password": "",
        "igig_waha_webhook_hmac_secret": "", "igig_meta_app_secret": "",
    })


@pytest.fixture
def api(crm_api, cfg):
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: cfg
    yield crm_api
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def admin(api):
    from app.main import app
    from app.pipelines import exigir_admin_da_org

    app.dependency_overrides[exigir_admin_da_org] = lambda: None
    yield api
    app.dependency_overrides.pop(exigir_admin_da_org, None)


@pytest.fixture
def transportes(igig_db, core_db, cfg):
    """Swap the engine's ports for ones whose e-mail/WhatsApp are the seed
    Fakes — the provider under test is the engine, not the transports."""
    from app.automacoes_deps import get_portas_automacao, get_portas_automacao_esteira
    from app.main import app

    email = FakeEmailSender()
    waha = FakeWahaClient()
    fabrica = lambda: PortasAutomacao(  # noqa: E731
        db=igig_db, admin_db=igig_db, core_db=core_db, cfg=cfg,
        email_sender=lambda _config: email, whatsapp_client=lambda **_k: waha,
    )
    app.dependency_overrides[get_portas_automacao] = fabrica
    app.dependency_overrides[get_portas_automacao_esteira] = fabrica
    yield email, waha
    app.dependency_overrides.pop(get_portas_automacao, None)
    app.dependency_overrides.pop(get_portas_automacao_esteira, None)


@pytest.fixture
def comercial(api) -> dict[str, dict]:
    resp = api.get("/api/comercial/pipeline/stages")
    assert resp.status_code == 200, resp.text
    return {s["slug"]: s for s in resp.json()["data"]}


@pytest.fixture
def esteira(api) -> dict[str, dict]:
    resp = api.get("/api/esteira/stages")
    assert resp.status_code == 200, resp.text
    return {s["slug"]: s for s in resp.json()["data"]}


@pytest.fixture
def profissional(igig_db) -> dict:
    return igig_db.table("profissional").insert(
        {"org_id": ORG, "nome": "Ana Vendas", "usuario_id": "user-ana", "ativo": True}
    ).execute().data[0]


def _regra(admin, pipeline, stage_id, tipo, params, **extra):
    resp = admin.post("/api/automacoes", json={
        "pipeline": pipeline, "stage_id": stage_id,
        "gatilho": extra.pop("gatilho", "entrada_etapa"),
        "acao": {"tipo": tipo, "params": params}, **extra,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _negocio(api, **lead) -> dict:
    resp = api.post("/api/comercial/negocios", json={
        "lead": {"nome": "João", "empresa": "Padaria Sol", "email": "joao@sol.com",
                 "telefone": "(11) 99457-3387", **lead},
        "valor_estimado": 3000,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _mover(api, negocio_id, etapa_id, **extra):
    resp = api.post(f"/api/comercial/negocios/{negocio_id}/mover-etapa",
                    json={"para_etapa_id": etapa_id, **extra})
    assert resp.status_code == 200, resp.text
    return resp


def _execucoes(igig_db, automacao_id=None):
    linhas = igig_db.table("automacao_execucao")._data
    return [e for e in linhas if automacao_id is None or e["automacao_id"] == automacao_id]


def _notificacoes(core_db, tipo):
    return [n for n in core_db.table("notifications")._data if n["type"] == tipo]


# ── Auth boundary ────────────────────────────────────────────────────
class TestAuthBoundary:
    def test_list_requires_auth(self, api):
        assert api.raw().get("/api/automacoes").status_code == 401

    def test_create_requires_auth(self, api):
        assert api.raw().post("/api/automacoes", json={}).status_code == 401

    def test_patch_requires_auth(self, api):
        assert api.raw().patch("/api/automacoes/x", json={"ativo": False}).status_code == 401

    def test_delete_requires_auth(self, api):
        assert api.raw().delete("/api/automacoes/x").status_code == 401

    def test_execucoes_requires_auth(self, api):
        assert api.raw().get("/api/automacoes/execucoes").status_code == 401


# ── CRUD ─────────────────────────────────────────────────────────────
class TestCrud:
    def test_create_list_patch_delete(self, admin, comercial):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "notificar",
                       {"mensagem": "Novo lead qualificado: {nome}"})
        assert regra["stage_id"] == comercial["qualificacao"]["id"]
        assert regra["acao"] == {"tipo": "notificar", "params": {
            "titulo": None, "mensagem": "Novo lead qualificado: {nome}", "usuario_ids": []}}
        assert regra["ativo"] is True and regra["sla_horas"] is None

        lista = admin.get("/api/automacoes?pipeline=comercial")
        assert lista.status_code == 200
        assert [r["id"] for r in lista.json()["data"]] == [regra["id"]]
        assert admin.get("/api/automacoes?pipeline=esteira").json()["data"] == []

        desligada = admin.patch(f"/api/automacoes/{regra['id']}", json={"ativo": False})
        assert desligada.status_code == 200
        assert desligada.json()["data"]["ativo"] is False

        assert admin.delete(f"/api/automacoes/{regra['id']}").status_code == 204
        assert admin.patch(f"/api/automacoes/{regra['id']}", json={"ativo": True}).status_code == 404

    def test_writes_are_admin_only(self, api, comercial):
        """The conftest user holds no admin role in the trusted table."""
        resp = api.post("/api/automacoes", json={
            "pipeline": "comercial", "stage_id": comercial["leads"]["id"],
            "gatilho": "entrada_etapa", "acao": {"tipo": "notificar", "params": {}},
        })
        assert resp.status_code == 403
        assert resp.json()["code"] == "admin_obrigatorio"

    def test_sla_rule_needs_hours(self, admin, comercial):
        resp = admin.post("/api/automacoes", json={
            "pipeline": "comercial", "stage_id": comercial["leads"]["id"], "gatilho": "sla",
            "acao": {"tipo": "notificar", "params": {}},
        })
        assert resp.status_code == 422

    def test_patch_to_sla_without_hours_is_refused(self, admin, comercial):
        regra = _regra(admin, "comercial", comercial["leads"]["id"], "notificar", {})
        resp = admin.patch(f"/api/automacoes/{regra['id']}", json={"gatilho": "sla"})
        assert resp.status_code == 422
        assert resp.json()["code"] == "sla_sem_horas"

    def test_stage_of_the_other_board_is_refused(self, admin, esteira):
        resp = admin.post("/api/automacoes", json={
            "pipeline": "comercial", "stage_id": esteira["revisao_interna"]["id"],
            "gatilho": "entrada_etapa", "acao": {"tipo": "notificar", "params": {}},
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "etapa_invalida"

    def test_checklist_on_the_esteira_is_refused(self, admin, esteira):
        resp = admin.post("/api/automacoes", json={
            "pipeline": "esteira", "stage_id": esteira["revisao_interna"]["id"],
            "gatilho": "entrada_etapa",
            "acao": {"tipo": "criar_checklist", "params": {"titulo": "X"}},
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "acao_incompativel"

    def test_unknown_params_are_refused(self, admin, comercial):
        resp = admin.post("/api/automacoes", json={
            "pipeline": "comercial", "stage_id": comercial["leads"]["id"],
            "gatilho": "entrada_etapa",
            "acao": {"tipo": "enviar_email", "params": {"assunto": "Oi", "mensagem": "x", "cco": "a@b.c"}},
        })
        assert resp.status_code == 422

    def test_missing_profissional_is_refused(self, admin, comercial):
        resp = admin.post("/api/automacoes", json={
            "pipeline": "comercial", "stage_id": comercial["leads"]["id"],
            "gatilho": "entrada_etapa",
            "acao": {"tipo": "definir_responsavel", "params": {"profissional_id": "nao-existe"}},
        })
        assert resp.status_code == 422
        assert resp.json()["code"] == "profissional_invalido"


# ── Engine: stage entry on the Comercial funnel ──────────────────────
class TestEntradaComercial:
    def test_move_runs_the_stage_rule_once_per_entry(self, admin, comercial, igig_db, core_db):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "notificar",
                       {"mensagem": "Qualificado: {nome} ({empresa})"})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])

        execs = _execucoes(igig_db, regra["id"])
        assert [e["status"] for e in execs] == ["sucesso"]
        assert execs[0]["movimento_id"], "an execution is keyed on its entry"
        avisos = _notificacoes(core_db, "automacao")
        assert len(avisos) == 1
        # No responsável on the card → the person who moved it hears about it.
        assert avisos[0]["user_id"] == TEST_USER_ID
        assert avisos[0]["message"] == "Qualificado: João (Padaria Sol)"

        # Reordering inside the same column is not a new entry.
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"], novo_indice=0)
        assert len(_execucoes(igig_db, regra["id"])) == 1

        # Leaving and coming back IS a new entry.
        _mover(admin, negocio["id"], comercial["negociacao"]["id"])
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"], motivo="voltou")
        assert len(_execucoes(igig_db, regra["id"])) == 2

    def test_inactive_rule_does_not_fire(self, admin, comercial, igig_db):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "notificar", {},
                       ativo=False)
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        assert _execucoes(igig_db, regra["id"]) == []

    def test_creation_fires_the_entry_stage_checklist(self, admin, comercial, igig_db):
        regra = _regra(admin, "comercial", comercial["leads"]["id"], "criar_checklist",
                       {"titulo": "Qualificar {empresa}", "itens": ["Ligar", "Pedir Instagram"]})
        negocio = _negocio(admin)

        assert [e["status"] for e in _execucoes(igig_db, regra["id"])] == ["sucesso"]
        checklists = [c for c in igig_db.table("negocio_checklists")._data
                      if c["negocio_id"] == negocio["id"]]
        assert [c["titulo"] for c in checklists] == ["Qualificar Padaria Sol"]
        itens = [i["texto"] for i in igig_db.table("negocio_checklist_itens")._data
                 if i["checklist_id"] == checklists[0]["id"]]
        assert itens == ["Ligar", "Pedir Instagram"]

    def test_criar_tarefa_appends_to_the_tarefas_checklist(self, admin, comercial, igig_db):
        _regra(admin, "comercial", comercial["negociacao"]["id"], "criar_tarefa",
               {"titulo": "Enviar proposta", "prazo_dias": 2})
        _regra(admin, "comercial", comercial["negociacao"]["id"], "criar_tarefa",
               {"titulo": "Agendar call"})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["negociacao"]["id"])

        tarefas = [c for c in igig_db.table("negocio_checklists")._data
                   if c["negocio_id"] == negocio["id"] and c["titulo"] == "Tarefas"]
        assert len(tarefas) == 1, "both rules share ONE 'Tarefas' checklist"
        itens = sorted(i["texto"] for i in igig_db.table("negocio_checklist_itens")._data
                       if i["checklist_id"] == tarefas[0]["id"])
        prazo = (datetime.now().date() + timedelta(days=2)).strftime("%d/%m/%Y")
        assert itens == ["Agendar call", f"Enviar proposta (até {prazo})"]

    def test_definir_responsavel_sets_the_owner(self, admin, comercial, igig_db, profissional):
        _regra(admin, "comercial", comercial["qualificacao"]["id"], "definir_responsavel",
               {"profissional_id": profissional["id"]})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        linha = next(n for n in igig_db.table("negocio")._data if n["id"] == negocio["id"])
        assert linha["responsavel_id"] == profissional["id"]

    def test_notification_goes_to_the_responsavel(self, admin, comercial, core_db, profissional):
        _regra(admin, "comercial", comercial["qualificacao"]["id"], "notificar", {})
        resp = admin.post("/api/comercial/negocios", json={
            "lead": {"nome": "Maria"}, "responsavel_id": profissional["id"]})
        assert resp.status_code == 201
        _mover(admin, resp.json()["data"]["id"], comercial["qualificacao"]["id"])
        assert [n["user_id"] for n in _notificacoes(core_db, "automacao")] == ["user-ana"]

    def test_email_without_smtp_is_an_error_row_and_the_move_still_succeeds(
        self, admin, comercial, igig_db
    ):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "enviar_email",
                       {"assunto": "Olá", "mensagem": "Oi {nome}"})
        negocio = _negocio(admin)
        resp = _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        assert resp.json()["data"]["etapa_id"] == comercial["qualificacao"]["id"]
        [execucao] = _execucoes(igig_db, regra["id"])
        assert execucao["status"] == "erro"
        assert "SMTP" in execucao["detalhe"]

    def test_email_through_the_org_smtp(self, admin, comercial, igig_db, transportes):
        email, _waha = transportes
        igig_db.table("integracao").insert({
            "org_id": ORG, "canal": "smtp", "ativo": True,
            "token_cifrado": encrypt("senha-smtp", CHAVE.encode()),
            "config": {"host": "smtp.agencia.com", "port": 465, "username": "vendas@agencia.com",
                       "security": "ssl", "from_email": "vendas@agencia.com", "from_name": "Agência"},
        }).execute()
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "enviar_email",
                       {"assunto": "Proposta para {empresa}", "mensagem": "Olá {nome},\nvamos conversar?"})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])

        assert [e["status"] for e in _execucoes(igig_db, regra["id"])] == ["sucesso"]
        [enviado] = email.sent
        assert enviado.to == ["joao@sol.com"]
        assert enviado.subject == "Proposta para Padaria Sol"
        assert enviado.text == "Olá João,\nvamos conversar?"
        assert "<br>" in enviado.html

    def test_transport_failure_is_recorded_with_its_reason(self, admin, comercial, igig_db,
                                                           core_db, cfg):
        from app.automacoes_deps import get_portas_automacao
        from app.main import app

        class SmtpQueCai:
            async def send(self, _email):
                raise EmailSendError("servidor recusou a conexão")

        igig_db.table("integracao").insert({
            "org_id": ORG, "canal": "smtp", "ativo": True,
            "token_cifrado": encrypt("x", CHAVE.encode()),
            "config": {"host": "h", "port": 587, "username": "u", "security": "starttls",
                       "from_email": "u@h.com"},
        }).execute()
        app.dependency_overrides[get_portas_automacao] = lambda: PortasAutomacao(
            db=igig_db, admin_db=igig_db, core_db=core_db, cfg=cfg,
            email_sender=lambda _c: SmtpQueCai(),
        )
        try:
            regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "enviar_email",
                           {"assunto": "A", "mensagem": "B"})
            negocio = _negocio(admin)
            _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        finally:
            app.dependency_overrides.pop(get_portas_automacao, None)
        [execucao] = _execucoes(igig_db, regra["id"])
        assert execucao["status"] == "erro"
        assert "servidor recusou a conexão" in execucao["detalhe"]

    def test_whatsapp_through_the_org_waha(self, admin, comercial, igig_db, transportes):
        _email, waha = transportes
        igig_db.table("integracao").insert({
            "org_id": ORG, "canal": "whatsapp", "ativo": True,
            "token_cifrado": encrypt("waha-key", CHAVE.encode()),
            "config": {"base_url": "http://waha:3000", "session": "agencia"},
        }).execute()
        _regra(admin, "comercial", comercial["qualificacao"]["id"], "enviar_whatsapp",
               {"mensagem": "Oi {nome}!"})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        assert waha.sent_messages == [
            {"id": "fake-msg-1", "session": "default", "chatId": "5511994573387@c.us", "text": "Oi João!"}
        ]

    def test_whatsapp_without_waha_is_an_error_row(self, admin, comercial, igig_db, transportes):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "enviar_whatsapp",
                       {"mensagem": "Oi"})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        [execucao] = _execucoes(igig_db, regra["id"])
        assert execucao["status"] == "erro"
        assert "WAHA" in execucao["detalhe"]

    def test_execucoes_log_lists_newest_with_the_rule(self, admin, comercial):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "enviar_email",
                       {"assunto": "A", "mensagem": "B"})
        negocio = _negocio(admin)
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        resp = admin.get("/api/automacoes/execucoes?limit=10")
        assert resp.status_code == 200
        [linha] = resp.json()["data"]
        assert linha["status"] == "erro"
        assert linha["entidade_id"] == negocio["id"]
        assert linha["automacao"] == {
            "id": regra["id"], "pipeline": "comercial",
            "stage_id": comercial["qualificacao"]["id"], "gatilho": "entrada_etapa",
            "tipo": "enviar_email",
        }


    def test_aceitar_orcamento_fires_the_fechado_rule_exactly_once(self, admin, comercial, igig_db):
        """Slice A's aceite moves the negócio into Fechado through the same
        transition service; entering Fechado fires its rules — and a
        re-accept (no new transition) must not fire them again."""
        regra = _regra(admin, "comercial", comercial["fechado"]["id"], "notificar",
                       {"mensagem": "Fechou: {empresa}"})
        negocio = _negocio(admin)
        orcamento = igig_db.table("orcamento").insert({
            "org_id": ORG, "negocio_id": negocio["id"], "lead_id": negocio["lead_id"],
            "titulo": "Proposta", "versao": 1, "status": "enviado",
        }).execute().data[0]
        for _ in range(2):
            resp = admin.post(f"/api/orcamentos/{orcamento['id']}/aceitar")
            assert resp.status_code == 200, resp.text
        assert [e["status"] for e in _execucoes(igig_db, regra["id"])] == ["sucesso"]

# ── Engine: stage entry on the Esteira ───────────────────────────────
class TestEntradaEsteira:
    @pytest.fixture
    def tarefa(self, admin, igig_db, esteira) -> dict:
        cliente = igig_db.table("cliente").insert(
            {"org_id": ORG, "nome": "Padaria Sol", "status": "ativo"}).execute().data[0]
        pauta = igig_db.table("pauta").insert(
            {"org_id": ORG, "cliente_id": cliente["id"], "titulo": "Post"}).execute().data[0]
        resp = admin.post("/api/esteira/tarefas", json={"pauta_id": pauta["id"], "titulo": "Roteiro"})
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_criar_tarefa_adds_one_on_the_same_pauta(self, admin, esteira, igig_db, tarefa):
        regra = _regra(admin, "esteira", esteira["roteiro_em_producao"]["id"], "criar_tarefa",
                       {"titulo": "Revisar roteiro de {titulo}", "prazo_dias": 1})
        resp = admin.post(f"/api/esteira/tarefas/{tarefa['id']}/mover-etapa",
                          json={"para_etapa_id": esteira["roteiro_em_producao"]["id"]})
        assert resp.status_code == 200, resp.text
        assert [e["status"] for e in _execucoes(igig_db, regra["id"])] == ["sucesso"]
        novas = [t for t in igig_db.table("tarefa")._data if t["id"] != tarefa["id"]]
        assert [t["titulo"] for t in novas] == ["Revisar roteiro de Roteiro"]
        assert novas[0]["pauta_id"] == tarefa["pauta_id"]
        assert novas[0]["etapa_id"] == esteira["aguardando_roteiro"]["id"]


# ── SLA sweep ────────────────────────────────────────────────────────
class TestSla:
    def _portas(self, igig_db, core_db, cfg, agora):
        return PortasAutomacao(db=igig_db, admin_db=igig_db, core_db=core_db, cfg=cfg,
                               agora=lambda: agora)

    def test_breach_alerts_once_per_entry(self, admin, comercial, igig_db, core_db, cfg,
                                                profissional):
        regra = _regra(admin, "comercial", comercial["qualificacao"]["id"], "notificar",
                       {"usuario_ids": ["user-gestor"]}, gatilho="sla", sla_horas=24)
        resp = admin.post("/api/comercial/negocios", json={
            "lead": {"nome": "Maria"}, "responsavel_id": profissional["id"]})
        negocio = resp.json()["data"]
        _mover(admin, negocio["id"], comercial["qualificacao"]["id"])
        agora = datetime.now(timezone.utc)

        antes = asyncio.run(varrer_sla(self._portas(igig_db, core_db, cfg, agora + timedelta(hours=23))))
        assert antes["estourados"] == 0 and _notificacoes(core_db, "sla_estourado") == []

        depois = asyncio.run(varrer_sla(self._portas(igig_db, core_db, cfg, agora + timedelta(hours=25))))
        assert depois["estourados"] == 1 and depois["execucoes"] == 1
        avisos = _notificacoes(core_db, "sla_estourado")
        assert sorted(a["user_id"] for a in avisos) == ["user-ana", "user-gestor"]
        assert "há mais de 24h" in avisos[0]["message"]
        assert [e["status"] for e in _execucoes(igig_db, regra["id"])] == ["sucesso"]

        # The next tick must not re-alert the same entry.
        asyncio.run(varrer_sla(self._portas(igig_db, core_db, cfg, agora + timedelta(hours=26))))
        assert len(_notificacoes(core_db, "sla_estourado")) == 2

    def test_unowned_breach_falls_back_to_org_admins(self, admin, comercial, igig_db,
                                                          core_db, cfg):
        core_db.table("noctus_users").insert(
            {"id": "user-dona", "org_id": ORG, "org_role": "owner", "email": "d@a.com"}).execute()
        _regra(admin, "comercial", comercial["leads"]["id"], "notificar", {}, gatilho="sla",
               sla_horas=1)
        _negocio(admin)
        asyncio.run(varrer_sla(self._portas(igig_db, core_db, cfg,
                                      datetime.now(timezone.utc) + timedelta(hours=2))))
        assert [a["user_id"] for a in _notificacoes(core_db, "sla_estourado")] == ["user-dona"]

    def test_sla_rule_with_another_action_alerts_and_acts(self, admin, comercial, igig_db,
                                                               core_db, cfg, profissional):
        _regra(admin, "comercial", comercial["leads"]["id"], "definir_responsavel",
               {"profissional_id": profissional["id"]}, gatilho="sla", sla_horas=1)
        negocio = _negocio(admin)
        asyncio.run(varrer_sla(self._portas(igig_db, core_db, cfg,
                                      datetime.now(timezone.utc) + timedelta(hours=2))))
        linha = next(n for n in igig_db.table("negocio")._data if n["id"] == negocio["id"])
        assert linha["responsavel_id"] == profissional["id"]
        assert [a["user_id"] for a in _notificacoes(core_db, "sla_estourado")] == ["user-ana"]

    def test_the_sweep_is_registered_every_15_minutes(self):
        from noctusai_lib.api.scheduler import scheduler

        import app.main  # noqa: F401 — registration happens at import

        job = scheduler.get_job("igig_automacoes_sla")
        assert job is not None
        assert job.trigger.interval == timedelta(minutes=15)
