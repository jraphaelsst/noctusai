"""Per-PART hashes of a compiled spec (eval consolidation, owner rule 2026-11-09).

``compiled_hash`` says "something changed"; consolidation needs "WHAT changed", so a case whose dependencies did not
move is not re-run. :func:`partes_da_compilacao` splits exactly what ``hash_payload`` covers into named parts:

    ``secao:<chave>``        one prompt section (title, order, text) -- active sections only
    ``texto:<chave>``        one required text row                 ``ferramenta:<nome>``  one tool row (text + params)
    ``decisao:<chave>``      one decision row                      ``spec:<chave>``       one org-spec declaration
    ``skill:<nome>``         one own skill (body + files)          ``skill_ref:<key>``    one pinned library skill
    ``qualificacao``         the pinned qualification standard     ``conhecimento``       the knowledge-collection index
    ``extras``               the other hash-covered inputs
    ``modelo`` / ``config`` / ``estrutura`` / ``texto_legado``  GLOBAL parts (see :data:`PARTES_GLOBAIS`)

Completeness invariant (tested): any input change that moves ``compiled_hash`` moves at least one part. Pure, no IO.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

__all__ = ["PARTES_GLOBAIS", "hash_parte", "partes_da_compilacao"]

#: Parts that affect EVERY case regardless of its declared dependencies: the model that answers, the run limits /
#: tool policy, and the section layout. A case cannot opt out of these.
PARTES_GLOBAIS: frozenset[str] = frozenset({"modelo", "config", "estrutura", "texto_legado"})


def hash_parte(valor: Any) -> str:
    raw = json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def partes_da_compilacao(
    *, texto: str, version: Any, secoes_ativas: Iterable[Any], skills_ativas: Iterable[Any],
    conteudo: Any, extras: dict[str, Any] | None, qualificacao: Any, knowledge: Sequence[Any],
) -> dict[str, str]:
    """``{part ref: short hash}`` of one compile (``version`` / ``conteudo`` are the post-org-resolution ones)."""
    p: dict[str, str] = {}
    secoes = list(secoes_ativas)
    for s in secoes:
        p[f"secao:{s.chave}"] = hash_parte([s.titulo, s.ordem, s.conteudo])
    p["estrutura"] = hash_parte([s.chave for s in secoes])
    p["modelo"] = hash_parte([version.provider, version.model, version.effort])
    p["config"] = hash_parte([version.max_turns, version.idioma, dict(version.tool_policy or {})])
    for sk in skills_ativas:
        p[f"skill:{sk.nome}"] = hash_parte(
            [sk.descricao, sk.corpo, sk.ordem, sorted([f.caminho, f.titulo, f.sha256] for f in sk.arquivos)])
    for r in version.skill_refs or ():
        p[f"skill_ref:{r.skill_key}"] = hash_parte([str(r.skill_versao_id), r.descricao, sorted(r.obrigatoria_para)])
    p["conhecimento"] = hash_parte(sorted(
        [c.slug, c.nome, c.tag, c.descricao, c.doc_count, c.ordem] for c in knowledge))
    if conteudo is None:
        # legacy agent: the hash IS the prompt text, so the text itself is the (global) part
        p["texto_legado"] = hash_parte(texto)
        return p
    for t in conteudo.textos:
        p[f"texto:{t.chave}"] = hash_parte(t.conteudo)
    for f in conteudo.ferramentas:
        p[f"ferramenta:{f.ferramenta}"] = hash_parte(
            [f.ativo, f.descricao, sorted(f.parametros.items()), f.obrigatoria_skill])
    for d in conteudo.decisoes:
        p[f"decisao:{d.chave}"] = hash_parte([d.titulo, d.regra, [[o.valor, o.rotulo, o.padrao] for o in d.opcoes]])
    for sp in conteudo.specs:
        p[f"spec:{sp.chave}"] = hash_parte([sp.rotulo, sp.descricao, sp.tipo, sp.obrigatoria, sp.exemplo])
    p["extras"] = hash_parte(extras or {})
    p["qualificacao"] = hash_parte(None if qualificacao is None else {
        "versao_id": str(qualificacao.versao_id) if qualificacao.versao_id else None,
        "criterios": sorted(
            [c.chave, c.rotulo, c.descricao_modelo, c.grupo, c.ordem, [list(o) for o in c.opcoes]]
            for c in qualificacao.criterios),
        "estagios": sorted([e.chave, e.rotulo, e.descricao, e.ordem] for e in qualificacao.estagios),
        "minimo": list(qualificacao.minimo_para_ofertar),
        "identidade": [list(i) for i in qualificacao.identidade],
    })
    return p
