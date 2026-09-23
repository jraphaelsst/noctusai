/**
 * "Can this user change agency-wide settings?" — the FE mirror of the
 * backend's `exigir_admin_da_org` (`app/pipelines.py`): a platform/product
 * admin, or an org owner/admin.
 *
 * ONE predicate for every admin-gated control (stage editors on Comercial and
 * Esteira, Automações rules, lead-source setup). Before this helper the
 * Comercial page checked `isProductAdmin || org role ∈ ADMIN_ROLES` while the
 * Esteira board checked `isProductAdmin` only — an org owner could edit one
 * board's stages and not the other's, though the server allows both.
 *
 * UX only: it hides what the server would refuse. The server's check (the
 * TRUSTED `public.noctus_users` cascade, not `user_metadata`) stays
 * authoritative.
 */
import { ADMIN_ROLES, resolveSSOContext, type OrgRole } from "@noctusai/lib";
import { useAuthStore } from "@noctusai/seed/infra";

export function useIsOrgAdmin(): boolean {
  const { user } = useAuthStore();
  const sso = resolveSSOContext(user?.user_metadata);
  return sso.isProductAdmin || ADMIN_ROLES.includes(sso.org.role as OrgRole);
}
