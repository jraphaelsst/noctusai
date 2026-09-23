"""Orçamento by e-mail (wave-2 slice B, roadmap R7).

`POST /api/orcamentos/{id}/enviar` needs the PDF slice A generates (seeded
here: the row's ``pdf_key`` + the object in the fake storage) and sends it,
attached, through the org's SMTP; the send is logged as an ``out`` row that
the reply watcher later threads against, and the response answers the FULL
`Orcamento` shape (slice A's serializer, `app/services/orcamentos.py`) — the
same one every other orçamento endpoint answers, not the raw stored row.

Runs on the shared `igig` mock (`crm_api`): the router builds its own
`Repositorios` over the SAME PostgREST client `get_db` injects, so the write
and the re-read see the same row, as in production.
"""
import asyncio

import pytest
from noctusai_lib.integrations.persistence import SupabaseRecordStore
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.email_deps import get_email_sender_factory, get_email_settings, get_pdf_storage
from app.repositories import Repositorios
from app.repositories.email import repositorios_email
from app.services import email_config
from tests.email_support import MAILBOX, ORG, SEM_GCP, SMTP, ConfigBox, Senders

PDF = b"%PDF-1.7 orcamento"
CHAVE_PDF = f"{ORG}/orcamentos/o1/v1.pdf"


@pytest.fixture
def repos(igig_db) -> Repositorios:
    return Repositorios(SupabaseRecordStore(igig_db))


@pytest.fixture
def cfg() -> ConfigBox:
    return ConfigBox(SEM_GCP)


@pytest.fixture
def senders() -> Senders:
    return Senders()


@pytest.fixture
def storage() -> FakeStorageBackend:
    backend = FakeStorageBackend()
    asyncio.run(backend.put(bucket="igig", key=CHAVE_PDF, data=PDF, content_type="application/pdf"))
    return backend


@pytest.fixture
def api(crm_api, cfg, senders, storage):
    from app.main import app

    overrides = {
        get_email_settings: cfg,
        get_email_sender_factory: lambda: senders,
        get_pdf_storage: lambda: storage,
    }
    app.dependency_overrides.update(overrides)
    yield crm_api
    for dep in overrides:
        app.dependency_overrides.pop(dep, None)


@pytest.fixture
def smtp(repos):
    email_config.salvar_smtp(
        repos, ORG, SEM_GCP, **{k: v for k, v in SMTP.items()},
    )


@pytest.fixture
def lead(repos) -> dict:
    return repos.lead.criar(ORG, {"nome": "Padaria Sol", "email": "contato@padariasol.com"})


def _orcamento(repos, lead, **extra) -> dict:
    valores = {
        "lead_id": lead["id"], "titulo": "Gestão de Instagram", "status": "rascunho",
        "total_mensal": 1500, "validade": "2026-10-31", "pdf_key": CHAVE_PDF, **extra,
    }
    return repos.orcamento.criar(ORG, valores)


def _enviar(api, orcamento_id, **body):
    return api.post(f"/api/orcamentos/{orcamento_id}/enviar", json=body)


class TestEnviar:
    def test_requires_auth(self, api, repos, lead):
        orc = _orcamento(repos, lead)
        assert api.raw().post(f"/api/orcamentos/{orc['id']}/enviar", json={}).status_code == 401

    def test_sends_the_pdf_to_the_lead(self, api, repos, lead, smtp, senders):
        orc = _orcamento(repos, lead)
        resp = _enviar(api, orc["id"])
        assert resp.status_code == 200
        data = resp.json()["data"]
        enviado = senders.fake.sent[0]
        assert enviado.to == ["contato@padariasol.com"]
        assert enviado.attachments[0].content == PDF
        assert enviado.attachments[0].mime_type == "application/pdf"
        assert "Padaria Sol" in enviado.html and "R$ 1.500,00" in enviado.html
        assert "31/10/2026" in enviado.html
        assert data["message_id"] == "<fake-1@fake.noctus.test>"
        assert data["orcamento"]["id"] == orc["id"]
        assert data["orcamento"]["status"] == "enviado"
        assert data["orcamento"]["enviado_em"]

    def test_answers_the_full_orcamento_shape(self, api, repos, lead, smtp):
        """Not the raw stored row — the same serializer `GET /{id}` answers,
        with items, the lead and the totals embedded."""
        orc = _orcamento(repos, lead)
        data = _enviar(api, orc["id"]).json()["data"]
        corpo = data["orcamento"]
        assert corpo["lead"]["email"] == "contato@padariasol.com"
        assert corpo["itens"] == []
        assert corpo["total_mensal"] == 1500.0
        assert corpo["limites_escopo"]

    def test_logs_the_out_row(self, api, repos, lead, smtp):
        orc = _orcamento(repos, lead)
        _enviar(api, orc["id"], assunto="Nossa proposta", mensagem="Oi!\nSegue.")
        linhas = api.get(f"/api/orcamentos/{orc['id']}/emails").json()["data"]
        assert len(linhas) == 1
        linha = linhas[0]
        assert linha["direction"] == "out"
        assert linha["message_id"] == "<fake-1@fake.noctus.test>"
        assert linha["subject"] == "Nossa proposta"
        assert linha["from_addr"] == "agencia@gmail.com"
        assert set(linha) == {
            "id", "orcamento_id", "direction", "message_id", "thread_id",
            "from_addr", "subject", "snippet", "occurred_at",
        }

    def test_explicit_recipients_and_cc(self, api, repos, lead, smtp, senders):
        orc = _orcamento(repos, lead)
        resp = _enviar(api, orc["id"], para="a@x.com; b@y.com", cc=["c@z.com"])
        assert resp.status_code == 200
        assert senders.fake.sent[0].to == ["a@x.com", "b@y.com"]
        assert senders.fake.sent[0].cc == ["c@z.com"]

    def test_default_subject_names_the_version(self, api, repos, lead, smtp, senders):
        orc = _orcamento(repos, lead, versao=2)
        _enviar(api, orc["id"])
        assert senders.fake.sent[0].subject == "Proposta: Gestão de Instagram (v2)"

    def test_reply_to_is_the_watched_mailbox(self, api, repos, lead, senders):
        email_config.salvar_smtp(repos, ORG, SEM_GCP, **{**SMTP, "from_email": "noreply@agencia.com"})
        email_config.salvar_gmail(
            repos, ORG, SEM_GCP, email=MAILBOX, refresh_token="r", access_token=None,
            scopes=list(email_config.GMAIL_OAUTH_SCOPES),
        )
        _enviar(api, _orcamento(repos, lead)["id"])
        assert senders.fake.sent[0].reply_to == MAILBOX

    def test_without_pdf_is_409(self, api, repos, lead, smtp):
        orc = _orcamento(repos, lead, pdf_key=None)
        resp = _enviar(api, orc["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "pdf_nao_gerado"

    def test_pdf_missing_from_storage_is_409(self, api, repos, lead, smtp, senders):
        orc = _orcamento(repos, lead, pdf_key=f"{ORG}/orcamentos/x/v9.pdf")
        resp = _enviar(api, orc["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "pdf_nao_gerado"
        assert senders.fake.sent == []

    def test_without_recipient_is_422(self, api, repos, smtp):
        sem_email = repos.lead.criar(ORG, {"nome": "Sem e-mail"})
        resp = _enviar(api, _orcamento(repos, sem_email)["id"])
        assert resp.status_code == 422
        assert resp.json()["code"] == "email_destinatario_ausente"

    def test_without_smtp_is_409_and_nothing_changes(self, api, repos, lead, senders):
        orc = _orcamento(repos, lead)
        resp = _enviar(api, orc["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "smtp_nao_configurado"
        assert senders.fake.sent == []
        assert repos.orcamento.buscar(ORG, orc["id"])["status"] == "rascunho"

    def test_accepted_orcamento_cannot_be_sent(self, api, repos, lead, smtp):
        orc = _orcamento(repos, lead, status="aceito")
        resp = _enviar(api, orc["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_bloqueado"

    def test_send_failure_is_502_and_not_marked_sent(self, api, repos, lead, smtp, senders):
        senders.falhar = True
        orc = _orcamento(repos, lead)
        resp = _enviar(api, orc["id"])
        assert resp.status_code == 502
        assert repos.orcamento.buscar(ORG, orc["id"])["status"] == "rascunho"
        assert repositorios_email(repos.store).emails.do_orcamento(ORG, orc["id"]) == []

    def test_platform_smtp_fallback(self, api, repos, lead, cfg, senders):
        from dataclasses import replace

        cfg.valor = replace(
            SEM_GCP, smtp_host="smtp.noctus.test", smtp_user="noc@noctus.test",
            smtp_password="p",
        )
        assert _enviar(api, _orcamento(repos, lead)["id"]).status_code == 200
        assert senders.configs[0].host == "smtp.noctus.test"

    def test_unknown_orcamento_is_404(self, api, smtp):
        assert _enviar(api, "00000000-0000-0000-0000-000000000000").status_code == 404

    def test_invalid_recipient_is_422(self, api, repos, lead, smtp):
        assert _enviar(api, _orcamento(repos, lead)["id"], para="nope").status_code == 422

    def test_is_org_scoped(self, api, repos, lead, smtp):
        outro = repos.orcamento.criar("11111111-1111-1111-1111-111111111111", {
            "titulo": "de outra org", "pdf_key": CHAVE_PDF,
        })
        assert _enviar(api, outro["id"]).status_code == 404
        assert api.get(f"/api/orcamentos/{outro['id']}/emails").status_code == 404


class TestEmails:
    def test_requires_auth(self, api, repos, lead):
        orc = _orcamento(repos, lead)
        assert api.raw().get(f"/api/orcamentos/{orc['id']}/emails").status_code == 401

    def test_empty(self, api, repos, lead):
        orc = _orcamento(repos, lead)
        assert api.get(f"/api/orcamentos/{orc['id']}/emails").json() == {"data": []}
