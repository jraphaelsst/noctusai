"""Credenciais do provedor — cifra em repouso, máscara na resposta, troca de
ambiente.

O que estes testes protegem, em ordem de gravidade:

1. **A chave nunca volta em claro** por `GET /credenciais`. É a razão de a
   máscara existir; se um refactor a remover, é aqui que quebra.
2. **O que está gravado está CIFRADO.** O teste lê a linha crua do fake e
   exige que a chave não apareça nela — sem isso "usamos Fernet" seria uma
   afirmação sobre o código, não sobre o dado.
3. **Trocar a chave invalida o adapter memoizado.** O sintoma que isto impede
   ("salvei a chave nova e continua dando 401") não tem log que o denuncie.
4. **Não dá para ativar um ambiente sem credencial** — senão o erro aparece
   longe daqui, na primeira tentativa de cobrar.
"""
import json

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.services.credenciais import chave_provider

ROTA = "/api/integracoes/credenciais"

CHAVE_SANDBOX = "$aact_hmlg_" + "a" * 60
CHAVE_PRODUCAO = "$aact_prod_" + "b" * 60


@pytest.fixture
def cifra(monkeypatch):
    """Uma `ENCRYPTION_KEY` real para a suíte — Fernet de verdade, não mock.

    Cifra é barata e determinística; um fake aqui exercitaria código
    diferente do que roda em produção e não provaria nada sobre o dado
    gravado, que é justamente o que estes testes medem.
    """
    chave = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "encryption_key", chave)
    return chave


@pytest.fixture
def admin(fake_db, monkeypatch):
    """Aponta `get_admin_client` para o FakeDB, nos DOIS módulos que o chamam.

    A tabela de credenciais não tem policy para `authenticated` (migration
    008), então o service só existe sobre um client service-role — em teste,
    o fake.

    Trocar só em `app.dependencies` não basta: `integracoes_router` fez
    `from app.database import get_admin_client`, e um `from … import` liga o
    nome ao MÓDULO QUE IMPORTOU. O router seguia chamando o real, que sem
    `SUPABASE_SERVICE_ROLE_KEY` responde 400 — e o sintoma era um webhook
    devolvendo 400 num teste que falava de token. Mesma técnica de
    `test_webhook_router.py::admin_db`, pelo mesmo motivo.
    """
    import app.dependencies as deps
    import app.routers.integracoes_router as router_mod

    monkeypatch.setattr(deps, "get_admin_client", lambda *a, **k: fake_db)
    monkeypatch.setattr(router_mod, "get_admin_client", lambda *a, **k: fake_db)
    return fake_db


# ── leitura ──────────────────────────────────────────────────────────────

def test_status_sem_nada_cadastrado(client, admin, cifra):
    res = client.get(ROTA)

    assert res.status_code == 200
    corpo = res.json()
    assert corpo["provedor"] == "asaas"
    # Default deliberado: um deploy que não escolheu não pode emitir boleto
    # real por omissão.
    assert corpo["ambiente_ativo"] == "sandbox"
    assert [a["ambiente"] for a in corpo["ambientes"]] == ["sandbox", "producao"]
    assert all(a["configurado"] is False for a in corpo["ambientes"])


def test_sem_encryption_key_a_rota_recusa_alto(client, admin, monkeypatch):
    """503 e a frase que diz o que gerar — nunca 500 opaco, nunca gravar em claro."""
    monkeypatch.setattr(settings, "encryption_key", "")

    res = client.get(ROTA)

    assert res.status_code == 503
    assert "ENCRYPTION_KEY" in res.json()["error"]["message"]


# ── escrita ──────────────────────────────────────────────────────────────

def test_salvar_cifra_a_chave_no_banco(client, admin, cifra):
    res = client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})

    assert res.status_code == 200
    linhas = admin.data["provedor_credenciais"]
    assert len(linhas) == 1

    # 🔴 A asserção que importa: a chave NÃO está na linha gravada.
    bruto = json.dumps(linhas[0])
    assert CHAVE_SANDBOX not in bruto

    # E o que está lá decifra de volta para o bundle correto.
    aberto = json.loads(
        Fernet(cifra.encode()).decrypt(linhas[0]["encrypted_tokens"].encode())
    )
    assert aberto["api_key"] == CHAVE_SANDBOX
    assert aberto["webhook_token"]  # gerado automaticamente


def test_a_resposta_nunca_carrega_a_chave(client, admin, cifra):
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})

    corpo = client.get(ROTA).json()

    assert CHAVE_SANDBOX not in json.dumps(corpo)
    sandbox = next(a for a in corpo["ambientes"] if a["ambiente"] == "sandbox")
    assert sandbox["configurado"] is True
    assert sandbox["api_key_mascarada"].startswith("$aact_hmlg_")
    assert sandbox["api_key_mascarada"].endswith(CHAVE_SANDBOX[-4:])
    assert sandbox["webhook_token_configurado"] is True


def test_chave_do_ambiente_errado_e_recusada(client, admin, cifra):
    """O prefixo declara o ambiente. Uma chave de produção salva como sandbox
    devolveria 401 `invalid_environment` na primeira cobrança — longe daqui."""
    res = client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_PRODUCAO})

    assert res.status_code == 422
    assert "producao" in res.json()["error"]["message"]
    assert "provedor_credenciais" not in admin.data or not admin.data["provedor_credenciais"]


def test_trocar_a_chave_substitui_a_linha_em_vez_de_empilhar(client, admin, cifra):
    """UPSERT na chave natural — duas linhas para o mesmo (org, provider)
    fariam a leitura pegar a errada."""
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})
    nova = "$aact_hmlg_" + "c" * 60
    client.put(f"{ROTA}/sandbox", json={"api_key": nova})

    linhas = admin.data["provedor_credenciais"]
    assert len(linhas) == 1
    aberto = json.loads(
        Fernet(cifra.encode()).decrypt(linhas[0]["encrypted_tokens"].encode())
    )
    assert aberto["api_key"] == nova


def test_trocar_a_chave_preserva_o_token_do_webhook(client, admin, cifra):
    """Trocar a chave de API não pode derrubar um webhook já cadastrado no
    painel do Asaas."""
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})
    antes = client.get(f"{ROTA}/sandbox/webhook-token").json()["webhook_token"]

    client.put(f"{ROTA}/sandbox", json={"api_key": "$aact_hmlg_" + "d" * 60})
    depois = client.get(f"{ROTA}/sandbox/webhook-token").json()["webhook_token"]

    assert antes == depois


def test_salvar_limpa_a_memoizacao_do_provedor(client, admin, cifra, monkeypatch):
    """Sem isto o adapter da chave ANTIGA seguiria servido até o processo
    reiniciar — e nada no log ligaria o sintoma à causa."""
    import app.providers as providers

    chamou = {"n": 0}
    original = providers.limpar_cache
    monkeypatch.setattr(
        providers,
        "limpar_cache",
        lambda: (chamou.__setitem__("n", chamou["n"] + 1), original())[1],
    )

    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})

    assert chamou["n"] == 1


# ── ambiente ativo ───────────────────────────────────────────────────────

def test_ativar_ambiente_sem_credencial_e_recusado(client, admin, cifra):
    res = client.patch(f"{ROTA}/ativo", json={"ambiente": "producao"})

    assert res.status_code == 422
    assert "não tem credencial" in res.json()["error"]["message"]


def test_alternar_para_producao_depois_de_cadastrar(client, admin, cifra):
    client.put(f"{ROTA}/producao", json={"api_key": CHAVE_PRODUCAO})

    res = client.patch(f"{ROTA}/ativo", json={"ambiente": "producao"})

    assert res.status_code == 200
    assert res.json()["ambiente_ativo"] == "producao"
    assert client.get(ROTA).json()["ambiente_ativo"] == "producao"


def test_ambiente_desconhecido_e_422(client, admin, cifra):
    assert client.put(
        f"{ROTA}/homologacao", json={"api_key": CHAVE_SANDBOX}
    ).status_code == 422
    assert client.patch(
        f"{ROTA}/ativo", json={"ambiente": "homologacao"}
    ).status_code == 422


# ── remoção + rotação ────────────────────────────────────────────────────

def test_remover_apaga_a_linha(client, admin, cifra):
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})

    assert client.delete(f"{ROTA}/sandbox").status_code == 204
    assert admin.data["provedor_credenciais"] == []


def test_rotacionar_troca_o_token_e_mantem_a_chave(client, admin, cifra):
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})
    antes = client.get(f"{ROTA}/sandbox/webhook-token").json()["webhook_token"]

    novo = client.post(f"{ROTA}/sandbox/webhook-token").json()["webhook_token"]

    assert novo != antes
    aberto = json.loads(
        Fernet(cifra.encode()).decrypt(
            admin.data["provedor_credenciais"][0]["encrypted_tokens"].encode()
        )
    )
    assert aberto["api_key"] == CHAVE_SANDBOX
    assert aberto["webhook_token"] == novo


def test_ler_token_de_ambiente_sem_credencial_e_404(client, admin, cifra):
    assert client.get(f"{ROTA}/producao/webhook-token").status_code == 404


# ── autenticação ─────────────────────────────────────────────────────────

def test_todas_as_rotas_de_credencial_exigem_autenticacao(client_anon):
    """Estrito `== 401`: um 404/422 aqui esconderia rota ausente ou validação
    rodando ANTES do guard."""
    assert client_anon.get(ROTA).status_code == 401
    assert client_anon.put(
        f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX}
    ).status_code == 401
    assert client_anon.delete(f"{ROTA}/sandbox").status_code == 401
    assert client_anon.get(f"{ROTA}/sandbox/webhook-token").status_code == 401
    assert client_anon.post(f"{ROTA}/sandbox/webhook-token").status_code == 401
    assert client_anon.patch(
        f"{ROTA}/ativo", json={"ambiente": "sandbox"}
    ).status_code == 401


# ── webhook autenticado pelo token guardado ──────────────────────────────

def test_webhook_aceita_o_token_de_qualquer_ambiente_cadastrado(
    client, admin, cifra
):
    # `client_anon` NÃO entra aqui: ele limpa `app.dependency_overrides` no
    # setup — depois do setup do `client` — e derruba a autenticação que o
    # próprio teste precisa para cadastrar as credenciais. O webhook não
    # depende de `get_current_user`, então o mesmo `client` serve às duas
    # metades: o que a rota confere é o header `asaas-access-token`.
    """Sandbox e produção são webhooks distintos no painel do Asaas e podem
    estar ambos registrados. Validar só contra o ativo faria o outro tomar
    401 — e 15 desses seguidos PARAM a fila de entrega daquele ambiente."""
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})
    client.put(f"{ROTA}/producao", json={"api_key": CHAVE_PRODUCAO})
    token_producao = client.get(f"{ROTA}/producao/webhook-token").json()["webhook_token"]

    # Ativo é sandbox; mesmo assim o token de produção autentica.
    assert client.get(ROTA).json()["ambiente_ativo"] == "sandbox"
    res = client.post(
        "/api/integracoes/asaas/webhook",
        json={"event": "PAYMENT_UNKNOWN", "payment": {"id": "pay_x"}},
        headers={"asaas-access-token": token_producao},
    )

    assert res.status_code == 200


def test_webhook_recusa_token_que_nao_bate(client, admin, cifra):
    """Este teste PASSAVA antes de a credencial ser gravada de verdade — o
    setup 401-ava por causa do `client_anon` e a asserção de 401 batia pelo
    motivo errado. Falso-verde clássico: o status certo por outra causa. A
    asserção de setup abaixo é o que impede a repetição."""
    client.put(f"{ROTA}/sandbox", json={"api_key": CHAVE_SANDBOX})
    assert admin.data["provedor_credenciais"], "setup falhou — nada foi gravado"

    res = client.post(
        "/api/integracoes/asaas/webhook",
        json={},
        headers={"asaas-access-token": "token-errado"},
    )

    assert res.status_code == 401


def test_chave_de_provider_e_composta_num_lugar_so():
    """Os dois lados (escrita pela UI, leitura pelo adapter) passam por aqui —
    strings divergentes produziriam 'conectado mas sem dados'."""
    assert chave_provider("asaas", "sandbox") == "asaas_sandbox"
    assert chave_provider("asaas", "producao") == "asaas_producao"
    with pytest.raises(ValueError):
        chave_provider("asaas", "homologacao")
