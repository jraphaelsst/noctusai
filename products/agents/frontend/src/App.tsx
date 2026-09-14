/**
 * Agentes App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, Bot, MessageCircle, CheckCircle2 } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Julia agents UI — contract §E (`projects/julia-agents-academia-CONTRACT.md`).
const Julia = lazy(() => import("@/pages/Julia"));
const Agentes = lazy(() => import("@/pages/Agentes"));
const JuliaPersona = lazy(() => import("@/pages/JuliaPersona"));
const Aprovacoes = lazy(() => import("@/pages/Aprovacoes"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Julia", href: "/julia", icon: MessageCircle, route: "julia" },
      { name: "Agentes", href: "/agentes", icon: Bot, route: "agentes" },
      { name: "Aprovações", href: "/aprovacoes", icon: CheckCircle2, route: "aprovacoes" },
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
      { name: "Julia", href: "/julia", icon: MessageCircle },
      { name: "Agentes", href: "/agentes", icon: Bot },
      { name: "Aprovações", href: "/aprovacoes", icon: CheckCircle2 },
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Bot,
  brandTitle: "Agentes",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/julia", component: Julia },
    { path: "/agentes", component: Agentes },
    { path: "/agentes/julia/persona", component: JuliaPersona },
    { path: "/aprovacoes", component: Aprovacoes },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
