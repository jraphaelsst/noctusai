/**
 * RoleLayout — role routing for the one app that serves both the back
 * office and the member portal (ninho-vazio CONTRACT.md §Frontend).
 *
 * Seam: `createProductApp({ Layout })` — the seed's declared Layout slot
 * (any `ComponentType<{children}>`). This wrapper resolves the role from
 * `GET /api/eu` and hands the route content to one of two
 * `createProductLayout` instances:
 *
 * - `membro` → `Membro` layout (portal nav only). Any path outside the
 *   member area redirects to `/portal` BEFORE the staff page mounts, so a
 *   staff page never renders (nor fires its staff-only queries) for a member.
 * - `admin` / `moderador` → `Staff` layout, nav unchanged. Portal paths
 *   redirect to `/` (the portal API is member-only server-side).
 *
 * Why not the seed's `roleRoutes` + `resolveRole`: `resolveRole(user)` is
 * synchronous over auth metadata, while this product's role lives in
 * `noctus_users.org_role` and reaches the FE only through `GET /api/eu`
 * (async); and the staff home is `/`, which `roleRoutes`' root redirect
 * would bounce to itself. Surfaced as a seed scoped-improvement.
 *
 * Fail closed: while `/api/eu` is pending the page skeleton shows; if it
 * fails with no cached answer, neither layout renders — an error with retry
 * and sign-out instead of guessing a role.
 */
import type { ComponentType, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Button, PageSkeleton } from "@noctusai/lib/design-system";
import { supabase } from "@noctusai/seed/infra";

import { useEu, isMembro } from "@/hooks/useEu";
import { errorMessage } from "@/lib/errors";

export const PORTAL_HOME = "/portal";

/** Paths a member may reach: the portal plus the seed-mounted `/settings/*`
 * (personal AI-consent settings every authenticated user owns). */
const MEMBER_PATH_PREFIXES = [PORTAL_HOME, "/settings"];

function underPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function isMemberPath(pathname: string): boolean {
  return MEMBER_PATH_PREFIXES.some((prefix) => underPrefix(pathname, prefix));
}

type LayoutComponent = ComponentType<{ children: ReactNode }>;

export interface RoleLayoutConfig {
  Staff: LayoutComponent;
  Membro: LayoutComponent;
}

function EuIndisponivel({ message, onRetry, retrying }: { message: string; onRetry: () => void; retrying: boolean }) {
  async function sair() {
    try {
      await supabase.auth.signOut();
    } finally {
      window.location.assign("/");
    }
  }
  return (
    <div role="alert" className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-lg font-medium text-foreground">Não conseguimos carregar sua conta.</p>
      <p className="max-w-md text-base text-muted-foreground">{message}</p>
      <div className="flex flex-wrap justify-center gap-3">
        <Button variant="primary" className="h-11 px-6 text-base" onClick={onRetry} disabled={retrying}>
          {retrying ? "Tentando…" : "Tentar novamente"}
        </Button>
        <Button variant="outline" className="h-11 px-6 text-base" onClick={sair}>
          Sair
        </Button>
      </div>
    </div>
  );
}

export function createRoleLayout({ Staff, Membro }: RoleLayoutConfig) {
  function RoleLayout({ children }: { children: ReactNode }) {
    const { pathname } = useLocation();
    const { data, isPending, isFetching, error, refetch } = useEu();
    const showSkeleton = isPending && !data;

    if (showSkeleton) return <PageSkeleton />;
    if (!data) {
      return <EuIndisponivel message={errorMessage(error)} onRetry={() => refetch()} retrying={isFetching} />;
    }

    if (isMembro(data)) {
      if (!isMemberPath(pathname)) return <Navigate to={PORTAL_HOME} replace />;
      return <Membro>{children}</Membro>;
    }

    if (underPrefix(pathname, PORTAL_HOME)) return <Navigate to="/" replace />;
    return <Staff>{children}</Staff>;
  }
  return RoleLayout;
}
