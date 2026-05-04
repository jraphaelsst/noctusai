/**
 * Media Scheduling App — the simplest possible product.
 *
 * Infrastructure comes from @/infra (one file, one createProductInfra call).
 * Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import { LayoutDashboard, Users, Home, Calendar, UserCheck, Link2 } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const AuthorizedUsersPage = lazy(() => import("@/pages/AuthorizedUsersPage"));
const AppointmentsPage = lazy(() => import("@/pages/AppointmentsPage"));
const OAuthStatusPage = lazy(() => import("@/pages/OAuthStatusPage"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Agendamentos", href: "/appointments", icon: Calendar, route: "appointments" },
      { name: "Usuários autorizados", href: "/authorized-users", icon: UserCheck, route: "authorized-users" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Google Calendar", href: "/oauth", icon: Link2, route: "oauth" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      { name: "Agendamentos", href: "/appointments", icon: Calendar },
      { name: "Usuários autorizados", href: "/authorized-users", icon: UserCheck },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Google Calendar", href: "/oauth", icon: Link2 },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Calendar,
  brandTitle: "Media Scheduling",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/appointments", component: AppointmentsPage },
    { path: "/authorized-users", component: AuthorizedUsersPage },
    { path: "/equipe", component: Equipe },
    { path: "/oauth", component: OAuthStatusPage },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
