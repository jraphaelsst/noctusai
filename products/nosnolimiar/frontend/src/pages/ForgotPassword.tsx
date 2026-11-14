import { Link } from "react-router-dom";
import { supabase } from '@noctusai/seed/infra';
import { ForgotPasswordPage } from "@noctusai/lib/design-system";
import { Users } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={Users}
      brandTitle="Nós no Limiar"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
