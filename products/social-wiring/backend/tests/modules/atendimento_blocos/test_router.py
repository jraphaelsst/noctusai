"""`GET` / `PUT /api/atendimento-blocos` (maya-blocks CONTRACT §4.1 / §4.2): strict `== 401`, member reads,
owner/admin writes, the error table, whole-config validation before any write, the two-phase save.
Seams: mock DB through the router's `get_blocos_client`, the real auth chain over a mocked session."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.modules.atendimento_blocos import repository as repo
from app.modules.atendimento_blocos import service as svc

from tests.support.lais_world import ADMIN_ID, MEMBER_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World
from .conftest import _stages, supervisao_on

H = {"Authorization": "Bearer test-token"}
BASE = "/api/atendimento-blocos"


class Scene:
    def __init__(self, tc: TestClient, world: World):
        self.tc, self.w = tc, world

    def get(self, headers=H):
        return self.tc.get(BASE, headers=headers)

    def put(self, blocos: Any, headers=H):
        return self.tc.put(BASE, headers=headers, json={"blocos": blocos} if not isinstance(blocos, dict) else blocos)

    def rows(self) -> list[dict]:
        return self.w.sw.table("atendimento_blocos").select("*").execute().data or []


def _scene(role: str):
    world = World()
    world.sw.set_table_data("pipeline_stages", _stages(ORG_ID) + _stages(OTHER_ORG_ID) + [
        {"id": "pos", "org_id": ORG_ID, "pipeline": "funil", "slug": "pos_venda", "label": "Pós-venda",
         "cor": "secondary", "posicao": 9, "ativo": True, "papel": None},
        {"id": "velha", "org_id": ORG_ID, "pipeline": "funil", "slug": "arquivada", "label": "Velha",
         "cor": "secondary", "posicao": 10, "ativo": False, "papel": None},
        {"id": "est", "org_id": ORG_ID, "pipeline": "esteira", "slug": "roteiro", "label": "Roteiro",
         "cor": "secondary", "posicao": 0, "ativo": True, "papel": None},
    ])
    for t in ("atendimento_blocos", "supervisao_config"):
        world.sw.set_table_data(t, [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"}, {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.modules.atendimento_blocos.router import get_blocos_client

        bind_consent_module_to_mock(world.root)
        app.dependency_overrides[get_blocos_client] = lambda: world.sw
        yield Scene(TestClient(app), world)
        app.dependency_overrides.pop(get_blocos_client, None)


@pytest.fixture
def owner():
    yield from _scene("owner")


@pytest.fixture
def admin():
    yield from _scene("admin")


@pytest.fixture
def member():
    yield from _scene("member")


def _item(bloco: str, etapas: list[str], *, ativo: bool = True, agent_key: str | None = None) -> dict:
    return {"bloco": bloco, "agent_key": agent_key, "ativo": ativo, "etapas": etapas}


class TestAuth:
    @pytest.mark.parametrize("method", ["get", "put"])
    def test_no_session_is_exactly_401(self, owner, method):
        r = owner.get(headers={}) if method == "get" else owner.put([_item("atendimento", [])], headers={})
        assert r.status_code == 401

    def test_member_reads_but_cannot_write(self, member):
        assert member.get().status_code == 200
        assert member.put([_item("atendimento", ["qualificacao"])]).status_code == 403
        assert member.rows() == []

    def test_admin_writes(self, admin):
        assert admin.put([_item("atendimento", ["qualificacao", "visitas", "proposta_recebida"])]).status_code == 200


class TestGet:
    def test_empty_org_is_all_padrao_six_blocks_in_order(self, member):
        d = member.get().json()["data"]
        assert [b["bloco"] for b in d["blocos"]] == ["sdr", "atendimento", "negociacao", "juridico", "financeiro", "contador"]
        assert all(b["origem"] == "padrao" and b["ativo"] is False for b in d["blocos"])
        sdr = d["blocos"][0]
        assert sdr == {"bloco": "sdr", "rotulo": "SDR (Julia)", "ordem": 1, "agent_key": "lead-imob", "ativo": False,
                       "pipeline": None, "etapas": [], "origem": "padrao", "updated_at": None, "updated_by": None}
        assert d["blocos"][1]["etapas"] == ["qualificacao", "visitas", "proposta_recebida"]
        assert d["agentes_por_bloco"] == {"sdr": ["lead-imob"]}
        assert d["supervisao_ativa"] is False

    def test_etapas_sem_bloco_lists_only_active_unowned_atendimento_stages(self, member):
        d = member.get().json()["data"]
        assert d["etapas_sem_bloco"] == [{"pipeline": "funil", "slug": "pos_venda", "label": "Pós-venda"}]

    def test_supervisao_switch_is_reported(self, member):
        supervisao_on(member.w)
        assert member.get().json()["data"]["supervisao_ativa"] is True

    def test_another_orgs_rows_are_invisible(self, member):
        member.w.sw.table("atendimento_blocos").insert({
            "org_id": OTHER_ORG_ID, "bloco": "atendimento", "agent_key": None, "ativo": True, "pipeline": "funil",
            "etapas": ["qualificacao"]}).execute()
        assert all(b["origem"] == "padrao" for b in member.get().json()["data"]["blocos"])


class TestPut:
    def test_partial_save_roundtrip(self, owner):
        r = owner.put([_item("atendimento", ["qualificacao", "visitas", "proposta_recebida", "pos_venda"])])
        assert r.status_code == 200
        d = r.json()["data"]
        at = d["blocos"][1]
        assert at["origem"] == "org" and at["ativo"] is True and at["pipeline"] == "funil"
        assert at["etapas"] == ["qualificacao", "visitas", "proposta_recebida", "pos_venda"]
        assert at["updated_by"] == TEST_USER_ID
        assert d["etapas_sem_bloco"] == []
        assert all(b["origem"] == "padrao" for b in d["blocos"] if b["bloco"] != "atendimento")
        (row,) = owner.rows()
        assert row["org_id"] == ORG_ID and row["pipeline"] == "funil"  # the pipeline comes from the closed list

    def test_sdr_can_be_switched_on_with_julia(self, owner):
        d = owner.put([_item("sdr", [], agent_key="lead-imob")]).json()["data"]
        assert d["blocos"][0]["ativo"] is True and d["blocos"][0]["agent_key"] == "lead-imob"

    @pytest.mark.parametrize("body,code", [
        ([_item("sdr", ["qualificacao"])], "sdr_sem_etapas"),
        ([_item("atendimento", ["qualificacao"], agent_key="lead-imob")], "agente_indisponivel"),
        ([_item("sdr", [], agent_key="julia")], "agente_indisponivel"),
        ([_item("atendimento", ["nao_existe"])], "etapa_desconhecida"),
        ([_item("atendimento", ["arquivada"])], "etapa_desconhecida"),  # inactive stage
        ([_item("atendimento", ["assinatura"])], "etapa_desconhecida"),  # a processos stage on a funil block
        ([_item("atendimento", ["qualificacao", "negociacao"])], "etapa_em_dois_blocos"),  # vs the negociacao default
    ])
    def test_contract_errors_are_422_and_write_nothing(self, owner, body, code):
        r = owner.put(body)
        assert r.status_code == 422 and r.json()["error"]["code"] == code
        assert owner.rows() == []

    def test_overlap_message_names_the_slug_and_the_blocks(self, owner):
        err = owner.put([_item("atendimento", ["qualificacao", "negociacao"])]).json()["error"]
        assert "negociacao" in err["message"] and "atendimento" in err["message"]

    @pytest.mark.parametrize("body", [
        {"blocos": [{**_item("atendimento", []), "pipeline": "funil"}]},          # unknown field
        {"blocos": [_item("posvenda", [])]},                                       # unknown bloco
        {"blocos": [_item("atendimento", []), _item("atendimento", [])]},         # duplicate bloco
        {"blocos": [_item("atendimento", ["visitas", "visitas"])]},               # duplicate stage
        {"blocos": []},
        {"blocos": [_item("atendimento", [])], "extra": 1},
    ])
    def test_shape_errors_are_validation_error(self, owner, body):
        r = owner.put(body)
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
        assert owner.rows() == []

    def test_a_stage_moves_between_blocks_in_one_save(self, owner):
        assert owner.put([_item("atendimento", ["qualificacao", "visitas", "proposta_recebida"]),
                          _item("negociacao", ["negociacao", "proposta_decisao"])]).status_code == 200
        r = owner.put([_item("atendimento", ["qualificacao", "visitas"]),
                       _item("negociacao", ["proposta_recebida", "negociacao", "proposta_decisao"])])
        assert r.status_code == 200
        d = {b["bloco"]: b["etapas"] for b in r.json()["data"]["blocos"]}
        assert d["atendimento"] == ["qualificacao", "visitas"] and "proposta_recebida" in d["negociacao"]


class _TriggerRefuses:
    """A DB double whose `atendimento_blocos` upsert refuses like the 286 trigger does under a concurrent save."""

    def __init__(self, inner: Any):
        self._inner = inner

    def table(self, name: str):
        builder = self._inner.table(name)
        if name != "atendimento_blocos":
            return builder

        class _B:
            def __getattr__(self, item):
                return getattr(builder, item)

            def upsert(self, *a, **k):
                raise RuntimeError('new row violates check constraint "atendimento_blocos_etapas_disjuntas"')

        return _B()


def test_a_trigger_refusal_is_409_conflito_concorrente():
    world = World()
    world.sw.set_table_data("pipeline_stages", _stages(ORG_ID))
    world.sw.set_table_data("atendimento_blocos", [])
    world.sw.set_table_data("supervisao_config", [])
    from noctusai_lib.primitives.exceptions import AppException

    with pytest.raises(AppException) as exc:
        svc.salvar(_TriggerRefuses(world.sw), ORG_ID, [_item("atendimento", ["qualificacao"])], updated_by=None)
    assert exc.value.status_code == 409 and exc.value.code == "conflito_concorrente"


def test_two_blocks_swapping_stages_shrink_first_then_write():
    """Phase 1 shrinks every saved row that loses a stage, so a swap never puts one slug on two rows."""
    world = World()
    world.sw.set_table_data("pipeline_stages", _stages(ORG_ID))
    world.sw.set_table_data("supervisao_config", [])
    world.sw.set_table_data("atendimento_blocos", [
        {"org_id": ORG_ID, "bloco": "juridico", "agent_key": None, "ativo": True, "pipeline": "processos_venda",
         "etapas": ["elaboracao_contrato", "analise_partes", "revisao_contrato", "assinatura"]},
        {"org_id": ORG_ID, "bloco": "financeiro", "agent_key": None, "ativo": True, "pipeline": "processos_venda",
         "etapas": ["financiamento_escritura", "finalizacao", "entrega_chaves"]},
    ])
    svc.salvar(world.sw, ORG_ID, [
        _item("juridico", ["elaboracao_contrato", "analise_partes", "revisao_contrato", "finalizacao"]),
        _item("financeiro", ["financiamento_escritura", "assinatura", "entrega_chaves"]),
    ], updated_by=None)
    shrinks = world.sw.table("atendimento_blocos").updated_payloads
    assert {tuple(p["etapas"]) for p in shrinks} == {
        ("elaboracao_contrato", "analise_partes", "revisao_contrato"), ("financiamento_escritura", "entrega_chaves"),
    }
    cfg = repo.configuracao_efetiva(world.sw, ORG_ID)
    assert "finalizacao" in cfg["juridico"].etapas and "assinatura" in cfg["financeiro"].etapas
