"""Every funnel route, against BOTH tenancies (`fn` is parametrized org + platform).

Strict status asserts only (`== 401`, never `in (401, 404)`): the non-401 branch
of a tuple is a false-green. Refusals are proven by watching a write NOT happen
(`snapshot()` before == after).
"""
from __future__ import annotations

import pytest

from .conftest import GATED_ROLE, HEADERS, ORG, OTHER_ORG, PLATFORM_ORG, READ_ONLY, USER

CARD = "11111111-1111-4111-8111-111111111111"

#: (method, path template, json body) for every route the board router mounts.
ROUTES = [
    ("GET", "/meta", None),
    ("GET", "/board", None),
    ("GET", "/board/orfaos", None),
    ("POST", "/cards", {"titulo": "x"}),
    ("GET", f"/cards/{CARD}", None),
    ("PATCH", f"/cards/{CARD}", {"titulo": "y"}),
    ("POST", f"/cards/{CARD}/mover-etapa", {"para_etapa_id": CARD}),
    ("POST", f"/cards/{CARD}/perder", {"motivo_codigo": "preco"}),
    ("POST", f"/cards/{CARD}/reabrir", None),
    ("POST", f"/cards/{CARD}/arquivar", None),
    ("POST", f"/cards/{CARD}/acoes/livre", {"payload": {}}),
    ("GET", f"/cards/{CARD}/movimentos", None),
    ("GET", "/etapas", None),
    ("POST", "/etapas", {"label": "Nova"}),
]
WRITES = [r for r in ROUTES if r[0] != "GET"]


def _call(fn, method, path, body, headers):
    return fn.client.request(method, fn.url(path), json=body, headers=headers)


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_unauthenticated_is_401(self, fn, method, path, body):
        response = _call(fn, method, path, body, None)
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path,body", WRITES)
    def test_read_only_session_cannot_write_403(self, fn, method, path, body):
        before = fn.snapshot()
        response = _call(fn, method, path, body, READ_ONLY)
        assert response.status_code == 403
        assert fn.snapshot() == before

    def test_read_only_session_can_read(self, fn):
        assert fn.client.get(fn.url("/board"), headers=READ_ONLY).status_code == 200
        assert fn.client.get(fn.url("/meta"), headers=READ_ONLY).status_code == 200


class TestMeta:
    def test_meta_describes_the_config(self, fn):
        data = fn.client.get(fn.url("/meta"), headers=HEADERS).json()["data"]
        assert data["pipeline"] == "crm"
        assert GATED_ROLE in data["papeis"]
        assert data["lost_reasons"] == [
            {"codigo": "preco", "label": "Preço", "exige_texto": False},
            {"codigo": "outro", "label": "Outro", "exige_texto": True},
        ]
        assert data["gates"] == {GATED_ROLE: {"codigo": "telefone_obrigatorio", "inputs": ["confirmado"], "mensagem": "Telefone"}}
        assert {a["codigo"]: a["papeis"] for a in data["acoes"]} == {"aceitar": [GATED_ROLE], "livre": []}
        assert data["campos_editaveis"] == ["telefone"]


class TestBoard:
    def test_every_active_stage_is_a_column_even_empty(self, fn):
        fn.add_stage("morta", posicao=9, ativo=False)
        data = fn.client.get(fn.url("/board"), headers=HEADERS).json()["data"]
        assert [c["stage"]["slug"] for c in data] == ["entrada", "proposta", "fechado"]
        assert all(set(c) == {"etapa", "stage", "total", "valorTotal", "exibidos", "cards"} for c in data)
        assert all(c["total"] == 0 and c["cards"] == [] for c in data)

    def test_cards_sorted_by_position_and_totals_cover_the_whole_column(self, fn):
        a = fn.add_card(titulo="A", etapa="entrada", pos="2", valor=10)
        b = fn.add_card(titulo="B", etapa="entrada", pos="1.5", valor=5)
        fn.add_card(titulo="C", etapa="entrada", pos="3", valor=1)
        data = fn.client.get(fn.url("/board?limite_por_etapa=2"), headers=HEADERS).json()["data"]
        col = data[0]
        assert [c["id"] for c in col["cards"]] == [b, a]
        assert (col["total"], col["exibidos"], col["valorTotal"]) == (3, 2, 16)

    def test_card_wire_shape(self, fn):
        fn.add_card(titulo="Ana", etapa="entrada", pos="1.25", valor=7, telefone="119", responsavel_id=USER)
        card = fn.client.get(fn.url("/board"), headers=HEADERS).json()["data"][0]["cards"][0]
        assert set(card) == {
            "id", "etapa_id", "kanban_pos", "status", "titulo", "subtitulo", "valor", "responsavel", "badges",
            "motivo_perda_codigo", "motivo_perda", "created_at", "updated_at", "hub_entity_id", "campos",
        }
        assert card["kanban_pos"] == "1.25" and card["status"] == "aberto" and card["valor"] == 7
        assert card["campos"] == {"telefone": "119"} and card["hub_entity_id"] is None
        assert card["responsavel"] == {"id": USER, "nome": None}

    def test_only_open_cards_by_default_and_status_filter(self, fn):
        open_ = fn.add_card(etapa="entrada")
        lost = fn.add_card(etapa="entrada", status="perdido")
        ids = lambda q: [c["id"] for col in fn.client.get(fn.url(f"/board{q}"), headers=HEADERS).json()["data"] for c in col["cards"]]
        assert ids("") == [open_]
        assert ids("?status=perdido") == [lost]
        assert sorted(ids("?status=todos")) == sorted([open_, lost])

    def test_bad_status_filter_is_422(self, fn):
        assert fn.client.get(fn.url("/board?status=nope"), headers=HEADERS).status_code == 422

    def test_busca_folds_accents_and_case(self, fn):
        hit = fn.add_card(titulo="João Ação", etapa="entrada")
        fn.add_card(titulo="Maria", etapa="entrada")
        cards = fn.client.get(fn.url("/board?busca=joao%20acao"), headers=HEADERS).json()["data"][0]["cards"]
        assert [c["id"] for c in cards] == [hit]

    def test_responsavel_filter(self, fn):
        mine = fn.add_card(etapa="entrada", responsavel_id=USER)
        fn.add_card(etapa="entrada")
        cards = fn.client.get(fn.url(f"/board?responsavel_id={USER}"), headers=HEADERS).json()["data"][0]["cards"]
        assert [c["id"] for c in cards] == [mine]

    def test_orphans_are_cards_with_no_active_stage(self, fn):
        fn.add_stage("morta", posicao=9, ativo=False)
        placed = fn.add_card(etapa="entrada")
        nowhere = fn.add_card(etapa=None)
        dead = fn.add_card(etapa="morta")
        ids = [c["id"] for c in fn.client.get(fn.url("/board/orfaos"), headers=HEADERS).json()["data"]]
        assert sorted(ids) == sorted([nowhere, dead]) and placed not in ids


class TestCreate:
    def test_creates_on_top_of_first_stage_with_entry_movimento(self, fn):
        older = fn.add_card(titulo="old", etapa="entrada", pos="5")
        response = fn.client.post(fn.url("/cards"), json={"titulo": "Novo", "valor": 12, "campos": {"telefone": "11"}}, headers=HEADERS)
        assert response.status_code == 201
        card = response.json()["data"]
        assert card["etapa_id"] == fn.stages["entrada"] and card["titulo"] == "Novo" and card["valor"] == 12
        assert float(card["kanban_pos"]) < 5 and card["campos"] == {"telefone": "11"} and card["status"] == "aberto"
        entry = fn.movimentos(card["id"])
        assert len(entry) == 1 and entry[0]["de_etapa_id"] is None and entry[0]["para_etapa_id"] == fn.stages["entrada"]
        assert entry[0]["org_id"] == fn.effective_org and entry[0]["responsavel_id"] == USER
        assert fn.audit[-1][1] == "criar" and older  # audit-logged

    def test_card_row_carries_org_only_for_org_tenancy(self, fn):
        card_id = fn.client.post(fn.url("/cards"), json={"titulo": "x"}, headers=HEADERS).json()["data"]["id"]
        row = fn.card(card_id)
        assert ("org_id" in row) == (fn.name == "org")
        if fn.name == "org":
            assert row["org_id"] == ORG

    def test_unknown_stage_is_404_and_writes_nothing(self, fn):
        before = fn.snapshot()
        response = fn.client.post(fn.url("/cards"), json={"titulo": "x", "etapa_id": "nope"}, headers=HEADERS)
        assert response.status_code == 404 and response.json()["error"]["code"] == "stage_not_found"
        assert fn.snapshot() == before

    def test_inactive_stage_is_409(self, fn):
        dead = fn.add_stage("morta", posicao=9, ativo=False)
        before = fn.snapshot()
        response = fn.client.post(fn.url("/cards"), json={"titulo": "x", "etapa_id": dead}, headers=HEADERS)
        assert response.status_code == 409 and response.json()["error"]["code"] == "etapa_inativa"
        assert fn.snapshot() == before

    def test_non_editable_campo_is_422_and_writes_nothing(self, fn):
        before = fn.snapshot()
        response = fn.client.post(fn.url("/cards"), json={"titulo": "x", "campos": {"etapa_id": "z"}}, headers=HEADERS)
        assert response.status_code == 422 and response.json()["error"]["code"] == "campo_nao_editavel"
        assert fn.snapshot() == before

    def test_blank_title_is_422(self, fn):
        assert fn.client.post(fn.url("/cards"), json={"titulo": ""}, headers=HEADERS).status_code == 422

    def test_unknown_body_key_is_422(self, fn):
        assert fn.client.post(fn.url("/cards"), json={"titulo": "x", "status": "ganho"}, headers=HEADERS).status_code == 422


class TestReadAndPatch:
    def test_get_card(self, fn):
        cid = fn.add_card(titulo="Ana", etapa="entrada")
        response = fn.client.get(fn.url(f"/cards/{cid}"), headers=HEADERS)
        assert response.status_code == 200 and response.json()["data"]["titulo"] == "Ana"

    def test_missing_card_is_404(self, fn):
        response = fn.client.get(fn.url(f"/cards/{CARD}"), headers=HEADERS)
        assert response.status_code == 404 and response.json()["error"]["code"] == "card_not_found"

    def test_patch_edits_and_logs(self, fn):
        cid = fn.add_card(titulo="Ana", etapa="entrada")
        response = fn.client.patch(fn.url(f"/cards/{cid}"), json={"titulo": "Bia", "valor": 3, "campos": {"telefone": "9"}}, headers=HEADERS)
        assert response.status_code == 200
        card = response.json()["data"]
        assert (card["titulo"], card["valor"], card["campos"]) == ("Bia", 3, {"telefone": "9"})
        assert fn.audit[-1][1] == "editar"

    def test_patch_can_unassign_the_owner(self, fn):
        cid = fn.add_card(etapa="entrada", responsavel_id=USER)
        response = fn.client.patch(fn.url(f"/cards/{cid}"), json={"responsavel_id": None}, headers=HEADERS)
        assert response.status_code == 200 and response.json()["data"]["responsavel"] is None

    def test_empty_patch_writes_and_logs_nothing(self, fn):
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        assert fn.client.patch(fn.url(f"/cards/{cid}"), json={}, headers=HEADERS).status_code == 200
        assert fn.snapshot() == before

    def test_patch_non_editable_campo_is_422(self, fn):
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        response = fn.client.patch(fn.url(f"/cards/{cid}"), json={"campos": {"kanban_pos": "1"}}, headers=HEADERS)
        assert response.status_code == 422 and response.json()["error"]["code"] == "campo_nao_editavel"
        assert fn.snapshot() == before

    def test_patch_closed_card_is_409(self, fn):
        cid = fn.add_card(etapa="entrada", status="perdido")
        before = fn.snapshot()
        response = fn.client.patch(fn.url(f"/cards/{cid}"), json={"titulo": "z"}, headers=HEADERS)
        assert response.status_code == 409 and response.json()["error"]["code"] == "card_fechado"
        assert fn.snapshot() == before


class TestMove:
    def test_real_move_writes_exactly_one_movimento(self, fn):
        cid = fn.add_card(etapa="entrada", telefone="11")
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["fechado"], "motivo": "pronto"}, headers=HEADERS)
        assert response.status_code == 200 and response.json()["data"]["etapa_id"] == fn.stages["fechado"]
        mov = fn.movimentos(cid)
        assert len(mov) == 1
        assert (mov[0]["de_etapa_id"], mov[0]["para_etapa_id"], mov[0]["motivo"]) == (fn.stages["entrada"], fn.stages["fechado"], "pronto")
        assert mov[0]["org_id"] == fn.effective_org and fn.audit[-1][1] == "mover"

    def test_cross_stage_move_without_index_lands_on_top(self, fn):
        fn.add_card(etapa="fechado", pos="4")
        cid = fn.add_card(etapa="entrada")
        card = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["fechado"]}, headers=HEADERS).json()["data"]
        assert float(card["kanban_pos"]) < 4

    def test_drop_index_lands_between_neighbours(self, fn):
        fn.add_card(etapa="fechado", pos="1")
        fn.add_card(etapa="fechado", pos="2")
        cid = fn.add_card(etapa="entrada")
        card = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["fechado"], "novo_indice": 1}, headers=HEADERS).json()["data"]
        assert card["kanban_pos"] == "1.5"

    def test_same_stage_reorder_moves_the_card_but_writes_no_movimento(self, fn):
        a = fn.add_card(etapa="entrada", pos="1")
        fn.add_card(etapa="entrada", pos="2")
        c = fn.add_card(etapa="entrada", pos="3")
        card = fn.client.post(fn.url(f"/cards/{c}/mover-etapa"), json={"para_etapa_id": fn.stages["entrada"], "novo_indice": 0}, headers=HEADERS).json()["data"]
        assert float(card["kanban_pos"]) < 1 and a
        assert fn.movimentos(c) == [] and fn.audit[-1][1] == "reordenar"

    def test_same_stage_call_without_index_changes_nothing(self, fn):
        cid = fn.add_card(etapa="entrada", pos="7")
        card = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["entrada"]}, headers=HEADERS).json()["data"]
        assert card["kanban_pos"] == "7" and fn.movimentos(cid) == []

    def test_gate_refuses_with_pendencias_and_writes_nothing(self, fn):
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["proposta"]}, headers=HEADERS)
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "gate_refused"
        assert error["details"] == {"gate": "telefone_obrigatorio", "pendencias": [{"codigo": "telefone", "mensagem": "Informe o telefone antes de avançar."}]}
        assert fn.snapshot() == before

    def test_gate_opens_when_the_declared_input_confirms(self, fn):
        cid = fn.add_card(etapa="entrada")
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["proposta"], "extra": {"confirmado": True}}, headers=HEADERS)
        assert response.status_code == 200 and len(fn.movimentos(cid)) == 1

    def test_gate_ignores_undeclared_extra_keys(self, fn):
        cid = fn.add_card(etapa="entrada")
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["proposta"], "extra": {"telefone": "x", "outro": True}}, headers=HEADERS)
        assert response.status_code == 409

    def test_gate_is_skipped_on_a_reorder_inside_the_gated_stage(self, fn):
        cid = fn.add_card(etapa="proposta", pos="2")
        fn.add_card(etapa="proposta", pos="1")
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["proposta"], "novo_indice": 0}, headers=HEADERS)
        assert response.status_code == 200

    def test_inactive_destination_is_409(self, fn):
        dead = fn.add_stage("morta", posicao=9, ativo=False)
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": dead}, headers=HEADERS)
        assert response.status_code == 409 and response.json()["error"]["code"] == "etapa_inativa"
        assert fn.snapshot() == before

    def test_another_tenants_stage_is_404(self, fn):
        foreign = fn.add_stage("alheia", posicao=5, org=OTHER_ORG)
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": foreign}, headers=HEADERS)
        assert response.status_code == 404 and response.json()["error"]["code"] == "stage_not_found"
        assert fn.snapshot() == before

    def test_closed_card_cannot_move(self, fn):
        cid = fn.add_card(etapa="entrada", status="ganho")
        before = fn.snapshot()
        response = fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages["fechado"]}, headers=HEADERS)
        assert response.status_code == 409 and response.json()["error"]["code"] == "card_fechado"
        assert fn.snapshot() == before

    def test_missing_card_is_404(self, fn):
        response = fn.client.post(fn.url(f"/cards/{CARD}/mover-etapa"), json={"para_etapa_id": fn.stages["fechado"]}, headers=HEADERS)
        assert response.status_code == 404 and response.json()["error"]["code"] == "card_not_found"


class TestLoseReopenArchive:
    def test_perder_records_the_closed_reason(self, fn):
        cid = fn.add_card(etapa="entrada")
        response = fn.client.post(fn.url(f"/cards/{cid}/perder"), json={"motivo_codigo": "preco", "motivo_texto": " caro "}, headers=HEADERS)
        assert response.status_code == 200
        card = response.json()["data"]
        assert (card["status"], card["motivo_perda_codigo"], card["motivo_perda"]) == ("perdido", "preco", "caro")
        assert fn.audit[-1][1] == "perder"

    @pytest.mark.parametrize("body,code", [({}, "motivo_obrigatorio"), ({"motivo_codigo": "zzz"}, "motivo_desconhecido"), ({"motivo_codigo": "outro"}, "motivo_obrigatorio")])
    def test_perder_refusals_write_nothing(self, fn, body, code):
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        response = fn.client.post(fn.url(f"/cards/{cid}/perder"), json=body, headers=HEADERS)
        assert response.status_code == 422 and response.json()["error"]["code"] == code
        assert fn.snapshot() == before

    def test_perder_a_lost_card_is_409(self, fn):
        cid = fn.add_card(etapa="entrada", status="perdido")
        response = fn.client.post(fn.url(f"/cards/{cid}/perder"), json={"motivo_codigo": "preco"}, headers=HEADERS)
        assert response.status_code == 409 and response.json()["error"]["code"] == "card_fechado"

    def test_reabrir_clears_the_loss(self, fn):
        cid = fn.add_card(etapa="entrada", status="perdido", motivo_perda_codigo="preco", motivo_perda="caro")
        card = fn.client.post(fn.url(f"/cards/{cid}/reabrir"), headers=HEADERS).json()["data"]
        assert (card["status"], card["motivo_perda_codigo"], card["motivo_perda"]) == ("aberto", None, None)
        assert fn.audit[-1][1] == "reabrir"

    def test_reabrir_an_open_card_is_a_no_op(self, fn):
        cid = fn.add_card(etapa="entrada")
        before = fn.snapshot()
        assert fn.client.post(fn.url(f"/cards/{cid}/reabrir"), headers=HEADERS).status_code == 200
        assert fn.snapshot() == before

    def test_arquivar(self, fn):
        cid = fn.add_card(etapa="entrada")
        assert fn.client.post(fn.url(f"/cards/{cid}/arquivar"), headers=HEADERS).json()["data"]["status"] == "arquivado"
        again = fn.client.post(fn.url(f"/cards/{cid}/arquivar"), headers=HEADERS)
        assert again.status_code == 409 and again.json()["error"]["code"] == "card_fechado"

    def test_missing_card_is_404(self, fn):
        for verb in ("reabrir", "arquivar"):
            assert fn.client.post(fn.url(f"/cards/{CARD}/{verb}"), headers=HEADERS).status_code == 404
        assert fn.client.post(fn.url(f"/cards/{CARD}/perder"), json={"motivo_codigo": "preco"}, headers=HEADERS).status_code == 404


class TestActions:
    def test_action_returns_card_and_efeitos(self, fn):
        cid = fn.add_card(etapa="proposta")
        response = fn.client.post(fn.url(f"/cards/{cid}/acoes/aceitar"), json={"payload": {"valor": 99}}, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["efeitos"] == {"aceito": True, "valor": 99} and data["card"]["valor"] == 99
        assert fn.audit[-1][1] == "acao"

    def test_unknown_action_is_404(self, fn):
        cid = fn.add_card(etapa="entrada")
        response = fn.client.post(fn.url(f"/cards/{cid}/acoes/nada"), json={}, headers=HEADERS)
        assert response.status_code == 404 and response.json()["error"]["code"] == "acao_desconhecida"

    def test_action_outside_its_stage_role_is_404_and_does_not_run(self, fn):
        cid = fn.add_card(etapa="entrada", valor=5)
        response = fn.client.post(fn.url(f"/cards/{cid}/acoes/aceitar"), json={"payload": {"valor": 99}}, headers=HEADERS)
        assert response.status_code == 404 and response.json()["error"]["code"] == "acao_desconhecida"
        assert fn.card(cid)["valor"] == 5

    def test_action_on_a_closed_card_is_409(self, fn):
        cid = fn.add_card(etapa="entrada", status="perdido")
        response = fn.client.post(fn.url(f"/cards/{cid}/acoes/livre"), json={}, headers=HEADERS)
        assert response.status_code == 409 and response.json()["error"]["code"] == "card_fechado"


class TestMovimentos:
    def test_history_is_newest_first_with_resolved_stage_labels_and_pages(self, fn):
        cid = fn.add_card(etapa="entrada", telefone="1")
        for stage in ("fechado", "entrada", "fechado"):
            assert fn.client.post(fn.url(f"/cards/{cid}/mover-etapa"), json={"para_etapa_id": fn.stages[stage]}, headers=HEADERS).status_code == 200
        # the mock stamps no created_at; give the rows a real order
        rows = fn.movimentos(cid)
        for i, row in enumerate(rows):
            row["created_at"] = f"2026-02-0{i + 1}T00:00:00+00:00"
        first = fn.client.get(fn.url(f"/cards/{cid}/movimentos?limite=2"), headers=HEADERS).json()["data"]
        assert [i["para_etapa"]["slug"] for i in first["items"]] == ["fechado", "entrada"]
        assert first["items"][0]["de_etapa"]["slug"] == "entrada" and first["items"][0]["ator"] == {"id": USER, "nome": None}
        assert first["next_cursor"] and first["total"] == 3
        assert first["items"][0]["kind"] == "movimento" and first["items"][0]["ocorrido_em"]
        second = fn.client.get(fn.url(f"/cards/{cid}/movimentos?limite=2&cursor={first['next_cursor']}"), headers=HEADERS).json()["data"]
        assert [i["para_etapa"]["slug"] for i in second["items"]] == ["fechado"] and second["next_cursor"] is None
        assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})

    def test_bad_cursor_is_422(self, fn):
        cid = fn.add_card(etapa="entrada")
        assert fn.client.get(fn.url(f"/cards/{cid}/movimentos?cursor=%%%"), headers=HEADERS).status_code == 422

    def test_missing_card_is_404(self, fn):
        assert fn.client.get(fn.url(f"/cards/{CARD}/movimentos"), headers=HEADERS).status_code == 404


class TestStagesRouterIsScopedToo:
    def test_stage_list_is_the_effective_tenants_only(self, fn):
        fn.add_stage("alheia", posicao=5, org=OTHER_ORG)
        slugs = [s["slug"] for s in fn.client.get(fn.url("/etapas"), headers=HEADERS).json()["data"]]
        assert slugs == ["entrada", "proposta", "fechado"]

    def test_stage_create_stamps_the_effective_org(self, fn):
        response = fn.client.post(fn.url("/etapas"), json={"label": "Nova"}, headers=HEADERS)
        assert response.status_code == 200
        created = next(r for r in fn.rows("pipeline_stages") if r["slug"] == "nova")
        assert created["org_id"] == fn.effective_org


class TestTenancy:
    def test_org_funnel_refuses_a_session_without_an_org_on_every_route(self, org_fn):
        no_org = {"Authorization": "Bearer t", "X-Can-Write": "1"}
        for method, path, body in ROUTES:
            response = _call(org_fn, method, path, body, no_org)
            assert response.status_code == 500, (method, path)

    def test_org_funnel_never_widens_to_other_tenants(self, org_fn):
        org_fn.add_card(titulo="mine", etapa="entrada")
        org_fn.add_card(titulo="theirs", etapa="entrada", org=OTHER_ORG)
        cards = org_fn.client.get(org_fn.url("/board"), headers=HEADERS).json()["data"][0]["cards"]
        assert [c["titulo"] for c in cards] == ["mine"]

    def test_org_funnel_other_tenants_card_is_404_everywhere(self, org_fn):
        theirs = org_fn.add_card(titulo="theirs", etapa="entrada", org=OTHER_ORG)
        before = org_fn.snapshot()
        probes = [
            ("GET", f"/cards/{theirs}", None), ("PATCH", f"/cards/{theirs}", {"titulo": "x"}),
            ("POST", f"/cards/{theirs}/mover-etapa", {"para_etapa_id": org_fn.stages["fechado"]}),
            ("POST", f"/cards/{theirs}/perder", {"motivo_codigo": "preco"}), ("POST", f"/cards/{theirs}/reabrir", None),
            ("POST", f"/cards/{theirs}/arquivar", None), ("POST", f"/cards/{theirs}/acoes/livre", {}),
            ("GET", f"/cards/{theirs}/movimentos", None),
        ]
        for method, path, body in probes:
            response = _call(org_fn, method, path, body, HEADERS)
            assert response.status_code == 404, (method, path)
            assert response.json()["error"]["code"] == "card_not_found"
        assert org_fn.snapshot() == before

    def test_platform_funnel_ignores_the_session_org_and_uses_the_declared_one(self, funnel_schema_cache):
        from .conftest import build_funnel

        f = build_funnel("platform")
        f.add_stage("entrada", posicao=0)
        f.add_stage("alheia", posicao=1, org=OTHER_ORG)
        f.add_card(titulo="lead", etapa="entrada")
        for headers in (HEADERS, {"Authorization": "Bearer t", "X-Org": OTHER_ORG, "X-Can-Write": "1"}, {"Authorization": "Bearer t", "X-Can-Write": "1"}):
            cols = f.client.get(f.url("/board"), headers=headers).json()["data"]
            assert [c["stage"]["slug"] for c in cols] == ["entrada"] and cols[0]["total"] == 1
        assert PLATFORM_ORG not in (ORG, OTHER_ORG)
