"""Aditivos — amendments to a signed contract (owner, 2026-09-24: "model,
store and generate them"; migration 190).

The office's corpus (5 deals) has two styles — house ("ADITIVO AO
INSTRUMENTO…") and formal ("PRIMEIRO TERMO ADITIVO") — and every aditivo
re-qualifies the parties, cites the original by its signing date, amends
payments / posse / commission, and ratifies the rest.

Seed-first by import: nothing of the contract generator is copied. The
parties, imóvel and schedule come from `contrato_gerador.carregador`; the
gate reuses `derivacao`'s party and payment rules; the wording reuses
`frases` (qualification, parcela lines), `concordancia`, `estilo`; the
render reuses the seed `docx_render` adapter, the office page face, the
post-render `lint` and `gerar_pdf`; versions reuse `DocumentoStore` and the
contract's legal-review predicate.

Layout:
- `schemas`     — the structured amendment vocabulary (HTTP boundary)
- `dados`       — `DadosAditivo` (pure input)
- `store`       — persistence: rows, restated parcelas, versions
- `avaliacao`   — readiness gate (pronto/faltando/bloqueios/avisos)
- `frases`      — the amending sections' wording
- `modelo_texto`— the two instrument templates
- `documento`   — context, render, lint (original-citation aware), snapshot
- `service`     — `obter_geracao` / `gerar`
- `router`      — the HTTP surface
"""
