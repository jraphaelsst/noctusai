# SW lead → proposta → contrato — skeleton, live-tested e2e

Status: AUTHORED 2026-10-09 by noc-2 (session noctusai-89), tech-lead for this project. noc-0 (noctusai-ed) coordinates the tree and collisions.
Contract (both sides build to it, nobody re-derives it): [`CONTRACT.md`](CONTRACT.md).

## Why
The owner is walking deal 876 by hand to learn and harden the SW pipeline. They want the commercial path from first contact to contract to exist end to end, coherent with the funnel stage at every step, and proven by a live test in prod **before** any further extraction work:

> Lead arrives from Meta Ads → card on the kanban, with the imóvel taken from the campaign → a conversation where we ask the lead for documents → first extraction check on basic docs (RG, CPF, CIN, CNH…) → roteiro de visita with 3 imóveis of interest → "visita aconteceu?" with recorded data, so we can measure steps → on yes, the roteiro lists the visited imóveis with a "Gerar proposta" button each → the proposta is its own registry, a card on the atendimento's first tab, opened in a modal for full CRUD → Aceitar / Recusar → accept triggers contract generation.

Out of scope for now (owner: "skeleton first"): message automations around the proposta, the deeper contract-generation pass, and the rest of the extraction (imóvel docs, certidões, Serasa, empresas, financiamento). These are an open owner reminder (`reminder_sw_lead_to_contract_deferred_talks`).

## What exists today (gap audit 2026-10-09, origin/dev c165e69e0)
| Stage | Exists | Missing |
|---|---|---|
| **S1 Intake** | Meta leadgen webhook (HMAC) → `meta_ads_leads` → trigger spawns the card on stage 0 → `ingest_meta_lead` → `leads` row; imóvel linked from the form's `REF` answer (mig 180) | Campaign/ad → imóvel resolution: `campanhas` / `campanha_imoveis` / `campanha_veiculacoes` (mig 065) exist but nothing reads or writes them. Cliente attached late (sweep, 47–65 s, up to 6 h), and the card can't move until then. The 06:00 `sync_all` skips `ingest_meta_lead`. No safe simulation path. |
| **S2 Conversation + docs** | WhatsApp inbox (WAHA webhook → `conversation_messages`); card upload → `identidade_extracao_service` (RG/CNH/CIN/CPF/certidões/comprovante); provenance + human confirm; checklist | Chat has no stored `cliente_id`/`atendimento_id`. No "pedir documentos" action. Inbound media is summarized to text and dropped, never becoming `cliente_documentos`. No type classification at intake. No WhatsApp inbound simulation. HEIC is not accepted. |
| **S3 Roteiro + visita** | `roteiros` / `visitas` (mig 082/104/184), generation dialog, PDF, per-visita Realizada / Não realizada pills, timeline events | No post-visit prompt ("visita aconteceu?"), no roteiro-level yes/no, no structured não-realizada reason, no metrics (`vw_imovel_visita_contagem` unused), no "visited only" list, no funnel coupling |
| **S4 Proposta → contrato** | `visitas.proposta_em` / `proposta_aceita_em` toggles; `registrar_proposta` writes `atendimento_negociacao.imovel_codigo`; funnel `aceitar-proposta` → `processos_venda`; contract generator (`iniciar` / `geracao` / `gerar`) | No proposta table, no "Gerar proposta", no card or modal, no Recusar. Three acceptance paths (visita, funnel, contract) never call each other. |

## Slices (file-disjoint; the map is also sent to noc-0)
| Slice | Owner | Files (exclusive) | Migration |
|---|---|---|---|
| **S4-BE** proposta registry + accept orchestration | **noc-1** (noctusai-2a) | new `backend/app/modules/card_hub/propostas/` (service, router, schemas), its mount line in `card_hub/router.py`, tests | 217 |
| **S1** campaign→imóvel + immediate cliente + lead simulation | **noc-4** (noctusai-b5) | `backend/app/modules/meta_ads/**`, `backend/app/modules/leads/services/meta_ingest_service.py`, new `campanhas` veiculação service + router, FE `pages/campanhas/**` (new) | 218 |
| **S3** visita aconteceu? + metrics + visited list + stage coupling | **noc-2** subagents | `card_hub/roteiros_service.py`, roteiro routes in `card_hub/router.py` (roteiro block only), new `pipeline/funil_eventos` helper, FE `RoteirosSection.tsx`, `ImovelVisitaCard.tsx`, `useRoteiros.ts`, new `VisitaFeedbackPrompt` | 219 |
| **S4-FE** proposta card + modal | **noc-2** subagent | new FE `components/propostas/**`, `hooks/usePropostas.ts`, one `renderPropostas` slot in `ClienteDetailModal.tsx` / `ClienteCardDialog.tsx` Geral | — |
| **S5** post-aceite: certidões for all vendedores + their companies, matrícula extraction | **noc-2** subagent | new `card_hub/pos_aceite_service.py` + its re-run route + FE "Preparando contrato" panel (new component, mounted by S4-FE) | — |
| **S2** chat↔card link + "Pedir documentos" + inbound media → documento + simulate | **noc-2** subagents (or the next idle session) | `routers/whatsapp_router.py`, `services/media_service.py`, `whatsapp_connections_router.py`, `card_hub/documentos_service.py` (accept HEIC), new `services/documento_intake_service.py` | 220 |

Shared helper: the **funnel-stage mover** `pipeline/funil_eventos.mover_por_evento()` is owned by S3 and consumed by S1/S4 by import only (CONTRACT §6). Migration numbers are tentative; each slice re-runs `noctus.dev.next_migration_number` at integrate.

Collision rules: noc-3 (noctusai-ba) owns seed FE/core auth, so nothing here touches `seed/**` or `products/core/**`. `card_hub/router.py` is shared, and each slice edits only its own block; a merge conflict there is mechanical, resolved at integrate.

## Phases
1. **Contract on dev** (this commit).
2. **Build** S1, S3, S4-BE, S4-FE and S2 in parallel, each in its own `task_branch` worktree, each session parallelizing internally with subagents.
3. **Integrate** on dev and re-run the gates on the merged tip (per-branch green ≠ integration green).
4. **Release**: one release lane, prod only on the owner's go.
5. **Live e2e test** in prod through the browser as a user (the deal-876 walkthrough mode): every step validated against the DB, paused, reported. Done = the whole chain works live, with each stage move coherent.

## Live test script (Phase 5, executed by noc-2 through the UI)
1. Register imóvel Al. Liverpool 81 (Reserva do Vianna) and a Meta campaign/ad linked to it (S1 UI).
2. Simulate a Meta lead for that ad (S1 simulate). Expect: card on Qualificação, `atendimento_imoveis.origem='campanha'` with the imóvel, cliente attached at once.
3. Open the conversation from the card; "Pedir documentos" sends the checklist message (S2). The lead (test phone) sends RG/CNH/CIN/CPF; each becomes a `cliente_documentos` row, gets classified and extracted; fields shown with provenance; RG-from-CNH asks for confirmation.
4. Add 2 more imóveis of interest; generate a roteiro with 3; card moves to **Visitas**.
5. After `data_visita`, the "visita aconteceu?" prompt appears; answer yes for 2 and no (with reason) for 1. Metrics update.
6. The visited list shows 2 imóveis with "Gerar proposta"; generate a proposta for one; card moves to **Proposta recebida**; the proposta card is on Geral.
7. Edit the proposta in the modal (valor, parcelas, termos, imobiliária = Tangerino, testemunhas); save; reload; values persist.
8. Recusar a second proposta (reason recorded). Aceitar the first: negociação materialized, contract draft created with imobiliária + testemunhas preset, funnel → processos_venda at elaboração de contrato.
9. Post-aceite (S5): certidões start emitting for every vendedor and their companies, the matrícula is extracted (or flagged missing), and antigos proprietários are certified when the purchase is < 5 years. `GET …/geracao` then shows what is still missing.

## Open owner questions (asked as we reach them, never assumed)
- Q1: on Aceitar, should the atendimento close into **processos_venda** (today's `aceitar-proposta` behavior), or stay on the funil until the contract is signed? (CONTRACT §5.4 assumes today's behavior.)
- Q2: when one proposta is accepted, do the other open propostas of the same atendimento become `recusada` automatically, or stay as they are?
- Q3: should the "visita aconteceu?" prompt be per roteiro (one question, then per-imóvel detail) or per imóvel? (The CONTRACT supports both: the roteiro-level answer fills the per-imóvel ones.)
- Q4: the proposta's validity period (`validade_ate`): is there a default?
- Q5: matrícula EMISSION: should the system request the certidão de matrícula itself (ARISP/ONR, or an InfoSimples product if one exists), or does the office keep uploading it? Nothing in the repo emits matrículas today (CONTRACT §7.2).

## Next phase (owner's MAIN goal, after this skeleton; not built now)
A reliable contract-generation tool: walk through uploading every document one by one; **one dedicated, rule-based extractor per document type** (patterns and parsing, not "let the AI decide"); 100% of file-borne data extracted and stored; an explicit list of the data that must be typed by hand; the generated contract 100% compliant with the data. The skeleton keeps that seam: one `tipo → extractor` interface used by card upload, WhatsApp intake (§2.3) and post-aceite (§7). Memory: `project_sw_reliable_contract_generation_goal`.
