"""Rotas de /api/financeiro — lançamentos, baixa e o resumo da tela.

O ponto sensível deste domínio é `atrasado`: ele não existe no banco, é
derivado na leitura (faturado + vencimento no passado). Boa parte dos testes
abaixo existe para pinar essa derivação.
"""
from datetime import date

from tests.conftest import dias, make_row, seed_basico

INEXISTENTE = "00000000-0000-0000-0000-000000000999"


def test_status_expostos_incluem_o_derivado(client_anon):
    res = client_anon.get("/api/financeiro/status")
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()]
    assert ids == ["a_faturar", "faturado", "recebido", "atrasado", "cancelado"]


def test_listar_vazio_devolve_lista_vazia(client):
    assert client.get("/api/financeiro").json() == []


def test_listar_enriquece_com_nome_do_cliente(client, fake_db):
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"], valor=1800)
    ]

    corpo = client.get("/api/financeiro").json()
    assert corpo[0]["cliente_nome"] == "Imobiliária Alfa"
    assert corpo[0]["valor"] == 1800


def test_faturado_vencido_aparece_como_atrasado(client, fake_db):
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="faturado", vencimento=dias(-5), valor=1000)
    ]

    corpo = client.get("/api/financeiro").json()
    assert corpo[0]["status"] == "faturado"          # armazenado
    assert corpo[0]["status_exibido"] == "atrasado"  # derivado


def test_faturado_dentro_do_prazo_nao_e_atrasado(client, fake_db):
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="faturado", vencimento=dias(5), valor=1000)
    ]
    assert client.get("/api/financeiro").json()[0]["status_exibido"] == "faturado"


def test_faturado_sem_vencimento_nunca_atrasa(client, fake_db):
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="faturado", vencimento=None, valor=1000)
    ]
    assert client.get("/api/financeiro").json()[0]["status_exibido"] == "faturado"


def test_recebido_vencido_nao_vira_atrasado(client, fake_db):
    """Quem já pagou não deve, por mais que o vencimento tenha passado."""
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="recebido", vencimento=dias(-30), pago_em=dias(-31), valor=900)
    ]
    assert client.get("/api/financeiro").json()[0]["status_exibido"] == "recebido"


def test_cancelado_vencido_nao_vira_atrasado(client, fake_db):
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="cancelado", vencimento=dias(-10), valor=900)
    ]
    assert client.get("/api/financeiro").json()[0]["status_exibido"] == "cancelado"


def test_filtro_por_status_roda_sobre_o_exibido(client, fake_db):
    """`?status=atrasado` precisa achar linhas gravadas como `faturado`."""
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(-3), valor=100),
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(30), valor=200),
    ]

    atrasados = client.get("/api/financeiro?status=atrasado").json()
    assert len(atrasados) == 1
    assert atrasados[0]["valor"] == 100

    em_dia = client.get("/api/financeiro?status=faturado").json()
    assert len(em_dia) == 1
    assert em_dia[0]["valor"] == 200


def test_criar_lancamento(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/financeiro",
        json={"cliente_id": seed["cliente"]["id"], "valor": 1800,
              "descricao": "Ensaio + drone", "vencimento": dias(10)},
    )
    assert res.status_code == 201
    assert res.json()["status"] == "a_faturar"
    assert res.json()["cliente_nome"] == "Imobiliária Alfa"


def test_criar_sem_cliente_da_422(client):
    assert client.post("/api/financeiro", json={"valor": 100}).status_code == 422


def test_criar_com_forma_de_pagamento_invalida_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/financeiro",
        json={"cliente_id": seed["cliente"]["id"], "forma_pagamento": "cheque"},
    )
    assert res.status_code == 422


def test_criar_com_status_derivado_da_422(client, fake_db):
    """`atrasado` é derivado — não pode ser gravado."""
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/financeiro",
        json={"cliente_id": seed["cliente"]["id"], "status": "atrasado"},
    )
    assert res.status_code == 422


def test_obter_id_inexistente_da_404(client):
    res = client.get(f"/api/financeiro/{INEXISTENTE}")
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Lançamento não encontrado"


def test_dar_baixa_marca_recebido_com_a_data_de_hoje(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/financeiro",
        json={"cliente_id": seed["cliente"]["id"], "valor": 950, "status": "faturado"},
    ).json()

    res = client.post(f"/api/financeiro/{criado['id']}/baixa", json={})
    assert res.status_code == 200
    assert res.json()["status"] == "recebido"
    assert res.json()["pago_em"] == date.today().isoformat()


def test_dar_baixa_respeita_a_data_informada(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/financeiro", json={"cliente_id": seed["cliente"]["id"], "valor": 950}
    ).json()

    res = client.post(
        f"/api/financeiro/{criado['id']}/baixa",
        json={"pago_em": dias(-2), "forma_pagamento": "pix"},
    )
    assert res.json()["pago_em"] == dias(-2)
    assert res.json()["forma_pagamento"] == "pix"


def test_dar_baixa_tira_o_lancamento_do_atrasado(client, fake_db):
    seed = seed_basico(fake_db)
    lancamento = make_row(
        "lancamentos", cliente_id=seed["cliente"]["id"],
        status="faturado", vencimento=dias(-10), valor=500,
    )
    fake_db.data["lancamentos"] = [lancamento]
    assert client.get("/api/financeiro").json()[0]["status_exibido"] == "atrasado"

    res = client.post(f"/api/financeiro/{lancamento['id']}/baixa", json={})
    assert res.json()["status_exibido"] == "recebido"


def test_dar_baixa_id_inexistente_da_404(client):
    assert client.post(f"/api/financeiro/{INEXISTENTE}/baixa", json={}).status_code == 404


def test_atualizar_lancamento(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/financeiro", json={"cliente_id": seed["cliente"]["id"], "valor": 100}
    ).json()

    res = client.patch(f"/api/financeiro/{criado['id']}", json={"valor": 250})
    assert res.status_code == 200
    assert res.json()["valor"] == 250


def test_atualizar_id_inexistente_da_404(client):
    assert client.patch(f"/api/financeiro/{INEXISTENTE}", json={"valor": 1}).status_code == 404


def test_excluir_apaga_o_lancamento(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/financeiro", json={"cliente_id": seed["cliente"]["id"], "valor": 100}
    ).json()

    assert client.delete(f"/api/financeiro/{criado['id']}").status_code == 204
    assert client.get("/api/financeiro").json() == []


# ── resumo ───────────────────────────────────────────────────────────────

def test_resumo_zerado_sem_lancamentos(client):
    corpo = client.get("/api/financeiro/resumo").json()
    assert corpo["faturamento_total"] == 0
    assert corpo["ticket_medio"] == 0
    assert corpo["clientes_inadimplentes"] == 0


def test_resumo_separa_recebido_em_aberto_e_atrasado(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="recebido",
                 pago_em=date.today().isoformat(), valor=1000),
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(15), valor=500),
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(-15), valor=300),
    ]

    corpo = client.get("/api/financeiro/resumo").json()
    assert corpo["faturamento_total"] == 1800
    assert corpo["recebido"] == 1000
    assert corpo["atrasado"] == 300
    assert corpo["em_aberto"] == 800  # 500 em dia + 300 atrasado
    assert corpo["clientes_inadimplentes"] == 1


def test_resumo_ignora_cancelados_no_total(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="recebido",
                 pago_em=date.today().isoformat(), valor=1000),
        make_row("lancamentos", cliente_id=cid, status="cancelado", valor=9999),
    ]
    assert client.get("/api/financeiro/resumo").json()["faturamento_total"] == 1000


def test_resumo_ticket_medio_so_conta_recebidos(client, fake_db):
    seed = seed_basico(fake_db)
    cid = seed["cliente"]["id"]
    hoje = date.today().isoformat()
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="recebido", pago_em=hoje, valor=1000),
        make_row("lancamentos", cliente_id=cid, status="recebido", pago_em=hoje, valor=500),
        make_row("lancamentos", cliente_id=cid, status="a_faturar", valor=9999),
    ]
    assert client.get("/api/financeiro/resumo").json()["ticket_medio"] == 750


def test_resumo_conta_inadimplentes_distintos(client, fake_db):
    seed = seed_basico(fake_db)
    outro = make_row("clientes", nome="Imobiliária Beta")
    fake_db.data["clientes"].append(outro)
    cid = seed["cliente"]["id"]
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(-1), valor=100),
        make_row("lancamentos", cliente_id=cid, status="faturado",
                 vencimento=dias(-2), valor=100),
        make_row("lancamentos", cliente_id=outro["id"], status="faturado",
                 vencimento=dias(-3), valor=100),
    ]
    assert client.get("/api/financeiro/resumo").json()["clientes_inadimplentes"] == 2


def test_receita_por_cliente_ordena_do_maior_para_o_menor(client, fake_db):
    seed = seed_basico(fake_db)
    outro = make_row("clientes", nome="Imobiliária Beta")
    fake_db.data["clientes"].append(outro)
    hoje = date.today().isoformat()
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="recebido", pago_em=hoje, valor=300),
        make_row("lancamentos", cliente_id=outro["id"],
                 status="recebido", pago_em=hoje, valor=1200),
    ]

    corpo = client.get("/api/financeiro/por-cliente").json()
    assert [c["nome"] for c in corpo] == ["Imobiliária Beta", "Imobiliária Alfa"]
    assert corpo[0]["valor"] == 1200


def test_receita_por_cliente_ignora_o_que_nao_foi_recebido(client, fake_db):
    seed = seed_basico(fake_db)
    fake_db.data["lancamentos"] = [
        make_row("lancamentos", cliente_id=seed["cliente"]["id"],
                 status="faturado", vencimento=dias(10), valor=5000)
    ]
    assert client.get("/api/financeiro/por-cliente").json() == []
