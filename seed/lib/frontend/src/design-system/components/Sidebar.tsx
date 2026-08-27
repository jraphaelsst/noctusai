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
 */
import { NavLink } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
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
  defaultOpen?: boolean;
  items: NavItem[];
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

  const initialOpenState: Record<string, boolean> = {};
  navGroups.forEach((g) => {
    initialOpenState[g.key] = g.defaultOpen ?? false;
  });

  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(initialOpenState);

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

            const isOpen = openGroups[group.key] ?? group.defaultOpen ?? false;

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
