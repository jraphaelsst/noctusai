import { useNavigate, Link } from "react-router-dom";
import { CalendarClock } from "lucide-react";
import { LoginForm } from "@noctusai/lib/design-system";
import { supabase } from '@noctusai/seed/infra';

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export default function Login() {
  const navigate = useNavigate();

  return (
    <div className="relative">
      <LoginForm
        brandIcon={CalendarClock}
        brandTitle="Imobi Scheduling"
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
