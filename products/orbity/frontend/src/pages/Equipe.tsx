import { api, useAuthStore } from "@noctusai/seed/infra";
import { StatusPaginaPanel, TeamPage, resolveSSOContext } from "@noctusai/lib";

// The canonical seed Equipe organ — roster, policy-driven invite and pending
// invitations. Removal is a NoctusAI Core action. Orbity extends it through the
// organ's declared `children` seam with the page-visibility (status_pagina)
// panel, shown to admins only.
// → seed/lib/frontend/src/components/team/TeamPage.tsx
export default function Equipe() {
  const user = useAuthStore((s) => s.user);
  const sso = resolveSSOContext(user?.user_metadata ?? undefined);
  const isAdmin = sso.isProductAdmin || sso.org.role === "owner" || sso.org.role === "admin";
  return (
    <TeamPage api={api} user={user}>
      {isAdmin && <StatusPaginaPanel api={api} enabled />}
    </TeamPage>
  );
}
