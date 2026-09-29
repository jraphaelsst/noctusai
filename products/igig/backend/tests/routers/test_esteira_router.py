"""Esteira (editable stages on the seed pipeline) + the public approval portal.

Two groups of properties:

* the BOARD rules (forward one step; backward only with a reason; backward out
  of client approval is a refação, counted atomically; the stage editor is
  admin-only and seeds the org's defaults exactly once);
* the PUBLIC portal's security (unguessable, expirable, single-decision,
  narrow projection, unknown/expired indistinguishable) — plus the smoke-test
  fixes: minting a link moves the tarefa INTO approval, a decision is only
  valid while it is still there, and the agency is actually notified.

Everything runs on one shared `igig` mock (`crm_api` in conftest): the
pipeline code reads through PostgREST, the timer/portal repositories through
the real `SupabaseRecordStore` adapter over the same mock.
"""
from datetime import datetime, timedelta, timezone
from app.services.quadro_comum import hoje_local

import pytest
from noctusai_lib.integrations.persistence import SupabaseRecordStore
from noctusai_lib.testing.clients import TEST_USER_ID

from app.dependencies import coerce_org_uuid
from app.pipelines import ESTEIRA_PADRAO
from app.repositories import Repositorios

#: The org the authed endpoints resolve to (the conftest user's fixture org,
#: through `coerce_org_uuid`). Seeding under the raw string would write to an
#: org the API never reads.
ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def api(crm_api):
    return crm_api


@pytest.fixture
def repos(igig_db) -> Repositorios:
    return Repositorios(SupabaseRecordStore(igig_db))


@pytest.fixture
def etapas(api) -> dict[str, dict]:
    """slug → stage row (seeded by the first read)."""
    resp = api.get("/api/esteira/stages")
    assert resp.status_code == 200, resp.text
    return {s["slug"]: s for s in resp.json()["data"]}


@pytest.fixture
def pauta(igig_db) -> dict:
    cliente = igig_db.table("cliente").insert(
        {"org_id": ORG, "nome": "Padaria Sol", "status": "ativo"}
    ).execute().data[0]
    return igig_db.table("pauta").insert(
        {
            "org_id": ORG,
            "cliente_id": cliente["id"],
            "titulo": "Post institucional",
            "copy_texto": "Pão quentinho todo dia às 6h.",
            "formato": "feed",
        }
    ).execute().data[0]


@pytest.fixture
def tarefa(api, pauta, etapas) -> dict:
    resp = api.post("/api/esteira/tarefas", json={"pauta_id": pauta["id"], "titulo": "Arte do post"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _mover(api, tarefa_id, etapa_id, **extra):
    return api.post(
        f"/api/esteira/tarefas/{tarefa_id}/mover-etapa",
        json={"para_etapa_id": etapa_id, **extra},
    )


def _colocar_em(igig_db, tarefa_id, etapa_id):
    """Place a tarefa on a stage directly (fixture setup, not the rule under test)."""
    igig_db.table("tarefa").update({"etapa_id": etapa_id}).eq("id", tarefa_id).execute()


def _historico(igig_db, tarefa_id):
    return [m for m in igig_db.table("pipeline_movimentos")._data if m["entidade_id"] == tarefa_id]


def _refacoes(igig_db, tarefa_id):
    return next(t for t in igig_db.table("tarefa")._data if t["id"] == tarefa_id)["refacoes"]


# ── Stage editor (seed router) ──────────────────────────────────────
class TestEtapas:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/esteira/stages").status_code == 401

    def test_first_read_seeds_the_eight_default_stages_in_order(self, api, etapas):
        assert list(etapas) == [s.slug for s in ESTEIRA_PADRAO]
        assert etapas["aprovacao_cliente"]["papel"] == "aprovacao_cliente"
        assert etapas["agendado"]["papel"] == "agendado"

    def test_seeding_is_idempotent(self, api, igig_db, etapas):
        api.get("/api/esteira/stages")
        api.get("/api/esteira/board")
        esteira = [s for s in igig_db.table("pipeline_stages")._data if s["pipeline"] == "esteira"]
        assert len(esteira) == len(ESTEIRA_PADRAO)

    def test_opcoes_offer_only_the_esteira_roles(self, api):
        body = api.get("/api/esteira/stages/opcoes").json()["data"]
        assert body["papeis"] == ["aprovacao_cliente", "agendado"]

    def test_non_admin_cannot_create_a_stage(self, api, etapas):
        """The conftest user holds no admin role in the trusted table."""
        resp = api.post("/api/esteira/stages", json={"label": "Legendas"})
        assert resp.status_code == 403
        assert resp.json()["code"] == "admin_obrigatorio"

    def test_write_requires_auth(self, api):
        assert api.raw().post("/api/esteira/stages", json={"label": "X"}).status_code == 401

    def test_admin_can_create_and_the_role_stage_is_protected(self, api, etapas):
        from app.main import app
        from app.pipelines import exigir_admin_do_quadro

        app.dependency_overrides[exigir_admin_do_quadro] = lambda: None
        try:
            criada = api.post("/api/esteira/stages", json={"label": "Legendas"})
            assert criada.status_code == 200, criada.text
            assert criada.json()["data"]["slug"] == "legendas"
            recusada = api.delete(f"/api/esteira/stages/{etapas['aprovacao_cliente']['id']}")
            assert recusada.status_code == 400, "a system-role stage must not be deletable"
        finally:
            app.dependency_overrides.pop(exigir_admin_do_quadro, None)

    def test_deleting_a_stage_with_cards_records_who_moved_them(
        self, api, etapas, tarefa, igig_db,
    ):
        """`delete_stage`'s bulk reassignment now writes ONE `pipeline_movimentos`
        row per moved card, attributed to the deleting admin — the seed's
        `pipeline_stages_router` threads `ctx.user_id` through as `moved_by`
        so this trail exists with NO igig-specific code (tech-lead
        follow-up: audit-trail gap on stage-delete reassignment)."""
        from app.main import app
        from app.pipelines import exigir_admin_do_quadro

        origem = etapas["aguardando_roteiro"]
        destino = etapas["roteiro_em_producao"]
        _colocar_em(igig_db, tarefa["id"], origem["id"])

        app.dependency_overrides[exigir_admin_do_quadro] = lambda: None
        try:
            resp = api.delete(
                f"/api/esteira/stages/{origem['id']}",
                params={"reassign_to": destino["id"]},
            )
        finally:
            app.dependency_overrides.pop(exigir_admin_do_quadro, None)

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["cards_movidos"] == 1

        # The tarefa's own entry-into-the-board row (`de_etapa_id: None`,
        # written on creation — see `test_entry_is_recorded_in_the_history`'s
        # comercial sibling) is ALSO in here; this test cares about the row
        # the stage delete itself just wrote.
        historico = _historico(igig_db, tarefa["id"])
        reassign_row = next(m for m in historico if m["de_etapa_id"] == origem["id"])
        assert reassign_row["pipeline"] == "esteira"
        assert reassign_row["para_etapa_id"] == destino["id"]
        assert reassign_row["responsavel_id"] == TEST_USER_ID


# ── Stage roles (achado 11) ───────────────────────────────────────────
class TestAtribuirPapelEtapa:
    @pytest.fixture
    def admin(self, api):
        from app.main import app
        from app.pipelines import exigir_admin_do_quadro

        app.dependency_overrides[exigir_admin_do_quadro] = lambda: None
        yield api
        app.dependency_overrides.pop(exigir_admin_do_quadro, None)

    def test_requires_auth(self, api, etapas):
        resp = api.raw().patch(
            f"/api/esteira/stages/{etapas['pronto_para_agendamento']['id']}/papel",
            json={"papel": "agendado"},
        )
        assert resp.status_code == 401

    def test_non_admin_is_refused(self, api, etapas):
        resp = api.patch(
            f"/api/esteira/stages/{etapas['pronto_para_agendamento']['id']}/papel",
            json={"papel": "agendado"},
        )
        assert resp.status_code == 403

    def test_reassigning_to_a_new_stage_clears_the_old_holder(self, admin, etapas):
        resp = admin.patch(
            f"/api/esteira/stages/{etapas['pronto_para_agendamento']['id']}/papel",
            json={"papel": "agendado"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["papel"] == "agendado"
        antigo = admin.get("/api/esteira/stages").json()["data"]
        antigo_agendado = next(s for s in antigo if s["slug"] == "agendado")
        assert antigo_agendado["papel"] is None

    def test_refuses_to_clear_the_sole_aprovacao_cliente_holder(self, admin, etapas):
        resp = admin.patch(
            f"/api/esteira/stages/{etapas['aprovacao_cliente']['id']}/papel",
            json={"papel": None},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "papel_obrigatorio"

    def test_refuses_to_silently_drop_agendado_via_reassignment(self, admin, etapas):
        """Symmetric case of achado 11: assigning `aprovacao_cliente` to the
        stage that already holds `agendado` must REFUSE, not silently drop
        `agendado` off the pipeline entirely (tech-lead addendum, 2026-09)."""
        resp = admin.patch(
            f"/api/esteira/stages/{etapas['agendado']['id']}/papel",
            json={"papel": "aprovacao_cliente"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "papel_obrigatorio"
        assert "Agendado" in resp.json()["detail"]
        etapas_atuais = {s["slug"]: s for s in admin.get("/api/esteira/stages").json()["data"]}
        assert etapas_atuais["agendado"]["papel"] == "agendado"  # untouched
        assert etapas_atuais["aprovacao_cliente"]["papel"] == "aprovacao_cliente"  # untouched

    def test_reassigning_aprovacao_cliente_elsewhere_is_the_sanctioned_path(
        self, admin, etapas
    ):
        """The 409 above forces this single-call path instead: hand the role
        to a DIFFERENT stage, and the old holder is cleared automatically."""
        resp = admin.patch(
            f"/api/esteira/stages/{etapas['revisao_interna']['id']}/papel",
            json={"papel": "aprovacao_cliente"},
        )
        assert resp.status_code == 200, resp.text
        etapas_atuais = {s["slug"]: s for s in admin.get("/api/esteira/stages").json()["data"]}
        assert etapas_atuais["revisao_interna"]["papel"] == "aprovacao_cliente"
        assert etapas_atuais["aprovacao_cliente"]["papel"] is None

    def test_no_op_when_already_holding_the_role(self, admin, etapas):
        resp = admin.patch(
            f"/api/esteira/stages/{etapas['aprovacao_cliente']['id']}/papel",
            json={"papel": "aprovacao_cliente"},
        )
        assert resp.status_code == 200

    def test_unknown_stage_returns_404(self, admin):
        resp = admin.patch(
            "/api/esteira/stages/nao-existe/papel", json={"papel": "agendado"}
        )
        assert resp.status_code == 404


# ── Board ───────────────────────────────────────────────────────────
class TestBoard:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/esteira/board").status_code == 401

    def test_every_stage_is_a_column_even_when_empty(self, api, tarefa):
        colunas = api.get("/api/esteira/board").json()["data"]
        assert [c["stage"]["slug"] for c in colunas] == [s.slug for s in ESTEIRA_PADRAO]
        assert colunas[0]["total"] == 1
        assert all(c["total"] == 0 for c in colunas[1:])

    def test_cards_carry_cliente_pauta_and_responsavel(self, api, tarefa):
        """Smoke finding 5: the cards showed none of these."""
        card = api.get("/api/esteira/board").json()["data"][0]["cards"][0]
        assert card["cliente"]["nome"] == "Padaria Sol"
        assert card["pauta"]["titulo"] == "Post institucional"
        assert "responsavel" in card

    def test_filters_by_cliente(self, api, tarefa):
        vazio = api.get("/api/esteira/board", params={"cliente_id": "outro"}).json()["data"]
        assert sum(c["total"] for c in vazio) == 0
        cheio = api.get(
            "/api/esteira/board", params={"cliente_id": tarefa["cliente_id"]}
        ).json()["data"]
        assert sum(c["total"] for c in cheio) == 1


# ── Create ──────────────────────────────────────────────────────────
class TestCriarTarefa:
    def test_requires_auth(self, api, pauta):
        resp = api.raw().post("/api/esteira/tarefas", json={"pauta_id": pauta["id"], "titulo": "X"})
        assert resp.status_code == 401

    def test_lands_at_the_first_stage_with_the_pautas_cliente(self, tarefa, pauta, etapas):
        assert tarefa["etapa_id"] == etapas["aguardando_roteiro"]["id"]
        assert tarefa["cliente_id"] == pauta["cliente_id"]

    def test_records_the_entry_in_the_history(self, tarefa, igig_db, etapas):
        entrada = _historico(igig_db, tarefa["id"])
        assert len(entrada) == 1
        assert entrada[0]["de_etapa_id"] is None
        assert entrada[0]["para_etapa_id"] == etapas["aguardando_roteiro"]["id"]

    def test_missing_pauta_returns_404(self, api, etapas):
        resp = api.post("/api/esteira/tarefas", json={"pauta_id": "nao-existe", "titulo": "X"})
        assert resp.status_code == 404

    def test_missing_pauta_message_agrees_in_gender(self, api, etapas):
        """The seed `NotFoundError` used to say 'Pauta não encontrado'
        through `qc.carregar` while every router-level 404 already said
        'Pauta não encontrada' — a gender mismatch (achado 23)."""
        resp = api.post("/api/esteira/tarefas", json={"pauta_id": "nao-existe", "titulo": "X"})
        assert "Pauta não encontrada" in resp.text
        assert "Pauta não encontrado" not in resp.text


# ── One tarefa by id, regardless of the board's cliente filter ────────
class TestObterTarefa:
    """`?tarefa=<id>` deep links (a decision or automation notification) used
    to resolve ONLY against whatever the board's active `?cliente=` filter
    happened to have loaded — a tarefa that genuinely exists, but belongs to
    a DIFFERENT cliente than the one currently filtered, read as "tarefa não
    encontrada". This endpoint has no filter at all, so the frontend can
    fetch-and-open it independent of the board's current view."""

    def test_requires_auth(self, api, tarefa):
        resp = api.raw().get(f"/api/esteira/tarefas/{tarefa['id']}")
        assert resp.status_code == 401

    def test_returns_the_rich_card_shape(self, api, tarefa, pauta):
        resp = api.get(f"/api/esteira/tarefas/{tarefa['id']}")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["id"] == tarefa["id"]
        # The same nested shape the board's card carries — the detail sheet
        # needs these, unlike the narrow `TarefaOut` create/edit responses.
        assert body["pauta"]["id"] == pauta["id"]
        assert body["cliente"]["nome"] == "Padaria Sol"

    def test_missing_tarefa_returns_404(self, api):
        assert api.get("/api/esteira/tarefas/nao-existe").status_code == 404

    def test_another_orgs_tarefa_returns_404(self, api, core_db, igig_db, pauta):
        """Org-scoped: `qc.carregar` filters on `org_id`, so a tarefa that
        exists but belongs to a different org is indistinguishable from one
        that does not exist at all."""
        de_outra_org = igig_db.table("tarefa").insert(
            {
                "org_id": "outra-org", "pauta_id": pauta["id"], "titulo": "Alheia",
                "etapa_id": pauta["id"],  # any non-null id; not read by this test
            }
        ).execute().data[0]
        resp = api.get(f"/api/esteira/tarefas/{de_outra_org['id']}")
        assert resp.status_code == 404


# ── Edit ────────────────────────────────────────────────────────────
class TestAtualizarTarefa:
    """achado 3: there was no way to fix título/responsável/prazo/pauta
    short of deleting the tarefa (and losing its apontamentos)."""

    def test_requires_auth(self, api, tarefa):
        resp = api.raw().patch(
            f"/api/esteira/tarefas/{tarefa['id']}", json={"titulo": "Novo"}
        )
        assert resp.status_code == 401

    def test_edits_titulo(self, api, tarefa):
        resp = api.patch(f"/api/esteira/tarefas/{tarefa['id']}", json={"titulo": "Carrossel novo"})
        assert resp.status_code == 200
        assert resp.json()["titulo"] == "Carrossel novo"

    def test_edits_prazo(self, api, tarefa):
        resp = api.patch(f"/api/esteira/tarefas/{tarefa['id']}", json={"prazo": "2026-12-01"})
        assert resp.status_code == 200
        assert resp.json()["prazo"] == "2026-12-01"

    def test_changing_pauta_follows_the_new_pautas_cliente(self, api, igig_db, tarefa, pauta):
        outro_cliente = igig_db.table("cliente").insert(
            {"org_id": ORG, "nome": "Café Lua", "status": "ativo"}
        ).execute().data[0]
        outra_pauta = igig_db.table("pauta").insert(
            {"org_id": ORG, "cliente_id": outro_cliente["id"], "titulo": "Post da lua"}
        ).execute().data[0]
        resp = api.patch(
            f"/api/esteira/tarefas/{tarefa['id']}", json={"pauta_id": outra_pauta["id"]}
        )
        assert resp.status_code == 200
        assert resp.json()["cliente_id"] == outro_cliente["id"]

    def test_unknown_responsavel_returns_404(self, api, tarefa):
        resp = api.patch(
            f"/api/esteira/tarefas/{tarefa['id']}", json={"responsavel_id": "nao-existe"}
        )
        assert resp.status_code == 404

    def test_no_fields_returns_400(self, api, tarefa):
        assert api.patch(f"/api/esteira/tarefas/{tarefa['id']}", json={}).status_code == 400

    def test_cannot_move_etapa_through_this_endpoint(self, api, tarefa):
        """Stage moves stay `mover-etapa`'s job — this endpoint doesn't even
        accept the field."""
        resp = api.patch(f"/api/esteira/tarefas/{tarefa['id']}", json={"etapa_id": "x"})
        assert resp.status_code == 422

    def test_unknown_tarefa_returns_404(self, api, etapas):
        resp = api.patch("/api/esteira/tarefas/nao-existe", json={"titulo": "X"})
        assert resp.status_code == 404


# ── Delete ──────────────────────────────────────────────────────────
class TestExcluirTarefa:
    def test_requires_auth(self, api, tarefa):
        assert api.raw().delete(f"/api/esteira/tarefas/{tarefa['id']}").status_code == 401

    def test_deletes_and_returns_204(self, api, igig_db, tarefa):
        resp = api.delete(f"/api/esteira/tarefas/{tarefa['id']}")
        assert resp.status_code == 204
        assert resp.content == b""
        assert all(t["id"] != tarefa["id"] for t in igig_db.table("tarefa")._data)
        colunas = api.get("/api/esteira/board").json()["data"]
        assert sum(c["total"] for c in colunas) == 0

    def test_keeps_the_history_as_the_audit_trail(self, api, igig_db, tarefa):
        api.delete(f"/api/esteira/tarefas/{tarefa['id']}")
        assert len(_historico(igig_db, tarefa["id"])) == 1

    def test_unknown_tarefa_returns_404(self, api, etapas):
        assert api.delete("/api/esteira/tarefas/nao-existe").status_code == 404

    def test_another_orgs_tarefa_is_404_and_untouched(self, api, igig_db, tarefa):
        igig_db.table("tarefa").update({"org_id": "outra-org"}).eq("id", tarefa["id"]).execute()
        assert api.delete(f"/api/esteira/tarefas/{tarefa['id']}").status_code == 404
        assert any(t["id"] == tarefa["id"] for t in igig_db.table("tarefa")._data)

    def test_refuses_when_hours_are_logged(self, api, igig_db, tarefa):
        """achado 4 (esteira half): deleting used to erase apontamentos with
        no warning — the input to custo real / DRE."""
        igig_db.table("apontamento").insert({
            "org_id": ORG, "tarefa_id": tarefa["id"], "usuario_id": TEST_USER_ID,
            "iniciado_em": "2026-01-01T10:00:00", "encerrado_em": "2026-01-01T10:40:00",
            "minutos": 40,
        }).execute()
        resp = api.delete(f"/api/esteira/tarefas/{tarefa['id']}")
        assert resp.status_code == 409
        assert resp.json()["code"] == "horas_serao_perdidas"
        assert "40 min" in resp.json()["detail"]
        assert any(t["id"] == tarefa["id"] for t in igig_db.table("tarefa")._data)

    def test_confirming_deletes_it_anyway(self, api, igig_db, tarefa):
        igig_db.table("apontamento").insert({
            "org_id": ORG, "tarefa_id": tarefa["id"], "usuario_id": TEST_USER_ID,
            "iniciado_em": "2026-01-01T10:00:00", "encerrado_em": "2026-01-01T10:40:00",
            "minutos": 40,
        }).execute()
        resp = api.delete(
            f"/api/esteira/tarefas/{tarefa['id']}", params={"confirmar_perda_horas": "true"}
        )
        assert resp.status_code == 204
        assert all(t["id"] != tarefa["id"] for t in igig_db.table("tarefa")._data)


# ── Move rules ──────────────────────────────────────────────────────
class TestMoverEtapa:
    def test_requires_auth(self, api, tarefa, etapas):
        resp = api.raw().post(
            f"/api/esteira/tarefas/{tarefa['id']}/mover-etapa",
            json={"para_etapa_id": etapas["roteiro_em_producao"]["id"]},
        )
        assert resp.status_code == 401

    def test_forward_one_step_is_allowed_and_logged(self, api, igig_db, tarefa, etapas):
        resp = _mover(api, tarefa["id"], etapas["roteiro_em_producao"]["id"])
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["etapa_id"] == etapas["roteiro_em_producao"]["id"]
        movimento = _historico(igig_db, tarefa["id"])[-1]
        assert movimento["de_etapa_id"] == etapas["aguardando_roteiro"]["id"]
        assert movimento["responsavel_id"] == TEST_USER_ID

    def test_skipping_forward_is_409(self, api, tarefa, etapas):
        resp = _mover(api, tarefa["id"], etapas["design_em_producao"]["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "etapa_invalida"

    def test_backward_without_a_reason_is_422(self, api, igig_db, tarefa, etapas):
        _colocar_em(igig_db, tarefa["id"], etapas["revisao_interna"]["id"])
        resp = _mover(api, tarefa["id"], etapas["aguardando_roteiro"]["id"])
        assert resp.status_code == 422
        assert resp.json()["code"] == "motivo_obrigatorio"

    def test_backward_any_distance_with_a_reason(self, api, igig_db, tarefa, etapas):
        _colocar_em(igig_db, tarefa["id"], etapas["revisao_interna"]["id"])
        resp = _mover(api, tarefa["id"], etapas["aguardando_roteiro"]["id"], motivo="refazer o roteiro")
        assert resp.status_code == 200, resp.text
        assert _historico(igig_db, tarefa["id"])[-1]["motivo"] == "refazer o roteiro"
        assert _refacoes(igig_db, tarefa["id"]) == 0, "not out of approval — no refação"

    def test_backward_out_of_approval_counts_a_refacao_atomically(
        self, api, igig_db, tarefa, etapas
    ):
        _colocar_em(igig_db, tarefa["id"], etapas["aprovacao_cliente"]["id"])
        resp = _mover(api, tarefa["id"], etapas["revisao_interna"]["id"], motivo="cliente pediu")
        assert resp.status_code == 200, resp.text
        assert _refacoes(igig_db, tarefa["id"]) == 1
        assert ("incrementar_refacoes", {"p_tarefa_id": tarefa["id"], "p_org_id": ORG}) in (
            igig_db.rpc_calls
        ), "the increment must be the atomic database function, not a read-then-write"

    def test_reorder_within_the_column_needs_no_reason(self, api, tarefa, etapas):
        resp = _mover(api, tarefa["id"], etapas["aguardando_roteiro"]["id"], novo_indice=0)
        assert resp.status_code == 200

    def test_unknown_stage_returns_404(self, api, tarefa, etapas):
        assert _mover(api, tarefa["id"], "nao-existe").status_code == 404

    def test_unknown_tarefa_returns_404(self, api, etapas):
        assert _mover(api, "nao-existe", etapas["roteiro_em_producao"]["id"]).status_code == 404

    def test_unknown_field_returns_422(self, api, tarefa, etapas):
        resp = _mover(api, tarefa["id"], etapas["roteiro_em_producao"]["id"], etapa="x")
        assert resp.status_code == 422


# ── Timesheet ───────────────────────────────────────────────────────
class TestTimesheet:
    def test_iniciar_requires_auth(self, api, tarefa):
        resp = api.raw().post(f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar")
        assert resp.status_code == 401

    def test_the_timer_runs_as_the_authenticated_user_never_the_payload(self, api, tarefa):
        """Smoke finding 3: a payload `usuario_id` booked hours onto anyone."""
        resp = api.post(
            f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar", json={"usuario_id": "colega"}
        )
        assert resp.status_code == 201
        assert resp.json()["usuario_id"] == TEST_USER_ID
        assert resp.json()["encerrado_em"] is None

    def test_the_segment_records_the_callers_profissional(self, api, igig_db, tarefa):
        """Smoke finding 8: responsável is a profissional; so is the timer's owner."""
        prof = igig_db.table("profissional").insert(
            {"org_id": ORG, "nome": "Ana", "usuario_id": TEST_USER_ID, "ativo": True}
        ).execute().data[0]
        resp = api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar")
        assert resp.json()["profissional_id"] == prof["id"]

    def test_encerrar_closes_the_callers_segment(self, api, tarefa):
        api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar")
        resp = api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/encerrar")
        assert resp.status_code == 200
        assert resp.json()["encerrado_em"] is not None

    def test_encerrar_without_a_running_timer_returns_404(self, api, tarefa):
        assert api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/encerrar").status_code == 404

    def test_iniciar_on_a_missing_tarefa_returns_404(self, api, etapas):
        assert api.post("/api/esteira/tarefas/nao-existe/timer/iniciar").status_code == 404

    def test_iniciar_reports_when_it_closed_another_running_timer(self, api, pauta, etapas):
        """achado 22: this used to happen with zero feedback on screen."""
        outra = api.post(
            "/api/esteira/tarefas", json={"pauta_id": pauta["id"], "titulo": "Outra tarefa"}
        ).json()
        primeiro = api.post(f"/api/esteira/tarefas/{outra['id']}/timer/iniciar")
        assert primeiro.json()["timer_anterior_encerrado"] is False

        segundo = api.post(f"/api/esteira/tarefas/{outra['id']}/timer/iniciar")
        # Starting on the SAME tarefa still auto-closes the running one.
        assert segundo.json()["timer_anterior_encerrado"] is True

    def test_sub_minute_sessions_still_add_up_in_the_tarefas_total(
        self, api, igig_db, tarefa, repos,
    ):
        """achado 22: three 40-second sessions used to record 0+0+0 = zero
        minutes — each one floored away on its own."""
        for _ in range(3):
            api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/iniciar")
            aberto = [
                a for a in igig_db.table("apontamento")._data
                if a.get("tarefa_id") == tarefa["id"] and a.get("encerrado_em") is None
            ][0]
            passado = datetime.now(timezone.utc) - timedelta(seconds=40)
            igig_db.table("apontamento").update(
                {"iniciado_em": passado.isoformat()}
            ).eq("id", aberto["id"]).execute()
            api.post(f"/api/esteira/tarefas/{tarefa['id']}/timer/encerrar")

        assert repos.apontamento.minutos_da_tarefa(ORG, tarefa["id"]) == 2


# ── Approval link minting ───────────────────────────────────────────
class TestLinkAprovacao:
    def test_requires_auth(self, api, tarefa):
        resp = api.raw().post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        assert resp.status_code == 401

    def test_minting_moves_the_tarefa_into_approval(self, api, igig_db, tarefa, etapas):
        """Smoke finding 4: the link used to leave the card wherever it was."""
        resp = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        assert resp.status_code == 201
        assert resp.json()["token"]
        atual = next(t for t in igig_db.table("tarefa")._data if t["id"] == tarefa["id"])
        assert atual["etapa_id"] == etapas["aprovacao_cliente"]["id"]

    def test_token_is_long_and_unpredictable(self, api, tarefa):
        """A guessable token exposes unpublished client content."""
        tokens = {
            api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()["token"]
            for _ in range(5)
        }
        assert len(tokens) == 5, "tokens must not repeat"
        for token in tokens:
            _org, _, secret = token.partition(".")
            assert len(secret) >= 32, "secret half must carry real entropy"

    def test_refused_once_past_approval(self, api, igig_db, tarefa, etapas):
        _colocar_em(igig_db, tarefa["id"], etapas["agendado"]["id"])
        resp = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        assert resp.status_code == 409
        assert resp.json()["code"] == "etapa_invalida"

    def test_missing_task_returns_404(self, api, etapas):
        assert api.post("/api/esteira/tarefas/nao-existe/link-aprovacao").status_code == 404

    def test_minting_again_revokes_the_older_undecided_link(self, api, repos, tarefa):
        """achado 6: every click used to leave the previous link live for the
        rest of its 14 days — an old link could decide a round of feedback
        the client was never shown."""
        primeiro = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()
        api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        aprovacao_antiga = repos.aprovacao.buscar(ORG, primeiro["id"])
        assert repos.aprovacao.expirada(aprovacao_antiga)
        resp = api.raw().get(f"/api/esteira/aprovar/{primeiro['token']}")
        assert resp.status_code == 404

    def test_a_decided_link_is_never_revoked(self, api, repos, tarefa):
        """Revoking a SPENT link would blur the audit trail of what the
        client actually saw and answered. `ajuste` returns the tarefa one
        stage (still before approval), so a second link can legally be
        minted afterwards."""
        primeiro = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()
        api.raw().post(f"/api/esteira/aprovar/{primeiro['token']}", json={"decisao": "ajuste"})
        segundo = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao")
        assert segundo.status_code == 201, segundo.text
        aprovacao_antiga = repos.aprovacao.buscar(ORG, primeiro["id"])
        assert not repos.aprovacao.expirada(aprovacao_antiga)


# ── PUBLIC portal ───────────────────────────────────────────────────
class TestPortalPublico:
    @pytest.fixture
    def token(self, api, tarefa) -> str:
        return api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()["token"]

    def test_view_needs_no_auth(self, api, token):
        """The whole point: the agency's client has no noc account."""
        resp = api.raw().get(f"/api/esteira/aprovar/{token}")
        assert resp.status_code == 200

    def test_view_shows_the_content(self, api, token):
        body = api.raw().get(f"/api/esteira/aprovar/{token}").json()
        assert body["titulo"] == "Arte do post"
        assert body["copy_texto"] == "Pão quentinho todo dia às 6h."
        assert body["cliente_nome"] == "Padaria Sol"
        assert body["aguardando_aprovacao"] is True

    def test_view_leaks_no_agency_internals(self, api, token):
        """Narrow projection — no ids, no org, no refação counter."""
        body = api.raw().get(f"/api/esteira/aprovar/{token}").json()
        for proibido in ("org_id", "id", "tarefa_id", "refacoes", "responsavel_id", "pauta_id"):
            assert proibido not in body, f"public payload leaked {proibido}"

    def test_unknown_token_returns_404(self, api):
        assert api.raw().get("/api/esteira/aprovar/nao-existe").status_code == 404

    def test_malformed_token_returns_404(self, api):
        assert api.raw().get("/api/esteira/aprovar/sem-ponto-nenhum").status_code == 404

    def test_unknown_and_expired_are_indistinguishable(self, api, repos, tarefa):
        """Otherwise the endpoint is a token oracle."""
        vencido = repos.aprovacao.emitir(ORG, tarefa["id"], validade=timedelta(days=-1))
        desconhecido = api.raw().get("/api/esteira/aprovar/org.naoexiste")
        expirado = api.raw().get(f"/api/esteira/aprovar/{vencido['token']}")
        assert desconhecido.status_code == expirado.status_code == 404
        assert desconhecido.json() == expirado.json()

    def test_aprovar_advances_to_the_next_stage(self, api, igig_db, tarefa, token, etapas):
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert resp.status_code == 200
        atual = next(t for t in igig_db.table("tarefa")._data if t["id"] == tarefa["id"])
        assert atual["etapa_id"] == etapas["pronto_para_agendamento"]["id"]
        movimento = _historico(igig_db, tarefa["id"])[-1]
        assert movimento["responsavel_id"] is None, "the actor is the client, not a noc user"

    def test_ajuste_returns_one_stage_and_counts_a_refacao(
        self, api, igig_db, tarefa, token, etapas
    ):
        resp = api.raw().post(
            f"/api/esteira/aprovar/{token}",
            json={"decisao": "ajuste", "observacao": "trocar a cor do fundo"},
        )
        assert resp.status_code == 200
        atual = next(t for t in igig_db.table("tarefa")._data if t["id"] == tarefa["id"])
        assert atual["etapa_id"] == etapas["revisao_interna"]["id"]
        assert atual["refacoes"] == 1
        assert atual["observacao_cliente"] == "trocar a cor do fundo"
        assert _historico(igig_db, tarefa["id"])[-1]["motivo"] == "trocar a cor do fundo"

    def test_the_agency_is_notified(self, api, core_db, token):
        """Smoke finding 4: 'agência notificada' was never sent."""
        api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        enviadas = core_db.table("notifications").inserted_payloads
        assert [n["user_id"] for n in enviadas] == [TEST_USER_ID], "the link's emitter"
        assert enviadas[0]["org_id"] == ORG
        assert enviadas[0]["metadata"]["decisao"] == "aprovado"

    def test_the_notification_link_opens_the_tarefa_not_just_the_board(
        self, api, core_db, tarefa, token,
    ):
        """The client's decision notification used to link to a bare
        `/esteira` — the board, not the tarefa the client just decided on —
        the same gap `plat achado #10` already closed for the automation
        notifications (`AutomacaoContext.link`)."""
        api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        aviso = core_db.table("notifications").inserted_payloads[0]
        assert aviso["metadata"]["link"] == f"/esteira?tarefa={tarefa['id']}"

    def test_response_reports_whether_the_notify_actually_landed(self, api, token):
        """achado 8: the portal used to say 'sua agência já foi notificada'
        unconditionally. `notificado` is the honest signal the FE now reads."""
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert resp.json()["notificado"] is True

    def test_notificado_is_false_with_no_recipient_to_tell(self, api, igig_db, token):
        """`emitido_por` is the ONLY guaranteed recipient here — remove it
        and no responsável exists, so nobody can be notified."""
        igig_db.table("aprovacao")._data[
            next(i for i, a in enumerate(igig_db.table("aprovacao")._data) if a["token"] == token)
        ]["emitido_por"] = None
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert resp.json()["notificado"] is False

    def test_aprovar_clears_a_stale_ajuste_observation(self, api, igig_db, tarefa, etapas):
        """achado 9: an earlier round's 'Cliente pediu: …' used to keep
        showing even after a LATER approval."""
        link1 = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()
        api.raw().post(
            f"/api/esteira/aprovar/{link1['token']}",
            json={"decisao": "ajuste", "observacao": "trocar a cor"},
        )
        link2 = api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()
        api.raw().post(f"/api/esteira/aprovar/{link2['token']}", json={"decisao": "aprovado"})
        atual = next(t for t in igig_db.table("tarefa")._data if t["id"] == tarefa["id"])
        assert atual["observacao_cliente"] is None


    def test_a_decision_needs_the_tarefa_still_in_approval(
        self, api, igig_db, tarefa, token, etapas
    ):
        """The agency pulled it back — the client's stale link must not move it."""
        _colocar_em(igig_db, tarefa["id"], etapas["revisao_interna"]["id"])
        assert api.raw().get(f"/api/esteira/aprovar/{token}").json()["aguardando_aprovacao"] is False
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "fora_de_aprovacao"

    def test_a_link_can_only_be_decided_once(self, api, token):
        primeira = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert primeira.status_code == 200
        segunda = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "ajuste"})
        assert segunda.status_code == 404, "a spent link must not flip the decision"

    def test_invalid_decision_returns_422(self, api, token):
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "talvez"})
        assert resp.status_code == 422

    def test_unknown_field_returns_422(self, api, token):
        resp = api.raw().post(
            f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado", "extra": "x"}
        )
        assert resp.status_code == 422

    def test_a_token_cannot_reach_another_orgs_tarefa(self, api, tarefa):
        """The org half of the token is parsed, not trusted as a bypass."""
        forjado = f"outra-org.{'x' * 40}"
        assert api.raw().get(f"/api/esteira/aprovar/{forjado}").status_code == 404


class TestPortalBloqueioFinanceiro:
    """`IGIG_PORTAL_BLOQUEIO_DIAS` — off by default; when set, a cliente with
    a fatura overdue past that many days gets 423 `portal_bloqueado` on BOTH
    the view and the decision, instead of the normal portal.

    `bloqueado` overrides `get_settings` — the router's own DI seam
    (`decidir_aprovacao_publica` already took `Depends(get_settings)`) —
    never the bare `settings` singleton.
    """

    @pytest.fixture
    def token(self, api, tarefa) -> str:
        return api.post(f"/api/esteira/tarefas/{tarefa['id']}/link-aprovacao").json()["token"]

    @pytest.fixture
    def bloqueado(self, api):
        """`IGIG_PORTAL_BLOQUEIO_DIAS=5` for the duration of one test."""
        from app.config import get_settings, settings
        from app.main import app

        app.dependency_overrides[get_settings] = lambda: settings.model_copy(
            update={"igig_portal_bloqueio_dias": 5}
        )
        yield
        app.dependency_overrides.pop(get_settings, None)

    @staticmethod
    def _fatura_vencida(igig_db, cliente_id: str, *, dias_atraso: int) -> dict:
        vencimento = (hoje_local() - timedelta(days=dias_atraso)).isoformat()
        return igig_db.table("fatura").insert({
            "org_id": ORG, "cliente_id": cliente_id, "competencia": "2026-01",
            "valor_total": 500, "status": "aberta", "vencimento": vencimento,
        }).execute().data[0]

    def test_off_by_default_even_with_an_old_overdue_fatura(self, api, igig_db, pauta, token):
        self._fatura_vencida(igig_db, pauta["cliente_id"], dias_atraso=999)
        assert api.raw().get(f"/api/esteira/aprovar/{token}").status_code == 200

    def test_view_is_423_past_the_configured_days(self, api, igig_db, pauta, token, bloqueado):
        self._fatura_vencida(igig_db, pauta["cliente_id"], dias_atraso=10)
        resp = api.raw().get(f"/api/esteira/aprovar/{token}")
        assert resp.status_code == 423
        assert resp.json()["code"] == "portal_bloqueado"

    def test_not_yet_blocked_below_the_threshold(self, api, igig_db, pauta, token, bloqueado):
        self._fatura_vencida(igig_db, pauta["cliente_id"], dias_atraso=3)
        assert api.raw().get(f"/api/esteira/aprovar/{token}").status_code == 200

    def test_decision_is_also_423_and_never_applied(self, api, igig_db, repos, pauta, token, bloqueado):
        self._fatura_vencida(igig_db, pauta["cliente_id"], dias_atraso=10)
        resp = api.raw().post(f"/api/esteira/aprovar/{token}", json={"decisao": "aprovado"})
        assert resp.status_code == 423
        assert resp.json()["code"] == "portal_bloqueado"
        aprovacao = repos.aprovacao.por_token(token)
        assert not repos.aprovacao.decidida(aprovacao), "a blocked decision must not be recorded"

    def test_a_paid_fatura_never_blocks(self, api, igig_db, pauta, token, bloqueado):
        fatura = self._fatura_vencida(igig_db, pauta["cliente_id"], dias_atraso=10)
        igig_db.table("fatura").update({"status": "paga"}).eq("id", fatura["id"]).execute()
        assert api.raw().get(f"/api/esteira/aprovar/{token}").status_code == 200


class TestPublicPortalWiring:
    """Structural guarantees the request-level tests cannot give.

    Dependency overrides replace a dependency's whole subtree — including an
    auth dep nested inside it — so a request test passes even when a public
    route is wired to an AUTHENTICATED provider. These inspect the wiring.
    """

    @staticmethod
    def _flat(path: str, method: str):
        from app.main import app

        for route in app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", ()):
                seen = set()
                stack = list(route.dependant.dependencies)
                while stack:
                    d = stack.pop()
                    if d.call:
                        seen.add(d.call)
                    stack.extend(d.dependencies)
                return seen
        raise AssertionError(f"route not found: {method} {path}")

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_public_routes_never_require_auth(self, method):
        from app.dependencies import get_current_user_org

        assert get_current_user_org not in self._flat("/api/esteira/aprovar/{token}", method)

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_public_routes_use_the_service_role_providers(self, method):
        from app.pipelines import get_db
        from app.store import get_repositorios, get_repositorios_admin

        deps = self._flat("/api/esteira/aprovar/{token}", method)
        assert get_repositorios_admin in deps
        assert get_repositorios not in deps and get_db not in deps

    def test_the_decision_moves_through_the_service_role_client(self):
        from app.pipelines import get_admin_db

        assert get_admin_db in self._flat("/api/esteira/aprovar/{token}", "POST")

    @pytest.mark.parametrize(
        ("path", "method"),
        [
            ("/api/esteira/board", "GET"),
            ("/api/esteira/tarefas/{tarefa_id}/mover-etapa", "POST"),
            ("/api/esteira/tarefas/{tarefa_id}/link-aprovacao", "POST"),
        ],
    )
    def test_authed_routes_use_the_rls_scoped_client(self, path, method):
        from app.dependencies import get_current_user_org
        from app.pipelines import get_admin_db, get_db

        deps = self._flat(path, method)
        assert get_db in deps and get_current_user_org in deps
        assert get_admin_db not in deps

    def test_the_legacy_hardcoded_board_is_gone(self):
        """`/quadro` + `/mover` validated against a fixed 8-tuple; stages are rows now."""
        from app.main import app

        caminhos = {getattr(r, "path", None) for r in app.routes}
        assert "/api/esteira/quadro" not in caminhos
        assert "/api/esteira/tarefas/{tarefa_id}/mover" not in caminhos
