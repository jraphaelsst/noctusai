-- O80: public-capture leads were stored with stage_id NULL, so they never showed in the Funil.
-- Backfill every live lead without a stage to its org's first stage (lowest position — the same
-- ordering list_stages()/the "Novo lead" dialog use). Orgs with no stage are left untouched
-- (nothing to point at; the app logs a warning for them). Idempotent.

SET search_path = orbity, public;

UPDATE orbity.leads l
   SET stage_id = fs.id
  FROM (
    SELECT DISTINCT ON (org_id) org_id, id
      FROM orbity.lead_stages
     ORDER BY org_id, position ASC, created_at ASC
  ) fs
 WHERE l.stage_id IS NULL
   AND l.deleted_at IS NULL
   AND l.org_id = fs.org_id;
