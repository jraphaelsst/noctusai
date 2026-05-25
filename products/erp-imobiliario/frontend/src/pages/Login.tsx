import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import { supabase } from '@noctusai/seed/infra';
import { LoginForm } from "@noctusai/lib/design-system";
import { Building2 } from "lucide-react";
import { env } from "@noctusai/lib";

// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

export default function Login() {
  const navigate = useNavigate();

  return (
    <div className="relative min-h-screen">
      <LoginForm
        brandIcon={Building2}
        brandTitle="ERP Imobiliario"
        brandSubtitle="Gestao imobiliaria inteligente"
        supabase={supabase}
        onSuccess={() => navigate("/")}
        showForgotPassword
        forgotPasswordPath="/forgot-password"
        renderLink={({ to, className, children }) => (
          <Link to={to} className={className}>{children}</Link>
        )}
      />
      <div className="fixed bottom-6 left-0 right-0 text-center">
        <a
          href={CORE_URL}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Acesse pelo NoctusAI
        </a>
      </div>
    </div>
  );
}
