# SRE craft canon — reliability engineering for a one-host, one-owner fleet

> Owner: agent `devops-engineer`. Companion: `KB § PATTERNS/devops/ops-craft-canon.md` (the ops-steward's daily side of the same numbers). Born 2026-11-05 (agent-refinement W1-S5) from the audit finding that devops depth was "world-class on containers and deploys, close to empty on SRE": no SLOs, no error budgets, no RPO/RTO, no restore drill, no severity scale, no supply-chain provenance.

## 0 · What this is, and how to use it

**What.** The profession's reliability canon (Google SRE, DORA, CIS, SLSA, Sigstore, OpenTelemetry), written down once and mapped onto how this platform actually runs. Each section has: principle → how it applies HERE (file:line) → checklist → anti-patterns.

**Why.** The house already learns from incidents and turns them into keepers. That loop is reactive: it only knows what has already hurt. The canon is the proactive half. It says what a reliable service needs before the incident that teaches it.

**How to use it.**
- **The house mechanism wins.** Where a house doc already decides something (`deploy_image` rollback, `predeploy_check`, the watchdog, the dormant dev fleet), this canon points to it and does not re-decide it. The canon fills gaps. It does not override house rules.
- **Numbers marked *starter* are proposals.** SLO targets, RPO/RTO targets and budget policies are the owner's decisions (money and priority are owner-class, `KB § PATTERNS/common/owner-questionnaire.md` §2). Until the owner ratifies them, use them to measure, not to block.
- **Merge flow is out of scope.** Branching, CI gating, bless/promote and the merge queue belong to the git/CI redesign. §8 points there and covers runtime release safety only.
- Use it as a checklist when you add a prod service, review an incident, plan capacity or touch CI supply chain.

**Standard term ↔ house term.**

| Standard term | House term / mechanism |
|---|---|
| SLI (availability) | watchdog HTTP probe of `/api/health` (`KB § PATTERNS/devops/prod-watchdog.md` §3) |
| SLI (latency) | `RequestTimingMiddleware` `req_timing` log line, read by `noctus.dev.latency_report` (`seed/lib/backend/noctusai_lib/api/request_timing.py:187`) |
| Latency SLO | `deploy/fleet/latency-budgets.json` p95 budgets (shell 150 ms · read 300 ms · write 500 ms) |
| Synthetic monitoring / black-box probe | `noctus.dev.prod_watchdog` (off-host, GitHub Actions `*/10`) |
| Dead-man switch | on-host heartbeat `noctus-heartbeat.timer` + the 07:00 brief's 26 h flag |
| Rollback | `noctus.dev.deploy_image` snapshot `:previous` → auto-rollback on failed health |
| Change gate | `noctus.dev.predeploy_check` + CI-green (`KB § PATTERNS/devops/dev-fleet-dormant.md`) |
| Production readiness review | `KB § PATTERNS/devops/prod-exposure-consent.md` (the owner's promotion decision) |
| Incident commander (IC) | the owner, or the tech-lead session acting for the owner (§4) |
| Toil | an ops-steward L3 action (`KB § PATTERNS/devops/owner-operations.md` §2) |
| Runbook | skill `noc-container-debug` · `KB § PATTERNS/devops/containerization-operations.md` |
| Remediation item with a named destination | `NOC-REMEDIATE[<class>]` marker or a roadmap entry (`KB § PATTERNS/common/remediation-markers.md`) |

---

## 1 · Operating context — what we are actually running

**Principle.** Reliability work starts from an honest inventory of what can fail, not from a generic architecture. (SRE Book, "Monitoring Distributed Systems".)

**Here.**
- **One VPS.** 8 GB RAM, 2 vCPU, 2 GB swap, about 96 GB disk (37 % used on 2026-11-05). It runs the whole product fleet, one container per product (`KB § PATTERNS/devops/containerization.md`). Address and access are configured outside the KB (§5 table; `KB § 05-INFRASTRUCTURE.md`).
- **Edge.** A Cloudflare named tunnel (`noctus-tunnel`). There are no open inbound web ports. Routes come from `deploy/tunnel/ingress.yml` (`KB § PATTERNS/devops/tunnel-ingress-source-of-truth.md`).
- **Images.** Built by GitHub Actions, pushed to GHCR, pulled by the VPS. The VPS never builds (`mcp/noctusai/tools/noctus/dev/deploy_image.py:1-24`).
- **Data.** Managed Supabase (Postgres + Storage, project `NoctusAI`, `sa-east-1`). In-fleet `noctus-cache-pg` (regenerable caches) and Redis. The `noctus-services` stack runs n8n with its own Postgres, plus WAHA (`deploy/services/compose.services.yml`).
- **Watch.** The off-host watchdog (GitHub Actions cron) plus the on-host heartbeat.

**Single points of failure (named so nobody assumes redundancy).**

| SPOF | Blast radius | Current mitigation | Residual |
|---|---|---|---|
| The VPS host | every product, WAHA, n8n | watchdog detects within about 20 min; manual reboot | no standby host; RTO not measured (§5) |
| Cloudflare tunnel (1 connector container) | every public hostname (CF 530) | `restart: unless-stopped`; watchdog sees 530 as failure | uid-65532 credentials footgun (`tunnel-ingress-source-of-truth.md` "Operational footgun") |
| WAHA on the same host | WhatsApp alerts die with the host | DOWN alerts go to email first (`prod-watchdog.md` §8) | DEGRADED alerting rides WAHA |
| GitHub Actions cron | watchdog cadence | the 2-run debounce tolerates one missed tick | cron is best effort; schedules only fire from `main` (`prod-watchdog.md` §8) |
| Supabase project | all product data | managed service | backup posture unverified as safe (§5) |
| The owner | every L2 decision, every IC role | autonomy levels push L3 work to agents | no second human; §4 adapts the roles |

**Checklist — adding anything to prod.** Which SPOF does it ride? Does it add one? Is it in the watchdog roster (`deploy/fleet/build-scope.txt`)? Does it have an SLO row (§2), a data-store row (§5) and the hardening baseline (§7)?

---

## 2 · SLIs, SLOs and error budgets

**Principle.** Choose a few indicators that reflect what users experience (SLIs). Set a target for each (SLO). The gap between the target and 100 % is the **error budget**, which pays for change and risk. Write down an **error-budget policy** that says what happens when the budget runs out, and get it agreed before you need it. (SRE Workbook ch.2, "Implementing SLOs".) Alert on the **rate the budget is burning**, not on raw causes. (SRE Workbook, "Alerting on SLOs".)

**Here — SLIs we can already measure.**

| SLI | Source | Good event | Valid event |
|---|---|---|---|
| Availability | watchdog HTTP probe, every 10 min (`prod-watchdog.md` §3) | 2xx from `/api/health` (core also `/`) | every probe run that reached the edge |
| Latency | `req_timing` log line per request → `noctus.dev.latency_report` | request duration ≤ its class budget in `latency-budgets.json` | every request not in `ignore_routes` (health checks excluded) |
| Host liveness | host probe: heartbeat age, journald age, MemAvailable, swap | heartbeat ≤ 15 min ∧ MemAvailable ≥ 600 MB | every probe that returned JSON |

The latency class is chosen exactly as `latency-budgets.json` `_doc` says: the first `shell_routes` match is shell, otherwise GET/HEAD is read and anything else is write. `min_samples: 5` means a route with fewer requests is not judged.

**Starter SLO table** (*starter*: proposed 2026-11-05 for the products in `deploy/fleet/active-scope.txt`; owner ratifies).

| Product | Availability SLO (30 d rolling) | Budget (30 d) | Latency SLO (7 d) |
|---|---|---|---|
| `core` (apex, auth, SSO, admin) | 99.5 % | ≈ 3 h 36 min ≈ 21 failed probe-runs | 95 % of requests within their class budget (that is the p95 budget restated as an SLO) |
| `agents` (customer-facing agents) | 99.5 % | ≈ 3 h 36 min | same |
| `nosnolimiar` | 99.0 % | ≈ 7 h 12 min ≈ 43 failed probe-runs | same |
| `social-wiring` | 99.0 % | ≈ 7 h 12 min | same |
| `seed` (reference product) | 99.0 % | ≈ 7 h 12 min | same |
| any other running container not in active scope | no SLO; best effort | — | — |

Why not 99.9 %: a single host with manual reboot cannot honestly promise 43 minutes a month. The 2026-10-11 freeze alone took the fleet down for longer than that. Promise what the architecture delivers; tighten the SLO when the architecture changes (§9).

**Starter error-budget policy** (owner ratifies).
1. Budget remaining > 50 %: ship normally.
2. Budget 0–50 %: every prod change for that product needs a stated rollback plan, and the next planned work includes one reliability item.
3. Budget exhausted: feature ships for that product freeze. Reliability fixes, security fixes and rollbacks are still allowed. The freeze ends when the 30-day budget is positive again or the owner waives it in writing (recorded like any owner decision).
4. One incident that consumes more than 20 % of the budget in one go always gets a postmortem (§4).

**Burn-rate alerting, adapted to a 10-minute probe.** The SRE Workbook's recommended alerts for a 99.9 % / 30-day SLO are: page at 14.4× burn over 1 h (with a 5 min short window), page at 6× over 6 h (30 min short window), and open a ticket at 1× over 3 days (6 h short window). Our probe produces 6 samples an hour, so a 5-minute window is impossible, and one failed probe is already a large burn. The Workbook's advice for low-traffic services applies: generate synthetic traffic (the watchdog is that traffic), and lengthen the windows.

| Alert | Condition | Action |
|---|---|---|
| Fast burn (page) | 2 consecutive failed probes (≈ 20 min), which is the watchdog's existing DOWN or DEGRADED rule | this is the watchdog alert you already get. Declare per §4 |
| Medium burn (page in the brief) | more than 10 % of the 30-day budget consumed in the last 24 h | ops-steward puts it in "Today" (`ops-craft-canon.md` §2) |
| Slow burn (ticket) | budget consumed faster than the window elapses for 3 days (burn rate > 1 over 72 h) | a reliability item for that product in the weekly review |

The budget arithmetic needs the probe history, and the watchdog only keeps current state in the Actions cache (`prod-watchdog.md` §8). **Gap:** persist one row per probe run so budgets can be computed. Named destination: the "budget ledger" proposal in `KB § PATTERNS/devops/ops-craft-canon.md` §2 (to be built as a `noctus.dev.*` tool, never a bare script).

**Checklist.** Every active product has an SLO row. Every SLO has a measurable SLI source. The policy is written before it is needed. Alerts page on symptoms that burn budget, not on causes such as "CPU 80 %".

**Anti-patterns.** 100 % targets. An SLO nobody computes. A budget policy invented mid-incident. Paging on a cause that users never feel. An SLO tighter than the architecture can deliver.

---

## 3 · Monitoring, observability and alerting

**Principle.** Monitor the **four golden signals**: latency, traffic, errors and saturation. Alert on **symptoms** (what users see), and keep causes for debugging. (SRE Book, "Monitoring Distributed Systems".) For each **resource**, use **USE**: utilization, saturation, errors (Brendan Gregg). For each **service**, use **RED**: rate, errors, duration (Grafana / Tom Wilkie). **OpenTelemetry** is the vendor-neutral standard for the three signals: traces, metrics and logs (plus baggage for context).

**Here.**

| Lens | What we have | Where | Gap |
|---|---|---|---|
| Golden: latency | p95 per route template | `request_timing.py:187`, added in `app_factory.py:297`; `noctus.dev.latency_report` | read after deploys only (`KB § PATTERNS/backend/request-path-latency.md`), not trended |
| Golden: traffic | request count in the `req_timing` lines | same | not aggregated over time |
| Golden: errors | watchdog non-2xx; Sentry when `SENTRY_DSN` is set (`app_factory.py:169`) | watchdog + Sentry | no per-product error-rate SLI |
| Golden: saturation | MemAvailable, swap, load1/load5 at probe time | host probe (`prod-watchdog.md` §2) | point-in-time only; spikes between runs are invisible |
| USE (host) | the same host-probe fields; `sysstat` collects every 10 min on the host | host | nobody reads sysstat; no trend |
| RED (API) | `RequestTimingMiddleware` (rate + duration); errors via status code | seed | no dashboard |
| Traces | none in prod | — | OTel is a target, not a current state |
| Logs | Docker `json-file`, rotated 10 MB × 3 per container by the host daemon (verified 2026-11-05, §7); journald capped at 1 GB / 7 days | host | the rotation config lives only on the host, not in git (§7) |

**OpenTelemetry — how to adopt it here, when we do.**
- Instrument once in the seed (`create_product_app`), never per product. That is the seed-first rule: one seam, every product inherits it.
- Start with metrics (RED per route), because the `req_timing` line already carries them. Add traces when a cross-service call path (product → transcriber, product → n8n) needs debugging.
- Export over OTLP to one collector. Do not run a heavy observability stack on the 8 GB host; host capacity is the binding constraint (§9). A free-tier hosted backend or the existing Sentry project are the options. Choosing one costs money, so it is an owner decision.
- The OTel GenAI semantic conventions are still in Development status, so pin the version if you use them (`owner-operations.md` §1 "Hype flags").

**Alerting rules.**
- Every page must be actionable. Aim for a 1:1 alert-to-incident ratio (SRE Book ch.11, "Being On-Call"). The steward measures this with the alert-outcome log (`ops-craft-canon.md` §3).
- Alert on change, deduplicate, and remind no more often than every 6 h. The watchdog already does all three (`prod-watchdog.md` §4). Keep it that way.
- Every scheduler and every watcher needs a dead-man switch. The heartbeat covers the host, and the 26 h flag covers the brief. A new scheduled job gets one too.
- Monitoring must not live only on the host it watches. That was the lesson of 2026-10-11.

**Checklist.** New service: does `/api/health` reflect real dependencies (and report `startup_hook_error`)? Is it in the watchdog roster? Does it emit `req_timing`? Does it have a dead-man switch if it is scheduled?

**Anti-patterns.** Dashboards nobody opens. Alerting on CPU instead of user pain. A monitoring stack heavier than the service. On-host-only monitoring. Logs as the only signal.

---

## 4 · Incident management

**Principle.** Declare early, give the incident a single commander, mitigate before you diagnose, communicate on a schedule, and learn without blame. (SRE Book ch.14, "Managing Incidents"; SRE Workbook ch.9, "Incident Response"; PagerDuty Incident Response docs; SRE Book, "Postmortem Culture".)

**Severity scale for this fleet** (adapted from PagerDuty's SEV-1..5; SEV-5 folds into ordinary tickets here).

| SEV | Definition here | Examples | Response |
|---|---|---|---|
| **SEV1** | All products or the apex down, data loss, or a security exposure of customer data | 2026-10-11 host freeze (CF 530 everywhere); tunnel credentials crash loop; a public bucket with personal data | declare now; IC = owner; mitigate first; customer notice if paying customers were affected; LGPD/ANPD assessment if personal data is involved (agent `security`); postmortem required |
| **SEV2** | One paying or customer-facing product down or badly degraded; or an exhausted error budget on core/agents | `agents` failing health for 2 runs; core login broken | declare; IC; rollback if a deploy is the likely cause; postmortem required |
| **SEV3** | Partial loss, a risk of escalating, or a lost safety net | watchdog cannot alert (workflow red); backups or restore drill failing; one internal product down | fix during working hours; postmortem if it recurs (§4 "Problem") |
| **SEV4** | Minor; nobody blocked | a slow route over budget; a failed non-critical cron job | ticket or brief item |

If you cannot decide between two levels, pick the higher one and review it in the postmortem. Do not debate severity during the incident (PagerDuty).

**Roles for a one-owner team.** The canon's roles are Incident Commander (decides and coordinates), Operations Lead (changes things) and Communications Lead (tells people). Here one human, plus agent sessions, holds all three. The discipline is to **switch roles explicitly**:
- **IC**: the owner. When the owner is absent and an agent detects the incident, the tech-lead session acts as IC up to L2 limits. Any L2 action (deploy, data change, customer message) still needs the owner's yes (`owner-operations.md` §2).
- **Ops**: agent `devops-engineer` (L2 fixes) or the tech-lead. ops-steward only performs pre-approved L3 actions.
- **Comms**: the owner. Agents draft customer messages and never send them (Rule of Two; `notify` is plan-only for the steward).
- Write one timeline line every time someone changes role or takes an action. That timeline is the postmortem's raw material.

**The flow: declare → mitigate → resolve → learn.**
1. **Declare** when any of these is true: customer-visible impact; more than one product affected; not solved within 1 hour; a safety net (watchdog, backups, alert channel) is down. Open the incident record (template below) with a UTC start time.
2. **Mitigate first.** Use the cheapest lever that restores service, and save root-causing for later:
   - bad deploy → `noctus.dev.deploy_image` rollback to `:previous` (automatic on failed health; manual for a healthy-but-wrong image);
   - stuck container → `noctus.vps_restart` (confirm-gated), at most twice; the third time is a problem, not an event (`owner-operations.md` §2);
   - host frozen → reboot from the provider console (owner);
   - tunnel down → check credentials ownership (uid 65532) and `tunnel_config action='check'`.
3. **Resolve.** Service is back within SLO and the watchdog has recovered to `up`. Record the end time.
4. **Learn.** A blameless postmortem within 5 working days for SEV1/SEV2, or for any incident that matches a trigger: user-visible downtime beyond the threshold, any data loss, a manual rollback or intervention, a long resolution, or a monitoring failure (the incident was found by hand) (SRE Book, "Postmortem Culture").

**Blameless rules.** Assume everyone, human or agent, acted in good faith with what they knew. Ask what made the wrong action look right. Fix the system: a keeper, a seed default, a runbook, an alert. Do not just tell people to be more careful. Every action item has a **named destination**: a keeper, a `NOC-REMEDIATE[...]` marker, a roadmap entry or a PROJECT.md. No "TBD" (`KB § 01-PHILOSOPHY.md` no silent deferral).

**Postmortem home (proposal).** `project-history/postmortems/YYYY-MM-DD-<slug>.md`, one file per incident, plus a one-line row per incident in an index file in the same folder. `project-history/retrospectives/` stays for ship retros. Today the only postmortem lives inside `prod-watchdog.md` §1. Creating the folder is a tech-lead decision (it is a durable-surface change); until then, write postmortems in the owning project's `findings.md`.

**Postmortem template.**

```markdown
# Postmortem — <title> (SEV<n>)
- Date/UTC window: start … detected … mitigated … resolved
- IC: <who> · Ops: <who> · Comms: <who>
- Impact: products, users, duration, error budget consumed (§2), data lost (yes/no)
- Detection: how we found out (alert? owner noticed? customer?) · time to detect
## Timeline (UTC)
- hh:mm — event / decision / role switch
## Contributing causes (not "root cause" — usually several)
## What went well · What went badly · Where we got lucky
## Action items
| Action | Type (prevent/detect/mitigate) | Destination (keeper / marker / roadmap / PROJECT) | Owner | Due |
## Lessons → KB/keeper (the house learning loop)
```

**Checklist.** Severity assigned in under 5 minutes. IC named. Timeline started. Mitigation lever chosen before the root-cause hunt. Postmortem filed and every action item routed.

**Anti-patterns.** Debugging before mitigating. A silent incident that only the owner knows about. Postmortems that blame. Action items with no destination. Restart loops that hide the cause. Treating the 3rd restart in a week as an event.

---

## 5 · Backups and disaster recovery

**Principle.** For every data store, state a **RPO** (how much data you can afford to lose, measured in time) and a **RTO** (how long you can afford to be down). Keep **3 copies, on 2 kinds of media, with 1 off-site** (3-2-1). A backup that has never been restored is a hope, not a backup. Prove it with scheduled restore drills that measure the real RTO.

**Here — the fleet's data-store inventory (verified 2026-11-05, read-only).**

| Store | What it holds | Mechanism today | RPO today | RTO today | *Starter* target | Gap / owner decision |
|---|---|---|---|---|---|---|
| **Supabase DB** (project `NoctusAI`) | all product data | 🔴 The Supabase API (`get_organization`, 2026-11-05) reports the org plan as **`free`**. Supabase automatically backs up only Pro, Team and Enterprise projects daily. For Free projects it recommends regular `supabase db dump` exports. No dump job was found in the repo. | **undefined (no backup found)** | unknown | RPO ≤ 24 h (Pro daily backups, 7-day retention) or about 2 min (PITR add-on: needs Pro and at least Small compute; about $100/month for 7 days) · RTO ≤ 4 h | 🔴 **owner money decision, now.** Interim with no spend: a nightly `supabase db dump` to off-host storage (devops L1 proposal). Confirm the plan in the dashboard; the API answer may lag a recent upgrade. |
| **Supabase Storage** | uploaded files (product media, documents) | none. Database backups never include Storage objects, on any plan. | **undefined** | unknown | RPO ≤ 24 h via periodic object sync to an off-host bucket | owner decision (which bucket, cost) |
| **`noctus-cache-pg`** | keeper-mirror caches (Tier-2) | none, **by design**: everything is regenerable from git plus embeddings (`KB § PATTERNS/devops/prod-cache-container.md` § Backup) | unbounded (stated, accepted) | cold rebuild via each cache's `--force` + `cache_deploy_mirror`; time **not measured** | RTO measured once in a drill | measure it (drill C below) |
| **Redis** (`noctus-redis`, infra Redis) | rate limits, ephemeral cache | none needed | n/a (ephemeral) | restart | — | fail-open behaviour when Redis is down is a known code item (PROJECT follow-up 8) |
| **n8n** (`noctus-services`: `pgdata` + `n8n-data` volumes) | workflows, credentials, execution history | none found (no cron.d job, no systemd timer, no dump directory) | **undefined** | unknown | RPO ≤ 24 h: nightly `pg_dump` + `n8n export:workflow --all` off-host | devops L1 proposal |
| **WAHA sessions** (`waha-sessions`, `noctus-waha-nosnolimiar`) | paired WhatsApp sessions | none | n/a: re-pairing with a QR scan restores it | the owner's phone time | document re-pair in the rebuild runbook | — |
| **Deploy-local secrets** (`.env`, `.env.fleet`, `.env.services`, tunnel credentials and `cert.pem`) | every secret the fleet needs | `deploy/prod-pull.sh` tars them before each pull into `/opt/noctus/backups` (257 archives, 1.8 MB, newest 2026-11-04) | per deploy | minutes, **if the host survives** | 3-2-1: an encrypted off-host copy (owner's password manager, or an age-encrypted file in private storage) | 🔴 all copies are **on the same host**. Host loss means secret loss. Key names (not values) are in `deploy/fleet/env.fleet.keys`. |
| **GHCR images** | built product images | GHCR, off-host; rebuildable from git | 0 | one CI build | — | — |
| **Git** | code, KB, ledgers (`origin/ledgers`) | GitHub plus local clones | 0 | clone | — | — |
| **Host configuration** | systemd heartbeat units, `daemon.json`, sshd and fail2ban, `authorized_keys` forced-command lines | partly in git (`deploy/watchdog/`), partly only on the host (`daemon.json`) | — | **host rebuild time not measured** | RTO ≤ 4 h for "VPS gone, rebuild from zero" | write the rebuild runbook and measure it in a game day (§11) |

**Quarterly restore drill (procedure).**
1. **Pick one store per quarter**, in rotation: Supabase DB → n8n → cache-pg → secrets/host rebuild.
2. **Restore into scratch, never into prod.** Supabase: restore the latest dump or backup into a scratch Postgres or a Supabase branch. cache-pg: restore a `pg_dump` into a scratch database. Secrets: rebuild `.env.fleet` from the off-host copy into a temporary file and diff its key set against `env.fleet.keys`.
3. **Measure.** RTO = wall-clock time from "start" to "data queryable". RPO = the gap between the newest row in the restore and the moment of the backup.
4. **Verify.** Row counts for the critical tables (or a checksum) match the source within the RPO. One real query per product succeeds.
5. **Record** the date, store, RTO, RPO, pass/fail and surprises. Proposed home: one row in a `dr-drills.ndjson` ledger on `origin/ledgers` (`KB § PATTERNS/common/ledger-store.md`), which ops-steward reads (`ops-craft-canon.md` §6).
6. **A failed drill is a SEV3 incident** (§4). It means the backup is a hope.

The drill reads production only. Restores go to scratch. Any VPS write needs the usual confirm gate (`noctus.vps_*`).

**Checklist — new data store.** Add a row to the table above in the same commit that introduces the store. State RPO/RTO, even when it is "unbounded by design". Say where the off-host copy lives. Add it to the drill rotation.

**Anti-patterns.** Backups on the same host as the data. "Supabase backs us up" without checking the plan. Backups never restored. Secrets with one copy. An RPO nobody wrote down.

---

## 6 · Supply chain and CI hardening (target state)

> **Scope.** CI implementation belongs to the git/CI redesign (`KB § PATTERNS/devops/ci-security-gates.md`; workflows under `.github/workflows/`). This section describes the **target state** and the facts. It changes no workflow.

**Principle.** Pin everything that executes to an immutable reference. Prove where each artifact came from (provenance). Know what is inside it (SBOM). Sign it, and verify the signature before you deploy. (SLSA; Sigstore; GitHub Actions security hardening; Docker build attestations.)

**Facts here (2026-11-05).**
- 79 `uses:` lines across the workflows; **0 are pinned to a full commit SHA**. Examples: `aquasecurity/trivy-action@v0.36.0` (`.github/workflows/test.yml:1056`), `gitleaks/gitleaks-action@v3` (`test.yml:1248`).
- Dependabot already watches `github-actions` weekly (`.github/dependabot.yml:489`). Dependabot can update SHA pins that carry a version comment, so pinning does not freeze us.
- Prod images default to `:latest` (`deploy/fleet/docker-compose.prod.yml:35-38`, `:122` and every product service). The file's own comment says to pin `NOCTUS_IMAGE_TAG=<git-sha>` for an immutable deploy. `deploy_image` snapshots the running image as `:previous`, which makes rollback safe even with a mutable tag (§8).
- Third-party images on mutable tags: `devlikeapro/waha:latest` (`deploy/fleet/compose.infra.prod.yml:116`), `redis:7-alpine` (`:47`), `pgvector/pgvector:pg16` (`:72`).
- Base images are not digest-pinned: `node:20-alpine` (`seed/docker/Dockerfile.frontend-base:14`), `python:3.11-slim` (`seed/docker/Dockerfile.backend-base:25,58`).
- No SBOM, provenance or signing step in any workflow (grep, 0 hits).
- Every workflow declares `permissions:`; `build-and-push.yml` uses least privilege. Keep that.

**Target state.**

| Control | Target | Standard |
|---|---|---|
| Action pinning | every third-party `uses:` pinned to a full 40-character SHA with a `# vX.Y.Z` comment; Dependabot bumps them | GitHub hardening guide ("Pin references to actions to a commit SHA"; verify the SHA belongs to the action's own repo, not a fork). The guide now also describes a workflow lockfile that supersedes SHA pinning for repos that adopt it. Evaluating it is the redesign's call. |
| Token scope | `permissions: contents: read` at the top; raise per job only | GitHub hardening guide |
| Cloud credentials | OIDC short-lived tokens where the provider supports them; forced-command SSH keys where it does not (already our pattern: `KB § PATTERNS/devops/ssh-deploy-key-restrictions.md`, `ci-deploy-prod.md`) | GitHub OIDC docs |
| Base images | pinned by digest (`FROM python:3.11-slim@sha256:…`), refreshed by Dependabot or Renovate; the Docker docs note the trade-off: a pinned digest never receives security fixes unless something bumps it | Docker build best practices |
| Provenance + SBOM | `docker/build-push-action` with `provenance: mode=max` and `sbom: true` | Docker build attestations |
| Signing | keyless `cosign sign <image>@sha256:…` in CI (OIDC identity = the workflow); `cosign verify` with `--certificate-identity` and `--certificate-oidc-issuer` before `deploy_image` pulls | Sigstore cosign |
| Build level | SLSA **Build L2**: a hosted build platform that generates and signs provenance. GitHub Actions plus attestations reaches it. L3 needs hardened, isolated builders, which is not worth it at our size. Cite the current spec version (v1.2), since the v1.0 page is marked retired. | SLSA levels |
| Deploy reference | deploy by digest or by git-sha tag; never `:latest` in prod | (§7, §8) |
| Vulnerability scan | Trivy fs scan exists (`ci-security-gates.md` §1). No image scan exists today (corrected 2026-11-05 in that doc). Target: scan the built image and diff the SBOM between releases. | — |

**Checklist — adding an action or image.** Pin by SHA or digest. Check the publisher. Request minimal permissions. Make sure Dependabot covers it.

**Anti-patterns.** Tag-pinned actions with secrets in the job. `:latest` in prod. A digest pin that nothing ever bumps. Signing without verifying. Long-lived cloud keys in CI.

---

## 7 · Container hardening baseline

**Principle.** Every production container gets the same small, checkable baseline, mapped to the CIS Docker Benchmark and Docker's build best practices. Least privilege by default, and resources bounded so that one container cannot take the host down.

**The baseline (every prod service must carry it, or record why not).**

| # | Control | How in compose / Dockerfile | CIS area | State here (2026-11-05) |
|---|---|---|---|---|
| 1 | Non-root user | `USER` in the Dockerfile | container images / runtime: run as non-root | ✅ all 19 product Dockerfiles set `USER` |
| 2 | Drop capabilities | `cap_drop: [ALL]` plus explicit `cap_add` only where needed | runtime: restrict Linux capabilities | ⚠️ 7 of 20 GHCR services (`docker-compose.prod.yml`) |
| 3 | No privilege escalation | `security_opt: [no-new-privileges:true]` | runtime: no new privileges | ⚠️ 7 of 20 |
| 4 | Read-only root filesystem | `read_only: true` plus `tmpfs:` for scratch | runtime: read-only root FS | ⚠️ 7 of 20 |
| 5 | Healthcheck | Dockerfile `HEALTHCHECK` or compose `healthcheck:` on `/api/health` | images: add HEALTHCHECK | ✅ 19 in prod compose plus 2 in infra |
| 6 | Memory and PID limits | `mem_limit`, `pids_limit` | runtime: limit memory / PIDs | ⚠️ some services. **Owner decision recorded at `docker-compose.prod.yml:614,645`: "server protection without per-container limits"** for commerce and nosnolimiar. Respect the decision, and record any new exception the same way. |
| 7 | Bounded logs | `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}` | host / daemon configuration | ✅ **at host level**: `/etc/docker/daemon.json` sets json-file 10 MB × 3, and all 20 running containers report that LogConfig (read-only check 2026-11-05). ⚠️ The setting is not in git, so a rebuilt host loses it silently, and the daemon setting only applies to containers created after a daemon restart (Docker json-file docs). Target: capture it in the host-rebuild runbook or in the `x-prod-defaults` anchor. |
| 8 | Restart policy | `restart: unless-stopped` | runtime: restart policy | ✅ via `x-prod-defaults` (`docker-compose.prod.yml:110-116`) |
| 9 | No published ports for internal services | `expose:` not `ports:`; `noctus-net` | network | ✅ house rule (`containerization.md`) |
| 10 | Immutable image reference | git-sha tag or digest, never `:latest` | images: content trust | ⚠️ `:latest` by default (§6) |
| 11 | Supported runtime | base image versions inside upstream support | images: up to date | ⚠️ `node:20-alpine` is EOL per nodejs.org (current LTS lines: 22, 24, 26). It is used only in the frontend **build stage** (`Dockerfile.frontend-base:14`); the runtime is `python:3.11-slim`. Lower runtime risk, but the build toolchain is unpatched. Move to the current Active LTS through the base-image path (`KB § PATTERNS/devops/base-image-dep-freshness.md`). |

**Root-level fix (not per service).** Controls 2, 3, 4 and 7 belong in the `x-prod-defaults` anchor (`docker-compose.prod.yml:110`). Every service already merges it, so one edit covers the fleet and new services inherit it. Adding them one service at a time is the per-product slip (§1 "No quick fixes"). Some services need exceptions (for example a writable path, or a capability for the transcriber). Declare each one next to the service with a reason, like the existing mem_limit comment. This is a compose edit, so it is its own devops slice with `predeploy_check` and a staged rollout. It does not belong in a docs slice.

**Checklist — new service.** All 11 rows are satisfied or carry a recorded exception. Run `docker inspect` on the live container (not the compose file) to confirm what actually applied.

**Anti-patterns.** Root containers. Privileged mode. Unbounded logs. A hardening applied by hand on the host and never written down. Per-service copy-paste instead of the anchor.

---

## 8 · Change management, release safety and DORA

> **Merge flow is out of scope.** Branching, CI gates, bless/promote, the merge queue and ship consent live in the git/CI redesign docs (`KB § PATTERNS/devops/dev-main-ci-gates.md`, `KB § PATTERNS/devops/ship-consent-riders.md`, `KB § GUIDES/production-deploy.md`). This section only covers what happens **at runtime** once a change is going to prod.

**Principle.** Most outages come from changes. Make changes small, frequent, observable and reversible. Builds should be hermetic and policy-enforced (SRE Book ch.8, "Release Engineering"). Measure delivery with the DORA metrics: change lead time, deployment frequency, failed deployment recovery time, change fail rate and deployment rework rate.

**Runtime release safety we already have.**
- **Pre-deploy gate:** `noctus.dev.predeploy_check`. Every leg verifies or blocks (`KB § PATTERNS/devops/predeploy-leg-verify-or-block.md`).
- **Canary by snapshot:** `deploy_image` tags the running image `:previous`, pulls, recreates, probes health, verifies the swap, and **rolls back automatically** on failed health (`deploy_image.py:1-24`).
- **Catalog scope guard:** `deploy_image` refuses products that are not `ativo ∧ live`.
- **Post-deploy:** prod smoke (`noctus.dev.smoke_fleet`, `spa_smoke`) and `latency_report`.

**Gaps (runtime side only).**
- **Staggered waves.** The 2026-10-11 freeze followed a whole-fleet deploy on an 8 GB host. Deploy in waves (core first, then active products, then the rest) and watch MemAvailable between waves.
- **No deploy ledger.** `deploy_image` returns a status (`deployed`, `rolled_back`, `rollback_failed`, `up_to_date`), but nothing persists it. Every DORA metric depends on a record of deploys. Target: one row per `deploy_image` run in a `deploys.ndjson` on `origin/ledgers`, written by the tool itself (a code change; it is the next devops slice, not part of this doc).

**DORA, derived from house sources (once the deploy ledger exists).**

| Metric | Source here |
|---|---|
| Change lead time | commit timestamp → the `deploy_image` `deployed` row carrying that revision label |
| Deployment frequency | count of `deployed` rows per week |
| Change fail rate | (`rolled_back` + `rollback_failed` + deploys followed by a SEV1/2 within 24 h) ÷ deploys |
| Failed deployment recovery time | incident start → recovery for deploy-caused incidents (postmortems, §4) |
| Deployment rework rate | deploys tagged as hotfixes for a live incident ÷ deploys |

Report the five monthly in the ops review (`ops-craft-canon.md` §7). The trend matters more than the absolute values.

**Anti-patterns.** Big-bang fleet deploys. Rolling forward when rollback is available and cheaper. Unrecorded deploys. Mutable prod tags without a snapshot.

---

## 9 · Capacity planning

**Principle.** Forecast demand, provision ahead of it with headroom, and load-test the assumptions. Saturation is the golden signal that predicts the next outage.

**Here.**
- The constraint is **memory on one 8 GB host**. Watchdog thresholds: DEGRADED below 600 MB MemAvailable or above 1024 MB swap used (`prod-watchdog.md` §3).
- *Starter* headroom targets: MemAvailable ≥ 1.5 GB at the daily p95; swap use near 0 in steady state; load5 ≤ 1.5 × ncpu.
- Trend data exists but is not read: `sysstat` collects every 10 min on the host (`sysstat-collect.timer`). A weekly `sar -r` / `sar -q` summary is the cheapest trend. Read it with `noctus.vps_exec`, which is read-only.
- **Resize or split triggers** (starter): MemAvailable below 1 GB at the daily p95 for 2 weeks; any SEV1 caused by memory; a new heavy service (for example local Whisper transcription) proposed for the host. Options in order of cost: tune the memory of the worst containers → vertical resize of the VPS → move stateful services (n8n/WAHA) to a second small host → split the fleet.
- Every new prod service states its expected steady-state memory in its PR.

**Anti-patterns.** Sizing by gut feel. Finding capacity limits during a deploy. Running build jobs on the prod host.

---

## 10 · Toil

**Principle.** Toil is operational work that is manual, repetitive, automatable, tactical, without lasting value, and that grows linearly with the service. A task does not need every trait to count. Google keeps toil below 50 % of each SRE's time (SRE Book ch.5, "Eliminating Toil").

**Here.** Known toil: manual fleet recreates; cache mirrors to prod; container restarts; re-running failed idempotent jobs; tmp cleanup; reading watchdog output. Most of it is ops-steward L3 work, which the steward counts (`ops-craft-canon.md` §5). devops-engineer owns the **automation** side: when the steward's toil ledger shows the same action on the same target 3 or more times in 7 days, devops gets an L1 proposal to remove the cause (or automate the action safely, with a cap and an alert).

**Anti-patterns.** Automating a restart loop instead of fixing the crash. Toil nobody counts. "It only takes five minutes", repeated daily.

---

## 11 · Game days (chaos engineering, scaled to us)

**Principle.** Inject failure on purpose, in a controlled way, to prove that detection, alerts, runbooks and recovery work, before a real incident tests them.

**Here, quarterly, one scenario at a time, announced, during the owner's working hours.**

| Scenario | How | Proves |
|---|---|---|
| Kill a non-core product container | `noctus.vps_restart` (confirm-gated) or stop it | watchdog DEGRADED in about 20 min; alert arrives; `restart` policy recovers it |
| Watchdog cannot alert | run the workflow with `send_test_alert: true` and one channel deliberately unset | the workflow goes red (`prod-watchdog.md` §4) |
| Simulated host freeze | stop `noctus-heartbeat.timer` for 20 min | DEGRADED on heartbeat age; the brief shows it |
| Tunnel credential failure | on a scratch tunnel only, never the prod connector | the runbook recovers in a measured time |
| Restore cache-pg from a dump | §5 drill | RTO measured |
| Host loss (tabletop) | walk the rebuild runbook on paper and time each step | the runbook is complete; secrets are reachable off-host |

Every game day writes a short record (date, scenario, detection time, recovery time, surprises), and anything that failed becomes an action item with a destination, like a postmortem.

**Anti-patterns.** Chaos without a hypothesis. Game days in prod that nobody announced. Skipping the record.

---

## 12 · FinOps basics

**Principle.** Cost is a reliability and product signal. Make spend visible per product, attribute it, and review the trend monthly.

**Here.**
- Cost sources: `public.ai_usage` (LLM spend per org → product), `public.cost_ledger`, `project-history/vector-costs.ndjson` (`/cost-report`), the VPS bill, GHCR storage and the Supabase plan.
- Monthly: cost per active product (LLM + share of VPS + share of Supabase), month-over-month delta, and the top three drivers. The ops-steward review carries it (`ops-craft-canon.md` §7).
- Reliability costs money too: Supabase Pro or PITR, off-host backup storage and a standby host are budget lines. They belong next to their RPO/RTO in §5, so the owner can weigh price against risk.
- The owner's standing rule: use agents as little as we need ("use agents the less we need", `owner-operations.md` §1).

**Anti-patterns.** Cost discovered at invoice time. Unattributed LLM spend. Cutting reliability spend without seeing the RPO it buys.

---

## 13 · Anti-patterns (the whole canon on one list)

- Mutable tags in prod (`:latest`), and tag-pinned actions that have access to secrets.
- Restart loops that hide root causes. A third restart in a week is a problem record.
- Monitoring that lives only on the host it monitors.
- Unbounded logs, or bounded logs whose configuration lives only on the host.
- Backups that were never restored, and backups that sit on the same host as the data.
- 100 % targets, SLOs nobody computes, budget policies invented mid-incident.
- Alerts that are not actionable; an alert-to-incident ratio far above 1:1.
- Postmortems that assign blame; action items without a destination.
- Fixing at the wrong level: hardening service by service instead of in the anchor or the seed.
- Re-adding a dev-container gate. The dev fleet is dormant by owner decision (`dev-fleet-dormant.md`); prod-first-contact safety comes from `predeploy_check` plus rollback.

---

## Worked examples (from this codebase)

### A · The 2026-10-11 freeze, written as a postmortem

Source facts: `KB § PATTERNS/devops/prod-watchdog.md` §1.

```markdown
# Postmortem — prod VPS hard freeze after fleet deploy (SEV1)
- UTC window: ~2026-10-10 05:00 (journald/cron/sysstat stop) … ~01:17 2026-10-11 (freeze, CF 530 everywhere)
  … detected by the owner (no alert existed) … mitigated by a manual reboot … resolved after reboot.
- IC/Ops/Comms: owner (all three).
- Impact: every product unreachable (CF 530) until reboot; ~20 h of silent host degradation beforehand.
  Error budget: one event of this size exhausts a 99.5 % monthly budget for every product.
- Detection: manual. Time to detect: unbounded — nothing off-host was watching.
## Contributing causes
- Memory pressure on an 8 GB / 2 vCPU host; swap had been added only that day.
- A whole-fleet deploy (simultaneous recreates) on that host.
- Host scheduling (journald, cron, sysstat) had stalled ~20 h earlier with no signal,
  because every check lived on the host.
- Monitoring failure is itself a postmortem trigger (SRE "Postmortem Culture").
## Went well
- Rebooting restored everything; there was no data loss.
## Action items
| Action | Type | Destination | State |
| Off-host watchdog + heartbeat | detect | prod-watchdog.md / prod_watchdog tool | ✅ shipped |
| Memory headroom SLO + trend | detect/prevent | this canon §9 | ⏳ starter targets written |
| Log rotation | prevent | this canon §7 row 7 | ✅ verified at host level; ⏳ capture in git |
| Staggered deploy waves | prevent | this canon §8 gaps | 📋 |
| Postmortem home | learn | this canon §4 proposal | 📋 tech-lead decision |
```

The value of the template: three of the five action items have no destination today except this canon. The canon is that destination until each one ships.

### B · trivy-action: tag pinning versus SHA pinning

Facts (Aqua Security advisory): on 2026-03-19 at about 17:43 UTC, attackers force-pushed 76 of the 77 version tags of `aquasecurity/trivy-action` to commits whose `entrypoint.sh` was an infostealer. The exposure window ran until about 05:40 UTC on 2026-03-20. The payload ran before the real scan, so jobs looked normal, and every secret reachable by the runner had to be treated as exposed. The advisory says pinning to a full commit SHA "remains the only reliable protection". Only `v0.35.0` was unaffected, which the advisory attributes to GitHub's immutable releases.

Our exposure: `ci-security-gates.md` records that the fs-scan gate first landed 2026-05-11 on `@0.24.0` (a tag in the force-pushed set), later found "yanked" and replaced with `@v0.36.0` on 2026-05-22. Our usage started after the window, so we were not hit. A tag pin would have run attacker code if the gate had existed in March, and it still would if a future tag is re-pointed.

```yaml
# BEFORE (.github/workflows/test.yml:1056) — re-pointable
- uses: aquasecurity/trivy-action@v0.36.0

# AFTER (target state; implementation belongs to the CI redesign)
permissions:
  contents: read                 # job-scoped; add security-events: write only on the SARIF upload job
steps:
  - uses: aquasecurity/trivy-action@<40-char SHA of the v0.36.0 release commit>  # v0.36.0
```

How to get the SHA: resolve it from the action's own repository (`git ls-remote https://github.com/aquasecurity/trivy-action refs/tags/v0.36.0`) and cross-check the release page. Never copy a SHA from a third-party blog, and never resolve it during a known compromise window. Dependabot (`.github/dependabot.yml:489`, `github-actions`) then keeps the SHA and its version comment current.

### C · The fleet's RPO/RTO table, and the first drill

The table in §5 is the worked example. Its loudest line is that the production database's RPO is currently **undefined**: the org plan reads `free`, Free projects get no automatic backups, and no dump job exists. The first drill therefore comes before the first backup exists:

1. Owner decision (money): Pro daily backups, or PITR, or the zero-cost interim of a nightly `supabase db dump` to off-host storage.
2. devops slice: implement the chosen mechanism plus a backup-age check that ops-steward reads daily (`ops-craft-canon.md` §6).
3. First drill: restore the newest backup into a scratch database; record RTO and RPO in `dr-drills.ndjson`; if it fails, open a SEV3.
4. Repeat for n8n (the next undefined RPO), then cache-pg (to measure its cold-rebuild RTO), then secrets and host rebuild.

---

## Sources

All URLs below were fetched and confirmed on 2026-11-05: either by the agent-refinement audit (`archive/projects/2026-11-05/01-agent-refinement/audits/audit-devops-ops-operator.md` §4) or re-fetched for this doc (marked †).

- Google SRE Book, "Monitoring Distributed Systems" — https://sre.google/sre-book/monitoring-distributed-systems/ — four golden signals; symptoms over causes (§3).
- Google SRE Workbook ch.2, "Implementing SLOs" — https://sre.google/workbook/implementing-slos/ — choosing SLIs/SLOs; written error-budget policy (§2).
- Google SRE Workbook, "Alerting on SLOs" † — https://sre.google/workbook/alerting-on-slos/ — multiwindow, multi-burn-rate table (14.4×/1 h/5 min; 6×/6 h/30 min; 1×/3 d/6 h); low-traffic advice (§2).
- Google SRE Book ch.5, "Eliminating Toil" † — https://sre.google/sre-book/eliminating-toil/ — toil traits; the 50 % cap (§10).
- Google SRE Book ch.11, "Being On-Call" † — https://sre.google/sre-book/being-on-call/ — 1:1 alert/incident ratio; actionable pages; alert fatigue (§3).
- Google SRE Book ch.14, "Managing Incidents" — https://sre.google/sre-book/managing-incidents/ — roles; when to declare (§4).
- Google SRE Workbook ch.9, "Incident Response" — https://sre.google/workbook/incident-response/ — IC/CL/OL roles (§4).
- Google SRE Book, "Postmortem Culture" † — https://sre.google/sre-book/postmortem-culture/ — postmortem triggers; blameless definition (§4).
- Google SRE Book ch.8, "Release Engineering" — https://sre.google/sre-book/release-engineering/ — hermetic builds, policy enforcement (§8).
- DORA, "DORA's software delivery performance metrics" † — https://dora.dev/guides/dora-metrics-four-keys/ — the five metrics incl. deployment rework rate (§8).
- PagerDuty Incident Response, Severity Levels † — https://response.pagerduty.com/before/severity_levels/ — SEV-1..5 definitions; "treat it as the higher one" (§4). Index page: https://response.pagerduty.com/.
- Atlassian, "How to run a blameless postmortem" — https://www.atlassian.com/incident-management/postmortem/blameless — postmortem practice (title and topic confirmed; body not fully readable by the audit) (§4).
- The Twelve-Factor App — https://12factor.net/ — config in env, dev/prod parity, logs as streams, disposability (§1, §3).
- Docker, "Building best practices" — https://docs.docker.com/build/building/best-practices/ — multi-stage builds, digest pinning and its trade-off, non-root USER (§6, §7).
- Docker, "JSON File logging driver" † — https://docs.docker.com/engine/logging/drivers/json-file/ — `max-size` default -1 (unlimited), `max-file` default 1; daemon changes do not apply to existing containers (§7).
- Docker, "Build attestations" — https://docs.docker.com/build/metadata/attestations/ — `--sbom`, `--provenance=mode=max` (§6).
- CIS Docker Benchmarks — https://www.cisecurity.org/benchmark/docker — hardening baseline areas (§7).
- SLSA, "Security levels" (v1.0, page marked retired; v1.2 current) † — https://slsa.dev/spec/v1.0/levels — Build L0–L3 (§6).
- Sigstore, "Signing containers" † — https://docs.sigstore.dev/cosign/signing/signing_with_containers/ — keyless `cosign sign` (§6).
- Sigstore, "Verifying signatures" † — https://docs.sigstore.dev/cosign/verifying/verify/ — `--certificate-identity` / `--certificate-oidc-issuer` (§6).
- GitHub, "Security hardening for GitHub Actions" † — https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions — pin to full commit SHA; minimal `GITHUB_TOKEN`; workflow lockfile option (§6).
- GitHub, "OpenID Connect" — https://docs.github.com/en/actions/concepts/security/openid-connect — short-lived tokens instead of long-lived cloud secrets (§6).
- Aqua Security, "Trivy supply chain attack: what you need to know" † — https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know — 2026-03-19 tag force-push; exposure window; SHA pinning (example B).
- Supabase, "Database Backups" † — https://supabase.com/docs/guides/platform/backups — daily backups for Pro/Team/Enterprise only (Free: use `db dump`); Pro 7 days; PITR RPO 2 min, add-on cost, Small compute; Storage objects not included (§5).
- Node.js, "Previous releases" † — https://nodejs.org/en/about/previous-releases — v20 listed as EOL; LTS lines 22/24/26 (§7).
- Brendan Gregg, "The USE Method" — https://www.brendangregg.com/usemethod.html — utilization/saturation/errors per resource (§3).
- Grafana, "The RED Method" — https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/ — rate/errors/duration per service (§3).
- OpenTelemetry, "Signals" — https://opentelemetry.io/docs/concepts/signals/ — traces, metrics, logs, baggage (§3).

Not cited for lack of a free canonical URL: the 3-2-1 backup rule (industry convention, stated without a source), ITIL 4 (proprietary) and *Accelerate* (book; the DORA site stands in).
