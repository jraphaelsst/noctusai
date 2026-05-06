import { useParams, useNavigate } from "react-router-dom";
import { PlaySquare } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8010";
const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export default function SeedAcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="YouTube Crawler"
      brandIcon={PlaySquare}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath={`${CORE_URL}/login`}
      onAccepted={() => navigate("/sso")}
    />
  );
}
