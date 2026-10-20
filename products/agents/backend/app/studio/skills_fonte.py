"""The turn's skill source over the shared, pinned skill library (Julia v2 D7/D8): an implementation of the
runtime's ``SkillFonte`` (``app.channels.tool_registry``) on top of :class:`SkillsRuntime`.

* ``abrir`` / ``ler_arquivo`` serve the PINNED library version of the agent version being run (never the
  latest published one), then fall back to the version's own skills;
* ``obrigatoria_para`` merges the pins' gated tools (skill -> tools) with the version's own.

Pure glue: no skill text lives here. Results use the same payload shapes as ``app.studio.tools``.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence
from uuid import UUID

from app.studio.skills_contract import SkillRef, SkillsRuntime
from app.studio import tools as _tools


def _payload(rendered: dict[str, Any]) -> dict[str, Any]:
    return json.loads(rendered["content"][0]["text"])


class FonteDaBiblioteca:
    def __init__(self, runtime: SkillsRuntime, version_id: UUID, propria: Any | None = None) -> None:
        self._refs: dict[str, SkillRef] = {r.skill_key: r for r in runtime.skill_refs_for(version_id)}
        self._runtime = runtime
        self._propria = propria  # the version's own skills (SkillFonte) or None

    async def abrir(self, nome: str) -> dict[str, Any]:
        ref = self._refs.get(nome)
        if ref is None:
            return await self._propria.abrir(nome) if self._propria is not None else _payload(
                _tools._erro("skill_inexistente", disponiveis=sorted(self._refs)))
        aberta = self._runtime.abrir(ref.skill_key, ref.skill_versao_id)
        if aberta is None:
            return _payload(_tools._erro("skill_inexistente", disponiveis=sorted(self._refs)))
        return _payload(_tools._render(
            {
                "nome": aberta.skill_key, "descricao": ref.descricao, "corpo": aberta.corpo,
                "arquivos": [{"caminho": a.caminho, "titulo": a.titulo} for a in aberta.arquivos],
            },
            trim_field="corpo",
        ))

    async def ler_arquivo(self, nome: str, caminho: str) -> dict[str, Any]:
        ref = self._refs.get(nome)
        if ref is None:
            return await self._propria.ler_arquivo(nome, caminho) if self._propria is not None else _payload(
                _tools._erro("skill_inexistente", disponiveis=sorted(self._refs)))
        aberta = self._runtime.abrir(ref.skill_key, ref.skill_versao_id)
        arquivos = aberta.arquivos if aberta is not None else ()
        for a in arquivos:
            if a.caminho == caminho:
                return _payload(_tools._render(
                    {"caminho": a.caminho, "titulo": a.titulo, "conteudo": a.conteudo}, trim_field="conteudo"))
        return _payload(_tools._erro("arquivo_inexistente", disponiveis=[a.caminho for a in arquivos]))

    def obrigatoria_para(self) -> Mapping[str, Sequence[str]]:
        out: dict[str, list[str]] = {}
        if self._propria is not None:
            for skill, tools in self._propria.obrigatoria_para().items():
                out[skill] = list(tools)
        for key, ref in self._refs.items():
            for t in ref.obrigatoria_para:
                if t not in out.setdefault(key, []):
                    out[key].append(t)
        return out


def skills_factory(runtime_provider):
    """``(definitions, definition_org, definition_agent, version_id) -> SkillFonte`` for the channel turn."""
    from app.channels.tool_registry import SkillsDaVersao

    def factory(definitions: Any, org_id: UUID, agent_id: UUID, version_id: UUID):
        propria = SkillsDaVersao(definitions, org_id, agent_id, version_id)
        runtime = runtime_provider()
        if not runtime.skill_refs_for(version_id):
            return propria
        return FonteDaBiblioteca(runtime, version_id, propria)

    return factory
