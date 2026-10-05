/**
 * NoctusAI Global Sidebar Component
 *
 * Generic, prop-driven sidebar with collapsible navigation groups.
 * Products provide their own nav data — this component handles rendering.
 *
 * Dependencies: react-router-dom, lucide-react, @radix-ui/react-collapsible
 *
 * ## Icon-rail rendering (canonical default since 2026-08-27)
 *
 * `AppShell` publishes `SidebarRailState` through `useSidebarRail()`. When
 * `collapsed` is true the sidebar renders icon-only AT `md+` — every
 * collapsed-mode class in this file is `md:`-prefixed, so the mobile
 * off-canvas drawer is byte-for-byte the pre-rail rendering. Outside an
 * `AppShell` the context default is "not a rail", so a standalone `<Sidebar>`
 * is also unchanged.
 *
 * ### Collapse technique — `max-w` + `opacity`, never `display`
 *
 * Labels collapse via `md:max-w-0 md:opacity-0` on an `overflow-hidden` span,
 * NOT via `hidden` / `sr-only`. Three reasons:
 *   1. `max-width` is animatable, so labels slide+fade with the same 200ms
 *      `ease-in-out` the rail width uses — they never pop.
 *   2. An `opacity: 0` element stays in the accessibility tree, so the
 *      accessible name survives the collapse for screen readers. Every
 *      interactive row additionally carries an explicit `aria-label` (belt and
 *      braces) plus a `title` while collapsed, which doubles as the native
 *      icon tooltip a rail needs.
 *   3. Zero max-width removes the label's footprint, so `md:justify-center`
 *      (paired with `md:gap-0`) genuinely centres the icon in the 64px rail.
 *
 * ### Group headers while collapsed — flat icon rows, open-state UNTOUCHED
 *
 * DECISION: a collapsed group trigger degrades to a muted icon row (label +
 * chevron collapse to zero width) and the Radix `Collapsible` keeps whatever
 * open/closed state the user last chose. It is deliberately NOT force-closed
 * while collapsed.
 *
 * ARGUMENT: a rail must surface DESTINATIONS, not categories — force-closing
 * groups would empty the rail of the very icons it exists to show, and would
 * make the hover-expanded panel open onto a nav that looks empty, costing an
 * extra click on every navigation. Leaving the open-state alone means the rail
 * shows the same icon column the expanded panel shows, and expanding only
 * reveals the words next to icons that were already there.
 *
 * Consequence, accepted: a CLOSED group contributes only its own group icon to
 * the rail. Hovering reveals the label and the user opens it exactly as today.
 *
 * ## Collapsed-by-construction nav groups (2026-09-21)
 *
 * DECISION: every group starts CLOSED. There is no per-group opt-in that
 * defaults a group to open — a new entry appended to a product's
 * `navGroups` array is collapsed with zero extra code, by construction, and
 * stays that way even if the product author reaches for `defaultOpen: true`
 * (see below).
 *
 * Two things keep the user oriented despite everything starting closed:
 *   1. The group that CONTAINS the currently-active route auto-opens (see
 *      `findActiveGroupKey`) — landing on a page always shows its own group
 *      expanded, so the user can see where they are.
 *   2. Once a user opens/closes a group by hand, that choice is persisted to
 *      `localStorage` (read/write wrapped in try/catch — a disabled/private
 *      localStorage degrades to "nothing persists", never a crash) so it
 *      survives a reload.
 *
 * `NavGroup.defaultOpen` is now IGNORED by this component. It is kept in the
 * type only so the ~15 products that still set it (mostly `true`) keep
 * type-checking without a synchronized fleet-wide edit — every one of those
 * call sites is dead configuration now, not a live per-product override.
 * Removing the field outright is the correct long-term move (nothing should
 * read a field it doesn't honour); flagged as a scoped follow-up rather than
 * done here as a fan-out edit across every product's `NAV_GROUPS`.

 *
 * ## Nested groups, accordion, most-specific current page (2026-10-05)
 *
 * DECISION (owner-approved 2026-10-05): a `NavGroup` may hold `items` AND
 * `groups` (sub-groups), recursively, up to 4 LEVELS in total
 * (L1 group > L2 group > L3 group > L4 leaf). A flat group config (only
 * `items`) renders exactly as before. Items render before sub-groups.
 *
 * Open state is an ACCORDION PER LEVEL: among the sibling groups of one parent
 * only one is open; opening one closes its siblings; clicking the open
 * group's header closes it. State is `{ [parentKey | ""]: openChildKey | null }`.
 *
 * Navigation auto-opens EVERY group on the path to the current page (and so
 * closes their siblings). The effect is keyed on the path, so a manual close
 * is respected until the user navigates to a page in a different group.
 *
 * Current page: ONLY the most specific matching href is the current leaf
 * (longest href that equals the pathname or is a path-prefix of it), so a
 * parent route such as `/admin` no longer highlights with `/admin/vendas`.
 * The leaf carries `aria-current="page"`. The L1 group on the path gets an
 * active style, intermediate groups on the path get an emphasized label.
 *
 * Persisted open state lives under a PER-PRODUCT key
 * (`noctus.sidebar.openGroups.<storageKey>`); pass `storageKey` (the
 * framework passes a slug of the brand title).
 */
import { Link, NavLink, useLocation } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";

import { cn } from "../../utils";
import { useSidebarRail } from "./AppShell";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
  badge?: string | number;
}

export interface NavGroup {
  key: string;
  label: string;
  icon: React.ElementType;
  /**
   * @deprecated IGNORED as of 2026-09-21 — every group now starts closed by
   * construction (see the module docblock's "Collapsed-by-construction nav
   * groups" section). Kept only so existing product `navGroups` literals
   * that still set this keep type-checking; it has no runtime effect.
   */
  defaultOpen?: boolean;
  items: NavItem[];
  /**
   * Nested sub-groups (2026-10-05). A group may hold `items` and `groups`;
   * total depth is limited to 4 levels (L1 group > L2 group > L3 group >
   * L4 leaf). Group keys must be unique across the whole tree. A group holding only
   * sub-groups passes `items: []`.
   */
  groups?: NavGroup[];
}

/** Max number of GROUP levels (the 4th level is the leaf item). */
export const SIDEBAR_MAX_GROUP_DEPTH = 3;

/** Prefix of the localStorage key for persisted open-group state. */
const OPEN_GROUPS_STORAGE_PREFIX = "noctus.sidebar.openGroups";

/** Per-product storage key. */
export function sidebarStorageKey(storageKey?: string): string {
  return `${OPEN_GROUPS_STORAGE_PREFIX}.${storageKey || "default"}`;
}

/** Accordion state: parent group key ("" = root) -> key of its open child, or null (closed). */
type OpenState = Record<string, string | null>;

/** Best-effort read — a disabled/private localStorage yields "nothing persisted". */
function readPersistedOpenGroups(storageKey: string): OpenState {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const out: OpenState = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === "string" || v === null) out[k] = v as string | null;
    }
    return out;
  } catch {
    return {};
  }
}

/** Best-effort write — never throws (private mode / storage disabled / quota). */
function writePersistedOpenGroups(storageKey: string, state: OpenState): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(state));
  } catch {
    // localStorage unavailable — render/toggle correctly, just don't persist.
  }
}

/** Does `href` match `pathname` (equal or path-prefix)? */
function hrefMatches(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Does the group (recursively) hold at least one item? Empty groups are not rendered. */
function groupHasContent(group: NavGroup): boolean {
  return group.items.length > 0 || (group.groups ?? []).some(groupHasContent);
}

interface CurrentPage {
  /** The single most specific matching item (null when nothing matches). */
  item: NavItem | null;
  /** Group keys from L1 down to the group holding `item` (empty for standalone/no match). */
  path: string[];
}

/** Most specific match across every group level and the standalone items. */
function findCurrentPage(
  navGroups: NavGroup[],
  standaloneItems: NavItem[],
  pathname: string,
): CurrentPage {
  let best: CurrentPage = { item: null, path: [] };
  const consider = (item: NavItem, path: string[]) => {
    if (!hrefMatches(item.href, pathname)) return;
    if (!best.item || item.href.length > best.item.href.length) best = { item, path };
  };
  const walk = (groups: NavGroup[], path: string[]) => {
    for (const g of groups) {
      if (!groupHasContent(g)) continue;
      const here = [...path, g.key];
      g.items.forEach((item) => consider(item, here));
      walk(g.groups ?? [], here);
    }
  };
  walk(navGroups, []);
  standaloneItems.forEach((item) => consider(item, []));
  return best;
}

/** Open every group along `path` (closing their siblings). */
function openPath(state: OpenState, path: string[]): OpenState {
  const next = { ...state };
  path.forEach((key, i) => {
    next[i === 0 ? "" : path[i - 1]] = key;
  });
  return next;
}

export interface SidebarProps {
  brandIcon: React.ElementType;
  brandTitle: string;
  brandSubtitle: string;
  /**
   * When set, the brand (icon + title) becomes a navigable link to this
   * route — e.g. back to the dashboard. Omitted ⇒ the brand renders as a
   * plain, non-interactive header (backward-compatible default).
   */
  brandHref?: string;
  navGroups: NavGroup[];
  standaloneItems?: NavItem[];
  footerContent?: React.ReactNode;
  onNavigate?: () => void;
  /**
   * Namespace for the persisted open-group state (use the product slug), so
   * products never share open/closed choices. Omitted ⇒ a shared "default" key.
   */
  storageKey?: string;
}

/**
 * Shared transition for every collapsing text surface. `motion-reduce` opts
 * out entirely — a prefers-reduced-motion user gets an instant swap.
 */
const COLLAPSIBLE_TEXT = "transition-all duration-200 ease-in-out motion-reduce:transition-none";

/** Applied to a text surface while the desktop rail is collapsed. */
const COLLAPSED_TEXT = "md:max-w-0 md:opacity-0 md:overflow-hidden";

export function Sidebar({
  brandIcon: BrandIcon,
  brandTitle,
  brandSubtitle,
  brandHref,
  navGroups,
  standaloneItems = [],
  footerContent,
  onNavigate,
  storageKey,
}: SidebarProps) {
  // `collapsed` is only meaningful at md+ — see the module docblock. Below md
  // the same DOM is the off-canvas drawer and every `md:` class is inert.
  const { collapsed } = useSidebarRail();

  // The current page = the single most specific matching href (see the
  // module docblock). Its group path drives auto-open + the active marks.
  const { pathname } = useLocation();
  const current = useMemo(
    () => findCurrentPage(navGroups, standaloneItems, pathname),
    [navGroups, standaloneItems, pathname],
  );
  const pathKey = current.path.join("/");
  const storage = sidebarStorageKey(storageKey);

  // Lazy init: persisted choices, overlaid with the path to the current page.
  const [openState, setOpenState] = useState<OpenState>(() =>
    openPath(readPersistedOpenGroups(storage), current.path),
  );

  // Navigating opens every group on the path (closing their siblings). Keyed
  // on the path, so a manual close is respected until the user navigates to
  // a page in a different group.
  useEffect(() => {
    if (current.path.length === 0) return;
    setOpenState((prev) => openPath(prev, current.path));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on pathKey
  }, [pathKey]);

  // Persist every change (manual toggle or auto-open). Best-effort.
  useEffect(() => {
    writePersistedOpenGroups(storage, openState);
  }, [storage, openState]);

  // Accordion: opening a group closes its siblings; the open one closes itself.
  const toggleGroup = (parentKey: string, key: string) => {
    setOpenState((prev) => ({ ...prev, [parentKey]: prev[parentKey] === key ? null : key }));
  };

  const renderNavLink = (item: NavItem) => (
    <Link
      key={`${item.href}:${item.name}`}
      to={item.href}
      onClick={onNavigate}
      aria-label={item.name}
      aria-current={current.item === item ? "page" : undefined}
      title={collapsed ? item.name : undefined}
      className={cn(
        "flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        collapsed && "md:justify-center md:gap-0 md:px-0",
        current.item === item
          ? "bg-primary text-primary-foreground"
          : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent"
      )}
    >
      <item.icon className="h-4 w-4 shrink-0" />
      <span className={cn("flex-1 truncate", COLLAPSIBLE_TEXT, collapsed && COLLAPSED_TEXT)}>
        {item.name}
      </span>
      {item.badge != null && (
        <span
          className={cn(
            "ml-auto text-xs bg-primary/20 text-primary-foreground px-1.5 py-0.5 rounded-full",
            COLLAPSIBLE_TEXT,
            collapsed && "md:max-w-0 md:px-0 md:opacity-0 md:overflow-hidden"
          )}
        >
          {item.badge}
        </span>
      )}
    </Link>
  );

  // Recursive group renderer. `depth` 0 = L1. Radix Collapsible keeps the
  // header a <button> with aria-expanded.
  const renderGroup = (group: NavGroup, depth: number, parentKey: string): React.ReactNode => {
    if (!groupHasContent(group)) return null;
    if (depth > SIDEBAR_MAX_GROUP_DEPTH - 1) {
      console.error(
        `Sidebar: group "${group.key}" is nested deeper than ${SIDEBAR_MAX_GROUP_DEPTH} group levels (max 4 levels incl. the leaf).`,
      );
    }
    const isOpen = openState[parentKey] === group.key;
    const onPath = current.path[depth] === group.key;
    return (
      <CollapsiblePrimitive.Root
        key={group.key}
        open={isOpen}
        onOpenChange={() => toggleGroup(parentKey, group.key)}
      >
        <CollapsiblePrimitive.Trigger
          aria-label={group.label}
          data-active={onPath ? "true" : undefined}
          title={collapsed ? group.label : undefined}
          className={cn(
            "flex items-center justify-between w-full px-3 py-2 text-xs font-semibold tracking-wider transition-colors rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            depth === 0 ? "uppercase" : "normal-case tracking-normal",
            collapsed && "md:justify-center md:px-0",
            onPath && depth === 0
              ? "bg-sidebar-accent text-sidebar-foreground"
              : onPath
                ? "text-sidebar-foreground hover:bg-sidebar-accent/50"
                : "text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
          )}
        >
          <div className={cn("flex items-center gap-2 min-w-0", collapsed && "md:gap-0")}>
            <group.icon className="h-3.5 w-3.5 shrink-0" />
            <span className={cn("truncate", COLLAPSIBLE_TEXT, collapsed && COLLAPSED_TEXT)}>
              {group.label}
            </span>
          </div>
          <ChevronRight
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-transform duration-200 motion-reduce:transition-none",
              isOpen && "rotate-90",
              collapsed && "md:max-w-0 md:opacity-0 md:overflow-hidden"
            )}
          />
        </CollapsiblePrimitive.Trigger>
        {/* Collapsed: drop the indent rail so item icons stay in the
            single centred column the rail reads as. */}
        <CollapsiblePrimitive.Content
          className={cn(
            "space-y-0.5 mt-0.5 ml-2 border-l border-sidebar-border pl-2",
            collapsed && "md:ml-0 md:border-l-0 md:pl-0"
          )}
        >
          {group.items.map(renderNavLink)}
          {(group.groups ?? []).map((sub) => renderGroup(sub, depth + 1, group.key))}
        </CollapsiblePrimitive.Content>
      </CollapsiblePrimitive.Root>
    );
  };

  // Brand text block — collapses to zero width so the 32px brand icon centres
  // in the rail. Shared by both brand variants below.
  const brandText = (
    <div className={cn("min-w-0", COLLAPSIBLE_TEXT, collapsed && COLLAPSED_TEXT)}>
      <h1 className="text-xl font-bold text-sidebar-primary-foreground truncate">{brandTitle}</h1>
      <p className="text-[10px] text-sidebar-foreground/60 uppercase tracking-wider truncate">
        {brandSubtitle}
      </p>
    </div>
  );

  return (
    // `overflow-y-auto` is required now that AppShell pins the aside to the
    // viewport (`fixed inset-y-0`): a long nav must scroll INSIDE the rail
    // instead of being clipped away. `overflow-x-hidden` clips arbitrary
    // `footerContent` that is wider than the collapsed rail.
    <div className="w-full h-full bg-sidebar text-sidebar-foreground flex flex-col overflow-y-auto overflow-x-hidden">
      <div className={cn("p-4 sm:p-5 flex-1", collapsed && "md:px-2")}>
        {/* Brand — a link back to brandHref when provided, else a plain header */}
        {brandHref ? (
          <NavLink
            to={brandHref}
            onClick={onNavigate}
            aria-label={`${brandTitle} — início`}
            title={collapsed ? brandTitle : undefined}
            className={cn(
              "flex items-center gap-2 mb-5 rounded-md transition-opacity hover:opacity-80",
              collapsed && "md:justify-center md:gap-0"
            )}
          >
            <BrandIcon className="h-8 w-8 shrink-0 text-sidebar-primary-foreground" />
            {brandText}
          </NavLink>
        ) : (
          <div
            className={cn(
              "flex items-center gap-2 mb-5",
              collapsed && "md:justify-center md:gap-0"
            )}
          >
            <BrandIcon className="h-8 w-8 shrink-0 text-sidebar-primary-foreground" />
            {brandText}
          </div>
        )}

        {/* Navigation */}
        <nav className="space-y-1">
          {navGroups.map((group) => renderGroup(group, 0, ""))}

          {/* Standalone items */}
          {standaloneItems.length > 0 && (
            <div className="pt-2 border-t border-sidebar-border space-y-0.5">
              {standaloneItems.map(renderNavLink)}
            </div>
          )}
        </nav>
      </div>

      {/* Footer — arbitrary product content, so it is CLIPPED rather than
          restructured when collapsed (the rail cannot know its shape). */}
      {footerContent && (
        <div className={cn("p-4 border-t border-sidebar-border", collapsed && "md:px-2")}>
          {footerContent}
        </div>
      )}
    </div>
  );
}
