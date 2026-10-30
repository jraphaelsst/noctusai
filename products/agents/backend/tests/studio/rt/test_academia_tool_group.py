"""agents-unified Renata cutover S7: the academia toolset as a content-configurable TOOL GROUP of a Studio agent.

Pinned here: the group is read from the same registry the ``ferramentas`` area uses; the class of a tool (read vs
write) is the gate table's, never the row's; a write tool never joins ``allowed_tools`` (an SDK whole-tool grant
would bypass ``can_use_tool`` and with it the approval broker); the provider-neutral runtime (no approval flow) is
never handed a group; a lead-facing channel turn never offers one."""
from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

from app.channels.tool_registry import TOOLS
from app.runtime import gate
from app.runtime.claude_runtime import _TurnDriver, grupo_academia_nomes_sdk
from app.studio.compiler import nome_no_modelo as compiler_nome
from app.studio.ferramentas_registry import (
    FERRAMENTAS_CONHECIDAS,
    GRUPOS_FERRAMENTAS,
    grupo_de,
    nome_no_modelo,
)
from app.studio.spec import StudioSpecError, _ferramentas_grupo, exigir_executor_do_grupo
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from tests.studio.rt.test_launch_options import _build, _ctx, _studio_spec

GRUPO = GRUPOS_FERRAMENTAS["academia"]
_ROW_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
LEITURA = sorted(f for f in GRUPO.ferramentas if GRUPO.classe(f) == "leitura")
ESCRITA = sorted(f for f in GRUPO.ferramentas if GRUPO.classe(f) == "escrita")


class TestRegistry:
    def test_every_gate_tool_is_in_the_group_and_known_to_the_ferramentas_area(self):
        servidor = [n for n in (*gate.LEITURA, *gate.ESCRITA) if n.startswith("mcp__academia__")]
        assert len(GRUPO.ferramentas) == len(servidor)  # the built-ins (WebSearch / Skill) are not group tools
        assert GRUPO.ferramentas <= FERRAMENTAS_CONHECIDAS
        assert all(_ROW_NAME.match(f) for f in GRUPO.ferramentas)

    def test_the_class_is_the_gate_tables(self):
        assert LEITURA and ESCRITA
        for f in GRUPO.ferramentas:
            assert gate.classify(GRUPO.nome_sdk(f)) == GRUPO.classe(f)

    def test_the_model_sees_the_server_name(self):
        f = LEITURA[0]
        assert nome_no_modelo(f) == compiler_nome(f) == f"mcp__academia__{f.removeprefix('academia_')}"
        assert nome_no_modelo("kb_buscar") == "kb_buscar" and grupo_de("kb_buscar") is None

    def test_a_lead_facing_channel_turn_never_offers_the_group(self):
        assert not set(TOOLS) & GRUPO.ferramentas
        assert not any(t.startswith("mcp__academia__") for t in TOOLS)


class TestSpec:
    def _compiled(self, *rows):
        return SimpleNamespace(conteudo=SimpleNamespace(ferramentas=[
            SimpleNamespace(ferramenta=n, descricao=d, ativo=a) for n, d, a in rows
        ]))

    def test_only_active_described_group_rows_switch_tools_on(self):
        compiled = self._compiled(
            (LEITURA[0], "Lê.", True), (ESCRITA[0], "Escreve.", True), (LEITURA[1], "", True),
            (LEITURA[2], "Desligada.", False), ("kb_buscar", "Busca.", True),
        )
        assert _ferramentas_grupo(compiled) == tuple(sorted(((LEITURA[0], "Lê."), (ESCRITA[0], "Escreve."))))
        assert _ferramentas_grupo(SimpleNamespace(conteudo=None)) == ()

    def test_the_provider_neutral_runtime_is_never_handed_a_group(self):
        with pytest.raises(StudioSpecError) as exc:
            exigir_executor_do_grupo(((ESCRITA[0], "x"),), "llm")
        assert exc.value.code == "ferramentas_exigem_claude_sdk"
        exigir_executor_do_grupo(((ESCRITA[0], "x"),), "claude_sdk")
        exigir_executor_do_grupo((), "llm")


class TestLaunch:
    def _spec(self):
        return _studio_spec(ferramentas_grupo=((LEITURA[0], "Lê."), (ESCRITA[0], "Escreve.")))

    def test_the_academia_server_rides_next_to_studio_and_writes_never_join_allowed_tools(self):
        opts, _ = _build(self._spec(), academia_grupo={"type": "sdk", "name": "academia", "instance": object()})
        assert set(opts.mcp_servers) == {"studio", "academia"}
        assert GRUPO.nome_sdk(LEITURA[0]) in opts.allowed_tools
        assert GRUPO.nome_sdk(ESCRITA[0]) not in opts.allowed_tools
        assert not any(gate.classify(t) == "escrita" for t in opts.allowed_tools)

    def test_refuses_to_launch_a_group_without_its_server(self):
        with pytest.raises(RuntimeError):
            _build(self._spec())

    def test_names_enabled_are_only_the_versions_rows(self):
        assert grupo_academia_nomes_sdk(self._spec()) == (GRUPO.nome_sdk(LEITURA[0]), GRUPO.nome_sdk(ESCRITA[0]))
        assert grupo_academia_nomes_sdk(_studio_spec()) == ()


class _Broker:
    def __init__(self) -> None:
        self.pedidos: list[str] = []

    async def request(self, **kw):  # the approval broker: records the ask, answers "denied"
        self.pedidos.append(kw.get("tool_name", ""))
        return False


class TestDriverGate:
    def _driver(self, broker):
        leitura = GRUPO.nome_sdk(LEITURA[0])
        escrita = GRUPO.nome_sdk(ESCRITA[0])
        return _TurnDriver(
            ctx=_ctx(), broker=broker, academia_api=None,
            allowlist=frozenset({"mcp__studio__kb_buscar", leitura}), gated=frozenset({escrita}),
        ), leitura, escrita

    def test_an_unconfigured_group_tool_is_denied_outright(self):
        driver, _, _ = self._driver(_Broker())
        other = GRUPO.nome_sdk(ESCRITA[1])
        r = asyncio.run(driver.can_use_tool(other, {}, SimpleNamespace(tool_use_id=str(uuid4()))))
        assert isinstance(r, PermissionResultDeny)

    def test_a_configured_read_tool_is_allowed(self):
        driver, leitura, _ = self._driver(_Broker())
        r = asyncio.run(driver.can_use_tool(leitura, {}, SimpleNamespace(tool_use_id=str(uuid4()))))
        assert isinstance(r, PermissionResultAllow)
