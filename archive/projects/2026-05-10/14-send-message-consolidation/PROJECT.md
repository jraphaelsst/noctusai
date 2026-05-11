# send-message-consolidation — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** §1 inlines the situation, §2 quotes the user, §5 names every call site with line numbers, §10 commands are copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED (Path A — 2026-05-10).** Both `send_via_waha` callsites (ERP `whatsapp_service.py:319` + therapy `whatsapp_therapy_service.py:44`) now delegate to seed `noctusai_lib.integrations.whatsapp.WahaClient.send_text` via the `get_whatsapp_client(...)` factory. Each product retains a thin wrapper for product-specific concerns (ERP: BR phone normalization + DB config + legacy envelope; therapy: explicit-arg signature + ValueError contract). ERP 33/33 + therapy 10/10 WhatsApp service tests green; full suites land on the same baseline (ERP 1860 passed / 4 pre-existing date-arith failures; therapy 1218 passed / 4 pre-existing order-dependent failures). Catalog entry FORMALIZED 2026-05-10. Auth-header behavior change captured in findings.md (X-Api-Key replaces ERP's previous Authorization: Bearer — aligns with WAHA standard).
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
seed/lib/backend/noctusai_lib/integrations/whatsapp/__init__.py
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

### Phase 0 — Re-grep + seed gate verification ✅
- [x] Re-confirmed seed `noctusai_lib.integrations.whatsapp.WahaClient.send_text` + `get_whatsapp_client(...)` factory + `chat_id_for_phone(...)` helper exist (seed ships Protocol + Fake + Real + factory shape per `KB § PATTERNS/seed-fake-real-adapter.md`).
- [x] Read both `send_via_waha` call sites — confirmed N=2 byte-level recurrence at ERP `whatsapp_service.py:319` + therapy `whatsapp_therapy_service.py:44`.
- [x] Re-grep `def send_via_waha|async def send_via_waha` across all products — N=2 confirmed.
- [x] Mapped response-shape divergence (ERP envelope vs therapy raw + therapy `ValueError`-on-error contract) — preserved as product-specific concerns in thin wrappers.

### Phase 1 — ERP refactor ✅
- [x] Replaced `whatsapp_service.send_via_waha` body: drops `httpx.AsyncClient`/import + `Authorization: Bearer` header; delegates to seed `WahaClient.send_text` via `get_whatsapp_client(base_url=, api_key=, session=)`.
- [x] Preserved BR phone normalization (digits + "55" prepend) at ERP boundary — phone normalization is product-specific (CRM-imported phones lack country code), not transport-level.
- [x] Preserved legacy `{message_id, status, phone, [error|dry_run]}` envelope expected by `/whatsapp/send` router.
- [x] Added 4 new tests (`TestSendViaWaha`) patching `httpx.AsyncClient` at the seed-lib boundary (`waha_client_module.httpx`) — mirrors the seed's own client-test pattern; never patches the product service itself.
- [x] `pytest products/erp-imobiliario/backend/tests/services/test_whatsapp_service.py` → 33/33 passed (29 baseline + 4 new).
- [x] Full `pytest products/erp-imobiliario/backend/` → 1860 passed + 4 pre-existing date-arithmetic failures (`test_financeiro_service.py::TestMarkOverdue` + `test_recorrencia_service.py::TestVerificarInadimplencia`) unchanged from baseline; verified via stash+rerun.
- [x] Keeper `noctus.dev.review(product="erp-imobiliario")` → 0 issues.
- **Improvements:** captured 1 behavioral change (auth-header swap Bearer → X-Api-Key) — documented in findings.md §3 lessons; no proposal needed (intentional alignment with WAHA standard).

### Phase 2 — Therapy refactor ✅
- [x] Replaced `whatsapp_therapy_service.send_via_waha` body: drops top-level `import httpx` + `httpx.AsyncClient` block; delegates to seed `WahaClient.send_text` via `get_whatsapp_client(base_url=, api_key=None, session=)`.
- [x] Preserved explicit-arg signature `(waha_url, session_name, phone, message)` + raw-WAHA-response return + `ValueError`-on-error contract (wraps seed's `httpx.HTTPStatusError` in `ValueError` to keep `send_reminder` happy).
- [x] Updated `TestSendViaWaha` — patches `httpx.AsyncClient` at the seed-lib boundary (`waha_client_module.httpx`) instead of `app.services.whatsapp_therapy_service.httpx.AsyncClient` (which no longer exists post-refactor).
- [x] `pytest products/therapy-platform/backend/tests/services/test_whatsapp_therapy_service.py` → 10/10 passed.
- [x] Full `pytest products/therapy-platform/backend/` → 1218 passed + 4 pre-existing test-order-dependent failures (`test_crisis_router.py::test_review_alert_admin_allowed`, `test_refunds_router.py::test_deny_refund_with_reason`, `test_crisis_service.py::test_review_as_false_positive`, `test_homework_service.py::test_review_pending_homework_fails`) unchanged from baseline; verified via stash+rerun.
- [x] `messaging_service.send_message` untouched — verified via `git diff --stat`.
- [x] Keeper `noctus.dev.review(product="therapy-platform")` → 0 issues.
- **Improvements:** captured 1 behavioral subtlety (raw-vs-envelope response shape preserved per consumer; therapy keeps raw because `send_reminder` packs it into `waha_response`).

### Phase 3 — Catalog flip + project close ✅
- [x] Replaced the `accept-with-rationale.md § send_message-collision` entry with a FORMALIZED 2026-05-10 entry under the title `send_via_waha exists in ERP and therapy (N=2 → FORMALIZED 2026-05-10)`. Preserved the slip-pattern history (filed at N=2 on wrong premise — `send_message` vs the real `send_via_waha`) so future scans can find the trail.
- [x] No `projects/README.md` to update (no per-project registry exists at the path the original phase template referenced).
- [x] No `NEXT-STEPS.md` `send_message` entry to strike (the deferral was rescoped in commit `33dd4f7`).
- [x] Inline improvements applied (no separate proposal); see findings.md for capture.
- [x] All phase headers ticked ✅; §11 close entry added below.
- [ ] **Folder deletion deferred to orchestrator** per dispatch brief: "Do NOT delete the project folder — orchestrator handles archive after fresh-eyes merge."

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
ls seed/lib/backend/noctusai_lib/integrations/whatsapp/__init__.py
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
| 2026-05-10 | **Re-scoped (Path A) after Engineer H Phase 0 STOP+escalate.** Engineer H correctly halted at premise-invalidation per "verify the seed ships it" methodology: seed `noctusai_lib.integrations.whatsapp.WahaClient.send_text` covers WAHA transport only, NOT Meta Cloud API. The REAL N=2 recurrence is `send_via_waha` (60→37 LoC dup at ERP `whatsapp_service.send_via_waha:319` + therapy `whatsapp_therapy_service.send_via_waha:44`), not `send_message`. Path A re-scope: (1) ERP `send_via_waha` → consume seed `WahaClient`. (2) Therapy `send_via_waha` → consume seed `WahaClient`. (3) ERP `send_message` (Meta Cloud API, N=1) UNTOUCHED — separate follow-up `whatsapp-meta-cloud-api-seed-absorption` filed. (4) Therapy `send_message` stub UNTOUCHED — wiring it to real send is a feature change. Re-dispatched 2026-05-10 with corrected scope. Engineer H's findings preserved as 6th confirmation of §17.6.1 return-as-text protocol. | claude-opus-4-7 |
| 2026-05-10 | **Path A executed (closed).** Phase 0-3 complete. ERP `whatsapp_service.send_via_waha:319` + therapy `whatsapp_therapy_service.send_via_waha:44` both now delegate to seed `noctusai_lib.integrations.whatsapp.WahaClient.send_text` via the `get_whatsapp_client(...)` factory. ERP wrapper retains BR phone normalization + DB config lookup + legacy `{message_id,status,phone}` envelope; therapy wrapper retains explicit-arg signature + raw-response + `ValueError`-on-error contract (wraps seed's `HTTPStatusError` to keep `send_reminder` happy). Both products: 0 keeper issues, all WhatsApp service tests green (ERP 33/33, +4 new `TestSendViaWaha` patching `httpx.AsyncClient` at seed boundary; therapy 10/10), full suites match baseline (4 unrelated pre-existing failures in each, verified via stash+rerun). Catalog flipped: `send_via_waha exists in ERP and therapy (N=2 → FORMALIZED 2026-05-10)` — slip-pattern history preserved (filed at N=2 on wrong premise `send_message` vs real `send_via_waha`). Behavioral change: ERP auth header swap `Authorization: Bearer` → `X-Api-Key` (aligns with WAHA standard + seed default; documented in findings.md). findings.md emitted as engineer report text per §17.6.1. Folder deletion + final merge deferred to orchestrator. | claude-opus-4-7 |
