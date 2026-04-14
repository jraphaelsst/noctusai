import { useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { LoginForm } from "@noctusai/shared/design-system";
import { {{PRODUCT_ICON}} } from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export function Login() {
  const { user, isInitialized } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (isInitialized && user) {
      navigate("/", { replace: true });
    }
  }, [isInitialized, user]);

  return (
    <>
      <LoginForm
        brandIcon={ {{PRODUCT_ICON}} }
        brandTitle="{{PRODUCT_NAME}}"
        supabase={supabase}
        onSuccess={() => navigate("/")}
        renderLink={({ to, className, children }) => (
          <Link to={to} className={className}>{children}</Link>
        )}
      />
      <div className="fixed bottom-4 left-0 right-0 text-center">
        <p className="text-xs text-muted-foreground">
          Ou acesse pelo{" "}
          <a
            href={CORE_URL}
            className="text-primary hover:underline font-medium"
          >
            painel NoctusAI
          </a>
        </p>
      </div>
    </>
  );
}
