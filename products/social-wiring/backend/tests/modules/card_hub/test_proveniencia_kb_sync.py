"""`CONTRACT-FIELD-PROVENANCE-MAP.md` § 0a's marker block MUST equal
`linhagem.bloco_secao_0a()`'s current output byte-for-byte — the doc used
to be hand-written prose that could (and did) drift from `fontes.py` with
nothing to notice; this is the "nothing to notice" fix.

The MCP keeper `check_contract_field_provenance_map` (`mcp/noctusai/tools/
noctus/dev/compliance.py`) additionally guards the STRUCTURAL half (both
markers present at all) repo-wide, without needing to import product code —
see that keeper's own docstring.
"""
from __future__ import annotations

from pathlib import Path

from app.modules.card_hub.proveniencia import linhagem

_KB_DOC = (
    Path(__file__).resolve().parents[6]
    / "KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md"
)


def test_secao_0a_marker_block_matches_the_generator_byte_for_byte():
    texto = _KB_DOC.read_text(encoding="utf-8")
    assert linhagem.MARCADOR_SECAO_0A_INICIO in texto, (
        f"{_KB_DOC} is missing the § 0a AUTOGEN begin marker — see "
        "linhagem.bloco_secao_0a()."
    )
    assert linhagem.MARCADOR_SECAO_0A_FIM in texto, (
        f"{_KB_DOC} is missing the § 0a AUTOGEN end marker — see "
        "linhagem.bloco_secao_0a()."
    )
    inicio = texto.index(linhagem.MARCADOR_SECAO_0A_INICIO)
    fim = texto.index(linhagem.MARCADOR_SECAO_0A_FIM) + len(linhagem.MARCADOR_SECAO_0A_FIM)
    bloco_no_disco = texto[inicio:fim]
    assert bloco_no_disco == linhagem.bloco_secao_0a(), (
        "CONTRACT-FIELD-PROVENANCE-MAP.md § 0a has drifted from fontes.py — "
        "regenerate it with `linhagem.bloco_secao_0a()`."
    )
