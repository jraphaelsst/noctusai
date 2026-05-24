import { useParams, useNavigate } from "react-router-dom";
import { GraduationCap } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";

// Single-container model: same-origin by default. Only set
// VITE_BACKEND_API_URL when the FE points at a non-co-located backend.
const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "";
const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export default function AcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="Knowledge Extractor"
      brandIcon={GraduationCap}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath={`${CORE_URL}/login`}
      onAccepted={() => navigate("/sso")}
    />
  );
}
