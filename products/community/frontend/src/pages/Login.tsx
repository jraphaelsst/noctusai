import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Feather } from "lucide-react";
import { LoginForm } from "@noctusai/lib/design-system";
import { supabase } from '@noctusai/seed/infra';
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

/** A plan id is a UUID; anything else in `?plano=` is ignored (never echoed
 * into a navigation target). */
const PLANO_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * After login: `/login?plano=<id>` (set by `/cadastro` when a paid tier was
 * picked) continues to `/portal?trocar=<id>`, which opens the member's plan
 * change dialog for that tier — NOT `/assinar`: the new member is already
 * `ativo` on the free plan, and the anonymous checkout (correctly) never
 * opens a subscription for an active member's e-mail. Otherwise `/`, where
 * `RoleLayout` sends a member to `/portal` and staff to the back office.
 */
export function destinoAposLogin(plano: string | null): string {
  if (plano && PLANO_ID_RE.test(plano)) return `/portal?trocar=${encodeURIComponent(plano)}`;
  return "/";
}

export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  return (
    <div className="relative">
      <LoginForm
        brandIcon={Feather}
        brandTitle="Ninho Vazio"
        brandSubtitle="Entre para continuar a sua travessia"
        supabase={supabase}
        onSuccess={() => navigate(destinoAposLogin(params.get("plano")))}
        showForgotPassword
        showRegisterLink
        registerPath="/cadastro"
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
