# 12 — Absorption Strategy: Seed-First Capability Uplift & Propagation Loop

> **Strategic intent (user, 2026-06-02):** the goal is to **improve our own mechanism *at the seed*, then propagate it back to the orbity-noc product without drift or quality loss.** The gain: every capability we harden on the seed propagates to **all** products — including the new orbity-noc version. The absorption is a **platform-uplift engine**, not a product port.

## 1. The loop (this is the methodology, applied)

```
   Orbity (battle-tested capability, real-business-proven)
        │  learn the INTENT (docs 08-11) — not the code
        ▼
   ┌─────────────────────────────────────────────┐
   │  SEED  — harden as a canonical organ /        │   ← improve OUR mechanism
   │  adapter / engine on noc's disciplined seam   │     (RLS-via-trusted-table,
   │  (seed/lib/* or seed framework)               │      encrypted creds, no silent
   └─────────────────────────────────────────────┘     fallbacks, contract-first, tested)
        │  pilot-products-first (prove on 1-3 cousins)
        ▼
   erp-imobiliario · social-wiring · core · personal-finance · …  ← propagation GAIN to the whole fleet
        │  the new orbity-noc product is just ANOTHER CONSUMER
        ▼
   orbity-noc  (consumes the same organ via named seams — no fork)
```

**Why this avoids drift + quality loss:** there is exactly **one** canonical implementation (the seed organ). Products — orbity-noc included — *consume* it; they never re-implement it. noc already enforces this (`check_canonical_organ_consumption`, products-consume-canonical-organs). So "propagate back to orbity-noc without drift" is automatic *by construction*: orbity-noc imports `@noctusai/lib/...`, gets the hardened mechanism, and any later improvement to the organ propagates to every consumer at once.

**The anti-pattern this rejects:** porting Orbity's code into a `products/orbity/` silo. That would (a) fork the capability (drift), (b) inherit Orbity's weaknesses (open finance RLS, plaintext tokens, mock-data fallbacks — see 09/10), (c) give zero platform gain. **We don't port Orbity. We let Orbity *teach the seed*, then orbity-noc is born already consuming the better mechanism.**

## 2. The capability → seed-organ map (where each learning lands)

Each Tier-1/Tier-2 learning from [`08-CAPABILITY-COMPARISON`](./08-CAPABILITY-COMPARISON.md) becomes a **seed capability**, not an orbity-noc feature. The "propagation gain" column is the whole point — what the *rest of the fleet* gets for free.

| Learning (from Orbity) | Seed organ to build / extend | Disciplined-seam upgrades vs Orbity | Pilot consumers (prove here) | Propagation gain (fleet-wide) |
|---|---|---|---|---|
| **Financial mgmt** (DRE, month-end closure, recurring/installment, dual accrual/cash, dunning) | **NEW** `noctusai_lib.domain.finance` (closure engine + DRE service + expense model + dunning) | RLS-via-trusted-table (not `USING(true)`); snapshots that are *read* (single source); typed categories (not string); no abandoned-PPR | **erp-imobiliario** (near-isomorphic), personal-finance | Every money product gets DRE + idempotent closure + dunning |
| **Meta CAPI + Lead-Ads** | **EXTEND** `noctusai_lib.integrations.meta` (CAPI events + PII hash + pixel + lead-ads ingestion + spend/balance) — and **WIRE** the existing unwired ads adapter | encrypted tokens + refresh; webhook HMAC; no `Math.random()` fallbacks; cost-logged | erp-imobiliario (`meta_api`), social-wiring | Fleet gets real ad-ops + the CAPI quality-feedback moat |
| **No-code automation flow engine** | **NEW** `noctusai_lib.domain.automation` (durable-queue + trigger/condition/branch/action/delay + stop-rules + schedule-windows) | one implementation (not TS+PLpgSQL mirror); contract-first step schema; replaces external n8n reliance | social-wiring (replaces email-only drip), erp, daily-life | Platform-wide no-code automation; less n8n |
| **Multi-channel notifications** (fan-out, per-event prefs, web-push, dedup ledger, channel-by-purpose) | **EXTEND** `core` notification_service + seed `domain/notifications` (channel adapters Slack/Discord/FCM + prefs matrix + tracking ledger) | builds on noc's email-digest framework; encrypted webhook URLs | core, daily-life, erp | Every product gains Slack/Discord/push + opt-in prefs |
| **BR payment/fiscal** (PIX/boleto via Asaas, NFS-e via Conexa, reconcile-cron, dual-rail) | **NEW** `noctusai_lib.integrations.asaas` + `noctusai_lib.integrations.conexa` (Protocol+Fake+Real+factory) + dunning/reconcile pattern | bytea-hex credential parity; Fake+Real+factory (noc seed-IO contract); cost/audit logged | adconnect, erp-imobiliario, therapy | Fleet gets BR billing rails + fiscal invoicing |
| **Lead-scoring rule engine + public capture** | **EXTEND** seed CRM domain (configurable scoring rules + temperature) + a **seed public lead-capture route** | seed-mounted route (like consent routes); typed rule model | erp-imobiliario funil | Any product with leads gets configurable scoring |
| **Client-approval workflow + content calendar** | **EXTEND** social-wiring media organ → approval states + token-action + calendar | reuse noc's hardened token-portal + consent-route pattern | social-wiring, media-creator | Content products gain client approval + calendar |
| **BR WhatsApp** (9th-digit phoneVariants, inbound→lead auto-promotion) | **EXTEND** `noctusai_lib.integrations.whatsapp` (phoneVariants) + `domain/chatbot` (conversation→lead linking) | keep WAHA provider; reuse noc chatbot orchestrator (ahead of Orbity's) | social-wiring, erp | Fleet WhatsApp gets BR matching + lead linking |
| **PWA + product-tour + white-label** | **EXTEND** seed FRONTEND framework (PWA manifest/SW + tour engine + branding framework) | one seed framework → every product inherits | seed → ALL products | Every product becomes installable + toured + brandable |
| **Bulk Excel import** (column-mapping + chunked) | **NEW** `noctusai_lib.domain.import` (mapping + chunked insert) | typed mapping; trigger-cascade-safe | any product | Fleet gains a generic importer |

## 3. Quality & no-drift guards (already in noc — this loop leans on them)

- **Seed-first / componentize-everything** — a capability that ≥2 products need is built shared from day one (`KB § 04-SHARED-LIBRARY.md`). Every organ above qualifies.
- **Products consume canonical organs** — `check_canonical_organ_consumption` blocks a product (orbity-noc included) re-implementing an organ locally → **propagation-back-without-drift is enforced, not hoped for.**
- **Seed IO ships Fake+Real+factory** — the Asaas/Conexa/Meta adapters follow the seed-IO contract (no half-ship → no consumer-side fork).
- **Contract-first (FE↔BE + API + DB/RLS)** — author each organ's contract before building both sides; fit by construction.
- **Pilot-products-first** — prove each organ on 1-3 cousins (erp-imobiliario is the standout pilot) before fan-out; orbity-noc is the *last* consumer, validating the organ end-to-end.
- **Absorb the intent, not the code** — Orbity's weaknesses (09 §6, 10 §7) are re-implemented away on noc's disciplined seam; we keep noc's existing advantages (LLM cost governance, e-sign, portal hardening, ESP — see 08 Tier-3).

## 4. Implication for the absorption gates (methodology adaptation)

The standard absorb-product flow (`noc-absorb-product`) treats Gate 6 as "seed-reconcile the product's bones." **This absorption inverts the emphasis:** the *primary deliverable is the seed organs* (platform uplift); the orbity-noc product is the *validation consumer* born at the end. Concretely:

1. **Gate 5 (scaffold)** — scaffold orbity-noc as a thin shell that will *consume* organs, not host logic.
2. **Gate 6 (seed-reconcile) becomes Gate 6′ (seed-UPLIFT)** — build/extend the organs in §2, pilot-first, each on its disciplined seam. This is where most of the value is created and where the *whole fleet* gains.
3. **Gate 7 (port)** — orbity-noc consumes the organs via named seams (the "propagate back" leg) — by construction no drift.
4. **Gates 8-10** — consumer-adapt, teardown (salvage + absorb these docs into noc KB), container-refactor.

> **Candidate methodology codification (noc-side, when greenlit):** *"Absorption is seed-capability-uplift, not product-port — the absorbed product is the last consumer of organs it taught the seed to grow."* This sharpens the `noc-absorb-product` skill's Gate 6 and composes with seed-first + products-consume-canonical-organs + pilot-products-first. To be proposed into `KB § GUIDES/absorb-seed-workspace.md` + the skill at dev-greenlight (not codified yet — diagnosis phase).

## 5. The compounding gain (why this is worth doing carefully)

Because every learning lands on the seed:
- **erp-imobiliario** (the cousin) gets DRE + closure + CAPI + automation + BR billing + lead-scoring — it becomes dramatically more complete *as a side-effect* of absorbing Orbity.
- **social-wiring** gets the real automation engine (retiring its email-only drip) + multi-channel notifications + BR WhatsApp.
- **the whole fleet** gets PWA + product-tour + white-label + multi-channel notifications + a generic importer.
- **orbity-noc** is born already consuming all of it, at noc quality, with zero forked code.

That is the "in gains, we improve our capabilities to also propagate to other products" the directive names: **Orbity is the teacher; the seed is the student; the fleet is the beneficiary; orbity-noc is the proof.**
