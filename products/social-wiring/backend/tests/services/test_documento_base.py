"""`documento_base` — the pinned core across all three document-listing
surfaces (`card_hub.documentos_service`, `card_hub.financiamento_service`,
`imovel_hub.documentos_service`).

WHAT THIS PINS
--------------
A 4th hand-written copy of this projection (`documento_resumo`, deliberately
narrower — see its own docstring) is what made this an N=3-and-still-counting
DRY violation (auto-improvement ledger rowid 42579). Converging the three
`_documento_out` functions onto `documento_store.documento_base` only holds
if a future edit to any ONE of them can silently stop pulling from the
shared core without anything noticing. This test fails the moment that
happens, by asserting `documento_base`'s exact key/value set is a SUBSET of
each surface's real output for the same row.
"""
from __future__ import annotations

from app.modules.card_hub import documentos_service as card_hub_docs
from app.modules.card_hub import financiamento_service
from app.modules.imovel_hub import documentos_service as imovel_hub_docs
from app.services.documento_store import documento_base

_ACTOR_ID = "11111111-1111-1111-1111-111111111111"
_RESOLVED = {_ACTOR_ID: {"id": _ACTOR_ID, "nome": "Ana"}}

#: The 7 columns every surface's row carries, regardless of its own extras.
_CORE_ROW = {
    "id": "doc-1",
    "nome_original": "arquivo.pdf",
    "mime_type": "application/pdf",
    "tamanho_bytes": 1024,
    "tipo_documento": "rg",
    "enviado_por": _ACTOR_ID,
    "created_at": "2026-01-01T00:00:00+00:00",
}

_EXPECTED_BASE = {
    "id": "doc-1",
    "nome_original": "arquivo.pdf",
    "mime_type": "application/pdf",
    "tamanho_bytes": 1024,
    "tipo_documento": "rg",
    "enviado_por": {"id": _ACTOR_ID, "nome": "Ana"},
    "created_at": "2026-01-01T00:00:00+00:00",
}


def test_documento_base_shape():
    """The 7-field core, actor-resolved — nothing more, nothing less."""
    assert documento_base(_CORE_ROW, _RESOLVED) == _EXPECTED_BASE


def test_card_hub_documento_out_carries_the_full_core():
    row = {**_CORE_ROW, "categoria_lgpd": "identidade", "retencao_ate": None}
    out = card_hub_docs._documento_out(row, _RESOLVED)
    assert _EXPECTED_BASE.items() <= out.items()


def test_financiamento_documento_out_carries_the_full_core():
    row = {**_CORE_ROW, "categoria_lgpd": None, "retencao_ate": None}
    out = financiamento_service._documento_out(row, _RESOLVED)
    assert _EXPECTED_BASE.items() <= out.items()


def test_imovel_hub_documento_out_carries_the_full_core():
    row = {**_CORE_ROW, "codigo": "IMV-1"}
    out = imovel_hub_docs._documento_out(row, _RESOLVED)
    assert _EXPECTED_BASE.items() <= out.items()
