import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useState } from "react";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
}

export interface NavGroup {
  key: string;
  label: string;
  icon: React.ElementType;
  defaultOpen?: boolean;
  items: NavItem[];
}

interface SidebarProps {
  brandIcon: React.ElementType;
  brandTitle: string;
  brandSubtitle: string;
  navGroups: NavGroup[];
  standaloneItems?: NavItem[];
  onNavigate?: () => void;
}

export function Sidebar({
  brandIcon: BrandIcon,
  brandTitle,
  brandSubtitle,
  navGroups,
  standaloneItems = [],
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
    </NavLink>
  );

  return (
    <div className="w-full h-full bg-[hsl(var(--sidebar-background))] text-[hsl(var(--sidebar-foreground))] flex flex-col">
      <div className="p-4 sm:p-5">
        {/* Brand */}
        <div className="flex items-center gap-2 mb-5">
          <BrandIcon className="h-8 w-8 text-[hsl(var(--sidebar-primary-foreground))]" />
          <div>
            <h1 className="text-xl font-bold text-[hsl(var(--sidebar-primary-foreground))]">{brandTitle}</h1>
            <p className="text-[10px] text-[hsl(var(--sidebar-foreground))]/60 uppercase tracking-wider">
              {brandSubtitle}
            </p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="space-y-1">
          {navGroups.map((group) => {
            if (group.items.length === 0) return null;

            const isOpen = openGroups[group.key] ?? group.defaultOpen ?? false;

            return (
              <Collapsible
                key={group.key}
                open={isOpen}
                onOpenChange={() => toggleGroup(group.key)}
              >
                <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-2 text-xs font-semibold uppercase tracking-wider text-[hsl(var(--sidebar-foreground))]/50 hover:text-[hsl(var(--sidebar-foreground))] transition-colors rounded-md hover:bg-[hsl(var(--sidebar-accent))]/50">
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
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-0.5 mt-0.5 ml-2 border-l border-[hsl(var(--sidebar-border))] pl-2">
                  {group.items.map(renderNavLink)}
                </CollapsibleContent>
              </Collapsible>
            );
          })}

          {/* Standalone items */}
          {standaloneItems.length > 0 && (
            <div className="pt-2 border-t border-[hsl(var(--sidebar-border))] space-y-0.5">
              {standaloneItems.map(renderNavLink)}
            </div>
          )}
        </nav>
      </div>
    </div>
  );
}
