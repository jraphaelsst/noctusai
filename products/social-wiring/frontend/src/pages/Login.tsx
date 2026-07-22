import { useNavigate, Link } from "react-router-dom";
import { Share2 } from "lucide-react";
import { LoginForm } from "@noctusai/lib/design-system";
import { supabase } from '@noctusai/seed/infra';
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

/**
 * Social Wiring login — the platform-standard Supabase path, identical to
 * the other ten products.
 *
 * This page previously ran the seed `LoginForm` in `useSessionAuth` mode
 * (the HttpOnly-cookie flow, `/api/auth/{login,me,logout}`), making
 * social-wiring the ONLY product on cookie login. That left it half-migrated
 * and login was broken end-to-end — two independent causes:
 *
 *   1. `/api/auth/login` mints an opaque `nai_session` cookie, but the seed
 *      api client builds its `Authorization` header from
 *      `supabase.auth.getSession()` (`seed/framework/frontend/src/infra.tsx`).
 *      Cookie login creates no supabase-js session ⇒ no bearer ⇒ every
 *      product route answered 401 "Token ausente" (the seed standard routers
 *      — `/api/notificacoes`, `/api/team` — read ONLY the Authorization
 *      header) ⇒ `onUnauthenticated` ⇒ redirect to Landing.
 *   2. `App.tsx` still spreads `infra.appConfig`, so boot-restore runs
 *      `useSupabaseAuthInit` — on any reload the auth store resolves to
 *      `user = null` regardless of the cookie, bouncing before a 401 even
 *      fires.
 *
 * Reverting here is the correct fix rather than pushing the cookie flow
 * forward, because the roadmap
 * (`project-history/roadmaps/erp-httponly-cookie-session-2026-07.md`, Slice
 * 1b′) gates cookie mode on a seed `createProductLayout` seam that has NOT
 * landed — and explicitly warns that flipping the AuthProvider before it
 * does makes "Sair" a silent no-op (cookie never cleared, user only *looks*
 * logged out), which is worse than the posture it replaces.
 *
 * SSO is unaffected either way: core mints a one-time token and
 * `SSOCallback` exchanges it via `supabase.auth.setSession`, so
 * noc → subdomain launches always produced a real bearer. Only direct
 * credential login on this subdomain was broken.
 *
 * Re-migrating to cookie sessions is roadmap work (Slices 1b′ → 2 → 3), not
 * a per-product decision.
 */
export default function Login() {
  const navigate = useNavigate();

  return (
    <div className="relative">
      <LoginForm
        brandIcon={Share2}
        brandTitle="Social Wiring"
        brandSubtitle="A minimal NoctusAI product"
        supabase={supabase}
        onSuccess={() => navigate("/")}
        showForgotPassword
        renderLink={({ to, className, children }) => (
          <Link to={to} className={className}>{children}</Link>
        )}
      />

      {/* Link back to core platform */}
      <div className="fixed bottom-6 left-0 right-0 flex justify-center">
        <a
          href={CORE_URL}
          className="text-xs text-muted-foreground hover:text-primary transition-colors"
        >
          Acesse pelo NoctusAI
        </a>
      </div>
    </div>
  );
}
