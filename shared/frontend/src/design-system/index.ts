/**
 * NoctusAI Global Design System
 *
 * Export all shared design system components, hooks, and types.
 *
 * Usage:
 *   import { AppShell, Sidebar, Header, useTheme } from "@noctusai/shared/design-system";
 *   import type { NavGroup, NavItem, HeaderProps, HeaderUser } from "@noctusai/shared/design-system";
 */

export { AppShell } from "./components/AppShell";
export type { AppShellProps } from "./components/AppShell";

export { Sidebar } from "./components/Sidebar";
export type { SidebarProps, NavGroup, NavItem } from "./components/Sidebar";

export { Header } from "./components/Header";
export type { HeaderProps, HeaderUser } from "./components/Header";

export { useTheme } from "./useTheme";
export { useActivityRefresh } from "./useActivityRefresh";
export { InactivityWarning } from "./InactivityWarning";

export { HoverCard, HoverCardTrigger, HoverCardContent } from "./ui/hover-card";
