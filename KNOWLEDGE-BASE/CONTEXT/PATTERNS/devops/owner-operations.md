# Owner operations — how the platform is run day to day (and how it survives and evolves)

> Owner: agent `ops-steward` · procedure: skill `noc-daily-ops`. Born 2026-10-29 from the owner's ask: "an agent that helps me operate and maintain this whole system … guide me through my daily routine, notifications, automations, reminders … preferably do it for me, but first let's validate."
> Research basis (2026-10-29, sources dated): Anthropic "Building effective agents" (Dec 2024), "Writing tools for agents" / "Effective context engineering" (Sep 2025), "Demystifying evals" (Jan 2026); OpenAI "A practical guide to building agents" (Apr 2025); OWASP Top 10 for Agentic Applications (Dec 2025); Meta "Agents Rule of Two" (Oct 2025); LangChain State of Agent Engineering (late 2025); Feng et al. levels of autonomy (Jun 2025).

## 1 · What an agentic system needs to survive in production

The textbook definition (goal · reasoning/planning · tool use · memory) describes what an agent *can* do. Surviving needs six more things, and noc already owns most of the primitives:

| Need | What it means | noc today | Gap → where it lands |
|---|---|---|---|
| **Harness** | the loop, tools, context policy, budgets, kill switch | seed LLM client, tool_loop, budget.py, provider_choice | per-request/conversation caps (D27), kill switch per agent |
| **Ledger** | every call attributed + priced (org · product · feature · purpose) | per-product llm_usage, unattributed | central `public.ai_usage` (D25) — billing foundation |
| **Evals** | golden set per agent, run on every prompt/tool/model change; grade outcomes, not tool-call sequences; pass^k for customer-facing | agents studio evals table (013) | seed eval harness in CI |
| **Observability** | one trace per run, tokens/cost/latency/outcome; SLOs on task success + cost per task, not just uptime | watchdog, latency_report, Sentry | scheduler run ledger, Operação page |
| **Least privilege** | Rule of Two: at most two of {untrusted input, sensitive data, state-changing/sending power} per session; tier actions; append-only audit | tool_audit, D31 404s, RLS tenancy | seed tool-permission tiers |
| **Lifecycle** | prompts/tools/model ids/evals in git; regression → canary on one org → rollout → rollback; every prod failure becomes an eval case | studio versioning, release gates | eval-gated promotion |

Rules that follow (each one is a decision, not advice):
- **Simplest thing that works**: single call → workflow → agent only when the steps can't be predicted. An SDR qualification flow is a workflow; "research this lead" is an agent. Multi-agent costs ~15× a chat — never by default.
- **Prompt injection is unsolved — design as if it succeeds.** Tenant isolation lives in RLS, never in the prompt; customer-facing agents never hold broad CRM read + send power together.
- **Mechanical first.** Code + cron for everything deterministic; LLM only where judgment is needed, and then budgeted and ledgered. The owner's spend-cutting rule: "use agents the less we need."
- **Hype flags**: vendor "AI firewalls", agents rewriting their own prompts in prod without an eval gate, "multi-agent by default", OTel GenAI conventions called stable (still Development status, mid-2026 — pin the version).

## 2 · The operating model (one founder + agents)

**Autonomy is per ACTION, not per agent** — four levels:

| Level | Meaning | Examples |
|---|---|---|
| L0 inform | report only | daily brief, cost summary, drift found |
| L1 suggest | propose with the exact command/diff + blast radius | fix a failing job, bump a dependency, rotate a token |
| L2 act-with-approval | do it after the owner's explicit yes in chat | deploy, migration, send a message to a customer, money, data deletion |
| L3 act-and-report | do it, then report | restart an unhealthy container (≤2 retries), re-run a failed idempotent job, refresh caches, tmp cleanup |

- **Promote** an action one level after a clean track record (≥10 clean runs, recorded); **demote** immediately after an incident. Record both in this file's §5 ledger.
- **Never L3**: anything that sends to a customer, moves money, deletes data, touches prod schema, or changes security/settings. A standing owner grant (e.g. the 2026-10-29 overnight ship grant) is per-session and lapses.
- **Restart loops hide root causes**: cap auto-retries, escalate the repeat as a finding.

## 3 · The daily rhythm

| When (BRT) | What | Mechanism | Cost |
|---|---|---|---|
| 06:00 / 18:00 | social snapshots (YT/IG/Meta) | product schedulers | API quota only |
| 07:00 | **owner brief** — changes & exceptions only, de-duplicated: failed/missing jobs, LLM spend per org→product, deploy state | core job → in-app + email; dead-man flag after 26h | zero LLM |
| every 10 min | prod watchdog | GitHub Actions, off-host | free |
| on session start | `noc-daily-ops`: brief + reminders + open pointers + debt top-5 → a 3-item "today" list | skill, read-only tools | session tokens only |
| weekly (Mon) | hygiene sweep, stale caches, advisor findings, debt roll-up, alert-usefulness review | skill `noc-hygiene` + this procedure | session tokens |

**Alert fatigue rule**: track alerts acted-on vs sent; an alert class acted on <50% of the time is pruned or merged into the brief. Digests over pings. The brief itself has a dead-man switch on a separate channel (the Operação page "brief missing" flag + watchdog).

## 4 · Where things live

- Health: `noctus.dev.prod_watchdog` · `smoke_fleet` · `deploy_verify` · `latency_report` · `supabase_advisors` · `noctus.vps_*`.
- Jobs: seed scheduler (`seed/lib/backend/noctusai_lib/api/scheduler.py`) + `public.scheduler_runs` ledger + core admin **Operação** page.
- Cost: `public.ai_usage` (D25) · `public.cost_ledger` · `/cost-report` for vector spend.
- Debt: `scan_remediation_markers` · `branch_pointer list` · `findings` · `auto_improvement_query` · roadmaps.
- Reminders: memory `MEMORY-reminders.md` (session-bound today; a due-dated, pushable store is open — see the overnight roadmap).
- Notify: `noctus.dev.notify` (email + WhatsApp, plan-first) · seed `write_in_app` (bell). Telegram (D33) has no code yet.

## 5 · Autonomy ledger (promotions / demotions)

| Date | Action | From → To | Evidence |
|---|---|---|---|
| 2026-10-29 | initial levels | — | this doc §2 |

## Open (named destinations)
- AI agents acting on the mechanical time-based reports — owner: "we'll work on that later" (2026-10-29). Lives in `project-history/roadmaps/overnight-platform-2026-10.md` § Later.
- Telegram channel + severity routing + quiet hours (D33).
- Due-dated reminder store that can push to WhatsApp.
