"""Keeper: every WhatsApp send in a Lais module goes through `lais_envio_gate` (compliance by construction).

AST scan of `app/**/lais_*.py`: each call to a WhatsApp send (`send_text`, `enviar_template`, ...) must sit in a
function that references `lais_envio_gate` -- it calls `exigir` itself, or takes the `Liberacao` and `conferir`s it.
The only exceptions are listed in `FORA_DO_PORTAO`, one by one, with the reason (operator-initiated sends and the
transport implementation). A new sender that skips the gate fails here, and so does a stale exception.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
GATE = "lais_envio_gate"

#: Methods / functions that put a WhatsApp message on the wire.
ENVIOS = frozenset({
    "send_text", "send_text_sync", "send_text_to_phone", "send_text_to_phone_sync", "send_image", "send_file",
    "send_voice", "send_video", "send_template", "send_paragraphs", "enviar_texto", "enviar_template",
})

#: `(file relative to app/, function qualname) -> why it is not an automatic Julia send`.
FORA_DO_PORTAO: dict[tuple[str, str], str] = {
    ("services/lais_transporte.py", "WahaTransporte.enviar_texto"): "the transport itself -- callers are gated",
    ("services/lais_transporte.py", "CloudApiTransporte.enviar_texto"): "the transport itself -- callers are gated",
    ("services/lais_transporte.py", "CloudApiTransporte.enviar_template"): "the transport itself -- callers are gated",
    ("services/lais_disparos_service.py", "_enviar_um"): "operator-initiated disparo / owner request (POST endpoints), Cloud-only, opt-out + caps",
    ("services/lais_visitas_service.py", "avisar_lead"): "operator confirms / reschedules / cancels a visit in the UI",
}


def _chamadas_de_envio(arvore: ast.AST) -> list[tuple[str, int, bool]]:
    """`(qualname of the innermost function, line, that function references the gate)` per send call."""
    achados: list[tuple[str, int, bool]] = []

    def referencia_gate(fn: ast.AST) -> bool:
        return any(isinstance(n, ast.Name) and n.id == GATE for n in ast.walk(fn))

    def visitar(no: ast.AST, pilha: list[str], fn: ast.AST | None) -> None:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visitar(filho, [*pilha, filho.name], filho)
            elif isinstance(filho, ast.ClassDef):
                visitar(filho, [*pilha, filho.name], fn)
            else:
                if isinstance(filho, ast.Call):
                    f = filho.func
                    nome = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                    if nome in ENVIOS:
                        achados.append((".".join(pilha) or "<module>", filho.lineno, fn is not None and referencia_gate(fn)))
                visitar(filho, pilha, fn)

    visitar(arvore, [], None)
    return achados


def _varrer() -> tuple[list[str], set[tuple[str, str]]]:
    violacoes: list[str] = []
    usados: set[tuple[str, str]] = set()
    for path in sorted(APP.rglob("lais_*.py")):
        rel = path.relative_to(APP).as_posix()
        for qualname, linha, ok in _chamadas_de_envio(ast.parse(path.read_text(), filename=rel)):
            chave = (rel, qualname)
            if chave in FORA_DO_PORTAO:
                usados.add(chave)
            elif not ok:
                violacoes.append(f"{rel}:{linha} {qualname} sends without lais_envio_gate")
    return violacoes, usados


def test_every_lais_send_goes_through_the_gate():
    violacoes, _ = _varrer()
    assert violacoes == [], (
        "A Lais WhatsApp send bypasses the outbound gate. Call lais_envio_gate.exigir(...) in that function (or take "
        "the Liberacao and lais_envio_gate.conferir it); an operator-initiated send goes into FORA_DO_PORTAO with its "
        "reason:\n" + "\n".join(violacoes)
    )


def test_every_exception_still_matches_a_real_send():
    _, usados = _varrer()
    assert set(FORA_DO_PORTAO) - usados == set(), "stale FORA_DO_PORTAO entries -- remove them"


def test_the_scan_sees_the_gated_senders():
    """Non-vacuous: the scan reaches every automatic sender (a refactor that moves one must keep it scanned)."""
    vistos = set()
    for path in sorted(APP.rglob("lais_*.py")):
        rel = path.relative_to(APP).as_posix()
        vistos |= {(rel, q) for q, _, ok in _chamadas_de_envio(ast.parse(path.read_text())) if ok}
    for esperado in [
        ("services/lais_lead_turn_service.py", "LeadSender.send_reply"),
        ("services/lais_lead_turn_service.py", "_deliver"),
        ("services/lais_lead_turn_service.py", "_handle_deletion"),
        ("services/lais_reengajamento_service.py", "_enviar_template"),
        ("services/lais_disparos_service.py", "primeiro_contato_meta"),
        ("services/lais_avaliacoes_service.py", "enviador_padrao.enviar"),
    ]:
        assert esperado in vistos, esperado


class TestTheDetectorItself:
    def test_a_send_without_the_gate_is_caught(self):
        src = "async def novo_fluxo(t, tel):\n    await t.enviar_template(tel, 'x', [])\n"
        assert _chamadas_de_envio(ast.parse(src)) == [("novo_fluxo", 2, False)]

    def test_a_gate_in_an_outer_function_does_not_cover_a_nested_sender(self):
        src = (
            "def fabrica():\n    lais_envio_gate.exigir(1, 2, 3, 4)\n"
            "    async def enviar(w, c):\n        await w.send_text(c, 'oi')\n    return enviar\n"
        )
        assert _chamadas_de_envio(ast.parse(src)) == [("fabrica.enviar", 4, False)]

    def test_a_gated_send_passes(self):
        src = "async def f(w, lib, c):\n    lais_envio_gate.conferir(lib, c)\n    await w.send_text(c, 'oi')\n"
        assert _chamadas_de_envio(ast.parse(src)) == [("f", 3, True)]

    def test_a_bare_function_call_counts_too(self):
        src = "async def f(i, c):\n    await send_paragraphs(intake=i, sender=c, text='x')\n"
        assert _chamadas_de_envio(ast.parse(src)) == [("f", 2, False)]
