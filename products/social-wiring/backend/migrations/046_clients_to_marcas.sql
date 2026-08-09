-- 046_clients_to_marcas.sql — `clients` is not a client; it is a MARCA.
--
-- WHY THIS EXISTS
-- ────────────────
-- Roadmap `project-history/roadmaps/lead-card-hub-2026-08.md`, **Phase 0**
-- (decision D14). Phase 1 introduces `social_wiring.clientes` — the PERSON
-- entity, the lead/cliente a Funil card is about. `social_wiring.clients`
-- already existed and meant something completely different: the brand /
-- profile owner an integration account belongs to. Live contents at authoring
-- time, two rows:
--
--     One Consultoria   kind='empresa'
--     João Raphael      kind='pessoa_fisica'
--
-- Those are the profiles whose Instagram / Facebook / WhatsApp / YouTube
-- accounts are connected. They are MARCAS.
--
-- Shipping `clients` and `clientes` side by side would leave two tables one
-- letter apart meaning two unrelated things — a permanent reading hazard for
-- every human and every agent that opens this schema. Postgres would allow it;
-- that is exactly why the guard has to be a decision rather than a constraint.
--
-- ⚠️ `colaboradores` was the user's first choice for this rename and was
-- WITHDRAWN. Phase 3 of the same roadmap invites 28 corretores + admins as
-- real noc users — THOSE are the colaboradores. The name would have collided
-- one phase later. `marcas` describes what the rows actually are.
--
-- ── WHAT MOVES ────────────────────────────────────────────────────────
--   social_wiring.clients                   → social_wiring.marcas
--   <6 tables>.client_id                    → marca_id
--   FK constraints + indexes                → renamed to match
--   status_pagina 'clientes'                → 'marcas'   (frees /clientes)
--
-- ── WHAT DELIBERATELY DOES NOT MOVE ───────────────────────────────────
-- 🔴 OAuth `client_id` is a DIFFERENT THING and is NOT touched anywhere:
--        settings.google_oauth_client_id
--        settings.youtube_client_id
--        the `client_id`/`client_secret` pairs handed to Google/YouTube
-- A blanket `client_id` → `marca_id` pass across this product would break
-- Google and YouTube auth. The application-side rename that accompanies this
-- migration is scoped to an explicit file allowlist for exactly that reason;
-- `app/services/account_credentials.py` carries BOTH meanings in one file and
-- was edited line-by-line, never in bulk.
--
-- ── RLS ────────────────────────────────────────────────────────────────
-- No policy anywhere in this schema references `client_id` (verified against
-- the live catalog via pg_policies before authoring). Nothing to re-grant.
-- Policies, indexes, FKs and the `mc_brand_owners` view all track the table by
-- OID, so they follow the rename automatically — only their NAMES are stale,
-- and those are corrected below for readability.
--
-- 🔴 BREAKING WITH OLD CODE — NOT BACKWARD COMPATIBLE, BY DECISION.
-- No compat view is created. The user chose the full rename (table + columns +
-- API + frontend) over the table-only variant, so old code cannot read the new
-- shape and there is nothing to be gained by pretending otherwise. **This
-- migration and its application code must ship together.** Verified before
-- authoring that the frontend never queries this table directly (all access is
-- through the backend API), so there is exactly one code path to land with it.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
--
-- APPLY CONTRACT: run inside an explicit transaction. Every statement is
-- guarded so a partial run is repaired by re-running this file unchanged.

SET search_path = social_wiring, public;

-- ─────────────────────────────────────────────────────────────────────
-- 1. The table
-- ─────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'social_wiring' AND table_name = 'clients')
     AND NOT EXISTS (SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'social_wiring' AND table_name = 'marcas')
  THEN
    ALTER TABLE social_wiring.clients RENAME TO marcas;
  END IF;
END
$$;

COMMENT ON TABLE social_wiring.marcas IS
  'A brand / profile whose social accounts are connected (One Consultoria, '
  'João Raphael). Renamed from `clients` by migration 046 so that `clientes` '
  'could mean the PERSON entity (leads/clientes) introduced in Phase 1 of '
  'project-history/roadmaps/lead-card-hub-2026-08.md. NOT to be confused with '
  'OAuth client_id, which is unrelated and untouched.';

-- ─────────────────────────────────────────────────────────────────────
-- 2. The 6 FK columns: client_id → marca_id
-- ─────────────────────────────────────────────────────────────────────
-- Enumerated explicitly rather than discovered by a catalog loop: these six
-- are the FKs to this table, verified against pg_constraint before authoring.
-- A loop over "every column named client_id" would be the same blanket rename
-- the header warns about, one layer down.
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'integration_accounts',
    'mailchimp_connections',
    'mc_brand_kits',
    'meta_ads_lead_forms',
    'notification_recipients',
    'whatsapp_connections'
  ]
  LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'social_wiring'
                  AND table_name = t AND column_name = 'client_id')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'social_wiring'
                  AND table_name = t AND column_name = 'marca_id')
    THEN
      EXECUTE format('ALTER TABLE social_wiring.%I RENAME COLUMN client_id TO marca_id', t);
    END IF;
  END LOOP;
END
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 3. Constraint names (cosmetic, but a stale name is a lie in a psql \d)
-- ─────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT c.conname, c.conrelid::regclass::text AS tbl
      FROM pg_constraint c
      JOIN pg_class rel ON rel.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = rel.relnamespace
     WHERE n.nspname = 'social_wiring'
       AND c.contype = 'f'
       AND c.confrelid = 'social_wiring.marcas'::regclass
       AND c.conname LIKE '%client_id%'
  LOOP
    EXECUTE format('ALTER TABLE %s RENAME CONSTRAINT %I TO %I',
                   r.tbl, r.conname, replace(r.conname, 'client_id', 'marca_id'));
  END LOOP;
END
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 4. Index names (definitions already track the renamed column by OID)
-- ─────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT i.indexrelid::regclass::text AS idx,
           c.relname                    AS idx_name
      FROM pg_index i
      JOIN pg_class c ON c.oid = i.indexrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'social_wiring'
       AND c.relname ~ '_client$|_client_'
       AND pg_get_indexdef(i.indexrelid) ILIKE '%marca_id%'
  LOOP
    EXECUTE format('ALTER INDEX social_wiring.%I RENAME TO %I',
                   r.idx_name,
                   regexp_replace(r.idx_name, '_client($|_)', '_marca\1'));
  END LOOP;
END
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 4b. Policy names on the renamed table
-- ─────────────────────────────────────────────────────────────────────
-- The policies themselves are untouched — they track the table by OID and
-- none of them references a renamed column (verified via pg_policies before
-- authoring). Only their NAMES still say `clients_*`, which would read as a
-- policy belonging to some other table.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT policyname FROM pg_policies
     WHERE schemaname = 'social_wiring'
       AND tablename = 'marcas'
       AND policyname LIKE 'clients\_%'
  LOOP
    EXECUTE format('ALTER POLICY %I ON social_wiring.marcas RENAME TO %I',
                   r.policyname,
                   'marcas_' || substring(r.policyname from length('clients_') + 1));
  END LOOP;
END
$$;

-- ─────────────────────────────────────────────────────────────────────
-- 5. Nav — free the `/clientes` route for Phase 1's PERSON page
-- ─────────────────────────────────────────────────────────────────────
-- An unlisted route is HIDDEN (see migration 036 + the status_pagina role
-- parity rule), so this row is what makes the page appear at all. Renaming it
-- moves the brand page to /marcas AND releases `clientes` — which Phase 1
-- registers for the new people page. Leaving both would put two entries in the
-- sidebar one letter apart.
UPDATE social_wiring.status_pagina
   SET nome_pagina = 'marcas',
       descricao   = 'Marcas — perfis cujas contas sociais estão conectadas'
 WHERE nome_pagina = 'clientes'
   AND NOT EXISTS (SELECT 1 FROM social_wiring.status_pagina WHERE nome_pagina = 'marcas');

-- PostgREST must re-read the schema to see the renamed table + columns.
NOTIFY pgrst, 'reload schema';
