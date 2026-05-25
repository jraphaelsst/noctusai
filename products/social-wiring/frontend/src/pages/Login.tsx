import { useNavigate, Link } from "react-router-dom";
import { Share2 } from "lucide-react";
import { LoginForm } from "@noctusai/lib/design-system";
import { useAuthStore } from '@noctusai/seed/infra';
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

/**
 * Social Wiring login — uses the HttpOnly-cookie session flow
 * (`/api/auth/{login,me,logout}`) introduced by Wave 3 of
 * platform-auth-modernization. The seed `LoginForm` operates in
 * `useSessionAuth` mode here; the rest of the platform stays on the
 * legacy Supabase path via the same component.
 *
 * After login succeeds, `onSessionSuccess` pushes the user into the
 * shared `useAuthStore` so the rest of the app sees the authenticated
 * state immediately — without needing a separate `/api/auth/me`
 * round-trip (the AuthProvider's boot-time `useSessionAuthInit` covers
 * page reloads).
 */
export default function Login() {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  return (
    <div className="relative">
      <LoginForm
        brandIcon={Share2}
        brandTitle="Social Wiring"
        brandSubtitle="A minimal NoctusAI product"
        useSessionAuth
        onSessionSuccess={({ user }) => setUser(user)}
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
