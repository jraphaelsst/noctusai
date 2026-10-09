/**
 * `useIsAdmin` — the community staff write gate, read off the SSO context.
 *
 * The same expression was inlined in `Equipe.tsx`, `WhatsApp.tsx` and
 * `Configuracoes.tsx` (N=3, and WhatsApp's copy had already drifted by
 * dropping `owner`). The Ninho Vazio back office adds five more call sites,
 * so the expression lives in the seed (`useIsOrgAdmin`) and this is its local name. The server is still the boundary —
 * every admin write also 403s a `moderador` — this only decides whether the
 * write controls are rendered at all.
 */
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

export function useIsAdmin(): boolean {
  return useIsOrgAdmin();
}
