import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

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
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-sm p-8 text-center">
        <h1 className="text-2xl font-bold text-foreground mb-2">{{PRODUCT_NAME}}</h1>
        <p className="text-muted-foreground mb-6">
          Acesse este produto pelo painel NoctusAI.
        </p>
        <a
          href={CORE_URL}
          className="inline-flex items-center justify-center w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Ir para NoctusAI
        </a>
      </div>
    </div>
  );
}
