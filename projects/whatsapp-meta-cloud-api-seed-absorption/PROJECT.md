# whatsapp-meta-cloud-api-seed-absorption — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 🟢 **LOW PRIORITY (N=1, no recurrence pressure).** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer H's `send-message-consolidation` Phase 0 STOP+escalate surfaced that ERP's `send_message` (Meta WhatsApp Cloud API) has NO seed counterpart today. Seed-lib `WahaClient.send_text` covers WAHA only. N=1 (ERP-only) so no recurrence-rule pressure.
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

### Phase 0 — Confirm N=1 + design lock

- [ ] Grep platform for Meta Cloud API usage (`graph.facebook.com` + `messaging_product=whatsapp`). Confirm N=1 (ERP only).
- [ ] Decide config shape: ERP's existing `WhatsAppConfig` or new `MetaCloudCredentials`? Default rec: new `MetaCloudCredentials` for symmetry with `WahaClient`.

### Phase 1 — Ship seed-lib adapter

- [ ] `meta_cloud_client.py` — Real + Fake colocated.
- [ ] Factory in `__init__.py`.
- [ ] Tests: happy path, error path, dry-run fallback, payload shape.

### Phase 2 — Consumer refactor

- [ ] ERP `send_message` → delegate to `MetaCloudClient`.
- [ ] Tests inject `FakeMetaCloudClient` (no monkey-patching of our code).
- [ ] Manual smoke if Meta creds available.

### Phase 3 — Close

- [ ] KB amend `KB § PATTERNS/whatsapp-chatbot-seed.md` — flip Meta-Cloud-later note.
- [ ] Memory entry.
- [ ] Archive.

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

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
