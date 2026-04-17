import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import { supabase } from '@noctusai/seed/infra';
import { LoginForm } from "@noctusai/lib/design-system";
import { Heart } from "lucide-react";

export default function Login() {
  const navigate = useNavigate();

  return (
    <LoginForm
      brandIcon={Heart}
      brandTitle="Plataforma de Terapia"
      supabase={supabase}
      onSuccess={() => navigate("/")}
      showForgotPassword
      showRegisterLink
      showGoogleOAuth
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
