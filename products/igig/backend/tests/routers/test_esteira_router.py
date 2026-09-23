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
from datetime import timedelta

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
        from app.pipelines import exigir_admin_da_org

        app.dependency_overrides[exigir_admin_da_org] = lambda: None
        try:
            criada = api.post("/api/esteira/stages", json={"label": "Legendas"})
            assert criada.status_code == 200, criada.text
            assert criada.json()["data"]["slug"] == "legendas"
            recusada = api.delete(f"/api/esteira/stages/{etapas['aprovacao_cliente']['id']}")
            assert recusada.status_code == 400, "a system-role stage must not be deletable"
        finally:
            app.dependency_overrides.pop(exigir_admin_da_org, None)


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
