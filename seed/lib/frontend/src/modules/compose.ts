/**
 * `composeModules` — merge modules + a product's local groups into the sidebar + routes, honouring per-org enablement.
 *
 * A module disabled for the org is NOT RENDERED: its nav group and routes are absent from the result (not hidden,
 * not disabled), so no page of it can mount. While enablement is unknown (`enabledKeys == null`, still loading) NO
 * module renders and `pending` is true — the host shows its loader instead of a wrong sidebar or a 404 deep link.
 */
import { orderNavGroups } from '../design-system/components/nav-groups';
import type { NavGroupWithRoute } from '../page-status';
import type { DefinedModule, ModuleRoute } from './define';

export interface ComposeModulesInput {
  modules: readonly DefinedModule[];
  /** The product's own groups (non-module nav: settings, local pages). Always rendered. */
  localGroups?: readonly NavGroupWithRoute[];
  /** `enablement keys` the org has (from `useEnabledModules`); `null`/`undefined` = not known yet. */
  enabledKeys: ReadonlySet<string> | null | undefined;
  /** When set, items/routes whose `roles` exclude it are dropped. Omit while the role is unknown. */
  orgRole?: string | null;
}

export interface ComposedModules {
  /** Canonical order (`orderNavGroups`): module groups by `MODULE_GROUP_ORDER`, unknown local keys after. */
  navGroups: NavGroupWithRoute[];
  routes: ModuleRoute[];
  /** Page keys of the RENDERED modules (what must have `status_pagina` rows). */
  pageKeys: string[];
  /** Enablement still unknown: render a loader. */
  pending: boolean;
  /** Module keys not rendered because the org does not have them. */
  hiddenModules: string[];
}

function pruneByRole(group: NavGroupWithRoute, role: string): NavGroupWithRoute | null {
  const items = group.items.filter((i) => {
    const roles = (i as { roles?: readonly string[] }).roles;
    return !roles || roles.includes(role);
  });
  const groups = (group.groups ?? []).map((g) => pruneByRole(g, role)).filter((g): g is NavGroupWithRoute => g !== null);
  if (!items.length && !groups.length) return null;
  return { ...group, items, groups: groups.length ? groups : undefined };
}

export function composeModules(input: ComposeModulesInput): ComposedModules {
  const { modules, enabledKeys, orgRole } = input;
  const seen = new Map<string, string>();
  for (const m of modules) {
    for (const k of m.pageKeys) {
      const owner = seen.get(k);
      if (owner && owner !== m.key) throw new Error(`composeModules: pageKey "${k}" is in modules "${owner}" and "${m.key}"; a page lives in one module`);
      seen.set(k, m.key);
    }
  }
  const local = [...(input.localGroups ?? [])];
  const moduleKeys = new Set(modules.map((m) => m.key));
  for (const g of local) {
    if (moduleKeys.has(g.key as never)) throw new Error(`composeModules: local group "${g.key}" collides with a module; use extendModule`);
  }
  const pending = enabledKeys == null;
  const rendered = pending ? [] : modules.filter((m) => enabledKeys.has(m.enablementKey));
  const hiddenModules = pending ? [] : modules.filter((m) => !enabledKeys.has(m.enablementKey)).map((m) => m.key);
  const groups: NavGroupWithRoute[] = [];
  const routes: ModuleRoute[] = [];
  for (const m of rendered) {
    const g = orgRole ? pruneByRole(m.navGroup, orgRole) : m.navGroup;
    if (g) groups.push(g);
    routes.push(...m.routes.filter((r) => !orgRole || !r.roles || r.roles.includes(orgRole)));
  }
  return {
    navGroups: orderNavGroups([...groups, ...local]),
    routes,
    pageKeys: rendered.flatMap((m) => [...m.pageKeys]),
    pending,
    hiddenModules,
  };
}
