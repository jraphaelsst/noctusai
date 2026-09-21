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
 */
import { NavLink, useLocation } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
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
}

/** localStorage key for persisted per-group expand/collapse choices. */
const OPEN_GROUPS_STORAGE_KEY = "noctus.sidebar.openGroups";

/** Best-effort read — a disabled/private localStorage yields "nothing persisted". */
function readPersistedOpenGroups(): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(OPEN_GROUPS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

/** Best-effort write — never throws (private mode / storage disabled / quota). */
function writePersistedOpenGroups(state: Record<string, boolean>): void {
  try {
    window.localStorage.setItem(OPEN_GROUPS_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage unavailable — render/toggle correctly, just don't persist.
  }
}

/** Is `href` the currently active route? Mirrors `NavLink`'s own `end`-less matching. */
function isItemActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Which group (if any) contains the currently active route — auto-expand target. */
function findActiveGroupKey(navGroups: NavGroup[], pathname: string): string | null {
  const group = navGroups.find((g) => g.items.some((item) => isItemActive(item.href, pathname)));
  return group ? group.key : null;
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
}: SidebarProps) {
  // `collapsed` is only meaningful at md+ — see the module docblock. Below md
  // the same DOM is the off-canvas drawer and every `md:` class is inert.
  const { collapsed } = useSidebarRail();

  // Which group holds the current route — the one exception to "starts
  // closed" (see the module docblock's "Collapsed-by-construction" section).
  const { pathname } = useLocation();
  const activeGroupKey = findActiveGroupKey(navGroups, pathname);

  // Lazy init: every group starts closed UNLESS a prior visit persisted a
  // choice for it, or it holds the active route on this very first render.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    const persisted = readPersistedOpenGroups();
    if (activeGroupKey && persisted[activeGroupKey] === undefined) {
      return { ...persisted, [activeGroupKey]: true };
    }
    return persisted;
  });

  // Navigating into a different group's route auto-opens that group without
  // touching any other group's state — a manual close of the CURRENT active
  // group is respected (this effect only re-fires when `activeGroupKey`
  // itself changes, i.e. on navigation, not on every render).
  useEffect(() => {
    if (!activeGroupKey) return;
    setOpenGroups((prev) => (prev[activeGroupKey] ? prev : { ...prev, [activeGroupKey]: true }));
  }, [activeGroupKey]);

  // Persist every change (manual toggle or the auto-open above) so choices
  // survive a reload. Best-effort — see `writePersistedOpenGroups`.
  useEffect(() => {
    writePersistedOpenGroups(openGroups);
  }, [openGroups]);

  const toggleGroup = (key: string) => {
    setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderNavLink = (item: NavItem) => (
    <NavLink
      key={item.name}
      to={item.href}
      onClick={onNavigate}
      aria-label={item.name}
      title={collapsed ? item.name : undefined}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
          collapsed && "md:justify-center md:gap-0 md:px-0",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent"
        )
      }
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
    </NavLink>
  );

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
          {navGroups.map((group) => {
            if (group.items.length === 0) return null;

            // `defaultOpen` is deliberately NOT consulted here — see the
            // "Collapsed-by-construction" module docblock section.
            const isOpen = openGroups[group.key] ?? false;

            return (
              <CollapsiblePrimitive.Root
                key={group.key}
                open={isOpen}
                onOpenChange={() => toggleGroup(group.key)}
              >
                <CollapsiblePrimitive.Trigger
                  aria-label={group.label}
                  title={collapsed ? group.label : undefined}
                  className={cn(
                    "flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors rounded-md hover:bg-sidebar-accent/50",
                    collapsed && "md:justify-center md:px-0"
                  )}
                >
                  <div className={cn("flex items-center gap-2 min-w-0", collapsed && "md:gap-0")}>
                    <group.icon className="h-3.5 w-3.5 shrink-0" />
                    <span
                      className={cn("truncate", COLLAPSIBLE_TEXT, collapsed && COLLAPSED_TEXT)}
                    >
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
                </CollapsiblePrimitive.Content>
              </CollapsiblePrimitive.Root>
            );
          })}

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
