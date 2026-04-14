import { Link } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { ForgotPasswordPage } from "@noctusai/shared/design-system";
import { Building2 } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={Building2}
      brandTitle="ERP Imobiliario"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
