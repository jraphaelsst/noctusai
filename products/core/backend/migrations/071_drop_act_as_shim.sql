-- 071 — contract step: drop the prod-only act_as_sessions shim (2026-10-09)
--
-- 067 dropped public.act_as_sessions; on 2026-10-07 an EMPTY copy (065 DDL) was
-- re-created by hand in prod because the then-running image (720fdcf4e) still
-- read it on every superadmin request (feedback: expand → deploy → contract).
-- The org picker (core 070, prod 4a5aff5ed+) replaced it with
-- public.platform_org_selections and no running image reads act_as_sessions
-- (verified: 0 rows, no function/view references, only its own CHECK depends on
-- it; inactive containers run 2b1ffcd1, which predates act-as).
-- No-op on a fresh chain (067 already dropped it). audit_logs.acting_org_id /
-- act_as_session_id stay — the org picker writes them.

DROP TABLE IF EXISTS public.act_as_sessions;
