/**
 * ERP Accept Invite — thin wrapper around the shared AcceptInvitePage.
 *
 * Public route (outside auth guard) that handles invitation acceptance.
 * The backend creates the auth user from the invitation record.
 */
import { useNavigate, useParams } from "react-router-dom";
import { Building2 } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";

const API_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8001";

export default function AcceptInvite() {
  const navigate = useNavigate();
  const { token } = useParams<{ token: string }>();

  return (
    <AcceptInvitePage
      productName="ERP Imobiliario"
      brandIcon={Building2}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={API_URL}
      token={token}
      loginPath="/"
      onAccepted={() => navigate("/")}
    />
  );
}
