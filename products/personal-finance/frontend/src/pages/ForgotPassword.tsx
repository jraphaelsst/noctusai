import { Link } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { ForgotPasswordPage } from "@noctusai/shared/design-system";
import { DollarSign } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={DollarSign}
      brandTitle="Financas Pessoais"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
