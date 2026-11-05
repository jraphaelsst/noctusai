# Audit: devops-engineer · ops-steward · orchestrator-operator (read-only, 2026-11-05)

I edited nothing in the repo. Evidence comes from file:line references and from read-only greps of `.github/workflows`, `seed/docker`, `deploy/fleet`, `products/*/backend/Dockerfile` and the KB.

---

## 1 · devops-engineer (`.claude/agents/devops-engineer.md`, 106 lines)

### Verdict
The material is strong, but it is the most overloaded agent on the roster. **owns_kb lists 37 docs (about 7,000 KB lines), not about 29.** The L1 file is 106 lines against a target of 45–65. About a third of it repeats CLAUDE.md §1 or reads like incident write-ups. The **reliability-engineering canon is missing**: no SLOs or error budgets, no RPO/RTO, no restore drill, no incident severity scale or postmortem home, no supply-chain provenance, and actions are not pinned by SHA. The container and deploy depth is world-class. The SRE depth is close to empty.

### Leanness issues
- **It duplicates §1.** L54 and L87 restate cache-first, twice, and §1 already says it. L62 repeats the PROD-ONLY rule. L70 repeats the prod-exposure rule. L71 repeats main/dev and ship-on-ask. The agent-context-architecture anti-pattern "Inline universal-rules duplication" forbids this.
- **Some lines are incident narratives, not rules:** L60 (uid 65532, a 3-month backstory), L78 (OpenSSH_9.6p1), L84 (a 6-clause tmp_cleanup spec), L85 (11 cache-path sites, fcntl), and L86.
- **Seven cache/vector lines (L81–L82, L85–L88) form one family.** `cache-family-index.md` already exists for them.
- **The "Owned KB depth" block (L100–103) lists 11 of 37 docs**, so the declared territory is only partly visible.

### Strengths to keep
- The container debug chain: git→file→manifest→inspect→exec→logs, with "Docker Desktop is NEVER truth" (L57).
- Dev↔prod parity is ranked as the highest-recurrence drift (L61).
- The deploy-config 3-legged contract (L63).
- `predeploy_check` must verify or block (L72).
- The off-host watchdog with heartbeat, 2-run debounce and alert-on-change (L67). Its own "Limits" section (prod-watchdog.md:100) is unusually honest.
- Hardware admission on measured capacity (L68).
- Tunnel ingress derived rather than hand-edited (L60).
- `prod_consent` refuses to write consent on the owner's behalf (L70).
- Sanitization classify-before-delete (L73).
- `noctus.vps.*` reads freely and requires confirmation for writes (L74).
- The prod compose already has partial hardening: `cap_drop` ×7, `read_only` ×7, `security_opt` ×7, 19 healthchecks.
- All 19 product Dockerfiles set `USER`.
- `build-and-push.yml:67` uses least-privilege `permissions:`, and all 10 workflows declare `permissions:`.

### Gaps (ranked)
1. **No backup or DR canon.** "RPO" and "RTO" appear 0 times in the KB (case-sensitive), and "restore drill" appears 0 times. `prod-cache-container.md:80-90` reads "Backup — Phase 2 follow-up … Future P3.2". Supabase daily backups exclude Storage objects and keep 7 days on Pro; PITR is a paid add-on. Nothing records which plan or restore path we rely on. There is no "VPS dies, rebuild from zero" runbook with a measured time to recover.
2. **CI supply chain.** Every action is pinned by tag: `actions/checkout@v7` ×28, `aquasecurity/trivy-action@v0.36.0`, `gitleaks-action@v3`, `docker/*@v4/v7`. The trivy-action tags were force-pushed to malicious commits on 2026-03-19, and that is exactly the class of attack SHA pinning stops. `ci-security-gates.md` has no pinning rule. There is no SBOM, provenance or cosign step (grep finds 0 hits in the workflows). Prod images default to a mutable tag: `docker-compose.prod.yml` has `image: ghcr.io/jraphaelsst/noctus-core:${NOCTUS_IMAGE_TAG:-latest}`. Base images are not digest-pinned. `seed/docker/Dockerfile.frontend-base:14` uses `FROM node:20-alpine`, and **Node 20 is EOL** per nodejs.org (it matters less if it is used only in the build stage, but it is still unpatched).
3. **No SLOs or error budgets.** "SLO" appears in 2 KB files, "error budget" in 0. `deploy/fleet/latency-budgets.json` (p95 shell/read/write) is a latency SLI with no availability SLO, budget or burn-rate alert. The watchdog is binary up/degraded/down.
4. **Incident response has no depth.** L90 is the only L1 rule with **no `→` pointer**. There is no severity scale, IC/comms/ops role split, postmortem template or incident register. The 2026-10-11 freeze postmortem lives inside `prod-watchdog.md` §1, and `project-history/retrospectives/` holds ship retros, not incidents.
5. **Container log rotation.** The prod compose has no `logging:`/`max-size` (grep finds 0). The json-file default is unbounded, a known way to fill a disk on a single VPS. Verify `/etc/docker/daemon.json` on the host before claiming the gap; this audit could not read the host.
6. **Capacity and observability.** The watchdog "is not a metrics system" (prod-watchdog.md:104). An 8 GB / 2 vCPU host froze, and there are no USE/RED trends or headroom forecast. Mentions of OTel and Sentry exist, but nothing in the canon says how to use them.
7. **No DORA measurement.** Deploy frequency, lead time, change-fail rate and recovery time are derivable from `ship-consent.ndjson`, `deploy_image` rollbacks and the watchdog state, but nobody computes them.
8. **`05-INFRASTRUCTURE.md` is stale.** At 29 lines it says "Let's Encrypt SSL" and lists n8n, while the fleet runs behind a Cloudflare tunnel. It also commits the raw VPS IP into the KB.
9. **The hardening baseline is uneven.** `cap_drop` covers 7 of about 20 services and `mem_limit` covers 5. Nothing maps it to the CIS Docker Benchmark or says what a new service must carry.

### Proposed new L1 one-liners
- **Reliability is budgeted, not felt.** Every prod surface gets an availability and latency SLO, and alerts page on error-budget burn, not on raw causes. → `KB § PATTERNS/devops/sre-craft-canon.md §2`
- **A backup that was never restored is a hope.** Each data store declares RPO/RTO and its backup mechanism (Supabase plan or PITR, Storage objects, cache-pg, VPS config), and a quarterly restore drill records the measured recovery time. → `KB § PATTERNS/devops/sre-craft-canon.md §5`
- **Pin what executes: actions by full SHA, base images by digest, deploys by immutable tag or digest. Never `:latest` in prod.** A mutable tag is a re-pointable supply chain (trivy-action, 2026-03). → `KB § PATTERNS/devops/sre-craft-canon.md §6` · `ci-security-gates.md`
- **Incidents: declare, assign IC, mitigate first, blameless postmortem within 5 days, every action item has a named destination.** → `KB § PATTERNS/devops/sre-craft-canon.md §4` (this replaces the pointer-less L90)
- **Every prod container carries the hardening baseline:** non-root, `cap_drop: [ALL]` plus explicit adds, `no-new-privileges`, healthcheck, memory limit, rotated logs. → `KB § PATTERNS/devops/sre-craft-canon.md §7`
- **Cache/vector platform: one family, one line.** → `KB § PATTERNS/common/cache-family-index.md`. This replaces L81, L82, L85, L86, L87 and L88; the per-doc pointers move to the depth block.

### Trim plan (lossless: each detail removed already exists in its target doc)
| Line(s) | Action |
|---|---|
| L54, L87 | Delete. §1 already carries the rule. Keep the `cache-as-agent-tool.md` pointer in the depth block so owns_kb stays mirrored. |
| L62 | Cut to "Dev fleet dormant; prod-first-contact ⇒ predeploy_check + CI-green → KB § …dev-fleet-dormant.md". The detail is in dev-fleet-dormant.md §§24-64. |
| L70 | Cut to one clause plus pointer. The detail is in prod-exposure-consent.md. |
| L60 | Drop the backstory and uid; keep "derive, check in_sync + DNS CNAME". The uid 65532 detail is already at tunnel-ingress-source-of-truth.md "Operational footgun". |
| L67, L68, L79 | Cut each to ≤1 sentence. The details are in prod-watchdog.md §2–4, hardware-admission-budget.md §2, and ci-deploy-prod.md. |
| L78 | Merge into the L79 line as "forced-command keys → ssh-deploy-key-restrictions.md". |
| L81, L82, L85, L86, L88 | Collapse into one cache-family line. Keep the cache-deploy-mirror "row count must match" clause, which is high-value. |
| L84 | One clause: "tmp_cleanup: you own the doc; the caller is fixed by the doc." Its re-homing depends on the orchestrator-operator decision. |
| L100–103 | Rewrite as 6 grouped rows listing all 37 pointers. |

Net effect: about 106 → about 66 lines, with 5 new rules added.

### Craft-canon KB doc: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/sre-craft-canon.md` (owned by devops-engineer)
Outline:
0. Scope and how to use it: a checklist-first doc with a decision tree into the existing devops docs.
1. **Operating context.** Single VPS, one container per product, CF tunnel, GHCR, Actions, managed Supabase, off-host watchdog. Name the single points of failure (host, tunnel, WAHA-on-host, GitHub-cron cadence).
2. **SLIs, SLOs and error budgets.** Four golden signals per product. Availability SLI from the watchdog plus `/api/health`. Latency SLI from `latency-budgets.json`. A starting SLO table. A written error-budget policy (budget exhausted ⇒ freeze feature ships for that product). Multiwindow burn-rate alerting adapted to a 10-minute probe cadence.
3. **Monitoring and alerting.** Symptoms over causes. USE for the host (watchdog host-probe fields). RED for the APIs (RequestTimingMiddleware). Alert-to-incident ratio. Alert-on-change and dedupe (already done). Dead-man switches.
4. **Incident response.** SEV1–3 definitions for this fleet. Roles (IC, ops, comms; one person can hold all three solo, but the role switch is explicit). Comms to customers. Mitigation levers (`deploy_image` rollback, `prod-backup` pointer, `vps_restart`). The postmortem template, kept in an incident register under `project-history/incidents/`. Blameless rules and named destinations for every action item.
5. **Backup and DR.** A data-store inventory with RPO/RTO each: Supabase DB (plan or PITR), Supabase Storage (not in DB backups), cache-pg (regenerable, so RPO=∞ by design and stated), VPS `/srv` config and secrets, GHCR images. 3-2-1. A quarterly restore drill with timings. A host-loss rebuild runbook.
6. **Supply chain and CI hardening.** SHA-pinned actions plus Dependabot for actions. Least-privilege `GITHUB_TOKEN` per job. OIDC where the provider supports it, and the SSH forced-command keys where it does not. Digest-pinned bases. Buildx `--sbom`/`--provenance`. Keyless cosign signing of GHCR images and verify-before-deploy. A SLSA Build L2 target. Trivy plus an SBOM diff.
7. **Container hardening baseline.** A CIS-Docker-mapped checklist: non-root, cap_drop, no-new-privileges, read_only plus tmpfs, mem and pids limits, healthcheck, json-file `max-size`/`max-file`, a restart policy.
8. **Release safety and change management.** Pointer-only into merge-flow docs (owned by noctusai-3d). This section covers only runtime: canary via `deploy_image` snapshot, auto-rollback, post-deploy smoke.
9. **Capacity planning and FinOps.** Headroom targets (MemAvailable, swap, CPU). Trend capture. When to resize the VPS or split hosts. Cost per product (`ai_usage`, VPS, GHCR, Supabase).
10. **Toil and DORA.** A toil inventory (manual fleet recreates, cache mirrors). The four keys plus rework rate derived from the ledgers.
11. **Game days.** Quarterly: kill a container, revoke the tunnel credential, simulate host freeze, restore cache-pg from a dump.
12. **Anti-patterns.** Mutable tags in prod, restart loops hiding root causes, on-host-only monitoring, unbounded logs, untested backups.
13. Sources.

Worked examples (from this codebase):
- **A. The 2026-10-11 freeze, replayed under the canon.** journald stopped about 20 hours early, the host hard-froze after a fleet deploy, and every site returned CF 530. Classified as SEV1. IC is the owner; mitigation was a manual reboot. Time to detect was unbounded, because nothing off-host existed. Action items: the off-host watchdog (shipped), plus the remaining open items: memory headroom SLO, log rotation, staggered deploy waves. This example shows the postmortem template filled in.
- **B. The trivy-action tag compromise against `ci-security-gates.md`.** Our `aquasecurity/trivy-action@v0.36.0` would have resolved to attacker code during the 2026-03-19/20 window, with access to every secret in that job. The fix is SHA pinning plus Dependabot `package-ecosystem: github-actions` plus job-scoped secrets. Show the before/after YAML.
- **C. RPO/RTO table for the fleet.** Supabase DB (Pro daily backups give RPO ≤24 h; PITR gives about 2 min), Storage (not in backups, so RPO is undefined until replication exists), `noctus-cache-pg` (regenerable, so RTO = cold rebuild time measured by `--force`), and `.env.fleet` secrets (where the off-host copy lives). Close with a quarterly drill script that uses `noctus.vps_exec_sql` against a scratch DB.

### Split recommendation
Do not add an SRE agent yet: each extra L1 file is a per-dispatch cost, and there is no recurrence evidence for a split. Do three things instead:
- Move the **cache/vector platform** docs (`cache-as-agent-tool`, `vectorize-embed-cache-framework`, `memory-embeddings`, `corpus-embeddings`, `push-time-embedding-gate`, `cache-portable-architecture`, `openai-mcp`) to a declared shared-owner or architect "platform-tooling" set. Do the same for **harness-mods / hardware-admission / usage-evaluation**, which are dev-harness rather than prod-infra. Those 10 docs are about 1,400 lines that do not belong to production DevOps.
- **Release manager:** this is merge-flow territory. Defer it to noctusai-3d.
- Trigger an SRE split only if N≥3 incidents a quarter or the fleet grows past one host.

### Merge-flow lines — leave for noctusai-3d
- L3 (description: "commits ONLY its own branch")
- L18 `owns_kb: dev-main-ci-gates.md`. This is an **off-limits doc owned by devops**. Tell noctusai-3d that devops holds its owns_kb pointer.
- L24 `ship-consent-riders.md` (bless rider)
- L51 "FF-only releases"
- L64 Deploys + rollback (release bless/promote, FF-only)
- L68 "merged-tip gates" admission clause
- L71 Ship on the owner's ask (bless FF to the newest CI-green commit)
- L76 dev→main CI gates
- L79 deploy-prod.yml FF of the VPS checkout and ref whitelist (the deploy half is runtime; the FF/ref policy is merge-flow)
- L80 pre-push embedding gate (collides with "fast local checks only")
- L84 the patch-id-on-`origin/dev` retirement rule
- L92–93 Commit ownership ("The tech-lead merges")
- L106 composes-with `self-branching-mode.md` and skill `noc-ship`

### Frontmatter issues
- owns_kb has 37 entries. The keeper passes, but the body's depth block mirrors only 11 of them.
- The `description` promises "observability, and incident response", but neither has an owned doc.
- `model: sonnet` is fine for an executor. Consider `higher` effort for incident-mode dispatches.

---

## 2 · ops-steward (`.claude/agents/ops-steward.md`, 33 lines; owns `owner-operations.md` 70, `owner-questionnaire.md` 39; skill `noc-daily-ops` 30)

### Verdict
The best-shaped L1 of the three: lean, rule plus pointer, with a clear autonomy model. The underlying craft is **AI-agent-ops-first and ITIL/SRE-ops-light**. It has autonomy levels and Rule of Two, but no event→incident→problem flow, no measurable alert-fatigue loop, no toil budget, no SLO-based "is the platform healthy" verdict, and no weekly or monthly review template. Two of its rules are currently **unmeasurable or contradicted**.

### Strengths to keep
- Autonomy per action, L0–L3, with a promotion and demotion ledger (owner-operations.md:27-38, 61-65). This is directly in line with the levels-of-autonomy literature.
- Rule of Two and `notify` plan-only (L20).
- "Mechanical first, quote tool and timestamp" (L21).
- `inconclusive`, never green (L22).
- "Changes and exceptions only", plus a dead-man switch on the 07:00 brief (owner-operations.md:45,50).
- The simplest-human-decision taxonomy (owner-questionnaire.md §2–3).
- The data sources really exist: `090_scheduler_runs.sql`, `091_ai_usage.sql`, `admin_operations.py`, and the `prod_watchdog`, `deploy_verify`, `smoke_fleet` and `notify` tools.

### Gaps (ranked)
1. **The alert-fatigue rule cannot be measured.** owner-operations.md:50 and the skill (L22) say "prune alert classes acted on <50%", but nothing records "acted-on". The watchdog state has no ack field, and there is no alert ledger. The SRE target is a 1:1 alert-to-incident ratio with a median of 0 pages a day.
2. **There is an L3 contradiction on tmp cleanup.** owner-operations.md:34 lists "tmp cleanup" as L3 for ops-steward. orchestrator-operator.md:76 and devops-engineer.md:84 say orchestrator-operator is the "sole authorized caller".
3. **The ship-consent rule is contradicted.** owner-questionnaire.md:19 says "promote to `main` … Yes/No (literal consent phrase)". CLAUDE.md §1 and ship-consent-riders say "no approval phrase" since 2026-09-24. Only first prod **exposure** (`prod_consent`) is phrase-bound. This is merge-flow-adjacent, so give the wording to noctusai-3d and note it.
4. **There is no event/incident/problem flow.** A failure found in the brief has no path to "declare an incident → devops (L2) → postmortem → problem record → recurring-failure finding". owner-operations.md:38 ("escalate the repeat as a finding") is the only hook.
5. **There is no platform health verdict tied to SLOs.** Health is a list of tool outputs, not "within budget / burning / exhausted per product". This depends on devops gap 3.
6. **There is no toil budget or toil ledger.** L3 actions are toil by definition; the ledger tracks autonomy, not volume. Automate an L3 action that repeats more than N times a week.
7. **Backup and restore freshness are not in the daily or weekly check.** It should check the last successful backup age per store and the last restore-drill date.
8. **Cadence stops at weekly.** There is no monthly review (cost trend, SLO report, autonomy promotions, alert-class review) and no quarterly game day or access review.
9. **Reminders are session-bound** (owner-operations.md:58). It is an acknowledged open item, but the brief's own dead-man depends on it.

### Proposed new L1 one-liners
- **Every alert sent is logged with its outcome (acted / noise / duplicate); a class under 50% acted-on over 4 weeks is pruned or folded into the brief.** → `KB § PATTERNS/devops/ops-craft-canon.md §3`
- **Health is a budget verdict, not a tool dump:** per product, report within / burning / exhausted against its SLO. → `KB § PATTERNS/devops/ops-craft-canon.md §2` (depends on the devops SLOs)
- **A failure that recurs is a problem, not an event:** a 2nd occurrence in 14 days opens a problem record with a named owner. → `KB § PATTERNS/devops/ops-craft-canon.md §4`
- **Toil is counted:** every L3 run is logged; an action over N runs a week becomes an automation proposal (L1). → `KB § PATTERNS/devops/ops-craft-canon.md §5`
- **Backups are checked like jobs:** last-success age per store daily, last restore drill monthly. → `KB § PATTERNS/devops/ops-craft-canon.md §6`

### Trim plan
Nothing material to trim. L24 ("Never: credentials, --no-verify, …") partly repeats L19 and the §1 rule; it could fold into L19. Adding the 5 rules puts it at about 40 lines, still inside budget. The skill must sync: add a monthly section and the alert-outcome step.

### Craft-canon KB doc: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/ops-craft-canon.md` (owned by ops-steward)
Outline:
0. The operating model for one founder plus agents, and why ITIL-lite rather than full ITIL.
1. **Practice map (ITIL-lite).** Monitoring & event management → incident → problem → change enablement (pointer to merge-flow docs) → service request → continual improvement. For each: one sentence, the noc tool, and the owner (ops-steward or devops).
2. **Health verdicts.** Golden signals per product and SLO budget states. "Inconclusive" semantics.
3. **Alert hygiene.** Alert ledger schema (class, sent_at, channel, outcome). The 1:1 ratio target. Digest vs page. Quiet hours. Dead-man switches. The weekly review.
4. **Event → incident → problem.** Declaration triggers (customer-visible, more than one product, unsolved after 1 hour). Hand-off to devops at L2. The problem record and how it links to findings and remediation markers.
5. **Toil budgeting.** Toil definition and inventory. L3 run counts. An automation threshold. A target share of toil.
6. **Backup and DR checks.** The daily freshness check and the monthly drill check. Pointers into the devops canon §5.
7. **Cadence.** Daily, weekly, monthly and quarterly checklists, each with a ≤3-item "today" output.
8. **Autonomy ledger mechanics.** Evidence needed to promote (≥10 clean runs) and immediate demotion.
9. **Anti-patterns.** Status walls, re-asking decided questions, restart loops, alerts nobody reads, green-by-default.
10. Sources.

Worked examples:
- **A. The 2026-10-11 freeze under the daily brief.** The heartbeat went stale 20 hours before the freeze, so the brief should have shown "DEGRADED: journald silent >30 min" the morning before. This walks the event→incident path and the L2 hand-off to devops.
- **B. Alert-class pruning.** WAHA DEGRADED reminders every 6 hours during a known tunnel issue. The ledger shows 1 of 8 acted on, so the class merges into the 07:00 brief while the incident stays open.
- **C. Toil to automation.** `vps_restart` of the same product 3 times in a week trips the toil threshold. That yields an L1 proposal to devops (root-cause the restart loop), per owner-operations.md:38.

### Merge-flow lines — leave for noctusai-3d
- owner-questionnaire.md:19 "Prod exposure — promote to `main` … literal consent phrase". The wording conflicts with ship-on-ask; noctusai-3d decides.
- owner-operations.md:33 L2 "deploy" and :37 "overnight ship grant". These are ship-consent policy.
- The daily-ops skill step 5 `branch_pointer action=list` (branch debt): reading it is fine, but its semantics belong to the branching redesign.
- ops-steward.md has no merge-flow lines.

### Frontmatter issues
- `tools` has no Write or Edit. That is correct for an advisor, but it means ops-steward **cannot update its own autonomy ledger** (owner-operations.md §5, skill guardrail L27), so ledger writes must go through the tech-lead. Say so explicitly or add a narrow write path.
- `description` is good. The owns_kb (2) is mirrored.

---

## 3 · orchestrator-operator (`.claude/agents/orchestrator-operator.md`, 235 lines, owns none)

### Verdict: retire, or at most narrow to nothing git-related. Here is the evidence.
- **Usage is dead.** The `.claude/dispatcher.md` Outbox holds only two ticks, both from the pilot (`2026-05-11 21:25` "first pilot tick" and `21:40` "tick 2 — partial (aborted …)"). Since then the file has been used as an architect handoff log (2026-09-11 sweep notes), not as a task queue. The file was last modified Sep 11.
- **The model is stale.** It cherry-picks onto `origin/main` (L55–58), validates `origin/main..HEAD` (L48), and may push `main` on `push-main: yes` (L116). The house model is now worktree off `origin/dev` plus `task_branch`, and soon one merge queue into dev. Every git behaviour in it is superseded by the noctusai-3d redesign.
- **It breaks §1 "No workarounds".** L169–177 "Workaround recipe": patch an unrelated PROJECT.md with `[DEFERRED-…]` annotations to get past the phase-state hook. That is an agent editing project state to bypass a gate, which is the exact shape §1 forbids.
- **It breaks the lean-L1 house shape.** It runs 235 lines under a "procedure-doc carve-out" (L10). The procedure should live in a skill or KB doc, as ops-steward/noc-daily-ops does.
- **It describes a known inconsistency and leaves it:** L26, `## <task-id>` vs `### YYYY-MM-DDTHH:MM`.
- **The only live, non-git value is `tmp_cleanup`'s sole-caller role** (L72–85). owner-operations.md:34 already lists tmp cleanup as an ops-steward L3 action, so the natural home exists.

### Strengths worth salvaging (into KB, not an agent)
- The outbox entry shape (L87–103) and "failure ⇒ stop and outbox verbatim, never retry" (L179–183). This is a good dispatch-receipt pattern for whatever queue noctusai-3d builds.
- "Detect-don't-presume", verifying brief claims against the tree (L154–165). This is already the §1 "codebase is source of truth" rule.
- The file-disjoint overlap check (L120–152). It belongs to the collision-class/merge-queue design, which is noctusai-3d's.

### Recommended path (proposal only; the decision and its timing belong to noctusai-3d and the owner)
1. Re-home `tmp_cleanup` as an ops-steward L3 action (weekly). Update `tmp-artifact-cleanup.md` and devops-engineer.md:84 in the same commit.
2. Mark `autonomous-operator-via-subagent.md` as superseded, with a pointer to the merge-queue design.
3. Delete the agent and update every reference in the same commit (§4 sync rule): `KB § INDEX.md`, `06-AGENTS.md:214`, `parallelization-first-orchestration.md:42`, `methodology-codification-pipeline.md`, `tmp-artifact-cleanup.md`, `ops-steward.md:13` (the "Distinct from" note), `devops-engineer.md:84`, the CLAUDE.md §2 roster, and the `test_agent_archetype_contract.py:64-66` fixture. That fixture is a test of the skip list; keep it with a neutral name.
4. Decide what `.claude/dispatcher.md` is now (a handoff log) and rename or re-document it. This touches the two-session protocol, so it is noctusai-3d's call.

If it is kept rather than retired, narrow it to: a non-git "maintenance tick" runner (tmp_cleanup, cache refresh, hygiene scans) with an L1 of about 40 lines, the procedure in a skill, `owns_kb: [tmp-artifact-cleanup.md]`, and no Agent, push or cherry-pick powers. Even then it overlaps ops-steward L3, so retirement is the cleaner answer.

No craft-canon doc is proposed, since the recommendation is to retire. If the narrowed form survives, its canon becomes a section of `ops-craft-canon.md` (§5 toil automation).

### Merge-flow lines — leave for noctusai-3d (nearly the whole file)
- L3 (description: cherry-pick + push)
- L12–16 (dispatch loop)
- L23 (Kinds: dispatch-engineer, validate-worktree, cherry-pick-and-push)
- L33–42 (dispatch-engineer)
- L44–51 (validate-worktree, `origin/main..HEAD`)
- L53–64 (cherry-pick-and-push, authorship guard)
- L76 (patch-id on `origin/dev` retirement)
- L112–118 (git ownership, push-main)
- L120–152 (no-overlap / file-disjoint rule, a branching-and-merging.md §17.6 mirror)
- L154–177 (detect-don't-presume for branches, plus the phase-state hook workaround)
- L188–190 (one operator per tick, serial dispatch)
- L210 (wakeup cadence)

Non-merge-flow: L66–70 (archive-project), L72–85 (tmp hygiene), L87–110 (outbox/inbox format), L223–231 (symbology, which repeats engineer-seed §10).

### Frontmatter issues
- There is no `model:` line, so it inherits the parent model, which is expensive for a mechanical drainer.
- `tools` includes `Agent`, giving it unbounded spawn power, and `Write/Edit`, though L187 says it never edits the KB. It is over-privileged for its stated scope.
- `description` names `ScheduleWakeup`, and there are 0 references to it in `.claude` or the KB patterns.
- `owns_kb: []` is consistent.

---

## 4 · Sources (each fetched and confirmed 2026-11-05)
- Google SRE Book, "Monitoring Distributed Systems" — https://sre.google/sre-book/monitoring-distributed-systems/ — four golden signals; symptoms over causes.
- SRE Workbook ch.2, "Implementing SLOs" — https://sre.google/workbook/implementing-slos/ — SLO/SLI selection, written error-budget policy.
- SRE Workbook, "Alerting on SLOs" — https://sre.google/workbook/alerting-on-slos/ — multiwindow multi-burn-rate alerts (14.4× over 1h/5m).
- SRE Book ch.5, "Eliminating Toil" — https://sre.google/sre-book/eliminating-toil/ — toil definition, <50% cap.
- SRE Book ch.11, "Being On-Call" — https://sre.google/sre-book/being-on-call/ — alert fatigue, 1:1 alert:incident ratio, ≤2 incidents/shift, actionable pages.
- SRE Book ch.14, "Managing Incidents" — https://sre.google/sre-book/managing-incidents/ — roles, when to declare an incident.
- SRE Workbook ch.9, "Incident Response" — https://sre.google/workbook/incident-response/ — ICS roles IC/CL/OL.
- SRE Book, "Postmortem Culture" — https://sre.google/sre-book/postmortem-culture/ — blameless postmortems, triggers.
- SRE Book ch.8, "Release Engineering" — https://sre.google/sre-book/release-engineering/ — hermetic builds, policy enforcement, high velocity.
- DORA metrics — https://dora.dev/guides/dora-metrics-four-keys/ — change lead time, deploy frequency, failed-deploy recovery time, change fail rate, rework rate.
- PagerDuty Incident Response docs — https://response.pagerduty.com/ — IC role, severity levels.
- Atlassian, "How to run a blameless postmortem" — https://www.atlassian.com/incident-management/postmortem/blameless — postmortem practice. Body text not fully readable; title and topic confirmed.
- The Twelve-Factor App — https://12factor.net/ — config in env, dev/prod parity, logs as streams, disposability.
- Docker build best practices — https://docs.docker.com/build/building/best-practices/ — multi-stage, digest pinning (with trade-off), non-root USER.
- Docker json-file logging driver — https://docs.docker.com/engine/logging/drivers/json-file/ — `max-size` default unlimited; no rotation by default.
- Docker build attestations — https://docs.docker.com/build/metadata/attestations/ — `--sbom`, `--provenance=mode=max`.
- CIS Docker Benchmarks — https://www.cisecurity.org/benchmark/docker — hardening baseline.
- SLSA security levels — https://slsa.dev/spec/v1.0/levels — Build L1–L3 (v1.0 page marked retired; v1.2 current).
- Sigstore cosign, signing containers — https://docs.sigstore.dev/cosign/signing/signing_with_containers/ — keyless OIDC signing.
- GitHub Actions security hardening — https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions — pin actions to commit SHA; minimal GITHUB_TOKEN.
- GitHub OIDC — https://docs.github.com/en/actions/concepts/security/openid-connect — short-lived tokens replace long-lived cloud secrets.
- Aqua, "Trivy supply chain attack: what you need to know" — https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know — trivy-action tags force-pushed 2026-03-19; pin by SHA.
- Supabase backups — https://supabase.com/docs/guides/platform/backups — Pro 7d daily backups; PITR add-on (~2 min RPO); Storage objects not included.
- Node.js previous releases — https://nodejs.org/en/about/previous-releases — v20 EOL.
- Brendan Gregg, "The USE Method" — https://www.brendangregg.com/usemethod.html — utilization/saturation/errors per resource.
- Grafana, "The RED Method" — https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/ — rate/errors/duration per service.
- OpenTelemetry signals — https://opentelemetry.io/docs/concepts/signals/ — traces, metrics, logs, baggage.

Not cited, for lack of a free canonical URL: ITIL 4 (proprietary), and Accelerate (book; the DORA site stands in).
