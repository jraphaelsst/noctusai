"""Guarda estrutural: vocabulário de provedor não escapa do adapter.

A produção vai ser **Banco do Brasil**; o Asaas é a casca que destrava o ERP
agora. O que decide se a migração é "escrever outro adapter" ou "reescrever o
financeiro" é uma coisa só: `billingType`, `externalReference`,
`PAYMENT_RECEIVED` e `access_token` aparecerem apenas em
`app/providers/asaas.py`.

Isso é fácil de combinar e fácil de esquecer numa segunda-feira. Então é
teste, não convenção — o mesmo raciocínio do guard de rotas em
`tests/test_main.py`.
"""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# Termos do dialeto Asaas. Se algum aparecer fora do adapter, o seam furou.
DIALETO = re.compile(
    r"\b(billingType|externalReference|cpfCnpj|invoiceUrl|"
    r"identificationField|PAYMENT_[A-Z_]+|access_token)\b"
)

# O adapter pode falar o dialeto — é o trabalho dele.
ISENTOS = {"app/providers/asaas.py"}


def _arquivos_do_app() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in str(p))


def _linhas_de_docstring(fonte: str) -> set[int]:
    """Linhas ocupadas por docstrings de módulo, classe e função."""
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:  # pragma: no cover
        return set()

    linhas: set[int] = set()
    alvos = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for no in ast.walk(arvore):
        if not isinstance(no, alvos):
            continue
        corpo = getattr(no, "body", None)
        if not corpo:
            continue
        primeiro = corpo[0]
        if (
            isinstance(primeiro, ast.Expr)
            and isinstance(primeiro.value, ast.Constant)
            and isinstance(primeiro.value.value, str)
        ):
            fim = primeiro.end_lineno or primeiro.lineno
            linhas.update(range(primeiro.lineno, fim + 1))
    return linhas


def _linhas_de_codigo(caminho: Path) -> list[tuple[int, str]]:
    """Linhas de código, sem docstring e sem comentário.

    Duas tentativas anteriores erraram, e por motivos opostos — vale registrar
    porque a segunda passou despercebida:

    1. Fatiar no `#` deixava as docstrings passarem, e as docstrings que
       *documentam* esta regra citam os termos proibidos. Falso positivo.
    2. Usar `tokenize` e descartar todo token STRING deixava o guard **vazio**:
       os termos aparecem no código justamente como literais
       (`dados.get("externalReference")`), então descartar strings descartava
       exatamente o que era para detectar. Falso negativo — e só apareceu
       porque injetamos um vazamento de propósito para conferir.

    A distinção correta é entre *docstring* (prosa, ignora) e *literal de
    string em expressão* (código, verifica). É o que o `ast` sabe fazer.
    """
    fonte = caminho.read_text(encoding="utf-8")
    ignoradas = _linhas_de_docstring(fonte)

    linhas = []
    for numero, linha in enumerate(fonte.splitlines(), 1):
        if numero in ignoradas:
            continue
        sem_comentario = linha.split("#", 1)[0]
        if sem_comentario.strip():
            linhas.append((numero, sem_comentario))
    return linhas


def test_dialeto_do_provedor_nao_vaza_para_o_app():
    vazamentos = []
    for caminho in _arquivos_do_app():
        relativo = caminho.relative_to(APP.parent).as_posix()
        if relativo in ISENTOS:
            continue
        for numero, linha in _linhas_de_codigo(caminho):
            achado = DIALETO.search(linha)
            if achado:
                vazamentos.append(f"{relativo}:{numero} → {achado.group()}")

    assert not vazamentos, (
        "vocabulário de provedor fora do adapter:\n  "
        + "\n  ".join(vazamentos)
        + "\n\nTraduza no adapter e use o léxico de app/providers/tipos.py."
    )


def test_services_e_routers_nao_importam_o_adapter_direto():
    """Quem depende do adapter concreto não pode trocar de provedor."""
    culpados = []
    for caminho in _arquivos_do_app():
        relativo = caminho.relative_to(APP.parent).as_posix()
        if relativo.startswith("app/providers/"):
            continue
        texto = caminho.read_text(encoding="utf-8")
        if "providers.asaas" in texto or "from app.providers import asaas" in texto:
            culpados.append(relativo)

    assert not culpados, (
        f"importam o adapter concreto: {culpados}. "
        "Dependa do Protocol ProvedorCobranca e resolva por Depends."
    )


def test_app_continua_sem_async():
    """O backend inteiro é sync `def`; o provedor usa httpx.Client.

    Um `async def` solto obrigaria FastAPI a rodá-lo no event loop enquanto
    todo o resto está no threadpool — e a primeira chamada bloqueante ali
    trava o processo inteiro.
    """
    assincronos = []
    for caminho in _arquivos_do_app():
        for numero, linha in _linhas_de_codigo(caminho):
            if re.search(r"\basync\s+def\b", linha):
                assincronos.append(f"{caminho.relative_to(APP.parent).as_posix()}:{numero}")

    assert not assincronos, f"async def encontrado: {assincronos}"
