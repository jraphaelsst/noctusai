-- 066 — public.roles carries EVERY canonical org role (2026-10-07)
--
-- Core's team router validates an invite / role change against the
-- `public.roles` system rows, but 001 only seeded owner/admin/member/viewer.
-- The canonical set (`noctusai_lib.primitives.roles.ORG_ROLES` ↔ roles.ts)
-- also has manager/dev/test/corretor and, from today, `juridico` (an org's
-- legal staff: member-level rights + approving a contract's legal review).
-- Without these rows Core 422/400s a role every product's UI offers.
--
-- `public.roles` has no unique key on (org_id, slug), so each insert is
-- guarded by NOT EXISTS (idempotent, re-runnable).

INSERT INTO public.roles (org_id, name, slug, permissions, is_system)
SELECT NULL, v.name, v.slug, v.permissions, true
  FROM (VALUES
    ('Gerente',       'manager',  ARRAY['team:manage', 'products:access']),
    ('Desenvolvedor', 'dev',      ARRAY['products:access', 'team:read']),
    ('Teste',         'test',     ARRAY['products:access', 'team:read']),
    ('Corretor',      'corretor', ARRAY['products:access', 'team:read']),
    ('Jurídico',      'juridico', ARRAY['products:access', 'team:read', 'contracts:legal_review'])
  ) AS v(name, slug, permissions)
 WHERE NOT EXISTS (
   SELECT 1 FROM public.roles r WHERE r.org_id IS NULL AND r.slug = v.slug
 );
