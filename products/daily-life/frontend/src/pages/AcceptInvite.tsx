import { useParams, useNavigate } from "react-router-dom";
import { CalendarCheck } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8005";
const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

export default function DailyLifeAcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="Daily Life"
      brandIcon={CalendarCheck}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath={`${CORE_URL}/login`}
      onAccepted={() => navigate("/sso")}
    />
  );
}
