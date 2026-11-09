"""The git mirror of a DB-source dev agent, rendered at publish (Agent Packages CONTRACT A11, §M2/§M3/§M7).

The publish route calls :func:`renderizar_espelho` AFTER every gate passed and BEFORE the flip: the 017 tree guard
only lets a DRAFT's tree be written, and storing the tree in the same request means a published DB-source version
always has its mirror (a render failure refuses the publish, ``espelho_falhou``; never an agent without its mirror).
``GET /api/agent-packages/{key}/{versao}`` then serves the stored tree unchanged, and ``noctus.dev.agent_export``
writes it into the repo.

What the tree holds (v1, §M7): ``.claude/agents/<key>.md`` (:func:`app.studio.claude_surface.db_mirror_markdown`),
``agents/<key>/PACKAGE.json``, and every ACTIVE version skill plus every PINNED library skill at its pinned version
as ``agents/<key>/skills/<nome>/SKILL.md`` + ``references/``. Knowledge collections are not mirrored: they are listed
in ``PACKAGE.json.nao_espelhado`` (never a silent gap).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.stores.studio_definitions import DEV_KINDS
from app.studio.bundles import skill_refs_of
from app.studio.claude_surface import body_hash, db_mirror_markdown, mirror_body

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")


class EspelhoErro(Exception):
    """The mirror cannot be rendered; the publish is refused with ``espelho_falhou``."""


@dataclass(frozen=True)
class Espelho:
    files: list[dict[str, str]]
    versao_semver: str
    compiled_hash: str


def versao_semver_de(versao: int) -> str:
    """§M7: each publish of a DB-source agent is a major — ``<versao>.0.0``."""
    return f"{int(versao)}.0.0"


def _seg(value: str, what: str) -> str:
    if not _SAFE_SEGMENT.match(value or "") or ".." in value:
        raise EspelhoErro(f"{what} {value!r} não serve como caminho no espelho")
    return value


def _ref_path(caminho: str) -> str:
    parts = [p for p in (caminho or "").replace("\\", "/").split("/") if p]
    if not parts:
        raise EspelhoErro(f"arquivo de skill sem caminho: {caminho!r}")
    return "/".join(_seg(p, "segmento") for p in parts)


def _skill_md(nome: str, descricao: str | None, corpo: str) -> str:
    return (
        "---\n"
        f"name: {nome}\n"
        f"description: {json.dumps(descricao or '', ensure_ascii=False)}\n"
        "---\n"
        + corpo.rstrip("\n") + "\n"
    )


def renderizar_espelho(
    *, store: Any, skills: Any, catalog: Any, org_id: Any, agent: Any, draft: Any, compiled_text: str,
) -> Espelho:
    """The mirror tree of ``draft`` (about to be published). Raises :class:`EspelhoErro` on anything that would
    make the mirror wrong (no surface, an unsafe path, a pinned skill that cannot be opened)."""
    if agent.kind not in DEV_KINDS or agent.fonte != "db":
        raise EspelhoErro("só um agente de desenvolvimento com fonte='db' tem espelho")
    sup = agent.superficie_claude or {}
    tools = list(sup.get("tools") or [])
    if not tools:
        raise EspelhoErro("superficie_claude.tools está vazio: defina a superfície Claude Code antes de publicar")
    key = _seg(agent.key, "chave")
    semver = versao_semver_de(draft.versao)
    md = db_mirror_markdown(
        key=key, descricao=agent.descricao or agent.nome, idioma=draft.idioma, compiled_text=compiled_text,
        tools=tools, model=sup.get("model"), owns_kb=sup.get("owns_kb") or [], versao=semver,
        version_id=str(draft.id),
    )
    files: dict[str, str] = {f".claude/agents/{key}.md": md}
    base = f"agents/{key}/skills"

    files_by_skill: dict[Any, list[Any]] = {}
    for f in store.list_version_skill_files(org_id, draft.id):
        files_by_skill.setdefault(f.skill_id, []).append(f)
    for s in sorted(store.list_skills(org_id, draft.id), key=lambda s: (s.ordem, s.nome)):
        if not s.ativo:
            continue
        nome = _seg(s.nome, "skill")
        files[f"{base}/{nome}/SKILL.md"] = _skill_md(nome, s.descricao, s.corpo)
        for f in files_by_skill.get(s.id, []):
            files[f"{base}/{nome}/references/{_ref_path(f.caminho)}"] = f.conteudo

    for ref in skill_refs_of(draft.id):
        nome = _seg(ref.skill_key, "skill")
        if f"{base}/{nome}/SKILL.md" in files:
            raise EspelhoErro(f"skill {nome!r} existe na versão e na biblioteca: o espelho teria dois corpos")
        aberta = skills.abrir(ref.skill_key, ref.skill_versao_id) if skills is not None else None
        if aberta is None:
            raise EspelhoErro(f"skill fixada {nome!r} não pôde ser aberta na versão fixada")
        files[f"{base}/{nome}/SKILL.md"] = _skill_md(nome, ref.descricao, aberta.corpo)
        for f in aberta.arquivos:
            files[f"{base}/{nome}/references/{_ref_path(f.caminho)}"] = f.conteudo

    nao_espelhado = sorted(
        {getattr(c, "tag", None) or getattr(c, "nome", "?") for c in catalog.collection_summaries(org_id, agent.id)}
    ) if catalog is not None else []
    h = body_hash(mirror_body(key, draft.idioma, compiled_text))
    files[f"agents/{key}/PACKAGE.json"] = json.dumps({
        "key": key, "versao": semver, "fonte": "db", "version_id": str(draft.id), "compiled_hash": h,
        "nao_espelhado": nao_espelhado,
    }, indent=2, ensure_ascii=False) + "\n"
    return Espelho(
        files=[{"caminho": k, "conteudo": v} for k, v in sorted(files.items())], versao_semver=semver, compiled_hash=h,
    )


__all__ = ["Espelho", "EspelhoErro", "renderizar_espelho", "versao_semver_de"]
