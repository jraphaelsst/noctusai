/**
 * `useIsOrgAdmin()` -- the canonical org-admin UX gate for a component.
 *
 * Applies `isOrgAdmin` (sso.ts) to the EFFECTIVE org of this visit
 * (`useEffectiveSSOContext`): after a member switches org, their role in the
 * org they are now in decides -- not the role the SSO token was minted with.
 * The token's role stands in only while `/api/me/access` has not answered.
 * Platform staff carry `noctus_role: 'admin'`, so this is true for them in any
 * picked org. UX only -- the server enforces.
 */
import { isOrgAdmin } from './sso';
import { useEffectiveSSOContext } from './use-effective-sso-context';

export function useIsOrgAdmin(): boolean {
  return isOrgAdmin(useEffectiveSSOContext());
}
