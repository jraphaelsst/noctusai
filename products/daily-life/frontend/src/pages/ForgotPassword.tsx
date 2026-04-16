import { Link } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { ForgotPasswordPage } from "@noctusai/lib/design-system";
import { CalendarCheck } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={CalendarCheck}
      brandTitle="Daily Life"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
