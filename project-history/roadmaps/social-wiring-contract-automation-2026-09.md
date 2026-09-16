# social-wiring-contract-automation-2026-09 — Promessa de Venda e Compra generated from the funnel card

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: the office assembles every "Instrumento Particular de Promessa de Venda e Compra de Bem Imóvel" by hand-copying the previous contract, and the 8 signed samples carry numbering, reference, extenso, gender-agreement and price errors.
> Decision: **ship the structured data (F1–F4) and a generator that refuses with a named missing-data list (F5) now; fill the missing fields (F6), apply the office's policy answers and enforce retention when their triggers fire.**

## Origin

On 2026-09-14 the user asked to automate the Promessa from the social-wiring funnel card, after the Contratos tab (F0, migration 106) landed. A gap audit showed the card lacked structured certidões, matrícula acts, civil qualification and deal terms, and that a generator needs all of them. The architect placed the reusable pieces in the seed (civil-status fields, matrícula act segmenter, `.docx` renderer, pt-BR legal-text helpers) and kept domain rules in the product. The user decided: build the generator now and gate the gaps; office policy questions go to the office; migrations are applied at the next deploy.

The template spec derived from the 8 samples (no personal data) is kept locally, gitignored, next to the samples: `products/social-wiring/contracts/f5-template-spec.md`. The office answers its open questions on the private page https://claude.ai/code/artifact/9f9379ab-08e3-48a0-bf45-eb4497c4ea23.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | Office answers the 15 policy questions | Answers saved on the office page (artifact republished with non-empty answers) | Each answer is a one-line change in `contrato_gerador/politica.py`; until then the generator emits an aviso per pending decision |
| T2 | User approves the F6 data wave | User request, or the first real generation attempt refused for a `Complementos` field | Every one of the 6 contract variants is refused today; F6 is what makes a contract actually come out |
| T3 | Next social-wiring deploy | `noc-ship` / `predeploy_check` run for social-wiring | **Corrected 2026-09-16**: the live schema is current through 113 (the `supabase_migrations` ledger is incomplete for social-wiring and must never be used to judge applied state — probe the schema). The migrations this deploy applies are **114–118**; until then the termos, ato-detalhes, certidão-situação, data-casamento and imóvel-certidão surfaces error |
| T0 | Already fired — recurrence N=3 | Three retention-sweep primitives with no scheduler (`NOC-REMEDIATE[retention-sweep-scheduler]`) | DRY rule: N=3 must formalize; retention dates are stamped but nothing purges, so the user's LGPD retention choice is not enforced |
| T4 | A third copy of a card/matrícula route helper appears | `_auth_parts` duplicated in `imovel_hub/router.py` + `matriculas/router.py` (N=2 left after card_hub consolidated) | Consolidate before the third copy ships |

**Today's status (2026-09-16)**: T1 **fired and applied** — the office answered all 15 questions on 2026-09-15 and each answer is now generator behavior. T2 **fired and delivered** — the F6 data wave shipped (migrations 114–118 + panels), and all six contract variants generate. T3 **fired** — this deploy. T0 still open (three retention sweeps, no scheduler). T4 still open (`_auth_parts` duplicated, N=2).

> **Every slice carries TWO recipes.** Test-recipes are green at merge (numbers in the decision log). The verify-recipes below are live-state checks — none can run until T3 applies the migrations.

## Phase 1 — structured data + gated generator (SHIPPED to `dev`, not deployed)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P1.1 | Seed: `estado_civil` / `regime_bens` identity fields + averbação precedence + `rg.is_same_as_cpf` | `seed/lib/backend/noctusai_lib/integrations/documents/{types,civil_status,rg,real,fake}.py` | **shipped** (855a8679) | Upload a synthetic certidão de casamento with a divórcio averbação on a card; the suggestion reads `divorciado` |
| P1.2 | Seed: matrícula act segmenter (char offsets, never rewritten text) | `seed/lib/backend/noctusai_lib/integrations/documents/matricula_atos.py` | **shipped** (1cb88095) | Transcribe a real matrícula; the acts list covers the whole text and each act's text matches the PDF byte for byte |
| P1.3 | Seed: `docx_render` IO module (Protocol + Fake + Real on docxtpl + factory) | `seed/lib/backend/noctusai_lib/integrations/docx_render/` | **shipped** (1b99b4e8) | Covered by P1.12 in production (a generated `.docx` opens in Word) |
| P1.4 | F1 certidões estruturadas (migration 107) — backend + card panel | `app/modules/certidoes/`, `frontend/src/components/CertidoesPartePanel.tsx` | **shipped** (cc4667f9, 733a1410) | On a card parte: link a consulta, upload a TJSP PDF, confirm número/emissão/resultado; `certidao_resultado_acessos` gets a row on view |
| P1.5 | F2 matrícula estruturada (migration 109) — acts, título/ônus sources, contract selection + UI | `app/modules/matriculas/`, `app/modules/imovel_hub/`, `frontend/src/components/MatriculaAtosContainer.tsx`, `pages/Matriculas.tsx` | **shipped** (a214e6bb, 84fc56c7) | Select acts on a contract; the preview text equals the matrícula slices; selecting another imóvel's matrícula is refused |
| P1.6 | F2 security follow-ups (migration 111) — text-read access log, imóvel retention surface, imóvel match on selection, write-once trigger | `app/modules/matriculas/estrutura_service.py`, `app/services/{documento_store,documento_retencao}.py`, `KB § PATTERNS/security/lgpd.md §10` | **shipped** (e5448530) | Open a matrícula's acts → `imovel_documento_acessos` row `text_view`; an UPDATE of `texto_extraido` on a concluded extraction fails in SQL |
| P1.7 | F3 qualificação civil (migration 110) — extraction suggestions, rg≠cpf guard, contract completeness + card panels | `app/modules/card_hub/{identidade_extracao,documento_checklist,compradores}_service.py`, `frontend/src/components/QualificacaoCompletudePanel.tsx` | **shipped** (73fccba8, 1c7774b2) | Save a cliente with RG = CPF → 400 with the pt-BR message; a married parte without a linked cônjuge shows "cônjuge" missing |
| P1.8 | F4 negociação estruturada (migration 108) — parcelas, favorecidos, intermediários, posse, permuta link, testemunhas + panels | `app/modules/card_hub/negociacao_estruturada_*.py`, `seed/.../domain/real_estate/parcelamento.py`, `frontend/src/components/card/NegociacaoEstruturadaPanel.tsx` | **shipped** (535bc878, bed1d499) | Add parcelas on a real deal; "saldo não alocado" reaches 0 when Σ parcelas = valor negociado; a third testemunha is refused |
| P1.9 | Settings + agentes financeiros take the RLS client via `Depends` (no mock.patch in tests) | `app/dependencies.py`, `app/routers/settings_router.py`, `app/modules/agentes_financeiros/` | **shipped** (535bc878) | Settings → imobiliária loads and saves for a non-admin user (RLS path) |
| P1.10 | Seed: pt-BR legal-text helpers (extenso, ordinais, prazos, datas) | `seed/lib/backend/noctusai_lib/domain/texto_ptbr.py` | **shipped** (954a13b5) | Covered by P1.12 (the rendered text round-trips every `R$ X (extenso)`) |
| P1.11 | Seed: `ApiError` keeps the parsed error body (`body`, `code`, `details`) | `seed/lib/frontend/src/api.ts` | **shipped** (ff86ee05) | In production, a 400 with `error.details` shows its field list in the Gerar contrato panel |
| P1.12 | F5 generator (migration 112) — policy defaults, switches, numbering, agreement, lint, `gerado` versions + "Gerar contrato" panel + imóvel retention rows | `app/modules/card_hub/contrato_gerador/`, `frontend/src/components/GeradorContratoContainer.tsx`, `pages/Settings.tsx` | **shipped** (954a13b5, ff86ee05) | Open Gerar contrato on a real card: readiness lists the `Complementos` fields (expected refusal until F6); after F6, generate and open the `.docx` in Word — clause numbers consecutive, references correct, matrícula text literal |

**Behavior guarantee**: nothing changes in production until T3. After T3, the Contratos card gains certidões/matrícula/qualificação/negociação data entry, and "Gerar contrato" shows readiness but refuses every contract until F6.

**Why ship now**: the data entry is useful on its own (it replaces free-text fields the office types today), and the generator's refusal list is the F6 work order.

## Phase 2 — F6 data wave: store what the contracts use (SHIPPED 2026-09-16 — T2 fired)

| # | Title | Files | Status | Verify recipe (live-state proof) |
|---|---|---|---|---|
| P2.1 | Per-deal contract terms: posse (prazo/marco/parcela), permuta reverse posse, itens integrantes, ad corpus, seller obligations, ônus payoff, confissão juros/garantia, corretagem payer + trigger parcelas; parcela tipo `permuta` with a multi-ativo link; intermediário qualification (pessoa_tipo, documento, e-mail, endereço, representante, favorecido); contract `assinatura_data` + per-contract `prazo_pendencias_dias` | `app/modules/card_hub/negociacao_estruturada_*.py`, `contratos_service.py`, `migrations/114`, `frontend/src/components/card/TermosNegocioSection.tsx` | **shipped** (a1a735e6, 8f862966) | On a real deal: fill Termos, add a permuta parcela carrying two imóveis, mark a parcela as triggering corretagem; those items leave the readiness list |
| P2.2 | Matrícula act details: seed deterministic extractor (natureza, date, parties + CPF, creditor, instrument, referenced acts, per-field confidence), `matricula_ato_detalhes`, título-aquisitivo phrase, ônus creditor, previous owners + last-sale date, per-imóvel act roles (objeto/permuta) | `seed/.../documents/matricula_ato_detalhes.py`, `app/modules/matriculas/{ato_detalhes,titulo}_service.py`, `migrations/115`, `frontend/src/components/matricula/MatriculaAtoDetalhesEditor.tsx` | **shipped** (86ee5e52, b4b84842) | Transcribe a matrícula; each act shows extracted details with confidence; confirm the título phrase; previous owners appear with the 5-year certidão requirement |
| P2.3 | Titular certidões + previous-owner role: `certidoes_por_cliente`, `GET /api/certidoes/clientes/{id}/resultados`, `vincular-cliente`, papel `antigo_proprietario`, `negativa_com_homonimos`, company situação cadastral | `app/modules/certidoes/**`, `migrations/116`, `frontend/src/components/CertidoesPartePanel.tsx` | **shipped** (6d4fc934, cc7ec83a) | The card titular gets its own certidões panel; a CNPJ consulta carries situação and shows "exigida no contrato" per the office rule |
| P2.4 | Imóvel certidões group + identity dates: `cnd_iptu`/`cnd_condominio` types with structured extraction, IPTU inscrição, matrícula certidão date, `GET /api/imoveis/{codigo}/certidoes`; marriage date + estado-civil certidão emission date through the real extraction ladder; office settings (signing platform, posse daily fine, pendências prazo) | `app/modules/imovel_hub/documentos_service.py`, `migrations/118`, `seed/.../documents/{types,civil_status,real,fake}.py`, `migrations/117`, `app/routers/settings_router.py` | **shipped** (224c9ee0, 13bbea97, dc51654d) | Upload an IPTU CND → número/emissão extracted; upload a certidão de casamento → marriage date suggested; Settings carries the platform + daily fine |
| P2.5 | Generator wired to real storage: every former `Complementos` field read from its table, `Complementos` (dataclass, provider, seam, marker) deleted, titular certidões resolved so `Pessoa.certidoes` is no longer optional, readiness items carry a `destino` screen target | `app/modules/card_hub/contrato_gerador/**` | **shipped** (ec27a505) | **All six spec §1.3 variants generate** with `faltando == []` and `bloqueios == []` (`TestVariantes::test_each_variant_generates_end_to_end[1..6]`); the saved version opens with consecutive clause numbers, correct cross-references and literal matrícula text |

**What shipped instead of the original plan**: P2.1–P2.4 were written as deferred rows gated on T2; the office's answers (T1) arrived first, so the wave was built with the answers already applied — which is why no rework was needed. P2.5 was not in the original plan: it is the wiring slice that turned stored data into a generated contract.

## Phase 3 — apply the office's policy answers (SHIPPED 2026-09-15/16 — T1 fired)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P3.1 | All 15 answers turned into generator behavior: Lei 6.515 chosen by marriage date (before/after 26/12/1977); rescisão = multa (= sinal) + proven costs; one FGTS+financiamento parcela (a separate `fgts` parcela is refused); company certidões when ativa/inapta/baixada < 5 years; previous-owner certidões when the last registered sale is < 5 years; certidão freshness < 30 days; estado-civil certidão < 90 days; office daily fine, applied to each party in permuta; the receiving party pays ITBI + registry; witnesses identified by CPF | `app/modules/card_hub/contrato_gerador/{politica,derivacao,contexto,frases,modelo_texto}.py` | **shipped** (1a96d726) | Readiness shows no pending-question avisos; answers that ruled out an alternative became fixed rules, so only the Q1 items, the Lei 6.515 cut-off and the day/year limits remain configurable |
| P3.2 | Confirm the correct prices of sample contracts 01 and 08 (Q15) | local samples only (never committed) | **answered, data fix outstanding** | The office confirmed: contract 01's declared price is right and its parcel split is wrong; contract 08's contract price is right and **the card's value is wrong**. Correcting that card is a production-data edit for the office, not a code change; the gate already blocks Σ parcelas ≠ price |

## Phase 4 — go-live of Phase 1 (DEFERRED — fires on T3)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P4.1 | Apply migrations **114–118** in order, then run every P1.x and P2.x verify recipe | `products/social-wiring/backend/migrations/114…118` | T3 — **firing 2026-09-16** | The live schema carries `atendimento_negociacao_termos`, `matricula_ato_detalhes`, `certidao_consultas.situacao_cadastral`, `clientes.data_casamento` and the `imovel_documentos` extraction columns; each recipe passes. **Judge applied state from the schema, never from `supabase_migrations`** — that ledger is incomplete for social-wiring (its last row is 101 while the schema was current through 113) |

## Phase 5 — enforce retention (T0 already fired — schedule next)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P5.1 | One seed cron-sweep registry that `DocumentoStore.varrer_expirados`, `financiamento_service.varrer_retencao` and `estrutura_service.purgar_texto_expirado` register into, wired once by the product scheduler | seed persistence/scheduler seam + social-wiring scheduler | T0 | A document past `retencao_ate` in staging is purged on the next sweep and logged |

## Anti-goals (explicit non-goals)

- ❌ "Type clause numbers, references or extensos into the template." They are computed and linted — hand-typing is the source of the samples' errors.
- ❌ "Render a contract with a blank or a guessed value." A missing field is a named refusal, never a placeholder.
- ❌ "Normalize or rewrite the matrícula text." The contract quotes it literally, typos included; selection is by act offsets.
- ❌ "Foreign-key social_wiring into `erp.*` for parcelas." `erp.parcelas_contrato` is a post-signing ledger in another live product.
- ❌ "Apply these migrations outside a deploy." User decision (2026-09-14).
- ❌ "Commit or quote the real contract samples." They carry real CPF/RG/bank data; the folder is gitignored.
- ❌ "Believe a pytest timeout taken under parallel load." Gates run with `--timeout=180`; a timeout is re-run before it is called a verdict. Under a six-agent dispatch the 60s default produced two confident, wrong "deterministic hang" diagnoses.
- ❌ "Run a gate against whatever tree the primary happens to be in." `predeploy_check` defaults to the primary checkout: pinned at a worktree it is evidence, unpinned it silently measured a tree 40 commits behind and returned green.

## Open questions (to revisit at trigger time)

- ~~**Q-office**~~: **answered 2026-09-15** — all 15, applied in P3.1.
- ~~**Q-titular**~~: **answered** — certidões got a titular path (`certidoes_por_cliente`), not a parte row.
- **Q-artifact** 🔴 **open, user's decision**: the saved version is an **ABNT PDF**, while the 2026-09-14 decision was an editable `.docx` (PDF only at signing). The `.docx` is now an internal intermediate — contract §5 and the pre-existing tests make PDF the stored artifact. Keep PDF, or store both?
- **Q-template**: does the office want to edit the clause wording in Word later? Today the wording is reviewable text in `contrato_gerador/modelo_texto.py`.
- **Q-identity-docs** 🔴 **open, user's decision**: the `rg` and `cpf` upload types are still `ativo = false` (migration 057 withholds them pending a human LGPD intake), so identity extraction runs only from certidões de casamento/nascimento. Run the intake and enable them, or leave as is?
- **Q-procuração**: procurador/inventariante contracts stay refused — no sample carries that wording. The office owes a sample before it can be built.
- **Still homeless by design** (named refusals, never invented values): `onus_quitacao='ja_quitado'` (stored by 114, no sample clause → `ONUS_QUITACAO_SEM_REDACAO`), `obrigacoes_vendedor` and `permuta_obrigacoes_entrega` (stored, no clause prints → aviso), and the permuta quote rendering without rich-text formatting.

## Decision log

- **2026-09-14**: Seed placement — civil-status fields, matrícula act segmenter, `docx_render` (docxtpl, LGPL server-side) and pt-BR text helpers in the seed; certidão parsers, negociação tables and generator rules in the product.
- **2026-09-14**: Migrations 105/106 (and everything after) are applied at the next deploy, not now.
- **2026-09-14**: TJSP certidões (email-delivered) are uploaded manually; Serasa, TJSP e-SAJ and e-PROC are manual-upload types; the API `tjsp` type stays unchanged.
- **2026-09-14**: The `.docx` template is derived by Claude from the 8 samples and reviewed by the office.
- **2026-09-14**: Imóvel documents and matrícula text follow the same retention mechanism as card documents.
- **2026-09-14**: F5 = build the generator now and gate the gaps (not "data wave first", not "wait for the office").
- **2026-09-14**: Merged-tip gates at the end of Phase 1 — social-wiring backend 3823 passed; seed domain + documents + docx_render 910 passed; frontend tsc clean, vitest 1354 passed across 110 files, vite build clean.
- **2026-09-15**: The office answered all 15 policy questions. Answers that ruled out an alternative became fixed rules rather than switches; only the Q1 items, the Lei 6.515 cut-off date and the day/year limits stayed configurable.
- **2026-09-16**: **Storage vocabulary is canonical.** The generator's `posse_marco='parcela_financiamento'` was dropped rather than mapped — it assumed the marco parcela *is* the financiamento parcela, true of one sample and false in general. The marco now names its parcela (`posse_marco_parcela_id`) and the printed number is computed.
- **2026-09-16**: **Readiness carries a screen target.** `faltando[].destino = {tela, rota, ancora, ids}` from one table; the card is not deep-linkable (the dialog owns its subpage in local state), so a card destino returns `/clientes` plus the subpage to select rather than inventing a query param the SPA ignores.
- **2026-09-16**: The permuta value is the permuta parcela's own `valor` — no side-car field, so it sits inside Σ parcelas by construction.
- **2026-09-16**: The `supabase_migrations` ledger is incomplete for social-wiring; applied state is judged by probing the live schema. Prod was current through 113, so this deploy applies 114–118 only.
- **2026-09-16**: Merged-tip gates at the end of Phase 2 (tip ec27a505) — social-wiring backend 4151 passed; seed documents + domain 1199 passed; frontend tsc clean, vitest 1504 passed across 117 files, vite build clean. Deploy cut at `7e5f5ad6` with CI green on both workflows.
- **2026-09-16**: Deploy coordination across four concurrent sessions — one owner blesses, the others hold pushes to a declared cut sha. Another session's migrations (core 045, academia/agents 006-009) ride to the prod branch **unapplied**; applying them early would break every product's next build, because `build-scope.txt` is derived from `deploy_scope='live'` and the build refuses a slug with no compose service.

## Retrospective (T1, T2 and T3 all fired 2026-09-15/16)

**What the plan got right.** Shipping the gated generator first (Phase 1) made the refusal list the work order for Phase 2: every `Complementos` field was already named, typed and consumed, so the data wave had a contract to build against instead of a guess. Six parallel slices landed with no substantive collision.

**What the plan got wrong.** Phase 2 was written as four deferred rows waiting on T2, and Phase 3 as the answers arriving later. In practice the office answered first, so the wave was built with the answers in hand — the deferral bought nothing, and the one row nobody had planned (P2.5, the wiring slice) was the row that actually produced a contract. Lesson: when a phase's only blocker is someone else's answer, plan the shape of the work anyway; it costs nothing and the phase ships intact when the answer lands.

**What nearly went wrong, twice, for the same reason — a verdict measured against the wrong thing.**
1. Two confident "deterministic hang" diagnoses came from a 60-second per-test timeout tripping under six concurrent agents. The test was fine; the machine was loaded. A timeout is not a verdict.
2. `predeploy_check` defaults to the primary checkout. Three green "ready" verdicts had been computed against a tree 40 commits behind with uncommitted files, and a peer session independently made the same class of error (asserting a stale-tree read as fact about migration 045) within the same hour. The tool's docstring already warns about it — the gap is that the dangerous behavior is the default and the failure mode is a green verdict. That is a silent error in the §1 sense and wants a refuse-not-null: the gate should refuse when the tree it is about to measure is behind its remote or dirty.

**Tooling drift worth fixing.** `branch_pointer` commits its ledger row to the primary's local `dev` *before* discovering the tree is dirty, stranding the commit and blocking every later push; `task_branch start` leaves a worktree without `node_modules`, so every frontend engineer hand-links three package directories; `noctus.dev.catalog` writes into the primary checkout as a side effect of a read-shaped call.

## Composes with

- `KB § PATTERNS/security/lgpd.md` §10 — public-registry documents are personal data; retention and access-log decisions are made together.
- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — `docx_render` follows it.
- `project-history/roadmaps/erp-processos-venda-2026-07.md` — the ERP's post-signing contract lifecycle this roadmap deliberately does not reuse.

## File trail

- `products/social-wiring/backend/migrations/107_certidoes_estruturadas.sql` … `112_contrato_versao_contexto_gerado.sql`
- `products/social-wiring/backend/app/modules/card_hub/contrato_gerador/`
- `seed/lib/backend/noctusai_lib/integrations/docx_render/`, `…/documents/matricula_atos.py`, `…/documents/civil_status.py`, `…/domain/texto_ptbr.py`
- `seed/lib/frontend/src/api.ts`
- This doc.
