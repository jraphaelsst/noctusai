import { useParams, useNavigate } from "react-router-dom";
import { Box } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";
import { env } from "@noctusai/lib";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8010";
// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

export default function SeedAcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="Orbity"
      brandIcon={Box}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath={`${CORE_URL}/login`}
      onAccepted={() => navigate("/sso")}
    />
  );
}
