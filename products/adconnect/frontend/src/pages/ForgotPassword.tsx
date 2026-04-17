import { Link } from "react-router-dom";
import { supabase } from '@noctusai/seed/infra';
import { ForgotPasswordPage } from "@noctusai/lib/design-system";
import { ShoppingCart } from "lucide-react";

export default function ForgotPassword() {
  return (
    <ForgotPasswordPage
      brandIcon={ShoppingCart}
      brandTitle="AdConnect"
      supabase={supabase}
      renderLink={({ to, className, children }) => (
        <Link to={to} className={className}>{children}</Link>
      )}
    />
  );
}
