-- ============================================================================
-- 002_plataforma_e_seeds.sql — registro na plataforma + dados iniciais
-- Idempotente: pode ser reexecutado sem duplicar nada.
--
-- Faz:
--   1. Expõe o schema `p_studio` no PostgREST (lista completa preservada).
--   2. Registra o produto em public.products (padrão da plataforma).
--   3. Cria a organização "P Studio".
--   4. Cria um usuário admin de DESENVOLVIMENTO e o vincula à org em
--      public.noctus_users — é isso que faz public.current_org_id() resolver.
--   5. Seeds de domínio: catálogo de serviços (preços reais do estúdio) e
--      equipamentos básicos do checklist.
--
-- ⚠️ CREDENCIAL DE DESENVOLVIMENTO. `admin@pstudio.local` / `senha123` existe
--    para subir o ambiente local. NÃO promover para produção: em produção o
--    usuário é provisionado pelo fluxo normal da plataforma. O protótipo
--    Lovable cometeu exatamente esse erro — gravou a senha real do dono do
--    estúdio no histórico do git, onde ela permanece. Ver
--    `_NOC_ABSORPTION/01-DATA-MODEL.md` § Security findings.
-- ============================================================================

-- Expõe `p_studio` no PostgREST ACRESCENTANDO à lista existente.
--
-- A versão anterior desta migration escrevia a lista inteira literal. Isso é
-- uma bomba num banco compartilhado: a lista foi copiada em 31/07/2026, e em
-- 13/08/2026 o banco já expunha `igig`, que não estava nela. Rodar o literal
-- teria removido `igig` do PostgREST e derrubado a API daquele produto — sem
-- erro nenhum, porque `ALTER ROLE ... SET` sempre "funciona".
--
-- Nenhum produto pode escrever a lista dos outros. Só a sua própria linha.
DO $$
DECLARE
  v_atual text;
BEGIN
  SELECT substring(cfg FROM 'pgrst[.]db_schemas=(.*)') INTO v_atual
  FROM (
    SELECT unnest(setconfig) AS cfg
    FROM pg_db_role_setting s
    JOIN pg_roles r ON r.oid = s.setrole
    WHERE r.rolname = 'authenticator'
  ) t
  WHERE cfg LIKE 'pgrst.db_schemas=%';

  v_atual := COALESCE(v_atual, 'public, graphql_public');

  IF v_atual !~ '(^|,)\s*p_studio\s*(,|$)' THEN
    EXECUTE format(
      'ALTER ROLE authenticator SET pgrst.db_schemas = %L',
      v_atual || ', p_studio'
    );
    RAISE NOTICE 'p_studio acrescentado ao PostgREST: %', v_atual || ', p_studio';
  ELSE
    RAISE NOTICE 'p_studio já exposto no PostgREST';
  END IF;
END $$;
NOTIFY pgrst, 'reload config';

DO $$
DECLARE
  v_org   uuid;
  v_admin uuid;
BEGIN
  -- ── Organização ────────────────────────────────────────────────────────
  SELECT id INTO v_org FROM public.organizations WHERE slug = 'p-studio';
  IF v_org IS NULL THEN
    INSERT INTO public.organizations (nome, slug)
    VALUES ('P Studio', 'p-studio')
    RETURNING id INTO v_org;
  END IF;

  -- ── Registro do produto na plataforma ──────────────────────────────────
  INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor)
  VALUES ('P Studio', 'p-studio',
          'Gestão operacional e financeira de produtora de fotografia e audiovisual imobiliário',
          'camera', 'http://localhost:5176', '#b45309')
  ON CONFLICT (slug) DO NOTHING;

  -- ── Admin de desenvolvimento ───────────────────────────────────────────
  SELECT id INTO v_admin FROM auth.users WHERE email = 'admin@pstudio.local';
  IF v_admin IS NULL THEN
    v_admin := gen_random_uuid();
    INSERT INTO auth.users (
      instance_id, id, aud, role, email, encrypted_password,
      email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
      created_at, updated_at,
      confirmation_token, recovery_token, email_change,
      email_change_token_new, email_change_token_current)
    VALUES (
      '00000000-0000-0000-0000-000000000000', v_admin, 'authenticated', 'authenticated',
      'admin@pstudio.local', extensions.crypt('senha123', extensions.gen_salt('bf')),
      now(), '{"provider":"email","providers":["email"]}'::jsonb,
      jsonb_build_object('nome', 'Admin P Studio', 'org_id', v_org::text),
      now(), now(), '', '', '', '', '');

    INSERT INTO auth.identities (
      id, provider_id, user_id, identity_data, provider,
      last_sign_in_at, created_at, updated_at)
    VALUES (
      gen_random_uuid(), v_admin::text, v_admin,
      jsonb_build_object('sub', v_admin::text, 'email', 'admin@pstudio.local', 'email_verified', true),
      'email', now(), now(), now());
  END IF;

  -- A fonte de verdade da organização. public.current_org_id() lê AQUI —
  -- nunca do raw_user_meta_data acima, que o próprio usuário pode editar.
  INSERT INTO public.noctus_users (id, nome, email, org_id, role, org_role)
  VALUES (v_admin, 'Admin P Studio', 'admin@pstudio.local', v_org, 'admin', 'owner')
  ON CONFLICT (id) DO UPDATE SET org_id = EXCLUDED.org_id;

  -- ── Catálogo de serviços ───────────────────────────────────────────────
  -- Preços e prazos reais do estúdio, preservados do protótipo Lovable
  -- (migration 20260727014921). Ver _NOC_ABSORPTION/01-DATA-MODEL.md.
  INSERT INTO p_studio.servicos (org_id, nome, categoria, preco, prazo_dias, descricao)
  SELECT v_org, s.nome, s.categoria, s.preco, s.prazo_dias, s.descricao
  FROM (VALUES
    ('Ensaio fotográfico',   'Fotografia',  950.00, 3, 'Até 30 fotos tratadas do imóvel'),
    ('Cobertura com drone',  'Aéreo',       700.00, 3, 'Fotos e vídeo aéreo do imóvel e entorno'),
    ('Vídeo horizontal',     'Audiovisual', 1500.00, 5, 'Vídeo institucional do imóvel em 16:9'),
    ('Reels vertical',       'Audiovisual', 700.00, 4, 'Vídeo vertical para redes sociais'),
    ('Tour guiado',          'Audiovisual', 1200.00, 5, 'Tour narrado pelo corretor'),
    ('Entrevista',           'Audiovisual', 900.00, 5, 'Entrevista com o corretor ou proprietário'),
    ('Conteúdo para redes',  'Social',      600.00, 3, 'Pacote de cortes e artes para redes sociais'),
    ('Filmagem institucional','Audiovisual', 2500.00, 7, 'Vídeo institucional da imobiliária')
  ) AS s(nome, categoria, preco, prazo_dias, descricao)
  WHERE NOT EXISTS (
    SELECT 1 FROM p_studio.servicos e WHERE e.org_id = v_org AND e.nome = s.nome
  );

  -- ── Equipamentos do checklist ──────────────────────────────────────────
  -- Vocabulário do checklist da spec § 3. Marca/modelo ficam em branco:
  -- o estúdio preenche com o inventário real.
  INSERT INTO p_studio.equipamentos (org_id, nome, categoria, quantidade)
  SELECT v_org, e.nome, e.categoria, e.quantidade
  FROM (VALUES
    ('Câmera',      'camera',     1),
    ('Lente 16-35', 'lente',      1),
    ('Lente 24-70', 'lente',      1),
    ('Drone',       'drone',      1),
    ('Microfone',   'microfone',  1),
    ('Gimbal',      'gimbal',     1),
    ('Baterias',    'bateria',    4),
    ('Cartões SD',  'cartao',     4),
    ('Iluminação',  'iluminacao', 1)
  ) AS e(nome, categoria, quantidade)
  WHERE NOT EXISTS (
    SELECT 1 FROM p_studio.equipamentos x WHERE x.org_id = v_org AND x.nome = e.nome
  );

  RAISE NOTICE 'P Studio: org_id = %', v_org;
END $$;
