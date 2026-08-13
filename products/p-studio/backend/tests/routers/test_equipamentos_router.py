"""Rotas de /api/equipamentos — inventário do estúdio."""
from tests.conftest import make_row, seed_basico


def test_listar_ordena_por_nome(client, fake_db):
    fake_db.data["equipamentos"] = [
        make_row("equipamentos", nome="Zhiyun Crane", categoria="gimbal"),
        make_row("equipamentos", nome="DJI Mavic 3", categoria="drone"),
    ]
    res = client.get("/api/equipamentos")
    assert res.status_code == 200
    assert [e["nome"] for e in res.json()] == ["DJI Mavic 3", "Zhiyun Crane"]


def test_listar_esconde_inativos_por_padrao(client, fake_db):
    fake_db.data["equipamentos"] = [
        make_row("equipamentos", nome="Em uso"),
        make_row("equipamentos", nome="Baixado", ativo=False),
    ]
    assert [e["nome"] for e in client.get("/api/equipamentos").json()] == ["Em uso"]


def test_criar_devolve_201(client):
    res = client.post(
        "/api/equipamentos",
        json={"nome": "DJI Mavic 3", "marca": "DJI", "modelo": "Mavic 3 Pro",
              "categoria": "drone", "valor": 15000, "quantidade": 2},
    )
    assert res.status_code == 201
    corpo = res.json()
    assert corpo["categoria"] == "drone"
    assert corpo["quantidade"] == 2
    assert corpo["ativo"] is True


def test_criar_usa_quantidade_um_por_padrao(client):
    corpo = client.post("/api/equipamentos", json={"nome": "Tripé Manfrotto"}).json()
    assert corpo["quantidade"] == 1
    assert corpo["valor"] == 0


def test_criar_sem_nome_da_422(client):
    assert client.post("/api/equipamentos", json={"marca": "DJI"}).status_code == 422


def test_criar_com_categoria_fora_do_catalogo_da_422(client):
    res = client.post("/api/equipamentos", json={"nome": "X", "categoria": "helicoptero"})
    assert res.status_code == 422


def test_obter_devolve_o_equipamento(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.get(f"/api/equipamentos/{seed['camera']['id']}")
    assert res.status_code == 200
    assert res.json()["nome"] == "Sony A7 IV"


def test_obter_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.get("/api/equipamentos/00000000-0000-0000-0000-000000000999")
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Equipamento não encontrado"


def test_atualizar_o_numero_de_serie(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.patch(
        f"/api/equipamentos/{seed['camera']['id']}", json={"numero_serie": "SN-4242"}
    )
    assert res.status_code == 200
    assert res.json()["numero_serie"] == "SN-4242"


def test_atualizar_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.patch(
        "/api/equipamentos/00000000-0000-0000-0000-000000000999", json={"valor": 1}
    )
    assert res.status_code == 404


def test_excluir_e_soft_delete(client, fake_db):
    seed = seed_basico(fake_db)
    assert client.delete(f"/api/equipamentos/{seed['camera']['id']}").status_code == 204
    assert client.get("/api/equipamentos").json() == []
    assert fake_db.data["equipamentos"][0]["ativo"] is False
