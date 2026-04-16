/**
 * Shared page status system for dev-gated page visibility.
 *
 * Each product schema has a `status_pagina` table with route-level
 * visibility flags.  This module provides hooks and utilities to
 * filter navigation based on page status and user role.
 *
 * Status values:
 * - `producao`        → visible to all users
 * - `desenvolvimento` → visible ONLY to dev + owner roles
 * - `desativado`      → hidden from everyone
 */
import { useQuery } from '@tanstack/react-query';
import { isDevOrOwner } from './roles';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { from: any };

export interface StatusPagina {
  id: string;
  nome_pagina: string;
  status: 'producao' | 'desenvolvimento' | 'desativado';
  descricao?: string | null;
}

export interface NavItemWithRoute {
  name: string;
  href: string;
  icon?: any;
  route: string;
  badge?: string;
}

export interface NavGroupWithRoute {
  key: string;
  label: string;
  icon?: any;
  defaultOpen?: boolean;
  items: NavItemWithRoute[];
}

/**
 * TanStack Query hook to fetch page status from the product's schema.
 *
 * @param supabase - The product's Supabase client (schema-targeted)
 * @param enabled - Whether the query should run (default: true)
 */
export function usePageStatus(supabase: AnySupabaseClient, enabled = true) {
  return useQuery<StatusPagina[]>({
    queryKey: ['status-paginas'],
    queryFn: async () => {
      const { data } = await supabase.from('status_pagina').select('*');
      return (data || []) as StatusPagina[];
    },
    staleTime: 10 * 60 * 1000, // 10 min — status changes rarely
    enabled,
  });
}

/**
 * Check if a page route is visible to the current user.
 *
 * @param route - The route key (matches `status_pagina.nome_pagina`)
 * @param statusPaginas - Array of status records
 * @param orgRole - The user's org_role (from SSO context or product role)
 */
export function isPageVisible(
  route: string,
  statusPaginas: StatusPagina[],
  orgRole: string | null | undefined,
): boolean {
  const page = statusPaginas.find((p) => p.nome_pagina === route);
  if (!page) return false; // unlisted pages are hidden
  if (page.status === 'desativado') return false;
  if (page.status === 'desenvolvimento') return isDevOrOwner(orgRole);
  return true; // producao
}

/**
 * Filter nav groups by page status visibility.
 *
 * Removes items whose routes are not visible, and removes empty groups.
 * Adds "DEV" badge to desenvolvimento pages for dev/owner users.
 */
export function filterNavByPageStatus<
  G extends { key: string; label: string; icon?: any; defaultOpen?: boolean; items: T[] },
  T extends { name: string; href: string; icon?: any; route: string; badge?: string },
>(
  groups: G[],
  statusPaginas: StatusPagina[],
  orgRole: string | null | undefined,
): Array<Omit<G, 'items'> & { items: Array<Omit<T, 'route'> & { badge?: string }> }> {
  const devUser = isDevOrOwner(orgRole);

  return groups
    .map((group) => ({
      ...group,
      items: group.items
        .filter((item) => isPageVisible(item.route, statusPaginas, orgRole))
        .map((item) => {
          const page = statusPaginas.find((p) => p.nome_pagina === item.route);
          const badge = devUser && page?.status === 'desenvolvimento' ? 'DEV' : item.badge;
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { route: _route, ...rest } = item;
          return { ...rest, badge };
        }),
    }))
    .filter((group) => group.items.length > 0);
}
