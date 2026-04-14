import { Link } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { ForgotPasswordPage } from "@noctusai/shared/design-system";
import { {{PRODUCT_ICON}} } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={{{PRODUCT_ICON}}}
      brandTitle="{{PRODUCT_NAME}}"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
