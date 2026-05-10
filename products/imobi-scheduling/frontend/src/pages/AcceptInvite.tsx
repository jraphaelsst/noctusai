import { useParams, useNavigate } from "react-router-dom";
import { CalendarClock } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8011";
const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export default function SeedAcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="Imobi Scheduling"
      brandIcon={CalendarClock}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath={`${CORE_URL}/login`}
      onAccepted={() => navigate("/sso")}
    />
  );
}
