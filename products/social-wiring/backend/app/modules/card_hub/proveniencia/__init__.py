"""The SW data -> file -> source catalog (contract-gate slice S1).

Before this package, "which upload feeds which field" lived in three
places that could drift from each other with nothing to notice: a
hand-written table in
`KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md`
§0a, and two independently-hand-maintained `TIPOS_*` literal sets —
`card_hub/identidade_extracao_service.py` and
`imovel_hub/documentos_service.py` — each answering its OWN slice of the
same question with no test tying either back to the other or to what the
seed extractor they call actually produces.

- `fontes` — `Entrada` (the upload/entry channel), `Fonte` (one
  `tipo_documento`'s extraction contract: which channels it arrives
  through, which extractor reads it, which `origem` values it writes,
  which canonical fields it claims), `FONTES` (the catalog, keyed by
  `tipo_documento` — same construction shape
  `contrato_gerador.validacao_extracao._POR_ENTIDADE_CAMPO` uses over
  `REGISTRO`), and `MANUAL_APENAS` (§0a's manual-only paragraph, in code).

Each `Fonte.campos` is checked against
`noctusai_lib.integrations.documents.capacidades.CAPACIDADES` — the seed's
own "what can this document type possibly carry" answer — so a product
claim that outruns what the extractor it names can actually produce is a
test failure, not a silent drift. `card_hub/identidade_extracao_service.py`'s
and `imovel_hub/documentos_service.py`'s own `TIPOS_*` constants are
re-derived from this catalog rather than hand-kept a second time.

Slice S2 (`linhagem.py`) walks the ACTUAL contract data
(`contrato_gerador.validacao_extracao.REGISTRO`) against this catalog and
answers, per contract-feeding value: what it holds, its state, its source
document, and — from `FONTES` — which document type(s) could still supply
it. `router.py` mounts its two endpoints (`GET /api/proveniencia/registro`,
the static FE-hint catalog; the per-contract lineage route lives on
`contrato_gerador/router.py` instead, next to its sibling
`.../validacao-extracao`).
"""
