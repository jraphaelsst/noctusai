# Agent refinement — tech-lead running log

## Wave 1 — slice returns

### W1-S4 frontend-engineer — merged 13b809e94
- Commits c408363be (L1 + canon) · 7f228e16e (fix-on-contact). Canon `frontend/frontend-craft-canon.md` 857 lines, 66 URLs verified (LBI art. 63 unverified — planalto timeout).
- L1 67 → 79 lines (52 body). Over the ~64 target: §3b sections + 10 new rules.
- Fixed on contact: frontend.md:40 invalidate advice + staleTime vs seed 5-min default; useMemo section → canon §1.3; 01-CORE.md rewritten to code reality; asleep banners on 02/03/04; 2 out-of-glossary glyphs.
- Audit corrections: seed `Dialog` is NOT Radix (no focus trap/return; Radix = CardHubDialog*); react-hook-form declared in 4 FEs but used once; dual-React vitest gap fixed 2026-05-29 (only in symlinked worktrees); React 18 not 19.
- Wave-3 todo: INDEX.md:487 prototype row still says "never mock-data" (stale vs mockup-first); CLAUDE/frontend.md:20 asleep-products note; no FE domain docs for social-wiring/agents/monica.

### W1-S5 devops-engineer + ops-steward — merged
- Commits b1155a51a (canons + L1) · 66d18ac08 (fix-on-contact). `devops/sre-craft-canon.md` 505 lines · `devops/ops-craft-canon.md` 285 lines. 23 agent tests passed via hw_admission.
- devops L1 body 62 → 65 (44 frontmatter lines = 38 owns_kb); ops-steward 33 → 51.
- Fixed: 05-INFRASTRUCTURE (raw VPS IP removed, Caddy/LE → CF tunnel, title), prod-cache-container backup stub, ci-security-gates (claimed image scan that NO workflow runs; action versions).
- 🔴 OWNER: Supabase org plan reads `free` ⇒ no managed daily backups; no dump job in repo ⇒ prod DB RPO undefined; Storage never backed up. Deploy secrets backups (257 tgz) only ON the VPS; n8n volumes unbacked. Log rotation EXISTS on host (daemon.json 10m×3, journald 1G/7d) but not in git.
- Wave-3 todo: INDEX prod-cache-container row stale; chatbot-operational-readiness.md:34 false "managed daily backups" claim (backend-owned); raw IP left in production-deploy.md:163,255 (merge-flow text), INSTRUCTIONS/06-TECH-STACK.md:265, WORKFLOWS/README.md:9; noc-daily-ops skill needs cadence/alert-classification/backup-age steps; ledger-append tool idea; leftover Coolify volumes on VPS.

### W1-S3 backend-engineer — merged
- Commits b0a863ac3 · a72117811. `backend/backend-craft-canon.md` 628 lines + `backend/postgres-craft.md` 289 lines.
- L1 body words 1,752 → 1,138 (target ~1,000; the 75-path owned-KB block is ~270 words). No pointer dropped; moved narrative grep-verified at destination.
- Audit corrections: Idempotency-Key IS read (commerce refunds router.py:383 + RPC money_sql.py:213; EventInbox, jobs dedupe_key exist) → example B generalizes them; the "no timeout" clients do pass per-request timeouts — real issue = fresh httpx client per call.
- Fixed: 01-CORE get_current_admin (MFA gate, platform authz), asleep banners 02/03/06/08, 04-DATABASE snapshot flag, 05 heading.
- Wave-3/2 todo: jobs-organ.md candidate; agents + social-wiring backend domain docs; 06-THERAPY user_metadata roles claim (asleep).

### W1-S2 security + agents-security — merged
- Commits 8fee81c06 · 998660e62. appsec-craft-canon 605 · secure-code-review-checklist 181 (83 items, 46 keeper-covered) · incident-response-playbook 268 · ai-agent-security-canon 445 · audits/julia-2026-11 108 (status rows moved out of the catalog verbatim + 2026-11-05 re-check).
- L1 security 41 → 58 (+WebFetch, llm-bot-security ownership → agents-security); agents-security 39 → 51.
- Fixed: lgpd.md broken pointer + misplaced §, webhook-signatures fail-closed-in-prod rule + numbering + adopter re-check, llm-bot-security wrong claims, threat-model stale pointer.
- Audit corrections: conversation_rate_limit.py / anomaly.py have NO callers on dev (dead code claimed as wired); real gap = SW Julia triage returns `erro` and lets turns through when Redis is down (julia_protecao_service.py:367-369) — P2 (P1 if org daily cap unset). erp-certidoes = CVSS 4.0 8.2 High (8.7 if URL leaked), P0 via LGPD; object path embeds a person's name. Seed webhook has an opt-in `WEBHOOK_REQUIRE_SIGNATURE` (default OFF).
- Dev harness: no PreToolUse guard on WebFetch / vps.exec curl / notify(confirm=True); no project permission allow/deny list → AI canon §13 proposal.
- Wave-3 todo: INDEX.md:381 "four shapes" stale; INDEX layout misplaced security/ node ~:202. feat/jl-sec* (3 branches) local-only, unmerged.

### W1-S6 compliance-reviewer · skill-scout · reverse-engineer · accountant — merged
- 5 commits; keeper pin isolated in f60a04cca (compliance.py:19395 + test 57-58). 292 agent/skill/KB tests passed via hw_admission.
- Canons: code-review-craft 254 · vendored-skills 175 (real register: 0/29 skills vendored) · reverse-engineering-craft 142 · br-tax-advisor-canon 190 · managerial-and-saas-metrics 156.
- L1: compliance 47→58 · skill-scout 46→64 · reverse-engineer 33→51 · accountant 38→50.
- Fixed: eight-way-sync pointer, all 7 owned docs listed, accessibility review lens, testing.md stale banner, dead vendored-register pointers (skill-scout + skill-creator:26), skill-creator spec link, RE description contradiction (vendor material only in `_private-studies/`), dre-structure §8/§1/§7.
- Re-verify: NFS-e Nacional new date 01/11/2026 (CGSN 191/2026, professional sources only); IT-CNAE Fator R practice; split-payment date; NBC TG final CFC texts.
- Wave-3 todo: compliance-reviewer accessibility pointer → `KB § PATTERNS/frontend/frontend-craft-canon.md` (now exists); compliance.py ~19706 message still names skill-scout as meta (minimal fix, own commit); test_agent_kb_alignment fixture uses orchestrator-operator (retiring!) → repoint; skills `version:` → `metadata.version` fleet decision; TaxRegime lacks `real`, no IBS/CBS rows, no subscription ledger (finance organ proposals).

## Wave 2 — slice returns

### W2-S4 tooling-engineer — merged
- Commit 50ea4a7be. `tooling/tooling-craft-canon.md` 588 lines; agent 62 lines (sonnet + Opus comment). Roster: CONTEXTUALIZE.md §4 executors line (+1 name; eight-way-sync demanded it).
- Transfers requested (Wave 3): architect → mcp-tool-conventions, mcp-first-scripts, dev-toolkit-scaffolders, noc-graph, component-bundle-tool, (component-list-and-validation weaker); devops → harness-mods, cache-portable-architecture, cache-as-agent-tool, vectorize-embed-cache-framework, memory-embeddings, corpus-embeddings, push-time-embedding-gate (ci-embedding-cache-gate only if noctusai-3d agrees); unowned allowlist → keeper-pattern-cache, keeper-check-before-docing, cache-locking-discipline, cache-auto-freshness, kb-vector-search, code-embeddings, vector-baseline, code-recurrence-baseline, vector-cost-tracking, vector-calibration, cache-telemetry, unified-query, absorption-tracking, extractor-correctness-vs-mirror, engineer-output-linter, auto-author-scaffolds, doc-to-code-drift, scan-repetition-semantic. Keep unowned: cache-family-index, gate-methodology-sync, doc-staleness-gate.
- Drift (toolkit follow-ups): server.py:268 claims retired legacy aliases still registered; stale docstrings (tools/__init__, dev/__init__, keeper_pattern_cache "~8000 lines" — real 26,079 lines / 178 check_*); mcp-tool-conventions §2 vs server.py registration; scaffold_mcp_tool emits connector-leaf shape not FastMCP register(); cache_backend.py:89-92 silent `except … pass`; gate_sweep has no cli flag; cli.py allow_abbrev default; no tool declares MCP annotations/outputSchema; kb_search/memory_search returned EMPTY (embedding provider unreachable?).

### W2-S5 test-engineer — merged 546f577a4
- Commit 8533a566d. test-engineering-canon 614 · test-harness-playbook 705 (lossless line-check 0 missing) · testing.md 1,137 → 625 (policy + redirect table). Agent 58 lines. Pointer fixes in 5 docs. Roster: CONTEXTUALIZE §4.
- Transfers: di-test-seam, boundary-contract-tests ← backend; (optional) silent-test-failure-from-missing-dep ← compliance.
- Drift: ~15 conftests/3 code files cite old `KB § PATTERNS/testing.md` (no compliance/); duplicate polling helper in agents tests (N=2); Playwright `retries: CI ? 2 : 0` greens flaky specs (CI → noctusai-3d); predicted surviving CANCELLED mutant simples_base.py:47.
- Owner choice: flaky quarantine expiry 14 days (Fowler suggests ~1 week).

### W2-S1 ai-engineer — merged 14b0b96a1
- Commit da1e706f0. ai-engineering-canon 591 · agent-evals 386; agent 53 lines (+WebFetch). Roster: CONTEXTUALIZE §4.
- Transfers: llm-usage, llm-provider-selection, llm-tool-audit, backend/05-AI-FEATURES, GUIDES/agent-creation, INTEGRATIONS/agents-org-specs (+ optional document-extraction-learnings) ← backend.
- Findings: eval judge fixed at claude-sonnet-5 (evals.py:109) also a generator ⇒ self-grading for Sonnet-5 agents; judge emits verdict before reasoning (evals.py:220); no judge-vs-human calibration tool; cache-min warning ~1024 tokens wrong per model (chat.py:26-30); judge uses json_object + hand parser (structured outputs available); no Batch API mode for offline evals.

## Merge-queue translation (noctusai-3d, 2026-11-05) — apply AFTER feat/merge-queue lands + rebase
Point to `KB § PATTERNS/devops/merge-queue.md`, don't restate. Map:
- integrate / FF-push to dev → enqueue to the CI merge queue (`task_branch action=enqueue`); queue lands it; `task_branch action=landed confirm=true` finishes cleanup; `integrate` only = fallback when GitHub Actions is down.
- merged-tip gates / re-run on merged tip before bless → the queue's CI run judges the combined tree; locally only scoped checks (`noctus.dev.gate_sweep`) before enqueueing. "per-branch green ≠ integration green" STAYS.
- train-before-integrate → enqueue each slice when green; queue batches + bisects (train only for joint conflict resolution).
- migration numbers → next free number vs origin/dev AND the queue (`noctus.dev.merge_queue`); enqueue auto-renumbers vs dev; in-queue collision ejects the later entry. NNN_*.sql unchanged.
- Commit ownership stays + "never enqueue on another's behalf unless briefed".
- hw_admission lines: local slot gate covers only LOCAL heavy checks; merged-tree verification is CI.
- Don't touch: noc-self-branch, noc-branch-dispatch, noc-ship, self-branching-mode, branching-dispatch, dev-main-ci-gates, hardware-admission-budget.
- orchestrator-operator: DELETE in this branch with 8-way sync (CLAUDE.md §2, 06-AGENTS, INDEX, CONTEXTUALIZE §4, refs listed in audit-devops-ops-operator.md).

## Follow-up code defects (added during the run)
- S3: `_batched` duplicated twice in seed (N=2 triage); jobs retry_policy.py:39-67 no jitter vs rate_limit full jitter; migration runner needs `-- noc:no-transaction` directive for CONCURRENTLY (runner = noctusai-3d's zone?).
- 🔴 P0 (S5): decide Supabase backups — Pro/PITR or free nightly `supabase db dump` off-host; off-host copy of deploy secrets; n8n volume backup. (Replaces §6 item 3 "no log rotation" → "rotation config not in git".)
- NEW (S4): stored XSS path — FaqAccordion.tsx:43 JSON-LD writes admin-editable FAQ unescaped (server escapes `<` at website_html.py:137, client JSON.parse undoes it at settings.tsx:32). Admin-only write.
- S4: seed Dialog lacks focus trap/initial focus/return; 3 date-format families in seed (N=3 → triage); core uses plain `lazy` on 38 routes; seed ErrorBoundary copy + raw error.message toast; 5,612 *ByTestId vs 1,367 *ByRole.
