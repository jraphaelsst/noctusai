/**
 * `useEffectiveSSOContext()` -- the SSO context re-based on the EFFECTIVE org of this visit
 * (`resolveEffectiveSSOContext`, sso.ts): the server's `/api/me/access` org + role once it
 * answered, the SSO token's only while it has not. Lives beside `useOrgSelection` (not the
 * dependency-free root barrel) because it needs `@noctusai/seed/infra` + React Query.
 *
 * Shares the ONE `/api/me/access` query (`useMeAccess`) -- no extra request.
 */
import { useAuthStore } from '@noctusai/seed/infra';

import { useMeAccess } from './org-selection';
import { resolveEffectiveSSOContext } from './sso';
import type { EffectiveSSOContext } from './sso';

export function useEffectiveSSOContext(): EffectiveSSOContext {
  const { user } = useAuthStore();
  const { data } = useMeAccess();
  return resolveEffectiveSSOContext(user?.user_metadata, data);
}
