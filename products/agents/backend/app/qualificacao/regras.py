"""The closed predicate DSL of stage rules and ``minimo_para_ofertar``
(CONTRACT §3.2). Pure: evaluate, collect references, validate at publish.

Grammar (anything else is a validation error, never silently ignored)::

    {"todos": [rule, ...]}            all true (empty = true)
    {"algum": [rule, ...]}            any true (empty = false)
    {"nao": rule}
    {"criterio": k, "op": "preenchido"}
    {"criterio": k, "op": "em", "valores": [..]}     equal to one / multi intersects
    {"criterio": k, "op": ">=", "valor": n}          numero; faixa uses its reference point
    {"score": {">=": n}}
    {"evento": "quer_visitar"}

A rule is a finite JSON tree, so a *reference cycle* cannot be expressed in this
grammar (a rule never names another stage). The cycle guard is therefore the
closed grammar plus a depth cap (``MAX_PROFUNDIDADE``): a deeper rule is refused
with ``regra_profunda``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.qualificacao.models import DERIVADOS, EVENTOS_REGRA

MAX_PROFUNDIDADE = 10
OPS = ("preenchido", "em", ">=")


class RegraInvalida(ValueError):
    """Raised by :func:`avaliar_regra` on a malformed rule (a validated version
    never triggers it)."""


@dataclass(frozen=True)
class Contexto:
    valores: dict[str, Any]
    score: int
    eventos: frozenset[str]
    scores: dict[str, int] | None = None  # per axis
    contagens: dict[str, int] | None = None  # event name -> how many
    identificacao_completa: bool = False


# ── value helpers ───────────────────────────────────────────────────────────

def preenchido(valor: Any) -> bool:
    """Answered. ``False`` and ``0`` count as answered; None / "" / [] / {} do not."""
    if valor is None:
        return False
    if isinstance(valor, bool):
        return True
    if isinstance(valor, (int, float)):
        return True
    if isinstance(valor, str):
        return valor.strip() != ""
    if isinstance(valor, (list, tuple, dict, set, frozenset)):
        return len(valor) > 0
    return True


def ponto_de_referencia(valor: Any) -> float | None:
    """The number a ``numero`` / ``faixa`` value stands for: the number itself;
    for a range the midpoint (or the one bound present)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, dict):
        lo, hi = valor.get("min"), valor.get("max")
        nums = [float(x) for x in (lo, hi) if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if len(nums) == 2:
            return (nums[0] + nums[1]) / 2
        if len(nums) == 1:
            return nums[0]
    return None


def _igual(a: Any, b: Any) -> bool:
    """Type-aware equality: ``True`` is not ``1``."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def _em(valor: Any, candidatos: list[Any]) -> bool:
    itens = valor if isinstance(valor, (list, tuple)) else [valor]
    return any(_igual(i, c) for i in itens for c in candidatos)


# ── evaluation ──────────────────────────────────────────────────────────────

def avaliar_regra(regra: Any, ctx: Contexto) -> bool:
    if not isinstance(regra, dict) or not regra:
        raise RegraInvalida(f"regra malformada: {regra!r}")
    regra = {k: v for k, v in regra.items() if k != "id"}  # "id" is explainability metadata only
    if not regra:
        raise RegraInvalida("regra sem corpo")
    if "todos" in regra:
        return all(avaliar_regra(r, ctx) for r in _lista(regra["todos"]))
    if "algum" in regra:
        return any(avaliar_regra(r, ctx) for r in _lista(regra["algum"]))
    if "nao" in regra:
        return not avaliar_regra(regra["nao"], ctx)
    if "score" in regra:
        sc = regra["score"] if isinstance(regra["score"], dict) else {}
        limite = sc.get(">=")
        if not isinstance(limite, (int, float)) or isinstance(limite, bool):
            raise RegraInvalida(f"score malformado: {regra['score']!r}")
        eixo = sc.get("eixo")
        if eixo is None:
            return ctx.score >= limite
        return (ctx.scores or {}).get(eixo, 0) >= limite
    if "evento" in regra:
        return regra["evento"] in ctx.eventos
    if "identificacao" in regra:
        if regra["identificacao"] != "completa":
            raise RegraInvalida(f"identificacao malformada: {regra!r}")
        return ctx.identificacao_completa
    if "contagem" in regra:
        c = regra["contagem"] if isinstance(regra["contagem"], dict) else {}
        if not isinstance(c.get(">="), (int, float)) or isinstance(c.get(">="), bool) or "evento" not in c:
            raise RegraInvalida(f"contagem malformada: {regra['contagem']!r}")
        return (ctx.contagens or {}).get(c["evento"], 0) >= c[">="]
    if "criterio" in regra:
        valor = ctx.valores.get(regra["criterio"])
        op = regra.get("op")
        if op == "preenchido":
            return preenchido(valor)
        if op == "em":
            return preenchido(valor) and _em(valor, _lista(regra.get("valores")))
        if op == ">=":
            ref = ponto_de_referencia(valor)
            alvo = regra.get("valor")
            if not isinstance(alvo, (int, float)) or isinstance(alvo, bool):
                raise RegraInvalida(f"valor malformado: {regra!r}")
            return ref is not None and ref >= alvo
        raise RegraInvalida(f"op desconhecido: {op!r}")
    raise RegraInvalida(f"regra desconhecida: {regra!r}")


def _lista(v: Any) -> list[Any]:
    if not isinstance(v, list):
        raise RegraInvalida(f"lista esperada: {v!r}")
    return v


def regra_disparada(regra: Any, ctx: Contexto) -> str | None:
    """The explainability id of a TRUE rule: the "id" of the first true branch of an ``algum``
    (descending), else the node's own "id", else None. Call only on a rule that evaluates true."""
    if not isinstance(regra, dict):
        return None
    proprio = regra.get("id") if isinstance(regra.get("id"), str) else None
    if "algum" in regra and isinstance(regra["algum"], list):
        for sub in regra["algum"]:
            if avaliar_regra(sub, ctx):
                return regra_disparada(sub, ctx) or proprio
    if "todos" in regra and isinstance(regra["todos"], list):
        return proprio or next((i for i in (regra_disparada(s, ctx) for s in regra["todos"]) if i), None)
    return proprio


# ── references ──────────────────────────────────────────────────────────────

def criterios_referenciados(regra: Any) -> list[str]:
    """Criterion keys a rule reads, in first-appearance order, de-duplicated."""
    out: list[str] = []

    def walk(r: Any) -> None:
        if not isinstance(r, dict):
            return
        for k in ("todos", "algum"):
            if k in r and isinstance(r[k], list):
                for sub in r[k]:
                    walk(sub)
        if "nao" in r:
            walk(r["nao"])
        if "criterio" in r and isinstance(r["criterio"], str) and r["criterio"] not in out:
            out.append(r["criterio"])

    walk(regra)
    return out


def usa_identificacao(regra: Any) -> bool:
    """Whether the rule contains the ``{"identificacao": "completa"}`` atom."""
    if isinstance(regra, dict):
        if "identificacao" in regra:
            return True
        return any(usa_identificacao(v) for v in regra.values() if isinstance(v, (dict, list))) or any(
            usa_identificacao(i) for v in regra.values() if isinstance(v, list) for i in v)
    return False


# ── static analysis (publish-time) ──────────────────────────────────────────

def sempre_verdadeira(regra: Any, score_max: int = 100) -> bool:
    """Structurally true for EVERY state (no criteria, no events needed)."""
    if not isinstance(regra, dict):
        return False
    if "todos" in regra and isinstance(regra["todos"], list):
        return all(sempre_verdadeira(r, score_max) for r in regra["todos"])
    if "algum" in regra and isinstance(regra["algum"], list):
        return any(sempre_verdadeira(r, score_max) for r in regra["algum"])
    if "nao" in regra:
        return sempre_falsa(regra["nao"], score_max)
    if "score" in regra and isinstance(regra["score"], dict):
        lim = regra["score"].get(">=")
        return isinstance(lim, (int, float)) and not isinstance(lim, bool) and lim <= 0
    return False


def sempre_falsa(regra: Any, score_max: int = 100) -> bool:
    if not isinstance(regra, dict):
        return False
    if "algum" in regra and isinstance(regra["algum"], list):
        return all(sempre_falsa(r, score_max) for r in regra["algum"])
    if "todos" in regra and isinstance(regra["todos"], list):
        return any(sempre_falsa(r, score_max) for r in regra["todos"])
    if "nao" in regra:
        return sempre_verdadeira(regra["nao"], score_max)
    if "score" in regra and isinstance(regra["score"], dict):
        lim = regra["score"].get(">=")
        return isinstance(lim, (int, float)) and not isinstance(lim, bool) and lim > score_max
    return False


def validar_regra(
    regra: Any, criterios_validos: Iterable[str], *, caminho: str = "regra", _prof: int = 0,
    eixos: Iterable[str] = (),
) -> list[dict[str, str]]:
    """Every problem of ``regra`` as ``{code, path, detail}`` (empty = valid).

    ``criterios_validos`` = the version's criterion keys plus :data:`DERIVADOS`.
    """
    validos = set(criterios_validos) | set(DERIVADOS)
    eixos_validos = set(eixos)
    erros: list[dict[str, str]] = []

    def err(code: str, path: str, detail: str) -> None:
        erros.append({"code": code, "path": path, "detail": detail})

    def walk(r: Any, path: str, prof: int) -> None:
        if prof > MAX_PROFUNDIDADE:
            err("regra_profunda", path, f"mais de {MAX_PROFUNDIDADE} niveis")
            return
        if isinstance(r, dict) and "id" in r:
            if not isinstance(r["id"], str) or not 0 < len(r["id"]) <= 64:
                err("regra_invalida", path, "id deve ser texto de 1..64")
            r = {k: v for k, v in r.items() if k != "id"}
        if not isinstance(r, dict) or not r:
            err("regra_invalida", path, "objeto nao vazio esperado")
            return
        if "todos" in r or "algum" in r:
            chave = "todos" if "todos" in r else "algum"
            if set(r) != {chave} or not isinstance(r[chave], list):
                err("regra_invalida", path, f"{chave} aceita so uma lista")
                return
            for i, sub in enumerate(r[chave]):
                walk(sub, f"{path}.{chave}[{i}]", prof + 1)
            return
        if "nao" in r:
            if set(r) != {"nao"}:
                err("regra_invalida", path, "nao aceita so uma regra")
                return
            walk(r["nao"], f"{path}.nao", prof + 1)
            return
        if "score" in r:
            s = r["score"]
            if set(r) != {"score"} or not isinstance(s, dict) or not set(s) <= {">=", "eixo"} \
                    or not isinstance(s.get(">="), (int, float)) or isinstance(s.get(">="), bool):
                err("regra_invalida", path, 'score exige {">=": numero} (e opcionalmente "eixo")')
            elif "eixo" in s and s["eixo"] not in eixos_validos:
                err("eixo_desconhecido", path, f"eixo {s['eixo']!r}")
            return
        if "evento" in r:
            if set(r) != {"evento"} or r["evento"] not in EVENTOS_REGRA:
                err("evento_desconhecido", path, f"evento {r.get('evento')!r}")
            return
        if "identificacao" in r:
            if set(r) != {"identificacao"} or r["identificacao"] != "completa":
                err("regra_invalida", path, 'identificacao exige "completa"')
            return
        if "contagem" in r:
            c = r["contagem"]
            if set(r) != {"contagem"} or not isinstance(c, dict) or set(c) != {"evento", ">="} \
                    or not isinstance(c[">="], (int, float)) or isinstance(c[">="], bool):
                err("regra_invalida", path, 'contagem exige {"evento": e, ">=": n}')
            elif c["evento"] not in EVENTOS_REGRA:
                err("evento_desconhecido", path, f"evento {c['evento']!r}")
            return
        if "criterio" in r:
            chave = r["criterio"]
            if chave not in validos:
                err("criterio_desconhecido", path, f"criterio {chave!r}")
            op = r.get("op")
            if op not in OPS:
                err("op_desconhecido", path, f"op {op!r}")
                return
            extra = set(r) - {"criterio", "op", "valores", "valor"}
            if extra:
                err("regra_invalida", path, f"chaves inesperadas {sorted(extra)}")
            if op == "em" and (not isinstance(r.get("valores"), list) or not r["valores"]):
                err("regra_invalida", path, "em exige valores (lista nao vazia)")
            if op == ">=" and (not isinstance(r.get("valor"), (int, float)) or isinstance(r.get("valor"), bool)):
                err("regra_invalida", path, ">= exige valor numerico")
            return
        err("regra_invalida", path, f"chaves {sorted(r)} nao reconhecidas")

    walk(regra, caminho, _prof)
    return erros
