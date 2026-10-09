/**
 * `useIsOrgAdmin()` — the canonical org-admin UX gate for a component.
 *
 * Reads the signed-in user off the auth store and applies `isOrgAdmin`
 * (sso.ts). Lives beside `useOrgSelection` (not the dependency-free root
 * barrel) because it needs `@noctusai/seed/infra`. UX only — the server
 * enforces. Org picker: platform staff carry `noctus_role: 'admin'`, so
 * this is true for them in any picked org.
 */
import { useAuthStore } from '@noctusai/seed/infra';

import { isOrgAdmin, resolveSSOContext } from './sso';

export function useIsOrgAdmin(): boolean {
  const { user } = useAuthStore();
  return isOrgAdmin(resolveSSOContext(user?.user_metadata));
}
