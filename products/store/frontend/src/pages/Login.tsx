import { useNavigate, Link } from "react-router-dom";
import { ShoppingBag } from "lucide-react";
import { LoginForm } from "@noctusai/lib/design-system";
import { supabase } from '@noctusai/seed/infra';

export default function Login() {
  const navigate = useNavigate();

  return (
    <div className="relative">
      <LoginForm
        brandIcon={ShoppingBag}
        brandTitle="Store"
        brandSubtitle="Administração da loja"
        supabase={supabase}
        onSuccess={() => navigate("/admin")}
        showForgotPassword
        renderLink={({ to, className, children }) => (
          <Link to={to} className={className}>{children}</Link>
        )}
      />
    </div>
  );
}
