/**
 * Shared role constants for the NoctusAI platform.
 *
 * Defines the 8-role org hierarchy used across Core and all products.
 * Products consume these in Layout.tsx, admin pages, and invite forms.
 *
 * 🔴 THIS FILE AND `noctusai_lib/primitives/roles.py` ARE ONE SET IN TWO
 * LANGUAGES. A role added to one and not the other is a split brain: the API
 * accepts a value the UI renders as a raw slug, or the UI offers a value the
 * API rejects. Change both, same commit.
 */

// `corretor` is a real business role, not a permission tier: it carries
// EXACTLY member-level rights (it appears in none of the grant arrays below)
// and exists so an agency's brokers are identifiable as brokers on the team
// page and attachable to their listings.
export const ORG_ROLES = [
  'owner', 'admin', 'manager', 'member', 'viewer', 'dev', 'test', 'corretor',
] as const;

export type OrgRole = (typeof ORG_ROLES)[number];

/** Roles that grant team/billing management */
export const ADMIN_ROLES: OrgRole[] = ['owner', 'admin'];

/** Roles that can manage team (invite/remove) but not billing */
export const MANAGE_TEAM_ROLES: OrgRole[] = ['owner', 'admin', 'manager'];

/**
 * Roles that see "in development" pages.
 * 🔴 PARITY CONTRACT: must stay identical to the RLS role array in every
 * `*_status_pagina_dev_visibility.sql` migration (the `dev_veem_desenvolvimento`
 * policy). Diverge and you get split-brain — RLS returns the row but the FE
 * hides it, or the reverse. Enforced by `check_status_pagina_role_parity`.
 */
export const DEV_ROLES: OrgRole[] = ['owner', 'dev', 'admin'];

/** Roles that grant product-level platform_admin via SSO */
export const PRODUCT_ADMIN_ROLES: OrgRole[] = ['owner', 'admin'];

/** Portuguese labels for UI display */
export const ORG_ROLE_LABELS: Record<OrgRole, string> = {
  owner: 'Proprietario',
  admin: 'Administrador',
  manager: 'Gerente',
  member: 'Membro',
  viewer: 'Visualizador',
  dev: 'Desenvolvedor',
  test: 'Teste',
  corretor: 'Corretor',
};

/** Assignable roles (cannot assign "owner" — that's the org creator only) */
export const ASSIGNABLE_ROLES: OrgRole[] = ['admin', 'manager', 'member', 'viewer', 'dev', 'test', 'corretor'];

/**
 * Check if user can see in-development pages (dev / owner / admin).
 * Consumes DEV_ROLES — the prior hardcoded `owner || dev` duplicated the
 * const beside it AND omitted admin, so it drifted from its own source of
 * truth. Name kept for call-site stability; it now means "can see dev pages".
 */
export function isDevOrOwner(orgRole: string | null | undefined): boolean {
  return DEV_ROLES.includes(orgRole as OrgRole);
}

/** Check if user can manage team (invite/remove) */
export function canManageTeam(orgRole: string | null | undefined): boolean {
  return MANAGE_TEAM_ROLES.includes(orgRole as OrgRole);
}

/** Check if user can manage billing */
export function canManageBilling(orgRole: string | null | undefined): boolean {
  return ADMIN_ROLES.includes(orgRole as OrgRole);
}
