"""The pure qualification engine (CONTRACT §3.2 / D10). No IO, no clock reads
except the explicit ``agora`` argument.

``calcular`` turns a standard version + the append-only records + the property
events into the lead's state. Stage and score are NEVER judged by the model.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Sequence

from app.qualificacao.models import (
    DERIVADOS,
    EVENTOS_IMOVEL,
    FONTES,
    GRUPOS,
    ORIGENS_IMOVEL,
    SENSIVEL,
    TIPOS,
    CriterioDef,
    EstadoQualificacao,
    EventoImovel,
    ProximoCriterio,
    Registro,
    VersaoPadrao,
)
from app.qualificacao.regras import (
    Contexto,
    avaliar_regra,
    criterios_referenciados,
    ponto_de_referencia,
    preenchido,
    sempre_verdadeira,
    validar_regra,
)

__all__ = [
    "EngineError",
    "calcular",
    "validar_valor",
    "validar_versao",
    "eventos_ativos",
    "valores_derivados",
    "pontuar_criterio",
]

_MAX_TEXTO = 500
_MAX_ITEM = 120
_MAX_ITENS = 20


class EngineError(RuntimeError):
    """The version cannot be evaluated (only an unvalidated version triggers it)."""


# ── value validation (shared by the engine and the service) ─────────────────

def validar_valor(criterio: CriterioDef, valor: Any) -> tuple[bool, Any, str | None]:
    """``(ok, valor_normalizado, codigo)`` — ``codigo`` is a typed refusal
    (``valor_invalido`` / ``opcao_invalida``), never prose."""
    tipo = criterio.tipo
    opcoes = {o.valor for o in criterio.opcoes}
    if tipo == "enum":
        if not isinstance(valor, str):
            return False, None, "valor_invalido"
        if valor not in opcoes:
            return False, None, "opcao_invalida"
        return True, valor, None
    if tipo == "multi":
        if not isinstance(valor, list) or not valor or len(valor) > _MAX_ITENS:
            return False, None, "valor_invalido"
        itens: list[str] = []
        for i in valor:
            if not isinstance(i, str) or not i.strip() or len(i) > _MAX_ITEM:
                return False, None, "valor_invalido"
            if opcoes and i not in opcoes:
                return False, None, "opcao_invalida"
            if i not in itens:
                itens.append(i)
        return True, itens, None
    if tipo == "bool":
        return (True, valor, None) if isinstance(valor, bool) else (False, None, "valor_invalido")
    if tipo == "numero":
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            return False, None, "valor_invalido"
        return True, valor, None
    if tipo == "faixa":
        if not isinstance(valor, dict) or not valor or set(valor) - {"min", "max"}:
            return False, None, "valor_invalido"
        nums = {}
        for k, v in valor.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                return False, None, "valor_invalido"
            nums[k] = v
        if "min" in nums and "max" in nums and nums["min"] > nums["max"]:
            return False, None, "valor_invalido"
        return True, nums, None
    if tipo == "texto":
        if not isinstance(valor, str) or not valor.strip() or len(valor) > _MAX_TEXTO:
            return False, None, "valor_invalido"
        return True, valor.strip(), None
    if tipo == "imovel_ref":
        if not isinstance(valor, str) or not valor.strip() or len(valor) > 64:
            return False, None, "valor_invalido"
        return True, valor.strip(), None
    return False, None, "valor_invalido"


# ── events → derived facts ──────────────────────────────────────────────────

def _por_codigo(eventos: Sequence[EventoImovel]) -> tuple[set[str], dict[str, str]]:
    """Offered codes and, per code, its LATEST reaction event (list order wins)."""
    oferecidos: set[str] = set()
    ultima: dict[str, str] = {}
    for e in eventos:
        if e.evento == "oferecido":
            oferecidos.add(e.codigo_imovel)
        else:
            ultima[e.codigo_imovel] = e.evento
    return oferecidos, ultima


def eventos_ativos(eventos: Sequence[EventoImovel]) -> frozenset[str]:
    """Event kinds currently in force: ``oferecido`` if anything was offered,
    plus each code's latest reaction (a later ``nao_gostou`` supersedes an
    earlier ``gostou`` of the same code)."""
    oferecidos, ultima = _por_codigo(eventos)
    ativos = set(ultima.values())
    if oferecidos:
        ativos.add("oferecido")
    return frozenset(ativos)


def valores_derivados(eventos: Sequence[EventoImovel]) -> dict[str, Any]:
    """The derived criteria, present only when non-trivial (count > 0 / true)."""
    oferecidos, ultima = _por_codigo(eventos)
    out: dict[str, Any] = {}
    gostou = sum(1 for ev in ultima.values() if ev in ("gostou", "quer_visitar"))
    if gostou:
        out["imoveis_gostou"] = gostou
    if "quer_visitar" in ultima.values():
        out["deseja_visitar"] = True
    if oferecidos:
        out["imoveis_oferecidos"] = len(oferecidos)
    if "quer_ver_mais" in ultima.values():
        out["quer_mais_opcoes"] = True
    return out


# ── scoring ─────────────────────────────────────────────────────────────────

def pontuar_criterio(criterio: CriterioDef, valor: Any) -> int:
    """Points of one criterion value (0 when the map has no entry)."""
    p = criterio.pontuacao or {}
    if not p or not preenchido(valor):
        return 0
    tipo = criterio.tipo
    if tipo == "enum":
        return int((p.get("opcoes") or {}).get(valor, 0)) if isinstance(valor, str) else 0
    if tipo == "bool":
        if isinstance(valor, bool):
            return int(p.get("true" if valor else "false", 0))
        return 0
    if tipo in ("numero", "faixa"):
        ref = ponto_de_referencia(valor)
        if ref is None:
            return 0
        for faixa in p if isinstance(p, list) else p.get("faixas", []):
            lo, hi = faixa.get("min"), faixa.get("max")
            if (lo is None or ref >= lo) and (hi is None or ref <= hi):
                return int(faixa.get("pts", 0))
        return 0
    # texto / multi / imovel_ref
    itens = len(valor) if isinstance(valor, list) else 1
    pts = int(p.get("preenchido", 0)) + int(p.get("por_item", 0)) * itens
    if "max" in p:
        pts = min(pts, int(p["max"]))
    return pts


# ── the engine ──────────────────────────────────────────────────────────────

def _expirado(c: CriterioDef, r: Registro, agora: datetime | None) -> bool:
    """``validade_dias``: a record older than the criterion's validity stops counting.
    Needs the clock (``agora``) and a record timestamp; without either nothing expires."""
    if c.validade_dias is None or agora is None or r.created_at is None:
        return False
    return (agora - r.created_at).total_seconds() > c.validade_dias * 86400


def _ultimos_validos(
    versao: VersaoPadrao, registros: Sequence[Registro], agora: datetime | None = None,
) -> dict[str, Any]:
    """Latest VALID, unexpired record per active, non-derived criterion of the version.
    Later in the sequence wins; a record the version no longer accepts is skipped, and an
    expired latest record leaves the criterion unfilled (it is missing again)."""
    ativos = {c.chave: c for c in versao.criterios if c.ativo and c.chave not in DERIVADOS}
    out: dict[str, Any] = {}
    for r in registros:
        c = ativos.get(r.criterio_chave)
        if c is None or c.sensivel == "nao_coletar":
            continue
        ok, norm, _ = validar_valor(c, r.valor)
        if ok:
            out[c.chave] = norm
            if _expirado(c, r, agora):
                out.pop(c.chave)
    return out


def _estado_hash(versao_id: Any, valores: dict[str, Any], score: int, estagio: str) -> str:
    raw = json.dumps(
        {"v": str(versao_id), "valores": valores, "score": score, "estagio": estagio},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def calcular(
    versao: VersaoPadrao,
    registros: Sequence[Registro],
    eventos_imovel: Sequence[EventoImovel],
    agora: datetime | None = None,
) -> EstadoQualificacao:
    valores = _ultimos_validos(versao, registros, agora)
    valores.update(valores_derivados(eventos_imovel))
    ativos_ev = eventos_ativos(eventos_imovel)

    score_max = versao.parametros.score_max
    total = 0
    por_eixo: dict[str, int] = {}
    for c in versao.criterios:
        if c.ativo and c.chave in valores:
            pts = pontuar_criterio(c, valores[c.chave])
            total += pts
            if c.eixo:
                por_eixo[c.eixo] = por_eixo.get(c.eixo, 0) + pts
    score = max(0, min(total, score_max))
    scores = {k: max(0, min(v, score_max)) for k, v in sorted(por_eixo.items())}
    for c in versao.criterios:  # an axis with no point yet is 0, not absent
        if c.eixo:
            scores.setdefault(c.eixo, 0)

    ctx = Contexto(valores=valores, score=score, eventos=ativos_ev, scores=scores)
    ordenados = sorted(versao.estagios, key=lambda e: e.ordem)
    verdadeiros = [e for e in ordenados if avaliar_regra(e.regra, ctx)]
    if not verdadeiros:
        raise EngineError("nenhum estagio satisfeito (versao sem estagio base)")
    atual = verdadeiros[-1]

    proximo = next((e for e in ordenados if e.ordem > atual.ordem and not e.terminal), None)
    faltando: list[str] = []
    if proximo is not None:
        ordem_crit = {c.chave: c for c in versao.criterios if c.ativo}
        refs = [
            k for k in criterios_referenciados(proximo.regra)
            if k in ordem_crit and k not in DERIVADOS and not preenchido(valores.get(k))
        ]
        faltando = sorted(refs, key=lambda k: (ordem_crit[k].ordem, k))

    proximo_criterio = None
    if faltando:
        c = next(c for c in versao.criterios if c.chave == faltando[0])
        proximo_criterio = ProximoCriterio(
            chave=c.chave, rotulo=c.rotulo, descricao_modelo=c.descricao_modelo,
            opcoes=tuple(
                {"valor": o.valor, "rotulo": o.rotulo, "descricao_modelo": o.descricao_modelo}
                for o in c.opcoes
            ),
        )

    return EstadoQualificacao(
        valores=valores,
        score=score,
        estagio=atual.chave,
        faltando=tuple(faltando),
        proximo_criterio=proximo_criterio,
        pode_ofertar=avaliar_regra(versao.parametros.minimo_para_ofertar, ctx),
        pode_concluir=atual.conclusivo,
        hash=_estado_hash(versao.id, valores, score, atual.chave),
        calculado_em=agora,
        scores=scores,
    )


# ── publish-time validation ─────────────────────────────────────────────────

def validar_versao(versao: VersaoPadrao) -> list[dict[str, str]]:
    """Every reason this version cannot be published (empty = publishable).
    Each entry is ``{code, path, detail}``; the router answers 422."""
    erros: list[dict[str, str]] = []

    def err(code: str, path: str, detail: str) -> None:
        erros.append({"code": code, "path": path, "detail": detail})

    chaves = [c.chave for c in versao.criterios]
    if len(set(chaves)) != len(chaves):
        err("criterio_duplicado", "criterios", "chaves repetidas")
    for c in versao.criterios:
        p = f"criterios.{c.chave}"
        if c.grupo not in GRUPOS:
            err("grupo_invalido", p, c.grupo)
        if c.tipo not in TIPOS:
            err("tipo_invalido", p, c.tipo)
        if c.sensivel not in SENSIVEL:
            err("sensivel_invalido", p, str(c.sensivel))
        if c.validade_dias is not None and c.validade_dias < 1:
            err("validade_invalida", p, "validade_dias >= 1")
        if c.eixo is not None and not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", c.eixo):
            err("eixo_invalido", p, str(c.eixo))
        if c.sensivel == "faixa" and c.tipo not in ("faixa", "enum"):
            err("sensivel_invalido", p, "sensivel=faixa exige tipo faixa ou enum")
        if c.tipo == "enum" and not c.opcoes:
            err("opcoes_obrigatorias", p, "enum sem opcoes")
        vals = [o.valor for o in c.opcoes]
        if len(set(vals)) != len(vals):
            err("opcao_duplicada", p, "valores repetidos")
        if c.tipo == "enum":
            for v in (c.pontuacao or {}).get("opcoes", {}):
                if v not in vals:
                    err("pontuacao_invalida", p, f"pontuacao de opcao inexistente {v!r}")
    estagios = sorted(versao.estagios, key=lambda e: e.ordem)
    if not estagios:
        err("sem_estagios", "estagios", "nenhum estagio")
    ek = [e.chave for e in estagios]
    if len(set(ek)) != len(ek):
        err("estagio_duplicado", "estagios", "chaves repetidas")
    if len({e.ordem for e in estagios}) != len(estagios):
        err("ordem_duplicada", "estagios", "ordens repetidas")
    validos = [c.chave for c in versao.criterios if c.ativo]
    eixos = sorted({c.eixo for c in versao.criterios if c.ativo and c.eixo})
    for e in estagios:
        erros.extend(validar_regra(e.regra, validos, caminho=f"estagios.{e.chave}.regra", eixos=eixos))
    erros.extend(validar_regra(
        versao.parametros.minimo_para_ofertar, validos, caminho="parametros.minimo_para_ofertar", eixos=eixos,
    ))
    if estagios and not sempre_verdadeira(estagios[0].regra, versao.parametros.score_max):
        err("sem_estagio_base", f"estagios.{estagios[0].chave}.regra",
            "o estagio de menor ordem precisa casar sempre")
    if not 1 <= versao.parametros.lote_ofertas <= 5:
        err("parametro_invalido", "parametros.lote_ofertas", "1..5")
    if versao.parametros.score_max < 1:
        err("parametro_invalido", "parametros.score_max", ">= 1")
    return erros
