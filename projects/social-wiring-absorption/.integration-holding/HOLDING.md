# Wave-2 held shared-file deltas (architect splices after W2.2+W2.3+W2.5b FF)

Engineers built NEW subtrees only + returned shared-file deltas as text (held-deltas pattern; prevents 3-way contention on `main.py`/`001`/`lifespan`/`requirements`). Integrate ALL TOGETHER in one coherent pass.

## ModuleRegistration lifespan-seam gap (N≥2 — formalize at integration)
W2.2 (and W2.3 likely) need module startup/shutdown wiring; `ModuleRegistration(routers, standard_routers)` has NO lifespan seam. **Architect action at integration:** extend `ModuleRegistration` with optional `on_startup`/`on_shutdown` callables + compose them in `main.py`'s assembly loop (fix-at-root + DRY N≥2), so modules return lifecycle via the seam instead of ad-hoc `lifespan.py` splices. Then email_marketing returns its `scheduler.start_scheduler/stop_scheduler` via the seam. → also a W5 codification candidate (seam completeness).

## W2.2 email_marketing — held deltas
- **main.py MODULES:** `from app.modules.email_marketing import register as _register_email_marketing` → append `_register_email_marketing` to `MODULES`.
- **Lifespan:** `scheduler.start_scheduler()` on_startup / `stop_scheduler()` on_shutdown (idempotent; via the seam above).
- **requirements.txt:** `resend>=2.0.0`, `APScheduler>=3.10.0` (confirm transitive via `noctusai_lib.api.scheduler`), `sqlalchemy>=2.0.0`.
- **config (SocialWiringSettings) — recommended (module degrades best-effort via getattr without):** `resend_api_key`, `resend_webhook_secret`, `default_from_email`, `default_from_name`, `max_batch_size`, `send_loop_seconds`, `scheduled_campaign_check_seconds`, `automation_check_minutes`, `postgres_url`.
- **001 migration SQL block:** see `email_marketing.sql` in this dir — splice verbatim under the `-- ─── W2.2 email_marketing tables — ADD BELOW` marker.
- Accept-with-rationale: consent feature keys kept `mailing.*` (stable identifiers; rename = coordinated data+code migration, later project). automation step-execution is a parity no-op (mailing carried same TODO) → future automation-engine project.

## W2.3 scheduling — held deltas
- **main.py MODULES:** `from app.modules.scheduling import register as _scheduling` → append `_scheduling` to `MODULES`.
- **Lifespan:** NONE (engine is request-driven; no background worker) → lifespan-seam gap is **N=1** (only W2.2). Decision: splice W2.2's scheduler start/stop directly into `lifespan.py`; do NOT formalize a ModuleRegistration lifespan seam (N=1 = gold-plating). Update the gap note above accordingly.
- **requirements.txt:** NONE (all consumed from existing noctusai_lib/seed; zoneinfo stdlib).
- **001 migration SQL block:** see `scheduling.sql` in this dir — splice verbatim under the `-- ─── W2.3 scheduling tables — ADD BELOW` marker.
- **Deferred (named destination):** router-level TestClient tests need the `sched_*` tables in `001` (MockSupabaseClient validate_schema) → architect/integration adds them AFTER the 001 splice (W2.3 unit tests cover engine/tool/LID/support with validate_schema=False).
- **N=2 seed-lift candidates surfaced** (route to W5 codification triage): `retry_call` sync wrapper, `sanitize_tool_result`/`wrap_handler` PII redactor, `RedisConversationRateLimiter`, `ToolDispatchAnomalyDetector`, `make_supabase_audit_writer` — fire the recurrence rule IF W2.2/therapy/mailing independently need the same shape (some now N=2 with email_marketing's audit). → W5.7-style triage, NOT this wave.
- `WAHA_RESPONSE_FORMATS.md` carry-forward is W2.1/W2.5-scope (already in product per W2.1), not W2.3 — no action here.

## W2.5b bridges — held deltas
(pending W2.5b return)
