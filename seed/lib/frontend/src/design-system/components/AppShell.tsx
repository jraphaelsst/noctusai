/**
 * NoctusAI Global App Shell
 *
 * Unified layout: dark sidebar + light content area.
 * Handles responsive sidebar (off-canvas on mobile, hover-expanding rail on desktop).
 *
 * Products wrap their routes in this shell and provide sidebar/header content.
 *
 * ## Desktop hover rail (canonical default since 2026-08-27)
 *
 * At `md+` the sidebar rests as a narrow icon-only rail (`w-16`, 64px) and
 * expands to full width (`w-64`, 256px) on mouse-enter **or** keyboard focus.
 *
 * 🔴 The expansion is an OVERLAY, never a layout change. Two mechanisms make
 * that true by construction:
 *
 *   1. The `<aside>` is `position: fixed` at EVERY breakpoint (it used to be
 *      `md:relative`, i.e. its width WAS the layout). Fixed also keeps the rail
 *      reachable at any scroll position — a rail that scrolls away is a rail
 *      you cannot hover.
 *   2. A dedicated, `aria-hidden` **layout slot** sibling reserves the
 *      COLLAPSED width in the flex row at all times. It never changes width,
 *      so `main` cannot reflow, resize, or shift by a single pixel when the
 *      rail expands — the expanded panel simply floats over the content.
 *
 * Stacking: the rail sits at `md:z-30` — above `main` (auto), below the
 * canonical `Dialog` overlay (`z-50`, see `design-system/ui/Dialog.tsx`), so an
 * open modal is never covered by an expanded rail. Below `md` the aside keeps
 * `z-50` because it must clear its own mobile backdrop (`z-40`).
 *
 * Mobile (`<md`) is UNCHANGED: off-canvas drawer at full `w-64`, driven by
 * `sidebarOpen` / `onMenuToggle`, with the tap-to-close backdrop. Every
 * rail-specific class is `md:`-prefixed, so the drawer always renders fully
 * expanded regardless of rail state.
 *
 * The rail state is published to the sidebar subtree via `SidebarRailContext`
 * (rather than a required prop) so `Sidebar` can render icon-only rows without
 * any consumer having to wire a new prop. The context DEFAULT is
 * "not a rail" — a `<Sidebar>` rendered outside an `AppShell` keeps its
 * pre-rail rendering exactly.
 */
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { cn } from "../../utils";

/**
 * How the shell renders the desktop sidebar.
 *
 * - `"hover-expand"` (DEFAULT) — the canonical icon rail described above.
 * - `"expanded"` — escape hatch: the pre-rail static 256px sidebar. Still
 *   `fixed` + slot-reserved, so it is layout-equivalent to the old shell.
 *   Reach for this only when a product genuinely needs a permanently-open
 *   sidebar; it is a documented seam, not a fork.
 */
export type SidebarRailMode = "hover-expand" | "expanded";

/** Rail state published to the sidebar subtree. */
export interface SidebarRailState {
  /** True when the shell is rendering the sidebar as a desktop hover rail. */
  enabled: boolean;
  /** True while the rail is expanded (pointer hover OR keyboard focus). */
  expanded: boolean;
  /**
   * `enabled && !expanded` — the "render icon-only AT `md+`" signal.
   * Consumers MUST gate every collapsed-mode class behind `md:` so the mobile
   * drawer is untouched.
   */
  collapsed: boolean;
}

const NO_RAIL: SidebarRailState = { enabled: false, expanded: false, collapsed: false };

const SidebarRailContext = createContext<SidebarRailState>(NO_RAIL);

/**
 * Read the current rail state. Returns the "not a rail" default outside an
 * `AppShell`, so standalone `<Sidebar>` usage is unaffected.
 */
export function useSidebarRail(): SidebarRailState {
  return useContext(SidebarRailContext);
}

/**
 * Did this focus arrive from the keyboard rather than a pointer?
 *
 * `:focus-visible` is the browser's own heuristic for that question, and it is
 * the one thing that separates "a keyboard user is navigating the rail, keep it
 * open" from "someone clicked a link and focus happens to be sitting there".
 *
 * Defaults to TRUE when the selector cannot be evaluated (very old engines,
 * a non-Element target, jsdom): failing toward expanded keeps the nav usable,
 * where failing toward collapsed would strand keyboard focus on clipped labels.
 */
function isKeyboardFocus(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return true;
  try {
    return target.matches(":focus-visible");
  } catch {
    return true;
  }
}

export interface AppShellProps {
  /** The sidebar content (typically a <Sidebar> component) */
  sidebar: React.ReactNode;
  /** The header content (typically a <Header> component receiving onMenuToggle) */
  header: (props: { onMenuToggle: () => void }) => React.ReactNode;
  /** Page content */
  children: React.ReactNode;
  /**
   * Desktop sidebar behaviour. Defaults to the canonical `"hover-expand"`
   * icon rail; pass `"expanded"` for the pre-rail static sidebar.
   */
  railMode?: SidebarRailMode;
}

export function AppShell({ sidebar, header, children, railMode = "hover-expand" }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const toggleSidebar = useCallback(() => setSidebarOpen((o) => !o), []);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  // Hover and focus are tracked separately so that tabbing OUT of the nav while
  // the pointer is still over the rail does not collapse it (and vice versa).
  // React's onFocus/onBlur are focusin/focusout — they bubble, which makes this
  // the JS equivalent of `:focus-within`. Keyboard parity is not polish: a
  // hover-only rail parks focus on invisible labels.
  const [railHovered, setRailHovered] = useState(false);
  const [railFocused, setRailFocused] = useState(false);

  const railEnabled = railMode === "hover-expand";
  const railExpanded = railEnabled && (railHovered || railFocused);

  const rail = useMemo<SidebarRailState>(
    () => ({
      enabled: railEnabled,
      expanded: railExpanded,
      collapsed: railEnabled && !railExpanded,
    }),
    [railEnabled, railExpanded],
  );

  const railHandlers = railEnabled
    ? {
        onMouseEnter: () => setRailHovered(true),
        onMouseLeave: () => setRailHovered(false),
        // 🔴 KEYBOARD focus only (fixed 2026-08-27, caught live in prod).
        // `focusin` fires for a MOUSE click too, so clicking a nav item left
        // focus on it and pinned the rail open over the page it had just
        // navigated to — it only closed once something else took focus.
        // `:focus-visible` is the browser's own "did this focus arrive by
        // keyboard?" answer, which is exactly the distinction wanted here.
        // Unsupported/throwing ⇒ treat as keyboard, because failing toward
        // "expanded" keeps the nav usable rather than stranding focus on
        // clipped labels.
        onFocus: (e: React.FocusEvent) => setRailFocused(isKeyboardFocus(e.target)),
        onBlur: () => setRailFocused(false),
      }
    : {};

  return (
    <div className="flex min-h-screen bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={closeSidebar}
        />
      )}

      {/*
        Layout slot — the load-bearing half of the overlay contract. It holds
        the sidebar's footprint in the flex row and NEVER changes width, so the
        expanding rail cannot move `main`. Purely presentational ⇒ aria-hidden.
      */}
      <div
        aria-hidden="true"
        className={cn("hidden md:block shrink-0", railEnabled ? "w-16" : "w-64")}
      />

      {/* Sidebar — fixed at every breakpoint; only its WIDTH animates on desktop. */}
      <aside
        {...railHandlers}
        data-rail-expanded={railEnabled ? railExpanded : undefined}
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 overflow-hidden md:z-30",
          "transform transition-[transform,width] duration-200 ease-in-out",
          "motion-reduce:transition-none",
          "md:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
          // Rail width. The shadow is the "I am floating above the content"
          // affordance — it has no layout cost, so it cannot shift `main`.
          railEnabled
            ? railExpanded
              ? "md:w-64 md:shadow-xl"
              : "md:w-16"
            : "md:w-64",
        )}
      >
        <SidebarRailContext.Provider value={rail}>{sidebar}</SidebarRailContext.Provider>
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
