"""Contract generator (F5) — "Instrumento Particular de Promessa de Venda e
Compra de Bem Imóvel" as an ABNT PDF, saved as a contract version with
origem='gerado'.

Design: `products/social-wiring/contracts/f5-template-spec.md` (gitignored,
office-internal). USER DECISION: gate the gaps — a contract that needs data
the system does not hold is REFUSED with a named `faltando` list (each item
carrying a `destino` the UI can link to); nothing is rendered blank and no
value is invented.

Layout (pure core, IO at the edges):

- `dados`        — the pure input (`DadosContrato` + `Termos`); its docstring
                   maps every spec §6.1 field to the migration that stores it
- `politica`     — the office's 15 answered questions, one named default each
- `concordancia` — V/C agreement engine (the only source of articles)
- `numeracao`    — clause registry, paragraph counter, refs, letters
- `modelo_texto` — the clause wording (reviewable text) + phrase builders
- `derivacao`    — switches, modelo derivado, completeness gate, consistency
- `contexto`     — `DadosContrato` -> template context
- `documento`    — builds the template .docx (python-docx), renders it via
                   the seed `docx_render` adapter, reads the text back
- `lint`         — post-render lint; any hit blocks saving
- `carregador`   — reads `DadosContrato` through the existing services
- `service`      — `obter_geracao` / `gerar`
- `router`       — GET .../geracao, POST .../gerar
"""
