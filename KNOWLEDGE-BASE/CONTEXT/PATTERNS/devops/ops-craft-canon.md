# Ops craft canon — running the platform day to day, measurably

> Owner: agent `ops-steward` · procedure: skill `noc-daily-ops` · operating model: `KB § PATTERNS/devops/owner-operations.md`. Engineering side of the same numbers: `KB § PATTERNS/devops/sre-craft-canon.md` (owned by devops-engineer). Born 2026-11-05 (agent-refinement W1-S5). The audit found that the steward's craft was strong on AI-agent operations (autonomy levels, Rule of Two) but light on IT operations: no event → incident → problem flow, an alert-fatigue rule that nothing measured, no toil budget, no SLO-based health verdict, and a cadence that stopped at weekly.

## 0 · What this is, and how to use it

**What.** A lightweight IT-operations practice for one founder plus agents. It borrows the practice names from ITIL 4 and the numbers from Google SRE, and maps each onto a house tool.

**Why ITIL-lite rather than full ITIL.** Full ITIL assumes service desks, change advisory boards and separate teams per practice. We have one owner, a few agent sessions and one host. What we keep is the *flow*: a signal becomes an event, a harmful event becomes an incident, a repeating incident becomes a problem, and a fix becomes a change. Each hand-off has a named owner and a record. The ceremonies are dropped.

**How to use it.**
- **The house mechanism wins.** Autonomy levels, L3 actions and the daily rhythm are decided in `owner-operations.md`. This canon adds measurement and flow on top and does not re-decide them.
- Merge and ship policy (what counts as a deploy approval, the overnight ship grant, branch-debt semantics) belongs to the git/CI redesign. This canon reads those signals and does not define them.
- ops-steward has no Write/Edit tool (`.claude/agents/ops-steward.md` frontmatter). Every ledger below is therefore **written by a tool or by the tech-lead**, never by the steward editing files. §3 and §5 say which.

**Standard term ↔ house term.**

| ITIL / SRE term | House term / mechanism |
|---|---|
| Monitoring & event management | watchdog, scheduler ledger, CI results, `smoke_fleet`, `deploy_verify` → the daily brief |
| Event | any signal in the brief (a failed job, a DEGRADED state, a cost spike) |
| Incident | an event with user impact or lost safety net, declared per `sre-craft-canon.md` §4 |
| Problem | a recurring incident or event class with an owner and a root-cause task (§4) |
| Known error | a problem with a workaround documented in the problem record |
| Change enablement | the git/CI redesign docs plus `predeploy_check` (pointer only) |
| Service request | an owner ask handled as L0–L3 work |
| Continual improvement | the weekly/monthly reviews (§7) plus the house learning loop (`KB § PATTERNS/common/learning-posture-family-index.md`) |
| Toil | an L3 action run |
| Alert | any push to the owner: watchdog email/WhatsApp, `notify`, the in-app bell |

---

## 1 · Practice map (ITIL-lite)

| Practice | One sentence | Tool here | Owner |
|---|---|---|---|
| Monitoring & event management | Collect signals and turn them into a short list of events that matter | `prod_watchdog` · `deploy_verify` · `smoke_fleet` · `public.scheduler_runs` · `public.ai_usage` · `latency_report` · `supabase_advisors` | ops-steward (reads) · devops (builds) |
| Incident management | Restore service fast when an event hurts users | `sre-craft-canon.md` §4; L3 restart ≤ 2; otherwise hand off L2 to devops | IC = owner; ops-steward declares and hands off |
| Problem management | Remove the cause of repeat incidents | problem record (§4) → `findings` / `NOC-REMEDIATE[...]` / roadmap | devops-engineer (root cause), steward (detects recurrence) |
| Change enablement | Make changes safe | pointer: git/CI redesign docs · `predeploy_check` · `deploy_image` rollback | tech-lead / devops |
| Service request management | Do routine asks without friction | L0–L3 autonomy (`owner-operations.md` §2) | ops-steward |
| Service level management | Know whether each product is healthy against its target | SLO budgets (`sre-craft-canon.md` §2) → health verdict (§2 below) | ops-steward reports · owner ratifies targets |
| Information security / backups | Know the data is recoverable | backup-age and drill checks (§6) | ops-steward checks · devops fixes |
| Continual improvement | Get better every week | weekly / monthly / quarterly reviews (§7) | ops-steward runs · owner decides |

---

## 2 · Health is a budget verdict, not a tool dump

**Principle.** "Is the platform OK?" has one honest answer per product: is it within its reliability target? Tool outputs are evidence for that verdict. They are not the verdict. (SRE Workbook, "Implementing SLOs"; SRE Book, "Monitoring Distributed Systems".)

**The verdict per product** (targets in `sre-craft-canon.md` §2 starter table).

| Verdict | Meaning | Brief placement |
|---|---|---|
| **within** | 30-day budget > 50 % remaining and no burn alert | omitted (changes and exceptions only) |
| **burning** | more than 10 % of the 30-day budget consumed in the last 24 h, or budget between 0 and 50 % | Exceptions; Today if the product is core or agents |
| **exhausted** | budget ≤ 0 | Today, with the error-budget policy consequence (feature-ship freeze for that product) |
| **inconclusive** | the history needed to compute the budget is missing | Inconclusive checks, never green |

Also report the golden signals briefly when they explain the verdict: latency over budget (`latency_report`), errors (watchdog failure reasons), saturation (MemAvailable, swap).

**Prerequisite — the budget ledger (design).** The watchdog keeps only its current state in the Actions cache (`KB § PATTERNS/devops/prod-watchdog.md` §8), so a 30-day budget cannot be computed today. Until a per-run history exists, every budget verdict is `inconclusive`, and the brief says so rather than reporting "up" as "healthy".

Proposed record, one row per watchdog run, appended by the watchdog itself to `watchdog-runs.ndjson` on `origin/ledgers` (`KB § PATTERNS/common/ledger-store.md`):

```json
{"ts": "2026-11-05T07:00:12Z", "run_id": "…", "state": "up|degraded|down",
 "products": {"core": {"ok": true, "status": 200, "ms": 412}, "agents": {"ok": false, "status": 530}},
 "host": {"heartbeat_age_s": 61, "journald_last_age_s": 3, "mem_available_mb": 2210, "swap_used_mb": 0, "load1": 0.8},
 "reasons": []}
```

Budget for product P over 30 days = 1 − (failed runs ÷ valid runs), compared against P's SLO. Named destination: a devops slice extending `noctus.dev.prod_watchdog` (it must stay stdlib-only) plus a read helper exposed as a `noctus.dev.*` tool.

---

## 3 · Alert hygiene — make "<50 % acted-on" measurable

**Principle.** Every alert that reaches a human should need a human response. Noisy alerts that fire several times per incident should be tuned toward a 1:1 alert/incident ratio. Frequent low-value alerts cause fatigue, and fatigue makes people miss the alert that matters. (SRE Book ch.11, "Being On-Call".)

**House rule (already decided).** An alert class that is acted on less than 50 % of the time is pruned or merged into the brief (`owner-operations.md` §3). Nothing records "acted on" today, so the rule cannot be applied. The alert-outcome log fixes that.

**The alert-outcome log (design).** One row per alert sent, in `alert-outcomes.ndjson` on `origin/ledgers`.

| Field | Type | Meaning |
|---|---|---|
| `alert_id` | string | stable id: `<source>:<class>:<sent_at>` |
| `source` | enum | `watchdog` · `brief` · `notify` · `scheduler` · `ci` · `bell` |
| `class` | string | the alert class, e.g. `watchdog.degraded.heartbeat`, `watchdog.reminder`, `brief.missing`, `cost.spike` |
| `severity` | enum | `page` (interrupting) · `digest` (in the brief) |
| `channel` | enum | `email` · `whatsapp` · `in_app` |
| `sent_at` | UTC ts | when it went out |
| `incident_ref` | string or null | the incident or postmortem it belongs to, if any |
| `outcome` | enum | `acted` (someone changed something because of it) · `noise` (no action was needed) · `duplicate` (an earlier alert already covered it) · `unknown` (not yet classified) |
| `outcome_by` · `outcome_at` | string · ts | who classified it, and when |
| `action_ref` | string or null | the command, commit or ticket that was the action |

**Who writes what.**
- The **sender** appends the row with `outcome: unknown` at send time: the watchdog's alert step, `noctus.dev.notify`, and the brief job. That is a code change in each sender, so the named destination is one devops/tooling slice. It must use one shared helper (DRY), not three hand-written writers.
- **ops-steward classifies.** At the next morning brief it lists the `unknown` rows from the last 24 h with a proposed outcome. The owner confirms them in one batched pick-one question (`KB § PATTERNS/common/owner-questionnaire.md` §3). The classification is written through the same tool (an `outcome` update row; append-only), never by hand-editing the file.

**Weekly computation (Monday).** For each class over the trailing 4 weeks: acted ÷ (acted + noise + duplicate). Report the classes under 50 %, with their counts.

**What to do with a class under 50 %.** Exactly one of:
1. **Prune**: stop sending it.
2. **Fold into the brief**: it becomes a digest line, not a page.
3. **Retune**: change the threshold or debounce (for example 2 → 3 consecutive runs), then re-measure for 4 weeks.

Record the decision as an owner decision. Never silently drop a class.

**Other hygiene rules.**
- Digest over page: anything that does not need action within an hour belongs in the brief.
- Quiet hours and severity routing are an open house item (`owner-operations.md` Open, D33). Do not invent them here.
- Every alerting path has a dead-man switch: the watchdog for the host, the 26 h flag for the brief.
- Target load: a median of 0 pages a day. The SRE ceiling of 2 incidents per 12-hour shift is a ceiling, not a goal.

---

## 4 · Event → incident → problem

**Flow.**

```
signal ──▶ EVENT (in the brief)
             │  user impact? >1 product? unsolved >1 h? safety net down?
             ├── no ──▶ L3 action if pre-approved (counted, §5) · else L1 suggestion
             └── yes ─▶ INCIDENT (declare; sre-craft-canon.md §4)
                          │  ops-steward: declare + hand off L2 to devops-engineer / tech-lead
                          ▼
                       resolved ──▶ postmortem (SEV1/2 or trigger)
             recurs? (same class, 2nd occurrence within 14 days)
                          ▼
                       PROBLEM RECORD (named owner, root-cause task)
```

**Declaration triggers for the steward** (the same as `sre-craft-canon.md` §4): customer-visible impact; more than one product affected; not solved after 1 hour; a safety net (watchdog, backups, alert channel) is down. The steward **declares and hands off**. It never runs L2 actions itself. The hand-off contains the exact command, the blast radius and the evidence (tool and timestamp), as `owner-operations.md` §2 requires for L2.

**The problem record.** A recurring failure is a problem, not an event. The second occurrence of the same event class within 14 days opens one. Minimum fields:

| Field | Content |
|---|---|
| id · opened | `PRB-YYYYMMDD-<slug>` · date |
| class | the event/alert class that recurred |
| occurrences | dates, with evidence (tool + timestamp) |
| owner | a named agent or the owner (devops-engineer by default for infra) |
| workaround (known error) | what the steward does meanwhile, e.g. an L3 restart with its cap |
| root-cause task | its named destination: a `NOC-REMEDIATE[<class>]` marker, a roadmap entry or a project |
| closed | when the class has not recurred for 30 days after the fix |

**Where it lives.** Until a dedicated store exists, a problem record is a `noctus.dev.findings` entry (or a `NOC-REMEDIATE[...]` marker at the code site when the cause is known), and its id is quoted in the brief's debt list. A `problems.ndjson` ledger on `origin/ledgers` is the proposed home. Named destination: the same tooling slice as the alert-outcome log. The point is that a repeat never stays only "a line in today's brief".

---

## 5 · Toil — counted, budgeted, automated away

**Principle.** Toil is manual, repetitive, automatable, tactical work with no lasting value that grows with the service. A task does not need every trait. Keep toil under 50 % of operational time, and spend the rest on removing it. (SRE Book ch.5, "Eliminating Toil".)

**Here.** Every L3 action is toil by definition (`owner-operations.md` §2): container restarts, re-running failed idempotent jobs, cache refreshes and tmp cleanup.

**The toil ledger (design).** One row per L3 run, in `ops-actions.ndjson` on `origin/ledgers`: `ts`, `action` (`vps_restart`, `job_rerun`, `cache_refresh`, `tmp_cleanup`), `target` (container, job or cache), `trigger` (the event or alert id), `result` (`ok` / `failed` / `escalated`), `minutes` (wall-clock, estimated if unknown). It is written by the tool that performs the action, or by the tech-lead on the steward's behalf. The steward cannot write files. The same ledger is the evidence for autonomy promotions (§8), so one record serves both purposes.

**Threshold.** The same `action` on the same `target` **3 or more times in 7 days** ⇒
1. it becomes a problem record (§4), and
2. ops-steward files an L1 proposal to devops-engineer: root-cause the repeat, or automate the action with a cap and an alert. That follows `owner-operations.md` §2 ("cap auto-retries, escalate the repeat as a finding").

**Budget.** Report monthly: total L3 runs, total minutes, the top three toil sources, and the share of operating time they represent. The target is the SRE ceiling (< 50 %). For a one-founder team, the more useful target is a downward trend month over month.

---

## 6 · Backups are checked like jobs

**Principle.** A backup is a scheduled job, and it fails like any other job. Check its last successful run every day. Prove it can be restored on a schedule. (Data stores, RPO/RTO and the drill procedure are in `sre-craft-canon.md` §5.)

**Daily (in the brief).** For each store in the `sre-craft-canon.md` §5 table that has a backup mechanism: **age of the last successful backup** compared with its RPO.
- Age > RPO ⇒ Exception. Age > 2 × RPO ⇒ Today, and it counts as a SEV3 "lost safety net" (`sre-craft-canon.md` §4).
- A store whose RPO is **undefined** (no backup exists) is reported in **Today** until the owner decides on it. As of 2026-11-05 that is the Supabase DB, Supabase Storage and n8n (see `sre-craft-canon.md` §5 and worked example C there). Silence would be the silent-error shape.
- A check that cannot run is `inconclusive`, never green.

**Monthly.** Days since the last restore drill per store. More than 90 days ⇒ Today item: "schedule the quarterly drill" (L1 to devops-engineer).

**Off-host copies.** Monthly, confirm each store's off-host copy exists. As of 2026-11-05, deploy-local secrets have **no** off-host copy: every safe-pull backup lives in `/opt/noctus/backups` on the same host.

---

## 7 · Cadence

Every review ends in the same output shape as the brief: **Today (≤ 3 items)** · Exceptions · Done for you · Reminders · Debt top-5 · Inconclusive.

| Cadence | Checks (in addition to the previous level) | Owner decisions it may produce |
|---|---|---|
| **Daily** (session start; 07:00 brief) | reminders · health verdict per product (§2) · watchdog state and heartbeat/journald age · failed or missing scheduler runs, including the brief's own dead-man · LLM spend anomalies · backup age vs RPO (§6) · unclassified alerts from the last 24 h (§3) · debt top-5 | classify alert outcomes (batched pick-one) |
| **Weekly** (Monday) | `supabase_advisors` · `latency_report` · `detect_stale_caches` · skill `noc-hygiene` · alert-class acted-on % over 4 weeks (§3) · toil counts and thresholds (§5) · open problem records (§4) · sysstat memory trend (`sre-craft-canon.md` §9) | prune / fold / retune an alert class |
| **Monthly** (first Monday) | SLO report per product: budget used, incidents, burn alerts · DORA five (`sre-craft-canon.md` §8) · cost per product and month-over-month delta (`sre-craft-canon.md` §12) · toil budget (§5) · days since the last restore drill (§6) · autonomy promotions/demotions due (§8) · postmortem action items still open | ratify SLO/budget changes · promote/demote an action · spend decisions |
| **Quarterly** | restore drill for the rotation's store (`sre-craft-canon.md` §5) · one game day (`sre-craft-canon.md` §11) · access review: who holds which keys (deploy keys, watchdog key, GHCR token, Supabase service role) and whether each is still needed · review the starter SLOs | SLO targets for the next quarter · keys to rotate or revoke |

The monthly and quarterly levels are new here. The skill `noc-daily-ops` (v1.1.0) runs all four levels.

---

## 8 · Autonomy ledger mechanics

**Principle.** Autonomy is earned per action from evidence and withdrawn at once after harm. This matches the levels-of-autonomy literature cited in `owner-operations.md`.

**Rules (decided in `owner-operations.md` §2; mechanics here).**
- **Promote one level** after **≥ 10 clean runs** of that action, where clean means `result: ok` in the toil ledger (§5), no incident traced to the action, and no owner reversal. The evidence is the ledger rows; quote their count and date range.
- **Demote immediately** after any incident caused or worsened by the action. Record it in the same edit that reports the incident.
- Record both in the `owner-operations.md` §5 table. The steward cannot edit files, so it drafts the row and the tech-lead writes it.
- A standing owner grant (for example an overnight grant) is per session and lapses. It is never evidence for a promotion.

---

## 9 · Anti-patterns

- **Status walls.** Pasting every tool output instead of the verdict and the exceptions.
- **Green by default.** Reporting "up" when the check could not run, or reporting "healthy" when no budget could be computed.
- **Re-asking a decided question.** Durable answers live in memory or in the accept-with-rationale register (`owner-questionnaire.md` §4).
- **Restart loops.** A third restart in a week is a problem record, not another L3 run.
- **Alerts nobody reads.** Any class under 50 % acted-on that is still paging.
- **Unbounded toil.** "It only takes a minute", every day.
- **Backups trusted on faith.** No age check, no drill, no off-host copy.
- **An L2 action taken under L3 cover.** Deploys, customer messages, data deletion and prod schema are never L3.

---

## Worked examples (from this codebase)

### A · The 2026-10-11 freeze, seen through the morning brief

Facts: host journald and cron stopped about 20 hours before the 01:17 UTC hard freeze, while the sites kept serving (`KB § PATTERNS/devops/prod-watchdog.md` §1). The heartbeat and the off-host watchdog did not exist yet.

Replay with today's mechanisms. The heartbeat would have gone stale within 15 minutes of the scheduling stall, and journald age would have passed 30 minutes. After two runs the watchdog classifies DEGRADED, and WhatsApp carries the alert (the host is still up). On the morning of 2026-10-10 the brief would have shown (times and values illustrative; only the shape is the point):

```
Today
1. DEGRADED since 05:20Z — heartbeat 4h old, journald silent 4h, MemAvailable 410 MB (prod_watchdog 07:00Z).
   Declared SEV2 (safety net + host at risk). Handed to devops-engineer (L2): inspect memory, plan a reboot
   window, hold the fleet deploy. Evidence: watchdog run <id>.
Exceptions
- core/agents budgets: inconclusive (no run history yet).
```

The path: event (DEGRADED) → declaration trigger "safety net down / host at risk" → incident → L2 hand-off to devops (the steward does not reboot hosts) → the deploy is held, which removes the trigger that froze the host. The steward's contribution is noticing and handing off in the morning, not 20 hours later.

### B · Pruning a noisy WAHA alert class

During a known WAHA/tunnel issue (an incident already open, with its owner working on it), the watchdog sends a DEGRADED reminder every 6 hours (`prod-watchdog.md` §4). Over 2 days that is 8 alerts in class `watchdog.reminder.degraded.waha`. The alert-outcome log reads: 1 `acted` (the first alert, which opened the incident), 7 `duplicate` (each with `incident_ref` pointing at the open incident). Acted-on = 1/8 = 12.5 %, under the 50 % rule.

Decision (owner, one pick-one question): **fold into the brief while an incident on the same class is open**. The reminder becomes a digest line ("WAHA DEGRADED, incident PRB-… open, 7 reminders suppressed"). Pages resume if the incident closes and the state comes back. The class is not deleted, because a new WAHA failure with no open incident still has to page. The rule change is a code change in the watchdog's reminder logic (devops slice), recorded as an owner decision.

### C · Three restarts in a week → an automation proposal

The toil ledger shows `vps_restart` on `noctus-nosnolimiar` on Monday, Wednesday and Friday, each after a DEGRADED event, each `ok`. The third run crosses the threshold (§5: same action, same target, 3 times in 7 days). The steward:
1. opens `PRB-YYYYMMDD-nosnolimiar-restarts` with the three ledger rows as evidence and the workaround "L3 restart, cap 2 per day";
2. files an L1 proposal to devops-engineer: "root-cause the nosnolimiar restart loop (OOM? healthcheck? leak?). Evidence: three `ops-actions` rows and the watchdog reasons. Do not raise the retry cap.";
3. stops counting further restarts as routine. Each new one is attached to the problem record.

Why not simply automate the restart: automating the restart would hide the cause, and `owner-operations.md` §2 forbids that ("restart loops hide root causes").

---

## Open (named destinations)

- **Tooling slice** (agent `tooling-engineer`): one shared append helper on `origin/ledgers` for `alert-outcomes.ndjson`, `ops-actions.ndjson`, `problems.ndjson` and `watchdog-runs.ndjson`, exposed as `noctus.dev.*` tools, so the steward can write through a tool without gaining Write/Edit.
- **Skill sync:** done 2026-11-05 — skill `noc-daily-ops` v1.1.0 carries the monthly/quarterly levels (§7), alert classification (§3, `inconclusive` until the outcome log exists) and the backup-age check (§6). Its step 5 wording (`branch_pointer action=list`) stays as it is until the git redesign settles branch-debt semantics.
- **tmp-cleanup ownership** — RESOLVED 2026-11-05: ops-steward runs it weekly (orchestrator-operator retired). It used to be claimed twice (owner-operations §2 vs the retired orchestrator-operator).

---

## Sources

All fetched and confirmed 2026-11-05 (by the agent-refinement audit, or re-fetched for this doc, marked †).

- Google SRE Book ch.11, "Being On-Call" † — https://sre.google/sre-book/being-on-call/ — 1:1 alert/incident ratio; actionable pages; 2 incidents per 12 h shift ceiling; alert fatigue (§3).
- Google SRE Book ch.5, "Eliminating Toil" † — https://sre.google/sre-book/eliminating-toil/ — toil traits; < 50 % cap (§5).
- Google SRE Book ch.14, "Managing Incidents" — https://sre.google/sre-book/managing-incidents/ — when to declare; roles (§4).
- Google SRE Book, "Postmortem Culture" † — https://sre.google/sre-book/postmortem-culture/ — postmortem triggers incl. monitoring failure (§4, example A).
- Google SRE Workbook ch.2, "Implementing SLOs" — https://sre.google/workbook/implementing-slos/ — SLO-based health and budget policy (§2).
- Google SRE Workbook, "Alerting on SLOs" † — https://sre.google/workbook/alerting-on-slos/ — burn-rate alerts; low-traffic services (§2).
- Google SRE Book, "Monitoring Distributed Systems" — https://sre.google/sre-book/monitoring-distributed-systems/ — symptoms over causes; golden signals (§2).
- PagerDuty Incident Response, Severity Levels † — https://response.pagerduty.com/before/severity_levels/ — severity classification; "treat it as the higher one" (§4).
- DORA metrics † — https://dora.dev/guides/dora-metrics-four-keys/ — the five delivery metrics in the monthly review (§7).
- Supabase, "Database Backups" † — https://supabase.com/docs/guides/platform/backups — which plans get automated backups; Storage not included (§6).

Not cited for lack of a free canonical URL: ITIL 4 practice guides (proprietary; the practice names in §1 are used descriptively). The agent-operations research basis (Anthropic, OpenAI, OWASP, Meta Rule of Two, levels of autonomy) is cited in `owner-operations.md` and not repeated here.
