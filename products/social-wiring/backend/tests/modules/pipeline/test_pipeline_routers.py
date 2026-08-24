"""Router tests for social-wiring's Funil de Vendas + Processos de Venda.

What these protect, beyond "it responds 200":

* **Org scoping.** This module talks to a schema-scoped ADMIN client, so RLS is
  NOT doing the filtering — every query must carry `org_id` itself. A test that
  only ever sees one tenant would never catch a missing filter, so the fixtures
  seed another org's stage and assert it never appears.
* **The history write.** Every move goes through the shared `move_card`, which
  is the only reason this board has an audit trail at all.
* **Role-keyed accept.** The seam resolves the gate stage by `papel`, so
  renaming "Proposta" cannot break it.
* **No create endpoint.** Cards come from the lead trigger; a POST would be a
  second, forkable way to make one.
"""
from __future__ import annotations

import pytest

from .conftest import (
    ORG_A,
    OTHER_ORG_STAGE,
    PROC_STAGE_ID,
    STAGE_ID,
    auth_headers,
    atendimento,
    processo,
    seed_titular,
)


class TestFunilBoard:
    def test_emits_every_configured_stage(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        r = http_client.get("/api/funil", headers=auth_headers())
        assert r.status_code == 200
        colunas = r.json()["data"]
        assert [c["stage"]["slug"] for c in colunas] == [
            "novo", "contato", "qualificado", "proposta", "negociacao", "fechado"
        ]
        assert [c["etapa"] for c in colunas] == [s for s in STAGE_ID.values()]

    def test_another_orgs_stage_never_appears(self, http_client):
        """The admin client sees every tenant; the QUERY must not."""
        r = http_client.get("/api/funil", headers=auth_headers())
        assert r.status_code == 200
        ids = [c["etapa"] for c in r.json()["data"]]
        assert OTHER_ORG_STAGE["id"] not in ids

    def test_groups_and_totals(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [
            atendimento("neg-1", "proposta", valor_estimado=1000),
            atendimento("neg-2", "proposta", valor_estimado=500),
            atendimento("neg-3", "novo", valor_estimado=250),
        ])
        r = http_client.get("/api/funil", headers=auth_headers())
        colunas = {c["stage"]["slug"]: c for c in r.json()["data"]}
        assert colunas["proposta"]["total"] == 2
        assert colunas["proposta"]["valorTotal"] == 1500
        assert colunas["novo"]["total"] == 1

    def test_closed_deals_are_off_the_board(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [
            atendimento("neg-1", "fechado", status="aceita", closed_at="2026-07-28T00:00:00Z"),
        ])
        r = http_client.get("/api/funil", headers=auth_headers())
        assert all(c["total"] == 0 for c in r.json()["data"])

    def test_dto_strips_unknown_columns(self, http_client):
        http_client.scoped.set_table_data(
            "atendimentos", [atendimento("neg-1", "novo", coluna_interna="não vaza")]
        )
        r = http_client.get("/api/funil", headers=auth_headers())
        cards = [c for col in r.json()["data"] for c in col["cards"]]
        assert cards and "coluna_interna" not in cards[0]


class TestP14OneCardPerPerson:
    """P1.4 completion (lead-card-hub roadmap §1/§5): a Meta lead fires
    BOTH `spawn_funil_card_on_lead` and `spawn_funil_card_on_meta_lead`, so
    one human can end up with two `atendimentos` rows. Migration `054`
    + `clientes_service._collapse_atendimentos` mark the loser
    (`substituida_por`) without deleting it; `obter_funil` excludes it and
    merges the union of both origins' data onto the survivor."""

    _CAMPANHA = {
        "id": "m1", "full_name": "Ana Silva", "email": None, "phone": "11999998888",
        "campaign_id": "camp-1", "campaign_name": "Campanha X", "form_id": None,
        "form_name": None, "ad_id": None, "adset_id": None, "platform": "facebook",
        "is_organic": False, "created_time": "2026-01-01T00:00:00Z", "answers": {"q": "a"},
    }

    def test_only_the_survivor_reaches_the_board(self, http_client):
        survivor = atendimento("neg-survivor", "novo", cliente_id="c1")
        loser = atendimento(
            "neg-loser", "novo", cliente_id="c1", substituida_por="neg-survivor",
            lead=None, campanha=self._CAMPANHA,
        )
        http_client.scoped.set_table_data("atendimentos", [survivor, loser])
        r = http_client.get("/api/funil", headers=auth_headers())
        assert r.status_code == 200
        cards = [c for col in r.json()["data"] for c in col["cards"]]
        assert [c["id"] for c in cards] == ["neg-survivor"]

    def test_dto_carries_the_union_of_both_origins(self, http_client):
        """The survivor here is lead-origin only; the collapsed sibling is
        campaign-origin only. Both must still be reachable from the ONE
        card the board now shows — `leadDetailSections` renders from
        `lead`, `campanhaDetailSections` from `campanha`."""
        survivor = atendimento("neg-survivor", "novo", cliente_id="c1")
        loser = atendimento(
            "neg-loser", "novo", cliente_id="c1", substituida_por="neg-survivor",
            lead=None, campanha=self._CAMPANHA,
        )
        http_client.scoped.set_table_data("atendimentos", [survivor, loser])
        r = http_client.get("/api/funil", headers=auth_headers())
        [card] = [c for col in r.json()["data"] for c in col["cards"]]
        assert card["lead"]["cliente_nome"] == "Lead Teste"  # survivor's own
        assert card["campanha"] == self._CAMPANHA               # merged from the sibling
        assert card["colapsadas"] == [{
            "id": "neg-loser", "lead_id": "lead-neg-loser", "meta_ads_lead_id": None,
            "titulo": "Lead Teste", "status": "aberta", "colapsada_em": None,
            "lead": None, "campanha": self._CAMPANHA,
        }]

    def test_survivor_missing_neither_origin_gets_no_merge_but_keeps_its_own(self, http_client):
        """A survivor that already carries BOTH origins (not this defect's
        shape, but possible) must never have its own data overwritten by a
        sibling's."""
        own_campanha = {**self._CAMPANHA, "id": "m-own", "full_name": "Own"}
        survivor = atendimento("neg-survivor", "novo", cliente_id="c1", campanha=own_campanha)
        loser = atendimento(
            "neg-loser", "novo", cliente_id="c1", substituida_por="neg-survivor",
            campanha=self._CAMPANHA,
        )
        http_client.scoped.set_table_data("atendimentos", [survivor, loser])
        r = http_client.get("/api/funil", headers=auth_headers())
        [card] = [c for col in r.json()["data"] for c in col["cards"]]
        assert card["campanha"]["id"] == "m-own"

    def test_a_cliente_id_less_card_still_renders(self, http_client):
        """No person layer resolved yet (or ever, for a keyless lead) must
        never make a card vanish from the board — the no-silent-errors leg
        of this slice."""
        orphan = atendimento("neg-orphan", "novo", cliente_id=None)
        http_client.scoped.set_table_data("atendimentos", [orphan])
        r = http_client.get("/api/funil", headers=auth_headers())
        cards = [c for col in r.json()["data"] for c in col["cards"]]
        assert [c["id"] for c in cards] == ["neg-orphan"]
        assert cards[0]["colapsadas"] == []

    def test_sibling_fetch_batches_past_the_in_filter_limit(self, http_client):
        """`_fetch_colapsadas`'s `in_("substituida_por", ...)` must survive
        more collapsed siblings than one PostgREST `in_` call's URL budget
        (`_IN_FILTER_BATCH`) — an unbatched call over-long request line is
        a bare 400, the exact class `KB § PATTERNS/backend/
        postgrest-row-cap.md` documents."""
        from app.modules.pipeline import configs as cfg

        survivor = atendimento("neg-survivor", "novo", cliente_id="c1")
        siblings = [
            atendimento(
                f"neg-loser-{i}", "novo", cliente_id="c1",
                substituida_por="neg-survivor", lead=None,
                campanha={**self._CAMPANHA, "id": f"m{i}"},
            )
            for i in range(cfg._IN_FILTER_BATCH + 5)
        ]
        http_client.scoped.set_table_data("atendimentos", [survivor, *siblings])
        r = http_client.get("/api/funil", headers=auth_headers())
        assert r.status_code == 200
        [card] = [c for col in r.json()["data"] for c in col["cards"]]
        assert len(card["colapsadas"]) == len(siblings)


class TestNoCreateEndpoint:
    def test_post_atendimentos_is_not_routable(self, http_client):
        """Cards exist because a lead arrived — the DB trigger owns creation."""
        r = http_client.post("/api/atendimentos-venda", json={}, headers=auth_headers())
        assert r.status_code == 405


class TestMoverEtapa:
    def test_move_writes_history(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1")
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        rows = http_client.scoped.table("pipeline_movimentos").inserted_payloads
        assert len(rows) == 1
        assert rows[0]["pipeline"] == "funil"
        assert rows[0]["entidade_id"] == "neg-1"
        assert rows[0]["de_etapa_id"] == STAGE_ID["novo"]
        assert rows[0]["para_etapa_id"] == STAGE_ID["contato"]
        # org stamped, because this history table is org-scoped
        assert rows[0]["org_id"]

    def test_same_stage_move_writes_no_history(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1")
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["novo"], "novo_indice": 2},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        assert http_client.scoped.table("pipeline_movimentos").inserted_payloads == []

    def test_move_to_another_orgs_stage_404s(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": OTHER_ORG_STAGE["id"]},
            headers=auth_headers(),
        )
        assert r.status_code == 404

class TestMoveRequiresNomeECelular:
    """🔴 A card cannot advance while nobody knows who this is (migration 073).

    The requirement is a NAME — whatever the channel supplied — and a phone.
    NOT a full legal name: the first cut of this gate demanded the checklist's
    "Nome Completo" item and therefore refused to move a lead called "Ana",
    which is exactly what a WhatsApp push name looks like. A gate that blocks
    the normal first move of a normal lead is an outage, not a quality gate.
    The legal name arrives later, off the uploaded RG.

    These pin the RULE, not its current membership: `EXIGENCIAS` is expected to
    grow, so the tests name the two requirements explicitly rather than looping
    the tuple — a test that derived its expectation from the code under test
    would keep passing if someone emptied it.
    """

    def test_a_lead_with_neither_field_cannot_move(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1", apto=False, nome=None)
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400
        assert http_client.scoped.table("pipeline_movimentos").inserted_payloads == []

    def test_the_refusal_names_every_missing_field_not_just_the_first(
        self, http_client
    ):
        """Otherwise a two-field gap costs two failed attempts to discover."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1", apto=False, nome=None)
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        detalhe = r.json()["error"]["message"]
        assert "Nome" in detalhe
        assert "Celular" in detalhe

    def test_a_whatsapp_push_name_plus_a_phone_is_enough(self, http_client):
        """🔴 The correction. "Ana" is what almost every lead arrives as, and
        the gate must let her move."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(
            http_client.scoped, "neg-1", apto=False,
            nome="Ana", celular="+5511999998888",
        )
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200

    def test_a_name_alone_is_not_enough(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1", apto=False, nome="Ana")
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400
        assert "Celular" in r.json()["error"]["message"]

    def test_a_celular_alone_is_not_enough(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(
            http_client.scoped, "neg-1", apto=False,
            nome=None, celular="+5511999998888",
        )
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400
        assert "Nome" in r.json()["error"]["message"]

    def test_a_whitespace_only_name_does_not_open_the_gate(self, http_client):
        """A name of "   " satisfies a NOT NULL check and satisfies nobody
        else."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(
            http_client.scoped, "neg-1", apto=False,
            nome="   ", celular="+5511999998888",
        )
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400

    def test_a_phone_keyed_cliente_needs_no_explicit_celular(self, http_client):
        """The number came from the registration act — that IS the celular."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(
            http_client.scoped, "neg-1", apto=False, nome="Ana",
            chave_canonica="+5511999998888", chave_tipo="telefone",
        )
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200

    def test_an_email_keyed_cliente_still_needs_a_phone(self, http_client):
        """🔴 The bug a naive `chave_canonica` read would ship: an email
        address satisfying "Celular"."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(
            http_client.scoped, "neg-1", apto=False, nome="Ana",
            chave_canonica="luciano@example.com", chave_tipo="email",
        )
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400
        assert "Celular" in r.json()["error"]["message"]

    def test_a_human_override_opens_the_gate(self, http_client):
        """The override means "I confirmed this by other means". Honouring it
        on the card but not on the move would just teach people to type a
        placeholder into the column instead."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1", apto=False, nome="Ana")
        http_client.scoped.set_table_data("cliente_documento_checklist", [
            {"id": "ovr-1", "org_id": ORG_A, "cliente_id": "cli-neg-1",
             "item_key": "celular", "concluido_manual": True,
             "concluido_em": "2026-08-24T00:00:00+00:00", "concluido_por": None},
        ])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["contato"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200

    def test_a_bad_stage_is_still_a_404_not_a_gate_complaint(self, http_client):
        """🔴 Ordering. The gate must not answer a foreign stage id with a 400
        about our client data — that reports on OUR record for a request that
        never named a valid destination."""
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        seed_titular(http_client.scoped, "neg-1", apto=False, nome=None)
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": OTHER_ORG_STAGE["id"]},
            headers=auth_headers(),
        )
        assert r.status_code == 404


class TestMoverEtapaGuards:
    def test_move_refuses_a_closed_deal(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [
            atendimento("neg-1", "fechado", status="aceita", closed_at="2026-07-28T00:00:00Z"),
        ])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/mover-etapa",
            json={"para_etapa_id": STAGE_ID["novo"]},
            headers=auth_headers(),
        )
        assert r.status_code == 400


class TestAceitarProposta:
    def test_accept_from_the_role_stage_spawns_a_processo(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["already_accepted"] is False
        inserted = http_client.scoped.table("processos_venda").inserted_payloads
        assert len(inserted) == 1
        # lands on the FIRST configured processos stage, derived from order
        assert inserted[0]["etapa_id"] == PROC_STAGE_ID["contrato"]
        assert inserted[0]["atendimento_id"] == "neg-1"

    def test_accept_is_refused_outside_the_role_stage(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "novo")])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 400
        assert http_client.scoped.table("processos_venda").inserted_payloads == []

    def test_accept_follows_the_ROLE_after_the_stage_is_renamed(self, http_client):
        """The whole point of `papel`: rename the column, keep the feature."""
        renamed = [
            {**s, "label": "Proposta Enviada"} if s["slug"] == "proposta" else s
            for s in http_client.scoped.table("pipeline_stages").select("*").execute().data
        ]
        http_client.scoped.set_table_data("pipeline_stages", renamed)
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 200

    def test_second_accept_is_idempotent(self, http_client):
        http_client.scoped.set_table_data("atendimentos", [atendimento("neg-1", "proposta")])
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1")])
        r = http_client.post(
            "/api/atendimentos-venda/neg-1/aceitar-proposta", headers=auth_headers()
        )
        assert r.status_code == 200
        assert r.json()["data"]["already_accepted"] is True
        assert http_client.scoped.table("processos_venda").inserted_payloads == []


class TestProcessosBoard:
    def test_emits_every_configured_stage(self, http_client):
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1", "briefing")])
        r = http_client.get("/api/processos-venda", headers=auth_headers())
        assert r.status_code == 200
        colunas = r.json()["data"]
        assert [c["stage"]["slug"] for c in colunas] == [
            "contrato", "onboarding", "briefing", "planejamento",
            "execucao", "entrega", "faturamento",
        ]
        briefing = next(c for c in colunas if c["stage"]["slug"] == "briefing")
        assert briefing["total"] == 1

    def test_move_writes_history_for_this_pipeline_too(self, http_client):
        """The gap that existed on erp's Processos board cannot recur here."""
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1", "contrato")])
        r = http_client.post(
            "/api/processos-venda/proc-1/mover-etapa",
            json={"para_etapa_id": PROC_STAGE_ID["briefing"]},
            headers=auth_headers(),
        )
        assert r.status_code == 200
        rows = http_client.scoped.table("pipeline_movimentos").inserted_payloads
        assert len(rows) == 1
        assert rows[0]["pipeline"] == "processos_venda"
        assert rows[0]["para_etapa_id"] == PROC_STAGE_ID["briefing"]

    def test_archive_toggles(self, http_client):
        http_client.scoped.set_table_data("processos_venda", [processo("proc-1", "faturamento")])
        r = http_client.post("/api/processos-venda/proc-1/arquivar", headers=auth_headers())
        assert r.status_code == 200
        assert http_client.scoped.table("processos_venda").updated_payloads == [{"arquivado": True}]


class TestNoAuth:
    """Strict `== 401`. A non-401 here would be a false green — it would mean
    the route is absent or validating before authenticating."""

    @pytest.mark.parametrize("method,path,payload", [
        ("get", "/api/funil", None),
        ("get", "/api/funil/etapas", None),
        ("post", "/api/funil/etapas", {"label": "Nova"}),
        ("patch", "/api/funil/etapas/fstage-0", {"label": "Nova"}),
        ("delete", "/api/funil/etapas/fstage-0", None),
        ("post", "/api/funil/etapas/reordenar", {"ordem": ["fstage-0"]}),
        ("get", "/api/atendimentos-venda", None),
        ("post", "/api/atendimentos-venda/neg-1/mover-etapa", {"para_etapa_id": "fstage-1"}),
        ("post", "/api/atendimentos-venda/neg-1/aceitar-proposta", None),
        ("post", "/api/atendimentos-venda/neg-1/perder", {}),
        ("get", "/api/processos-venda", None),
        ("get", "/api/processos-venda/etapas", None),
        ("post", "/api/processos-venda/proc-1/mover-etapa", {"para_etapa_id": "pstage-1"}),
        ("post", "/api/processos-venda/proc-1/arquivar", None),
    ])
    def test_requires_auth(self, http_client, method, path, payload):
        fn = getattr(http_client, method)
        r = fn(path, json=payload) if payload is not None else fn(path)
        assert r.status_code == 401


class TestStageEditor:
    def test_lists_only_this_pipelines_stages_for_this_org(self, http_client):
        r = http_client.get("/api/funil/etapas", headers=auth_headers())
        assert r.status_code == 200
        rows = r.json()["data"]
        assert {s["pipeline"] for s in rows} == {"funil"}
        assert OTHER_ORG_STAGE["id"] not in {s["id"] for s in rows}

    def test_create_appends_and_slugifies(self, http_client):
        r = http_client.post(
            "/api/funil/etapas", json={"label": "Reunião Agendada"}, headers=auth_headers()
        )
        assert r.status_code == 200
        payload = http_client.scoped.table("pipeline_stages").inserted_payloads[-1]
        assert payload["slug"] == "reuniao_agendada"
        assert payload["posicao"] == 6
        assert payload["pipeline"] == "funil"

    def test_delete_refuses_a_role_bearing_stage(self, http_client):
        r = http_client.delete(
            f"/api/funil/etapas/{STAGE_ID['proposta']}", headers=auth_headers()
        )
        assert r.status_code == 400
        assert "papel" in r.json()["error"]["message"]

    def test_opcoes_serves_the_valid_tokens(self, http_client):
        r = http_client.get("/api/funil/etapas/opcoes", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "primary" in data["cores"]
        assert "proposta_aceite" in data["papeis"]


class TestBoardSearchFindsTheNumberTheCardShows:
    """The board card renders the CANONICAL number through the phone seam
    while the row stores what arrived. Copying it off a card and pasting it
    into the board's own search box must find that card."""

    def _funil_row(self):
        return {
            "id": "n1",
            "titulo": None,
            "lead": {"cliente_nome": "Maria", "contato": "11 98191.2534"},
            "campanha": None,
        }

    def _campanha_row(self):
        return {
            "id": "n2",
            "titulo": None,
            "lead": None,
            "campanha": {"full_name": "Leonora", "phone": "+5511964540451"},
        }

    def test_funil_matches_the_displayed_canonical_number(self):
        from app.modules.pipeline.configs import search_atendimentos

        assert search_atendimentos([self._funil_row()], "+5511981912534")

    def test_funil_matches_a_partial_digit_fragment(self):
        from app.modules.pipeline.configs import search_atendimentos

        assert search_atendimentos([self._funil_row()], "981912534")

    def test_funil_name_search_still_works(self):
        from app.modules.pipeline.configs import search_atendimentos

        assert search_atendimentos([self._funil_row()], "maria")
        assert not search_atendimentos([self._funil_row()], "joão")

    def test_campaign_origin_matches_its_already_canonical_phone(self):
        from app.modules.pipeline.configs import search_atendimentos

        assert search_atendimentos([self._campanha_row()], "5511964540451")

    def test_a_different_number_does_not_match(self):
        from app.modules.pipeline.configs import search_atendimentos

        assert not search_atendimentos([self._funil_row()], "+5511999999999")

    def test_processos_reaches_the_phone_through_the_atendimento(self):
        # The processo board must answer the same query the funil board does,
        # or two boards showing the same deals disagree.
        from app.modules.pipeline.configs import search_processos

        processo = {"id": "p1", "observacoes": None, "atendimento": self._funil_row()}
        assert search_processos([processo], "+5511981912534")


class TestBoardReadsPagePastTheRowCap:
    """PostgREST caps any single response at `db-max-rows` (1000 on Supabase)
    with no error and no truncation signal, so a bare `.select().execute()`
    returns a plausible, WRONG answer. This product has shipped that bug
    repeatedly — a summary reporting `total=1000` against 12 177 real rows,
    and 365 of 1 365 negociações silently skipped (`98377d26`).

    The board reads were under the cap only by the luck of their per-org +
    `status='aberta'` filtering, which is not a property anyone maintains on
    purpose. `MockSupabaseClient` models the cap, so these tests fail against
    an unpaged read rather than merely documenting the intent.
    """

    _OVER_CAP = 1200

    def test_funil_returns_every_card_past_the_cap(self, http_client):
        rows = [atendimento(f"neg-{i:05d}", "novo") for i in range(self._OVER_CAP)]
        http_client.scoped.set_table_data("atendimentos", rows)

        r = http_client.get("/api/funil", headers=auth_headers())

        assert r.status_code == 200
        cards = [c for col in r.json()["data"] for c in col["cards"]]
        assert len(cards) == self._OVER_CAP, (
            f"board returned {len(cards)} of {self._OVER_CAP} — the read was "
            "truncated at PostgREST's row cap instead of paging past it"
        )
        assert len({c["id"] for c in cards}) == self._OVER_CAP, "a page was served twice"

    def test_atendimentos_list_returns_every_row_past_the_cap(self, http_client):
        rows = [atendimento(f"neg-{i:05d}", "novo") for i in range(self._OVER_CAP)]
        http_client.scoped.set_table_data("atendimentos", rows)

        r = http_client.get("/api/atendimentos-venda", headers=auth_headers())

        assert r.status_code == 200
        assert len(r.json()["data"]) == self._OVER_CAP

    def test_processos_board_returns_every_row_past_the_cap(self, http_client):
        rows = [processo(f"proc-{i:05d}") for i in range(self._OVER_CAP)]
        http_client.scoped.set_table_data("processos_venda", rows)

        r = http_client.get("/api/processos-venda", headers=auth_headers())

        assert r.status_code == 200
        cards = [c for col in r.json()["data"] for c in col["cards"]]
        assert len(cards) == self._OVER_CAP
