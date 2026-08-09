/**
 * IgIg App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, Palette, Boxes, Building2, KanbanSquare, Palette as PaletteIcon, CalendarDays, BarChart3, Plug } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Clientes = lazy(() => import("@/pages/Clientes"));
const Esteira = lazy(() => import("@/pages/Esteira"));
const Marca = lazy(() => import("@/pages/Marca"));
const Calendario = lazy(() => import("@/pages/Calendario"));
const Distribuicao = lazy(() => import("@/pages/Distribuicao"));
const Integracoes = lazy(() => import("@/pages/Integracoes"));
// PUBLIC route — the agency's client, no noc account. Token is the auth.
const AprovacaoPublica = lazy(() => import("@/pages/AprovacaoPublica"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Placeholder domain page — rename + replace per
// `products/seed/frontend/src/pages/Example.tsx`. Backend mirror at
// `app/routers/example_router.py`.
const Example = lazy(() => import("@/pages/Example"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Clientes", href: "/clientes", icon: Building2, route: "clientes" },
      { name: "Esteira", href: "/esteira", icon: KanbanSquare, route: "esteira" },
      { name: "Marca", href: "/marca", icon: PaletteIcon, route: "marca" },
      { name: "Calendário", href: "/calendario", icon: CalendarDays, route: "calendario" },
      { name: "Distribuição", href: "/distribuicao", icon: BarChart3, route: "distribuicao" },
      { name: "Integrações", href: "/integracoes", icon: Plug, route: "integracoes" },
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
      { name: "Clientes", href: "/clientes", icon: Building2 },
      { name: "Esteira", href: "/esteira", icon: KanbanSquare },
      { name: "Marca", href: "/marca", icon: PaletteIcon },
      { name: "Calendário", href: "/calendario", icon: CalendarDays },
      { name: "Distribuição", href: "/distribuicao", icon: BarChart3 },
      { name: "Integrações", href: "/integracoes", icon: Plug },
      { name: "Example", href: "/example", icon: Boxes },
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Palette,
  brandTitle: "IgIg",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/clientes", component: Clientes },
    { path: "/esteira", component: Esteira },
    { path: "/marca", component: Marca },
    { path: "/calendario", component: Calendario },
    { path: "/distribuicao", component: Distribuicao },
    { path: "/integracoes", component: Integracoes },
    { path: "/example", component: Example },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  publicRoutes: [{ path: "/aprovar/:token", component: AprovacaoPublica }],
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
