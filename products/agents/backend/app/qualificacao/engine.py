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
from typing import Any, Iterable, Sequence

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
    LeadSinais,
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
    regra_disparada,
    sempre_verdadeira,
    usa_identificacao,
    validar_regra,
)

__all__ = [
    "EngineError",
    "calcular",
    "no_escopo",
    "validar_valor",
    "validar_versao",
    "eventos_ativos",
    "contagens_de_eventos",
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
    if tipo in ("derivado", "identificacao"):
        return False, None, "criterio_derivado" if tipo == "derivado" else "usar_identificacao"
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


_REJEICAO = ("nao_gostou", "descartado")


def contagens_de_eventos(eventos: Sequence[EventoImovel], sinais: LeadSinais | None = None) -> dict[str, int]:
    """How many codes sit in each event state, plus ``lote_rejeitado`` (offer lotes whose every code
    was rejected) and the caller's own signalled events (``pediu_humano`` ...)."""
    oferecidos, ultima = _por_codigo(eventos)
    out: dict[str, int] = {}
    if oferecidos:
        out["oferecido"] = len(oferecidos)
    for ev in ultima.values():
        out[ev] = out.get(ev, 0) + 1
    lotes: dict[int, list[str]] = {}
    for e in eventos:
        if e.evento == "oferecido" and e.lote is not None:
            lotes.setdefault(e.lote, []).append(e.codigo_imovel)
    rejeitados = sum(1 for cods in lotes.values() if all(ultima.get(c) in _REJEICAO for c in cods))
    if rejeitados:
        out["lote_rejeitado"] = rejeitados
    for k, n in (sinais.eventos if sinais else {}).items():
        if n:
            out[k] = out.get(k, 0) + int(n)
    return out


def valores_derivados(
    eventos: Sequence[EventoImovel], sinais: LeadSinais | None = None, agora: datetime | None = None,
) -> dict[str, Any]:
    """System-derived criteria, present only when non-trivial (count > 0 / true). Never recordable
    by the model (``registrar_perfil`` refuses them)."""
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
    rejeitados = sum(1 for ev in ultima.values() if ev in _REJEICAO)
    if rejeitados:
        out["imoveis_rejeitados"] = rejeitados
    if sinais is not None:
        if sinais.respostas_count:
            out["respostas_count"] = sinais.respostas_count
        dias = _dias_sem_resposta(sinais, agora)
        if dias is not None:
            out["dias_sem_resposta"] = int(dias)
    return out


def _dias_sem_resposta(sinais: LeadSinais | None, agora: datetime | None) -> float | None:
    if sinais is None or sinais.ultima_resposta_em is None or agora is None:
        return None
    return max((agora - sinais.ultima_resposta_em).total_seconds() / 86400, 0.0)


# ── scoring ─────────────────────────────────────────────────────────────────

def pontuar_criterio(criterio: CriterioDef, valor: Any) -> int:
    """Points of one criterion value (0 when the map has no entry). May be negative."""
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
    if tipo in ("numero", "faixa", "derivado"):
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

def no_escopo(c: CriterioDef, escopo: str | None) -> bool:
    """Whether criterion ``c`` is askable in ``escopo`` (no scope asked = everything)."""
    return escopo is None or c.escopo is None or c.escopo == escopo


def _expirado(c: CriterioDef, r: Registro, agora: datetime | None) -> bool:
    """``validade_dias``: a record older than the criterion's validity stops counting.
    Needs the clock (``agora``) and a record timestamp; without either nothing expires."""
    if c.validade_dias is None or agora is None or r.created_at is None:
        return False
    return (agora - r.created_at).total_seconds() > c.validade_dias * 86400


def _ultimos_validos(
    versao: VersaoPadrao, registros: Sequence[Registro], agora: datetime | None = None,
) -> dict[str, Any]:
    """Latest VALID, unexpired record per active, recordable criterion of the version.
    Later in the sequence wins; a record the version no longer accepts is skipped, and an
    expired latest record leaves the criterion unfilled (it is missing again). System-derived
    and identity criteria are never read from records."""
    ativos = {
        c.chave: c for c in versao.criterios
        if c.ativo and c.chave not in DERIVADOS and c.tipo not in ("derivado", "identificacao")
    }
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


def _estado_hash(versao_id: Any, valores: dict[str, Any], scores: dict[str, int], score: int, estagio: str) -> str:
    raw = json.dumps(
        {"v": str(versao_id), "valores": valores, "scores": scores, "score": score, "estagio": estagio},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _fator_decaimento(cfg: dict[str, Any], dias: float | None) -> float:
    """Factor of the decay step with the largest ``apos_dias`` <= days since the last reply."""
    if dias is None:
        return 1.0
    fator = 1.0
    melhor = -1
    for passo in cfg.get("decaimento") or []:
        if passo["apos_dias"] <= dias and passo["apos_dias"] > melhor:
            melhor, fator = passo["apos_dias"], float(passo["fator"])
    return fator


def calcular(
    versao: VersaoPadrao,
    registros: Sequence[Registro],
    eventos_imovel: Sequence[EventoImovel],
    agora: datetime | None = None,
    escopo: str | None = None,
    sinais: LeadSinais | None = None,
    confirmados: Iterable[str] = (),
) -> EstadoQualificacao:
    """Pure state computation.

    * ``escopo``: the asking agent's scope. State (values, score, stage) is the lead's shared state
      over the whole standard; ``faltando`` / ``proximo_criterio`` only offer criteria whose ``escopo``
      is empty or equal to it, so one agent never asks another agent's questions.
    * ``sinais``: system signals (last reply time, reply count, signalled events, identity fields
      collected). With ``agora`` they drive ``dias_sem_resposta`` and per-axis decay.
    * ``confirmados``: terminal stages a HUMAN confirmed. The engine only ever *suggests* a terminal
      stage (LGPD art. 20) until it is confirmed.
    """
    sinais = sinais or LeadSinais()
    valores = _ultimos_validos(versao, registros, agora)
    valores.update(valores_derivados(eventos_imovel, sinais, agora))
    ident_chaves = [c.chave for c in versao.criterios if c.ativo and c.tipo == "identificacao"]
    for k in ident_chaves:  # the FLAG that it was collected, never the value
        if k in sinais.identificacao:
            valores[k] = True
    ident_completa = bool(ident_chaves) and all(k in sinais.identificacao for k in ident_chaves)
    contagens = contagens_de_eventos(eventos_imovel, sinais)
    ativos_ev = frozenset(k for k, n in contagens.items() if n > 0)
    dias = _dias_sem_resposta(sinais, agora)

    # ── points -> per-axis score (multipliers, decay, clamp) -> total ──
    score_max = versao.parametros.score_max
    cfg_eixos = versao.parametros.eixos or {}
    pontos: dict[str, dict[str, int]] = {}
    sem_eixo: dict[str, int] = {}
    for c in versao.criterios:
        if c.ativo and c.chave in valores:
            pts = pontuar_criterio(c, valores[c.chave])
            if c.eixo:
                pontos.setdefault(c.eixo, {})[c.chave] = pts
            elif pts:
                sem_eixo[c.chave] = pts
    nomes_eixos = sorted({c.eixo for c in versao.criterios if c.ativo and c.eixo} | set(cfg_eixos))
    ctx_base = Contexto(valores=valores, score=0, eventos=ativos_ev, scores={}, contagens=contagens,
                        identificacao_completa=ident_completa)
    scores: dict[str, int] = {}
    detalhe_eixos: dict[str, Any] = {}
    for eixo in nomes_eixos:
        cfg = cfg_eixos.get(eixo, {})
        bruto = sum(pontos.get(eixo, {}).values())
        mult = 1.0
        for mu in cfg.get("multiplicadores") or []:
            if avaliar_regra(mu["quando"], ctx_base):
                mult *= float(mu["fator"])
        decai = _fator_decaimento(cfg, dias)
        teto = int(cfg.get("max", score_max))
        scores[eixo] = max(0, min(round(bruto * mult * decai), teto))
        detalhe_eixos[eixo] = {
            "pontos": dict(pontos.get(eixo, {})), "bruto": bruto, "multiplicador": mult,
            "decaimento": decai, "score": scores[eixo],
        }
    score = max(0, min(sum(scores.values()) + sum(sem_eixo.values()), score_max))
    detalhe = {"eixos": detalhe_eixos, "sem_eixo": sem_eixo}

    ctx = Contexto(valores=valores, score=score, eventos=ativos_ev, scores=scores, contagens=contagens,
                   identificacao_completa=ident_completa)

    # ── stage: highest-ordem true NON-terminal; terminal ones are only suggested ──
    ordenados = sorted(versao.estagios, key=lambda e: e.ordem)
    verdadeiros = [e for e in ordenados if avaliar_regra(e.regra, ctx)]
    normais = [e for e in verdadeiros if not e.terminal]
    terminais = [e for e in verdadeiros if e.terminal]
    if not normais and not terminais:
        raise EngineError("nenhum estagio satisfeito (versao sem estagio base)")
    confirmados = set(confirmados)
    confirmado = next((t for t in reversed(terminais) if t.chave in confirmados), None)
    sugerido = None
    if confirmado is not None:
        atual = confirmado
    else:
        if not normais:
            raise EngineError("nenhum estagio nao terminal satisfeito (versao sem estagio base)")
        atual = normais[-1]
        if terminais:
            t = terminais[-1]
            sugerido = {"estagio": t.chave, "regra_id": regra_disparada(t.regra, ctx) or t.chave}
    regra_id = regra_disparada(atual.regra, ctx) or atual.chave

    pedir = True
    if versao.parametros.pedir_identificacao_quando is not None:
        pedir = avaliar_regra(versao.parametros.pedir_identificacao_quando, ctx)
    ident_faltando = [k for k in ident_chaves if k not in sinais.identificacao]

    proximo = None if atual.terminal else next(
        (e for e in ordenados if e.ordem > atual.ordem and not e.terminal), None)
    faltando: list[str] = []
    if proximo is not None:
        ordem_crit = {c.chave: c for c in versao.criterios if c.ativo and no_escopo(c, escopo)}
        refs = criterios_referenciados(proximo.regra)
        if usa_identificacao(proximo.regra):
            refs = [*refs, *[k for k in ident_chaves if k not in refs]]
        faltando = sorted(
            (k for k in refs if k in ordem_crit and k not in DERIVADOS and not preenchido(valores.get(k))
             and ordem_crit[k].tipo != "derivado"
             and (pedir or ordem_crit[k].tipo != "identificacao")),
            key=lambda k: (ordem_crit[k].ordem, k),
        )

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
        pode_concluir=atual.conclusivo and not atual.terminal,
        hash=_estado_hash(versao.id, valores, scores, score, atual.chave),
        calculado_em=agora,
        scores=scores,
        regra_id=regra_id,
        descartado_sugerido=sugerido,
        detalhe=detalhe,
        identificacao_faltando=tuple(ident_faltando),
        pedir_identificacao=pedir,
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
        if c.tipo == "derivado" and c.chave not in DERIVADOS:
            err("derivado_desconhecido", p, "sem fonte no sistema")
        if c.tipo == "identificacao" and c.pontuacao:
            err("pontuacao_invalida", p, "identificacao nao pontua")
        if c.escopo is not None and not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", c.escopo):
            err("escopo_invalido", p, str(c.escopo))
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
    eixos = sorted({c.eixo for c in versao.criterios if c.ativo and c.eixo} | set(versao.parametros.eixos or {}))
    erros.extend(_validar_eixos(versao.parametros.eixos or {}, validos, eixos))
    if versao.parametros.pedir_identificacao_quando is not None:
        erros.extend(validar_regra(
            versao.parametros.pedir_identificacao_quando, validos,
            caminho="parametros.pedir_identificacao_quando", eixos=eixos))
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


def _validar_eixos(cfg: dict[str, Any], validos: list[str], eixos: list[str]) -> list[dict[str, str]]:
    erros: list[dict[str, str]] = []

    def err(code: str, path: str, detail: str) -> None:
        erros.append({"code": code, "path": path, "detail": detail})

    for nome, c in cfg.items():
        p = f"parametros.eixos.{nome}"
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", nome) or not isinstance(c, dict):
            err("eixo_invalido", p, "nome ou config invalida")
            continue
        if set(c) - {"max", "multiplicadores", "decaimento"}:
            err("eixo_invalido", p, f"chaves {sorted(set(c) - {'max', 'multiplicadores', 'decaimento'})}")
        if "max" in c and (not isinstance(c["max"], int) or isinstance(c["max"], bool) or c["max"] < 1):
            err("eixo_invalido", f"{p}.max", ">= 1")
        for i, mu in enumerate(c.get("multiplicadores") or []):
            pm = f"{p}.multiplicadores[{i}]"
            if not isinstance(mu, dict) or set(mu) != {"quando", "fator"} \
                    or not isinstance(mu["fator"], (int, float)) or isinstance(mu["fator"], bool) or mu["fator"] < 0:
                err("multiplicador_invalido", pm, 'exige {"quando": regra, "fator": numero >= 0}')
                continue
            if "score" in str(mu["quando"]):
                err("multiplicador_invalido", pm, "o multiplicador nao pode depender de score")
            erros.extend(validar_regra(mu["quando"], validos, caminho=f"{pm}.quando", eixos=eixos))
        ultimo = 0
        for i, d in enumerate(c.get("decaimento") or []):
            pd = f"{p}.decaimento[{i}]"
            if not isinstance(d, dict) or set(d) != {"apos_dias", "fator"} \
                    or not isinstance(d["apos_dias"], int) or isinstance(d["apos_dias"], bool) or d["apos_dias"] < 1 \
                    or not isinstance(d["fator"], (int, float)) or isinstance(d["fator"], bool) \
                    or not 0 <= d["fator"] <= 1 or d["apos_dias"] <= ultimo:
                err("decaimento_invalido", pd, "apos_dias crescente >= 1 e fator em [0,1]")
                continue
            ultimo = d["apos_dias"]
    return erros
