/**
 * Orbity App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, Box, Boxes, DollarSign } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Placeholder domain page — rename + replace per
// `products/seed/frontend/src/pages/Example.tsx`. Backend mirror at
// `app/routers/example_router.py`.
const Example = lazy(() => import("@/pages/Example"));
const Financeiro = lazy(() => import("@/pages/Financeiro"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Example", href: "/example", icon: Boxes, route: "example" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Financeiro", href: "/financeiro", icon: DollarSign, route: "financeiro" },
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
      { name: "Example", href: "/example", icon: Boxes },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Financeiro", href: "/financeiro", icon: DollarSign },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Box,
  brandTitle: "Orbity",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/example", component: Example },
    { path: "/equipe", component: Equipe },
    { path: "/financeiro", component: Financeiro },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
