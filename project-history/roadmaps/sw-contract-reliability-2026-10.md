# sw-contract-reliability-2026-10 — make social-wiring contract generation reliable, measured, shipped

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: owner asked (2026-10-03) "is automated contract generation reliable already?" — audit said **no** (prod: 7 generated versions, last 2026-09-23; P3 loop 1/5 renders; no automated diff vs signed contracts; silent defaults in the generator).
> Decision: **do everything found, ship to prod** (owner: "i want it all. Ship to prod, you're allowed").

## Origin

The 2026-10-03 audit found the generator itself strict but the pipeline short of the owner's bar ([[feedback-sw-contract-success-definition]]): silent-wrong paths (typed obligations dropped, no review on all-human contracts, financing status defaulted, raw enums printed), no measurement against signed contracts, conflicts from since-fixed readers blocking every test card, CENPROT fields left empty, and recurring corpus cases the template could not express. The roadmaps before this one (`social-wiring-contract-automation-2026-09.md`, `sw-extraction-contract-gate-2026-09.md`, `sw-drive-extraction-2026-09.md`) had drifted — see "Superseded lines" below.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | Office supplies sample wording | a signed contract / office text for procurador, inventariante/espólio, penhora, indisponibilidade | these refuse by name today (`PAPEIS_SEM_REDACAO`, `ONUS_NAO_SUPORTADO`) — the corpus (34 contracts) has 0 cases; never invent legal content |
| T2 | Owner reviews the scorecard wording diffs | entries approved in `tests/e2e_contrato/allowlist.json` | the scorer fails on unexplained wording; only owner-approved deliberate differences pass |
| T3 | Owner confirms PJ wording | reminder `reminder_contrato_pj_qualificacao` closed | PJ qualification is derived from ONE signed contract (866) and raises `PJ_REDACAO_A_CONFIRMAR` on every contract |
| T4 | A deal needs a shape still blocked | readiness shows `CONFISSAO_EM_PARCELA_NAO_DIRETA`, consórcio, posse precária, arras | build from the corpus template at that time |

**Today's status**: none fired; Phase 1 shipped.

## Phase 1 — shipped 2026-10-03

| # | Title | Files | Status | Verify recipe (live-state proof) |
|---|---|---|---|---|
| P1.1 | Harden the generator: no silent omissions/defaults; a review on EVERY generated version; lint catches `None`/empty slots/bracket placeholders; fixed legal terms named in `politica` | `card_hub/contrato_gerador/*`, `contratos_service.py` | **shipped** (feef4cf3f, d780e199e) | generate on a card → version `revisao_juridica_status='aguardando'`; send-for-signature refused until approved |
| P1.2 | Scored comparison vs signed contracts: per-section scorecard, exact numbers, owner allowlist, `noctus.dev.contract_score`, CI golden snapshots | `tests/e2e_contrato/`, `mcp/.../contract_score.py`, `tests/.../golden/` | **shipped** (f30c0911d, 754bcce1a, ea740624b) | `noctus.dev.contract_score()` over `~/.noctusai/private/p3/cards.json` → verdict-only numbers; scorecard in `~/.noctusai/private/scores/` |
| P1.3 | Deterministic conflict resolver for since-fixed reader values (órgão UF, cartório locality, superseded extraction, prefeitura authority) + bank form applied the moment a CPF arrives by any path | `services/divergencia_resolucao.py`, `imovel_hub/conflito_resolucao.py`, … | **shipped** (dfcb4dfc6, 6592ff2a1) | Settings › Pendências → "Resolver conflitos automaticamente" → counts; rows `resolvido_automatico` with `motivo_resolucao` |
| P1.4 | CENPROT coverage: número 41→54/55 right, 0 empty; date 27→49/55; Sonnet escalation only when Haiku doesn't self-validate | `certidoes/cenprot.py` | **shipped** (be3d14cf5) | re-read a CENPROT upload → protocolo + date written, aviso when unvalidated |
| P1.5 | Pacto antenupcial doc type + seed reader → regime + citation fields via D1 | seed `documents/pacto_antenupcial.py`, `pacto_antenupcial_service.py`, mig 191 | **shipped** (7c4ba6c0d) | upload a pacto on a married party → regime + `pacto_antenupcial_*` pending confirmation |
| P1.6 | Aditivos (house + formal styles): model, store, generate, legal review, UI | `card_hub/contrato_aditivo/`, mig 190, FE `card/aditivos/` | **shipped** (de55c9242, 0f9fde5e5) | signed contract → Aditivos section → create, gerar → PDF+docx awaiting review |
| P1.7 | Payment shapes from the corpus: multi-sinal tranches, multi-permuta, FGTS split wording (old Q6 wording appeared in 0/34), parcela split among payees, lien paid by boleto | `contrato_gerador/*`, `negociacao_estruturada_service.py`, mig 192, FE `ParcelaFormDialog` | **shipped** (fde8bca6a, ffcdb4037) | negociação with a split parcela → contract prints `01.1)` sub-items; sums gate |
| P1.8 | Parties + clauses from the corpus: anuente, PJ qualification (866, flagged), pacto citation, RNE/RNM, "Cartório de Registro de Imóveis" (34/34), ônus `ja_quitado` (867) + usufruto (839), free-text obligations printed + review items, imóvel certidão real resultado | `contrato_gerador/*`, `partes_service.py`, mig 193, FE `QualificacaoContratoForm`, `ParteContratoCampos` | **shipped** (b237ee344, 66337e40a, 1d63de87c) | anuente spouse prints with "na vigência da Lei 6.515/77"; PJ party shows the amber confirm box |
| P1.9 | FE: legal-review copy for zero-extracted versions; certidão prefill follows a late CPF; admin auto-resolve button | FE | **shipped** (f9bb4d961, d0fb48b51, 714a349a8) | — |

**Behavior guarantee**: a contract is either refused by name or generated and awaiting a final legal review; nothing typed is silently dropped; scoring is verdict-only (no personal data leaves `~/.noctusai/private/`).

## Phase 2 — deferred

| # | Title | Trigger | Verify recipe |
|---|---|---|---|
| P2.1 | Procurador / inventariante / penhora / indisponibilidade wording | T1 | render a fixture with the office sample; lint clean; owner diff |
| P2.2 | Owner-approved allowlist entries | T2 | `contract_score` → `aprovado` on ≥1 real deal |
| P2.3 | Aditivo payment amendments accept the new shapes (split, valor_fgts, grupos) — needs aditivo parcela storage | T4 | aditivo with a split parcela renders sub-items |
| P2.4 | Consórcio ônus (897 template exists; no `situacao_onus` value), posse precária (141/863), arras confirmatórias, buyer "e sua esposa" | T4 | per-shape render test from the corpus |
| P2.5 | Bank-form extraction writes `valor_fgts`; FGTS adjustment paragraph (855/881/895) | next extraction wave | ficha upload fills `valor_fgts` |
| P2.6 | Comunhão parcial before 26/12/1977 also requires a pacto | owner decision | gate `faltando` for that regime/date |
| P2.7 | Route or retire the deal-level `escritura_pacto`/`registro_pacto` slots (078, archive-only) | owner decision | — |
| P2.8 | CENPROT harness gets each party's expected CPF so a "different consulta" file classifies itself | next CENPROT pass | harness reports it as `outra_consulta`, not wrong |

## Anti-goals

- ❌ Inventing legal wording the corpus does not contain — refuse by name instead.
- ❌ Scoring against values typed from the answer key (circular); score extraction against documents first, flag contract divergence separately.
- ❌ Personal data in git: answer keys, scorecards and transcripts stay in `~/.noctusai/private/`.

## Open questions

- **Q1 (owner)**: comprovante de residência in a relative's name — corpus shows **no evidence** either way (48/61 files image-only, 0 found in another name) ⇒ still a doubt (owner rule 2026-10-03: accepted only if signed contracts show it).
- **Q2 (owner/office)**: confirm the PJ qualification wording derived from 866 (T3).
- **Q3 (owner)**: "Pacto antenupcial" type was added (owner's "everything we can automate"); confirm the checklist rule (separação convencional, participação final, comunhão universal ≥ 26/12/1977).

## Superseded lines in older roadmaps (drift resolved 2026-10-03)

- `sw-extraction-contract-gate-2026-09.md` D2 "backend refuses generation while anything is pending" — superseded by `Politica.revisao_final_unica=True` (c7adb605f, 2026-09-30): only OPEN conflicts refuse; machine values are recorded and reviewed once per contract (and since P1.1 every generated version requires that review).
- `social-wiring-contract-automation-2026-09.md` "Q-endereco OPEN, blocks the first real contract" — resolved: the contract reads the imóvel-page matrícula's `endereco_registro_texto`; the Phase 1 header's "not deployed / nothing changes until T3" is stale (T3 fired 2026-09-16).
- `sw-drive-extraction-2026-09.md` status stops at P0a — P0c, P1, P2, P3, P4 ran; verdict-only results live in `~/.noctusai/private/p{2,3,4}/findings.md`.
- The FGTS wording from office answer Q6 ("através do uso de FGTS e financiamento imobiliário") appears in 0/34 signed contracts — replaced by the corpus wording (P1.7).

## Decision log

- **2026-10-03**: owner — do everything, ship to prod; implement recurring corpus cases too; run the conflict resolver org-wide.
- **2026-10-03**: CENPROT "different consulta" file (889) is not a misread — document-first; contract divergence is a separate flag.
- **2026-10-03**: payment shapes the owner asked for (multi-sinal, multi-permuta, separate FGTS) have 0 corpus examples — implemented by generalizing the single-instance wording; FGTS renders the corpus split wording either way.

## Retrospective (filled at first trigger fire)

*To be filled.*
