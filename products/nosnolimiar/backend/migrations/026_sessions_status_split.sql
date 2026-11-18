-- 026 -- session statuses of the weekly care (2026-11-17)
-- The single `cancelada` session status becomes `cancelada_paciente` | `cancelada_terapeuta` | `remarcada`
-- (`app/crm.py` SESSION_STATUSES). `status` is plain TEXT validated by the service, so the schema does not change; this
-- only carries the rows already cancelled onto the closest new status. Neither is billable, exactly like `cancelada`
-- was, so no receivable and no balance moves. Who cancelled is not recorded on the old rows: they land on
-- `cancelada_paciente` (the common case) and Mônica can change one in the session detail.
-- IDEMPOTENT: once converged no `cancelada` row is left, so a re-run updates nothing.
SET search_path = nosnolimiar, public;

UPDATE nosnolimiar.client_sessions
   SET status = 'cancelada_paciente', updated_at = now()
 WHERE status = 'cancelada';
