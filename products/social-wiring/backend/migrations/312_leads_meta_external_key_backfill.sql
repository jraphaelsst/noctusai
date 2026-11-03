-- 312_leads_meta_external_key_backfill.sql — complete the generic (external_source, external_lead_id) key for
-- Meta Lead-Ads leads ingested live.
--
-- Migration 051 backfilled the Meta rows that existed then; every lead ingested live since wrote only
-- `meta_lead_id` + `origem_id` and left the generic pair NULL (now fixed in `map_meta_lead_to_lead_payload`).
-- A lookup keyed on the pair therefore missed them. Same shape as 051: only rows whose source IS meta-lead-ads,
-- only where the pair is still empty, and a row whose target key is already taken is skipped (the partial unique
-- index uq_sw_leads_org_external_lead must never be the reason this fails). Idempotent: re-running updates nothing.
SET search_path = social_wiring, public;

UPDATE social_wiring.leads l
   SET external_source  = 'meta-lead-ads',
       external_lead_id = l.meta_lead_id
  FROM social_wiring.lead_sources s
 WHERE s.id = l.origem_id
   AND s.org_id = l.org_id
   AND s.slug = 'meta-lead-ads'
   AND l.meta_lead_id IS NOT NULL
   AND l.external_source IS NULL
   AND l.external_lead_id IS NULL
   AND NOT EXISTS (
       SELECT 1 FROM social_wiring.leads o
        WHERE o.org_id = l.org_id
          AND o.external_source = 'meta-lead-ads'
          AND o.external_lead_id = l.meta_lead_id
   );
