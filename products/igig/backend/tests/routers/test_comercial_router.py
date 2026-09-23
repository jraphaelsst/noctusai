"""CRM, orçamentos e onboarding — Módulo 1.

Two properties carry the weight (the orçamento calculator moved to
`test_orcamento_router.py` with wave 2):
  1. the PUBLIC lead form is write-only and cannot be used to read anything;
  2. the signature webhook is idempotent — providers retry, and re-running the
     side effects would re-activate a client and re-convert a lead — and it is
     HMAC-SIGNED: an unsigned or mis-signed call changes nothing (smoke
     finding 2, it used to accept anyone holding a guessable id).
"""
import json

import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.services.contrato_documento import enviar_para_assinatura
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos):
    from app.main import app
    from app.storage import get_storage

    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    app.dependency_overrides[get_storage] = lambda: FakeStorageBackend()
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)
    app.dependency_overrides.pop(get_storage, None)


SEGREDO = "segredo-de-teste-assinatura"


@pytest.fixture
def assinado():
    """Configure the webhook secret (via `get_settings` DI — no monkeypatch
    of the singleton, KB § PATTERNS/backend/di-test-seam.md); return a poster
    that signs its body."""
    from app.config import get_settings, settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"igig_assinatura_webhook_secret": SEGREDO}
    )

    def _post(api, payload: dict, *, segredo: str = SEGREDO):
        corpo = json.dumps(payload).encode()
        return api.raw().post(
            "/api/comercial/assinatura/webhook",
            content=corpo,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Hmac-SHA256": compute_hmac_sha256_hex(corpo, segredo),
            },
        )

    yield _post
    app.dependency_overrides.pop(get_settings, None)


class TestFormularioPublico:
    """The public form writes through the service-role PostgREST client (the
    lead AND its funnel card), so these run on the shared `igig` mock."""

    @pytest.fixture
    def publico(self, crm_api):
        return crm_api

    def test_accepts_a_lead_without_auth(self, publico):
        resp = publico.raw().post("/api/comercial/leads/publico", json={
            "org_id": ORG, "nome": "João", "email": "joao@example.com",
            "nicho": "padaria", "dores": "pouco alcance",
        })
        assert resp.status_code == 201
        assert resp.json()["ok"] is True

    def test_returns_no_stored_data(self, publico):
        """An anonymous endpoint echoing records back is a scraping surface."""
        resp = publico.raw().post("/api/comercial/leads/publico",
                                  json={"org_id": ORG, "nome": "João"})
        corpo = resp.json()
        assert "id" not in corpo
        assert "João" not in str(corpo)

    def test_the_lead_is_actually_stored(self, publico, igig_db):
        publico.raw().post("/api/comercial/leads/publico",
                           json={"org_id": ORG, "nome": "João", "origem": "Instagram"})
        leads = igig_db.table("lead")._data
        assert [l["nome"] for l in leads] == ["João"]
        assert leads[0]["origem"] == "formulario", "origem is the CHANNEL now"
        assert leads[0]["como_conheceu"] == "Instagram", "the form's free text is kept"

    def test_the_lead_lands_in_the_funnels_first_stage(self, publico, igig_db):
        """Roadmap R2: a form lead appears in the first stage ('Leads')."""
        publico.raw().post("/api/comercial/leads/publico", json={"org_id": ORG, "nome": "João"})
        negocios = igig_db.table("negocio")._data
        assert len(negocios) == 1
        entrada = min(
            (s for s in igig_db.table("pipeline_stages")._data if s["pipeline"] == "comercial"),
            key=lambda s: s["posicao"],
        )
        assert negocios[0]["etapa_id"] == entrada["id"]
        assert negocios[0]["status"] == "aberto"

    def test_rejects_unknown_fields(self, publico):
        resp = publico.raw().post("/api/comercial/leads/publico",
                                  json={"org_id": ORG, "nome": "J", "admin": True})
        assert resp.status_code == 422

    def test_listing_leads_still_requires_auth(self, api):
        assert api.raw().get("/api/comercial/leads").status_code == 401


class TestAtualizarLead:
    def test_requires_auth(self, api, repos):
        lead = repos.lead.criar(ORG, {"nome": "João"})
        resp = api.raw().patch(f"/api/comercial/leads/{lead['id']}", json={"nome": "X"})
        assert resp.status_code == 401

    def test_edits_the_contact_fields(self, api, repos):
        lead = repos.lead.criar(ORG, {"nome": "João", "empresa": "Padaria Sol"})
        resp = api.patch(f"/api/comercial/leads/{lead['id']}", json={
            "nome": "João Silva", "empresa": "Padaria do Sol", "email": "joao@sol.com",
            "telefone": "11999990000", "instagram": "@padariasol",
            "observacoes": "prefere WhatsApp",
        })
        assert resp.status_code == 200, resp.text
        corpo = resp.json()["data"]
        assert corpo["nome"] == "João Silva"
        assert corpo["empresa"] == "Padaria do Sol"
        assert corpo["email"] == "joao@sol.com"
        assert corpo["telefone"] == "11999990000"
        assert corpo["instagram"] == "@padariasol"
        assert corpo["observacoes"] == "prefere WhatsApp"

    def test_partial_update_keeps_other_fields(self, api, repos):
        lead = repos.lead.criar(ORG, {"nome": "João", "empresa": "Padaria Sol"})
        resp = api.patch(f"/api/comercial/leads/{lead['id']}", json={"observacoes": "ligar amanhã"})
        assert resp.status_code == 200
        assert resp.json()["data"]["nome"] == "João"
        assert resp.json()["data"]["empresa"] == "Padaria Sol"
        assert resp.json()["data"]["observacoes"] == "ligar amanhã"

    def test_invalid_email_is_422(self, api, repos):
        lead = repos.lead.criar(ORG, {"nome": "João"})
        resp = api.patch(f"/api/comercial/leads/{lead['id']}", json={"email": "não-é-email"})
        assert resp.status_code == 422

    def test_empty_body_is_422(self, api, repos):
        lead = repos.lead.criar(ORG, {"nome": "João"})
        assert api.patch(f"/api/comercial/leads/{lead['id']}", json={}).status_code == 422

    def test_unknown_lead_is_404(self, api):
        assert api.patch("/api/comercial/leads/nao-existe", json={"nome": "X"}).status_code == 404

    def test_rejects_unknown_fields(self, api, repos):
        lead = repos.lead.criar(ORG, {"nome": "João"})
        resp = api.patch(f"/api/comercial/leads/{lead['id']}", json={"status": "convertido"})
        assert resp.status_code == 422

    def test_is_org_scoped(self, api, repos):
        outro = repos.lead.criar("outra-org", {"nome": "De outra org"})
        resp = api.patch(f"/api/comercial/leads/{outro['id']}", json={"nome": "X"})
        assert resp.status_code == 404


class TestConversao:
    def test_creates_a_cliente_and_links_it(self, api, repos):
        repos.lead.criar(ORG, {"nome": "João", "empresa": "Padaria Sol", "nicho": "food"})
        lead = repos.lead.listar(ORG)[0]
        resp = api.post(f"/api/comercial/leads/{lead['id']}/converter")
        assert resp.status_code == 200
        assert resp.json()["status"] == "convertido"
        assert resp.json()["cliente_id"]
        assert [c["nome"] for c in repos.cliente.listar(ORG)] == ["Padaria Sol"]

    def test_conversion_is_idempotent(self, api, repos):
        """A second click must not create a second cliente."""
        repos.lead.criar(ORG, {"nome": "João", "empresa": "Padaria Sol"})
        lead = repos.lead.listar(ORG)[0]
        api.post(f"/api/comercial/leads/{lead['id']}/converter")
        api.post(f"/api/comercial/leads/{lead['id']}/converter")
        assert len(repos.cliente.listar(ORG)) == 1

    def test_unknown_lead_returns_404(self, api):
        assert api.post("/api/comercial/leads/nao-existe/converter").status_code == 404


class TestContratoEAssinatura:
    def _gerar(self, api, repos):
        """A contract awaiting signature, dispatched through the signing leg.

        Generation itself (orçamento aceito → contrato + PDF) is covered in
        `test_orcamento_router.py`; the webhook only needs a contract that the
        signature path issued an external id for.
        """
        cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
        solicitacao = enviar_para_assinatura(
            org_id=ORG, provedor="interno", documento_nome="Contrato",
            signatario_email="joao@sol.com",
        )
        contrato = repos.contrato.criar(ORG, {
            "cliente_id": cliente["id"], "valor_mensal": 5000.0, "posts_por_mes": 12,
            "status": "aguardando_assinatura",
            "assinatura_external_id": solicitacao.external_id,
        })
        return cliente, {"contrato_id": contrato["id"], "external_id": solicitacao.external_id,
                         "dry_run": solicitacao.dry_run}

    def test_dispatch_without_credentials_is_a_flagged_dry_run(self, api, repos):
        _cliente, corpo = self._gerar(api, repos)
        assert corpo["dry_run"] is True, "no provider credentials ⇒ dry run, surfaced"

    def test_contract_starts_awaiting_signature(self, api, repos):
        _cliente, corpo = self._gerar(api, repos)
        contrato = repos.contrato.buscar(ORG, corpo["contrato_id"])
        assert contrato["status"] == "aguardando_assinatura"

    def test_dry_run_external_id_is_not_guessable(self, api, repos):
        """Smoke finding 2: the id was `dry-<provedor>-<timestamp>`."""
        _c, primeiro = self._gerar(api, repos)
        _c, segundo = self._gerar(api, repos)
        assert primeiro["external_id"] != segundo["external_id"]
        # Split on the FIXED prefix, never on "-": the token is
        # `secrets.token_urlsafe`, whose alphabet itself contains "-" (a
        # rsplit("-") made this test flaky under pytest-randomly).
        prefixo = f"{ORG}.dry-interno-"
        assert primeiro["external_id"].startswith(prefixo)
        segredo = primeiro["external_id"][len(prefixo):]
        assert len(segredo) >= 24 and not segredo.isdigit()

    def test_signature_activates_contract_and_client(self, api, repos, assinado):
        """The Módulo 1 automation, end to end."""
        cliente, corpo = self._gerar(api, repos)
        resp = assinado(api, {"external_id": corpo["external_id"], "evento": "assinado"})
        assert resp.status_code == 200
        assert resp.json()["cliente_ativado"] is True
        assert repos.contrato.buscar(ORG, corpo["contrato_id"])["status"] == "ativo"
        assert repos.cliente.buscar(ORG, cliente["id"])["status"] == "ativo"

    def test_webhook_is_idempotent(self, api, repos, assinado):
        """Providers retry — a second delivery must not re-run side effects."""
        _cliente, corpo = self._gerar(api, repos)
        payload = {"external_id": corpo["external_id"], "evento": "assinado"}
        assinado(api, payload)
        segunda = assinado(api, payload)
        assert segunda.status_code == 200
        assert segunda.json()["ja_processado"] is True

    def test_webhook_needs_no_session_the_signature_is_the_credential(
        self, api, repos, assinado
    ):
        """The vendor has no noc session; the HMAC over the body authenticates it."""
        _cliente, corpo = self._gerar(api, repos)
        resp = assinado(api, {"external_id": corpo["external_id"], "evento": "assinado"})
        assert resp.status_code == 200

    def test_unsigned_call_is_401_and_changes_nothing(self, api, repos, assinado):
        cliente, corpo = self._gerar(api, repos)
        resp = api.raw().post("/api/comercial/assinatura/webhook", json={
            "external_id": corpo["external_id"], "evento": "assinado",
        })
        assert resp.status_code == 401
        assert repos.contrato.buscar(ORG, corpo["contrato_id"])["status"] != "ativo"
        assert repos.cliente.buscar(ORG, cliente["id"])["status"] == "prospect"

    def test_wrong_secret_is_401(self, api, repos, assinado):
        _cliente, corpo = self._gerar(api, repos)
        resp = assinado(
            api, {"external_id": corpo["external_id"], "evento": "assinado"}, segredo="outro"
        )
        assert resp.status_code == 401

    def test_without_a_configured_secret_every_call_is_refused(self, api, repos):
        """Fail-closed: no early-dev bypass on an endpoint that activates contracts."""
        _cliente, corpo = self._gerar(api, repos)
        corpo_json = json.dumps({"external_id": corpo["external_id"], "evento": "assinado"})
        resp = api.raw().post(
            "/api/comercial/assinatura/webhook", content=corpo_json.encode(),
            headers={"Content-Type": "application/json",
                     "X-Webhook-Hmac-SHA256": compute_hmac_sha256_hex(corpo_json.encode(), "x")},
        )
        assert resp.status_code == 401

    def test_unknown_external_id_returns_404(self, api, assinado):
        resp = assinado(api, {"external_id": "nao.existe", "evento": "assinado"})
        assert resp.status_code == 404

    def test_malformed_external_id_returns_404(self, api, assinado):
        resp = assinado(api, {"external_id": "sem-org", "evento": "assinado"})
        assert resp.status_code == 404

    def test_signed_but_invalid_body_returns_422(self, api, assinado):
        assert assinado(api, {"external_id": "x.y", "evento": "talvez"}).status_code == 422

    def test_refusal_does_not_activate(self, api, repos, assinado):
        cliente, corpo = self._gerar(api, repos)
        assinado(api, {"external_id": corpo["external_id"], "evento": "recusado"})
        assert repos.contrato.buscar(ORG, corpo["contrato_id"])["status"] != "ativo"
        assert repos.cliente.buscar(ORG, cliente["id"])["status"] == "prospect"
