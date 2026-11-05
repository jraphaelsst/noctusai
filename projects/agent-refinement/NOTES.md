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
