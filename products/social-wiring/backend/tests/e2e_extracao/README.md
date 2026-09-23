# E2E extraction fixtures — sw-extraction-contract-gate-2026-09

Synthetic, **entirely fictional** document set (no real person/imóvel data)
that proves social-wiring's file → DB extraction lands the contract's fields
in the right columns — for both a text-layer PDF (pdfminer.six leg) and a
scan-like image-only PDF (PyMuPDF-rasterize → vision leg) of the SAME
document.

Context: `project-history/roadmaps/sw-extraction-contract-gate-2026-09.md`
(owner decisions D1–D4 + the shared field-state contract table). Authored on
`feat/sw-extr-e2e-fixtures`, then reconciled 2026-09-23 against the MERGED
wave-1 slices (identity mig 153, imóvel mig 154, certidões mig 155,
validation gate mig 156, tip `75d5abf11` on `feat/sw-extraction-orchestrator`)
by running the REAL seed parsers directly against this fixture set's
rendered text — see "Dry-run trace" below.

## Files

| File | What |
|---|---|
| `dados.py` | The ONE source of persona/imóvel facts (names, CPFs, RGs, addresses, matrícula numbers, ...). Everything else derives from here. |
| `gerar_documentos.py` | Renders the PDFs + writes `esperado.json` (the answer key). |
| `verificar.py` | Reads a live DB (Supabase REST via the `supabase` client) and scores it against `esperado.json`. |
| `test_gerar_documentos.py` | Offline pytest — generator output is complete/well-formed/deterministic. Does NOT touch a database. |
| `fixtures/` | Checked-in output of `gerar_documentos.py` — 11 documents × 2 variants (`_texto.pdf` / `_scan.pdf`) + `esperado.json`. Small (~1.6 MB), fictional, safe to commit. |

## 1. Generate (or regenerate) the fixtures

```bash
cd products/social-wiring/backend/tests/e2e_extracao
python gerar_documentos.py            # writes into ./fixtures/
```

No new dependency: `reportlab` and `PyMuPDF` (`import fitz`) are already in
`products/social-wiring/backend/requirements.txt`. If your interpreter
doesn't have them yet: `pip install reportlab PyMuPDF` (or the full
`requirements.txt`).

Re-running is **deterministic for the text-layer PDFs and `esperado.json`**
(byte-identical — `reportlab`'s `invariant=1` pins the /CreationDate and
internal object IDs; a stable `zlib.crc32` seed, not the salted builtin
`hash()`, drives the scan variant's rotation/noise). The scan variant's
*rendered pixel content* is equally seeded/deterministic; its PDF container
bytes may still vary trivially run-to-run (PyMuPDF's own embedded producer
metadata) — verified, not assumed, across two full generator runs.

## 2. Upload — which file goes where

All fictional. `titular` = Ricardo, `conjuge` = Camila (his wife, comunhão
parcial), `vendedor` = Fernando (solteiro). Two imóveis: `e2e-imv-livre`
(alienação fiduciária registered THEN cancelled → ônus livre) and
`e2e-imv-hipoteca` (hipoteca registered, never cancelled → ônus ativo; its
"owners" are two more throwaway fictional names, not cards in this org).

Create three `clientes` cards (titular/cônjuge/vendedor) and two `imoveis` +
`imovel_dados` rows (`codigo = "e2e-imv-livre"` / `"e2e-imv-hipoteca"`) in a
test org first — this fixture set does not create them for you.

| File (either `_texto` or `_scan` variant) | Upload to | Tipo |
|---|---|---|
| `titular_rg` | Ricardo's card, identity checklist | `rg` |
| `conjuge_cin` | Camila's card, identity checklist | `rg` (CIN uses the same slot) |
| `vendedor_cnh` | Fernando's card, identity checklist | `cnh` |
| `certidao_casamento` | **BOTH** Ricardo's AND Camila's card (same file, two uploads) | `certidao_casamento` |
| `vendedor_certidao_nascimento` | Fernando's card | `certidao_nascimento` |
| `comprovante_endereco` | Ricardo's card | `comprovante_endereco` |
| `matricula_imovel_livre` | `e2e-imv-livre`'s matrícula upload, LINKED to the imóvel | `matricula` |
| `matricula_imovel_hipoteca` | `e2e-imv-hipoteca`'s matrícula upload, LINKED to the imóvel | `matricula` |
| `guia_iptu` | `e2e-imv-livre`'s documentos | `guia_iptu` |
| `cnd_iptu` | `e2e-imv-livre`'s documentos | `cnd_iptu` |
| `cnd_federal_vendedor` | Fernando's due-diligence certidões (manual upload) | `cnd_federal` |

Upload the `_texto` variant and the `_scan` variant as if they were two
INDEPENDENT documents (they will get two independent `cliente_documentos` /
`imovel_documentos` rows) — the point is comparing what each extraction path
lands, not deduplicating them. "LINKED to the imóvel" matters for the two
matrícula files: `matriculas/preenchimento_service.preencher_sincrono` only
fills `imovel_dados` once the transcription is associated with
`(org_id, codigo)`, either at upload time or via `vincular_imovel`.

**The only remaining manual step**: Fernando's `clientes.profissao`. Open the
`e2e-imv-livre` matrícula's **Qualificações** queue
(`matriculas/qualificacao_service.confirmar`) and click **Confirmar** on
Fernando's row. He has no certidão de casamento — the ONLY OTHER source of
`profissao` in this codebase (`profession.py`'s module docstring: never read
off an RG/CIN/CNH, and never off a certidão de nascimento's own holder, only
per-spouse off a certidão de casamento or a matrícula qualification). Ricardo
and Camila do NOT need this step — their `profissao` lands automatically from
the `certidao_casamento` upload (see the dry-run trace below).

## 3. Run the scorecard

```bash
python verificar.py --print-mapping-example > mapping.json   # edit the IDs
python verificar.py --mapping mapping.json
```

Needs `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (env or the repo's
`.env` — read-only SELECTs, `social_wiring` schema, service-role so RLS never
gets in the way of reading the harness's own rows). Prints, per uploaded
file: `OK` / `ERRADO` (shows both expected and real) / `FALTANDO`, plus a
`REVISAO` line per provenance check (`<campo>_origem` set, `<campo>
_confirmado_em` still NULL — the D2 validation-gate contract) and per
`bonus_campos`/`pending_spec` entry. Exit code is non-zero iff any core field
is `ERRADO` or `FALTANDO` — `REVISAO` never affects it.

## Dry-run trace (2026-09-23, post-merge reconciliation)

Every `campos` (core, scored) entry in `esperado.json` was verified by
running the REAL seed parsers directly against this fixture set's rendered
`_texto.pdf` text (pdfminer.six extraction — no DB, no network, no vision):
`name.find_name`, `cpf.find_cpf`/`find_cpf_conflitos`, `rg.find_rg`/
`find_rg_orgao`, `birthdate.find_birthdate`, `gender.find_gender`,
`civil_status.find_estado_civil`/`find_regime_bens`/`find_data_casamento`,
`nacionalidade.find_nacionalidade`, `profession.find_profissao`,
`conjuges.find_conjuges`, `address.find_endereco`, `matricula.find_matricula`,
`matricula_cabecalho.find_cartorio`/`find_inscricao_municipal`,
`matricula_atos.segment_matricula_atos`,
`matricula_abertura.segmentar_abertura`,
`matricula_ato_detalhes.extrair_detalhes_ato`/`frase_titulo_aquisitivo`, and
`matriculas/preenchimento_service.derivar_situacao_onus`'s logic (traced by
hand from the real `atos_referidos` the parser returned — same inputs the
service itself would see). Every one of them returned EXACTLY the value
`esperado.json` now asserts, at `alta` confidence, with no code changes.

**Two fixture-layout bugs were found and fixed** (not parser bugs — see the
in-code comments at each site for the full reasoning):

1. A `FILIAÇÃO`/`PAI`/`MAE` block sitting immediately BEFORE a `CPF:` or
   `DOC. IDENTIDADE:` line demotes that reading to `baixa` confidence (`cpf.py`
   and `rg.py` both apply this — a value inside a filiação block's lookback
   window might be a PARENT's, not the holder's). Camila's CIN and Fernando's
   CNH originally printed their CPF/RG right after `MAE:`; both now print
   FILIAÇÃO clear of the label window (see `_doc_conjuge_cin` / cnh's comment).
2. `reportlab`'s justified paragraph style (`alignment=4`) widens inter-word
   spacing on a wrapped line, and pdfminer.six's extraction turns that into
   literal DOUBLE spaces mid-value — an artifact of THIS renderer, not of a
   real scanned document. Switched the body style to left-aligned
   (`_STYLE_BODY`).
3. (Minor, same root cause as #2) A long decorative certidão header line that
   happened to word-wrap right after "...NACIONALIDADE E" fed the wrapped
   remainder into `conjuges.find_conjuges`' multi-holder name walk as a
   bogus third "spouse" (the header started with the word "NOMES", which
   ALSO opens that walk). Reworded to not start with "NOME"/"NOMES".

**Confirmed automatic, no manual step needed** (all landed exactly as
predicted by `matriculas/preenchimento_service.py`'s own docstring table,
run synchronously once a transcription is linked to its imóvel):
`imovel_dados.numero_matricula`, `numero_registro_imoveis`,
`prefeitura_cadastro_imobiliario`, `situacao_onus` (`"livre"` for
`e2e-imv-livre` — its R-2 alienação fiduciária IS correctly read as released
by AV-3's `atos_referidos=[R-2]`; `"hipoteca"` for `e2e-imv-hipoteca`, never
released), `titulo_aquisitivo_texto` (`frase_titulo_aquisitivo` over R-1's
own parsed `Instrumento`, reproduced verbatim in `esperado.json`). Also
confirmed automatic: `clientes.profissao` for Ricardo AND Camila, straight
off the `certidao_casamento` upload via `conjuges.find_conjuges` +
`profession.find_profissao` on each spouse's own qualification segment —
this used to require the same Qualificações-confirm step this README's
predecessor draft still described; migration 153 made it automatic, so only
Fernando (no certidão de casamento) still needs the manual click.

**A previously-flagged inconsistency is now RESOLVED, not a live risk**: an
earlier draft of this fixture set (authored before the wave-1 merge) found
that `matriculas/qualificacao_service._lidos` wrote `clientes.genero` as the
matrícula reader's raw `"m"/"f"` code, disagreeing with the identity ladder's
`"Masculino"/"Feminino"` words on the SAME column. Migration 153 added
`gender.canonical_gender()` and `qualificacao_service._lidos` now calls it
(see that function's own comment, added in the same slice) — verified by
reading the merged code, not re-asserted here as still-open.

**`onus_credor` for `e2e-imv-livre` is intentionally NOT a `campos` entry**:
R-2 (alienação fiduciária) is cancelled by AV-3, so
`estrutura_service.sugerir`'s onus-source suggestion excludes it (per
`preenchimento_service.py`'s own docstring: "onus_fonte — encumbrance acts
not cited by a cancelamento") and `imovel_dados.onus_credor` stays NULL. This
harness's `campos`/pytest schema asserts non-empty values, so an
expected-EMPTY field is reported under `bonus_campos` instead — the real
proof the cancellation landed is `situacao_onus == "livre"`, which IS scored.

**Still out of this harness's scope, on purpose**:
`clientes.certidao_estado_civil_emitida_em` — migration 148 states in so many
words "never written by extraction" (pure manual `[Q11]` entry). The
document's OWN emission date (`cliente_documentos.extracao_data_emissao`) is
what the extractor actually writes; scoring that row-level field would need a
document ID `mapping.json` doesn't carry today — documented gap, not a
silent skip.

## Grounding trace (file → parser)

- CPF: `noctusai_lib.integrations.documents.cpf.py` — mod-11, formatted
  `123.456.789-09`, label `CPF`/`C.P.F`.
- RG + órgão: `.../rg.py` — labels `REGISTRO GERAL`/`DOC. IDENTIDADE`/etc.,
  órgão must be ADJACENT to the number (`23.456.789-0 SSP/SP`); its own
  provenance quintet (`rg_orgao_expedidor_*`) is migration 153.
- Nome: `.../name.py` — label `NOME`; certidão de casamento uses the
  multi-holder `NOMES` header + interleaved `CPF` lines.
- Data de nascimento: `.../birthdate.py` — label `DATA DE NASCIMENTO`.
- Gênero: `.../gender.py` — label `SEXO`, accepts a bare `M`/`F` letter ONLY
  when labelled; outputs the WORD `Masculino`/`Feminino`; migration 153 adds
  `canonical_gender()`, the MRZ (CIN back-side) reader, and the table-layout
  reader.
- Estado civil / regime de bens: `.../civil_status.py` — `ESTADO CIVIL`
  label for the word; regime phrase ("COMUNHÃO PARCIAL DE BENS") matched
  UNLABELLED.
- Data de casamento: `.../civil_status.py` — label `DATA DO CASAMENTO`.
- Nacionalidade: `.../nacionalidade.py` — label `NACIONALIDADE`, output
  canonicalised to the MASCULINE spelling (`brasileiro`) regardless of the
  document's own grammatical gender.
- Profissão (migration 153, `.../profession.py`): label `PROFISSÃO`/
  `OCUPAÇÃO`; a whole-document read of a two-spouse certidão returns
  `nenhuma` (two disagreeing readings) — `conjuges.py` (below) resolves it
  per spouse.
- Endereço (migration 153, `.../address.py`): CEP-anchored; labelled mode
  (`CEP:`/`LOGRADOURO:`/`NÚMERO:`/`COMPLEMENTO:`/`BAIRRO:`/`CIDADE:`/`UF:`)
  or the unlabelled envelope-block mode. Feeds `clientes.endereco_*` (seven
  columns, ONE `endereco_origem` provenance quintet) — `comprovante_endereco`
  only, never an identity document or a certidão (whose address is the
  issuer's/cartório's, not the holder's).
- Cônjuges (migration 153, `.../conjuges.py`): both spouses of a certidão de
  casamento, each with their OWN cpf/data_nascimento/nacionalidade/
  profissão/genero read from their own qualification segment — resolves the
  "two-titular certidão" gap `find_name`/`find_cpf`/`find_profissao` all
  individually decline (disagreement is absence) to answer alone.
- Matrícula number: `.../matricula.py` — label `MATRÍCULA Nº`, heading-only
  (body citations of OTHER matrículas are explicitly excluded).
- Cartório / inscrição municipal (migration 154, `.../matricula_cabecalho.py`):
  `find_cartorio` reads the heading (before the abertura's first label),
  requires the literal phrase "REGISTRO DE IMÓVEIS"; `find_inscricao_municipal`
  reads the `CADASTRO MUNICIPAL:` abertura block.
- Matrícula abertura blocks: `.../matricula_abertura.py` — line-start labels
  `IMÓVEL:` / `CADASTRO MUNICIPAL:` / `PROPRIETÁRIOS:` / `REGISTRO ANTERIOR:`.
- Matrícula acts: `.../matricula_atos.py` — `R-<n>` / `AV-<n>` headers at
  line start.
- Matrícula act details (`.../matricula_ato_detalhes.py`): `natureza`
  (compra_e_venda/hipoteca/alienação fiduciária/cancelamento/...),
  `data_registro`, `transmitentes`/`adquirentes` (name+CPF pairs),
  `credor`, `instrumento` (Escritura Pública/Contrato + tabelionato/livro/
  folhas/data), `atos_referidos` (a cancelamento's own act-citations) —
  `frase_titulo_aquisitivo(instrumento, kind, numero)` renders the phrase
  `imovel_dados.titulo_aquisitivo_texto` stores.
- `imovel_dados` fill (migration 154,
  `app/modules/matriculas/preenchimento_service.py`): the single place all
  of the above compose into `numero_registro_imoveis` /
  `prefeitura_cadastro_imobiliario` / `titulo_aquisitivo_texto` /
  `onus_credor` / `situacao_onus`, synchronously, once a transcription is
  linked to its imóvel — see `derivar_situacao_onus`'s own docstring for the
  release/cancellation logic.
- `imovel_documentos` structured fields (`guia_iptu`/`cnd_iptu`):
  `app/modules/imovel_hub/documentos_service.py`'s
  `CAMPOS_ESTRUTURA_POR_TIPO` + `RESULTADO_VALUES`.

## Why every matrícula qualification clause says "brasileiro" for everyone

The matrícula's R-1 act still qualifies Fernando/Ricardo/Camila with the full
notarial formula (`dados.qualificacao()`) — it is how `matricula_ato_detalhes
.transmitentes`/`.adquirentes` (name+CPF Parte pairs) get populated, and it is
still Fernando's ONLY path to a `profissao`. But unlike the identity-document
ladder (which canonicalises nationality to the masculine spelling via
`nacionalidade.canonico()`), a value read off a matrícula qualification via
`matricula_qualificacao`-style tooling is not necessarily re-canonicalised
the same way everywhere it might be consumed. Writing the grammatically
correct `"brasileira"` for Camila's clause risks a machine-vs-machine
disagreement against her certidão-sourced canonical `"brasileiro"` if some
future consumer ever promotes that particular field off the matrícula text
too (D1: "machine vs machine disagreement ... is also a conflict"). So every
qualification clause in `dados.qualificacao()` uses the masculine spelling on
purpose, for both genders — a documented liberty, not an oversight. (Fields
this fixture set actually DOES score off the matrícula — the Parte name/CPF
pairs, `numero_registro_imoveis`, etc. — were individually verified against
the real, merged parsers; see the dry-run trace above.)
