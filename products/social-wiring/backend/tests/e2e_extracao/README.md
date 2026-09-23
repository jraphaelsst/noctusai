# E2E extraction fixtures — sw-extraction-contract-gate-2026-09

Synthetic, **entirely fictional** document set (no real person/imóvel data)
that proves social-wiring's file → DB extraction lands the contract's fields
in the right columns — for both a text-layer PDF (pdfminer.six leg) and a
scan-like image-only PDF (PyMuPDF-rasterize → vision leg) of the SAME
document.

Context: `project-history/roadmaps/sw-extraction-contract-gate-2026-09.md`
(owner decisions D1–D4 + the shared field-state contract table).

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
metadata) — this was verified, not assumed; see git history of this file's
authoring session if the exact byte-diff matters later.

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
| `matricula_imovel_livre` | `e2e-imv-livre`'s matrícula upload | `matricula` |
| `matricula_imovel_hipoteca` | `e2e-imv-hipoteca`'s matrícula upload | `matricula` |
| `guia_iptu` | `e2e-imv-livre`'s documentos | `guia_iptu` |
| `cnd_iptu` | `e2e-imv-livre`'s documentos | `cnd_iptu` |
| `cnd_federal_vendedor` | Fernando's due-diligence certidões (manual upload) | `cnd_federal` |

Upload the `_texto` variant and the `_scan` variant as if they were two
INDEPENDENT documents (they will get two independent `cliente_documentos` /
`imovel_documentos` rows) — the point is comparing what each extraction path
lands, not deduplicating them.

**Additional manual step for `profissao`** (both spouses + Fernando): after
uploading the two matrícula files, open the imóvel's **Qualificações** queue
(`matriculas/qualificacao_service`) and click **Confirmar** on each
identified party row. `profissao` has NO other source in this codebase — it
is only ever written via a human-confirmed matrícula qualification, never by
the RG/CNH/certidão ladder — see `gerar_documentos.py`'s `bonus_campos` note
on `_doc_matricula_livre`. This is why `clientes.profissao` is a
`bonus_campos` entry, not a core scored field: it needs this extra click, it
is not itself a defect if `verificar.py` shows it as ainda vazio before you
do it.

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

## Scope notes — read before treating a `REVISAO` line as a bug

This fixture set was authored in a worktree forked BEFORE the roadmap's
wave-1 slices (`feat/sw-extr-identity` mig 153, `feat/sw-extr-imovel` mig
154, `feat/sw-extr-certidoes` mig 155, `feat/sw-extr-validacao-gate` mig 156)
were merged. Every field is grounded against the extractor code that exists
TODAY in `noctusai_lib.integrations.documents.*` (see the trace below) —
except a small, explicitly-flagged set:

- **`clientes.profissao` / matrícula-sourced `nacionalidade`/`genero`** — the
  `matriculas/qualificacao_service.confirmar` path is human-confirm-gated
  (not an automatic write-on-upload) and writes `genero` as lowercase
  `"m"/"f"`, DIFFERENT from the identity ladder's `"Masculino"/"Feminino"`
  words (`noctusai_lib.integrations.documents.gender.py`). This is a real,
  pre-existing format inconsistency between the two `clientes.genero`
  writers — flagged for the tech-lead, not something this fixture works
  around. `bonus_campos`, not scored.
- **`imovel_dados.numero_registro_imoveis` / `situacao_onus` / `onus_credor`
  (post-cancellation)** — target format/vocabulary not yet defined (mig 154
  in flight when this was authored). `pending_spec`, not scored; each entry
  names its own best-guess + what to confirm once 154 ships.
- **`imovel_dados.prefeitura_cadastro_imobiliario`** — IS scored (via
  `guia_iptu` upload → `_sugestao_imovel_dados`, existing code,
  `app/modules/imovel_hub/documentos_service.py`), listed under
  `bonus_campos` only because the write requires the suggestion to be
  applied — check `imovel_dados` directly if `cliente:` scoring already
  passed but this one line still shows empty.
- **`clientes.certidao_estado_civil_emitida_em`** — NOT in this fixture's
  scored set at all. Migration 148 states explicitly: "never written by
  extraction" — it is a pure manual-entry field (`[Q11]`). The document's
  OWN emission date (`cliente_documentos.extracao_data_emissao`) is what the
  extractor actually writes; scoring a row-level `cliente_documentos` field
  needs a document ID this harness's `mapping.json` doesn't carry, so it is
  left as a documented gap rather than half-implemented.

## Grounding trace (file → parser, so a future reviewer doesn't have to re-derive it)

- CPF: `noctusai_lib.integrations.documents.cpf.py` — mod-11, formatted
  `123.456.789-09`, label `CPF`/`C.P.F`.
- RG + órgão: `.../rg.py` — labels `REGISTRO GERAL`/`DOC. IDENTIDADE`/etc.,
  órgão must be ADJACENT to the number (`23.456.789-0 SSP/SP`).
- Nome: `.../name.py` — label `NOME`; certidão de casamento uses the
  multi-holder `NOMES` header + interleaved `CPF` lines.
- Data de nascimento: `.../birthdate.py` — label `DATA DE NASCIMENTO`.
- Gênero: `.../gender.py` — label `SEXO`, accepts a bare `M`/`F` letter ONLY
  when labelled; outputs the WORD `Masculino`/`Feminino`.
- Estado civil / regime de bens: `.../civil_status.py` — `ESTADO CIVIL`
  label for the word; regime phrase ("COMUNHÃO PARCIAL DE BENS") matched
  UNLABELLED.
- Data de casamento: `.../civil_status.py` — label `DATA DO CASAMENTO`.
- Nacionalidade: `.../nacionalidade.py` — label `NACIONALIDADE`, output
  canonicalised to the MASCULINE spelling (`brasileiro`) regardless of the
  document's own grammatical gender.
- Matrícula number: `.../matricula.py` — label `MATRÍCULA Nº`, heading-only
  (body citations of OTHER matrículas are explicitly excluded).
- Matrícula abertura blocks: `.../matricula_abertura.py` — line-start labels
  `IMÓVEL:` / `CADASTRO MUNICIPAL:` / `PROPRIETÁRIOS:` / `REGISTRO ANTERIOR:`.
- Matrícula acts: `.../matricula_atos.py` — `R-<n>` / `AV-<n>` headers at
  line start.
- Matrícula party qualification (nacionalidade/profissão/RG/CPF/endereço):
  `.../matricula_qualificacao.py` — the notarial formula "NOME, nacionalidade,
  estado civil, [regime,] profissão, RG nº <n>-<órgão>, CPF nº <n>, residente
  e domiciliado[a] na <endereço>", anchored on a checksum-valid CPF/CNPJ.
- `imovel_documentos` structured fields (`guia_iptu`/`cnd_iptu`):
  `app/modules/imovel_hub/documentos_service.py`'s
  `CAMPOS_ESTRUTURA_POR_TIPO` + `RESULTADO_VALUES`.

## Why every matrícula qualification clause says "brasileiro" for everyone

`matricula_qualificacao.Qualificacao.nacionalidade` is stored **verbatim**
(`app/modules/matriculas/qualificacao_service.py::_lidos` passes
`row.get("nacionalidade")` straight through) — unlike the identity-document
ladder, which canonicalises to the masculine spelling
(`nacionalidade.canonico()`). Ricardo's and Camila's `clientes.nacionalidade`
is ALSO fed by their own identity documents (certidão de casamento) through
that canonicalising path, which will always land `"brasileiro"`. Writing the
grammatically-correct `"brasileira"` for Camila's matrícula clause would make
the two machine sources DISAGREE and open a real `cliente_campo_conflitos`
row (D1: "machine vs machine disagreement ... is also a conflict") — a real
platform behaviour this fixture set deliberately does not exercise. So every
qualification clause in `dados.qualificacao()` uses the masculine spelling on
purpose, for both genders — a documented liberty, not an oversight.
