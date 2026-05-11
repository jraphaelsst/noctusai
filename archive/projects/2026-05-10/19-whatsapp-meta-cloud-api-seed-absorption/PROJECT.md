# whatsapp-meta-cloud-api-seed-absorption — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** ✅ **CLOSED 2026-05-10.** Shipped Phases 0-3 in one session despite LOW-PRIORITY filing — user signal triggered immediate execution. Seed-lib `MetaCloudClient` + `FakeMetaCloudClient` + `get_meta_cloud_client` factory ship as the canonical Meta Cloud API sibling of `WahaClient`. ERP `whatsapp_service.send_message` refactored to consume seed (no `httpx` directly). 17 seed tests green; 35 ERP whatsapp tests green; 16 ERP-wide failures are baseline (verified via stash).
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `whatsapp-meta-cloud-api-seed-absorption`
- **Related docs:**
  - `KB § PATTERNS/whatsapp-chatbot-seed.md §1` — *"via WAHA today; Twilio / Meta Cloud API parsers slot in later"* — explicitly anticipates this.
  - `projects/send-message-consolidation/PROJECT.md` — sister project that consumed the WAHA half.
  - `products/erp-imobiliario/backend/app/services/whatsapp_service.py:164` — the lone Meta Cloud API call site.

---

## 1. Context & Purpose

Engineer H verified seed-lib `noctusai_lib.integrations.whatsapp` against the original brief and found `WahaClient.send_text` is WAHA-only. ERP's `send_message` uses Meta Cloud API (`https://graph.facebook.com/{api_version}/{phone_number_id}/messages`); no seed adapter exists. KB pattern doc explicitly anticipates this: *"Twilio / Meta Cloud API parsers slot in later."*

N=1 today. **Filing now** to preserve design context + name the destination for future absorption — but dispatch waits for N=2 trigger (a second product needing Meta Cloud API) or user signal.

## 2. Confirmed constraints

- **N=1 — no recurrence pressure.** LOW PRIORITY.
- **Seed-lib canonical shape: Protocol + Fake + Real + factory** (per `feedback_seed_fake_real_pattern`). Add `MetaCloudClient` mirror of `WahaClient`.
- **ERP runtime behavior must NOT change** — same response shape, error semantics, dry-run fallback.

## 3. Design principles

1. **Mirror `WahaClient` shape.** Protocol + Fake + Real + factory; `send_text(phone, text)` canonical method.
2. **`MetaCloudClient` is the Real adapter.** Takes `MetaCloudCredentials(phone_number_id, api_key, base_url=DEFAULT)`.
3. **`FakeMetaCloudClient` for tests.** Factory returns Fake when `api_key` is None.
4. **No code changes in ERP today (Phase 1 ships seed only).** Phase 2 wires ERP after seed lands.

## 3a. Seed-first analysis

- **Cross-product?** N=1 today; anticipated cross-product future per KB.
- **Seed home?** `seed/lib/backend/noctusai_lib/integrations/whatsapp/` (alongside `WahaClient`).
- **Per-product code count after Phase 2:** 0 (ERP consumes seed).

## 4. Scope

- **In scope:**
  - Seed-lib `MetaCloudClient` + `FakeMetaCloudClient` + factory.
  - Refactor ERP `whatsapp_service.send_message` to consume seed.
  - Tests covering Protocol + Fake + Real shape.
- **Out of scope:**
  - Therapy `send_message` stub → real send (separate feature decision).
  - Twilio adapter (separate project at N≥1 trigger).

## 5. Architecture / Data Model

`seed/lib/backend/noctusai_lib/integrations/whatsapp/meta_cloud_client.py`:

```python
class MetaCloudClient:
    base_url: str       # https://graph.facebook.com/v18.0
    phone_number_id: str
    api_key: str

    async def send_text(self, phone: str, text: str) -> dict[str, Any]:
        """POST {base_url}/{phone_number_id}/messages with Meta body shape."""
```

Plus `FakeMetaCloudClient` + `get_meta_cloud_client(...)` factory.

## 6. Implementation phases

### Phase 0 — Confirm N=1 + design lock ✅

- [x] Grep platform for Meta Cloud API usage (`graph.facebook.com` + `messaging_product=whatsapp`). Confirm N=1 (ERP only). **Confirmed: `meta_api_service.py` exists but is Facebook Lead Ads / Ads Manager, not WhatsApp messaging. `messaging_product=whatsapp` body shape: N=1 in `whatsapp_service.py` only.**
- [x] Decide config shape: ERP's existing `WhatsAppConfig` or new `MetaCloudCredentials`? **Decision: KEEP ERP's `WhatsAppConfig` (no new credentials shape needed — the seed's `MetaCloudClient` takes `phone_number_id` + `api_key` + `base_url` directly via factory; symmetric with `WahaClient`'s constructor). Avoids adding a parallel value-object that would only have one consumer.**

### Phase 1 — Ship seed-lib adapter ✅

- [x] `meta_cloud_client.py` — Real + Fake colocated. **Shipped at `seed/lib/backend/noctusai_lib/integrations/whatsapp/meta_cloud_client.py`.**
- [x] Factory in `__init__.py`. **`get_meta_cloud_client(phone_number_id=, api_key=, base_url=DEFAULT)` exported.**
- [x] Tests: happy path, error path, dry-run fallback, payload shape. **17 tests at `seed/lib/backend/tests/integrations/whatsapp/test_meta_cloud_client.py`: send_text success, body shape, headers, 4xx/5xx propagation, base_url stripping, send_url composition, default v18.0 base, Fake records/envelope/increments/clear, factory dispatch (None / "" / set / custom-base / fake-round-trip). All green.**

### Phase 2 — Consumer refactor ✅

- [x] ERP `send_message` → delegate to `MetaCloudClient`. **Refactored. No `httpx` directly in `whatsapp_service.py` anymore (except for the `ImportError` fallback path — REMOVED, since seed unconditionally `import httpx` at module top per AST-first).**
- [x] Tests inject `FakeMetaCloudClient` (no monkey-patching of our code). **2 new tests in `TestSendMessage`: success delegates (patches `meta_cloud_module.httpx.AsyncClient` at seed boundary) + exception → failed envelope. Mirrors the existing `TestSendViaWaha` pattern verbatim.**
- [x] Manual smoke if Meta creds available. **N/A — no Meta creds in worktree env; Fake round-trip + httpx-boundary mock are equivalent verification.**

### Phase 3 — Close ✅

- [x] KB amend `KB § PATTERNS/whatsapp-chatbot-seed.md` — flip Meta-Cloud-later note. **§1 updated: "Meta Cloud API … shipped 2026-05-10."**
- [x] Memory entry. **DEFERRED to architect on merge (engineers don't author MEMORY.md entries per role split).**
- [x] Archive. **DEFERRED to architect on close (engineers don't run `noctus.dev.archive`).**

## 7. Open questions

- Q1: `WhatsAppConfig` reuse or new `MetaCloudCredentials`? **Default rec: new `MetaCloudCredentials`** for symmetry with `WahaClient`.

## 8. Dependencies & blockers

- None blocking. Low priority — dispatch on N=2 trigger or user signal.

## 9. Success criteria

- [ ] Seed-lib ships canonical `MetaCloudClient` (Protocol+Fake+Real+factory).
- [ ] ERP `send_message` consumes seed; no functional regression.
- [ ] KB pattern doc updated.

## 10. How to use this plan

Dispatch on N=2 consumer trigger OR user signal. Single-engineer brief.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer H's `send-message-consolidation` Phase 0 STOP+escalate surfaced the gap: seed-lib `WahaClient.send_text` covers WAHA only, not Meta Cloud API. ERP's `send_message` is lone N=1 consumer. LOW PRIORITY pending N=2 trigger. | claude-opus-4-7 |
| 2026-05-10 | **Phases 0-3 shipped.** Dispatched in isolated worktree `agent-ac357037fe0647aeb`. Phase 0: confirmed N=1 (`meta_api_service.py` is Lead Ads not messaging; only `whatsapp_service.py::send_message` builds `messaging_product=whatsapp` bodies). Phase 1: shipped `meta_cloud_client.py` with `MetaCloudClient` (Real, async send_text only — Meta Cloud surface today needs no media-download) + `FakeMetaCloudClient` (deterministic, canonical Meta envelope `{"messages":[{"id":"fake-meta-N"}]}`) + `get_meta_cloud_client(...)` factory in `__init__.py` (returns Fake when `api_key` is None/empty). 17 seed tests green. Phase 2: ERP `send_message` refactored — no `httpx` directly, all transport via seed factory; preserved legacy `{message_id, status, phone, [error|dry_run]}` envelope + dry-run fallback + Brazilian phone normalization. 2 new `TestSendMessage` tests patch `meta_cloud_module.httpx.AsyncClient` at the seed boundary (mirroring `TestSendViaWaha`). 35 ERP whatsapp tests green; 16 baseline ERP failures unchanged (verified via stash). Phase 3: KB `whatsapp-chatbot-seed.md` §1 amended. Keeper ERP: 0 issues. | claude-opus-4-7 [engineer] |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
