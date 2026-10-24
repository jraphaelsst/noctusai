"""The FE's specification catalogue is GENERATED from `especificacoes.CATALOGO`.

`frontend/src/lib/especificacoesCatalogo.json` is the only copy of the
catalogue the SPA reads (keys, labels, eixos, `requer`, `exclusiva_com`) —
the picker enforces `requer`/`exclusiva_com` in the UI, so a drift between the
two would let the UI offer a selection the PUT refuses, or refuse one it
accepts. Same shape as `edicao_fotos/test_edicao_fotos_contract_fixture.py`:
the backend owns the vocabulary, a committed JSON carries it across, and this
test pins the two equal. `especificacoesCatalogo.test.ts` pins the FE side
(the typed accessors read exactly this file).

Regenerate after a catalogue change:

    NOCTUS_REGENERAR_CATALOGO_FE=1 pytest tests/modules/card_hub/test_especificacoes_catalogo_fe.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.modules.card_hub.contrato_gerador import especificacoes as esp

SNAPSHOT = (
    Path(__file__).resolve().parents[4] / "frontend" / "src" / "lib" / "especificacoesCatalogo.json"
)


def _esperado() -> dict:
    return {
        "versao": esp.CATALOGO_VERSAO,
        "base": esp.BASE,
        "eixos": list(esp.EIXOS),
        "catalogo": [
            {
                "chave": e.chave,
                "rotulo": e.rotulo,
                "eixo": e.eixo,
                "requer": list(e.requer),
                "exclusiva_com": list(e.exclusiva_com),
            }
            for e in esp.CATALOGO
        ],
    }


def _render(dados: dict) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2) + "\n"


def test_snapshot_do_frontend_e_o_catalogo():
    esperado = _render(_esperado())
    if os.environ.get("NOCTUS_REGENERAR_CATALOGO_FE") == "1":
        SNAPSHOT.write_text(esperado, encoding="utf-8")
    assert SNAPSHOT.exists(), f"{SNAPSHOT} ausente — regenere (ver docstring)."
    assert SNAPSHOT.read_text(encoding="utf-8") == esperado, (
        "frontend/src/lib/especificacoesCatalogo.json divergiu de especificacoes.CATALOGO — "
        "regenere com NOCTUS_REGENERAR_CATALOGO_FE=1 (ver docstring)."
    )
