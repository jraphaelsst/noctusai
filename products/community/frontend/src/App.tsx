/**
 * Community App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, UsersRound, Boxes, UserRound, Wallet, ClipboardList } from "lucide-react";

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

// Module 1 — Membros + Planos + Inscrições (community-m1-contract.md).
// Backend mirror at `app/routers/{membros,planos,aplicacoes}_router.py`.
const Membros = lazy(() => import("@/pages/Membros"));
const Planos = lazy(() => import("@/pages/Planos"));
const Inscricoes = lazy(() => import("@/pages/Inscricoes"));
// PUBLIC — the application form, mounted below as a `publicRoute` (no
// auth, no Layout — a visitor with no session must be able to reach it).
const Inscrever = lazy(() => import("@/pages/Inscrever"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Membros", href: "/membros", icon: UserRound, route: "membros" },
      { name: "Planos", href: "/planos", icon: Wallet, route: "planos" },
      { name: "Inscrições", href: "/inscricoes", icon: ClipboardList, route: "inscricoes" },
      { name: "Example", href: "/example", icon: Boxes, route: "example" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
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
      { name: "Membros", href: "/membros", icon: UserRound },
      { name: "Planos", href: "/planos", icon: Wallet },
      { name: "Inscrições", href: "/inscricoes", icon: ClipboardList },
      { name: "Example", href: "/example", icon: Boxes },
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: UsersRound,
  brandTitle: "Community",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/membros", component: Membros },
    { path: "/planos", component: Planos },
    { path: "/inscricoes", component: Inscricoes },
    { path: "/example", component: Example },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
  // PUBLIC — no auth, no Layout. The public application form must render
  // for a visitor with no session (community-m1-contract.md §Frontend).
  publicRoutes: [{ path: "/inscrever", component: Inscrever }],
});
