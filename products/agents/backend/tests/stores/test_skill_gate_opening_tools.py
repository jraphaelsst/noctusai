"""The skill-opening tools can never be gated on a skill: gating them makes the skill unopenable."""
from __future__ import annotations

import pytest

from app.channels.tool_registry import obrigatorias_por_ferramenta
from app.stores.skills_biblioteca import FERRAMENTAS_DE_ABERTURA, validar_obrigatoria_para
from types import SimpleNamespace


@pytest.mark.parametrize("ferramenta", sorted(FERRAMENTAS_DE_ABERTURA))
def test_put_refuses_gating_an_opening_tool(ferramenta: str) -> None:
    with pytest.raises(ValueError):
        validar_obrigatoria_para(["registrar_perfil", ferramenta])


def test_ordinary_tools_still_accepted() -> None:
    assert validar_obrigatoria_para(["registrar_perfil", "handoff"]) == ("registrar_perfil", "handoff")


def test_runtime_ignores_a_legacy_gate_on_an_opening_tool() -> None:
    gates = obrigatorias_por_ferramenta(
        SimpleNamespace(ferramentas=[]),  # type: ignore[arg-type]
        {"qualificar-lead": ["abrir_skill", "ler_arquivo_skill", "registrar_perfil"]},
    )
    assert gates == {"registrar_perfil": ("qualificar-lead",)}
