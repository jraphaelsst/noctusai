# send-message-consolidation — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** §1 inlines the situation, §2 quotes the user, §5 names every call site with line numbers, §10 commands are copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** 🅿️ **PARKED** — gated on `whatsapp-seed-absorption` Phase 1 (canonical `noctusai_lib.integrations.whatsapp.send_text()` lib must exist before either call site can be refactored).
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `send-message-consolidation` — cross-product naming + transport collision; lives at `projects/<slug>/` per `KB § PATTERNS/project-execution.md §1`.
- **Related docs:**
  - `KB § PATTERNS/accept-with-rationale.md § "send_message exists in ERP and therapy with different transports (N=2)"` — origin entry; this project flips that catalog row from `accept-with-rationale` → `formalize` once Phase 1 ships.
  - `projects/whatsapp-seed-absorption/PROJECT.md` — predecessor; lands the canonical `noctusai_lib.integrations.whatsapp` namespace this project depends on.
  - `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule` — N=2 → triage; N=3 → MUST formalize. This project is the **N=2 pre-emptive trigger** to avoid an N=3 hasty choice.

---

## 1. Context & Purpose

`send_message` exists at three call sites with three different shapes — same name, different transports, different DB coupling:

| Site | File:line | Shape | Transport |
|---|---|---|---|
| ERP WhatsApp | `products/erp-imobiliario/backend/app/services/whatsapp_service.py:164` | `send_message(phone, message, config: WhatsAppConfig) -> Dict` | Real Meta WhatsApp Cloud API via `httpx.post(config.send_url, ...)` |
| Therapy WhatsApp (stub) | `products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:161` | `send_message(therapist_id, body, db) -> Dict` | DB log via `log_message(...)`; **does NOT actually call WhatsApp** — returns `{"status": "sent"}` after writing the row |
| Therapy in-app messaging | `products/therapy-platform/backend/app/services/messaging_service.py:179` | `send_message(conversation_id, sender_user_id, sender_type, content, message_type, sender_clinic_id, db) -> Dict` | In-app `messages` + `conversation_participants` tables; participant validation, block enforcement, auto-unarchive |

The catalog entry framing was "ERP + therapy WhatsApp with different transports — coincidental name collision, don't consolidate." That decision was correct *at the time of filing*: the therapy WhatsApp site is a stub, and the in-app messaging is genuinely a different concern.

**What changed:** `projects/whatsapp-seed-absorption/` will land `noctusai_lib.integrations.whatsapp.send_text()` — a real WhatsApp transport in seed-lib. Once that lib exists:

1. **ERP `whatsapp_service.send_message`** becomes a duplicate of the seed-lib `send_text` — same Meta Cloud API call shape, same dry-run fallback. The right shape is a 1-line wrapper (or direct call from the router).
2. **Therapy `whatsapp_therapy_service.send_message`** stops being a stub — the seed-lib `send_text` is its real implementation. The therapy function shrinks to: validate patient phone, call `send_text`, write the audit log row.
3. **Therapy `messaging_service.send_message`** stays put — it's genuinely in-app messaging and has no overlap with WhatsApp transport.

So the consolidation target is **two of the three sites** (the WhatsApp ones), not all three. The in-app messaging keeps its name and shape.

The reason this project exists NOW (filed at N=2 instead of waiting for N=3) is the recurrence rule's pre-emption clause: *"third product hitting it forces a hasty choice."* Filing now means when whatsapp-seed-absorption Phase 1 lands, the refactor steps are pre-documented and the catalog row flips cleanly.

---

## 2. Confirmed constraints

- **N=2 pre-emption (no third site yet)** — derived from `NEXT-STEPS.md § P2 deferrals to escalate § 1`: *"`send_message` collision at N=2 → file `send_message-consolidation` follow-up project NOW. Recurrence rule: third product hitting it forces a hasty choice."* Filing this project IS the N=2 triage outcome (formalize-deferred-to-Phase-1-of-predecessor).
- **No code changes in this project until predecessor ships** — `noctusai_lib.integrations.whatsapp.send_text()` does not exist yet (`whatsapp-seed-absorption` Phase 0 is not run). Phase 1 of THIS project is gated on the lib being importable.
- **In-app `messaging_service.send_message` is OUT OF SCOPE** — different concern; keeps its name and shape.

---

## 3. Design principles

1. **Refactor to the seed-lib seam, not to a shared product helper.** Both ERP and therapy WhatsApp paths import from `noctusai_lib.integrations.whatsapp` directly; no `app/services/whatsapp_helpers.py` shim that duplicates the seam.
2. **Preserve the validated shape of each consumer.** ERP's dry-run fallback + phone normalization stays in the lib (it's a transport concern). Therapy's audit-log + patient-phone validation stays in the therapy service (product concern). The seam is *just the send*.
3. **Catalog flip is mandatory at close.** The accept-with-rationale entry must move from `accept` → `formalize` with a concrete `Recorded by` reference to this project's close commit. *Why:* the catalog is the durable register that survives this folder's deletion.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** YES (for the WhatsApp send) — `send_text(phone, message, config) -> dict` is uniform; differences are at consumer wiring (audit logging, business validation).
2. **Is the data source product-specific?** NO at the transport layer — the WhatsApp endpoint + auth headers are the same shape. YES at the consumer layer (each product owns its own audit table + business validation).
3. **Is the placement product-specific?** NO — `noctusai_lib/integrations/whatsapp/` is the right home (predecessor project owns the placement decision).
4. **Is the visibility / permission rule the same?** YES — uniform at the transport layer. Per-product LGPD redaction + audit logging belongs at consumer wiring.
5. **Does the seam already exist in seed?** **NO** — `noctusai_lib.integrations.whatsapp` is new (lands via `whatsapp-seed-absorption` Phase 1). This is the entire reason for the gate.
6. **Default-on or opt-in?** OPT-IN — products that need WhatsApp `import` and `configure_whatsapp_module(...)`; others stay dormant.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — each product keeps its consumer wrapper (audit logging + business validation around the seed-lib send). Acceptable.

**Phase plan implications:** §6 Phase 1 works in the two product `app/services/` files only. **No phase walks through products as a primitive** — the per-product change is the *refactor target*, not the structural unit. Per-product code count after refactor: 1 thin wrapper per product, 0 transport-level duplication.

---

## 4. Scope

**In scope:**

- Refactor `products/erp-imobiliario/backend/app/services/whatsapp_service.send_message` to delegate to `noctusai_lib.integrations.whatsapp.send_text`. ERP keeps its `WhatsAppConfig` dataclass (config-shape concern) but drops the `httpx.post` body.
- Refactor `products/therapy-platform/backend/app/services/whatsapp_therapy_service.send_message` to call `noctusai_lib.integrations.whatsapp.send_text` for the actual transport. Therapy retains the patient-phone lookup + `log_message` audit row write.
- Update both products' tests to reflect the new import path; preserve test assertions on outbound shape.
- Catalog flip in `KB § PATTERNS/accept-with-rationale.md`: the N=2 entry moves from `accept` to `FORMALIZED 2026-MM-DD` with `Recorded by: send-message-consolidation Phase 1 (closed)`.

**Out of scope (for now — with reason):**

- `products/therapy-platform/backend/app/services/messaging_service.send_message` — genuinely different concern (in-app messaging table, conversation participants). Same name, no shared transport. Stays put.
- Adding new WhatsApp consumers to the seed-lib — that's the sibling `whatsapp-seed-absorption` Phase 0+1 work.
- Cross-product audit log consolidation — separate concern (`projects/llm-tool-call-audit/` shipped the seed-lib audit pattern; per-product audit tables remain product-bound).

---

## 5. Architecture / Data Model

**Before (today, N=2 with stub at therapy):**

```
products/erp-imobiliario/backend/app/services/whatsapp_service.py:164
  async def send_message(phone, message, config) -> Dict:
    # Real Meta Cloud API: httpx.post(config.send_url, ...)
    # Dry-run fallback when not configured.

products/therapy-platform/backend/app/services/whatsapp_therapy_service.py:161
  async def send_message(therapist_id, body, db) -> Dict:
    # STUB: looks up patient.phone, writes log_message row, returns {"status": "sent"}.
    # Does NOT actually call WhatsApp.

products/therapy-platform/backend/app/services/messaging_service.py:179
  async def send_message(conversation_id, sender_user_id, ...) -> Dict:
    # In-app messaging — OUT OF SCOPE (different concern).
```

**After (post-Phase 1, predecessor's lib in place):**

```
seed/backend/lib/noctusai_lib/integrations/whatsapp/__init__.py
  async def send_text(phone, message, config) -> Dict:
    # The single canonical Meta Cloud API send.
    # Owns: dry-run fallback, phone normalization, error envelope.

products/erp-imobiliario/backend/app/services/whatsapp_service.py
  from noctusai_lib.integrations.whatsapp import send_text
  # Service shell: WhatsAppConfig dataclass + thin wrapper.
  send_message = send_text  # or 1-line forward; routers import unchanged.

products/therapy-platform/backend/app/services/whatsapp_therapy_service.py
  from noctusai_lib.integrations.whatsapp import send_text
  async def send_message(therapist_id, body, db) -> Dict:
    # Lookup patient.phone (unchanged).
    result = await send_text(patient.phone, message_text, config)
    await log_message({...therapist_id, status: result["status"]...}, db)
    return result

products/therapy-platform/backend/app/services/messaging_service.py
  # UNCHANGED — in-app messaging stays put.
```

**Catalog state after close:**

```
KB § PATTERNS/accept-with-rationale.md
  ### `send_message` ... (N=2 accept-with-rationale)
  → DELETED, replaced with FORMALIZED entry pointing here.
```

---

## 6. Implementation phases

### Phase 0 — Predecessor verification 🅿️ PARKED
- [ ] Confirm `noctusai_lib.integrations.whatsapp.send_text` exists at expected path (gate: `whatsapp-seed-absorption` Phase 1 close commit).
- [ ] Confirm send_text signature matches both ERP and therapy callers' needs (phone, message, config).
- [ ] Confirm dry-run fallback semantics preserved (ERP currently checks `config.is_configured`; lib must own that branch).
- [ ] Re-grep `def send_message|async def send_message` to confirm site count is still N=2 for WhatsApp transport (not N=3+ — if N=3 happened during the wait, escalate scope before continuing).

### Phase 1 — ERP refactor
- [ ] Replace `whatsapp_service.send_message` body with delegation to `send_text`.
- [ ] Update `WhatsAppConfig` if seed-lib expects a different config shape (likely: lib accepts `WhatsAppConfig` directly OR a smaller `WhatsAppCredentials` dataclass).
- [ ] Run `pytest products/erp-imobiliario/backend/`. Update mocks that patch `whatsapp_service.send_message` directly to patch the seed-lib seam instead (per "no monkey-patching of our own code in tests" rule — use `MockRequestBuilder` patterns or DI).
- [ ] **Improvements:** capture during steps; synthesize at phase end.

### Phase 2 — Therapy refactor
- [ ] Replace stub body in `whatsapp_therapy_service.send_message` with real `send_text` call wrapped in the existing audit-log shell.
- [ ] Update test assertions: previously `{"status": "sent", "phone": ...}` was always returned even without an HTTP call; now the lib's response shape carries through. Update tests to match.
- [ ] Run `pytest products/therapy-platform/backend/`.
- [ ] Verify `messaging_service.send_message` is untouched (sanity grep).
- [ ] **Improvements:** capture during steps; synthesize at phase end.

### Phase 3 — Catalog flip + project close
- [ ] Replace the `accept-with-rationale.md § "send_message exists in ERP and therapy"` entry with a `FORMALIZED YYYY-MM-DD` entry; `Recorded by: send-message-consolidation Phase 3 (closed); commit <hash>`.
- [ ] Update `projects/README.md` — drop this project's row from active.
- [ ] Update `NEXT-STEPS.md` — strike `send_message` collision from P2 deferrals.
- [ ] File ONE bundled phase proposal via `noctusai_file_proposal(project="send-message-consolidation", ...)` if any improvements accumulated; otherwise apply-inline-then-skip.
- [ ] Flip phase headers to ✅; add §11 close entry; delete this folder; final commit + push (project-close gate).

---

## 7. Open questions

1. **Will `noctusai_lib.integrations.whatsapp.send_text` accept ERP's `WhatsAppConfig` dataclass as-is, or define its own config type?** — needs answer before Phase 1 / decided when `whatsapp-seed-absorption` Phase 1 lands. *Recommendation:* lib defines `WhatsAppCredentials` (api_key + phone_number_id + send_url builder); ERP's `WhatsAppConfig` either becomes an alias or holds a `WhatsAppCredentials` instance internally.
2. **Should ERP's dry-run fallback move to the lib, or stay at consumer level?** — needs answer before Phase 1. *Recommendation:* MOVE TO LIB. Dry-run is a transport concern (it short-circuits the `httpx.post`), not a consumer concern. Both ERP and therapy benefit from the same fallback.
3. **Are there any other in-flight projects authoring NEW `send_message` functions during the wait?** — re-check at Phase 0 gate. If yes, expand scope to include them; if a third real WhatsApp consumer lands, this project's `Status:` flips from PARKED to URGENT.

---

## 8. Dependencies & blockers

- **Hard blocker:** `projects/whatsapp-seed-absorption/` Phase 1 close (lib must exist). All Phase 1+ work here is gated.
- **Soft dependency:** `projects/imobi-scheduling-bot-creation/` — if this product lands first and uses WhatsApp transport, it should consume `noctusai_lib.integrations.whatsapp.send_text` directly (not duplicate). Coordinate at imobi project's Phase 0 — flag if it intends to author its own `send_message`.
- **No infrastructure dependency.** No DB migrations. No deploy gates.

---

## 9. Success criteria

- [ ] Both `whatsapp_service.send_message` (ERP) and `whatsapp_therapy_service.send_message` (therapy) delegate to `noctusai_lib.integrations.whatsapp.send_text`.
- [ ] Zero `httpx.post(.*whatsapp|.*meta\.com)` calls remain in `products/*/backend/app/services/`.
- [ ] `messaging_service.send_message` (therapy in-app) untouched.
- [ ] `accept-with-rationale.md` entry flipped to FORMALIZED; both products' test suites green.
- [ ] No regression in either product's WhatsApp tests.

---

## 10. How to use this plan

```bash
# Verify predecessor lib exists (Phase 0 gate)
ls seed/backend/lib/noctusai_lib/integrations/whatsapp/__init__.py
python -c "from noctusai_lib.integrations.whatsapp import send_text; print('ok')"

# Re-grep current site count (catch N=3 escalation)
rg -ln "def send_message|async def send_message" products/

# Run both product test suites
cd products/erp-imobiliario/backend && pytest tests/services/test_whatsapp_service.py
cd products/therapy-platform/backend && pytest tests/services/test_whatsapp_therapy_service.py

# Catalog flip verification
rg -A 5 "send_message.*N=2" KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md

# KB sync after catalog edit
bash scripts/verify-kb-sync.sh
```

- **Phase-by-phase by default.** Phase 0 is the gate check; do not skip.
- **Live-tick tasks as they complete.** §6 sub-tasks flip `[ ]` → `[x]` the moment they pass.
- **Catalog flip is the close-state audit trail.** Without the FORMALIZED entry, the project did not actually close.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project filed at N=2** per `NEXT-STEPS.md § P2 deferrals` directive *"file `send_message-consolidation` follow-up project NOW"* and the recurrence-rule pre-emption clause. §1-§10 populated; §6 phases drafted with predecessor gate on `whatsapp-seed-absorption` Phase 1. Status: 🅿️ PARKED. Used `send-message-consolidation` (dashes, platform-consistent) as slug rather than the `send_message-consolidation` form NEXT-STEPS.md used (hybrid underscore/dash) — slug normalized in the same commit. | Claude Opus 4.7 |
