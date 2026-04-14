import { Link } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { ForgotPasswordPage } from "@noctusai/shared/design-system";
import { Sprout } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={Sprout}
      brandTitle="Seed Product"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
