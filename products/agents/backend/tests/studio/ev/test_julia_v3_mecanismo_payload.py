"""The committed Julia v3 mechanism suite payload is valid for the one validator every store calls, is synthetic
(PII-free) and covers the behaviours the go-live needs (opt-out, politics, price-by-tool, hand-off, links)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.studio.eval_mecanismo import validar_caso_mecanismo

_ARQ = Path(__file__).resolve().parents[4] / "projects/julia-v2/content-v3/julia-v3-evals-mecanismo.json"
_CASOS = json.loads(_ARQ.read_text(encoding="utf-8"))["itens"]


@pytest.mark.parametrize("caso", _CASOS, ids=[c["slug"] for c in _CASOS])
def test_caso_valido(caso):
    validar_caso_mecanismo(
        k=caso["k"], roteiro=caso["roteiro"], asserts=caso["asserts"], titulo=caso["titulo"], entrada=caso["entrada"])


def test_cobre_os_comportamentos_de_go_live():
    slugs = {c["slug"] for c in _CASOS}
    assert {"mec-opt-out-parar", "mec-opt-out-linguagem-natural", "mec-sem-politica", "mec-preco-so-por-ferramenta",
            "mec-handoff-pedido-humano", "mec-link-so-o-da-org"} <= slugs
    assert len(slugs) == len(_CASOS)


def test_textos_obrigatorios_do_go_live_estao_no_payload():
    textos = {i["chave"]: i["conteudo"] for i in json.loads(
        (_ARQ.parent / "julia-v3-textos.json").read_text(encoding="utf-8"))["itens"]}
    assert textos["runtime.confirmacao_opt_out"].strip()
    assert textos["conformidade.correcao.valor_sem_ferramenta"].strip()
