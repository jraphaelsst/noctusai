/**
 * The ONE access rule for the platform admin surface.
 *
 * `canReach(role, href)` is consumed by BOTH the route registration (`AdminApp`)
 * and the nav pruning (`pruneNavGroups`), so the sidebar can never list a page
 * the route gate would refuse (the old `visibleNavGroups` filtered by group KEY,
 * a second hand-kept list beside the path gate).
 *
 * `role` is the PLATFORM role from `/api/auth/me` (`noctus_users.role`, the same
 * value the backend `platform_admin_required` dependency reads). An org or
 * product admin is a different actor and never reaches this surface.
 *
 * This module lives in the code-split admin chunk: nothing here ships to a user
 * who is not a platform admin / marketing.
 */
import type { NavGroup, NavItem } from '@noctusai/lib/design-system';

export type AdminRole = 'admin' | 'marketing';

/** `marketing` reaches the website admin ONLY (contract `15-api-contract.md` §6). */
const MARKETING_PREFIX = '/admin/website';

export function canReach(role: AdminRole | undefined, href: string): boolean {
  if (role === 'admin') return true;
  if (role === 'marketing') return href === MARKETING_PREFIX || href.startsWith(`${MARKETING_PREFIX}/`);
  return false;
}

/** Drop every item the role cannot reach, then every group left empty. Pure; never mutates. */
// NOC-REMEDIATE[seed-prune-nav-groups]: promote to the seed Sidebar organ once Social Wiring needs role-pruned groups — 2026-11-08
export function pruneNavGroups(groups: NavGroup[], role: AdminRole | undefined): NavGroup[] {
  const out: NavGroup[] = [];
  for (const group of groups) {
    const items = group.items.filter((item) => canReach(role, item.href));
    const subgroups = pruneNavGroups(group.groups ?? [], role);
    if (items.length === 0 && subgroups.length === 0) continue;
    out.push({ ...group, items, ...(group.groups ? { groups: subgroups } : {}) });
  }
  return out;
}

export function pruneNavItems(items: NavItem[], role: AdminRole | undefined): NavItem[] {
  return items.filter((item) => canReach(role, item.href));
}
