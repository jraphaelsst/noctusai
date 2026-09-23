"""Gmail reply watch (wave-2 slice B, roadmap R8).

Push → verify (OIDC, pinned SA) → list_history → metadata → seed
`match_reply` against our sent orçamento Message-IDs → ``in`` row,
``respondido_em``, in-app notification + e-mail to the owner.

Runs on the PostgREST mock (`IgigMockClient`) because the push resolves its
org through a CROSS-ORG read of ``gmail_watch`` on the service-role client;
the repositories sit on the SAME mock through the real `SupabaseRecordStore`
adapter, as in production. The Pub/Sub token verifier is injected through the
seed's `verifier=` seam — the check itself (aud / issuer / SA / verified) is
the real one.
"""
import asyncio
import base64
import json
from dataclasses import replace

import pytest
from noctusai_lib.integrations.gmail import FakeGmailClient
from noctusai_lib.integrations.persistence import SupabaseRecordStore

from app.email_deps import (
    get_email_sender_factory,
    get_email_settings,
    get_gmail_client_factory,
    get_push_token_verifier,
)
from app.pipelines import get_admin_db, get_core_db
from app.repositories import Repositorios
from app.repositories.email import repositorios_email
from app.services import email_config, orcamento_email
from app.store import get_repositorios, get_repositorios_admin
from tests.email_support import COM_GCP, MAILBOX, ORG, SMTP, TOPICO, ConfigBox, Senders

SA = COM_GCP.gmail_push_service_account
AUD = COM_GCP.gmail_push_audience
ENVIADO = "<orc-1@agencia.com>"
URL = "/api/webhooks/gmail/push"


def _verificador(token, audience):
    if token != "token-bom":
        raise ValueError("assinatura inválida")
    return {"aud": audience, "iss": "https://accounts.google.com", "email": SA, "email_verified": True}


def _corpo(history_id="9999", email=MAILBOX) -> dict:
    dados = base64.b64encode(json.dumps({"emailAddress": email, "historyId": history_id}).encode())
    return {"message": {"data": dados.decode(), "messageId": "ps-1"}, "subscription": "s"}


@pytest.fixture
def repos(igig_db) -> Repositorios:
    return Repositorios(SupabaseRecordStore(igig_db))


@pytest.fixture
def cfg() -> ConfigBox:
    return ConfigBox(COM_GCP)


@pytest.fixture
def senders() -> Senders:
    return Senders()


@pytest.fixture
def gmail() -> FakeGmailClient:
    return FakeGmailClient()


@pytest.fixture
def api(client, igig_db, core_db, repos, cfg, senders, gmail):
    from app.main import app

    overrides = {
        get_admin_db: lambda: igig_db,
        get_core_db: lambda: core_db,
        get_repositorios: lambda: repos,
        get_repositorios_admin: lambda: repos,
        get_email_settings: cfg,
        get_email_sender_factory: lambda: senders,
        get_gmail_client_factory: lambda: (lambda _creds: gmail),
        get_push_token_verifier: lambda: _verificador,
    }
    app.dependency_overrides.update(overrides)
    yield client
    for dep in overrides:
        app.dependency_overrides.pop(dep, None)


@pytest.fixture
def cenario(repos, core_db, gmail) -> dict:
    """A connected + watched mailbox, SMTP, a sent orçamento, an owner."""
    email_config.salvar_smtp(repos, ORG, COM_GCP, **SMTP)
    email_config.salvar_gmail(
        repos, ORG, COM_GCP, email=MAILBOX, refresh_token="r", access_token=None,
        scopes=list(email_config.GMAIL_OAUTH_SCOPES),
    )
    erepos = repositorios_email(repos.store)
    watch = asyncio.run(gmail.watch(TOPICO))
    erepos.watches.registrar(
        ORG, email=MAILBOX, history_id=watch.history_id, expiration=watch.expiration, topic=TOPICO,
    )
    lead = repos.lead.criar(ORG, {"nome": "Padaria Sol", "email": "contato@padariasol.com"})
    orc = repos.orcamento.criar(ORG, {
        "lead_id": lead["id"], "titulo": "Gestão de Instagram", "status": "enviado",
    })
    erepos.emails.criar(ORG, {
        "orcamento_id": orc["id"], "direction": "out", "message_id": ENVIADO,
        "occurred_at": "2026-09-20T10:00:00+00:00",
    })
    core_db.table("noctus_users").insert([
        {"id": "owner-1", "email": "dono@agencia.com", "org_id": ORG, "org_role": "owner"},
        {"id": "membro-1", "email": "m@agencia.com", "org_id": ORG, "org_role": "member"},
    ]).execute()
    return {"orcamento": orc, "erepos": erepos}


def _resposta(gmail, mid="m1", **headers):
    return gmail.add_fake_message(
        mid, thread_id="t1", from_="Padaria Sol <contato@padariasol.com>",
        subject="Re: Proposta", snippet="Topamos! Podemos começar segunda?",
        headers={"Message-ID": f"<{mid}@mail.gmail.com>", "In-Reply-To": ENVIADO, **headers},
    )


def _push(api, **kw):
    return api.raw().post(URL, json=_corpo(**kw), headers={"Authorization": "Bearer token-bom"})


class TestVerificacao:
    def test_bad_token_is_401_and_nothing_is_read(self, api, cenario, gmail):
        _resposta(gmail)
        resp = api.raw().post(URL, json=_corpo(), headers={"Authorization": "Bearer forjado"})
        assert resp.status_code == 401
        assert cenario["erepos"].emails.do_orcamento(ORG, cenario["orcamento"]["id"])[1:] == []

    def test_missing_token_is_401(self, api, cenario):
        assert api.raw().post(URL, json=_corpo()).status_code == 401

    def test_token_from_another_service_account_is_401(self, api, cenario):
        from app.main import app

        def _outro(token, audience):
            return {"aud": audience, "iss": "accounts.google.com",
                    "email": "intruso@x.iam.gserviceaccount.com", "email_verified": True}

        app.dependency_overrides[get_push_token_verifier] = lambda: _outro
        assert _push(api).status_code == 401

    def test_missing_gcp_config_refuses_503(self, api, cfg):
        cfg.valor = replace(COM_GCP, gmail_push_audience="")
        assert _push(api).status_code == 503

    def test_malformed_envelope_is_400(self, api, cenario):
        resp = api.raw().post(
            URL, json={"message": {"data": "!!"}}, headers={"Authorization": "Bearer token-bom"},
        )
        assert resp.status_code == 400


class TestResposta:
    def test_a_reply_is_recorded(self, api, cenario, gmail, repos):
        _resposta(gmail)
        assert _push(api).status_code == 204
        linhas = cenario["erepos"].emails.do_orcamento(ORG, cenario["orcamento"]["id"])
        entrada = [linha for linha in linhas if linha["direction"] == "in"]
        assert len(entrada) == 1
        assert entrada[0]["message_id"] == "<m1@mail.gmail.com>"
        assert entrada[0]["thread_id"] == "t1"
        assert "contato@padariasol.com" in entrada[0]["from_addr"]
        assert entrada[0]["snippet"] == "Topamos! Podemos começar segunda?"
        assert repos.orcamento.buscar(ORG, cenario["orcamento"]["id"])["respondido_em"]

    def test_the_out_row_learns_its_thread(self, api, cenario, gmail):
        _resposta(gmail)
        _push(api)
        saida = cenario["erepos"].emails.por_message_id(ORG, ENVIADO)
        assert saida["thread_id"] == "t1"

    def test_owner_gets_an_in_app_notification_and_an_email(self, api, cenario, gmail, core_db, senders):
        _resposta(gmail)
        _push(api)
        notas = core_db.table("notifications").inserted_payloads
        assert [n["user_id"] for n in notas] == ["owner-1"]
        assert notas[0]["type"] == "orcamento_respondido"
        assert notas[0]["org_id"] == ORG
        assert notas[0]["metadata"]["link"] == f"/orcamentos?id={cenario['orcamento']['id']}"
        assert len(senders.fake.sent) == 1
        assert senders.fake.sent[0].to == ["dono@agencia.com"]
        assert "Topamos" in senders.fake.sent[0].text

    def test_the_negocio_responsavel_is_notified_in_app(self, api, cenario, gmail, repos, core_db):
        prof = repos.profissional.criar(ORG, {"nome": "Ana", "usuario_id": "ana-user"})
        negocio = repos.store.insert("negocio", ORG, {
            "lead_id": cenario["orcamento"]["lead_id"], "titulo": "Sol", "etapa_id": "e1",
            "responsavel_id": prof["id"],
        })
        repos.orcamento.atualizar(ORG, cenario["orcamento"]["id"], {"negocio_id": negocio["id"]})
        _resposta(gmail)
        _push(api)
        notas = core_db.table("notifications").inserted_payloads
        assert [n["user_id"] for n in notas] == ["ana-user"]

    def test_redelivered_push_does_not_double(self, api, cenario, gmail, repos, core_db):
        _resposta(gmail)
        _push(api)
        # Pub/Sub redelivers; also force the cursor back so history re-lists m1.
        watch = cenario["erepos"].watches.por_email(ORG, MAILBOX)
        cenario["erepos"].watches.avancar_cursor(ORG, str(watch["id"]), "1000")
        assert _push(api).status_code == 204
        linhas = cenario["erepos"].emails.do_orcamento(ORG, cenario["orcamento"]["id"])
        assert len([linha for linha in linhas if linha["direction"] == "in"]) == 1
        assert len(core_db.table("notifications").inserted_payloads) == 1

    def test_the_cursor_advances(self, api, cenario, gmail):
        _resposta(gmail)
        _push(api)
        assert cenario["erepos"].watches.por_email(ORG, MAILBOX)["history_id"] == gmail.history_id

    def test_unrelated_mail_is_ignored(self, api, cenario, gmail, core_db):
        gmail.add_fake_message("m2", headers={"Message-ID": "<x@y>", "In-Reply-To": "<outro@z>"})
        assert _push(api).status_code == 204
        linhas = cenario["erepos"].emails.do_orcamento(ORG, cenario["orcamento"]["id"])
        assert [linha["direction"] for linha in linhas] == ["out"]
        assert core_db.table("notifications").inserted_payloads == []

    def test_reply_matched_through_references(self, api, cenario, gmail):
        gmail.add_fake_message("m3", thread_id="t9", headers={
            "Message-ID": "<m3@mail.gmail.com>", "In-Reply-To": "<outra@lead.com>",
            "References": f"{ENVIADO} <outra@lead.com>",
        })
        _push(api)
        linhas = cenario["erepos"].emails.do_orcamento(ORG, cenario["orcamento"]["id"])
        assert [linha["direction"] for linha in linhas].count("in") == 1

    def test_unknown_mailbox_is_a_noop(self, api, cenario):
        assert _push(api, email="ninguem@gmail.com").status_code == 204

    def test_expired_history_reconciles_recent_inbox(self, api, cenario, gmail):
        _resposta(gmail)
        gmail.expire_history_before(10**6)
        assert _push(api).status_code == 204
        linhas = cenario["erepos"].emails.do_orcamento(ORG, cenario["orcamento"]["id"])
        assert [linha["direction"] for linha in linhas].count("in") == 1
        assert len(gmail.watches) == 2, "a fresh watch re-seeds the cursor"


class TestRenovacao:
    def test_renews_expiration_and_keeps_the_cursor(self, cenario, repos, igig_db, gmail):
        watch = cenario["erepos"].watches.por_email(ORG, MAILBOX)
        cenario["erepos"].watches.atualizar(ORG, str(watch["id"]), {
            "history_id": "1000", "expiration": "2026-01-02T00:00:00+00:00",
        })
        resultado = asyncio.run(orcamento_email.renovar_watches(
            igig_db, repos, gmail_factory=lambda _c: gmail, settings=COM_GCP,
        ))
        assert resultado == {"renovados": 1, "falhas": 0, "ignorados": 0}
        atual = cenario["erepos"].watches.por_email(ORG, MAILBOX)
        assert atual["history_id"] == "1000"
        assert atual["expiration"].startswith("2026-01-08")
        assert len(gmail.watches) == 2

    def test_without_gcp_nothing_is_attempted(self, cenario, repos, igig_db, gmail):
        resultado = asyncio.run(orcamento_email.renovar_watches(
            igig_db, repos, gmail_factory=lambda _c: gmail,
            settings=replace(COM_GCP, gmail_push_topic=""),
        ))
        assert resultado == {"renovados": 0, "falhas": 0, "ignorados": 0}
        assert len(gmail.watches) == 1

    def test_a_failing_org_is_recorded_and_the_loop_continues(self, cenario, repos, igig_db):
        class _Quebrado(FakeGmailClient):
            async def watch(self, topic_name, label_ids=None):
                raise RuntimeError("invalid_grant")

        resultado = asyncio.run(orcamento_email.renovar_watches(
            igig_db, repos, gmail_factory=lambda _c: _Quebrado(), settings=COM_GCP,
        ))
        assert resultado["falhas"] == 1
        assert "invalid_grant" in repos.integracao.por_canal(ORG, "gmail")["ultimo_erro"]
