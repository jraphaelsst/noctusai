/**
 * Shared role constants for the NoctusAI platform.
 *
 * Defines the 7-role org hierarchy used across Core and all products.
 * Products consume these in Layout.tsx, admin pages, and invite forms.
 */

export const ORG_ROLES = [
  'owner', 'admin', 'manager', 'member', 'viewer', 'dev', 'test',
] as const;

export type OrgRole = (typeof ORG_ROLES)[number];

/** Roles that grant team/billing management */
export const ADMIN_ROLES: OrgRole[] = ['owner', 'admin'];

/** Roles that can manage team (invite/remove) but not billing */
export const MANAGE_TEAM_ROLES: OrgRole[] = ['owner', 'admin', 'manager'];

/** Roles that see "in development" pages */
export const DEV_ROLES: OrgRole[] = ['owner', 'dev'];

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
};

/** Assignable roles (cannot assign "owner" — that's the org creator only) */
export const ASSIGNABLE_ROLES: OrgRole[] = ['admin', 'manager', 'member', 'viewer', 'dev', 'test'];

/** Check if user can see in-development pages */
export function isDevOrOwner(orgRole: string | null | undefined): boolean {
  return orgRole === 'owner' || orgRole === 'dev';
}

/** Check if user can manage team (invite/remove) */
export function canManageTeam(orgRole: string | null | undefined): boolean {
  return MANAGE_TEAM_ROLES.includes(orgRole as OrgRole);
}

/** Check if user can manage billing */
export function canManageBilling(orgRole: string | null | undefined): boolean {
  return ADMIN_ROLES.includes(orgRole as OrgRole);
}
