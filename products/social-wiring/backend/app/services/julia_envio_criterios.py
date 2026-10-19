"""Julia wave 3 -- the send-criteria vocabulary: validation + evaluation (contract 5). Pure functions, no IO.

`grupos` = `[[{campo, operador, valor}]]` -- groups are OR'd, the criteria inside one group AND'd:

  comportamento      =        "qualificado"   locked base of group 0 (Julia's `qualificar_lead`)
  visita_solicitada  =        true            a visit was pre-scheduled through Julia
  operacao           =        compra|aluguel|administracao|atualizacao
  <slot key>         preenchido | >= | <= | entre   (numeric slots for the last three)

`nome` / `email` count as slot keys (the foundation stores them in columns, not in `slots`).
`validar_grupos` is the typed-422 gate of `PUT /api/julia/envio/regras`; `avaliar` is what the
`qualificar_lead` action / the visit hook / the cold timer run against a contato.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_slots_sensiveis as sensiveis

MAX_GRUPOS = 10
MAX_CRITERIOS = 10
OPERACOES = ("compra", "aluguel", "administracao", "atualizacao")
OPERADORES_SLOT = ("preenchido", ">=", "<=", "entre")
OPERADORES_NUMERICOS = (">=", "<=", "entre")
COMPORTAMENTO = "comportamento"
QUALIFICADO = "qualificado"
VISITA = "visita_solicitada"
OPERACAO = "operacao"
CAMPOS_FIXOS = frozenset({COMPORTAMENTO, VISITA, OPERACAO})
COLUNAS = ("nome", "email")  # slot-like keys stored as columns of julia_contatos
_CHAVE_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _erro(code: str, message: str, **details: Any) -> AppException:
    return AppException(code, message, status_code=422, details=details)


def _num(valor: Any) -> Optional[float]:
    if isinstance(valor, bool) or valor is None:
        return None
    return sensiveis.numero(valor)


def _validar_criterio(c: Any, chaves_slot: set[str], gi: int, ci: int) -> dict[str, Any]:
    pos = {"grupo": gi, "criterio": ci}
    if not isinstance(c, dict) or set(c) - {"campo", "operador", "valor"} or "campo" not in c or "operador" not in c:
        raise _erro("criterio_invalido", "Critério inválido.", **pos)
    campo, op, valor = str(c["campo"]), str(c["operador"]), c.get("valor")
    if campo == COMPORTAMENTO:
        if op != "=" or valor != QUALIFICADO:
            raise _erro("criterio_invalido", "O comportamento só pode ser 'qualificado'.", **pos)
        return {"campo": campo, "operador": "=", "valor": QUALIFICADO}
    if campo == VISITA:
        if op != "=" or valor is not True:
            raise _erro("criterio_invalido", "A visita só pode ser 'solicitada'.", **pos)
        return {"campo": campo, "operador": "=", "valor": True}
    if campo == OPERACAO:
        if op != "=" or valor not in OPERACOES:
            raise _erro("criterio_invalido", "Operação inválida.", **pos)
        return {"campo": campo, "operador": "=", "valor": valor}
    if not _CHAVE_RE.match(campo) or campo not in chaves_slot:
        raise _erro("campo_desconhecido", f"Campo desconhecido: {campo[:64]}.", campo=campo[:64], **pos)
    if op not in OPERADORES_SLOT:
        raise _erro("operador_invalido", "Operador inválido.", operador=op[:20], **pos)
    if op == "preenchido":
        return {"campo": campo, "operador": op, "valor": None}
    if campo in sensiveis.SENSIVEIS or campo in COLUNAS:
        raise _erro("campo_sensivel", "Este campo só aceita o critério 'preenchido'.", campo=campo, **pos)
    if op == "entre":
        if not isinstance(valor, (list, tuple)) or len(valor) != 2:
            raise _erro("valor_invalido", "Informe o mínimo e o máximo.", **pos)
        lo, hi = _num(valor[0]), _num(valor[1])
        if lo is None or hi is None or lo > hi:
            raise _erro("valor_invalido", "Faixa de valores inválida.", **pos)
        return {"campo": campo, "operador": op, "valor": [lo, hi]}
    n = _num(valor)
    if n is None:
        raise _erro("valor_invalido", "Informe um número.", **pos)
    return {"campo": campo, "operador": op, "valor": n}


def validar_grupos(grupos: Any, chaves_slot: Iterable[str]) -> list[list[dict[str, Any]]]:
    """Normalised groups, or the contract's typed 422: `grupos_invalidos` / `criterio_invalido` /
    `campo_desconhecido` / `operador_invalido` / `valor_invalido` / `campo_sensivel` / `base_obrigatoria`."""
    chaves = set(chaves_slot) | set(COLUNAS)
    if not isinstance(grupos, list) or not grupos or len(grupos) > MAX_GRUPOS:
        raise _erro("grupos_invalidos", f"Informe de 1 a {MAX_GRUPOS} grupos de critérios.")
    saida: list[list[dict[str, Any]]] = []
    for gi, g in enumerate(grupos):
        if not isinstance(g, list) or not g or len(g) > MAX_CRITERIOS:
            raise _erro("grupos_invalidos", f"Cada grupo precisa de 1 a {MAX_CRITERIOS} critérios.", grupo=gi)
        saida.append([_validar_criterio(c, chaves, gi, ci) for ci, c in enumerate(g)])
    if not any(c["campo"] == COMPORTAMENTO for c in saida[0]):
        raise _erro("base_obrigatoria", "Defina ao menos um critério no cartão Comportamento.")
    return saida


def chaves_usadas(grupos: Any) -> set[str]:
    """The slot keys a stored rule references (fixed fields excluded) -- what Perguntas must keep active."""
    if not isinstance(grupos, list):
        return set()
    return {
        str(c["campo"])
        for g in grupos if isinstance(g, list)
        for c in g if isinstance(c, dict) and c.get("campo") and c["campo"] not in CAMPOS_FIXOS
    }


def usa_visita(grupos: Any) -> bool:
    return isinstance(grupos, list) and any(
        isinstance(c, dict) and c.get("campo") == VISITA for g in grupos if isinstance(g, list) for c in g
    )



# ── evaluation ──────────────────────────────────────────────────────────────
def _valor_do_campo(campo: str, contato: dict[str, Any]) -> Any:
    if campo in COLUNAS:
        return contato.get(campo)
    return (contato.get("slots") or {}).get(campo)


def _preenchido(valor: Any) -> bool:
    return valor is not None and str(valor).strip() != ""


def _criterio_ok(c: dict[str, Any], contato: dict[str, Any], *, qualificado: bool, visita: bool) -> bool:
    campo, op, esperado = c.get("campo"), c.get("operador"), c.get("valor")
    if campo == COMPORTAMENTO:
        return qualificado
    if campo == VISITA:
        return visita
    if campo == OPERACAO:
        return contato.get("operacao") == esperado
    valor = _valor_do_campo(str(campo), contato)
    if op == "preenchido":
        return _preenchido(valor)
    n = _num(valor)
    if n is None:
        return False
    if op == ">=":
        return esperado is not None and n >= float(esperado)
    if op == "<=":
        return esperado is not None and n <= float(esperado)
    if op == "entre":
        return isinstance(esperado, (list, tuple)) and len(esperado) == 2 and float(esperado[0]) <= n <= float(esperado[1])
    return False


def avaliar(grupos: Any, contato: dict[str, Any], *, qualificado: bool = False, visita: bool = False) -> bool:
    """OR of groups, each an AND of criteria. An empty / malformed rule never matches."""
    if not isinstance(grupos, list):
        return False
    return any(
        isinstance(g, list) and g and all(
            isinstance(c, dict) and _criterio_ok(c, contato, qualificado=qualificado, visita=visita) for c in g
        )
        for g in grupos
    )


__all__ = [
    "CAMPOS_FIXOS", "COMPORTAMENTO", "MAX_CRITERIOS", "MAX_GRUPOS", "OPERACAO", "OPERACOES", "QUALIFICADO", "VISITA",
    "avaliar", "chaves_usadas", "usa_visita", "validar_grupos",
]
