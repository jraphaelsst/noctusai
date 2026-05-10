import { Link } from "react-router-dom";
import { supabase } from '@noctusai/seed/infra';
import { ForgotPasswordPage } from "@noctusai/lib/design-system";
import { CalendarClock } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={CalendarClock}
      brandTitle="Imobi Scheduling"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
