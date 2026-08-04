# META-LEADS-HANDOFF.md — post-integration state → migrations + prod

> **Rewritten 2026-08-04 after integration.** The earlier version of this file described a
> pre-merge world (three unpushed branches, a contested migration 040) that no longer exists.
> A stale handoff is worse than none — it sends the reader to solve a problem that is already
> solved. Everything below is the state as of the integrated `dev`.
>
> Companion: `META-LEADS-CHECKLIST.md` (what shipped) ·
> `project-history/roadmaps/meta-ads-console-2026-07.md` (durable roadmap).

---

## 1 · State

| | |
|---|---|
| **Integrated** | ✅ All Meta lead-ads work is on `origin/dev` @ `7f1495db` |
| **Gates on the pushed tip** | social-wiring **1658** · erp-imobiliario **2161** · seed lib **2662** — all exit 0; `check_migration_number_collision` clean |
| **Prod** | `origin/main` = `origin/prod` = `4db0c4bc` — **untouched** |
| **Blocking prod** | two migrations unapplied + the operator's Meta dashboard steps |

Three initiatives merged into `dev` concurrently: this Meta lead-ads work, the WhatsApp realtime
inbox, and Imóveis/Vista. All three are integrated and green together.

---

## 2 · Migration state — read before touching the database

**Applied:** `036` · `040_imoveis` · `042_whatsapp_inbox_realtime_schema` · `043_lead_campanhas_vendas`

**PENDING:**

| Migration | Owner | Needed for |
|---|---|---|
| `037_erp_stage_parity_and_canonical_phone.sql` | not this work | canonical-phone contract |
| `038_n8n_folders.sql` · `039_n8n_nav_route.sql` | not this work | n8n feature (shipped in code, no schema behind it) |
| **`041_leads_meta_lead_id.sql`** | **this work** | the unified leads base — without it, Meta→`leads` normalization has no idempotency key |
| **`044_meta_webhook_events.sql`** | **this work** | the webhook inbox — without it, the receiver cannot persist a delivery at all |

🔴 **Apply by `target=`, never a bare `confirm=true`** — that applies the ENTIRE pending backlog,
including three migrations belonging to other initiatives that nobody here has vetted:

```
noctus.dev.migrate_product(product="social-wiring", target="041_leads_meta_lead_id.sql",  confirm=true)
noctus.dev.migrate_product(product="social-wiring", target="044_meta_webhook_events.sql", confirm=true)
```

⚠️ `migrate_product` has **no `worktree_path`** — run it from the PRIMARY checkout or it resolves
the wrong tree. Both are additive (new table + nullable column + indexes), so order-independent.

> **The migration-number history, because it will look strange in `git log`:** 040 was claimed by
> two different files on two unpushed branches; then, mid-integration, the WhatsApp peer renumbered
> theirs to 042 — the number this work held. Resolution was by *precedence, not preference*: the
> number already on `origin/dev` wins, and whoever is not yet pushed moves. Meta's inbox therefore
> travelled 040 → 042 → **044**. `check_migration_number_collision` now gates this class.

---

## 3 · Remaining path to production

1. **Apply `041` + `044`** (§2) with operator consent.
2. **Set `META_WEBHOOK_VERIFY_TOKEN`** in the root `.env` or the Fernet vault — **before** deploy.
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`
3. **Promote + deploy** `social-wiring` (skill `noc-ship`). No new prod-exposure consent needed —
   the slug is already on all three gated surfaces.
4. 🔴 **ONLY THEN: operator configures the Meta App Dashboard.** Meta issues the verification GET
   **synchronously** and refuses to save the subscription if it fails, so the receiver must already
   be live. Runbook: `META-APP-VERIFICATION.md` §10.
   Callback URL: `https://social.noctusai.com/api/meta/leadgen/webhook`
5. **Subscribe the Pages** in-product: Meta → Anúncios → Leads → "Assinar páginas".
   ⚠️ App-level (dashboard, step 4) and Page-level (this) are **both** required — either alone
   delivers nothing, silently.
6. **Live-verify** via the Lead Ads Testing Tool → Create Lead. Within ~30s expect all three:
   an inbox row `status='processed'`; a `meta_ads_leads` row with **non-null** name/email/phone
   (null ⇒ the form-schema lookup failed); exactly **one** `negociacoes_venda` card. Then replay the
   same signed payload → `200 duplicate`, **no second card**.
7. **Run the backfill** for the 958 stored leads: `POST /api/leads/meta-ingest/backfill`.

---

## 4 · Deliberately unfinished — do not "complete" these by accident

| Item | Why |
|---|---|
| **Slice 5b — live push (no-refresh lead list)** | Suspended by operator decision. The WhatsApp work landed `noctusai_lib/realtime` (SSE + Redis). Build the Meta live session **on top of it**; do not add Supabase Realtime as a second primitive. Now unblocked — the transport exists and can be assessed. |
| **erp Graph-client consolidation** | Scoped down deliberately. erp is a testing ground still being refined and its Meta receiver is inert (0 config rows, 0 leads). **The canon is social-wiring's `leadgen_router.py`**; erp's remainder is drift against it. The *security* half was fixed. |
| **Slice 7 — CSV history import** | Conditional on the operator finding off-platform exports. Meta permanently deletes leads after 90 days; pre-2026-04-28 history is unrecoverable by any means. |

---

## 5 · Hard-won notes

- **Number-shaped test names rot.** `test_042_*` pinned to whatever "042" means this hour broke
  twice during integration. The migration belongs in the *fixture*, not the identifier — this
  work's tests are now `test_meta_webhook_*` / `sql_meta_webhook`.
- **Detecting a migration collision across unpushed branches** — `ls migrations/` and
  `git log origin/dev` both miss it. Now gated by `check_migration_number_collision`, but the
  manual form is `git diff --name-only origin/dev...<branch>` across *every local* branch.
- **`noctusai_lib` resolution in worktrees is already solved** by each product's `tests/conftest.py`.
  pytest runs need no `PYTHONPATH`; a bare `python -c` does *not* load conftest and reports the
  primary tree. A probe contradicting your worktree is the probe being wrong.
- **Prove a guard can fail before trusting it** — `methodology-execution-discipline.md` §4.
- **Grep for prior art before designing a mechanism** — same doc, §5.
- **Verify by exit code, never a piped `tail`.**
