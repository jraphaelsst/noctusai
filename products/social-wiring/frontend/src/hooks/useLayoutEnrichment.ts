/**
 * Social Wiring Layout Enrichment Hook
 *
 * Fixes the role-label flicker: the header briefly showed "Membro" right
 * after login, then flipped to "Administrador" on a later load — same
 * user, same Supabase session. Root cause: `createProductLayout`'s
 * default role (`resolveSSOContext(user.user_metadata).org.role`) reads a
 * value baked into the Supabase JWT at ISSUE time. Core's `/api/sso/session`
 * syncs the authoritative `org_role` into `user_metadata` via the ADMIN api
 * (`products/core/backend/app/routers/sso.py`), but that write does not
 * retroactively rewrite the access token already held by the browser — the
 * local session (`supabase.auth.getSession()`, decoded from storage) keeps
 * serving the STALE snapshot until the SDK's next silent token refresh
 * re-issues a JWT with the current DB value. That's the "later load" flip:
 * not a second guess replacing a first guess, but a stale cache resolving
 * into the truth once the token happens to roll over.
 *
 * The fix does NOT touch the seed (`layout.tsx` / `infra.tsx`) or any other
 * product — it uses the ALREADY-SHIPPED, additive `useLayoutEnrichment`
 * extension point (see ERP's own `hooks/useLayoutEnrichment.ts` for the
 * established per-product convention) to supply `roleLabel` from the
 * seed's own `GET /api/team` (`noctus_users.org_role`, DB-backed, same
 * request `Equipe.tsx` already makes — `useTeamMembers()` — so this reads
 * from cache/shares the request instead of adding a new one) — the same
 * "owner | admin | manager | member | viewer" vocabulary the layout's
 * `DEFAULT_ROLE_LABELS` already maps, so the label swaps AT MOST ONCE per
 * boot, straight to the correct value.
 *
 * `enrichment.roleLabel` has TOP precedence in `createProductLayout`
 * (`userRole = enrichment.roleLabel || roleLabelOverride || (guess)`), so
 * setting it here always wins over the JWT-derived guess once resolved.
 *
 * States:
 *   - team list still loading (first fetch, no cached data) → "Carregando…"
 *     (a neutral placeholder — never a wrong-but-plausible label).
 *   - own row found → the authoritative label. Does NOT re-flip to
 *     "Carregando…" on a background refetch (gated on `isPending`, not
 *     `isFetching` — the same isPending-vs-isFetching rule the ChartCard/
 *     StatTile loading props follow elsewhere in this product).
 *   - team fetch failed, or the user's own row isn't in the list for any
 *     reason → `roleLabel` is left `undefined`, degrading to the PRE-
 *     EXISTING guess-based fallback (status quo, not a regression) rather
 *     than blocking the whole header.
 *
 * Scope note: this only overrides the DISPLAYED label. `effectiveDevRole`
 * (page-visibility gating) is untouched — that's a bigger blast-radius
 * access-control concern, out of scope for a display-flicker fix.
 */
import { useAuthStore } from "@noctusai/seed/infra";
import type { LayoutEnrichment } from "@noctusai/seed";
import { useTeamMembers } from "@/hooks/useTeam";

const ORG_ROLE_LABELS: Record<string, string> = {
  owner: "Proprietário",
  admin: "Administrador",
  manager: "Gerente",
  member: "Membro",
  viewer: "Visualizador",
};

export function useSocialWiringLayoutEnrichment(): LayoutEnrichment {
  const { user } = useAuthStore();
  const { data: members, isPending } = useTeamMembers();

  const ownRole = members?.find((m) => m.id === user?.id)?.org_role;

  return {
    roleLabel: isPending ? "Carregando…" : ownRole ? ORG_ROLE_LABELS[ownRole] ?? ownRole : undefined,
  };
}
