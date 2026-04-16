/**
 * NoctusAI Global App Shell
 *
 * Unified layout: dark sidebar + light content area.
 * Handles responsive sidebar (off-canvas on mobile, static on desktop).
 *
 * Products wrap their routes in this shell and provide sidebar/header content.
 */
import { useState, useCallback } from "react";

export interface AppShellProps {
  /** The sidebar content (typically a <Sidebar> component) */
  sidebar: React.ReactNode;
  /** The header content (typically a <Header> component receiving onMenuToggle) */
  header: (props: { onMenuToggle: () => void }) => React.ReactNode;
  /** Page content */
  children: React.ReactNode;
}

export function AppShell({ sidebar, header, children }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const toggleSidebar = useCallback(() => setSidebarOpen((o) => !o), []);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-64
          transform transition-transform duration-200 ease-in-out
          md:relative md:translate-x-0
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        {sidebar}
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {header({ onMenuToggle: toggleSidebar })}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
