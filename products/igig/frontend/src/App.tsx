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
import { LayoutDashboard, Users, Home, Palette, Boxes, Building2, KanbanSquare, Palette as PaletteIcon, CalendarDays, BarChart3, Plug, Wallet, Briefcase } from "lucide-react";

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
const Financeiro = lazy(() => import("@/pages/Financeiro"));
const Comercial = lazy(() => import("@/pages/Comercial"));
const Custos = lazy(() => import("@/pages/Custos"));
// PUBLIC route — the agency's client, no noc account. Token is the auth.
const AprovacaoPublica = lazy(() => import("@/pages/AprovacaoPublica"));
// PUBLIC route — Módulo 1's pré-qualificação form, embedded on the agency's
// own site. `org_id` rides in the path because there is no session to infer
// the agency from; the endpoint is write-only and rate-limited.
const PreQualificacao = lazy(() => import("@/pages/PreQualificacao"));
const Equipe = lazy(() => import("@/pages/Equipe"));
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
      { name: "Comercial", href: "/comercial", icon: Briefcase, route: "comercial" },
      { name: "Clientes", href: "/clientes", icon: Building2, route: "clientes" },
      { name: "Esteira", href: "/esteira", icon: KanbanSquare, route: "esteira" },
      { name: "Marca", href: "/marca", icon: PaletteIcon, route: "marca" },
      { name: "Calendário", href: "/calendario", icon: CalendarDays, route: "calendario" },
      { name: "Distribuição", href: "/distribuicao", icon: BarChart3, route: "distribuicao" },
      { name: "Financeiro", href: "/financeiro", icon: Wallet, route: "financeiro" },
      { name: "Integrações", href: "/integracoes", icon: Plug, route: "integracoes" },
      { name: "Custos", href: "/custos", icon: Boxes, route: "custos" },
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
      { name: "Comercial", href: "/comercial", icon: Briefcase },
      { name: "Clientes", href: "/clientes", icon: Building2 },
      { name: "Esteira", href: "/esteira", icon: KanbanSquare },
      { name: "Marca", href: "/marca", icon: PaletteIcon },
      { name: "Calendário", href: "/calendario", icon: CalendarDays },
      { name: "Distribuição", href: "/distribuicao", icon: BarChart3 },
      { name: "Financeiro", href: "/financeiro", icon: Wallet },
      { name: "Integrações", href: "/integracoes", icon: Plug },
      { name: "Custos", href: "/custos", icon: Boxes },
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
    { path: "/comercial", component: Comercial },
    { path: "/clientes", component: Clientes },
    { path: "/esteira", component: Esteira },
    { path: "/marca", component: Marca },
    { path: "/calendario", component: Calendario },
    { path: "/distribuicao", component: Distribuicao },
    { path: "/financeiro", component: Financeiro },
    { path: "/integracoes", component: Integracoes },
    { path: "/custos", component: Custos },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  publicRoutes: [
    { path: "/aprovar/:token", component: AprovacaoPublica },
    { path: "/pre-qualificacao/:orgId", component: PreQualificacao },
  ],
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
