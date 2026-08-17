"""Rotas de /api/producoes — pipeline de pós e histórico append-only."""
from tests.conftest import make_row, seed_basico

INEXISTENTE = "00000000-0000-0000-0000-000000000999"


def test_etapas_saem_na_ordem_canonica_do_pipeline(client_anon):
    res = client_anon.get("/api/producoes/etapas")
    assert res.status_code == 200
    assert [e["id"] for e in res.json()] == [
        "agendado", "captado", "backup", "selecao",
        "edicao", "revisao", "entregue", "arquivado",
    ]
    assert res.json()[2]["label"] == "Backup realizado"


def test_listar_vazio_devolve_lista_vazia(client):
    res = client.get("/api/producoes")
    assert res.status_code == 200
    assert res.json() == []


def test_listar_enriquece_com_cliente_e_endereco_da_captacao(client, fake_db):
    seed = seed_basico(fake_db)
    captacao = make_row(
        "captacoes", cliente_id=seed["cliente"]["id"], endereco="Av. Atlântica, 1500"
    )
    fake_db.data["captacoes"] = [captacao]
    fake_db.data["producoes"] = [
        make_row("producoes", cliente_id=seed["cliente"]["id"], captacao_id=captacao["id"])
    ]

    corpo = client.get("/api/producoes").json()
    assert len(corpo) == 1
    assert corpo[0]["cliente_nome"] == "Imobiliária Alfa"
    assert corpo[0]["endereco"] == "Av. Atlântica, 1500"


def test_listar_nao_carrega_historico_no_kanban(client, fake_db):
    """A listagem é o kanban; puxar evento de toda produção seria desperdício."""
    seed = seed_basico(fake_db)
    producao = make_row("producoes", cliente_id=seed["cliente"]["id"])
    fake_db.data["producoes"] = [producao]
    fake_db.data["producao_eventos"] = [
        make_row("producao_eventos", producao_id=producao["id"], comentario="oi")
    ]

    assert client.get("/api/producoes").json()[0]["eventos"] == []


def test_criar_producao_avulsa(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post("/api/producoes", json={"cliente_id": seed["cliente"]["id"]})
    assert res.status_code == 201
    assert res.json()["etapa"] == "agendado"
    assert res.json()["cliente_nome"] == "Imobiliária Alfa"


def test_criar_com_etapa_fora_do_pipeline_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    res = client.post(
        "/api/producoes",
        json={"cliente_id": seed["cliente"]["id"], "etapa": "renderizando"},
    )
    assert res.status_code == 422


def test_obter_id_inexistente_da_404(client):
    res = client.get(f"/api/producoes/{INEXISTENTE}")
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "Produção não encontrada"


def test_mudar_etapa_registra_evento_de_transicao(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    res = client.patch(f"/api/producoes/{criada['id']}/etapa", json={"etapa": "edicao"})
    assert res.status_code == 200
    assert res.json()["etapa"] == "edicao"

    eventos = res.json()["eventos"]
    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "transicao"
    assert eventos[0]["comentario"] == "Agendado → Edição"


def test_mudar_etapa_usa_o_comentario_informado_no_lugar_do_rotulo(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    res = client.patch(
        f"/api/producoes/{criada['id']}/etapa",
        json={"etapa": "revisao", "comentario": "cliente pediu recorte"},
    )
    assert res.json()["eventos"][0]["comentario"] == "cliente pediu recorte"


def test_mudar_etapa_para_entregue_carimba_a_data(client, fake_db):
    from datetime import date

    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()
    assert criada["entregue_em"] is None

    res = client.patch(f"/api/producoes/{criada['id']}/etapa", json={"etapa": "entregue"})
    assert res.json()["entregue_em"] == date.today().isoformat()


def test_reentrar_em_entregue_preserva_a_data_original(client, fake_db):
    """A data real da entrega não pode ser reescrita por um passeio no kanban."""
    seed = seed_basico(fake_db)
    producao = make_row(
        "producoes", cliente_id=seed["cliente"]["id"],
        etapa="entregue", entregue_em="2026-01-15",
    )
    fake_db.data["producoes"] = [producao]

    client.patch(f"/api/producoes/{producao['id']}/etapa", json={"etapa": "revisao"})
    res = client.patch(f"/api/producoes/{producao['id']}/etapa", json={"etapa": "entregue"})
    assert res.json()["entregue_em"] == "2026-01-15"


def test_mudar_etapa_com_responsavel_atualiza_a_producao(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    res = client.patch(
        f"/api/producoes/{criada['id']}/etapa",
        json={"etapa": "selecao", "responsavel": "Bruno"},
    )
    assert res.json()["responsavel"] == "Bruno"
    assert res.json()["eventos"][0]["responsavel"] == "Bruno"


def test_mudar_etapa_invalida_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()
    res = client.patch(f"/api/producoes/{criada['id']}/etapa", json={"etapa": "colorizando"})
    assert res.status_code == 422


def test_mudar_etapa_id_inexistente_da_404(client):
    res = client.patch(f"/api/producoes/{INEXISTENTE}/etapa", json={"etapa": "edicao"})
    assert res.status_code == 404


def test_comentar_registra_evento_sem_mover_a_etapa(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    res = client.post(
        f"/api/producoes/{criada['id']}/eventos",
        json={"comentario": "backup na nuvem ok", "responsavel": "Ana"},
    )
    assert res.status_code == 201
    assert res.json()["etapa"] == "agendado"
    assert res.json()["eventos"][0]["tipo"] == "comentario"
    assert res.json()["eventos"][0]["comentario"] == "backup na nuvem ok"


def test_comentar_sem_texto_da_422(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()
    assert client.post(f"/api/producoes/{criada['id']}/eventos", json={}).status_code == 422


def test_comentar_id_inexistente_da_404(client):
    res = client.post(f"/api/producoes/{INEXISTENTE}/eventos", json={"comentario": "oi"})
    assert res.status_code == 404


def test_historico_sai_do_mais_recente_para_o_mais_antigo(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    client.patch(f"/api/producoes/{criada['id']}/etapa", json={"etapa": "captado"})
    res = client.post(
        f"/api/producoes/{criada['id']}/eventos", json={"comentario": "último"}
    )

    # O fake carimba o mesmo created_at em tudo; o que se afirma aqui é que a
    # rota devolve o histórico completo, não que ele veio ordenado por relógio.
    assert len(res.json()["eventos"]) == 2
    assert {e["tipo"] for e in res.json()["eventos"]} == {"transicao", "comentario"}


def test_atualizar_campos_livres(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    res = client.patch(
        f"/api/producoes/{criada['id']}",
        json={"responsavel": "Carla", "observacoes": "urgente"},
    )
    assert res.status_code == 200
    assert res.json()["responsavel"] == "Carla"
    assert res.json()["observacoes"] == "urgente"


def test_atualizar_id_inexistente_da_404(client):
    assert client.patch(f"/api/producoes/{INEXISTENTE}", json={"responsavel": "X"}).status_code == 404


def test_excluir_apaga_a_producao(client, fake_db):
    seed = seed_basico(fake_db)
    criada = client.post(
        "/api/producoes", json={"cliente_id": seed["cliente"]["id"]}
    ).json()

    assert client.delete(f"/api/producoes/{criada['id']}").status_code == 204
    assert client.get("/api/producoes").json() == []
