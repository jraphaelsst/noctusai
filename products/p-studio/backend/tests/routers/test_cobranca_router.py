"""Rotas de emissão e sincronização de cobrança.

Rodam contra o `ProvedorFake` — sem rede, sem chave de API. O adapter real do
Asaas é exercitado em `tests/providers/` com tráfego gravado; aqui o que se
testa é a orquestração: o que vai para o provedor, o que volta para o banco, e
o que acontece quando alguém clica duas vezes.
"""
import pytest

from app.dependencies import get_provedor_cobranca
from app.main import app
from app.providers.fake import ProvedorFake
from tests.conftest import dias, make_row, seed_basico

INEXISTENTE = "00000000-0000-0000-0000-000000000999"


@pytest.fixture
def provedor():
    p = ProvedorFake()
    app.dependency_overrides[get_provedor_cobranca] = lambda: p
    yield p
    app.dependency_overrides.pop(get_provedor_cobranca, None)


def _cenario(fake_db, **overrides):
    """Cliente com documento + lançamento a faturar."""
    seed = seed_basico(fake_db)
    fake_db.data["clientes"][0]["cpf_cnpj"] = "34028316000103"
    campos = {
        "cliente_id": seed["cliente"]["id"],
        "valor": 1800,
        "vencimento": dias(7),
        "descricao": "Ensaio + drone",
    }
    campos.update(overrides)
    lancamento = make_row("lancamentos", **campos)
    fake_db.data["lancamentos"] = [lancamento]
    return seed, lancamento


# ── emissão ──────────────────────────────────────────────────────────────

def test_emitir_cobranca_grava_o_espelho_no_lancamento(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db)

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    assert res.status_code == 201

    corpo = res.json()
    assert corpo["provedor"] == "fake"
    assert corpo["provedor_cobranca_id"].startswith("pay_")
    assert corpo["url_fatura"]
    assert corpo["linha_digitavel"]
    assert corpo["pix_copia_e_cola"]
    assert corpo["sincronizado_em"]


def test_emitir_cobranca_promove_a_faturar_para_faturado(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db, status="a_faturar")

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    assert res.json()["status"] == "faturado"


def test_emitir_cobranca_nao_rebaixa_status_ja_avancado(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db, status="faturado")

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    assert res.json()["status"] == "faturado"


def test_emitir_cobranca_manda_a_referencia_do_lancamento(client, fake_db, provedor):
    """Sem `referencia_externa` o webhook chega e não sabe a quem pertence."""
    _, lancamento = _cenario(fake_db)

    client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})

    pedidos = [arg for nome, arg in provedor.chamadas if nome == "criar_cobranca"]
    assert pedidos[0].referencia_externa == lancamento["id"]
    assert pedidos[0].valor == 1800


def test_emitir_cobranca_respeita_a_forma_pedida(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db)

    client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={"forma": "pix"})

    pedidos = [arg for nome, arg in provedor.chamadas if nome == "criar_cobranca"]
    assert pedidos[0].forma == "pix"


def test_forma_default_e_indefinido(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db)
    client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    pedidos = [arg for nome, arg in provedor.chamadas if nome == "criar_cobranca"]
    assert pedidos[0].forma == "indefinido"


def test_forma_invalida_da_422(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db)
    res = client.post(
        f"/api/financeiro/{lancamento['id']}/cobranca", json={"forma": "cheque"}
    )
    assert res.status_code == 422


# ── idempotência ─────────────────────────────────────────────────────────

def test_emitir_duas_vezes_nao_cria_segunda_cobranca(client, fake_db, provedor):
    """Clicar duas vezes é o caso comum, e boleto duplicado o cliente vê."""
    _, lancamento = _cenario(fake_db)

    primeira = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    segunda = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})

    assert segunda.status_code == 201
    assert (
        segunda.json()["provedor_cobranca_id"]
        == primeira.json()["provedor_cobranca_id"]
    )
    criadas = [n for n, _ in provedor.chamadas if n == "criar_cobranca"]
    assert len(criadas) == 1


def test_adota_cobranca_orfa_ja_existente_no_provedor(client, fake_db, provedor):
    """Emissão anterior cujo commit não completou: o provedor tem a cobrança,
    nós não. Adotar é melhor que emitir a segunda."""
    _, lancamento = _cenario(fake_db)
    # Cobrança existe lá, mas o lançamento local está limpo.
    from app.providers.tipos import ClienteCobranca, PedidoCobranca
    from decimal import Decimal
    from datetime import date

    orfa = provedor.criar_cobranca(PedidoCobranca(
        referencia_externa=lancamento["id"],
        pagador=ClienteCobranca(
            referencia_externa="c", nome="Alfa", cpf_cnpj="34028316000103"
        ),
        valor=Decimal("1800"),
        vencimento=date.today(),
    ))
    provedor.chamadas.clear()

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})

    assert res.json()["provedor_cobranca_id"] == orfa.id_no_provedor
    assert [n for n, _ in provedor.chamadas if n == "criar_cobranca"] == []


def test_emitir_guarda_o_id_do_pagador_no_cliente(client, fake_db, provedor):
    """Evita uma busca por requisição na próxima emissão."""
    seed, lancamento = _cenario(fake_db)

    client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})

    cliente = fake_db.data["clientes"][0]
    assert cliente["provedor"] == "fake"
    assert cliente["provedor_cliente_id"].startswith("cus_")


# ── recusas com mensagem útil ────────────────────────────────────────────

def test_cliente_sem_documento_recusa_dizendo_o_campo(client, fake_db, provedor):
    seed, lancamento = _cenario(fake_db)
    fake_db.data["clientes"][0]["cpf_cnpj"] = None

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})

    assert res.status_code == 400
    assert "CPF/CNPJ" in res.json()["error"]["message"]
    assert "Imobiliária Alfa" in res.json()["error"]["message"]


def test_lancamento_sem_vencimento_recusa(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db, vencimento=None)

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    assert res.status_code == 400
    assert "vencimento" in res.json()["error"]["message"].lower()


def test_lancamento_ja_recebido_recusa(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db, status="recebido")

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    assert res.status_code == 400
    assert "recebido" in res.json()["error"]["message"].lower()


def test_lancamento_cancelado_recusa(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db, status="cancelado")

    res = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={})
    assert res.status_code == 400


def test_lancamento_inexistente_da_404(client, fake_db, provedor):
    seed_basico(fake_db)
    res = client.post(f"/api/financeiro/{INEXISTENTE}/cobranca", json={})
    assert res.status_code == 404


def test_emitir_sem_autenticacao_da_401(client_anon):
    res = client_anon.post(f"/api/financeiro/{INEXISTENTE}/cobranca", json={})
    assert res.status_code == 401


# ── sincronização (o caminho do Banco do Brasil) ─────────────────────────

def test_sincronizar_atualiza_status_do_provedor(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db)
    emitida = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={}).json()

    res = client.post(f"/api/financeiro/{lancamento['id']}/sincronizar")
    assert res.status_code == 200
    assert res.json()["provedor_status"] == "pendente"


def test_sincronizar_liquidada_da_baixa(client, fake_db, provedor):
    """É assim que o BB vai conciliar — por consulta, não por webhook."""
    from datetime import date

    _, lancamento = _cenario(fake_db)
    emitida = client.post(f"/api/financeiro/{lancamento['id']}/cobranca", json={}).json()
    provedor.marcar_liquidada(emitida["provedor_cobranca_id"], date(2026, 9, 12))

    res = client.post(f"/api/financeiro/{lancamento['id']}/sincronizar")

    assert res.json()["status"] == "recebido"
    assert res.json()["pago_em"] == "2026-09-12"


def test_sincronizar_sem_cobranca_emitida_recusa(client, fake_db, provedor):
    _, lancamento = _cenario(fake_db)
    res = client.post(f"/api/financeiro/{lancamento['id']}/sincronizar")
    assert res.status_code == 400


def test_rotas_de_leitura_nao_exigem_provedor(client, fake_db):
    """Integração fora do ar não pode derrubar a tela do financeiro."""
    _cenario(fake_db)
    assert client.get("/api/financeiro").status_code == 200
    assert client.get("/api/financeiro/resumo").status_code == 200
