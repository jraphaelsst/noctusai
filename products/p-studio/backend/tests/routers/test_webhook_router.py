"""Webhook do provedor de cobrança.

É a única rota pública que escreve, e é onde mora a maior parte do risco real
da integração. O que se testa aqui, em ordem de importância:

1. **Ninguém sem o token escreve nada.**
2. **Quase tudo responde 200.** O Asaas interrompe a fila de entrega após 15
   respostas não-2xx consecutivas — um evento que não sabemos tratar não pode
   custar a conciliação de todos os outros pagamentos.
3. **Reentrega não duplica efeito.** Retry do provedor é rotina.
4. **O funil e o banco não brigam por `pago_em`.**
"""
import pytest

from app.config import settings
from app.database import get_admin_client
from app.dependencies import get_provedor_cobranca
from app.main import app
from app.providers.fake import ProvedorFake
from tests.conftest import dias, make_row, seed_basico

ROTA = "/api/integracoes/asaas/webhook"
TOKEN = {"asaas-access-token": "token-de-webhook-de-teste"}


@pytest.fixture
def provedor():
    p = ProvedorFake()
    app.dependency_overrides[get_provedor_cobranca] = lambda: p
    yield p
    app.dependency_overrides.pop(get_provedor_cobranca, None)


@pytest.fixture
def admin_db(fake_db):
    """O webhook usa o client service-role — aqui ele aponta para o FakeDB.

    O service de credenciais entra pelo SEAM (`Depends`), não por
    monkey-patch: `get_credenciais_service` resolve `get_admin_client` no
    namespace de `app.dependencies`, então trocar o nome no módulo do router
    nunca o alcançava — e as 17 rotas de webhook morriam num 400
    ("SUPABASE_SERVICE_ROLE_KEY não configurada") que nada tinha a ver com o
    que os testes afirmam. Injetar é o que este repositório manda fazer
    (`KB § PATTERNS/compliance/testing.md`); remendar o nosso próprio módulo
    é justamente o que ele proíbe.

    `get_admin_client` continua trocado no módulo porque `webhook_asaas` o
    chama direto para montar o `IntegracaoService` — um seam separado, ainda
    por fazer, anotado abaixo.
    """
    from app.dependencies import get_credenciais_service_opcional
    from app.services.credenciais import EncryptionNotConfigured
    from app.services.credenciais_service import CredenciaisService

    def _servico_sobre_o_fake():
        """Mirrors the real factory's tolerance over the FakeDB.

        Built lazily and per-request: `CredenciaisService.__init__` raises
        `EncryptionNotConfigured` when the suite runs without an
        `ENCRYPTION_KEY` (it usually does), and constructing it eagerly in the
        fixture would blow up every test at override time instead of
        exercising the None path production actually takes.
        """
        try:
            return CredenciaisService(fake_db, settings.org_id)
        except EncryptionNotConfigured:
            return None

    app.dependency_overrides[get_admin_client] = lambda: fake_db
    app.dependency_overrides[get_credenciais_service_opcional] = _servico_sobre_o_fake

    # NOC-REMEDIATE[di-seam]: `webhook_asaas` ainda chama `get_admin_client()`
    # inline, então este patch de módulo continua necessário. Trocar por
    # `Depends` remove o último monkey-patch deste arquivo.
    import app.routers.integracoes_router as mod

    original = mod.get_admin_client
    mod.get_admin_client = lambda: fake_db
    yield fake_db
    mod.get_admin_client = original
    app.dependency_overrides.pop(get_admin_client, None)
    app.dependency_overrides.pop(get_credenciais_service_opcional, None)


def _evento(lancamento_id: str, tipo: str = "liquidada", **cobranca) -> dict:
    base = {
        "id": "pay_001",
        "referencia_externa": lancamento_id,
        "valor": 1800,
        "pago_em": "2026-09-12",
    }
    base.update(cobranca)
    return {"id": f"evt_{tipo}_{lancamento_id[:8]}", "tipo": tipo, "cobranca": base}


def _lancamento(fake_db, **overrides) -> dict:
    seed = seed_basico(fake_db)
    campos = {
        "cliente_id": seed["cliente"]["id"],
        "valor": 1800,
        "vencimento": dias(7),
        "status": "faturado",
    }
    campos.update(overrides)
    linha = make_row("lancamentos", **campos)
    fake_db.data["lancamentos"] = [linha]
    return linha


# ── autenticação ─────────────────────────────────────────────────────────

def test_sem_token_da_401(client_anon, admin_db, provedor):
    res = client_anon.post(ROTA, json={"tipo": "liquidada"})
    assert res.status_code == 401


def test_token_errado_da_401(client_anon, admin_db, provedor):
    res = client_anon.post(
        ROTA, json={"tipo": "liquidada"}, headers={"asaas-access-token": "errado"}
    )
    assert res.status_code == 401


def test_token_errado_nao_grava_evento(client_anon, admin_db, provedor):
    client_anon.post(ROTA, json={"tipo": "liquidada"},
                     headers={"asaas-access-token": "errado"})
    assert admin_db.data.get("provedor_eventos", []) == []


def test_get_nao_e_permitido(client_anon):
    assert client_anon.get(ROTA).status_code == 405


# ── liquidação ───────────────────────────────────────────────────────────

def test_liquidacao_da_baixa_no_lancamento(client_anon, admin_db, provedor):
    lancamento = _lancamento(admin_db)

    res = client_anon.post(ROTA, json=_evento(lancamento["id"]), headers=TOKEN)

    assert res.status_code == 200
    assert res.json()["efeito"] == "recebido"

    linha = admin_db.data["lancamentos"][0]
    assert linha["status"] == "recebido"
    assert linha["pago_em"] == "2026-09-12"


def test_liquidacao_grava_o_espelho_do_provedor(client_anon, admin_db, provedor):
    lancamento = _lancamento(admin_db)

    client_anon.post(ROTA, json=_evento(lancamento["id"]), headers=TOKEN)

    linha = admin_db.data["lancamentos"][0]
    assert linha["provedor"] == "fake"
    assert linha["provedor_cobranca_id"] == "pay_001"
    assert linha["provedor_status"] == "liquidada"
    assert linha["sincronizado_em"]


def test_evento_e_gravado_com_payload_cru(client_anon, admin_db, provedor):
    lancamento = _lancamento(admin_db)
    corpo = _evento(lancamento["id"])

    client_anon.post(ROTA, json=corpo, headers=TOKEN)

    eventos = admin_db.data["provedor_eventos"]
    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "liquidada"       # tipo cru do provedor
    assert eventos[0]["payload"] == corpo          # nada perdido
    assert eventos[0]["efeito"] == "recebido"
    assert eventos[0]["processado_em"]
    assert eventos[0]["lancamento_id"] == lancamento["id"]


# ── idempotência ─────────────────────────────────────────────────────────

def test_reentrega_nao_grava_segundo_evento(client_anon, admin_db, provedor):
    """Retry do provedor é rotina — não pode virar linha duplicada."""
    lancamento = _lancamento(admin_db)
    corpo = _evento(lancamento["id"])

    primeira = client_anon.post(ROTA, json=corpo, headers=TOKEN)
    segunda = client_anon.post(ROTA, json=corpo, headers=TOKEN)

    assert primeira.json()["status"] == "processado"
    assert segunda.status_code == 200
    assert segunda.json()["status"] == "duplicado"
    assert len(admin_db.data["provedor_eventos"]) == 1


def test_reentrega_nao_reescreve_pago_em(client_anon, admin_db, provedor):
    lancamento = _lancamento(admin_db)
    corpo = _evento(lancamento["id"])

    client_anon.post(ROTA, json=corpo, headers=TOKEN)
    corpo_novo = dict(corpo)
    corpo_novo["cobranca"] = {**corpo["cobranca"], "pago_em": "2026-12-25"}
    corpo_novo["id"] = "evt_outro"  # id diferente: passa pelo dedupe
    client_anon.post(ROTA, json=corpo_novo, headers=TOKEN)

    assert admin_db.data["lancamentos"][0]["pago_em"] == "2026-09-12"


def test_lancamento_ja_recebido_pelo_funil_e_ignorado(client_anon, admin_db, provedor):
    """O conflito dos três escritores: o primeiro a liquidar vence."""
    lancamento = _lancamento(admin_db, status="recebido", pago_em="2026-01-15")

    res = client_anon.post(ROTA, json=_evento(lancamento["id"]), headers=TOKEN)

    assert res.json()["efeito"] == "ignorado_ja_recebido"
    assert admin_db.data["lancamentos"][0]["pago_em"] == "2026-01-15"


def test_ja_recebido_ainda_assim_grava_o_espelho(client_anon, admin_db, provedor):
    """Descartar a versão do banco é como a conciliação apodrece em silêncio."""
    lancamento = _lancamento(admin_db, status="recebido", pago_em="2026-01-15")

    client_anon.post(ROTA, json=_evento(lancamento["id"]), headers=TOKEN)

    assert admin_db.data["lancamentos"][0]["provedor_status"] == "liquidada"
    assert admin_db.data["lancamentos"][0]["sincronizado_em"]


# ── o que NÃO pode virar erro ────────────────────────────────────────────

def test_referencia_desconhecida_responde_200(client_anon, admin_db, provedor):
    """Cobrança criada no painel do provedor, ou lançamento apagado.
    404 aqui pausaria a fila de entrega."""
    seed_basico(admin_db)
    admin_db.data["lancamentos"] = []

    res = client_anon.post(ROTA, json=_evento("nao-existe"), headers=TOKEN)

    assert res.status_code == 200
    assert res.json()["efeito"] == "sem_lancamento"
    assert admin_db.data["provedor_eventos"][0]["efeito"] == "sem_lancamento"


def test_evento_desconhecido_responde_200_e_fica_registrado(
    client_anon, admin_db, provedor
):
    seed_basico(admin_db)

    res = client_anon.post(
        ROTA, json={"id": "evt_x", "tipo": "COISA_NOVA"}, headers=TOKEN
    )

    assert res.status_code == 200
    assert res.json()["status"] == "ignorado"
    assert len(admin_db.data["provedor_eventos"]) == 1


def test_corpo_vazio_responde_200(client_anon, admin_db, provedor):
    res = client_anon.post(ROTA, json={}, headers=TOKEN)
    assert res.status_code == 200


def test_evento_nao_liquidado_apenas_espelha(client_anon, admin_db, provedor):
    lancamento = _lancamento(admin_db)

    res = client_anon.post(
        ROTA, json=_evento(lancamento["id"], tipo="vencida"), headers=TOKEN
    )

    assert res.json()["efeito"] == "ignorado"
    assert admin_db.data["lancamentos"][0]["status"] == "faturado"
    assert admin_db.data["lancamentos"][0]["provedor_status"] == "pendente"


def test_falha_ao_aplicar_fica_estacionada_e_responde_200(
    client_anon, admin_db, provedor, monkeypatch
):
    """Evento envenenado não pode derrubar a fila dos outros pagamentos."""
    lancamento = _lancamento(admin_db)

    import app.services.integracao_service as mod

    def explodir(*args, **kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(mod, "registrar_recebimento", explodir)

    res = client_anon.post(ROTA, json=_evento(lancamento["id"]), headers=TOKEN)

    assert res.status_code == 200
    assert res.json()["status"] == "erro_registrado"

    evento = admin_db.data["provedor_eventos"][0]
    assert evento["efeito"] == "erro"
    assert "banco fora do ar" in evento["erro"]
    # `processado_em` NULL é o que a rota de reprocessamento consulta.
    assert evento["processado_em"] is None


# ── reprocessamento ──────────────────────────────────────────────────────

def test_reprocessar_drena_a_fila(client, admin_db, provedor, monkeypatch):
    # Um TestClient só: a fixture `client_anon` limpa os overrides, então
    # pedir os dois no mesmo teste derrubaria a autenticação do `client`. O
    # webhook não exige token de usuário, então o client autenticado serve.
    lancamento = _lancamento(admin_db)

    import app.services.integracao_service as mod

    original = mod.registrar_recebimento
    monkeypatch.setattr(mod, "registrar_recebimento",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("falhou")))
    client.post(ROTA, json=_evento(lancamento["id"]), headers=TOKEN)
    assert admin_db.data["provedor_eventos"][0]["processado_em"] is None

    monkeypatch.setattr(mod, "registrar_recebimento", original)
    res = client.post("/api/integracoes/reprocessar")

    assert res.status_code == 200
    assert res.json() == {"total": 1, "ok": 1, "erro": 0}
    assert admin_db.data["lancamentos"][0]["status"] == "recebido"
    assert admin_db.data["provedor_eventos"][0]["processado_em"]


def test_reprocessar_exige_autenticacao(client_anon):
    assert client_anon.post("/api/integracoes/reprocessar").status_code == 401


def test_listar_eventos_exige_autenticacao(client_anon):
    assert client_anon.get("/api/integracoes/eventos").status_code == 401


def test_webhook_sem_token_configurado_da_503(client_anon, admin_db, provedor, monkeypatch):
    """Falha nossa, não de quem chamou — e explícita no log."""
    monkeypatch.setattr(settings, "asaas_webhook_token", "")

    res = client_anon.post(ROTA, json={}, headers=TOKEN)

    assert res.status_code == 503
    # A mensagem mudou de "defina ASAAS_WEBHOOK_TOKEN" para o caminho que hoje
    # resolve de verdade — a credencial vive cifrada no banco e é cadastrada
    # pela tela, não mais por env var (migration 008). A PROPRIEDADE testada é
    # a mesma: sem segredo configurado, falha FECHADA e a culpa é nossa (503),
    # nunca 200 e nunca 401.
    assert "Integrações" in res.json()["error"]["message"]
