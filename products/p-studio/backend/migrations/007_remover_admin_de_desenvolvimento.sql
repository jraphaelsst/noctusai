-- ============================================================================
-- 007_remover_admin_de_desenvolvimento.sql — P Studio
-- Schema: auth + public (conta da plataforma, não do schema do produto)
--
-- A 002 semeia `admin@pstudio.local` e o cabeçalho dela já dizia, em letras
-- maiúsculas, que a conta NÃO podia ir para produção. Ela foi mesmo assim:
-- em 2026-08-17 a linha existia em `auth.users`
-- (id 7cfc5a7c-0503-4950-9301-d71e816c8f94), `email_confirmed_at` preenchido,
-- `role='admin'` / `org_role='owner'` em `public.noctus_users`, e
-- `last_sign_in_at = 2026-08-13 20:34:38+00`. Este projeto Supabase
-- (`nyplttplcoyiiqjrvtiw`) é o de produção da plataforma — `public.products`
-- carrega erp-imobiliario, igig, orbity e social-wiring, todos no ar — e
-- `auth.users` é COMPARTILHADO pela frota inteira.
--
-- ⚠️ O QUE **NÃO** ERA VERDADE, e está aqui para não ser reinventado: a senha
-- viva NÃO era o `senha123` do arquivo. Conferido no banco em 2026-08-14 —
-- `SELECT encrypted_password = crypt('senha123', encrypted_password)` devolve
-- **false** (ver `project-history/roadmaps/p-studio-2026-08.md`
-- § Known hazards). O que rodou gravou outra coisa. A remoção se justifica
-- pelo que a conta É — admin/owner de desenvolvimento, rotulada como tal,
-- viva no auth de produção, com senha que ninguém tem registrada — não por
-- uma credencial fraca publicada, que é uma afirmação que o banco não
-- sustenta. Esta migration foi escrita na primeira vez repetindo o erro que
-- aquela seção do roadmap documenta: ler o arquivo e relatá-lo como o estado
-- do mundo.
--
-- Por que forward migration e não editar a 002 (mesma razão da 004): a 002 já
-- rodou neste banco. Editar um arquivo já aplicado faz o arquivo mentir sobre
-- o que rodou. E como as migrations rodam em ordem, num banco novo a 002 cria
-- e a 007 remove logo em seguida — o estado final é correto-por-construção nos
-- dois caminhos (banco existente e banco do zero).
--
-- ⚠️ O que esta migration NÃO resolve. Ela remove a CONTA, não o padrão que a
-- produziu: uma credencial de desenvolvimento literal dentro de uma migration
-- que roda contra produção. O ARQUIVO continua com o hash de `senha123`
-- (`002:90`), então uma reaplicação da 002 introduziria a credencial fraca de
-- verdade — este é o perigo real e ele é FUTURO, não passado. Numa base do
-- zero a ordem resolve (002 cria, 007 remove logo em seguida); numa base já
-- existente, não reaplique a 002. O roadmap registra o corolário mais durável:
-- **o arquivo não é um registro fiel do que rodou.**
-- `products/p-studio/README.md:64` ainda publica o par como credencial local.
--
-- Alcance da remoção, conferido antes de escrever (contagens no banco vivo):
--   public.organizations.owner_id  → 0   (a org "P Studio" tem owner_id NULL)
--   public.audit_logs.user_id      → 0
--   public.notifications.user_id   → 0
--   public.api_keys.created_by     → 0
--   public.ai_consent.user_id      → 0
--   public.ai_feedback.user_id     → 0
--   public.noctus_users.id         → 1   (removida aqui, explicitamente)
--   auth.identities.user_id        → 1   (cai por CASCADE)
--   auth.sessions.user_id          → 1   (cai por CASCADE — invalida o login de 08-13)
-- Nenhuma tabela de `p_studio` referencia usuário; os seeds de domínio
-- (serviços, equipamentos) pertencem à ORG (cb78914a-…), que permanece.
--
-- Sobre o CASCADE: as DEZ FKs do schema `auth` que apontam para
-- `auth.users`/`auth.sessions` têm `confdeltype='c'` (conferido no banco vivo,
-- `pg_constraint`) — identities, sessions, mfa_factors, mfa_amr_claims,
-- refresh_tokens, oauth_authorizations, oauth_consents, one_time_tokens,
-- webauthn_challenges, webauthn_credentials. Por isso um único DELETE em
-- `auth.users` basta. Apagar `sessions`/`identities` à mão, como esta migration
-- fazia no primeiro rascunho, seria ao mesmo tempo redundante e INCOMPLETO:
-- deixaria de fora mfa_factors, oauth_* , one_time_tokens e webauthn_*.
--
-- A org fica com 0 membros de propósito. O dono real entra pelo fluxo normal
-- de convite da plataforma — `p_studio.invitations`, que a 006 criou.
--
-- Idempotente: todo DELETE casa por e-mail/id; reaplicar não faz nada.
--
-- NOC-REMEDIATE[dev-credential-in-migration]: mover o seeding de credencial de
-- desenvolvimento para um seed script dev-only, fora da cadeia de migrations
-- que roda contra produção. Afeta a 002 deste produto e qualquer migration da
-- frota que semeie `auth.users`. Ver o cabeçalho da 002 e
-- `KB § PATTERNS/security/lgpd.md`.
-- ============================================================================

DO $$
DECLARE
  v_admin uuid;
BEGIN
  SELECT id INTO v_admin
    FROM auth.users
   WHERE email = 'admin@pstudio.local';

  IF v_admin IS NULL THEN
    RAISE NOTICE '007: admin@pstudio.local ausente — nada a fazer (idempotente).';
    RETURN;
  END IF;

  -- `public.noctus_users` é da PLATAFORMA, fora do cascade do GoTrue: sai à mão.
  DELETE FROM public.noctus_users WHERE id = v_admin;

  -- E este DELETE leva junto identities / sessions / refresh_tokens /
  -- mfa_* / oauth_* / one_time_tokens / webauthn_* pelo CASCADE.
  DELETE FROM auth.users WHERE id = v_admin;

  RAISE NOTICE '007: admin@pstudio.local removido (id %).', v_admin;
END
$$;
