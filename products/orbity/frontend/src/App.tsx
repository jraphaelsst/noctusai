/**
 * Orbity App — agency-management SaaS routes + nav.
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
import { LayoutDashboard, Users, Home, Box, DollarSign, UserCheck, Kanban, ClipboardList, CalendarDays, RefreshCw, FileBarChart2, Target, Zap, Megaphone } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
// Public pages — no auth required
const RelatorioPublico = lazy(() => import("@/pages/RelatorioPublico"));
const AprovacaoPublica = lazy(() => import("@/pages/AprovacaoPublica"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Financeiro = lazy(() => import("@/pages/Financeiro"));
// CRM module
const Clientes = lazy(() => import("@/pages/Clientes"));
const Funil = lazy(() => import("@/pages/Funil"));
// Tasks + Agenda + Routines module
const Tarefas = lazy(() => import("@/pages/Tarefas"));
const Agenda = lazy(() => import("@/pages/Agenda"));
const Rotinas = lazy(() => import("@/pages/Rotinas"));
const Relatorios = lazy(() => import("@/pages/Relatorios"));
// Meta Ads / Tráfego module
const Trafego = lazy(() => import("@/pages/Trafego"));
const Automacao = lazy(() => import("@/pages/Automacao"));
// Content / Social Studio module
const Conteudo = lazy(() => import("@/pages/Conteudo"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Financeiro", href: "/financeiro", icon: DollarSign, route: "financeiro" },
    ],
  },
  {
    key: "crm",
    label: "CRM",
    icon: UserCheck,
    defaultOpen: true,
    items: [
      { name: "Clientes", href: "/clientes", icon: UserCheck, route: "clientes" },
      { name: "Funil", href: "/funil", icon: Kanban, route: "funil" },
    ],
  },
  {
    key: "operacoes",
    label: "Operações",
    icon: ClipboardList,
    defaultOpen: true,
    items: [
      { name: "Tarefas", href: "/tarefas", icon: ClipboardList, route: "tarefas" },
      { name: "Agenda", href: "/agenda", icon: CalendarDays, route: "agenda" },
      { name: "Rotinas", href: "/rotinas", icon: RefreshCw, route: "rotinas" },
    ],
  },
  {
    key: "relatorios",
    label: "Relatórios",
    icon: FileBarChart2,
    defaultOpen: true,
    items: [
      { name: "Relatórios", href: "/relatorios", icon: FileBarChart2, route: "relatorios" },
    ],
  },
  {
    key: "trafego",
    label: "Tráfego",
    icon: Target,
    defaultOpen: true,
    items: [
      { name: "Tráfego", href: "/trafego", icon: Target, route: "trafego" },
    ],
  },
  {
    key: "automacao",
    label: "Automação",
    icon: Zap,
    defaultOpen: true,
    items: [
      { name: "Automacao", href: "/automacao", icon: Zap, route: "automacao" },
    ],
  },
  {
    key: "conteudo",
    label: "Conteúdo",
    icon: Megaphone,
    defaultOpen: true,
    items: [
      { name: "Conteúdo", href: "/conteudo", icon: Megaphone, route: "conteudo" },
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
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Financeiro", href: "/financeiro", icon: DollarSign },
    ],
  },
  {
    key: "crm",
    label: "CRM",
    icon: UserCheck,
    defaultOpen: true,
    items: [
      { name: "Clientes", href: "/clientes", icon: UserCheck },
      { name: "Funil", href: "/funil", icon: Kanban },
    ],
  },
  {
    key: "operacoes",
    label: "Operações",
    icon: ClipboardList,
    defaultOpen: true,
    items: [
      { name: "Tarefas", href: "/tarefas", icon: ClipboardList },
      { name: "Agenda", href: "/agenda", icon: CalendarDays },
      { name: "Rotinas", href: "/rotinas", icon: RefreshCw },
    ],
  },
  {
    key: "relatorios",
    label: "Relatórios",
    icon: FileBarChart2,
    defaultOpen: true,
    items: [
      { name: "Relatórios", href: "/relatorios", icon: FileBarChart2 },
    ],
  },
  {
    key: "trafego",
    label: "Tráfego",
    icon: Target,
    defaultOpen: true,
    items: [
      { name: "Tráfego", href: "/trafego", icon: Target },
    ],
  },
  {
    key: "automacao",
    label: "Automação",
    icon: Zap,
    defaultOpen: true,
    items: [
      { name: "Automacao", href: "/automacao", icon: Zap },
    ],
  },
  {
    key: "conteudo",
    label: "Conteúdo",
    icon: Megaphone,
    defaultOpen: true,
    items: [
      { name: "Conteúdo", href: "/conteudo", icon: Megaphone },
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
  publicRoutes: [
    { path: "/relatorio/:token", component: RelatorioPublico },
    { path: "/aprovar/:token", component: AprovacaoPublica },
  ],
  routes: [
    { path: "/", component: Dashboard },
    { path: "/equipe", component: Equipe },
    { path: "/financeiro", component: Financeiro },
    { path: "/clientes", component: Clientes },
    { path: "/funil", component: Funil },
    { path: "/tarefas", component: Tarefas },
    { path: "/agenda", component: Agenda },
    { path: "/rotinas", component: Rotinas },
    { path: "/relatorios", component: Relatorios },
    { path: "/trafego", component: Trafego },
    { path: "/automacao", component: Automacao },
    { path: "/conteudo", component: Conteudo },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
