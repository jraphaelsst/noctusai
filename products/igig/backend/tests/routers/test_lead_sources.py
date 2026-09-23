"""Lead sources v1 — WAHA + Meta Lead Ads setup and their PUBLIC webhooks
(contract §E2, roadmap decision log "Lead sources v1").

The properties that carry the weight:
* a secret goes IN and never comes back out of any response;
* the public webhooks authenticate BEFORE any write (per-org token + HMAC for
  WAHA; the owning app's signature for Meta) and never enumerate tokens;
* one person → one lead: a redelivery or a second message dedupes on the
  `waha_chat_id` / `meta_lead_id` key;
* a new lead lands on the funnel's entry stage AND fires its automations;
* a per-lead failure is recorded on the channel (`ultimo_erro`), the vendor
  still gets its 200.
"""
import json

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.meta import FakeMetaAdapter, Lead, LeadFieldEntry
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

from app.config import get_settings, settings
from app.dependencies import coerce_org_uuid

ORG = str(coerce_org_uuid("test-org-123"))
OUTRA_ORG = "3b0c7f2e-9a41-4d8e-b0a6-2f1d5c7e9a10"
CHAVE = Fernet.generate_key().decode()
HMAC_WAHA = "waha-hmac-secret"
APP_SECRET = "meta-app-secret-da-agencia"
PAGINA = "1234567890"


@pytest.fixture
def cfg():
    return settings.model_copy(update={
        "igig_cofre_key": CHAVE,
        "igig_waha_webhook_hmac_secret": HMAC_WAHA,
        "igig_meta_app_secret": "",
        "smtp_host": "", "smtp_user": "", "smtp_password": "",
    })


@pytest.fixture
def api(crm_api, cfg, monkeypatch):
    from app.main import app

    # The deploy's own public URL comes from the environment (seed
    # `resolve_product_url`), not from igig code.
    monkeypatch.setenv("PRODUCT_URL_IGIG", "https://igig.noctus.test")
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
def comercial(api) -> dict[str, dict]:
    return {s["slug"]: s for s in api.get("/api/comercial/pipeline/stages").json()["data"]}


def _segredos_no(corpo: object, *segredos: str) -> bool:
    texto = json.dumps(corpo)
    return any(s in texto for s in segredos)


# ── Auth boundary ────────────────────────────────────────────────────
class TestAuthBoundary:
    def test_whatsapp_get_requires_auth(self, api):
        assert api.raw().get("/api/integracoes/leads/whatsapp").status_code == 401

    def test_whatsapp_put_requires_auth(self, api):
        assert api.raw().put("/api/integracoes/leads/whatsapp", json={}).status_code == 401

    def test_meta_get_requires_auth(self, api):
        assert api.raw().get("/api/integracoes/leads/meta").status_code == 401

    def test_meta_put_requires_auth(self, api):
        assert api.raw().put("/api/integracoes/leads/meta", json={}).status_code == 401

    def test_writes_are_admin_only(self, api):
        resp = api.put("/api/integracoes/leads/whatsapp", json={"base_url": "http://waha:3000"})
        assert resp.status_code == 403


# ── WhatsApp (WAHA) setup ────────────────────────────────────────────
class TestWhatsappConfig:
    def test_unconfigured_status(self, api):
        resp = api.get("/api/integracoes/leads/whatsapp")
        assert resp.status_code == 200
        dados = resp.json()["data"]
        assert dados["configurado"] is False and dados["webhook_url"] is None
        assert dados["hmac_configurado"] is True and dados["cofre_configurado"] is True

    def test_save_never_returns_the_key_and_mints_a_stable_webhook(self, admin, igig_db):
        resp = admin.put("/api/integracoes/leads/whatsapp", json={
            "base_url": "http://waha:3000/", "api_key": "waha-key-secreta", "session": "agencia"})
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        assert not _segredos_no(resp.json(), "waha-key-secreta")
        assert dados["configurado"] is True and dados["api_key_configurada"] is True
        assert dados["base_url"] == "http://waha:3000" and dados["session"] == "agencia"
        assert dados["webhook_url"].startswith(f"https://igig.noctus.test/api/webhooks/waha/{ORG}.")

        [row] = [r for r in igig_db.table("integracao")._data if r["canal"] == "whatsapp"]
        assert "waha-key-secreta" not in json.dumps(row), "stored encrypted, never plaintext"

        # Editing without a key keeps the key AND the already-pasted URL.
        de_novo = admin.put("/api/integracoes/leads/whatsapp",
                            json={"base_url": "http://waha2:3000", "session": "agencia"})
        assert de_novo.json()["data"]["webhook_url"] == dados["webhook_url"]
        assert de_novo.json()["data"]["api_key_configurada"] is True

    def test_save_without_the_vault_key_is_refused(self, admin, cfg):
        from app.main import app

        app.dependency_overrides[get_settings] = lambda: cfg.model_copy(update={"igig_cofre_key": ""})
        resp = admin.put("/api/integracoes/leads/whatsapp",
                         json={"base_url": "http://waha:3000", "api_key": "k"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "cofre_nao_configurado"


# ── WAHA webhook ─────────────────────────────────────────────────────
def _mensagem(chat="5511994573387@c.us", texto="Oi, quero um orçamento", **extra):
    return {"event": "message", "session": "agencia",
            "payload": {"id": "wamid-1", "from": chat, "chatId": chat, "body": texto,
                        "notifyName": "Carla Doces", **extra}}


def _post_waha(api, token, corpo, *, segredo=HMAC_WAHA):
    bruto = json.dumps(corpo).encode()
    cabecalhos = {"content-type": "application/json"}
    if segredo:
        cabecalhos["X-Webhook-Hmac-SHA256"] = compute_hmac_sha256_hex(bruto, segredo)
    return api.raw().post(f"/api/webhooks/waha/{token}", content=bruto, headers=cabecalhos)


class TestWahaWebhook:
    @pytest.fixture
    def token(self, admin) -> str:
        url = admin.put("/api/integracoes/leads/whatsapp",
                        json={"base_url": "http://waha:3000", "api_key": "k"}).json()["data"]["webhook_url"]
        return url.rsplit("/", 1)[-1]

    def test_first_message_creates_lead_and_negocio_once(self, admin, token, igig_db, comercial):
        admin.post("/api/automacoes", json={
            "pipeline": "comercial", "stage_id": comercial["leads"]["id"],
            "gatilho": "entrada_etapa",
            "acao": {"tipo": "criar_checklist", "params": {"titulo": "Responder {nome}"}},
        })
        resp = _post_waha(admin, token, _mensagem())
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "criado"

        [lead] = igig_db.table("lead")._data
        assert lead["origem"] == "whatsapp" and lead["waha_chat_id"] == "5511994573387@c.us"
        assert lead["telefone"] == "+5511994573387" and lead["nome"] == "Carla Doces"
        [negocio] = igig_db.table("negocio")._data
        assert negocio["lead_id"] == lead["id"]
        assert negocio["etapa_id"] == comercial["leads"]["id"]
        assert [c["titulo"] for c in igig_db.table("negocio_checklists")._data] == ["Responder Carla Doces"]

        segunda = _post_waha(admin, token, _mensagem(texto="alô?"))
        assert segunda.status_code == 200
        assert segunda.json()["status"] == "existente"
        assert len(igig_db.table("lead")._data) == 1 and len(igig_db.table("negocio")._data) == 1

    def test_bad_signature_is_401_and_writes_nothing(self, api, token, igig_db):
        resp = _post_waha(api, token, _mensagem(), segredo="outro-segredo")
        assert resp.status_code == 401
        assert igig_db.table("lead")._data == []

    def test_unknown_or_malformed_token_is_404(self, api, token, igig_db):
        org, _sep, _segredo = token.partition(".")
        assert _post_waha(api, f"{org}.nao-e-este", _mensagem()).status_code == 404
        assert _post_waha(api, "sem-ponto", _mensagem()).status_code == 404
        assert _post_waha(api, "nao-uuid.abc", _mensagem()).status_code == 404
        assert igig_db.table("lead")._data == []

    def test_own_and_group_messages_are_not_leads(self, api, token, igig_db):
        proprio = _post_waha(api, token, _mensagem(fromMe=True))
        assert proprio.status_code == 200 and proprio.json()["status"] == "ignorado"
        grupo = _post_waha(api, token, _mensagem(chat="120363@g.us"))
        assert grupo.status_code == 200 and grupo.json()["status"] == "ignorado"
        assert igig_db.table("lead")._data == []

    def test_session_events_are_ignored(self, api, token):
        resp = _post_waha(api, token, {"event": "session.status", "payload": {"status": "WORKING"}})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignorado"


# ── Meta Lead Ads setup ──────────────────────────────────────────────
class TestMetaConfig:
    def test_save_never_returns_secrets(self, admin):
        resp = admin.put("/api/integracoes/leads/meta", json={
            "page_id": PAGINA, "verify_token": "verifica-12345",
            "page_access_token": "EAAG-page-token", "app_secret": APP_SECRET})
        assert resp.status_code == 200, resp.text
        assert not _segredos_no(resp.json(), "verifica-12345", "EAAG-page-token", APP_SECRET)
        dados = resp.json()["data"]
        assert dados["configurado"] is True and dados["app_secret_origem"] == "org"
        assert dados["webhook_url"] == "https://igig.noctus.test/api/webhooks/meta/leadgen"

    def test_first_save_needs_the_verify_and_page_tokens(self, admin):
        resp = admin.put("/api/integracoes/leads/meta", json={"page_id": PAGINA})
        assert resp.status_code == 422
        assert resp.json()["code"] == "verify_token_obrigatorio"

    def test_a_page_belongs_to_one_org(self, admin, igig_db):
        igig_db.table("integracao").insert({
            "org_id": OUTRA_ORG, "canal": "meta_leads", "ativo": True,
            "config": {"page_id": PAGINA}}).execute()
        resp = admin.put("/api/integracoes/leads/meta", json={
            "page_id": PAGINA, "verify_token": "verifica-12345", "page_access_token": "t"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "pagina_em_uso"


# ── Meta Lead Ads webhook ────────────────────────────────────────────
def _entrega(leadgen_id="lg-1", pagina=PAGINA):
    return {"object": "page", "entry": [{"id": pagina, "time": 1, "changes": [{
        "field": "leadgen",
        "value": {"leadgen_id": leadgen_id, "page_id": pagina, "form_id": "f-1",
                  "created_time": 1727000000}}]}]}


def _post_meta(api, corpo, *, segredo=APP_SECRET):
    bruto = json.dumps(corpo).encode()
    cabecalhos = {"content-type": "application/json"}
    if segredo:
        cabecalhos["X-Hub-Signature-256"] = "sha256=" + compute_hmac_sha256_hex(bruto, segredo)
    return api.raw().post("/api/webhooks/meta/leadgen", content=bruto, headers=cabecalhos)


class TestMetaWebhook:
    @pytest.fixture
    def meta(self, admin):
        from app.main import app
        from app.routers.lead_webhooks_router import get_meta_adapter_factory

        resp = admin.put("/api/integracoes/leads/meta", json={
            "page_id": PAGINA, "verify_token": "verifica-12345",
            "page_access_token": "EAAG-page-token", "app_secret": APP_SECRET})
        assert resp.status_code == 200, resp.text
        adaptador = FakeMetaAdapter()
        adaptador.seed(leads_by_id={"lg-1": Lead(
            id="lg-1", form_id="f-1", campaign_name="Black Friday",
            field_data=[
                LeadFieldEntry(name="full_name", values=["Bruno Lima"]),
                LeadFieldEntry(name="email", values=["bruno@lima.com"]),
                LeadFieldEntry(name="phone_number", values=["+5511988887777"]),
                LeadFieldEntry(name="qual_seu_nicho", values=["Restaurante"]),
            ])})
        tokens: list[str] = []

        def fabrica(token):
            tokens.append(token)
            return adaptador

        app.dependency_overrides[get_meta_adapter_factory] = lambda: fabrica
        yield tokens
        app.dependency_overrides.pop(get_meta_adapter_factory, None)

    def test_handshake_echoes_only_for_the_right_token(self, api, meta):
        ok = api.raw().get("/api/webhooks/meta/leadgen", params={
            "hub.mode": "subscribe", "hub.verify_token": "verifica-12345", "hub.challenge": "abc-123"})
        assert ok.status_code == 200 and ok.text == "abc-123"
        errado = api.raw().get("/api/webhooks/meta/leadgen", params={
            "hub.mode": "subscribe", "hub.verify_token": "outro", "hub.challenge": "abc-123"})
        assert errado.status_code == 403

    def test_signed_delivery_creates_the_lead_once(self, api, meta, igig_db, comercial):
        resp = _post_meta(api, _entrega())
        assert resp.status_code == 200, resp.text
        [resultado] = resp.json()["resultados"]
        assert resultado["status"] == "criado"
        assert meta == ["EAAG-page-token"], "the Page's own token reads the lead"

        [lead] = igig_db.table("lead")._data
        assert lead["origem"] == "meta_ads" and lead["meta_lead_id"] == "lg-1"
        assert (lead["nome"], lead["email"], lead["telefone"]) == (
            "Bruno Lima", "bruno@lima.com", "+5511988887777")
        assert lead["especificacoes"]["respostas"] == {"qual_seu_nicho": "Restaurante"}
        assert lead["especificacoes"]["meta"]["campaign_name"] == "Black Friday"
        [negocio] = igig_db.table("negocio")._data
        assert negocio["etapa_id"] == comercial["leads"]["id"]

        repetida = _post_meta(api, _entrega())
        assert repetida.json()["resultados"][0]["status"] == "existente"
        assert len(igig_db.table("lead")._data) == 1

    def test_unsigned_or_wrongly_signed_is_401(self, api, meta, igig_db):
        assert _post_meta(api, _entrega(), segredo=None).status_code == 401
        assert _post_meta(api, _entrega(), segredo="outro").status_code == 401
        assert igig_db.table("lead")._data == []

    def test_no_secret_anywhere_is_401_not_a_bypass(self, api, igig_db):
        """Unknown Page, no platform secret: refuse — never accept unsigned PII."""
        assert _post_meta(api, _entrega(pagina="999"), segredo="x").status_code == 401

    def test_graph_failure_is_recorded_on_the_channel(self, api, meta, igig_db):
        resp = _post_meta(api, _entrega(leadgen_id="lg-desconhecido"))
        assert resp.status_code == 200
        assert resp.json()["resultados"][0]["status"] == "erro"
        [row] = [r for r in igig_db.table("integracao")._data if r["canal"] == "meta_leads"]
        assert "lg-desconhecido" in row["ultimo_erro"]
        assert igig_db.table("lead")._data == []
