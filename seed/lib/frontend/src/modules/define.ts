/**
 * `defineModule` / `extendModule` — the FE half of a `ModuleSpec` (BE: `noctusai_seed.modules`).
 *
 * A module yields its sidebar group (key = a `ModuleGroupKey`), its routes and its page keys. `pageKey` is the
 * `status_pagina.nome_pagina` row AND the BE `PageSpec.key`; `moduleManifest()` (manifest.ts) emits the shared
 * page-key contract both sides compare.
 *
 * A market adds/overrides items through `extendModule` (declared, never a copied module).
 */
import type { ComponentType, ElementType } from 'react';
import { MODULE_GROUP_LABELS, MODULE_GROUP_ORDER, type ModuleGroupKey } from '../design-system/components/nav-groups';
import type { NavGroupWithRoute, NavItemWithRoute } from '../page-status';

export type ModulePageStatus = 'producao' | 'desenvolvimento' | 'desativado';

export interface ModuleItem {
  label: string;
  /** Absolute path. New module pages take the `/crm|/erp|/cms/...` prefix; existing URLs never move. */
  path: string;
  /** `status_pagina.nome_pagina` and the BE `PageSpec.key`. */
  pageKey: string;
  icon?: ElementType;
  /** The page component (typically `lazy(() => import(...))`). Omit for a nav-only item. */
  element?: ComponentType<any>;
  /** Org roles that may see this item/route (UX only — the server enforces). Omitted = every role. */
  roles?: readonly string[];
  /** Default `status_pagina.status` (the BE `PageSpec.status`). */
  status?: ModulePageStatus;
  badge?: string;
  /** Sub-items render as a nested sidebar group; each is a page of this module too. */
  children?: readonly ModuleItem[];
}

export interface ModuleDefinition {
  key: ModuleGroupKey;
  /** Per-org enablement key (BE `ModuleSpec.license_key`); defaults to `key`. */
  enablementKey: string;
  label: string;
  icon?: ElementType;
  items: readonly ModuleItem[];
}

export interface ModuleRoute {
  path: string;
  pageKey: string;
  moduleKey: ModuleGroupKey;
  Component: ComponentType<any>;
  roles?: readonly string[];
}

export interface DefinedModule {
  readonly definition: ModuleDefinition;
  readonly key: ModuleGroupKey;
  readonly enablementKey: string;
  /** The module's sidebar group, `route` = `pageKey` so `filterNavByPageStatus` gates it by `status_pagina`. */
  readonly navGroup: NavGroupWithRoute;
  readonly routes: readonly ModuleRoute[];
  /** Every page key, depth-first. */
  readonly pageKeys: readonly string[];
  /** Flat `[item, depth]`-free page list (children flattened) — the manifest and role filters read it. */
  readonly pages: readonly ModuleItem[];
}

export interface DefineModuleInput {
  key: ModuleGroupKey;
  enablementKey?: string;
  label?: string;
  icon?: ElementType;
  items: readonly ModuleItem[];
}

function flatten(items: readonly ModuleItem[]): ModuleItem[] {
  return items.flatMap((i) => [i, ...flatten(i.children ?? [])]);
}

function navItem(item: ModuleItem): NavItemWithRoute & { roles?: readonly string[] } {
  return { name: item.label, href: item.path, icon: item.icon, route: item.pageKey, badge: item.badge, roles: item.roles };
}

function toGroup(moduleKey: string, items: readonly ModuleItem[]): { items: NavItemWithRoute[]; groups: NavGroupWithRoute[] } {
  const leaves: NavItemWithRoute[] = [];
  const groups: NavGroupWithRoute[] = [];
  for (const item of items) {
    if (item.children?.length) {
      const sub = toGroup(moduleKey, item.children);
      groups.push({ key: `${moduleKey}:${item.pageKey}`, label: item.label, icon: item.icon, items: sub.items, groups: sub.groups.length ? sub.groups : undefined });
    } else {
      leaves.push(navItem(item));
    }
  }
  return { items: leaves, groups };
}

export function defineModule(input: DefineModuleInput): DefinedModule {
  if (!MODULE_GROUP_ORDER.includes(input.key)) {
    throw new Error(`defineModule: "${input.key}" is not a canonical module-group key (${MODULE_GROUP_ORDER.join(', ')})`);
  }
  const pages = flatten(input.items);
  const seenKeys = new Set<string>();
  const seenPaths = new Set<string>();
  for (const p of pages) {
    if (!p.path.startsWith('/')) throw new Error(`defineModule(${input.key}): path of "${p.pageKey}" must start with "/"`);
    if (seenKeys.has(p.pageKey)) throw new Error(`defineModule(${input.key}): duplicate pageKey "${p.pageKey}"`);
    if (seenPaths.has(p.path)) throw new Error(`defineModule(${input.key}): duplicate path "${p.path}"`);
    seenKeys.add(p.pageKey);
    seenPaths.add(p.path);
  }
  const { items, groups } = toGroup(input.key, input.items);
  const navGroup: NavGroupWithRoute = {
    key: input.key,
    label: input.label ?? MODULE_GROUP_LABELS[input.key],
    icon: input.icon,
    items,
    groups: groups.length ? groups : undefined,
  };
  const routes: ModuleRoute[] = pages
    .filter((p) => p.element)
    .map((p) => ({ path: p.path, pageKey: p.pageKey, moduleKey: input.key, Component: p.element!, roles: p.roles }));
  const definition: ModuleDefinition = {
    key: input.key,
    enablementKey: input.enablementKey ?? input.key,
    label: navGroup.label,
    icon: input.icon,
    items: input.items,
  };
  return Object.freeze({
    definition,
    key: input.key,
    enablementKey: definition.enablementKey,
    navGroup,
    routes,
    pageKeys: pages.map((p) => p.pageKey),
    pages,
  });
}

export interface ExtendModuleInput {
  /** Items appended (or inserted after `insertAfter`, a pageKey of the base). */
  items?: readonly ModuleItem[];
  insertAfter?: string;
  /** Per-pageKey field overrides; `pageKey` itself can never change (it is the BE contract). */
  override?: Readonly<Record<string, Partial<Omit<ModuleItem, 'pageKey' | 'children'>>>>;
  /** Page keys removed from the module (their routes disappear with them). */
  remove?: readonly string[];
  label?: string;
  icon?: ElementType;
}

function mapItems(items: readonly ModuleItem[], fn: (i: ModuleItem) => ModuleItem | null): ModuleItem[] {
  return items.flatMap((i) => {
    const next = fn(i);
    if (!next) return [];
    return [{ ...next, children: next.children ? mapItems(next.children, fn) : undefined }];
  });
}

/** A market's declared adjustment of a seed module; the base is never mutated or copied by hand. */
export function extendModule(base: DefinedModule, ext: ExtendModuleInput): DefinedModule {
  const known = new Set(base.pageKeys);
  for (const k of [...Object.keys(ext.override ?? {}), ...(ext.remove ?? [])]) {
    if (!known.has(k)) throw new Error(`extendModule(${base.key}): unknown pageKey "${k}"`);
  }
  if (ext.insertAfter && !base.definition.items.some((i) => i.pageKey === ext.insertAfter)) {
    throw new Error(`extendModule(${base.key}): insertAfter "${ext.insertAfter}" is not a top-level item`);
  }
  const removed = new Set(ext.remove ?? []);
  let items = mapItems(base.definition.items, (i) =>
    removed.has(i.pageKey) ? null : { ...i, ...(ext.override?.[i.pageKey] ?? {}) },
  );
  const added = ext.items ?? [];
  if (added.length) {
    if (ext.insertAfter) {
      const at = items.findIndex((i) => i.pageKey === ext.insertAfter);
      items = [...items.slice(0, at + 1), ...added, ...items.slice(at + 1)];
    } else {
      items = [...items, ...added];
    }
  }
  return defineModule({
    key: base.key,
    enablementKey: base.enablementKey,
    label: ext.label ?? base.definition.label,
    icon: ext.icon ?? base.definition.icon,
    items,
  });
}
