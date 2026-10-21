"""B10 keeper (GUARDRAILS B10): the Julia / media modules never log message text, transcripts, descriptions or raw exception strings,
and never log a LID or a chat id un-hashed. A static AST scan -- every `logger.<level>(...)` call in the listed modules (and the listed
Julia functions of the two WhatsApp routers) is checked:

  * no `logger.exception(...)` and no `exc_info=...` (a traceback prints the exception string, which for an HTTP / DB error carries the
    URL, the row or the text);
  * no argument that is the caught exception itself (`exc`, `e`, `str(exc)`, an f-string of it) -- only `type(exc).__name__` or a code;
  * no argument named like content: text / texto / body / transcript / legenda / descricao / resumo / `.text` / `.texto` / `.body`;
  * no argument named like an identifier of the lead: lid / sender / phone / telefone / chat_id / chat -- log `protecao.ref(x)` (a 10-hex
    SHA-256 prefix) instead.

A line that has a vetted reason carries `# log-ok: <why>`. The scan is derived (a new Julia module is added to MODULES by the test below,
which fails when a `julia_*` / media service exists that is not listed)."""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: DERIVED: every `services/julia_*.py` (a new Julia module is scanned the day it is added) plus the media path.
EXTRA = ("services/media_service.py", "services/identidade_mascara.py", "services/message_store.py")
MODULES = tuple(sorted(f"services/{p.name}" for p in (APP / "services").glob("julia_*.py"))) + EXTRA
#: (file, function) pairs: the Julia functions inside the two big WhatsApp routers
ROUTER_FUNCS = {
    "routers/whatsapp_router.py": {
        "_handle_lead_message", "_triar_remetente", "_resolver_midia_do_lead", "_staff_na_linha", "_avisar_staff_na_linha_publica",
        "_apply_human_takeover",
    },
    "routers/whatsapp_connections_router.py": {"_encaminhar_humano_ao_agente"},
}
LEVELS = {"debug", "info", "warning", "error", "critical", "exception", "log"}
CONTENT = {"text", "texto", "body", "message_body", "transcript", "transcricao", "legenda", "descricao", "resumo", "texto_extraido", "conteudo"}
IDENT = {"lid", "sender", "phone", "telefone", "chat_id", "chat", "numero", "raw_sender"}


def _is_logger_call(node: ast.Call) -> bool:
    f = node.func
    return isinstance(f, ast.Attribute) and f.attr in LEVELS and isinstance(f.value, ast.Name) and f.value.id in {"logger", "log", "_log"}


def _names(node: ast.AST) -> list[tuple[str, ast.AST]]:
    """Every Name / Attribute leaf under `node` that is NOT inside a `type(...)` / `ref(...)` / `len(...)` wrapper."""
    out: list[tuple[str, ast.AST]] = []

    def walk(n: ast.AST) -> None:
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute)):
            fname = n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            if fname in {"type", "ref", "ref_log", "len", "bool", "id"}:
                return  # a vetted reducer: only the type name / a hash / a count leaves
        if isinstance(n, ast.Name):
            out.append((n.id, n))
        elif isinstance(n, ast.Attribute):
            out.append((n.attr, n))
        for c in ast.iter_child_nodes(n):
            walk(c)

    walk(node)
    return out


def _scan(path: Path, only_funcs: set[str] | None = None) -> list[str]:
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    findings: list[str] = []

    def visit(fn: ast.AST, caught: set[str]) -> None:
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call) and _is_logger_call(n)):
                continue
            if "log-ok:" in lines[n.lineno - 1] or any("log-ok:" in lines[i] for i in range(n.lineno - 1, min(n.end_lineno or n.lineno, len(lines)))):
                continue
            where = f"{path.name}:{n.lineno}"
            if n.func.attr == "exception":
                findings.append(f"{where} logger.exception prints the exception string")
            if any(k.arg == "exc_info" for k in n.keywords):
                findings.append(f"{where} exc_info prints the exception string")
            for a in [*n.args[1:], *(k.value for k in n.keywords if k.arg != "exc_info")]:
                for name, _node in _names(a):
                    if name in caught:
                        findings.append(f"{where} logs the exception object `{name}` (use type({name}).__name__)")
                    if name in CONTENT:
                        findings.append(f"{where} logs content-like `{name}`")
                    if name in IDENT:
                        findings.append(f"{where} logs an identifier `{name}` un-hashed (use ref(...))")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if only_funcs is not None and node.name not in only_funcs:
                continue
            caught = {h.name for h in ast.walk(node) if isinstance(h, ast.ExceptHandler) and h.name}
            visit(node, caught)
    # module-level logger calls (rare) are not scanned: there are none in these modules by construction
    return sorted(set(findings))


def test_the_julia_and_media_modules_log_no_content_no_raw_exceptions_no_bare_identifiers():
    findings: list[str] = []
    for rel in MODULES:
        findings += _scan(APP / rel)
    for rel, funcs in ROUTER_FUNCS.items():
        findings += _scan(APP / rel, funcs)
    assert not findings, "B10 log hygiene:\n  " + "\n  ".join(findings)


def test_every_julia_service_is_covered_by_the_scan():
    listed = {Path(m).name for m in MODULES}
    assert {p.name for p in (APP / "services").glob("julia_*.py")} <= listed
    assert {"julia_lead_turn_service.py", "julia_protecao_service.py", "julia_staff_service.py", "media_service.py"} <= listed
    assert all((APP / m).exists() for m in MODULES)


def test_the_scan_itself_catches_the_shapes_it_claims_to(tmp_path):
    bad = tmp_path / "m.py"
    bad.write_text(
        "import logging\nlogger = logging.getLogger(__name__)\n"
        "def f(texto, lid, chat_id):\n"
        "    try:\n        pass\n    except Exception as exc:\n"
        "        logger.exception('x')\n        logger.error('a %s', exc)\n        logger.error('b %s', texto)\n"
        "        logger.info('c %s', lid)\n        logger.info('d %s', chat_id, exc_info=True)\n"
        "        logger.info('ok %s', type(exc).__name__)\n        logger.info('ok2 %s', ref(lid))\n"
        "        logger.info('vetted %s', lid)  # log-ok: test\n"
    )
    f = _scan(bad)
    assert len(f) == 6 and not any(":13" in x or ":14" in x or ":15" in x for x in f), f
