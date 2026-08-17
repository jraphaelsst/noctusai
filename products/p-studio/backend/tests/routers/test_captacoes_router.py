"""Rotas de /api/captacoes — agenda operacional e checklist de equipamentos."""
from tests.conftest import dias, make_row, seed_basico

INEXISTENTE = "00000000-0000-0000-0000-000000000999"


def _payload(seed, **extra):
    base = {
        "cliente_id": seed["cliente"]["id"],
        "imovel_id": seed["imovel"]["id"],
        "data": dias(1),
        "endereco": "Av. Atlântica, 1500",
    }
    return {**base, **extra}


def test_listar_vazio_devolve_lista_vazia(client):
    res = client.get("/api/captacoes")
    assert res.status_code == 200
    assert res.json() == []


def test_listar_ordena_por_data_e_hora(client, fake_db):
    seed_basico(fake_db)
    fake_db.data["captacoes"] = [
        make_row("captacoes", data=dias(2), hora="08:00:00", endereco="C"),
        make_row("captacoes", data=dias(1), hora="15:00:00", endereco="B"),
        make_row("captacoes", data=dias(1), hora="09:00:00", endereco="A"),
    ]
    assert [c["endereco"] for c in client.get("/api/captacoes").json()] == ["A", "B", "C"]


def test_listar_filtra_pelo_periodo(client, fake_db):
    seed_basico(fake_db)
    fake_db.data["captacoes"] = [
        make_row("captacoes", data=dias(-10), endereco="Passada"),
        make_row("captacoes", data=dias(1), endereco="Amanhã"),
        make_row("captacoes", data=dias(30), endereco="Longe"),
    ]
    res = client.get("/api/captacoes", params={"inicio": dias(0), "fim": dias(7)})
    assert [c["endereco"] for c in res.json()] == ["Amanhã"]


def test_listar_com_data_invalida_da_422(client):
    assert client.get("/api/captacoes", params={"inicio": "ontem"}).status_code == 422


def test_listar_enriquece_com_cliente_e_checklist(client, fake_db):
    seed = seed_basico(fake_db)
    captacao = make_row("captacoes", cliente_id=seed["cliente"]["id"], data=dias(1))
    fake_db.data["captacoes"] = [captacao]
    fake_db.data["captacao_equipamentos"] = [
        make_row("captacao_equipamentos", captacao_id=captacao["id"],
                 equipamento_id=seed["camera"]["id"]),
    ]

    corpo = client.get("/api/captacoes").json()
    assert corpo[0]["cliente_nome"] == "Imobiliária Alfa"
    assert corpo[0]["equipamentos"][0]["nome"] == "Sony A7 IV"
    assert corpo[0]["equipamentos"][0]["categoria"] == "camera"
    assert corpo[0]["equipamentos"][0]["conferido"] is False


def test_criar_devolve_201_com_defaults_de_hora_e_duracao(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post("/api/captacoes", json=_payload(seed))
    assert res.status_code == 201
    corpo = res.json()
    assert corpo["hora"] == "09:00:00"
    assert corpo["duracao_minutos"] == 120
    assert corpo["status"] == "agendado"


def test_criar_com_checklist_de_equipamentos(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/captacoes",
        json=_payload(seed, equipamento_ids=[seed["camera"]["id"]]),
    )
    assert res.status_code == 201
    assert [e["nome"] for e in res.json()["equipamentos"]] == ["Sony A7 IV"]


def test_criar_com_endereco_em_branco_herda_o_do_imovel(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post("/api/captacoes", json=_payload(seed, endereco=""))
    assert res.status_code == 201
    assert res.json()["endereco"] == "Av. Atlântica, 1500"


def test_criar_sem_data_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    payload = _payload(seed)
    payload.pop("data")
    assert client.post("/api/captacoes", json=payload).status_code == 422


def test_criar_com_data_invalida_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post("/api/captacoes", json=_payload(seed, data="31/07/2026"))
    assert res.status_code == 422


def test_criar_com_hora_invalida_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post("/api/captacoes", json=_payload(seed, hora="25:00"))
    assert res.status_code == 422


def test_obter_devolve_a_captacao(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post("/api/captacoes", json=_payload(seed)).json()
    res = client.get(f"/api/captacoes/{criada['id']}")
    assert res.status_code == 200
    assert res.json()["cliente_nome"] == "Imobiliária Alfa"


def test_obter_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.get(f"/api/captacoes/{INEXISTENTE}")
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Captação não encontrada"


def test_atualizar_muda_o_status_para_captado(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post("/api/captacoes", json=_payload(seed)).json()
    res = client.patch(f"/api/captacoes/{criada['id']}", json={"status": "captado"})
    assert res.status_code == 200
    assert res.json()["status"] == "captado"


def test_atualizar_com_status_fora_do_catalogo_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post("/api/captacoes", json=_payload(seed)).json()
    res = client.patch(f"/api/captacoes/{criada['id']}", json={"status": "remarcado"})
    assert res.status_code == 422


def test_atualizar_id_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.patch(f"/api/captacoes/{INEXISTENTE}", json={"status": "captado"})
    assert res.status_code == 404


def test_atualizar_substitui_o_checklist_inteiro(client, fake_db):
    seed = seed_basico(fake_db)
    tripe = make_row("equipamentos", nome="Tripé Manfrotto", categoria="outro")
    fake_db.data["equipamentos"].append(tripe)

    criada = client.post(
        "/api/captacoes", json=_payload(seed, equipamento_ids=[seed["camera"]["id"]])
    ).json()

    res = client.patch(
        f"/api/captacoes/{criada['id']}", json={"equipamento_ids": [tripe["id"]]}
    )
    assert [e["nome"] for e in res.json()["equipamentos"]] == ["Tripé Manfrotto"]


def test_marcar_item_do_checklist(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/captacoes", json=_payload(seed, equipamento_ids=[seed["camera"]["id"]])
    ).json()
    item_id = criada["equipamentos"][0]["id"]

    res = client.patch(f"/api/captacoes/checklist/{item_id}", json={"conferido": True})
    assert res.status_code == 200
    assert res.json()["conferido"] is True

    conferida = client.get(f"/api/captacoes/{criada['id']}").json()
    assert conferida["equipamentos"][0]["conferido"] is True


def test_marcar_item_inexistente_da_404(client, fake_db):
    seed_basico(fake_db)
    res = client.patch(f"/api/captacoes/checklist/{INEXISTENTE}", json={"conferido": True})
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Item do checklist não encontrado"


def test_marcar_item_sem_conferido_da_422(client, fake_db):
    seed_basico(fake_db)
    assert client.patch(
        f"/api/captacoes/checklist/{INEXISTENTE}", json={}
    ).status_code == 422


def test_excluir_apaga_a_captacao(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post("/api/captacoes", json=_payload(seed)).json()
    assert client.delete(f"/api/captacoes/{criada['id']}").status_code == 204
    assert client.get("/api/captacoes").json() == []
