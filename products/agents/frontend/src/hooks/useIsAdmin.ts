/**
 * Admin-gating hook for the Agentes UI.
 *
 * Contract §E ("Roles"): persona writes, agent toggles and approval
 * decisions on someone else's request are `owner`/`admin` only; any org
 * member can chat and read their own conversations. `resolveSSORoles`
 * (`@noctusai/lib`) already resolves `org_role in (owner, admin)` OR
 * `noctus_role === "admin"` into one `isProductAdmin` boolean — the same
 * role set as the backend's `ADMIN_ROLES = frozenset({"owner", "admin"})`
 * (`app/dependencies.py`). Mirrors the `Equipe.tsx` / `Dashboard.tsx`
 * `resolveSSOContext(user?.user_metadata)` convention already used
 * elsewhere in this product.
 */
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSORoles } from "@noctusai/lib";

export function useIsAdmin(): boolean {
  const { user } = useAuthStore();
  return resolveSSORoles(user?.user_metadata).isProductAdmin;
}
