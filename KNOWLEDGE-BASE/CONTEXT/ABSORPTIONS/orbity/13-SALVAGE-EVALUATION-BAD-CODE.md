# 13 — Salvage Evaluation: the Ideas Behind the Bad Code

> **Directive (user, 2026-06-02):** where noc supersedes Orbity, don't just discard. **A weakness can encrypt a valuable idea, poorly executed.** For each Orbity drift / error / loss-on-comparison: (1) decrypt the **rationale** behind the bad code (why did they do it that way?), (2) judge whether the **idea** behind it is valuable, (3) decide whether it's worth **fixing the execution to absorb the functionality.** Bad code ≠ bad idea.

## Method

For each Orbity weakness, a verdict:
- 🟩 **SALVAGE-IDEA / FIX-CODE** — valuable idea, poor execution → re-implement clean on noc's seam, absorb the functionality.
- 🟦 **ABSORB-AS-IS** — good idea *and* good execution (battle-tested) → port the technique faithfully.
- 🟥 **SKIP — noc supersedes** — the code is just bad and noc already has the better mechanism; the *functionality* is still absorbed, but via noc's clean organ, not their code. (The bad code often still teaches a confirming lesson.)
- ⬜ **SKIP — no value** — hygiene debt / dead code, nothing to learn.

## The evaluation

| # | Orbity weakness (from 08/09/10/11) | Rationale behind the bad code (decrypted) | Is the idea valuable? | Verdict |
|---|---|---|---|---|
| 1 | **`monthly_snapshots` write-only & diverge from live** (uses `amount` not `amount_paid`, ignores `gateway_fee`, FE never reads them) | Closure job written to produce them, but the FE was built first/separately computing KPIs live → snapshots orphaned (fast Lovable iteration, two authors, no single-source discipline) | **YES** — frozen-at-event-time financials = cheap reads + consistency + audit trail + a clean feed for PPR/reports | 🟩 **SALVAGE-IDEA** — seed finance organ writes snapshots **as the read source of truth** (net-of-fees, `amount_paid`), not a parallel artifact |
| 2 | **PPR profit-share built then DROPPED** (formulas authored out-of-VCS in Lovable, abandoned after ~3 months) | Over-built for the agency's stage; calc bodies lived in the dashboard, not the repo → unmaintainable → ripped out | **YES** — a statute-aware (Lei da PPR) incentive model: pool gated by revenue ∧ NPS, split by eligibility-weight × a 3-dimension weighted scorecard, with staleness-recalc triggers | 🟩 **SALVAGE-IDEA** — the *design* is captured (09 §4); rebuild clean as a seed organ **if/when a product needs profit-sharing**. Do NOT resurrect their code |
| 3 | **Auto-tax classification by free-text category keyword match** (`[imposto,tributo,taxa,das,simples,iss,…]`) feeding the DRE | Speed — `expenses.category` is free-text with no FK; tax detection bolted on as a string heuristic | **YES** — auto-classifying expenses as taxes so the DRE separates Impostos automatically is genuinely useful | 🟩 **SALVAGE-IDEA / FIX** — typed category + explicit `is_tax`/`tax_kind` flag (or a small classification-rules table), not fragile keyword matching |
| 4 | **`Math.random()` mock-data fallbacks in production FB paths** (`facebook-sync`/`analysis` fabricate spend when Graph fails/short) | Avoid blank dashboards during dev/demo; never hardened back to a real empty/error state | **PARTIALLY** — graceful degradation on integration failure is a real need; *fabricating numbers* is the dangerous part | 🟩 **SALVAGE-IDEA / FIX** — degrade to an explicit **"data unavailable"** empty/error state, **never fabricate** (noc's *no-silent-errors* already mandates this) |
| 5 | **TS edge + PL/pgSQL trigger dual-implementation** of automation start/condition | Wanted a flow to start whether a lead arrives via an edge-function webhook OR a direct DB insert → duplicated the logic in two languages | **YES** — *multiple trigger sources feeding one engine* is the right resilience goal | 🟩 **SALVAGE-IDEA / FIX** — one engine, one contract (the seed automation organ), multiple **trigger sources** funnel into it; never two impls of one rule |
| 6 | **`agency_ai_prompts` CHECK `IN('task','post')` but 8 prompt types read** (6 silently un-saveable) | CHECK shipped early; the function grew 6 more types; the constraint was never widened | **YES** — per-tenant AI-prompt customization is a good capability | 🟩 **SALVAGE-IDEA / FIX** — per-tenant prompt overrides with an extensible/typed model, no narrow CHECK drift |
| 7 | **Hardcoded `MASTER_AGENCY_ID` + dogfooding via `orbity_leads`** | Single-vendor MVP shortcut — the "platform operator" tier was a UUID check, not a role | **YES (the idea)** — a platform-operator tier *and* dogfooding the product's own CRM to sell it are both valuable | 🟩 **SALVAGE-IDEA / FIX** — a real platform-role/flag (noc `core.fleet_control` supersedes the mechanism); keep the dogfooding pattern |
| 8 | **Prepaid-BRL ad-account balance via regex on `funding_source_details.display_string`** | Meta's API exposes no clean "available balance" for prepaid BRL accounts → they regex `R$ x.xxx,yy` with a tiered fallback | **YES** — hard-won knowledge of a real gap in Meta's BR billing surface | 🟦 **ABSORB-AS-IS** — port the technique; it's the right answer to a real-world API hole |
| 9 | **Accent-folded `normalize()` on both question & answer** for pt-BR form matching | Meta sends `full_name` snake_case; human rules say `"full name"`; pt-BR has accents | **YES** — the unglamorous detail that makes pt-BR matching work at all | 🟦 **ABSORB-AS-IS** — bake a canonical pt-BR normalizer into the seed |
| 10 | **Open `USING(true)` RLS on core finance tables** | Genesis single-tenant era; never tightened after the multi-tenant retrofit; app-layer `.eq('agency_id')` masked it | **NO (no new idea)** — but the *lesson* is valuable | 🟥 **SKIP — noc supersedes** (RLS-via-trusted-table). Lesson confirms noc's *run `get_advisors` after any RLS change* + *retrofit leaves permissive policies* discipline |
| 11 | **Plaintext FB / integration tokens** (`facebook_connections.access_token`) | Speed; no encryption-at-rest beyond Postgres | **NO** | 🟥 **SKIP — noc supersedes** (`credential_vault` + bytea-hex parity). The *integration functionality* is absorbed via noc's encrypted-cred seam |
| 12 | **No webhook HMAC** (FB `leadgen` + UAZAPI inbound trust any caller) | Speed; relied on verify-token + dedup | **NO** | 🟥 **SKIP — noc supersedes** (webhook-signature discipline + `security` advisor). Lead-ads *functionality* absorbed **with HMAC added** |
| 13 | **Lovable AI-gateway lock-in, no cost-logging** | Built on Lovable → its gateway is the path of least resistance | **NO (infra)** / **YES (the prompts)** | 🟥 **SKIP infra** (noc `llm` lib + per-org cost governance supersedes). The **prompt content + patterns** (11) are the value, absorbed |
| 14 | **No `_shared` admin-client factory** (~60 inline `createClient(SERVICE_ROLE_KEY)`) | Edge-function-per-file with no shared lib discipline | **NO** | 🟥 **SKIP — noc supersedes** (seed adapters + factory). A DRY confirmation, nothing to salvage |
| 15 | **`profiles.role` overloaded** (job-role + platform super_admin) | Retrofit bolted platform-role onto the existing job-role column | **NO** | 🟥 **SKIP — noc supersedes** (`core.roles`). Split the concerns on absorption |
| 16 | **Single-active-agency** (`get_user_agency_id LIMIT 1`) | MVP simplicity | **NEUTRAL** — *both* noc and Orbity share this limitation | ⬜ **NOTE** — not Orbity-specific; a *platform* decision for the seed if multi-org-switching is ever wanted |
| 17 | Dead cron schedules, deprecated stubs, mixed Graph v18/v19, `_deprecated` tables | Fast-iteration churn, incomplete migrations | **NO** | ⬜ **SKIP — no value** (hygiene debt; don't port) |
| 18 | Orbity **lacks** segmentation/analytics depth in email-marketing (uses SendPulse plainly) | Single-provider email | **n/a — noc ahead** | 🟥 noc's ESP supersedes; only a **SendPulse adapter** if a tenant needs that provider |
| 19 | Orbity **lacks** e-signature (manual contracts) | Out of scope for them | **n/a — noc ahead** | 🟥 noc's 3-provider e-sign supersedes; salvage Orbity's **fiscal-snapshot-at-signing** idea (🟩, see 08 #7) |

## Net salvage list — valuable ideas worth fixing-then-absorbing

These are the "ideas were valuable, execution poor" items — re-implemented clean on noc's seam as part of the relevant seed organ (see [`12 §2`](./12-ABSORPTION-STRATEGY-SEED-FIRST.md)):

1. **Snapshot-as-read-source-of-truth** for financials (net-of-fees, single source) → seed `domain.finance`.
2. **PPR profit-share model** (revenue∧NPS-gated pool × eligibility-weight × 3-dim scorecard) → seed organ, rebuilt clean, demand-gated.
3. **Auto-tax classification** for the DRE (typed/rules, not string keywords) → seed `domain.finance`.
4. **Graceful integration-failure degradation** (explicit unavailable state, never fabricate) → a cross-organ pattern (already noc doctrine; Orbity is the cautionary example).
5. **Multi-entry-source automation triggers** (one engine, many sources) → seed `domain.automation`.
6. **Per-tenant AI-prompt overrides** (extensible model) → seed AI/chatbot organ.
7. **Platform-operator tier + dogfooding** the product's own CRM → noc `core.fleet_control` + an absorption pattern.

## Absorb-as-is (good idea + good execution)
Prepaid-BRL balance extraction · accent-folded pt-BR matching · the CAPI quality-feedback loop · anti-ghost 60-day forecast · dunning dedup-tracking ledger · schedule-windows (`outside_window_behavior`) · WhatsApp line-purpose routing · idempotent-closure two-layer guard · the `setup-demo-account` demo-fixture pattern.

## Skip — noc supersedes (functionality absorbed via noc's clean organ, not their code)
Plaintext tokens · open `USING(true)` finance RLS · missing webhook HMAC · Lovable AI lock-in · inline-client duplication · overloaded `profiles.role` · mixed Graph versions · dead crons/stubs.

> **The meta-lesson (feeds the methodology codification):** *"Skip — noc supersedes" is a verdict on the CODE, never automatically on the FUNCTIONALITY.* Every 🟥 row still has its capability absorbed — through noc's disciplined organ. The salvage pass exists precisely so a 🔴 "they do it worse" verdict in the comparison (08) doesn't throw away a valuable idea trapped inside bad execution.
