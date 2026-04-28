# LGPD Concerns — Rolling Log

> **Auto-generated** by `noctusai_lgpd_flag` (see
> `mcp/noctusai/tools/lgpd.py`). Each item is an unresolved concern
> discovered during development. They are **not blockers** — the code
> ships and this file tracks what must be reviewed before the feature
> can be called done.
>
> Mark an item `- [x]` when the concern is resolved (code changed or
> dismissed with rationale). Do not delete items — strike through or
> move to an "Archive" section at the bottom.
>
> Philosophy + the five questions: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`.

- [ ] **Admin-only live Vista CRM showcase exposes personal data (lead/client names, contact details, possibly CPF/CNPJ, addresses) fetched live through ERP backend proxy routes; retention, access-log sink, and export policy are not yet locked.** at `products/erp-imobiliario/projects/vista-crm-wiring/` — Vista payloads contain personal data under LGPD. Phase 1 is read-only and admin-only, but the access-audit log location, the no-personal-cache contract, and the no-LLM-on-personal-fields rule are written into PROJECT.md §2/§3/§5 as commitments, not as shipped controls. This flag stands as the open item until (a) the backend proxy actually writes access-audit records, and (b) the retention contract (how long raw Vista responses may sit in memory/temp files) is documented in MASTER-PROMPT.md. Admin-only is the mitigation, not the exemption.
  - *Mitigation*: Admin-only route gating via existing ERP role system; frontend blind to the Vista API key; no DB cache or cross-schema copy in v1; no LLM summarization of personal fields in v1. Resolution gate: before Phase 3 flips to completed, both (a) access-audit sink must be shipped and tested, and (b) retention contract must be written into products/erp-imobiliario/MASTER-PROMPT.md.
  - *Flagged*: 2026-04-23
- [ ] **patient-attachment-to-llm** at `products/therapy-platform/backend/app/services/attachment_service.py:81` — Patient-uploaded files (images + audio) flow to OpenAI Vision + Whisper. Clinical documents, handwritten notes, voice recordings — all Art. 11 sensitive.
  - *Mitigation*: Prompt user for explicit consent at upload time. Offer 'no-AI' upload flow for sensitive attachments. Revisit Whisper self-hosting.
  - *Flagged*: 2026-04-19
- [ ] **patient-audio-to-whisper** at `products/therapy-platform/backend/app/services/transcription_service.py:45` — Raw patient audio segments are uploaded to OpenAI Whisper. Voice is Art. 5 biometric data. OpenAI retains audio per its API data policies. Unavoidable for transcription feature.
  - *Mitigation*: Evaluate a self-hosted Whisper deployment for clinical audio. Document upload + retention in user-facing privacy disclosure. Offer a consent toggle at recording time.
  - *Flagged*: 2026-04-19
- [ ] **longitudinal-clinical-aggregation** at `products/therapy-platform/backend/app/services/longitudinal_service.py:66` — Service aggregates multiple session summaries (6-month windows) into a single OpenAI prompt — higher re-identification risk than individual sessions because combined context reveals patterns unique to one patient (Art. 11 sensitive data, Art. 5 re-identification risk).
  - *Mitigation*: Consider summarizing per-session first and only passing compressed abstracts to the longitudinal pass. Or offer users a toggle to opt-out of longitudinal AI analysis entirely.
  - *Flagged*: 2026-04-19
- [ ] **patient-clinical-text-in-llm-prompt** at `products/therapy-platform/backend/app/services/summary_service.py:73` — Full session transcript + therapist observations (Art. 11 sensitive data) are embedded in every OpenAI chat prompt. Request bodies travel unencrypted to 3rd-party infra and are retained per OpenAI's data policies. We mitigate caching (cache=False), but the outbound request itself is unavoidable for the feature.
  - *Mitigation*: Longer-term: self-host a clinical-grade LLM, or pre-redact patient-identifiable tokens (names, phone, addresses) before the outbound call. Document the OpenAI data-retention contract in user-facing privacy policy (Art. 9 transparency duty).
  - *Flagged*: 2026-04-19
- [x] **llm-cache-key-cross-org-leak** at `seed/backend/lib/noctusai_lib/llm/cache.py::build_cache_key` — Cache key shape `llm:{product}:{provider}:{model}:{prompt_version}:{sha256(messages_json)}` did NOT include `org_id`. Two organizations with identical (product, provider, model, prompt_version, messages) would share a cache entry — cross-org PII bleed via cache hit. Low-probability collision but architecturally leaky. Surfaced by ai-expansion Tier 1.5 G5 audit 2026-04-24.
  - *Mitigation*: **RESOLVED 2026-04-24**. Added `org_id` parameter to `build_cache_key`; new key shape `llm:{product}:{provider}:{model}:{prompt_version}:org={org_id_or___platform__}:{sha256}`. `chat.py` passes `org_id=org_id` from the call site. Three regression tests in `mcp/noctusai/tests/test_llm_cache.py::TestKeyBuilder` (`test_org_id_isolates_cache_entries`, `test_org_id_none_uses_platform_segment`, `test_no_org_id_collides_with_platform_segment`). 14/14 cache tests green.
  - *Flagged*: 2026-04-24
  - *Resolved*: 2026-04-24
