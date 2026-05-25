import { useParams, useNavigate } from "react-router-dom";
import { {{PRODUCT_ICON}} } from "lucide-react";
import { AcceptInvitePage } from "@noctusai/lib/design-system";
import { env } from "@noctusai/lib";

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:{{BACKEND_PORT}}";
// canonical seed resolver (env.CORE_URL) — no hand-rolled localhost:5173
const CORE_URL = env.CORE_URL;

export default function SeedAcceptInvite() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  return (
    <AcceptInvitePage
      productName="{{PRODUCT_NAME}}"
      brandIcon={{{PRODUCT_ICON}}}
      acceptEndpoint="/api/team/accept"
      apiBaseUrl={BACKEND_URL}
      token={token}
      loginPath={`${CORE_URL}/login`}
      onAccepted={() => navigate("/sso")}
    />
  );
}
