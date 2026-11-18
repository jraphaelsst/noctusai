"""The ``onboarding`` tool group: registry, strict schemas, rows-as-words, server-side binding, runtime wiring."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.onboarding.ferramentas import ONBOARDING_SERVER_NAME, TOOL_NAMES, onboarding_tool_specs
from app.runtime.claude_runtime import grupo_onboarding_nomes_sdk, pares_do_grupo
from app.runtime.types import AgentSpec
from app.studio.ferramentas_registry import (
    FERRAMENTAS_CONHECIDAS, GRUPOS_FERRAMENTAS, grupo_de, nome_no_modelo,
)

from .test_entrevista import Kit

DESC = {n: f"descrição de {n}" for n in TOOL_NAMES}


def _chama(specs, nome, args):
    spec = next(s for s in specs if s.name == nome)
    out = asyncio.run(spec.handler(args))
    return json.loads(out["content"][0]["text"])


def test_group_is_registered_under_the_content_pattern_and_model_names():
    g = GRUPOS_FERRAMENTAS["onboarding"]
    assert g.ferramentas == {f"onboarding_{n}" for n in TOOL_NAMES}
    assert g.escrita == () and set(g.leitura) == set(TOOL_NAMES)
    assert all(f in FERRAMENTAS_CONHECIDAS for f in g.ferramentas)
    assert grupo_de("onboarding_registrar_resposta") is g
    assert nome_no_modelo("onboarding_registrar_resposta") == "mcp__onboarding__registrar_resposta"
    assert ONBOARDING_SERVER_NAME == "onboarding"


def test_schemas_are_strict_and_never_carry_an_org_or_session_id():
    specs = onboarding_tool_specs(lambda: None, DESC)
    assert [s.name for s in specs] == list(TOOL_NAMES)
    for s in specs:
        assert s.input_schema["additionalProperties"] is False
        assert not {"org_id", "sessao_id", "conversation_id", "agent_key", "alvo"} & set(s.input_schema["properties"])
        assert s.description == DESC[s.name]  # words are rows


def test_a_tool_without_a_row_description_is_not_registered():
    specs = onboarding_tool_specs(lambda: None, {"progresso_onboarding": "x", "registrar_resposta": "  "})
    assert [s.name for s in specs] == ["progresso_onboarding"]


def test_a_conversation_without_a_session_gets_sem_sessao_never_another_orgs_data():
    specs = onboarding_tool_specs(lambda: None, DESC)
    for nome, args in (("progresso_onboarding", {}), ("revisar_e_aplicar", {"fase": "resumo"})):
        r = _chama(specs, nome, args)
        assert r["ok"] is False and r["erro"] == "sem_sessao"


def test_handlers_run_the_interview_and_record_events():
    kit = Kit()
    specs = onboarding_tool_specs(lambda: kit.e, DESC)
    assert _chama(specs, "progresso_onboarding", {})["proximo"]["n"] == 9
    kit.diz("Somos a Acme")
    r = _chama(specs, "registrar_resposta", {"item": 1, "situacao": "respondido", "valor": "Acme", "trecho": "Somos a Acme"})
    assert r["ok"] and kit.tipos() == ["resposta_registrada"]
    assert _chama(specs, "registrar_resposta", {"item": 2, "situacao": "pendente", "motivo": "depois"})["estado"] == "pendente"


def test_an_unexpected_failure_never_leaks_its_text_to_the_model():
    class Quebrada:
        def progresso(self):
            raise RuntimeError("segredo interno")

    specs = onboarding_tool_specs(lambda: Quebrada(), DESC)
    r = _chama(specs, "progresso_onboarding", {})
    assert r == {"erro": "falha_interna"}


def _spec(ferramentas):
    return AgentSpec(
        key="onboarding-imob", model="m", effort="low", prompt_append="p", skills=(), tools=(), max_turns=5,
        prompt_mode="custom", toolset="studio", agent_id=uuid4(), version_id=uuid4(), ferramentas_grupo=tuple(ferramentas))


def test_spec_pairs_split_by_group_so_an_onboarding_turn_needs_no_academia_config():
    s = _spec([("onboarding_registrar_resposta", "d"), ("academia_kb_buscar", "d2")])
    assert pares_do_grupo(s, "onboarding") == (("onboarding_registrar_resposta", "d"),)
    assert pares_do_grupo(s, "academia") == (("academia_kb_buscar", "d2"),)
    assert grupo_onboarding_nomes_sdk(s) == ("mcp__onboarding__registrar_resposta",)
    assert pares_do_grupo(_spec([("onboarding_revisar_e_aplicar", "d")]), "academia") == ()


def test_launch_options_add_the_onboarding_server_and_allow_only_its_tools():
    from app.runtime.academia_api import FakeAcademiaApi
    from app.runtime.claude_runtime import build_launch_options
    from app.runtime.slots import FakeSlotPool
    from app.runtime.types import TurnContext
    from app.stores.approvals import FakeApprovalStore

    s = _spec([(f"onboarding_{n}", "d") for n in TOOL_NAMES])
    opts = build_launch_options(
        spec=s, ctx=TurnContext(org_id=uuid4(), conversation_id=uuid4(), requested_by=uuid4(), instance_id="i", sdk_session_id=None),
        academia_api=FakeAcademiaApi(), agent_id=uuid4(), approval_secret="s", can_use_tool=None, approvals=FakeApprovalStore(),
        slot=FakeSlotPool(1).try_reserve(), mirror=None, resume=None, plugin_path="/p",
        studio_tools={"type": "sdk", "name": "studio", "instance": object()}, anthropic_api_key="k",
        onboarding_grupo={"type": "sdk", "name": "onboarding", "instance": object()},
    )
    assert "onboarding" in opts.mcp_servers and "academia" not in opts.mcp_servers
    assert {f"mcp__onboarding__{n}" for n in TOOL_NAMES} <= set(opts.allowed_tools)
