/**
 * Assistant App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, MessageCircle, Smartphone, Settings, ClipboardCheck } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
// Settings (seed `SectionTabsPage`) -- `/configuracoes/*`; the tab is a sub-route.
const Configuracoes = lazy(() => import("@/pages/Configuracoes"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// WhatsApp pairing page (seed `WhatsAppConnectionsPage` organ).
const Conexao = lazy(() => import("@/pages/Conexao"));
const Avaliacao = lazy(() => import("@/pages/avaliacao/Avaliacao"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Conexão", href: "/conexao", icon: Smartphone, route: "conexao" },
      { name: "Avaliação", href: "/avaliacao", icon: ClipboardCheck, route: "avaliacao" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Configurações", href: "/configuracoes/conta", icon: Settings, route: "configuracoes" },
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
      { name: "Conexão", href: "/conexao", icon: Smartphone },
      { name: "Avaliação", href: "/avaliacao", icon: ClipboardCheck },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Configurações", href: "/configuracoes/conta", icon: Settings },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: MessageCircle,
  brandTitle: "Assistant",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/conexao", component: Conexao },
    { path: "/avaliacao", component: Avaliacao },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes/*", component: Configuracoes },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
