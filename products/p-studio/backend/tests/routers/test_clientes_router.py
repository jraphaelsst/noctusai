"""Rotas de /api/clientes — CRUD com soft-delete."""
from tests.conftest import make_row, seed_basico

NOVO = {"nome": "Imobiliária Beta", "empresa": "Beta S.A.", "email": "contato@beta.com"}


def test_listar_devolve_os_clientes_ativos(client, fake_db):
    seed_basico(fake_db)
    res = client.get("/api/clientes")
    assert res.status_code == 200
    assert [c["nome"] for c in res.json()] == ["Imobiliária Alfa"]


def test_listar_ordena_por_nome(client, fake_db):
    fake_db.data["clientes"] = [
        make_row("clientes", nome="Zeta"),
        make_row("clientes", nome="Alfa"),
        make_row("clientes", nome="Mega"),
    ]
    assert [c["nome"] for c in client.get("/api/clientes").json()] == [
        "Alfa", "Mega", "Zeta",
    ]


def test_listar_esconde_inativos_por_padrao(client, fake_db):
    fake_db.data["clientes"] = [
        make_row("clientes", nome="Ativa"),
        make_row("clientes", nome="Desativada", ativo=False),
    ]
    assert [c["nome"] for c in client.get("/api/clientes").json()] == ["Ativa"]


def test_incluir_inativos_traz_os_desativados(client, fake_db):
    fake_db.data["clientes"] = [
        make_row("clientes", nome="Ativa"),
        make_row("clientes", nome="Desativada", ativo=False),
    ]
    res = client.get("/api/clientes", params={"incluir_inativos": "true"})
    assert [c["nome"] for c in res.json()] == ["Ativa", "Desativada"]


def test_criar_devolve_201_com_o_registro_gravado(client, fake_db):
    res = client.post("/api/clientes", json=NOVO)
    assert res.status_code == 201
    corpo = res.json()
    assert corpo["nome"] == "Imobiliária Beta"
    assert corpo["ativo"] is True
    assert len(fake_db.data["clientes"]) == 1


def test_criar_sem_nome_da_422(client):
    assert client.post("/api/clientes", json={"empresa": "Sem nome"}).status_code == 422


def test_criar_com_email_invalido_da_422(client):
    res = client.post("/api/clientes", json={"nome": "Gama", "email": "nao-e-email"})
    assert res.status_code == 422


def test_obter_devolve_o_cliente(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.get(f"/api/clientes/{seed['cliente']['id']}")
    assert res.status_code == 200
    assert res.json()["nome"] == "Imobiliária Alfa"


def test_obter_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.get("/api/clientes/00000000-0000-0000-0000-000000000999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Cliente não encontrado"


def test_atualizar_altera_so_o_que_foi_enviado(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.patch(
        f"/api/clientes/{seed['cliente']['id']}", json={"telefone": "11999998888"}
    )
    assert res.status_code == 200
    assert res.json()["telefone"] == "11999998888"
    assert res.json()["empresa"] == "Alfa Ltda"  # não foi apagado


def test_atualizar_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.patch(
        "/api/clientes/00000000-0000-0000-0000-000000000999", json={"nome": "X"}
    )
    assert res.status_code == 404


def test_atualizar_sem_campos_da_400(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.patch(f"/api/clientes/{seed['cliente']['id']}", json={})
    assert res.status_code == 400
    assert res.json()["detail"] == "Nada para atualizar"


def test_atualizar_com_tipo_errado_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.patch(f"/api/clientes/{seed['cliente']['id']}", json={"ativo": "talvez"})
    assert res.status_code == 422


def test_excluir_e_soft_delete(client, fake_db):
    seed = seed_basico(fake_db)
    assert client.delete(f"/api/clientes/{seed['cliente']['id']}").status_code == 204
    assert client.get("/api/clientes").json() == []
    inativos = client.get("/api/clientes", params={"incluir_inativos": "true"}).json()
    assert inativos[0]["ativo"] is False


def test_excluir_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.delete("/api/clientes/00000000-0000-0000-0000-000000000999")
    assert res.status_code == 404
