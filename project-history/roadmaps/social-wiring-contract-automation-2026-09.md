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
| T3 | Next social-wiring deploy | `noc-ship` / `predeploy_check` run for social-wiring | Migrations 105–112 are on `dev` but unapplied; the Contratos, certidões, matrícula, qualificação and negociação screens error until they are |
| T0 | Already fired — recurrence N=3 | Three retention-sweep primitives with no scheduler (`NOC-REMEDIATE[retention-sweep-scheduler]`) | DRY rule: N=3 must formalize; retention dates are stamped but nothing purges, so the user's LGPD retention choice is not enforced |
| T4 | A third copy of a card/matrícula route helper appears | `_auth_parts` duplicated in `imovel_hub/router.py` + `matriculas/router.py` (N=2 left after card_hub consolidated) | Consolidate before the third copy ships |

**Today's status**: T0 fired (not yet worked). T1, T2, T3, T4 not fired.

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

## Phase 2 — F6 data wave: store what the contracts use (DEFERRED — fires on T2)

| # | Title | Files | Trigger | Verify recipe (write it now, run it when it ships) |
|---|---|---|---|---|
| P2.1 | Replace the empty `Complementos` provider (`NOC-REMEDIATE[contrato-f6-campos-missing]`) with stored fields: título aquisitivo phrase, posse prazo/marco/prorrogação/multa diária, ônus credor/quitação, signing platform, corretagem payer/marcos/favorecido link, intermediário qualification | `app/modules/card_hub/contrato_gerador/dados.py` provider + new migration + panels | T2 | Generate a contract for each of the 6 variants on staging data; each opens in Word with no lint findings |
| P2.2 | Permuta as a parcela tipo, several permuta imóveis per deal, per-imóvel act selection role, permuta deed/ITBI payer | negociação estruturada + matrículas selection | T2 | A permuta deal renders both imóveis' literal descriptions in Preço and Posse |
| P2.3 | Titular as an `atendimento_partes` row (or a titular certidões path) so the titular's certidões reach the generator | card_hub partes + certidões routes | T2 | A card whose titular is the seller renders the seller's 12 certidões |
| P2.4 | Certidões the contracts cite but the system lacks: IPTU and condomínio CND, company and previous-owner certidões, "negativa com apontamentos de homônimos" | certidões registry + migration | T2 | The certidões clause lists the imóvel group with IPTU number and date |

**Why not now**: the office's answers (T1) change several of these fields (e.g. Q4 encargo, Q12 multa diária, Q13 permuta despesas); building them before the answers risks rework.

## Phase 3 — apply the office's policy answers (DEFERRED — fires on T1)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P3.1 | Turn each answered question into its `politica.py` value; remove the matching aviso | `app/modules/card_hub/contrato_gerador/politica.py` | T1 | The readiness panel no longer shows the aviso for an answered question |
| P3.2 | Confirm the correct prices of sample contracts 01 and 08 (Q15) and use them as the first real generation check | local samples only (never committed) | T1 | Generating those deals from their card data matches the agreed price |

## Phase 4 — go-live of Phase 1 (DEFERRED — fires on T3)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P4.1 | Apply migrations 105–112 in order through the deploy flow, then run every P1.x verify recipe | `products/social-wiring/backend/migrations/105…112` | T3 | `supabase_migration_list` shows 105–112; each P1.x recipe passes |

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

## Open questions (to revisit at trigger time)

- **Q-office**: the 15 policy questions on the office page (canonical wording, Lei 6.515/77, multa rescisória, rescisão encargo, corretagem on rescisão, FGTS parcela shape, meaning of `saldo`, TJSP/TRF3 mapping, company and previous-owner certidões, certidão validity, pendência deadlines, posse daily fine, permuta costs, signature block, prices of contracts 01 and 08).
- **Q-template**: does the office want to edit the clause wording in Word later? Today the wording is reviewable text in `contrato_gerador/modelo_texto.py`, built into `.docx` at runtime.
- **Q-titular**: model the titular as a parte, or give certidões a titular path (P2.3)?

## Decision log

- **2026-09-14**: Seed placement — civil-status fields, matrícula act segmenter, `docx_render` (docxtpl, LGPL server-side) and pt-BR text helpers in the seed; certidão parsers, negociação tables and generator rules in the product.
- **2026-09-14**: Migrations 105/106 (and everything after) are applied at the next deploy, not now.
- **2026-09-14**: TJSP certidões (email-delivered) are uploaded manually; Serasa, TJSP e-SAJ and e-PROC are manual-upload types; the API `tjsp` type stays unchanged.
- **2026-09-14**: The `.docx` template is derived by Claude from the 8 samples and reviewed by the office.
- **2026-09-14**: Imóvel documents and matrícula text follow the same retention mechanism as card documents.
- **2026-09-14**: F5 = build the generator now and gate the gaps (not "data wave first", not "wait for the office").
- **2026-09-14**: Merged-tip gates at the end of Phase 1 — social-wiring backend 3823 passed; seed domain + documents + docx_render 910 passed; frontend tsc clean, vitest 1354 passed across 110 files, vite build clean.

## Retrospective (filled at first trigger fire)

*To be filled when T1, T2 or T3 fires.*

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
