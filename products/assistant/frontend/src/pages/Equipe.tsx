import { api, useAuthStore } from "@noctusai/seed/infra";
import { TeamPage } from "@noctusai/lib";

// The canonical seed Equipe organ — roster, policy-driven invite (roles from
// GET /api/team/policy) and pending invitations. Removal is a NoctusAI Core
// action. → seed/lib/frontend/src/components/team/TeamPage.tsx
export default function Equipe() {
  return <TeamPage api={api} user={useAuthStore((s) => s.user)} />;
}
