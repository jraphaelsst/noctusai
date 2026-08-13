"""Rotas de /api/negocios — funil comercial, serviços contratados e kanban."""
from tests.conftest import make_row, seed_basico

INEXISTENTE = "00000000-0000-0000-0000-000000000999"


def test_etapas_saem_na_ordem_canonica_do_funil(client_anon):
    res = client_anon.get("/api/negocios/etapas")
    assert res.status_code == 200
    assert [e["id"] for e in res.json()] == [
        "novo_lead", "orcamento", "negociacao", "aprovado", "agendamento",
        "producao", "entregue", "recebido", "arquivado",
    ]
    assert res.json()[0]["label"] == "Novo Lead"


def test_listar_vazio_devolve_lista_vazia(client):
    res = client.get("/api/negocios")
    assert res.status_code == 200
    assert res.json() == []


def test_listar_enriquece_com_cliente_imovel_e_servicos(client, fake_db):
    seed = seed_basico(fake_db)
    negocio = make_row(
        "negocios", cliente_id=seed["cliente"]["id"], imovel_id=seed["imovel"]["id"],
        titulo="Pacote completo", valor=1650,
    )
    fake_db.data["negocios"] = [negocio]
    fake_db.data["negocio_servicos"] = [
        make_row("negocio_servicos", negocio_id=negocio["id"],
                 servico_id=seed["foto"]["id"], preco=950),
    ]

    corpo = client.get("/api/negocios").json()
    assert len(corpo) == 1
    assert corpo[0]["cliente_nome"] == "Imobiliária Alfa"
    assert corpo[0]["imovel_endereco"] == "Av. Atlântica, 1500"
    assert [s["nome"] for s in corpo[0]["servicos"]] == ["Ensaio fotográfico"]
    assert corpo[0]["servicos"][0]["preco"] == 950


def test_criar_soma_o_valor_dos_servicos_quando_omitido(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios",
        json={
            "cliente_id": seed["cliente"]["id"],
            "servico_ids": [seed["foto"]["id"], seed["drone"]["id"]],
        },
    )
    assert res.status_code == 201
    assert res.json()["valor"] == 1650  # 950 + 700


def test_criar_respeita_o_valor_negociado_informado(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios",
        json={
            "cliente_id": seed["cliente"]["id"],
            "servico_ids": [seed["foto"]["id"], seed["drone"]["id"]],
            "valor": 1500,
        },
    )
    assert res.json()["valor"] == 1500


def test_criar_sem_titulo_usa_o_endereco_do_imovel(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "imovel_id": seed["imovel"]["id"]},
    )
    assert res.json()["titulo"] == "Av. Atlântica, 1500"


def test_criar_sem_imovel_usa_o_nome_do_cliente_como_titulo(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post("/api/negocios", json={"cliente_id": seed["cliente"]["id"]})
    assert res.json()["titulo"] == "Imobiliária Alfa"


def test_criar_congela_o_preco_de_tabela_no_vinculo(client, fake_db):
    """O preço já contratado não pode mudar quando a tabela mudar."""
    seed = seed_basico(fake_db)
    negocio_id = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "servico_ids": [seed["foto"]["id"]]},
    ).json()["id"]

    client.patch(f"/api/servicos/{seed['foto']['id']}", json={"preco": 9999})

    corpo = client.get(f"/api/negocios/{negocio_id}").json()
    assert corpo["servicos"][0]["preco"] == 950


def test_criar_deduplica_servicos_repetidos(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios",
        json={
            "cliente_id": seed["cliente"]["id"],
            "servico_ids": [seed["foto"]["id"], seed["foto"]["id"]],
        },
    )
    assert len(res.json()["servicos"]) == 1


def test_criar_com_servico_inexistente_da_400(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "servico_ids": [INEXISTENTE]},
    )
    assert res.status_code == 400
    assert "Serviço inexistente" in res.json()["detail"]


def test_criar_sem_cliente_da_422(client):
    assert client.post("/api/negocios", json={"titulo": "Sem cliente"}).status_code == 422


def test_criar_com_etapa_fora_do_funil_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios", json={"cliente_id": seed["cliente"]["id"], "etapa": "em_analise"}
    )
    assert res.status_code == 422


def test_criar_com_forma_de_pagamento_invalida_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "forma_pagamento": "cheque"},
    )
    assert res.status_code == 422


def test_obter_devolve_o_negocio_completo(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "servico_ids": [seed["drone"]["id"]]},
    ).json()

    res = client.get(f"/api/negocios/{criado['id']}")
    assert res.status_code == 200
    assert res.json()["cliente_nome"] == "Imobiliária Alfa"
    assert [s["nome"] for s in res.json()["servicos"]] == ["Cobertura com drone"]


def test_obter_id_inexistente_da_404(client):
    res = client.get(f"/api/negocios/{INEXISTENTE}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Negócio não encontrado"


def test_atualizar_troca_a_lista_de_servicos(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "servico_ids": [seed["foto"]["id"]]},
    ).json()

    res = client.patch(
        f"/api/negocios/{criado['id']}", json={"servico_ids": [seed["drone"]["id"]]}
    )
    assert res.status_code == 200
    assert [s["nome"] for s in res.json()["servicos"]] == ["Cobertura com drone"]


def test_atualizar_sem_mexer_em_servicos_preserva_os_vinculos(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios",
        json={"cliente_id": seed["cliente"]["id"], "servico_ids": [seed["foto"]["id"]]},
    ).json()

    res = client.patch(f"/api/negocios/{criado['id']}", json={"corretor": "Ana"})
    assert res.json()["corretor"] == "Ana"
    assert len(res.json()["servicos"]) == 1


def test_atualizar_id_inexistente_da_404(client):
    res = client.patch(f"/api/negocios/{INEXISTENTE}", json={"corretor": "Ana"})
    assert res.status_code == 404


def test_atualizar_com_servico_inexistente_da_400(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios", json={"cliente_id": seed["cliente"]["id"]}
    ).json()
    res = client.patch(f"/api/negocios/{criado['id']}", json={"servico_ids": [INEXISTENTE]})
    assert res.status_code == 400


def test_mudar_etapa_move_o_card(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    res = client.patch(f"/api/negocios/{criado['id']}/etapa", json={"etapa": "negociacao"})
    assert res.status_code == 200
    assert res.json()["etapa"] == "negociacao"


def test_mudar_etapa_id_inexistente_da_404(client):
    res = client.patch(f"/api/negocios/{INEXISTENTE}/etapa", json={"etapa": "aprovado"})
    assert res.status_code == 404


def test_mudar_etapa_com_etapa_invalida_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios", json={"cliente_id": seed["cliente"]["id"]}
    ).json()
    res = client.patch(f"/api/negocios/{criado['id']}/etapa", json={"etapa": "quase_la"})
    assert res.status_code == 422


def test_mudar_etapa_sem_corpo_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios", json={"cliente_id": seed["cliente"]["id"]}
    ).json()
    assert client.patch(f"/api/negocios/{criado['id']}/etapa", json={}).status_code == 422


def test_excluir_apaga_o_negocio(client, fake_db):
    seed = seed_basico(fake_db)
    criado = client.post(
        "/api/negocios", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    assert client.delete(f"/api/negocios/{criado['id']}").status_code == 204
    assert client.get("/api/negocios").json() == []
