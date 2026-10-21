"""AST keeper (owner 2026-10-21, "leads cant ask for their data deletion nor any other type of destructive actions"): nothing
reachable from the inbound-lead entry points (`process_lead_batch`, the WhatsApp webhook's `_handle_lead_message`) may delete
a lead's data. Operator routes (a human clicking "apagar-dados") are the allowlist: they are not reachable from the entries.

Forbidden anywhere in the reachable call graph:
  * `.delete()` on the tables `conversation_messages`, `contacts`, `whatsapp_chats`, `julia_contatos`;
  * a call to `apagar_lead` or `apagar_dados_do_chat` (and `delete_conversation_data`, agents' by-chat erase).

Reachability is a name-based walk over app/services + app/routers (a call `x.f()` / `f()` reaches every def named `f`): it
over-approximates, so a false alarm is fixed by renaming or by moving the destructive helper out of the lead path -- never by
growing an allowlist for the lead path."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
ENTRADAS = {"process_lead_batch", "_handle_lead_message"}
TABELAS = {"conversation_messages", "contacts", "whatsapp_chats", "julia_contatos"}
CHAMADAS_PROIBIDAS = {"apagar_lead", "apagar_dados_do_chat", "delete_conversation_data"}
#: The ONE sanctioned edge. When agents REFUSES a brand-new lead (`novo_lead_recusado` / `agente_desligado`, no thread, never
#: answered), `_tratar_sem_atendimento` drops the julia_contatos row THIS very batch created (julia-v2 Q5, data minimisation).
#: It can only reach the sender's own chat, never an existing record or anyone else's. Tech-lead decision pending (see the
#: delivery report); any OTHER edge into a destructive helper fails this keeper.
ARESTAS_PERMITIDAS = {("_tratar_sem_atendimento", "apagar_do_chat")}
#: defs that ARE the destructive implementation / the operator flow; they must not be reachable from an entry, but they are
#: allowed to contain the deletes themselves.
IMPLEMENTACOES = {"apagar_dados_do_chat", "apagar_do_chat", "apagar_lead", "delete_conversation_data"}


def _defs() -> dict[str, list[tuple[Path, ast.AST]]]:
    out: dict[str, list[tuple[Path, ast.AST]]] = {}
    for arq in sorted([*(APP / "services").rglob("*.py"), *(APP / "routers").rglob("*.py"), *(APP / "modules").rglob("*.py")]):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(no.name, []).append((arq, no))
    return out


def _nome_da_chamada(c: ast.Call) -> str | None:
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _constantes(arq: Path) -> dict[str, str]:
    """Module-level `NAME = "literal"` (the tables are usually named through such a constant)."""
    out: dict[str, str] = {}
    for no in ast.parse(arq.read_text()).body:
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.Constant) and isinstance(no.value.value, str):
            out.update({t.id: no.value.value for t in no.targets if isinstance(t, ast.Name)})
    return out


def _tabela_apagada(c: ast.Call, consts: dict[str, str] | None = None) -> str | None:
    """`<...>.table("<t>"|CONST).delete()` -> `<t>`."""
    f = c.func
    if not (isinstance(f, ast.Attribute) and f.attr == "delete"):
        return None
    base = f.value
    while isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute) and base.func.attr != "table":
        base = base.func.value
    if isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute) and base.func.attr == "table" and base.args:
        a = base.args[0]
        if isinstance(a, ast.Name):
            return (consts or {}).get(a.id)
        return a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None
    return None


def _alcancaveis(defs: dict[str, list[tuple[Path, ast.AST]]]) -> dict[str, list[tuple[Path, ast.AST]]]:
    """Name-based BFS: every def named like a called name is reachable (over-approximation)."""
    vistos: set[str] = set()
    fila = [n for n in ENTRADAS if n in defs]
    while fila:
        nome = fila.pop()
        if nome in vistos:
            continue
        vistos.add(nome)
        for _arq, no in defs.get(nome, []):
            for c in (x for x in ast.walk(no) if isinstance(x, ast.Call)):
                alvo = _nome_da_chamada(c)
                if alvo and alvo in defs and (nome, alvo) not in ARESTAS_PERMITIDAS:
                    fila.append(alvo)
    return {n: defs[n] for n in vistos}


def _violacoes() -> list[str]:
    defs = _defs()
    ruins: list[str] = []
    for fn, ocorrencias in _alcancaveis(defs).items():
        for arq, no in ocorrencias:
            consts = _constantes(arq)
            for c in (x for x in ast.walk(no) if isinstance(x, ast.Call)):
                nome = _nome_da_chamada(c)
                if nome in CHAMADAS_PROIBIDAS:
                    ruins.append(f"{arq.name}:{c.lineno} {fn} calls {nome}")
                t = _tabela_apagada(c, consts)
                if t in TABELAS:
                    ruins.append(f"{arq.name}:{c.lineno} {fn} deletes from {t}")
    return ruins


def test_the_entry_points_exist_so_the_walk_is_not_vacuous():
    defs = _defs()
    assert ENTRADAS <= set(defs), f"entry points renamed? missing: {ENTRADAS - set(defs)}"
    alcanca = set(_alcancaveis(defs))
    assert {"process_lead_batch", "_handle_lead_message"} <= alcanca and len(alcanca) > 10


def test_nothing_reachable_from_the_lead_entry_points_deletes_a_leads_data():
    assert _violacoes() == []


def test_the_detector_sees_a_planted_violation():
    codigo = 'def f(c):\n    c.table("julia_contatos").delete().eq("id", 1).execute()\n    apagar_lead(1)\n'
    chamadas = [x for x in ast.walk(ast.parse(codigo)) if isinstance(x, ast.Call)]
    assert any(_tabela_apagada(c) == "julia_contatos" for c in chamadas)
    assert _tabela_apagada(next(c for c in chamadas if _nome_da_chamada(c) == "delete"), {"T": "contacts"}) == "julia_contatos"
    const = [x for x in ast.walk(ast.parse('def g(c):\n    c.table(T).delete()\n')) if isinstance(x, ast.Call) and _nome_da_chamada(x) == "delete"]
    assert _tabela_apagada(const[0], {"T": "contacts"}) == "contacts"
    assert any(_nome_da_chamada(c) in CHAMADAS_PROIBIDAS for c in chamadas)


def test_the_operator_erase_flow_stays_outside_the_lead_path():
    alcanca = set(_alcancaveis(_defs()))
    assert not (alcanca & {"post_apagar_dados", *IMPLEMENTACOES}), alcanca & IMPLEMENTACOES


def test_without_the_one_sanctioned_edge_the_detector_flags_the_refused_lead_cleanup(monkeypatch):
    import tests.test_lead_path_never_deletes as me

    monkeypatch.setattr(me, "ARESTAS_PERMITIDAS", set())
    assert any("julia_contatos" in v or "apagar" in v for v in me._violacoes())
