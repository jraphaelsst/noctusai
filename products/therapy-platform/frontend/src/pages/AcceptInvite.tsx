import { useParams, useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8003";

export default function TherapyAcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="Plataforma de Terapia"
      brandIcon={Heart}
      acceptEndpoint="/api/invitations/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath="/login"
      onAccepted={() => navigate("/login")}
    />
  );
}
