"""CRM, orçamentos e onboarding — Módulo 1.

Three properties carry the weight:
  1. the PUBLIC lead form is write-only and cannot be used to read anything;
  2. the calculator refuses to quote confidently without custo/hora data,
     because quoting below cost loses money on every job it prices;
  3. the signature webhook is idempotent — providers retry, and re-running the
     side effects would re-activate a client and re-convert a lead.
"""
import pytest
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios
from app.store import aplicar_schema_sqlite, get_repositorios, get_repositorios_admin

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def api(client, repos, monkeypatch):
    from app.config import settings
    from app.main import app
    import app.storage as storage_mod

    monkeypatch.setattr(settings, "igig_storage_kind", "fake")
    storage_mod.reset_storage()
    app.dependency_overrides[get_repositorios] = lambda: repos
    app.dependency_overrides[get_repositorios_admin] = lambda: repos
    yield client
    app.dependency_overrides.pop(get_repositorios, None)
    app.dependency_overrides.pop(get_repositorios_admin, None)
    storage_mod.reset_storage()


def _com_equipe(repos, custo_hora=100.0):
    funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": custo_hora})
    repos.profissional.criar(ORG, {"nome": "Ana", "funcao_id": funcao["id"], "ativo": True})


class TestFormularioPublico:
    def test_accepts_a_lead_without_auth(self, api):
        resp = api.raw().post("/api/comercial/leads/publico", json={
            "org_id": ORG, "nome": "João", "email": "joao@example.com",
            "nicho": "padaria", "dores": "pouco alcance",
        })
        assert resp.status_code == 201
        assert resp.json()["ok"] is True

    def test_returns_no_stored_data(self, api):
        """An anonymous endpoint echoing records back is a scraping surface."""
        resp = api.raw().post("/api/comercial/leads/publico",
                              json={"org_id": ORG, "nome": "João"})
        corpo = resp.json()
        assert "id" not in corpo
        assert "João" not in str(corpo)

    def test_the_lead_is_actually_stored(self, api, repos):
        api.raw().post("/api/comercial/leads/publico", json={"org_id": ORG, "nome": "João"})
        leads = repos.lead.listar(ORG)
        assert [l["nome"] for l in leads] == ["João"]
        assert leads[0]["status"] == "novo"

    def test_rejects_unknown_fields(self, api):
        resp = api.raw().post("/api/comercial/leads/publico",
                              json={"org_id": ORG, "nome": "J", "admin": True})
        assert resp.status_code == 422

    def test_listing_leads_still_requires_auth(self, api):
        assert api.raw().get("/api/comercial/leads").status_code == 401


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


class TestCalculadoraDeEscopo:
    def test_prices_from_the_teams_real_hourly_cost(self, api, repos):
        _com_equipe(repos, custo_hora=100.0)
        resp = api.post("/api/comercial/estimar?margem_alvo=50",
                        json=[{"formato": "feed", "quantidade": 10}])
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["horas"] == 20.0          # 10 × 2h
        assert corpo["custo"] == 2000.0        # 20h × R$100
        assert corpo["preco_sugerido"] == 4000.0  # 50% margin ⇒ 2× cost
        assert corpo["alertas"] == []

    def test_hour_override_is_respected(self, api, repos):
        _com_equipe(repos, custo_hora=100.0)
        corpo = api.post("/api/comercial/estimar",
                         json=[{"formato": "feed", "quantidade": 2,
                                "horas_unitarias": 5}]).json()
        assert corpo["horas"] == 10.0

    def test_without_custo_hora_it_warns_loudly(self, api, repos):
        """Quoting below cost loses money on every job — say so, don't guess."""
        corpo = api.post("/api/comercial/estimar",
                         json=[{"formato": "feed", "quantidade": 10}]).json()
        assert corpo["preco_sugerido"] == 0.0
        assert corpo["alertas"]
        assert "NÃO deve ser usado" in corpo["alertas"][-1]

    def test_professionals_without_a_rate_are_excluded_not_zeroed(self, api, repos):
        """Averaging in a zero would drag the mean below cost."""
        _com_equipe(repos, custo_hora=100.0)
        repos.profissional.criar(ORG, {"nome": "Sem rate", "ativo": True})
        corpo = api.post("/api/comercial/estimar",
                         json=[{"formato": "feed", "quantidade": 1}]).json()
        assert corpo["custo_hora_medio"] == 100.0
        assert any("excluídos" in a for a in corpo["alertas"])

    def test_margin_of_100_is_rejected(self, api, repos):
        _com_equipe(repos)
        assert api.post("/api/comercial/estimar?margem_alvo=100",
                        json=[{"formato": "feed", "quantidade": 1}]).status_code == 422

    def test_invalid_format_returns_422(self, api):
        assert api.post("/api/comercial/estimar",
                        json=[{"formato": "outdoor", "quantidade": 1}]).status_code == 422


class TestOrcamento:
    def test_stores_the_estimate_rather_than_recomputing(self, api, repos):
        """A proposal already sent must keep the numbers it was sent with."""
        _com_equipe(repos, custo_hora=100.0)
        criado = api.post("/api/comercial/orcamentos", json={
            "titulo": "Social media mensal",
            "itens": [{"formato": "feed", "quantidade": 10}],
        }).json()
        assert criado["preco_sugerido"] == 4000.0

        # Rate doubles afterwards — the stored proposal must not move.
        for f in repos.funcao.listar(ORG):
            repos.funcao.atualizar(ORG, str(f["id"]), {"custo_hora_padrao": 200.0})
        assert api.get("/api/comercial/orcamentos").json()[0]["preco_sugerido"] == 4000.0

    def test_director_may_price_below_the_suggestion(self, api, repos):
        """The spec explicitly allows overriding the calculator."""
        _com_equipe(repos, custo_hora=100.0)
        orc = api.post("/api/comercial/orcamentos", json={
            "titulo": "X", "itens": [{"formato": "feed", "quantidade": 10}],
        }).json()
        resp = api.post(f"/api/comercial/orcamentos/{orc['id']}/preco",
                        json={"preco_final": 3000.0})
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["preco_final"] == 3000.0
        # The suggestion is KEPT — the concession stays visible.
        assert corpo["preco_sugerido"] == 4000.0

    def test_unknown_orcamento_returns_404(self, api):
        assert api.post("/api/comercial/orcamentos/nao-existe/preco",
                        json={"preco_final": 1.0}).status_code == 404


class TestContratoEAssinatura:
    def _gerar(self, api, repos):
        cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol"})
        return cliente, api.post("/api/comercial/contratos/gerar", json={
            "cliente_id": cliente["id"], "valor_mensal": 5000.0,
            "posts_por_mes": 12, "clausulas": ["Prazo de 12 meses."],
        }).json()

    def test_generates_a_pdf_and_dispatches(self, api, repos):
        _cliente, corpo = self._gerar(api, repos)
        assert corpo["documento_key"].endswith("contrato.pdf")
        assert corpo["link_assinatura"]
        assert corpo["dry_run"] is True, "no provider credentials ⇒ dry run, surfaced"

    def test_the_stored_document_is_a_real_pdf(self, api, repos):
        """reportlab output, not a placeholder — check the magic bytes."""
        import app.storage as storage_mod
        from app.config import settings

        _cliente, corpo = self._gerar(api, repos)
        # Read back through the backend's own API rather than its internals.
        import anyio

        async def _ler():
            return await storage_mod.get_storage().get(
                bucket=settings.igig_storage_bucket, key=corpo["documento_key"]
            )

        stored = anyio.run(_ler)
        assert stored is not None
        assert stored.data.startswith(b"%PDF")

    def test_contract_starts_awaiting_signature(self, api, repos):
        _cliente, corpo = self._gerar(api, repos)
        contrato = repos.contrato.buscar(ORG, corpo["contrato_id"])
        assert contrato["status"] == "aguardando_assinatura"

    def test_unknown_client_returns_404(self, api):
        resp = api.post("/api/comercial/contratos/gerar",
                        json={"cliente_id": "nao-existe", "valor_mensal": 1.0})
        assert resp.status_code == 404

    def test_signature_activates_contract_and_client(self, api, repos):
        """The Módulo 1 automation, end to end."""
        cliente, corpo = self._gerar(api, repos)
        resp = api.raw().post("/api/comercial/assinatura/webhook", json={
            "external_id": corpo["external_id"], "evento": "assinado",
        })
        assert resp.status_code == 200
        assert resp.json()["cliente_ativado"] is True
        assert repos.contrato.buscar(ORG, corpo["contrato_id"])["status"] == "ativo"
        assert repos.cliente.buscar(ORG, cliente["id"])["status"] == "ativo"

    def test_webhook_is_idempotent(self, api, repos):
        """Providers retry — a second delivery must not re-run side effects."""
        _cliente, corpo = self._gerar(api, repos)
        payload = {"external_id": corpo["external_id"], "evento": "assinado"}
        api.raw().post("/api/comercial/assinatura/webhook", json=payload)
        segunda = api.raw().post("/api/comercial/assinatura/webhook", json=payload)
        assert segunda.status_code == 200
        assert segunda.json()["ja_processado"] is True

    def test_webhook_needs_no_auth(self, api, repos):
        """The vendor has no noc session; the external_id is the credential."""
        _cliente, corpo = self._gerar(api, repos)
        resp = api.raw().post("/api/comercial/assinatura/webhook", json={
            "external_id": corpo["external_id"], "evento": "assinado",
        })
        assert resp.status_code == 200

    def test_unknown_external_id_returns_404(self, api):
        resp = api.raw().post("/api/comercial/assinatura/webhook", json={
            "external_id": "nao.existe", "evento": "assinado",
        })
        assert resp.status_code == 404

    def test_malformed_external_id_returns_404(self, api):
        resp = api.raw().post("/api/comercial/assinatura/webhook", json={
            "external_id": "sem-org", "evento": "assinado",
        })
        assert resp.status_code == 404

    def test_refusal_does_not_activate(self, api, repos):
        cliente, corpo = self._gerar(api, repos)
        api.raw().post("/api/comercial/assinatura/webhook", json={
            "external_id": corpo["external_id"], "evento": "recusado",
        })
        assert repos.contrato.buscar(ORG, corpo["contrato_id"])["status"] != "ativo"
        assert repos.cliente.buscar(ORG, cliente["id"])["status"] == "prospect"
