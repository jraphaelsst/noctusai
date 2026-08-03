# META-LEADS-HANDOFF.md — session handoff → integrate + deploy

> **Written 2026-08-03** by the session that built Meta Lead-Ads ingestion.
> Companion to `META-LEADS-CHECKLIST.md` (what shipped) and
> `project-history/roadmaps/meta-ads-console-2026-07.md` (the durable roadmap).
> This file is the *what you need to know to finish it* view.

---

## 1 · State in one table

| | |
|---|---|
| **Branch** | `feat/meta-leadgen-webhook` @ `7f8465d4` — **14 commits, NOT pushed** |
| **Worktree** | `.claude/worktrees/meta-leadgen-webhook` — clean |
| **Already on `origin/dev`** | Slices 0, 3, 4 (pushed before the operator asked me to stop pushing) |
| **Prod** | `origin/main` = `origin/prod` = untouched. **Nothing of this work is in production.** |
| **Suites at the tip** | social-wiring **1565** · erp-imobiliario **2161** · seed lib **2545** · frontend **483** — all by exit code, all on the merged tip |

**Operator instruction still in force:** *commit for history, do not push* — and
**no prod deploy until everything is validated**, one promotion at the end rather than a trickle.
Do not push or promote without re-confirming that instruction has been lifted.

---

## 2 · 🔴 The one thing that will bite you first: migration 040

**Three branches, two different files, same number, all unpushed.**

| Branch | File | Status |
|---|---|---|
| `feat/imoveis-phase2` | `040_imoveis.sql` | unpushed |
| `feat/wa-inbox-schema` (+ `wa-ingest`, `wa-read-endpoints`, `whatsapp-realtime-inbox`) | `040_whatsapp_inbox_realtime_schema.sql` | unpushed |
| `feat/meta-leadgen-webhook` (this work) | `042_meta_webhook_events.sql` | unpushed — **no conflict** |

`origin/dev` currently holds `…039`, then **`041_leads_meta_lead_id.sql`** (mine, already landed).
So the live sequence has a **gap at 040**, reserved by whichever of the two claimants merges first.
**The second one MUST renumber to `043`.** Renumber the file *and* any structural test that
references it by name.

**How to detect this class of collision** (the ONLY check that works — `ls migrations/` and
`git log origin/dev` both miss unpushed sibling branches):

```bash
for b in $(git branch --format='%(refname:short)'); do
  f=$(git diff --name-only origin/dev...$b 2>/dev/null | grep 'backend/migrations/')
  [ -n "$f" ] && echo "$b -> $f"
done
```

**No migration on any branch has been applied to any database.** `041` and `042` are both
`🔴 MIGRATION FILE ONLY`. Applying them is a separate, explicitly-consented step (§4).

---

## 3 · Merge order (three initiatives, one tree)

Three agents worked this tree concurrently. Suggested integration order, lowest-risk first:

1. **`feat/meta-leadgen-webhook`** (this work) — 042 is uncontested, and its product-backend zone
   (`modules/meta_ads`, `modules/leads`) is disjoint from the WhatsApp zone.
2. **`feat/wa-*` / `feat/whatsapp-realtime-inbox`** — 30 commits; owns `integrations/whatsapp`,
   `noctusai_lib/realtime`, `design-system/chat`, `whatsapp_router`, `message_store`.
3. **`feat/imoveis-phase2`** — renumber its 040 if the WhatsApp work landed first.

**Known shared-file contention to expect at merge:**
- `products/social-wiring/backend/migrations/` — the 040 problem above.
- `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` — the `kb_sync` pre-commit hook rewrites counts in it,
  so nearly every branch touches it. Conflicts here are mechanical; take either side and let the
  hook regenerate.
- `project-history/*.ndjson` ledgers — append-only, `merge=union` is configured. Do not hand-resolve.

🔴 **Re-run gates on the MERGED tip, not per-branch.** File-disjoint is not effect-disjoint; the
seed lib is shared and derived artifacts couple the slices.
→ `KB § PATTERNS/common/methodology-execution-discipline.md`

---

## 4 · Path to production (ordering is NOT flexible)

1. **Integrate** all three branches to `dev`; re-run gates on the merged tip.
2. **Apply migrations** with explicit operator consent — `noctus.dev.migrate_product`.
   ⚠️ That tool has **no `worktree_path` parameter**: run it from the PRIMARY checkout, or it will
   apply whatever is pending *there* rather than your branch's file. (Logged as drift by a peer.)
   - `042_meta_webhook_events.sql` (this work) · plus the WhatsApp and imoveis migrations.
3. **Promote + deploy** `social-wiring` per skill `noc-ship`. **No new prod-exposure consent is
   needed** — `social-wiring` is already on all three gated surfaces, and
   `check_prod_exposure_consent` fires only on a slug's *first* arrival.
4. 🔴 **ONLY NOW: the operator configures the Meta App Dashboard.** Meta issues the GET handshake
   **synchronously** when they click *Verify and Save*, and refuses to save the subscription if it
   fails — so the receiver must already be live. Full runbook: `META-APP-VERIFICATION.md` §10.
   - Callback URL: `https://social.noctusai.com/api/meta/leadgen/webhook`
   - Verify token: the value of `META_WEBHOOK_VERIFY_TOKEN` (must be set in the root `.env` or the
     Fernet vault **before** step 3).
5. **Subscribe the Pages** — in-product: Meta → Anúncios → Leads → "Assinar páginas".
   ⚠️ App-level (dashboard) and Page-level (this) are **both** required. Either alone delivers
   nothing, silently.
6. **Live-verify** with the Lead Ads Testing Tool → Create Lead. Within ~30s expect **all three**:
   an inbox row `status='processed'`, a `meta_ads_leads` row with **non-null** name/email/phone
   (null ⇒ the form-schema lookup failed), and exactly **one** `negociacoes_venda` card.
   Then replay the same signed payload → `200 duplicate`, **no second card**.
7. **Run the backfill** for the 958 stored leads: `POST /api/leads/meta-ingest/backfill`
   (deliberate, authenticated, idempotent — never auto-runs).

---

## 5 · Deliberately not done — do not "finish" these by accident

| Item | Why |
|---|---|
| **Slice 5b — live push (no-refresh lead list)** | SUSPENDED by operator decision. The peer is building `noctusai_lib/realtime` (SSE + Redis) for the WhatsApp inbox. Two realtime primitives in one seed is a fork. Assess their transport once it lands, then build the Meta live session **on top of it** — do not add Supabase Realtime as a second mechanism. |
| **erp Graph-client consolidation** | Scoped down on purpose. erp is a testing ground still being refined and its Meta receiver is inert (0 config rows, 0 leads). **The canon lives in `social-wiring`**; erp's remainder is drift against it, not a second model. The *security* half was fixed. |
| **Slice 7 — CSV history import** | Conditional. Meta permanently deletes leads after 90 days; anything before ~2026-04-28 is unrecoverable by any means. Only build if the operator finds off-platform exports or Meta notification emails. |

---

## 6 · Things this session learned that will save you time

- **`noctusai_lib` resolution in worktrees is already solved** — every product's `tests/conftest.py`
  injects this tree's seed roots and purges shadowing editable finders. Your **pytest runs are
  correct and need no `PYTHONPATH`**. But a bare `python -c` does *not* load conftest and will
  report the PRIMARY tree's copy. A manual import probe contradicting your worktree is the probe
  being wrong. (I burned real time getting this backwards — the retraction is in
  `auto-improvement.ndjson`.)
- **Prove a guard can fail before trusting it.** New in `methodology-execution-discipline.md` §4.
- **Grep for prior art before designing a mechanism.** New in the same doc, §5.
- **The pre-commit agent-context gate is flaky under concurrent sessions.** If it blocks on a cache
  you did not touch: `NOCTUSAI_HOME=$PWD <venv> mcp/noctusai/cli.py --refresh-agent-context-cache --force`.
  Never `--no-verify`.
- **Verify by exit code, never a piped `tail`** — `cmd | tail` returns tail's status. I tripped this
  and misread an aborted commit as successful.

---

## 7 · Open surfaced items (in `auto-improvement.ndjson`, none blocking)

- `notification_log` is upload-shaped — a lead-triggered row cannot be traced back to its
  `meta_ads_leads.id`. Needs a generic `source_kind`/`source_id`. N=2 ⇒ triage now, mandatory at a
  third notification source.
- `migrate_product` has no `worktree_path` (peer-surfaced; see §4 warning).
- agent-context cache freshness flakiness under concurrent sessions.
- `seed/framework/frontend/node_modules` is not wired by worktree provisioning — bites any
  full-stack dispatch needing `tsc`/`vite build`.
