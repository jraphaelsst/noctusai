"""Rotas de /api/servicos — catálogo de serviços do estúdio."""
from tests.conftest import make_row, seed_basico


def test_listar_ordena_por_nome(client, fake_db):
    seed_basico(fake_db)
    res = client.get("/api/servicos")
    assert res.status_code == 200
    assert [s["nome"] for s in res.json()] == [
        "Cobertura com drone", "Ensaio fotográfico",
    ]


def test_listar_esconde_inativos_por_padrao(client, fake_db):
    fake_db.data["servicos"] = [
        make_row("servicos", nome="Tour virtual"),
        make_row("servicos", nome="Serviço descontinuado", ativo=False),
    ]
    assert [s["nome"] for s in client.get("/api/servicos").json()] == ["Tour virtual"]


def test_incluir_inativos_traz_os_descontinuados(client, fake_db):
    fake_db.data["servicos"] = [
        make_row("servicos", nome="Tour virtual"),
        make_row("servicos", nome="Serviço descontinuado", ativo=False),
    ]
    res = client.get("/api/servicos", params={"incluir_inativos": "true"})
    assert len(res.json()) == 2


def test_criar_devolve_201(client):
    res = client.post(
        "/api/servicos",
        json={"nome": "Tour virtual 360", "categoria": "Virtual",
              "preco": 1200.5, "prazo_dias": 5},
    )
    assert res.status_code == 201
    corpo = res.json()
    assert corpo["preco"] == 1200.5
    assert corpo["prazo_dias"] == 5
    assert corpo["ativo"] is True


def test_criar_usa_os_defaults_de_preco_e_prazo(client):
    corpo = client.post("/api/servicos", json={"nome": "Diária avulsa"}).json()
    assert corpo["preco"] == 0
    assert corpo["prazo_dias"] == 3


def test_criar_sem_nome_da_422(client):
    assert client.post("/api/servicos", json={"preco": 100}).status_code == 422


def test_criar_com_preco_nao_numerico_da_422(client):
    res = client.post("/api/servicos", json={"nome": "X", "preco": "caro"})
    assert res.status_code == 422


def test_obter_devolve_o_servico(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.get(f"/api/servicos/{seed['foto']['id']}")
    assert res.status_code == 200
    assert res.json()["nome"] == "Ensaio fotográfico"


def test_obter_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.get("/api/servicos/00000000-0000-0000-0000-000000000999")
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Serviço não encontrado"


def test_atualizar_o_preco(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.patch(f"/api/servicos/{seed['foto']['id']}", json={"preco": 1100})
    assert res.status_code == 200
    assert res.json()["preco"] == 1100


def test_atualizar_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.patch(
        "/api/servicos/00000000-0000-0000-0000-000000000999", json={"preco": 1}
    )
    assert res.status_code == 404


def test_excluir_e_soft_delete(client, fake_db):
    seed = seed_basico(fake_db)
    assert client.delete(f"/api/servicos/{seed['foto']['id']}").status_code == 204
    assert [s["nome"] for s in client.get("/api/servicos").json()] == [
        "Cobertura com drone",
    ]


def test_reativar_um_servico_desativado(client, fake_db):
    """O soft-delete existe justamente para permitir desfazer."""
    seed = seed_basico(fake_db)
    client.delete(f"/api/servicos/{seed['foto']['id']}")
    res = client.patch(f"/api/servicos/{seed['foto']['id']}", json={"ativo": True})
    assert res.status_code == 200
    assert res.json()["ativo"] is True
    assert len(client.get("/api/servicos").json()) == 2
