/**
 * NoctusAI Global Sidebar Component
 *
 * Generic, prop-driven sidebar with collapsible navigation groups.
 * Products provide their own nav data — this component handles rendering.
 *
 * Dependencies: react-router-dom, lucide-react, @radix-ui/react-collapsible
 */
import { NavLink } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";

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

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

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
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent"
        )
      }
    >
      <item.icon className="h-4 w-4 shrink-0" />
      <span className="flex-1 truncate">{item.name}</span>
      {item.badge != null && (
        <span className="ml-auto text-xs bg-primary/20 text-primary-foreground px-1.5 py-0.5 rounded-full">
          {item.badge}
        </span>
      )}
    </NavLink>
  );

  return (
    <div className="w-full h-full bg-sidebar text-sidebar-foreground flex flex-col">
      <div className="p-4 sm:p-5 flex-1">
        {/* Brand — a link back to brandHref when provided, else a plain header */}
        {brandHref ? (
          <NavLink
            to={brandHref}
            onClick={onNavigate}
            aria-label={`${brandTitle} — início`}
            className="flex items-center gap-2 mb-5 rounded-md transition-opacity hover:opacity-80"
          >
            <BrandIcon className="h-8 w-8 text-sidebar-primary-foreground" />
            <div>
              <h1 className="text-xl font-bold text-sidebar-primary-foreground">{brandTitle}</h1>
              <p className="text-[10px] text-sidebar-foreground/60 uppercase tracking-wider">
                {brandSubtitle}
              </p>
            </div>
          </NavLink>
        ) : (
          <div className="flex items-center gap-2 mb-5">
            <BrandIcon className="h-8 w-8 text-sidebar-primary-foreground" />
            <div>
              <h1 className="text-xl font-bold text-sidebar-primary-foreground">{brandTitle}</h1>
              <p className="text-[10px] text-sidebar-foreground/60 uppercase tracking-wider">
                {brandSubtitle}
              </p>
            </div>
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
                <CollapsiblePrimitive.Trigger className="flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/50 hover:text-sidebar-foreground transition-colors rounded-md hover:bg-sidebar-accent/50">
                  <div className="flex items-center gap-2">
                    <group.icon className="h-3.5 w-3.5" />
                    <span>{group.label}</span>
                  </div>
                  <ChevronRight
                    className={cn(
                      "h-3.5 w-3.5 transition-transform duration-200",
                      isOpen && "rotate-90"
                    )}
                  />
                </CollapsiblePrimitive.Trigger>
                <CollapsiblePrimitive.Content className="space-y-0.5 mt-0.5 ml-2 border-l border-sidebar-border pl-2">
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

      {/* Footer */}
      {footerContent && (
        <div className="p-4 border-t border-sidebar-border">
          {footerContent}
        </div>
      )}
    </div>
  );
}
