-- ROLLBACK of product migration 024 (idx_nosnolimiar_* -> idx_monica_*). Run it BEFORE rollback-023.sql (the
-- indexes must be back under their old names while the schema is still `nosnolimiar`), then delete 024's ledger row
-- so a forward retry re-applies it. Not a migration: never place it under backend/migrations/.
DO $mig$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.relname
      FROM pg_class c
     WHERE c.relnamespace = to_regnamespace('nosnolimiar')
       AND c.relkind = 'i'
       AND c.relname IN ('idx_nosnolimiar_examples_ativo', 'idx_nosnolimiar_examples_org',
                         'idx_nosnolimiar_invitations_org', 'idx_nosnolimiar_invitations_token',
                         'idx_nosnolimiar_whatsapp_chats_list', 'idx_nosnolimiar_whatsapp_connections_org',
                         'idx_nosnolimiar_whatsapp_connections_webhook_token', 'idx_nosnolimiar_whatsapp_messages_thread')
  LOOP
    EXECUTE format('ALTER INDEX nosnolimiar.%I RENAME TO %I',
                   r.relname, 'idx_monica_' || substr(r.relname, length('idx_nosnolimiar_') + 1));
  END LOOP;
  IF to_regclass('nosnolimiar.schema_migrations') IS NOT NULL THEN
    DELETE FROM nosnolimiar.schema_migrations WHERE filename = '024_rename_monica_indexes.sql';
  END IF;
END
$mig$;
