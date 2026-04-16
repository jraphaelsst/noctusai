/**
 * NoctusAI Global Design System
 *
 * Export all shared design system components, hooks, and types.
 *
 * Usage:
 *   import { AppShell, Sidebar, Header, useTheme } from "@noctusai/lib/design-system";
 *   import type { NavGroup, NavItem, HeaderProps, HeaderUser } from "@noctusai/lib/design-system";
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

export { PageSkeleton } from "./components/PageSkeleton";

export { LoginForm } from "./components/LoginForm";
export type { LoginFormProps } from "./components/LoginForm";

export { ForgotPasswordPage } from "./components/ForgotPasswordPage";
export type { ForgotPasswordPageProps } from "./components/ForgotPasswordPage";

export { NotificationBell } from "./components/NotificationBell";
export type { NotificationBellProps, NotificationHooks } from "./components/NotificationBell";

export { PoweredByFooter } from "./components/PoweredByFooter";

export { AcceptInvitePage } from "./components/AcceptInvitePage";
export type { AcceptInvitePageProps } from "./components/AcceptInvitePage";

export { HoverCard, HoverCardTrigger, HoverCardContent } from "./ui/hover-card";
