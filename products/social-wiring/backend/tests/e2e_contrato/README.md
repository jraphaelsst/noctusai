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
| `allowlist.json` | Versioned, owner-approved deliberate template-vs-reference wording differences — PATTERNS only (regex on accent-free lowercase text), never a real value; `comparador.validar_allowlist` refuses digit runs/e-mails. Only `aprovado_pelo_dono: true` entries explain a difference. |
| `limiares.json` | The scorecard's pass bars (`comparador.Limiares`). Numbers and dates are zero-tolerance. |
| `test_comparador_offline.py` / `test_harness_offline.py` | Collected by the default `pytest` run — invented strings + synthetic fixtures only, no database, no real data. |

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

## The scorecard — the enforced number

`comparador.pontuar(ref, gerado)` cuts both texts into sections (preamble ·
one per clause, keyed by TITLE so a renumbering is not a missing clause ·
closing block), aligns them, and scores per category: `estrutura`,
`qualificacao`, `matricula` (the `IMÓVEL:` quote), `certidoes` (item labels),
`redacao` (word similarity, digits masked), plus EXACT multiset checks of
`numeros` (CPF/CNPJ/CEP/R$/any digit run) and `datas`. Verdict:
`aprovado` · `reprovado` (any unexplained missing/extra clause, number or
date diff, or a category under its bar) · `incompleto` (no failure, but the
render carries `[[LACUNA]]` gap markers — a not-`pronto` card, rendered with
its empty printable fields marked by `harness.dados_com_marcadores`; what a
marker stands in for counts as a GAP, never as a wording/number diff).

```bash
<repo-venv-python> comparador.py --ref ref.txt --gerado gen.txt   # exit 0 aprovado / 1 reprovado / 2 incompleto
```

Against real signed contracts (private disk only) use the MCP tool
`noctus.dev.contract_score` — it renders read-only from the live DB via
`harness.py --lote`, writes the masked scorecard to
`~/.noctusai/private/scores/<ts>.json` (0600) and returns verdict-level
numbers only. CI's half is `tests/modules/card_hub/test_contrato_golden.py`
(golden full-text snapshots of the 6 synthetic variants).

Readiness comes from production's own functions — `service.obter_geracao`
plus `service.precondicao_gerar` (the extraction precondition `service.gerar`
itself calls) — never a re-derivation.

A reference clause the generator SWITCHED OFF for this card (its switch is
false — e.g. intermediação with no corretagem data; `numeracao.
CLAUSULA_CONDICIONAL`) is reported as `clausulas_desligadas`, a DATA gap
(verdict `incompleto`), never as a missing-clause failure.

## Honest comparison — what is NOT a divergence (2026-10-05 audit)

The divergence-email study found ~56 % of extraction "divergences" were
formatting-only or noise. The scorer is held to the same bar: a number/date
counts as a DIVERGENCE only when the generated text states a different FACT.
Everything else is normalised away or counted apart (`Scorecard.resumo()`):

| Class | Handling |
|---|---|
| FORMAT (`R$ 5.000,00`/`5000`, CPF/CNPJ/CEP punctuation, `14/09/2026` vs extenso, `Parcela 01` vs `1`, `170,00m2` vs `170,000 m²`, RG with/without check digit, `59 884 041`, registry-number separators) | normalised in `extrair_numeros` before comparing (RG via the seed `identificador` registry) |
| EXTRACTION/LAYOUT ARTIFACT (e-mail digits, list enumerators, `itens 1.7, 1.9` cross-references, `__31__` fill-in blanks, PDF-glued certidão items) | stripped / split before tokenising |
| ALIGNMENT (a repeated mention, or the value stated in another clause) | distinct values per section; a specific value present elsewhere on the other side = `numeros_alinhados`/`datas_alinhadas` (a bare small number gets no such benefit) |
| GAP (marker/sentinel) | typed: `CPF [[LACUNA]]` absorbs a missing CPF only — never an RG the render printed wrong (`numeros_em_lacuna`) |
| GAP (certidão the card does not carry) | `certidoes_lacuna` — out of numbers, wording and the certidões ratio; verdict `incompleto` |
| DATA-UNAVAILABLE (favorecido bank account) | `dados_indisponiveis` — expected gap; bank data the render prints wrong still diverges |
| Render-time (signing-date line, identifier kinds only one block prints) | `assinatura_excluidos` |
| Newer certidão (same kind/person, other identifier AND emission date) | `certidoes_reemitidas` — counted, not failed |
| Certidão the render lists and the signed text does not | `certidoes_extras` — lowers the `certidoes` ratio (printed-and-listed kinds) |

Kept strict (still divergences): a different value, a different date, a
different installment→amount pair (`parcela:N=valor` tokens), a different RG,
a different identifier on the same certidão emission date, an area written
with a pt-BR thousands dot where the signed text has a decimal comma.
Certidões are paired by person then kind, never by position.

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
