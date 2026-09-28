/**
 * `useIsAdmin` — the community staff write gate, read off the SSO context.
 *
 * The same expression was inlined in `Equipe.tsx`, `WhatsApp.tsx` and
 * `Configuracoes.tsx` (N=3, and WhatsApp's copy had already drifted by
 * dropping `owner`). The Ninho Vazio back office adds five more call sites,
 * so the expression lives here once. The server is still the boundary —
 * every admin write also 403s a `moderador` — this only decides whether the
 * write controls are rendered at all.
 */
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";

export function useIsAdmin(): boolean {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  return ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";
}
