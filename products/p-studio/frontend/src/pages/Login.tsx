import { useNavigate } from "react-router-dom";
import { Camera } from "lucide-react";
import { LoginForm } from "@noctusai/lib/design-system";
import { supabase } from "@noctusai/seed/infra";

/**
 * P Studio login — the platform-standard Supabase path (same organ as
 * social-wiring / igig), replacing the hand-rolled form that used to talk
 * directly to the local `useAuth` zustand store.
 */
export default function Login() {
  const navigate = useNavigate();

  return (
    <LoginForm
      brandIcon={Camera}
      brandTitle="P Studio"
      brandSubtitle="Gestão da produtora — entre para continuar"
      supabase={supabase}
      onSuccess={() => navigate("/")}
    />
  );
}
