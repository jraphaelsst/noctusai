-- org-per-brand restructure — ONE-OFF prod data move (owner-approved 2026-10-07)
--
-- Owner decisions (2026-10-07): every brand is its own org, one org per user,
-- NoctusAI keeps every license (core 068), act-as removed (core 067), Marina is
-- One's jurídico and a normal noc user (loses platform superadmin).
--
--   NoctusAI        6dd73140…  Noctus staff · brands noctusai + joao-raphael (personal)
--   One Consultoria fd169d29…  the real-estate CRM + team (Gilson admin, Marina juridico)
--   Gilson          0ca4abef…  NEW · brand gilson-tangerino (Store's identity) · product Store
--   Mônica          fa80a1e0…  NEW · brands monica-tangerino (primary, carries the
--                              Nós no Limiar kit) + nos-no-limiar · agent nos-no-limiar
--
-- Preconditions (runbook.md): core 066-068 + social-wiring 210 applied; the One
-- owner account exists (its uuid replaces :one_owner); branding storage objects
-- already COPIED to the new org prefixes.
--
-- social_wiring's composite (org_id, id) FKs are NOT deferrable and have no
-- ON UPDATE CASCADE, so the row moves run under session_replication_role =
-- replica; integrity is re-verified by runbook.md's post-checks. Org creation
-- and the noctus_users updates run with triggers ON (erp agency profile +
-- auth metadata sync must fire).

BEGIN;

-- ── 0 · guards ──────────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = '6dd73140-74a4-41c6-aeff-bc94b5312b53')
     OR NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d') THEN
    RAISE EXCEPTION 'org-per-brand: NoctusAI / One Consultoria org missing — wrong database';
  END IF;
  IF EXISTS (SELECT 1 FROM public.organizations WHERE id IN
             ('0ca4abef-c84f-410a-b878-4b22f4ea5ed9', 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688')) THEN
    RAISE EXCEPTION 'org-per-brand: already applied (Gilson/Mônica org exists)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users WHERE id = ':one_owner') THEN
    RAISE EXCEPTION 'org-per-brand: One Consultoria owner account has no noctus_users row';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'social_wiring'
                  AND table_name = 'marcas' AND column_name = 'is_primary') THEN
    RAISE EXCEPTION 'org-per-brand: social-wiring migration 210 not applied';
  END IF;
END $$;

-- ── 1 · new orgs (triggers ON: erp agency profile + default stages) ────────
INSERT INTO public.organizations (id, nome, slug, plano, owner_id, category, org_type,
                                  onboarding_completed, is_personal, number_of_users)
VALUES
  ('0ca4abef-c84f-410a-b878-4b22f4ea5ed9', 'Gilson Tangerino', 'gilson-tangerino', 'free',
   '801d1f15-2c78-44c5-9c5e-2bf2274e0c66', 'normal', 'individual', true, false, 1),
  ('fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'Mônica Tangerino', 'monica-tangerino', 'free',
   '5beb7a7b-eb79-4fca-b449-ded0c74142a3', 'normal', 'individual', true, false, 1);

UPDATE public.organizations
   SET owner_id = ':one_owner', onboarding_completed = true, updated_at = now()
 WHERE id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d';

-- ── 2 · row moves (replica: no FK / trigger firing) ────────────────────────
SET LOCAL session_replication_role = replica;

DO $$
DECLARE
  noc CONSTANT uuid := '6dd73140-74a4-41c6-aeff-bc94b5312b53';
  one CONSTANT uuid := 'fd169d29-4d0a-4b04-9a5e-25e69407614d';
  gil CONSTANT uuid := '0ca4abef-c84f-410a-b878-4b22f4ea5ed9';
  mon CONSTANT uuid := 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688';
  m_joao CONSTANT uuid := '9d4c1b63-9899-48c0-8b93-8fabb545817c';
  m_noc  CONSTANT uuid := 'd0ca17e7-f6ee-400b-a316-24b0f1cdcc0d';
  m_one  CONSTANT uuid := 'c2b77620-c550-48e1-b789-b680c7e6bb0d';
  m_gil  CONSTANT uuid := 'd9b83e82-4b0f-45c9-be6c-11c91e3d6e4c';
  m_nnl  CONSTANT uuid := '06c35543-1a90-44eb-ab6f-e111e879e3f4';
  m_mon  CONSTANT uuid := '07798cf9-01aa-465e-aa11-49f3a0a18386';
  k_noc   CONSTANT uuid := '378e56fb-fefb-4167-8093-0ae7471636c4';
  k_one   CONSTANT uuid := 'ddfd4c20-fdab-4466-94a0-21f411f55adc';
  k_store CONSTANT uuid := '8345f7ec-acb4-4bfe-ba83-98f3575a7718';
  k_nnl   CONSTANT uuid := 'a9db50cd-3996-480e-9d7e-3b6989e1a510';
  a_nnl CONSTANT uuid := '214e523d-82f5-4e6d-8071-c8dfb2eb9549';
  -- tables moved by explicit rules below (the generic loop skips them)
  special CONSTANT text[] := ARRAY['marcas', 'integration_accounts', 'mc_brand_kits',
    'mc_brand_components', 'mc_brand_references', 'api_tokens', 'api_token_audit',
    'youtube_videos', 'youtube_shorts', 'youtube_channel_snapshots', 'youtube_video_snapshots',
    'ig_media', 'ig_media_snapshots', 'ig_profile_snapshots'];
  rel text;
  n bigint;
BEGIN
  -- social_wiring · brands (joao-raphael + noctusai stay in NoctusAI) -----
  UPDATE social_wiring.marcas SET org_id = one WHERE id = m_one;
  UPDATE social_wiring.marcas SET org_id = gil WHERE id = m_gil;
  UPDATE social_wiring.marcas SET org_id = mon WHERE id IN (m_mon, m_nnl);

  -- Mônica's identity IS the Nós no Limiar kit: it moves to her personal
  -- marca; nos-no-limiar (her product) inherits it via the org's primary.
  UPDATE social_wiring.mc_brand_kits SET org_id = one WHERE id = k_one;
  UPDATE social_wiring.mc_brand_kits SET org_id = gil WHERE id = k_store;
  UPDATE social_wiring.mc_brand_kits SET org_id = mon, marca_id = m_mon WHERE id = k_nnl;
  UPDATE social_wiring.mc_brand_components SET org_id = one WHERE brand_kit_id = k_one;
  UPDATE social_wiring.mc_brand_components SET org_id = gil WHERE brand_kit_id = k_store;
  UPDATE social_wiring.mc_brand_components SET org_id = mon WHERE brand_kit_id = k_nnl;
  UPDATE social_wiring.mc_brand_references SET org_id = one WHERE brand_kit_id = k_one;
  UPDATE social_wiring.mc_brand_references
     SET org_id = gil, storage_path = replace(storage_path, noc::text || '/', gil::text || '/')
   WHERE brand_kit_id = k_store;
  UPDATE social_wiring.mc_brand_references
     SET org_id = mon, storage_path = replace(storage_path, noc::text || '/', mon::text || '/')
   WHERE brand_kit_id = k_nnl;

  -- primary brand per org + primary kit per marca (migration 210)
  UPDATE social_wiring.marcas SET is_primary = true WHERE id IN (m_noc, m_one, m_gil, m_mon);
  UPDATE social_wiring.mc_brand_kits SET is_primary = true WHERE id IN (k_noc, k_one, k_store, k_nnl);

  -- social_wiring · connected accounts follow their marca ----------------
  UPDATE social_wiring.integration_accounts SET org_id = one
   WHERE org_id = noc AND marca_id IS DISTINCT FROM m_joao;
  UPDATE social_wiring.integration_accounts SET is_default = true
   WHERE org_id = one AND provider = 'youtube';
  FOREACH rel IN ARRAY ARRAY['youtube_videos', 'youtube_shorts', 'youtube_channel_snapshots',
      'youtube_video_snapshots', 'ig_media', 'ig_media_snapshots', 'ig_profile_snapshots'] LOOP
    EXECUTE format(
      'UPDATE social_wiring.%I d SET org_id = a.org_id FROM social_wiring.integration_accounts a
        WHERE d.account_id = a.id AND d.org_id = %L AND a.org_id <> d.org_id', rel, noc);
  END LOOP;
  -- api_tokens / api_token_audit stay (NoctusAI live-test token + the One Chat
  -- bridge, whose inactive agent stays in NoctusAI).

  -- social_wiring · everything else is One Consultoria's CRM -------------
  FOR rel IN
    SELECT c.table_name
      FROM information_schema.columns c
      JOIN information_schema.tables tb USING (table_schema, table_name)
     WHERE c.table_schema = 'social_wiring' AND c.column_name = 'org_id'
       AND tb.table_type = 'BASE TABLE' AND c.table_name NOT LIKE '\_%'
       AND c.table_name <> ALL (special)
  LOOP
    EXECUTE format('UPDATE social_wiring.%I SET org_id = %L WHERE org_id = %L', rel, one, noc);
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n > 0 THEN RAISE NOTICE 'social_wiring.% → One: %', rel, n; END IF;
  END LOOP;

  -- erp · the CRM's certidão / matrícula rows ----------------------------
  UPDATE erp.certidao_consultas  SET org_id = one WHERE org_id = noc;
  UPDATE erp.certidao_resultados SET org_id = one WHERE org_id = noc;
  UPDATE erp.matricula_extracoes SET org_id = one WHERE org_id = noc;

  -- agents · the Nós no Limiar guardian → Mônica -------------------------
  UPDATE agents.agents SET org_id = mon WHERE id = a_nnl;
  FOREACH rel IN ARRAY ARRAY['agent_personas', 'conversations', 'agent_package_trees',
      'agent_project_sources', 'agent_learnings', 'agent_versions', 'agent_clients',
      'agent_audit_log', 'knowledge_collections', 'knowledge_documents', 'eval_cases', 'eval_runs'] LOOP
    EXECUTE format('UPDATE agents.%I SET org_id = %L WHERE agent_id = %L', rel, mon, a_nnl);
  END LOOP;
  UPDATE agents.knowledge_documents SET org_id = mon
   WHERE collection_id IN (SELECT id FROM agents.knowledge_collections WHERE agent_id = a_nnl);
  UPDATE agents.knowledge_revisions SET org_id = mon
   WHERE document_id IN (SELECT id FROM agents.knowledge_documents WHERE org_id = mon);
  FOREACH rel IN ARRAY ARRAY['agent_prompt_sections', 'agent_skills', 'compiled_prompts', 'messages'] LOOP
    EXECUTE format('UPDATE agents.%I SET org_id = %L
                     WHERE version_id IN (SELECT id FROM agents.agent_versions WHERE agent_id = %L)',
                   rel, mon, a_nnl);
  END LOOP;
  UPDATE agents.agent_skill_files SET org_id = mon
   WHERE skill_id IN (SELECT id FROM agents.agent_skills WHERE org_id = mon);
  UPDATE agents.eval_results SET org_id = mon
   WHERE run_id IN (SELECT id FROM agents.eval_runs WHERE agent_id = a_nnl);
  FOREACH rel IN ARRAY ARRAY['messages', 'session_transcript_entries', 'approvals'] LOOP
    EXECUTE format('UPDATE agents.%I SET org_id = %L
                     WHERE conversation_id IN (SELECT id FROM agents.conversations WHERE agent_id = %L)',
                   rel, mon, a_nnl);
  END LOOP;

  -- store · the shop's API keys belong to the shop owner (STORE_ORG_ID → Gilson)
  UPDATE store.credentials SET org_id = gil WHERE org_id = noc;
END $$;

SET LOCAL session_replication_role = origin;

-- ── 3 · people (triggers ON: auth metadata sync) ───────────────────────────
UPDATE public.noctus_users SET org_id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d', updated_at = now()
 WHERE org_id = '6dd73140-74a4-41c6-aeff-bc94b5312b53' AND email LIKE '%@one.com.br'
   AND email <> 'monica@one.com.br';
UPDATE public.noctus_users SET org_role = 'admin', updated_at = now() WHERE email = 'gilson@one.com.br';
UPDATE public.noctus_users SET org_role = 'juridico', role = 'user', updated_at = now()
 WHERE email = 'marina@one.com.br';
UPDATE public.noctus_users
   SET org_id = 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', org_role = 'owner', updated_at = now()
 WHERE email = 'monica@one.com.br';
UPDATE public.noctus_users
   SET org_id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d', org_role = 'owner', role = 'user', updated_at = now()
 WHERE id = ':one_owner';

UPDATE erp.profiles p SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE p.id = u.id
   AND u.org_id IN ('fd169d29-4d0a-4b04-9a5e-25e69407614d', 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688')
   AND p.org_id IS DISTINCT FROM u.org_id;
UPDATE public.notifications nt SET org_id = u.org_id
  FROM public.noctus_users u
 WHERE nt.user_id = u.id AND nt.org_id = '6dd73140-74a4-41c6-aeff-bc94b5312b53' AND u.org_id <> nt.org_id;

UPDATE public.organizations o
   SET number_of_users = GREATEST(1, (SELECT count(*) FROM public.noctus_users u WHERE u.org_id = o.id))
 WHERE id IN ('6dd73140-74a4-41c6-aeff-bc94b5312b53', 'fd169d29-4d0a-4b04-9a5e-25e69407614d',
              '0ca4abef-c84f-410a-b878-4b22f4ea5ed9', 'fa80a1e0-1bcd-4c65-8a37-2162e8ffa688');

-- ── 4 · licenses (NoctusAI's are by construction — core 068) ───────────────
INSERT INTO public.licenses (org_id, product_id, status, source)
SELECT v.org_id::uuid, p.id, 'active', 'manual'
  FROM (VALUES ('fd169d29-4d0a-4b04-9a5e-25e69407614d', 'social-wiring'),
               ('0ca4abef-c84f-410a-b878-4b22f4ea5ed9', 'store'),
               ('fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'agents'),
               ('fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'social-wiring')) AS v(org_id, slug)
  JOIN public.products p ON p.slug = v.slug
 WHERE NOT EXISTS (SELECT 1 FROM public.licenses l WHERE l.org_id = v.org_id::uuid
                     AND l.product_id = p.id AND l.status = 'active');

-- ── 5 · One keeps the LLM choices its CRM ran on (org_settings tier-1) ─────
INSERT INTO public.org_settings (org_id, key, value, is_secret)
SELECT 'fd169d29-4d0a-4b04-9a5e-25e69407614d', s.key, s.value, s.is_secret
  FROM public.org_settings s
 WHERE s.org_id = '6dd73140-74a4-41c6-aeff-bc94b5312b53'
   AND s.key IN ('anthropic_api_key', 'llm_chat_provider', 'llm_vision_provider')
   AND NOT EXISTS (SELECT 1 FROM public.org_settings x
                    WHERE x.org_id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d' AND x.key = s.key);

COMMIT;
