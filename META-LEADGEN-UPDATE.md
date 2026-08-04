# META-LEADGEN-UPDATE.md — Meta AI-agent lead qualification

> **Status: SHELL SHIPPED, PROCESSOR DELIBERATELY UNFINISHED.** Everything here
> is captured from the wire on **2026-08-04**, because Meta documents none of it.
> Read §4 before writing a line of the processor — it is the whole point of this file.
>
> Durable pattern home: `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md § leadgen_update`.
> Sibling trackers: `META-LEADS-CHECKLIST.md` (the ingestion feature) ·
> `META-APP-VERIFICATION.md` §10 (dashboard runbook).

---

## 1 · What `leadgen_update` is

A Page webhook field carrying **Meta's AI-agent lead-qualification updates**. Meta's
AI agent converses with a lead after submission and revises its assessment; each
revision fires this webhook.

It is a **different event class** from `leadgen`, not a variant of it:

| | `leadgen` | `leadgen_update` |
|---|---|---|
| Means | a new lead was **submitted** | an existing lead's **qualification changed** |
| Nature | immutable fact, fires once | mutable state, fires repeatedly per lead |
| Key | `leadgen_id` is a natural PK | `leadgen_id` alone is **not** a PK |
| Carries | ad context | ad context **+** `area` / `event` / `updated_fields` |

🔴 **Conflating them creates duplicate leads.** A qualification change routed down
the new-lead path would be enriched and upserted as a fresh submission. The two
parsers are deliberately separate functions returning different types, and
`test_the_two_parsers_never_see_each_others_events` pins that.

---

## 2 · The payload — captured, not guessed

Meta's own **"Teste" → Exemplo do campo `leadgen_update`** sample, v26.0,
App Dashboard, 2026-08-04:

```json
{
  "field": "leadgen_update",
  "value": {
    "adgroup_id": 123456789,
    "ad_id": 123456789,
    "leadgen_id": 987654321,
    "page_id": 111111111,
    "form_id": 222222222,
    "updated_time": "1704067200",
    "area": "ai_agent_updates",
    "event": "qualification_status_change",
    "updated_fields": ["qualification_details", "qualification_status"]
  }
}
```

**Three wire facts that will bite anyone who assumes otherwise:**

1. **Ids are INTEGERS here and STRINGS in the `leadgen` sample.** Meta is
   inconsistent with itself. Every id goes through `_stringify`; a comparison
   against a `str` PK would silently never match otherwise.
2. **`updated_time` is a quoted STRING** unix timestamp, where `leadgen`'s
   `created_time` is a bare number.
3. **`updated_fields` names WHICH fields changed and carries NONE of their
   values.** Reading the qualification data requires a Graph call — the same
   indirection `leadgen` uses for PII.

`area` reads as a namespace (`ai_agent_updates` is one; others likely exist) and
`event` as the change within it. Neither is treated as an enum — an unrecognised
pair is preserved and surfaced, never dropped.

---

## 3 · What is built (and works)

| Layer | Where | State |
|---|---|---|
| Parser | `noctusai_lib.integrations.meta.leadgen_webhook.parse_leadgen_update_webhook` → `LeadgenUpdateEvent` | ✅ real, 11 tests off Meta's verbatim sample |
| Routing | `leadgen_router.leadgen_receive` — parsed FIRST and separately from `leadgen` | ✅ real |
| Capture | `LeadgenWebhookService.process_qualification_event` | ✅ real |
| Lead match | `_find_lead(leadgen_id)` against `meta_ads_leads` | ✅ real |
| **Apply qualification to lead / funnel** | — | ❌ **not built — see §4** |

**Inbox row shape** (no migration needed — `field`/`object_type`/`status` already existed):

- `id` = `upd:<leadgen_id>:<fingerprint>` — namespaced away from real leadgen_ids
  and from `evt:` unknown-field rows.
- **fingerprint** = sha256 of `(updated_time, area, event, updated_fields)`, so
  successive *different* changes to one lead are separate rows (a qualification
  **history**) while a Meta **retry** of one change is idempotent.
- `status` = `received` when the lead matched · `unresolved` when it did not
  (the lead predates the receiver, or belongs to a page we do not sync — that is
  information, not an error, and must not enter the retry queue).
- `payload` = `area`, `event`, `updated_fields`, `matched_lead`, and the **raw
  value verbatim**.

---

## 4 · 🔴 Why the processor is NOT built, and what finishes it

**Do not "complete" this from the docs. There are no docs.**

`updated_fields` gives field NAMES only. Applying a qualification means calling
Graph for the lead and reading fields whose **names, types, and enum values we
have never observed**. Meta publishes nothing, and its test payload omits them.
Writing that mapping now means inventing a schema; the failure mode is not a
crash but **silently-wrong qualification on real leads** — worse than no feature.

### The trigger

One real, non-test `leadgen_update`. Find it with:

```sql
SELECT id, status, payload, received_at
FROM social_wiring.meta_webhook_events
WHERE field = 'leadgen_update'
  AND payload->>'leadgen_id' NOT IN ('987654321')  -- Meta's test id
ORDER BY received_at DESC;
```

The receiver also logs it at **WARNING** with the 🔔 marker, so it is greppable
in `noctus_vps_logs` without a query.

### Then, in order

1. **Read the captured `payload.raw`** — the real `area`/`event` vocabulary may
   be wider than the single sample.
2. **Call `GET /{leadgen_id}` with the Page token** and diff the response against
   what `meta_ads_leads.raw` already holds. The delta IS the qualification schema.
   Record it in `KB § INTEGRATIONS/meta.md` before writing code.
3. **Extend `meta_ads_leads`** with the qualification columns (migration — and it
   will need a real number; check for collisions across unpushed branches).
4. **Map qualification status → funnel stage** so a Meta-qualified lead
   auto-advances its `negociacoes_venda` card. This is the actual product value;
   everything above is plumbing to reach it safely.
5. **Decide the notification policy.** A lead qualifying is arguably a bigger
   event than it arriving. Reuse `notify_new_lead`'s `_dispatch` core; do not
   invent a second fan-out.

### Open questions to answer with the real event, not by reasoning

- Does it fire for **organic** leads or only paid?
- Can qualification move **backwards** (qualified → unqualified)? If so, does the
  funnel card move back, or is that a human decision?
- Is `updated_time` the agent's revision time or the conversation's?
- Does one conversation emit **many** events, or one on completion?

---

## 5 · Operator state (2026-08-04)

- `leadgen` — **subscribed**, app-level ∧ Page-level, verified end to end with two
  real production leads.
- `leadgen_update` — subscribed for capture. **Whether it ever fires depends on
  the AI-agent feature being enabled on the account's forms/campaigns**, which was
  being confirmed with the paid-traffic team at the time of writing. The sample
  proves the contract, not that it is active.
- Cost of leaving it on: one inbox row per event. It touches nothing else.

---

## 6 · Session note

This shell exists because the user said: *"If we don't use it now, we will, soon."*
That is the right reason to build a capture path and the wrong reason to build a
processor. The split above is deliberate — capture is cheap, correct, and useful
immediately; the processor is expensive, unverifiable today, and dangerous if
guessed. When the real event lands, everything needed to finish it will already
be sitting in `meta_webhook_events`.
