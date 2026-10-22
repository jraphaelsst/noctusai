"""The ITEMS of an AI generation run: how each area reads and writes the agent's draft (S3a).

Every area is a *merge* into the draft's own table, written through the SAME store functions the draft routers use
(``replace_sections`` / ``replace_textos`` / ``replace_ferramentas`` / ``replace_decisoes`` / ``replace_spec_defs`` /
``fixar_ref`` / ``update_draft``): the rows of the area that a PREVIOUS generation wrote (``anteriores``) are replaced by
the new output, every other row (typed by the author) is kept. Drafts only -- nothing here publishes.

``hashes_atuais`` is the single definition of an item's identity: the hash stored when the item is written and the hash
recomputed at READ time are the same function, so "gerado" (unchanged) vs "editado" (the author changed it) is exact.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from app.schemas.studio_geracao import (
    SaidaConfiguracoes,
    SaidaDecisoes,
    SaidaFerramentas,
    SaidaSecoes,
    SaidaSkills,
    SaidaSpecs,
    SaidaTextos,
)
from app.stores.errors import NotFound
from app.stores.skills_biblioteca import validar_obrigatoria_para
from app.stores.studio_definitions import SectionInput
from app.stores.studio_definitions_conteudo import DecisaoInput, FerramentaInput, SpecDefInput, TextoInput
from app.studio.ferramentas_registry import ferramenta_conhecida
from app.studio.textos_registry import TEXTOS, placeholders_de

logger = logging.getLogger(__name__)

__all__ = [
    "CAMPOS_CONFIGURACAO",
    "ErroEscrita",
    "hashes_atuais",
    "escrever_area",
    "estados_das_areas",
]

CAMPOS_CONFIGURACAO = ("provider", "model", "effort", "max_turns", "idioma", "tool_policy", "notas")


class ErroEscrita(Exception):
    """A write the store/library refused (fixed machine ``codigo`` only -- never row content)."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


def _h(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def hashes_atuais(area: str, *, store: Any, skills: Any, org_id: UUID, version: Any) -> dict[str, str]:
    """``{item key: hash}`` of the area's rows in ``version`` right now."""
    vid = version.id
    if area == "secoes":
        return {s.chave: _h(s.titulo, s.conteudo, s.ativo) for s in store.list_sections(org_id, vid)}
    if area == "textos":
        return {t.chave: _h(t.conteudo) for t in store.list_textos(org_id, vid)}
    if area == "ferramentas":
        return {
            f.ferramenta: _h(f.descricao, f.ativo, dict(f.parametros), f.obrigatoria_skill)
            for f in store.list_ferramentas(org_id, vid)
        }
    if area == "decisoes":
        return {d.chave: _h(d.titulo, d.regra, list(d.opcoes)) for d in store.list_decisoes(org_id, vid)}
    if area == "specs":
        return {
            s.chave: _h(s.rotulo, s.descricao, s.tipo, s.obrigatoria, s.exemplo)
            for s in store.list_spec_defs(org_id, vid)
        }
    if area == "skills":
        return {
            r.skill_chave: _h(str(r.skill_versao_id), sorted(r.obrigatoria_para), r.ordem)
            for r in skills.listar_refs(vid)
        }
    if area == "configuracoes":
        return {c: _h(getattr(version, c, None)) for c in CAMPOS_CONFIGURACAO}
    raise ValueError(f"unknown area {area!r}")


def estados_das_areas(
    area: str, itens: list[dict[str, str]], atuais: dict[str, str],
) -> list[dict[str, str]]:
    """The items of a stored area with their READ-TIME estado: ``gerado`` while the row's hash is still the one stored
    at generation, ``editado`` when it changed; a deleted row is omitted."""
    out: list[dict[str, str]] = []
    for it in itens:
        cur = atuais.get(it["chave"])
        if cur is None:
            continue
        out.append({"chave": it["chave"], "estado": "gerado" if cur == it["hash"] else "editado"})
    return out


# ── writes (one function per area; each returns (keys written, lacunas)) ────────────────────────────────────


def _guard(call):
    """Run a store write; map the store's typed refusals onto ONE fixed machine code."""
    try:
        return call()
    except (ValueError, KeyError) as exc:
        logger.warning("agents.geracao.escrita_recusada tipo=%s", type(exc).__name__)
        raise ErroEscrita("escrita_recusada") from exc
    except Exception as exc:  # noqa: BLE001 -- StudioConflict / VersionImmutable: mapped, logged, never leaked
        if type(exc).__name__ in ("StudioConflict", "VersionImmutable", "Conflict"):
            logger.warning("agents.geracao.escrita_recusada tipo=%s", type(exc).__name__)
            raise ErroEscrita("escrita_recusada") from exc
        raise


def escrever_area(
    area: str, saida: Any, *, store: Any, skills: Any, org_id: UUID, draft: Any, anteriores: set[str],
    textos_aplicaveis: dict[str, bool],
) -> tuple[list[str], list[str]]:
    """Merge the validated ``saida`` of ``area`` into ``draft``. ``anteriores`` = keys a previous generation wrote
    for this area (replaced by the new output); ``textos_aplicaveis`` = ``{chave: obrigatoria}`` of the registry slots
    that apply to the agent. Returns ``(chaves escritas, lacunas)``."""
    lacunas = list(saida.lacunas)
    escritas: list[str]
    if area == "secoes":
        assert isinstance(saida, SaidaSecoes)
        novas = {s.chave: s for s in saida.secoes}
        atuais = store.list_sections(org_id, draft.id)
        manter = [s for s in atuais if s.chave not in anteriores and s.chave not in novas]
        topo = max((s.ordem for s in manter), default=0)
        itens = [
            SectionInput(id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, conteudo=s.conteudo, ativo=s.ativo)
            for s in manter
        ]
        for i, s in enumerate(saida.secoes, 1):
            itens.append(SectionInput(
                chave=s.chave, titulo=s.titulo, ordem=s.ordem if s.ordem is not None else topo + 10 * i,
                conteudo=s.conteudo, ativo=s.ativo,
            ))
        _guard(lambda: store.replace_sections(org_id, draft.id, itens))
        escritas = list(novas)
    elif area == "textos":
        assert isinstance(saida, SaidaTextos)
        validos: dict[str, str] = {}
        for t in saida.textos:
            spec = TEXTOS.get(t.chave)
            if spec is None or t.chave not in textos_aplicaveis:
                lacunas.append(f"chave_desconhecida:{t.chave}")
            elif not placeholders_de(t.conteudo) <= set(spec.placeholders_permitidos):
                lacunas.append(f"placeholder_invalido:{t.chave}")
            elif not t.conteudo.strip():
                lacunas.append(f"texto_vazio:{t.chave}")
            else:
                validos[t.chave] = t.conteudo
        atuais = store.list_textos(org_id, draft.id)
        itens = [TextoInput(t.chave, t.conteudo) for t in atuais if t.chave not in anteriores and t.chave not in validos]
        itens += [TextoInput(k, v) for k, v in validos.items()]
        _guard(lambda: store.replace_textos(org_id, draft.id, itens, expected_hash=None))
        preenchidos = {i.chave for i in itens if i.conteudo.strip()}
        lacunas += [f"texto_obrigatorio_ausente:{k}" for k, obrig in sorted(textos_aplicaveis.items()) if obrig and k not in preenchidos]
        escritas = list(validos)
    elif area == "ferramentas":
        assert isinstance(saida, SaidaFerramentas)
        validas = {}
        for f in saida.ferramentas:
            if ferramenta_conhecida(f.ferramenta):
                validas[f.ferramenta] = f
            else:
                lacunas.append(f"ferramenta_desconhecida:{f.ferramenta}")
        atuais = store.list_ferramentas(org_id, draft.id)
        itens = [
            FerramentaInput(
                ferramenta=f.ferramenta, descricao=f.descricao, ativo=f.ativo, parametros=dict(f.parametros),
                obrigatoria_skill=f.obrigatoria_skill,
            )
            for f in atuais if f.ferramenta not in anteriores and f.ferramenta not in validas
        ]
        itens += [
            FerramentaInput(
                ferramenta=f.ferramenta, descricao=f.descricao, ativo=f.ativo, parametros=dict(f.parametros),
                obrigatoria_skill=f.obrigatoria_skill,
            )
            for f in validas.values()
        ]
        _guard(lambda: store.replace_ferramentas(org_id, draft.id, itens, expected_hash=None))
        escritas = list(validas)
    elif area == "decisoes":
        assert isinstance(saida, SaidaDecisoes)
        novas = {d.chave: d for d in saida.decisoes}
        atuais = store.list_decisoes(org_id, draft.id)
        itens = [
            DecisaoInput(chave=d.chave, titulo=d.titulo, regra=d.regra, opcoes=[dict(o) for o in d.opcoes])
            for d in atuais if d.chave not in anteriores and d.chave not in novas
        ]
        itens += [
            DecisaoInput(
                chave=d.chave, titulo=d.titulo, regra=d.regra,
                opcoes=[{"valor": o.valor, "rotulo": o.rotulo, "padrao": o.padrao} for o in d.opcoes],
            )
            for d in novas.values()
        ]
        _guard(lambda: store.replace_decisoes(org_id, draft.id, itens, expected_hash=None))
        escritas = list(novas)
    elif area == "specs":
        assert isinstance(saida, SaidaSpecs)
        novas = {s.chave: s for s in saida.specs}
        atuais = store.list_spec_defs(org_id, draft.id)
        itens = [
            SpecDefInput(
                chave=s.chave, rotulo=s.rotulo, descricao=s.descricao, tipo=s.tipo, obrigatoria=s.obrigatoria,
                exemplo=s.exemplo,
            )
            for s in atuais if s.chave not in anteriores and s.chave not in novas
        ]
        itens += [
            SpecDefInput(
                chave=s.chave, rotulo=s.rotulo, descricao=s.descricao, tipo=s.tipo, obrigatoria=s.obrigatoria,
                exemplo=s.exemplo,
            )
            for s in novas.values()
        ]
        _guard(lambda: store.replace_spec_defs(org_id, draft.id, itens, expected_hash=None))
        escritas = list(novas)
    elif area == "skills":
        assert isinstance(saida, SaidaSkills)
        escritas = _escrever_skills(saida, skills=skills, org_id=org_id, draft=draft, anteriores=anteriores, lacunas=lacunas)
    elif area == "configuracoes":
        assert isinstance(saida, SaidaConfiguracoes)
        campos = {c: getattr(saida, c) for c in CAMPOS_CONFIGURACAO if getattr(saida, c) is not None}
        if not campos:
            raise ErroEscrita("saida_vazia")
        _guard(lambda: store.update_draft(org_id, draft.id, campos))
        escritas = list(campos)
    else:  # pragma: no cover -- Area is a closed Literal
        raise ValueError(f"unknown area {area!r}")
    return escritas, lacunas


def _escrever_skills(saida: SaidaSkills, *, skills: Any, org_id: UUID, draft: Any, anteriores: set[str], lacunas: list[str]) -> list[str]:
    """Pin library skills (the existing pin write; never touches the shared library)."""
    escolhidas = {}
    for s in saida.skills:
        escolhidas.setdefault(s.chave, s)
    for chave in sorted(anteriores - set(escolhidas)):
        try:
            skills.remover_ref(draft.id, chave)
        except NotFound:
            pass
    escritas: list[str] = []
    for chave, s in escolhidas.items():
        try:
            lib = skills.obter_skill(chave)
        except NotFound:
            lacunas.append(f"skill_inexistente:{chave}")
            continue
        publicada = next((v for v in skills.listar_versoes(lib.id) if v.status == "publicada"), None)
        if publicada is None:
            lacunas.append(f"skill_sem_versao_publicada:{chave}")
            continue
        try:
            para = validar_obrigatoria_para(list(s.obrigatoria_para))
        except ValueError:
            lacunas.append(f"obrigatoria_para_invalida:{chave}")
            continue
        _guard(lambda: skills.fixar_ref(org_id, draft.id, publicada.id, list(para), 0))
        escritas.append(chave)
    return escritas
