-- ============================================================================
-- Migration 321 -- whatsapp_connections: one WAHA session = one line; the browser never reads the secrets (Julia go-live hardening)
-- ============================================================================
-- WHY (1/2): every org's line points at the shared WAHA server on the `default` session. Nothing stopped a second org from creating a
-- line on a session another org already owns -- it then reads that org's chats and sends as its number. The create route now refuses
-- (409 `sessao_ja_vinculada`); this index is the race-proof backstop. Scoped to the WAHA transport: a `cloud` line has no WAHA
-- session (its base_url/session_name are placeholders), so it must not collide.
-- WHY (2/2): the 004/086/211 policies let any AUTHENTICATED org member SELECT whole rows of this table -- `webhook_token` (the opaque
-- path secret of the inbound webhook: with it anyone can post forged messages to the line) and `encrypted_api_key` included. A secret
-- must not be reachable from the browser (same rule as migration 319 for `credentials`). The backend reads through service_role.
--
-- WHAT: (1) a UNIQUE partial index on (base_url, session_name) WHERE transporte = 'waha'; a pre-flight aborts LOUDLY, naming the
-- count, when two WAHA lines already share a session (resolve those rows by hand first -- nothing is merged or deleted silently).
-- (2) authenticated / anon lose the table-wide SELECT; authenticated gets a column-level SELECT on the non-secret columns (the RLS
-- own-org policy still scopes the rows); `webhook_token` and `encrypted_api_key` are service_role only. Idempotent.

DO $$
DECLARE
  _dup integer;
BEGIN
  SELECT count(*) INTO _dup FROM (
    SELECT 1 FROM social_wiring.whatsapp_connections
    WHERE transporte = 'waha'
    GROUP BY base_url, session_name HAVING count(*) > 1
  ) d;
  IF _dup > 0 THEN
    RAISE EXCEPTION 'migration 321: % WAHA session(s) are bound to more than one line -- resolve social_wiring.whatsapp_connections duplicates on (base_url, session_name) first', _dup;
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_whatsapp_connections_waha_session
  ON social_wiring.whatsapp_connections (base_url, session_name)
  WHERE transporte = 'waha';

REVOKE ALL ON TABLE social_wiring.whatsapp_connections FROM PUBLIC, anon;
REVOKE ALL ON TABLE social_wiring.whatsapp_connections FROM authenticated;
-- The column list is DERIVED (every column except the two secrets), so a column added by an earlier migration is not lost here and a
-- future secret column is hidden by default (it needs an explicit GRANT).
DO $$
DECLARE
  _cols text;
BEGIN
  SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) INTO _cols
  FROM information_schema.columns
  WHERE table_schema = 'social_wiring' AND table_name = 'whatsapp_connections'
    AND column_name NOT IN ('webhook_token', 'encrypted_api_key');
  EXECUTE format('GRANT SELECT (%s) ON TABLE social_wiring.whatsapp_connections TO authenticated', _cols);
END
$$;
GRANT ALL ON TABLE social_wiring.whatsapp_connections TO service_role;
