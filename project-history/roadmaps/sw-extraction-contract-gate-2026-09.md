# sw-extraction-contract-gate-2026-09 — file extraction feeds 100% of the contract + human validation gate

> Durable record (`KB § PATTERNS/common/roadmap-tracking.md`). Origin: 2026-09-22 owner session —
> "make sure all data a contract needs is correctly extracted from files and stored on the DB";
> contract generation itself was validated 100% by a previous session.

> **Evidence for D2 (2026-09-23):** a real certidão sweep found the vision rung misreads identifiers
> (6/10 CENPROT protocolos) while getting every status right — vision-read numbers are machine-pending by
> default. → `KB § CONTEXT/PRODUCTS/social-wiring/CERTIDOES-LEVANTAMENTO-LEARNINGS.md`

## Owner decisions (verbatim intent, 2026-09-22)

- **D1 Write policy.** Machinery writes extracted values straight into the contract column.
  - Field EMPTY → machine fills it (provenance recorded). A human may change it later, unbothered.
  - Field already set by a HUMAN (`*_origem='manual'`) → machine never overwrites; opens a conflict and a
    human is **notified** and accepts/rejects. Accepted-then-later-edited by a human is fine (no prompt).
  - Machine vs machine disagreement (field set by an earlier extraction, not yet human-validated) → also a
    conflict (never a silent overwrite).
- **D2 Validation gate.** Clicking "Gerar contrato" opens a modal listing every contract-feeding value that
  came from a machine and is not yet human-validated. Each field: ✓ accept / ✗ reject icon. Plus "accept all"
  and "reject all". Every decision is logged (ledger) for extractor refinement. When nothing is pending,
  generation proceeds. The backend refuses generation while any such field is pending (not FE-only).
- **D3 Retries.** Automatic retry after a failed extraction happens at most **2** times, then the row stays in
  `erro` for a human. No long loops.
- **D4 Tests.** Both: re-extract the real stuck prod rows in place AND UI-upload the existing files to a
  dedicated test card, asserting DB columns.

## Shared field-state contract (ALL slices build to this)

A contract-feeding field is **machine-pending** iff `origem IS NOT NULL AND origem <> 'manual' AND
confirmado_em IS NULL` on its provenance columns. Provenance column naming convention (existing):
`<campo>_origem`, `<campo>_documento_id`, `<campo>_em`, `<campo>_confirmado_por`, `<campo>_confirmado_em`.
`origem` values: `'manual'` (human) | a document tipo (`'rg'`, `'cnh'`, `'certidao_casamento'`,
`'comprovante_endereco'`, `'matricula'`, …) | `'ia'` | `'api'`.

**Accept** = set `<campo>_confirmado_por/_em` (value untouched). **Reject** = set the value AND its provenance
columns to NULL (field becomes empty → the contract gate reports it `faltando`, human types it; a later
extraction may refill it). Both append one ledger row.

| Entity | Field(s) | Provenance columns | Owner slice |
|---|---|---|---|
| `clientes` | nome_oficial, cpf, rg, genero, estado_civil, regime_bens, data_casamento, nacionalidade, profissao, data_nascimento | existing `<campo>_*` | identity (already exist) |
| `clientes` | rg_orgao_expedidor | NEW `rg_orgao_expedidor_origem/_documento_id/_em/_confirmado_por/_confirmado_em` | identity (mig 153) |
| `clientes` | endereco_{cep,logradouro,numero,complemento,bairro,cidade,uf} (ONE group) | NEW `endereco_origem/_documento_id/_em/_confirmado_por/_confirmado_em` | identity (mig 153) |
| `clientes` | conjuge_cliente_id (link from certidão de casamento) | NEW `conjuge_origem/_documento_id/_em/_confirmado_por/_confirmado_em` | identity (mig 153) |
| `clientes` | certidao_estado_civil_emitida_em | existing `_origem`/`_em`; NEW `_confirmado_por/_confirmado_em` | identity (mig 153) |
| `imovel_dados` | numero_matricula | existing `numero_matricula_*` | imóvel |
| `imovel_dados` | numero_registro_imoveis, prefeitura_cadastro_imobiliario, situacao_onus | NEW `<campo>_origem/_documento_id/_em/_confirmado_por/_confirmado_em` (`_documento_id` = `matricula_extracoes.id` or `imovel_documentos.id`) | imóvel (mig 154) |
| `imovel_dados` | titulo_aquisitivo_texto, onus_credor | existing `_confirmado_por/_em`; NEW `titulo_aquisitivo_texto_origem`, `onus_credor_origem` | imóvel (mig 154) |
| `imovel_dados` | onus_fonte_atos | existing `onus_fonte_origem/_confirmado_*` | imóvel |
| `imovel_documentos` | numero, emitida_em, validade_ate, resultado (per doc, ONE group) | existing `origem` (`'ia'`/`'manual'`), `confirmado_por/_em` | imóvel |
| `certidao_resultados` | numero, emitida_em, validade_ate, resultado (ONE group) | existing `resultado_origem` (`'api'`/`'ia'`/`'manual'`), `confirmado_por/_em` | certidões |
| `matricula_ato_detalhes` | data_registro, transmitentes (última transferência) | existing `origem` (`'sugestao'`/`'confirmado'`), `confirmado_por/_em` | imóvel |

Ledger (validation slice, mig 156) `social_wiring.extracao_validacoes`: `id, org_id, contrato_id,
entidade, entidade_id, campo, valor_extraido text, origem, fonte_documento_id, confianca, decisao
('aceito'|'rejeitado'), decidido_por, decidido_em, created_at`. RLS like sibling tables.

## Slices (wave 1, parallel)

| Slice | Branch | Migration | Scope |
|---|---|---|---|
| identity | feat/sw-extr-identity | 153 | D1 write policy for identity pipeline; rg_orgao; profissão; endereço from comprovante; two-spouse certidão + cônjuge link; genero (CIN "Sexo" + m/f normalisation); RG text-layer→vision fallback; retry ≤2; card sweep NULL `extracao_em`; conflict notification |
| imóvel | feat/sw-extr-imovel | 154 | matrícula → imovel_dados (nº, cartório, inscrição, situação ônus, título/ônus credor/fonte fill-empty); scanned nº promotion; markup + abertura backfill; structured-read status + retry ≤2 + trigger from /matriculas/extrair |
| certidões | feat/sw-extr-certidoes | 155 (if needed) | vision for scanned manual certidões (bounded); retry ≤2 |
| validation gate | feat/sw-extr-validacao-gate | 156 | ledger; GET/POST validation endpoints; generation refusal while pending; FE modal |

## Manual-only contract data (no file source — by design)

Negociação (valor, parcelas, favorecidos, termos, posse, confissão, permuta terms), financiamento,
intermediários/corretagem, org settings (`org_dados_cadastrais`), testemunhas, e-mail of parties,
assinatura data, contract modelo, the operator's choice of which matrícula atos are quoted, policy constants
(`politica.py`), certidão consulta situação cadastral (PJ). Documented in
`KB § CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md`.

## Status

- 2026-09-22: roadmap + contract authored; wave 1 dispatched.
- 2026-09-23: waves 2–3 shipped to prod (d1dc3f834); handoff below.

## Handoff — 2026-09-23 (noctusai-1b → the next extractor session)

**Success definition (owner):** extraction 100% functional and feeding the DB; the generator consumes it and produces a contract 100% correct and 100% complete from a REAL card; shipped. Never report the flow as working without generating live from a real card and diffing it against the reference contract.

### Where things live
- **Extraction (seed)** `seed/lib/backend/noctusai_lib/integrations/documents/`: `transcription.py` (ladder text-layer → vision; JPEG render, `RenderDpiPolicy`, `force_vision`, QR-aware crop), `real.py` (identity prompt/fields), `name.py`, `rg.py`, `nacionalidade.py`, `misfile.py` (content-only `tipo_provavel` — logs, never retypes), `capacidades.py` (doc type → fields it can supply), `matricula_marcacao.py` (marker + boilerplate removal, offset-tracked). Stamp list: `integrations/media/pdf_text.py::_PROVENANCE_STAMP_PATTERNS` + `clean_extraction_output`.
- **SW wiring**: `card_hub/identidade_extracao_service.py` (fill-empty with provenance; disagreement → `cliente_campo_conflitos`), `matriculas/qualificacao_service.py` (matrícula parties auto-fill vinculado clientes), `matriculas/preenchimento_service.py` (imóvel_dados fill), `card_hub/proveniencia/{fontes,linhagem}.py` (field → source catalog; §0a of `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/CONTRACT-FIELD-PROVENANCE-MAP.md` is autogenerated + test-enforced).
- **Generator** `card_hub/contrato_gerador/`: `carregador` → `derivacao.avaliar` (`falta`/`bloqueia`/`avisa`) → `contexto` → `documento.renderizar`; `validacao_extracao` is the D2 gate (409 `EXTRACAO_PENDENTE_VALIDACAO`).
- **E2E harness (read-only, real data)** `products/social-wiring/backend/tests/e2e_contrato/harness.py` — readiness, gate, in-memory render, gap trace, diff vs a reference `.docx`. Redacted by default; `--mostrar-valores` only in a private terminal/scratch.
- **Reference contracts** `products/social-wiring/contracts/01–08*.docx` (git-ignored, PII, read-only). 08 = RODRIGO / EUROVILLE.

### Owner rules in force (memory `feedback_sw_contract_rules_owner_2026_09_23`)
- Sellers don't need certidões (existing ones still validated). Every former orange aviso blocks: profissão; witness e-mail (digital); intermediário % derived from the Negociação config (no per-party typing); itens integrantes / ad corpus block only when UNANSWERED; foro = comarca derived from the imóvel-page matrícula text (never typed, never the city).
- RG/CPF is ONE checklist item with CIN and CNH slots; one suffices if it yields both numbers. CIN (órgão IIGDR) ⇒ RG == CPF is valid. **No real CIN exists yet** — build CIN extraction only when the owner supplies one.
- Imóvel address comes from the property table; the matrícula address only warns on divergence. The contract's matrícula is the imóvel-page upload.
- Strip validation boilerplate from every PDF extraction. Audit every action. Real PII stays in local scratch — never in the repo, commits, tests, fixtures or reports.

### Measured on the real corpus
- ~37% of sampled `cliente_documentos` are misfiled (5 CNHs typed `rg`, a birth certidão typed casamento, roteiro/ads PDFs as identity/address docs). Persisting `tipo_provavel` needs a column + product decision.
- Vision-read identifiers (protocols, contract numbers, CPF/CNPJ roots) come back fluent but wrong (single-digit swaps); text-layer numbers are exact. Check digits first, then the D2 gate with the crop; record `texto` vs `ia_visao` (see `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/CERTIDOES-LEVANTAMENTO-LEARNINGS.md`).
- `temperature` can't be passed on the pinned Anthropic SDK — render quality is the determinism lever.
- Open gaps: CNH `rg_orgao` unstable without a printed issuer; one real matrícula's `numero_matricula` stays None; no misfile classifier on the imóvel side (matrícula/IPTU/CND).
- Matrícula qualificações carry party data the contract needs (Regina's profissão came from the matrícula, not contract 08).

### DB guards you will hit
- `matricula_extracoes.texto_extraido` is write-once after `concluida`; sanctioned rewrites are the marker strip (154) and boilerplate-line deletion (165, verified in SQL against a list mirrored from `_PROVENANCE_STAMP_PATTERNS` — keep the parity test green when adding patterns).
- `imovel_dados` título/ônus value ↔ `_origem` pairing (166). Core `audit_logs` is append-only (053).
- Core realdb tests are opt-in (`NOCTUS_REALDB_TESTS=1`) and refuse the prod project.

### State at handoff
- Prod = d1dc3f834. On dev, not yet shipped: SW migrations 165 + 166, matrícula-qualificação auto-fill, realdb opt-in. After shipping, run per org `matriculas.backfill_service.backfill` (strip stored boilerplate) and `qualificacao_service.backfill_aplicar_campos_vinculados`.
- RODRIGO (contrato c8ea4072): readiness `pronto`; generation held by the D2 gate (5 pending + 5 conflicts, owner decides in the validation modal). Diff vs 08 = 0.52 similarity: seller certidões list missing (consulta hard-deleted; owner: ignore for now); "RESIDENCIAL EUROVILLE"/condomínio wording needs the owner-approved ONE7515 move (not done); ONE representative's nacionalidade/estado civil/CRECI região missing; 7 template-wording diffs awaiting the owner's choice (reference vs template).
- noctusai-1b still owns integration/shipping and three in-flight fixes (core test-org audit erasure, SW Contatos e2e, primary-write guard restore contradiction). Message noctusai-1b before touching those files.
