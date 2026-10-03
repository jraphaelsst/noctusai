"""Golden-text snapshots of the rendered contract for the 6 synthetic variants
(`contrato_gerador_fixtures.variante(1..6)`, spec §1.3).

WHY. The real-contract scorecard (`tests/e2e_contrato/comparador.pontuar`,
`noctus.dev.contract_score`) measures the generator against signed contracts,
which live only on the owner's private disk — CI can never see them. These
goldens are the CI-side half: the FULL normalised rendered text of every
variant is checked in, so any wording change to the template / phrase bank /
context builder shows up as a reviewed diff of `golden/contrato_v<N>.txt`
instead of passing silently behind a `%PDF-` header check.

Everything rendered here is synthetic (the fixtures' own guarantee) — safe to
commit.

REGENERATE (after a DELIBERATE wording change, then review the diff):

    CONTRATO_GOLDEN_REGENERAR=1 <repo>/venv/bin/python -m pytest \\
        tests/modules/card_hub/test_contrato_golden.py

The regenerate run rewrites the files and FAILS on purpose (so a CI run with
the flag set can never go green by rewriting its own expectation); re-run
without the flag to confirm.
"""
from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento
from tests.modules.card_hub import contrato_gerador_fixtures as fx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "e2e_contrato"))
import comparador  # noqa: E402  (path insert must precede this)

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
ENV_REGENERAR = "CONTRATO_GOLDEN_REGENERAR"
VARIANTES = (1, 2, 3, 4, 5, 6)


def texto_normalizado(n: int) -> str:
    """The variant's full rendered text, one non-empty whitespace-normalised
    paragraph per line — the same normalisation the scorecard compares
    (`comparador.paragrafos_de_lista`). Every date input is pinned
    (`fx.ASSINATURA` / `fx.REFERENCIA`), so the text is identical on any day."""
    d = fx.variante(n)
    politica = fx.politica_variante(n)
    switches = derivacao.derivar_switches(d, politica, fx.REFERENCIA)
    avaliacao = derivacao.avaliar(d, switches, politica, fx.ASSINATURA, fx.REFERENCIA)
    assert avaliacao.pronto, (avaliacao.faltando, avaliacao.bloqueios)
    renderizado = documento.renderizar(
        get_docx_render_adapter(real=True), d, switches, politica, fx.ASSINATURA, fx.REFERENCIA
    )
    return "\n".join(comparador.paragrafos_de_lista(renderizado.paragrafos)) + "\n"


def _caminho(n: int) -> Path:
    return GOLDEN_DIR / f"contrato_v{n}.txt"


@pytest.mark.parametrize("n", VARIANTES)
def test_texto_renderizado_confere_com_golden(n: int):
    atual = texto_normalizado(n)
    caminho = _caminho(n)
    if os.environ.get(ENV_REGENERAR) == "1":
        GOLDEN_DIR.mkdir(exist_ok=True)
        caminho.write_text(atual, encoding="utf-8")
        pytest.fail(f"{caminho.name} regenerado — revise o diff e rode de novo sem {ENV_REGENERAR}")
    if not caminho.is_file():
        pytest.fail(f"{caminho.name} ausente — gere com {ENV_REGENERAR}=1 e revise o arquivo")
    esperado = caminho.read_text(encoding="utf-8")
    if atual != esperado:
        diff = "".join(
            difflib.unified_diff(
                esperado.splitlines(keepends=True),
                atual.splitlines(keepends=True),
                fromfile=f"golden/{caminho.name}",
                tofile="renderizado",
                n=1,
            )
        )
        linhas = diff.splitlines()
        corte = "\n".join(linhas[:120]) + ("\n... (diff truncado)" if len(linhas) > 120 else "")
        pytest.fail(
            f"O texto renderizado da variante {n} mudou. Se a mudança é deliberada, "
            f"regenere com {ENV_REGENERAR}=1 e revise o diff:\n{corte}"
        )


@pytest.mark.parametrize("n", VARIANTES)
def test_golden_pontua_aprovado_contra_si_mesmo(n: int):
    """The scorecard's own sanity bar on a real-shaped instrument: a render
    scored against its own golden is `aprovado` with zero number diffs —
    proves the sectioner/number extractor handle the generator's actual
    shape (clause headings, certidão items, closing block), not just the
    hand-written pairs in `test_comparador_offline.py`."""
    caminho = _caminho(n)
    if not caminho.is_file():
        pytest.skip(f"{caminho.name} ausente (test_texto_renderizado_confere_com_golden já falha)")
    golden = caminho.read_text(encoding="utf-8").splitlines()
    card = comparador.pontuar(golden, texto_normalizado(n).splitlines())
    assert card.veredito == "aprovado", card.motivos()
    assert card.secoes_ref > 10  # the instrument really was cut into clauses
    assert card.categorias["certidoes"] == 1.0
    assert card.categorias["matricula"] == 1.0
