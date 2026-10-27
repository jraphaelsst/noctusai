"""Keeper: every WhatsApp send in Julia code goes through `julia_envio_gate` (compliance by construction).

What it scans (derived, not listed): every `app/**/julia_*.py` PLUS every app module that imports a `julia_*` service
(the Julia dispatch lives in `conversation_module` / `whatsapp_router`, outside the `julia_` names) PLUS every file of
the block-agent modules (`AGENT_MODULES`: maya-blocks `atendimento_blocos` + `supervisao`) -- a block agent added
there is in scope from its first line, whether or not it imports a Julia service.

What counts as a send (derived, not listed): every `send*` method of the seed WhatsApp clients (`WahaClient`,
`MetaCloudClient`), every `enviar*` member of the `Transporte` Protocol, every `send*` method of the intake seam
(`WhatsAppIntakeService`) and every `send*` function of `whatsapp_outbound` -- minus `NAO_ENVIOS` (read receipts),
each of which must still exist. A new client method named `send_media` is covered the day it lands.

The rule: the innermost function around a send must CALL `julia_envio_gate.exigir` or `julia_envio_gate.conferir`
-- merely naming the module (`julia_envio_gate.Fluxo`, `except julia_envio_gate.EnvioBloqueado`) does not count.
The only exceptions are `FORA_DO_PORTAO`, one by one with the reason; a stale exception fails too.
A `Liberacao` is sealed by the gate module (`_SELO`): nothing outside it may reference the seal.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from noctusai_lib.integrations.whatsapp.client import WahaClient
from noctusai_lib.integrations.whatsapp.meta_cloud_client import MetaCloudClient

from app.services import julia_transporte, whatsapp_outbound
from app.services.whatsapp_intake_service import WhatsAppIntakeService

APP = Path(__file__).resolve().parents[2] / "app"
#: Packages whose every file is scanned (block agents live here, maya-blocks CONTRACT §1).
AGENT_MODULES: tuple[str, ...] = ("modules/atendimento_blocos/", "modules/supervisao/")
GATE = "julia_envio_gate"
GATE_FILE = "services/julia_envio_gate.py"
CHAMADAS_DO_PORTAO = frozenset({"exigir", "conferir"})

#: Client methods that are NOT a message to a person (a read receipt). Each must exist on a client.
NAO_ENVIOS = frozenset({"send_seen"})


def _envios() -> frozenset[str]:
    nomes = {m for c in (WahaClient, MetaCloudClient, WhatsAppIntakeService) for m in dir(c) if m.startswith("send")}
    nomes |= {m for m in dir(julia_transporte.Transporte) if m.startswith("enviar")}
    nomes |= {n for n, f in inspect.getmembers(whatsapp_outbound, inspect.isfunction) if n.startswith("send")}
    return frozenset(nomes - NAO_ENVIOS)


ENVIOS = _envios()

#: `(file relative to app/, function qualname) -> why it is not an automatic Julia send`.
FORA_DO_PORTAO: dict[tuple[str, str], str] = {
    # the transport implementations -- every caller is gated
    ("services/julia_transporte.py", "WahaTransporte.enviar_texto"): "transport implementation -- callers are gated",
    ("services/julia_transporte.py", "CloudApiTransporte.enviar_texto"): "transport implementation -- callers are gated",
    ("services/julia_transporte.py", "CloudApiTransporte.enviar_template"): "transport implementation -- callers are gated",
    # operator-initiated (a person clicks in the UI)
    ("services/julia_disparos_service.py", "_enviar_um"): "operator-initiated disparo / owner request (POST endpoints), Cloud-only, opt-out + caps",
    ("services/julia_visitas_service.py", "avisar_lead"): "operator confirms / reschedules / cancels a visit in the UI",
    ("routers/whatsapp_connections_router.py", "send_message"): "operator types a message in Conversas (POST endpoint)",
    # the OPERATOR bot (pre-Julia intake + chatbot). Not a Julia send: reached only after the Julia split
    # (`agente_leads_ativo` on -> leads go to Julia and return). It answers `authorized_numbers` only -- an EMPTY list
    # authorizes nobody (owner order 2026-10-20), so a lead line never reaches it.
    ("routers/whatsapp_router.py", "_process_waha_body"): "operator bot: once-per-24h denial reply + inline chatbot fallback",
    ("services/conversation_module.py", "_llm_fallback_dispatch_inner"): "operator bot LLM fallback",
    ("services/conversation_module.py", "route_inbound"): "operator bot code-first router: typed YouTube command replies",
}


def _imports_julia(arvore: ast.AST) -> bool:
    for n in ast.walk(arvore):
        if isinstance(n, ast.ImportFrom) and n.module:
            if n.module.startswith("app.services.julia_") or (
                n.module == "app.services" and any(a.name.startswith("julia_") for a in n.names)
            ):
                return True
        if isinstance(n, ast.Import) and any(a.name.startswith("app.services.julia_") for a in n.names):
            return True
    return False


def _chama_o_portao(fn: ast.AST) -> bool:
    """`julia_envio_gate.exigir(...)` / `julia_envio_gate.conferir(...)` called inside `fn` (its own body only)."""
    for n in _corpo_proprio(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in CHAMADAS_DO_PORTAO:
            alvo = n.func.value
            if isinstance(alvo, ast.Name) and alvo.id == GATE:
                return True
    return False


def _corpo_proprio(fn: ast.AST):
    """Every node of `fn` except those inside nested functions / classes (judged on their own)."""
    pilha = list(ast.iter_child_nodes(fn))
    while pilha:
        n = pilha.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield n
        pilha.extend(ast.iter_child_nodes(n))


def _chamadas_de_envio(arvore: ast.AST, envios: frozenset[str] = ENVIOS) -> list[tuple[str, int, bool]]:
    """`(qualname of the innermost function, line, that function calls the gate)` per send call."""
    achados: list[tuple[str, int, bool]] = []

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
                    if nome in envios:
                        achados.append((".".join(pilha) or "<module>", filho.lineno, fn is not None and _chama_o_portao(fn)))
                visitar(filho, pilha, fn)

    visitar(arvore, [], None)
    return achados


def _arquivos() -> list[tuple[str, ast.AST]]:
    out = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        arvore = ast.parse(path.read_text(), filename=rel)
        if path.name.startswith("julia_") or rel.startswith(AGENT_MODULES) or _imports_julia(arvore):
            out.append((rel, arvore))
    return out


def _varrer() -> tuple[list[str], set[tuple[str, str]]]:
    violacoes: list[str] = []
    usados: set[tuple[str, str]] = set()
    for rel, arvore in _arquivos():
        for qualname, linha, ok in _chamadas_de_envio(arvore):
            chave = (rel, qualname)
            if chave in FORA_DO_PORTAO:
                usados.add(chave)
            elif not ok:
                violacoes.append(f"{rel}:{linha} {qualname}")
    return violacoes, usados


def test_every_julia_send_goes_through_the_gate():
    violacoes, _ = _varrer()
    assert violacoes == [], (
        "A WhatsApp send in Julia code does not call the outbound gate. Call julia_envio_gate.exigir(...) in that "
        "function (or take the Liberacao and call julia_envio_gate.conferir on it); an operator-initiated send goes "
        "into FORA_DO_PORTAO with its reason:\n" + "\n".join(violacoes)
    )


def test_every_exception_still_matches_a_real_send():
    _, usados = _varrer()
    assert set(FORA_DO_PORTAO) - usados == set(), "stale FORA_DO_PORTAO entries -- remove them"


def test_the_send_vocabulary_is_derived_and_its_exclusions_are_real():
    assert {"send_text", "send_text_to_phone", "send_template", "send_reply", "send_paragraphs",
            "enviar_texto", "enviar_template"} <= ENVIOS
    clientes = {m for c in (WahaClient, MetaCloudClient) for m in dir(c)}
    assert NAO_ENVIOS <= clientes, "stale NAO_ENVIOS entry"


def test_the_scan_reaches_the_julia_dispatch_outside_the_julia_names():
    arquivos = {rel for rel, _ in _arquivos()}
    assert {"services/conversation_module.py", "routers/whatsapp_router.py"} <= arquivos


def test_the_scan_reaches_every_block_agent_module_file():
    """Non-vacuous: every file of `modules/atendimento_blocos/` is scanned (supervisao joins the day it exists)."""
    arquivos = {rel for rel, _ in _arquivos()}
    blocos = {p.relative_to(APP).as_posix() for p in (APP / "modules" / "atendimento_blocos").rglob("*.py")}
    assert blocos and blocos <= arquivos
    supervisao = APP / "modules" / "supervisao"
    if supervisao.is_dir():
        assert {p.relative_to(APP).as_posix() for p in supervisao.rglob("*.py")} <= arquivos


def test_the_scan_sees_the_gated_senders():
    """Non-vacuous: the scan reaches every automatic sender (a refactor that moves one must keep it scanned)."""
    vistos = {(rel, q) for rel, a in _arquivos() for q, _, ok in _chamadas_de_envio(a) if ok}
    for esperado in [
        ("services/julia_lead_turn_service.py", "LeadSender.send_reply"),
        ("services/julia_lead_turn_service.py", "_deliver"),
        ("services/julia_reengajamento_service.py", "_enviar_template"),
        ("services/julia_disparos_service.py", "primeiro_contato_meta"),
        ("services/julia_avaliacoes_service.py", "enviador_padrao.enviar"),
    ]:
        assert esperado in vistos, esperado


#: Direct sends to a LEAD (no agents turn in between: a turn is refused by agents itself with `lead_opt_out`). Each
#: must consult agents' opt-out before sending (owner decision 2026-10-21). `(file, function) -> calls it must contain`.
ENVIOS_A_LEAD_COM_OPT_OUT: dict[tuple[str, str], frozenset[str]] = {
    ("services/julia_reengajamento_service.py", "executar_default"): frozenset({"_bloqueio_opt_out"}),
    ("services/julia_reengajamento_service.py", "executar_tentativa"): frozenset({"_bloqueio_opt_out"}),
    ("services/julia_reengajamento_service.py", "_bloqueio_opt_out"): frozenset({"exigir_sem_opt_out"}),
    ("services/julia_disparos_service.py", "primeiro_contato_meta"): frozenset({"exigir_sem_opt_out"}),
    ("services/julia_disparos_service.py", "_enviar_um"): frozenset({"motivo_opt_out"}),
    ("services/julia_avaliacoes_service.py", "executar_pedido"): frozenset({"exigir_sem_opt_out"}),
    ("services/julia_visitas_service.py", "avisar_lead"): frozenset({"motivo_opt_out"}),
}


def test_every_direct_send_to_a_lead_consults_the_opt_out():
    achados: dict[tuple[str, str], set[str]] = {}
    for rel, arvore in _arquivos():
        for fn in ast.walk(arvore):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and (rel, fn.name) in ENVIOS_A_LEAD_COM_OPT_OUT:
                achados[(rel, fn.name)] = {
                    n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
                    for n in _corpo_proprio(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, (ast.Attribute, ast.Name))
                }
    assert set(achados) == set(ENVIOS_A_LEAD_COM_OPT_OUT), "a listed lead sender no longer exists -- update the list"
    faltando = {k: sorted(v - achados[k]) for k, v in ENVIOS_A_LEAD_COM_OPT_OUT.items() if v - achados[k]}
    assert faltando == {}, f"a direct lead send lost its opt-out check: {faltando}"


def test_the_seal_is_used_only_by_the_gate_module():
    fora = [
        f"{rel}:{n.lineno}"
        for rel, arvore in _arquivos() if rel != GATE_FILE
        for n in ast.walk(arvore)
        if (isinstance(n, ast.Attribute) and n.attr == "_SELO") or (isinstance(n, ast.Name) and n.id == "_SELO")
    ]
    assert fora == [], fora


class TestTheDetectorItself:
    def test_a_send_without_the_gate_is_caught(self):
        src = "async def novo_fluxo(t, tel):\n    await t.enviar_template(tel, 'x', [])\n"
        assert _chamadas_de_envio(ast.parse(src)) == [("novo_fluxo", 2, False)]

    def test_only_naming_the_gate_module_is_not_a_gate(self):
        src = (
            "async def f(w, c):\n    fluxo = julia_envio_gate.Fluxo.RESPOSTA\n"
            "    try:\n        await w.send_text(c, 'oi')\n    except julia_envio_gate.EnvioBloqueado:\n        pass\n"
        )
        assert _chamadas_de_envio(ast.parse(src)) == [("f", 4, False)]

    def test_a_gate_in_an_outer_function_does_not_cover_a_nested_sender(self):
        src = (
            "def fabrica():\n    julia_envio_gate.exigir(1, 2, 3, 4)\n"
            "    async def enviar(w, c):\n        await w.send_text(c, 'oi')\n    return enviar\n"
        )
        assert _chamadas_de_envio(ast.parse(src)) == [("fabrica.enviar", 4, False)]

    def test_a_gate_call_inside_a_nested_function_does_not_cover_the_outer_send(self):
        src = (
            "async def f(w, c):\n    def g():\n        julia_envio_gate.exigir(1, 2, 3, 4)\n"
            "    await w.send_text(c, 'oi')\n"
        )
        assert _chamadas_de_envio(ast.parse(src)) == [("f", 4, False)]

    def test_a_gated_send_passes(self):
        src = "async def f(w, lib, c):\n    julia_envio_gate.conferir(lib, c)\n    await w.send_text(c, 'oi')\n"
        assert _chamadas_de_envio(ast.parse(src)) == [("f", 3, True)]

    def test_a_bare_function_call_counts_too(self):
        src = "async def f(i, c):\n    await send_paragraphs(intake=i, sender=c, text='x')\n"
        assert _chamadas_de_envio(ast.parse(src)) == [("f", 2, False)]

    def test_a_new_client_send_name_is_covered_once_it_exists_on_a_client(self):
        src = "async def f(w, c):\n    await w.send_media(c, b'x')\n"
        assert _chamadas_de_envio(ast.parse(src), ENVIOS | {"send_media"}) == [("f", 2, False)]

    def test_a_module_that_imports_a_julia_service_is_in_scope(self):
        assert _imports_julia(ast.parse("from app.services import julia_agente_service as julia\n"))
        assert _imports_julia(ast.parse("def f():\n    from app.services.julia_lead_turn_service import LeadDeps\n"))
        assert not _imports_julia(ast.parse("from app.services import whatsapp_outbound\n"))
