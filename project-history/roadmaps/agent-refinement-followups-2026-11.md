# Roadmap · Agent-refinement follow-ups — 2026-11

**Slug:** `agent-refinement-followups` · **Source:** `archive/projects/2026-11-05/01-agent-refinement/` (archived 2026-11-05; landed on dev as `2eb3ac936`) · **Report:** https://claude.ai/artifact/STw8cXnCtov3zrx3pBKmAj

## Goal
Give every open item the agent-refinement run surfaced a named owner and destination, so archiving the project loses nothing. The craft knowledge itself is already absorbed into the owned canons (`KB § INDEX.md`). This file holds only the residue: defects, owner decisions, and drift.

## Status legend
`[x]` landed · `[~]` in flight (branch named) · `[ ]` open · `[owner]` owner decision · `[peer]` held by another session

## 1 · Owner decisions
- [owner] **Supabase backups (P0).** Org on the Free plan: no managed backups, no dump job, Storage never backed up; deploy secrets backed up only on the VPS; n8n volumes unbacked. Choose Pro/PITR or a nightly off-host `supabase db dump`. → `KB § PATTERNS/devops/sre-craft-canon.md`
- [owner] **Meta Graph versions.** WhatsApp Cloud client `meta_cloud_client.py:21` pins v18.0 (expired 2026-01-26); `_meta_api.py:67` pins v21.0 (sunsets 2027-01-21). The bump itself is integrations-engineer work once approved.
- [owner] **erp-certidoes public-bucket exposure** (CVSS 4.0 8.2): ANPD incident decision + register entry; lawyer questions on the small-agent exclusion and the controller = encarregado conflict. → `KB § PATTERNS/legal/lgpd-privacy-program.md`
- [owner] **Contracts.** D4Sign registrability at Registro de Imóveis ("autorização de registro" clause); PJ powers act + CC 1.015 check (memory `reminder_contrato_pj_qualificacao`). → `KB § PATTERNS/legal/contracts-br.md`
- [owner] **Palette contrast.** Muted text 3.48–3.98 on light, white on pastel status fills 2.0–2.7, dark primary 4.24. → `KB § PATTERNS/design/accessibility.md`
- [owner] **Store / CDC.** `schemas/store.py:34` `guarantee_days` must be `ge=7`; storefront lacks supplier ID, pre-checkout summary and withdrawal channel (Decreto 7.962); `consent.ts` lacks the "acting as operator" section and transfer page; the store is absent from `deploy/fleet/active-scope.txt` (confirm scope first). → `KB § PATTERNS/legal/consumer-ecommerce.md`
- [owner] **agno lens mapping** in `dev_team/MASTER-PROMPT.md`.
- [owner] **Flaky quarantine expiry**: 14 days proposed (Fowler suggests ~1 week).
- [owner] **ADR home** `project-history/decisions/` (architecture-craft-canon §3).
- [owner] **Pilot re-pick**: project-execution §2.12 lists 2 asleep pilots.
- [owner] **LGPD-WARNINGS split** (file + `lgpd_flag` stay security; legal disposition of buckets B/C/D/F → legal-advisor). → `KB § PATTERNS/legal/lgpd-privacy-program.md` §14
- [owner] **Fleet conventions**: skills `version:` → `metadata.version`; owner of `PRODUCTS/**` and `ABSORPTIONS/**` KB docs; INDEX Layout misplaced `security/` node; family-index line "Orchestrator=architect" (`/gc`).

## 2 · Code defects
- [~] Seed webhook accepts unsigned requests when the secret is unset (P0); `WebhookDedup` has no `release()`; `oauth_router` `/refresh` + `/revoke` unauthenticated → `feat/df-seed-webhooks` (integrations-engineer)
- [~] Meta BUC throttle codes 80000–80014 unclassified; `parse_retry_after` ignores HTTP-date and caps at 60s; jobs `retry_policy.py:39-67` has no jitter; `waha:latest` unpinned → `feat/df-vendor-ratelimits` (integrations-engineer)
- [~] FaqAccordion JSON-LD stored XSS; seed `tokens.css:183-187` kills focus outlines + Button has no ring; seed Dialog has no focus trap/return; `formatCurrency(null)` renders R$ 0,00; core Dashboard launcher + seed IntegrationCard mouse-only → `feat/df-seed-a11y-xss` (frontend-engineer)
- [~] Playwright CI retries green flaky specs; social-wiring `test_lead_novo_notice.py` `validate_schema=False` without rationale → `feat/df-test-falsegreens` (test-engineer)
- [~] Migration runner: `-- noc:no-transaction` directive + default `lock_timeout` → `feat/df-migration-runner` (backend-engineer, coordinated with noctusai-51)
- [peer] Julia triage fails open when Redis is down (`julia_protecao_service.py:367-369`) → noctusai-3d, `feat/sw-julia-allowlist-be`
- [peer] Eval judge fixed at the generator model (`evals.py:109`, self-grading); verdict emitted before reasoning (`evals.py:220`); no judge-vs-human calibration; `json_object` + hand parser; cache-min warning per model (`chat.py:26-30`); no Batch API for offline evals → noctusai-3d / ai-engineer, `feat/julia-readiness`
- [ ] Vista Real adapter constructed directly at 6+ sites (DRY N≥3) → integrations-engineer, AFTER `feat/vista-calibration-empty-list` + SW Julia work land
- [ ] TypeScript `strict` off → multi-session frontend migration; needs its own roadmap (pilot products first)
- [ ] `_batched` duplicated in seed (N=2 triage); 3 date-format families in seed (N=3 → must formalize) → backend / frontend via skill `noc-triage`
- [ ] core uses plain `lazy` on 38 routes; seed ErrorBoundary shows raw `error.message` → frontend-engineer
- [ ] p-studio `ProvedorCobranca` beside shared payments (N=2) → triage before any Banco do Brasil adapter (architect)

## 3 · Keepers and tooling
- [ ] Keeper candidates: `check_token_contrast` (ratchet), `check_global_focus_reset` → tooling-engineer, after the a11y slice lands
- [ ] Toolkit drift: `server.py:268` retired-alias claim; stale docstrings (`tools/__init__`, `dev/__init__`, keeper_pattern_cache "~8000 lines"); mcp-tool-conventions §2 vs server registration; `scaffold_mcp_tool` emits the connector-leaf shape; `cache_backend.py:89-92` silent `except … pass`; `gate_sweep` has no CLI flag; no tool declares MCP annotations/outputSchema → tooling-engineer
- [ ] Semantic caches (`kb_search` / `memory_search`) returned empty (embedding provider unreachable?) → tooling-engineer
- [ ] Doc-staleness checks scoped to a commit range miss repo-wide missing paths; run full mode before enqueue (2026-11-05 batch ejection) → tooling-engineer: make `gate_sweep` run full-mode doc-staleness
- [ ] Dev-harness guards: no PreToolUse guard on WebFetch / `vps.exec` curl / `notify(confirm=True)` → ai-engineering-canon §13 proposal, tooling-engineer
- [ ] `union_roster.py` handles only executor-style roster lines → tooling-engineer
- [ ] ~15 conftests + 3 code files cite `KB § PATTERNS/testing.md` (now `compliance/`); duplicate polling helper in agents tests (N=2); predicted surviving CANCELLED mutant `simples_base.py:47` → test-engineer
- [ ] DSAR-locator tool; `bucket:` field on `lgpd_flag` → tooling-engineer + legal-advisor

## 4 · Docs and infra drift
- [ ] KB: outbound-rate-limiting "WAHA pending"; `google.md` §3 YouTube quota units; `whatsapp.md` §6 "CORE one session" → integrations-engineer (partly in `feat/df-vendor-ratelimits`)
- [ ] Domain docs missing for social-wiring / agents backend + frontend; `jobs-organ.md` candidate → backend / frontend engineers
- [ ] Raw VPS IP in `GUIDES/production-deploy.md:163,255` (merge-flow text) → noctusai-3d
- [ ] Leftover Coolify volumes on the VPS → ops-steward (L1 proposal; deletion needs owner approval)
- [ ] Finance organ: TaxRegime lacks `real`; no IBS/CBS rows; no subscription ledger → accountant proposal
- [ ] noctusai-3d git roadmap: P3 freeze stored as data, P4 claims as leases, origin/HEAD detection keeper

## Recovery
The full project folder (NOTES, PROJECT, WAVE2, the seven audits) lives at `archive/projects/2026-11-05/01-agent-refinement/`; ledger row in `project-history/ledger.ndjson` (slug `agent-refinement`).
