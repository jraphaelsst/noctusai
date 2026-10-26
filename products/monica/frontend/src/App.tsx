/**
 * Monica App -- the CRM of Mônica Tangerino's psychoanalysis practice.
 *
 * Infrastructure comes from @/infra (one file, one createProductInfra call).
 * Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav -- every screen is a seed organ wired in `src/pages/`.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import { stripNavRoutes, type NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import {
  BookOpenText, Boxes, Filter, Home, Kanban, LayoutDashboard, List, MessageCircle, Settings, Smartphone, Users, Wallet,
} from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Leads = lazy(() => import("@/pages/Leads"));
const Conversas = lazy(() => import("@/pages/Conversas"));
const Contexto = lazy(() => import("@/pages/Contexto"));
const Configuracoes = lazy(() => import("@/pages/Configuracoes"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Finance organ (seed `FinanceShell`) -- `/financeiro/*`; section in the URL. The future ERP side.
const Financeiro = lazy(() => import("@/pages/Financeiro"));

// Nav. `route` is the `status_pagina.nome_pagina` key (migrations 001/013/016): a route without a row is hidden
// from everyone.
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Início", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Conversas", href: "/conversas", icon: MessageCircle, route: "conversas" },
      { name: "Contexto", href: "/contexto", icon: BookOpenText, route: "contexto" },
    ],
  },
  {
    key: "leads",
    label: "Leads",
    icon: Filter,
    items: [
      { name: "Funil", href: "/leads", icon: Kanban, route: "leads" },
      { name: "Lista", href: "/leads/lista", icon: List, route: "leads_lista" },
    ],
  },
  {
    key: "gestao",
    label: "Gestão",
    icon: Boxes,
    items: [
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Financeiro", href: "/financeiro", icon: Wallet, route: "financeiro" },
    ],
  },
  {
    key: "configuracoes",
    label: "Configurações",
    icon: Settings,
    items: [{ name: "Conexões", href: "/configuracoes/conexoes", icon: Smartphone, route: "conexoes" }],
  },
];

// The same tree without the status gate (shown while the page-status query has not answered).
const NAV_FALLBACK: NavGroup[] = stripNavRoutes(NAV_GROUPS);

const Layout = createProductLayout({
  brandIcon: Users,
  brandTitle: "Monica",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/leads/*", component: Leads },
    { path: "/conversas", component: Conversas },
    { path: "/contexto", component: Contexto },
    { path: "/configuracoes/*", component: Configuracoes },
    { path: "/equipe", component: Equipe },
    { path: "/financeiro/*", component: Financeiro },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
