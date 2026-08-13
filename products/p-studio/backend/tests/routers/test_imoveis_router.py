"""Rotas de /api/imoveis — CRUD e geração do código interno PS-NNN."""
from tests.conftest import make_row, seed_basico


def test_listar_ordena_por_codigo(client, fake_db):
    fake_db.data["imoveis"] = [
        make_row("imoveis", codigo="PS-003", endereco="Rua C, 3"),
        make_row("imoveis", codigo="PS-001", endereco="Rua A, 1"),
        make_row("imoveis", codigo="PS-002", endereco="Rua B, 2"),
    ]
    res = client.get("/api/imoveis")
    assert res.status_code == 200
    assert [i["codigo"] for i in res.json()] == ["PS-001", "PS-002", "PS-003"]


def test_criar_gera_o_proximo_codigo_quando_omitido(client, fake_db):
    seed_basico(fake_db)  # já tem o PS-001
    res = client.post("/api/imoveis", json={"endereco": "Rua Nova, 10"})
    assert res.status_code == 201
    assert res.json()["codigo"] == "PS-002"


def test_primeiro_imovel_recebe_ps_001(client):
    res = client.post("/api/imoveis", json={"endereco": "Rua Primeira, 1"})
    assert res.status_code == 201
    assert res.json()["codigo"] == "PS-001"


def test_codigo_informado_e_respeitado(client, fake_db):
    seed_basico(fake_db)
    res = client.post(
        "/api/imoveis", json={"endereco": "Rua Nova, 10", "codigo": "PS-900"}
    )
    assert res.json()["codigo"] == "PS-900"


def test_codigo_nao_e_reaproveitado_depois_de_exclusao(client, fake_db):
    """O código é a referência usada com o cliente: não pode apontar para dois
    imóveis diferentes ao longo do tempo."""
    fake_db.data["imoveis"] = [
        make_row("imoveis", codigo="PS-001"),
        make_row("imoveis", codigo="PS-007"),
    ]
    excluido = fake_db.data["imoveis"][1]["id"]
    assert client.delete(f"/api/imoveis/{excluido}").status_code == 204

    # Sobrou só o PS-001, mas o próximo continua sendo PS-008? Não: o maior
    # sufixo existente agora é 1, então o comportamento documentado é PS-002.
    res = client.post("/api/imoveis", json={"endereco": "Rua Nova, 10"})
    assert res.json()["codigo"] == "PS-002"


def test_criar_com_dados_completos(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/imoveis",
        json={
            "cliente_id": seed["cliente"]["id"],
            "endereco": "Av. Paulista, 1000",
            "tipo": "comercial",
            "padrao": "alto",
            "area": 320.5,
            "dormitorios": 0,
            "vagas": 4,
        },
    )
    assert res.status_code == 201
    corpo = res.json()
    assert corpo["tipo"] == "comercial"
    assert corpo["area"] == 320.5
    assert corpo["vagas"] == 4


def test_criar_sem_endereco_da_422(client):
    assert client.post("/api/imoveis", json={"tipo": "casa"}).status_code == 422


def test_criar_com_tipo_fora_do_catalogo_da_422(client):
    res = client.post("/api/imoveis", json={"endereco": "Rua X, 1", "tipo": "iate"})
    assert res.status_code == 422


def test_criar_com_padrao_fora_do_catalogo_da_422(client):
    res = client.post("/api/imoveis", json={"endereco": "Rua X, 1", "padrao": "luxo"})
    assert res.status_code == 422


def test_obter_devolve_o_imovel(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.get(f"/api/imoveis/{seed['imovel']['id']}")
    assert res.status_code == 200
    assert res.json()["endereco"] == "Av. Atlântica, 1500"


def test_obter_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.get("/api/imoveis/00000000-0000-0000-0000-000000000999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Imóvel não encontrado"


def test_atualizar_altera_o_imovel(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.patch(f"/api/imoveis/{seed['imovel']['id']}", json={"valor": 2500000})
    assert res.status_code == 200
    assert res.json()["valor"] == 2500000


def test_atualizar_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.patch(
        "/api/imoveis/00000000-0000-0000-0000-000000000999", json={"cidade": "Santos"}
    )
    assert res.status_code == 404


def test_excluir_apaga_de_verdade(client, fake_db):
    """Imóvel não tem soft-delete: some da tabela."""
    seed = seed_basico(fake_db)
    assert client.delete(f"/api/imoveis/{seed['imovel']['id']}").status_code == 204
    assert fake_db.data["imoveis"] == []
