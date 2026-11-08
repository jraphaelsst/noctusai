/**
 * Breadcrumb trail derivation (pure) for the seed `Breadcrumbs` organ.
 *
 * The trail is DERIVED, never hand-maintained: the nav registry that already
 * drives the sidebar (groups -> items -> hrefs) names the ancestors, and the
 * router's current match supplies the deeper (detail-route) crumbs.
 *
 *   /admin/products          -> Administração / Comercial / Produtos
 *   /clientes/42 (detail)    -> Clientes (link) / <handle.crumb>   (never "42")
 *   /unknown/deep/path       -> nearest known ancestor, else "Início"
 */
import type { NavGroup, NavItem } from "./Sidebar";

export type CrumbMenuEntry =
  | { kind: "heading"; label: string }
  | { kind: "item"; label: string; href: string };

export interface Crumb {
  key: string;
  label: string;
  /** Present on route crumbs that are NOT the current page. */
  href?: string;
  /** Present on group crumbs: the pages of that group, for sideways jumps. */
  menu?: CrumbMenuEntry[];
  /** True only on the last crumb (the current page). */
  current?: boolean;
}

/** Context handed to a crumb function (route-spec or `handle.crumb`). */
export interface CrumbContext {
  params: Record<string, string | undefined>;
  pathname: string;
  /** Loader data of the matched route (data routers only). */
  data?: unknown;
}

export type CrumbResolver = string | ((ctx: CrumbContext) => string | null | undefined);

/** Declarative detail-route crumb for apps on a non-data router. */
export interface RouteCrumbSpec {
  /** react-router path pattern, e.g. "/clientes/:id". */
  path: string;
  crumb: CrumbResolver;
}

/** A crumb already resolved from the router (e.g. `handle.crumb`). */
export interface ResolvedRouteCrumb {
  pathname: string;
  label: string | null | undefined;
}

export const BREADCRUMB_ROOT_LABEL = "Início";
export const BREADCRUMB_DETAIL_FALLBACK = "Detalhes";

export function resolveCrumb(resolver: CrumbResolver, ctx: CrumbContext): string {
  const label = typeof resolver === "function" ? resolver(ctx) : resolver;
  // Never surface a raw id: an unresolved crumb is a generic word.
  return label && label.trim() ? label : BREADCRUMB_DETAIL_FALLBACK;
}

function normalize(p: string): string {
  const q = p.split(/[?#]/)[0] ?? "";
  return q.length > 1 ? q.replace(/\/+$/, "") : q || "/";
}

function covers(href: string, pathname: string): boolean {
  const h = normalize(href);
  if (h === pathname) return true;
  return h !== "/" && pathname.startsWith(h + "/");
}

function menuFor(group: NavGroup): CrumbMenuEntry[] {
  const out: CrumbMenuEntry[] = group.items.map((i) => ({ kind: "item", label: i.name, href: i.href }));
  for (const sub of group.groups ?? []) {
    const inner = menuFor(sub);
    if (inner.length) out.push({ kind: "heading", label: sub.label }, ...inner);
  }
  return out;
}

interface Hit {
  chain: NavGroup[];
  item: NavItem;
}

function findBest(groups: NavGroup[], pathname: string, chain: NavGroup[] = []): Hit | null {
  let best: Hit | null = null;
  const consider = (h: Hit) => {
    if (!best || normalize(h.item.href).length > normalize(best.item.href).length) best = h;
  };
  for (const g of groups) {
    for (const item of g.items) if (covers(item.href, pathname)) consider({ chain: [...chain, g], item });
    const inner = g.groups ? findBest(g.groups, pathname, [...chain, g]) : null;
    if (inner) consider(inner);
  }
  return best;
}

export interface BuildTrailInput {
  navGroups: NavGroup[];
  standaloneItems?: NavItem[];
  pathname: string;
  /** Crumbs resolved by the router (`handle.crumb` / route specs), any depth. */
  routeCrumbs?: ResolvedRouteCrumb[];
}

export function buildBreadcrumbTrail(input: BuildTrailInput): Crumb[] {
  const pathname = normalize(input.pathname);
  let hit = findBest(input.navGroups, pathname);
  const bestStandalone = (input.standaloneItems ?? [])
    .filter((i) => covers(i.href, pathname))
    .sort((a, b) => normalize(b.href).length - normalize(a.href).length)[0];
  if (bestStandalone && (!hit || normalize(bestStandalone.href).length > normalize(hit.item.href).length)) {
    hit = { chain: [], item: bestStandalone };
  }

  const itemPath = hit ? normalize(hit.item.href) : "";
  const extras = (input.routeCrumbs ?? [])
    .map((c) => ({
      pathname: normalize(c.pathname),
      label: c.label && c.label.trim() ? c.label : BREADCRUMB_DETAIL_FALLBACK,
    }))
    // With a nav hit only STRICTLY deeper routes add crumbs (the page itself is named by the nav).
    .filter((c) => (hit ? c.pathname !== itemPath && covers(itemPath, c.pathname) : true))
    .sort((a, b) => a.pathname.length - b.pathname.length)
    .filter((c, i, arr) => i === 0 || arr[i - 1]!.pathname !== c.pathname);

  const trail: Crumb[] = [];
  if (hit) {
    for (const g of hit.chain) trail.push({ key: `group:${g.key}`, label: g.label, menu: menuFor(g) });
    trail.push({ key: `item:${hit.item.href}`, label: hit.item.name, href: hit.item.href });
  }
  for (const e of extras) trail.push({ key: `route:${e.pathname}`, label: e.label, href: e.pathname });

  if (trail.length === 0) trail.push({ key: "root", label: BREADCRUMB_ROOT_LABEL });
  const last = trail[trail.length - 1]!;
  last.current = true;
  delete last.href;
  return trail;
}
