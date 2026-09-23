# SW contract-generation e2e harness — read-only, real-data-capable

Proves the contract generator (`app.modules.card_hub.contrato_gerador`)
against a REAL card in a REAL org, exactly the way production loads it —
without ever writing anything. Context:
`project-history/roadmaps/sw-extraction-contract-gate-2026-09.md`.

## Files

| File | What |
|---|---|
| `harness.py` | The harness + CLI. Loads a card (`carregador.carregar`), evaluates readiness (`derivacao.avaliar`) + the validation gate (`validacao_extracao.situacao`), renders in memory (`documento.renderizar`) WITHOUT persisting a version, traces every gap back to "document missing" / "extraction pending validation" / "manual field empty" / "outside the provenance ledger's scope" via `proveniencia.linhagem`, and (given a reference file) diffs the render against it. |
| `comparador.py` | Generic paragraph-aligned diff (`difflib.SequenceMatcher` on a normalised key) + heuristic categorisation: `clausula_faltando` / `clausula_extra` / `valor_errado` / `formatacao` / `clausula_faltando_e_extra`. Knows nothing about any specific contract. |
| `test_comparador_offline.py` | The only file here collected by the default `pytest` run — invented strings only, no database, no real data. |

`harness.py` is a CLI script, not a `test_*.py` module: it is never collected
by `noctus.dev.pytest` / CI, so a run against a live database is always an
explicit, deliberate invocation.

## Usage

```bash
cd products/social-wiring/backend/tests/e2e_contrato
<repo-venv-python> harness.py \
    --org <org_id> --cliente <cliente_id> [--contrato <contrato_id>] \
    [--referencia /path/to/reference.docx]
```

- `--contrato` defaults to the card's most recently created contract.
- Default output is REDACTED: `cliente_id`/`contrato_id` become
  `"<redigido>"`, `faltando`/`gaps`/`lint`/`diferencas` are trimmed to
  field names, categories and paragraph COUNTS — no name/CPF/address ever
  reaches stdout. Pass `--mostrar-valores` in a private terminal to see
  real values (never redirect that output into the repo).
- The render step is SKIPPED unless the card is `pronto` (mirrors
  `service.gerar`'s own precondition — production never calls
  `documento.renderizar` on an incomplete card either). Pass
  `--forcar-render` to attempt it anyway when debugging the template
  itself; a resulting `KeyError`/`AttributeError` on an incomplete card is
  expected and unreachable in production, not a generator defect.

Org-wide discovery (which cards are worth checking):

```bash
<repo-venv-python> harness.py --org <org_id> --descobrir --min-documentos 3
```

Lists every card with >= N live documents, its live-document count,
whether it has a contract, and (when it does) its readiness counts —
ranked by how close to `pronto`. Read-only; one extra query per
qualifying card (no bulk fan-out over the whole org beyond the initial
document scan).

## What "provenance" means here

`gaps` cross-references each `faltando` item against
`proveniencia.linhagem`'s per-field ledger (`validacao_extracao.REGISTRO`)
and classifies it:

- `manual_vazio` — the field has no document source at all; it is filled
  on the card by hand.
- `documento_ausente` — a document TYPE that could supply this field
  exists in the catalogue, but none has been uploaded/linked yet
  (`candidatos_tipo_documento` names which).
- `extracao_pendente_validacao` — a document supplied a value, but a
  human has not confirmed it yet (this blocks `gerar` via a 409, not via
  `faltando`, so seeing this here means the harness caught it separately).
- `fora_do_escopo_da_linhagem` — the field is not inside
  `validacao_extracao.REGISTRO` at all (financiamento, negociação,
  permuta, certidões, imobiliária, intermediação — see
  `proveniencia.linhagem`'s own module docstring). Honestly reported as
  "cannot trace via linhagem_do_card", never guessed at.

## Known limitation

Certidão gaps (`certidao.*`) are always `fora_do_escopo_da_linhagem` — the
`linhagem_do_card` module docstring documents `CAMPO_CERTIDAO` /
`CAMPO_ATO_DETALHE` as explicitly out of its scope (a different source
table, `certidao_resultados`, not one of the three tables `linhagem`
joins against). Certidão gaps are still reported (in `faltando`), just not
traceable to a specific document the way a `clientes`/`imoveis` column is.
