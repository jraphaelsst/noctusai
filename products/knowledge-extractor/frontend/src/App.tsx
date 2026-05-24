/**
 * Knowledge Extractor App — extract, organize and search course knowledge.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav:
 *   Principal     · Dashboard / Módulos / Metodologia / Busca / Processamentos
 *   Configuração  · Configurações / Equipe
 * UI language: pt-BR.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from "@noctusai/seed/infra";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import {
  LayoutDashboard,
  Users,
  Home,
  GraduationCap,
  Layers,
  BookMarked,
  Search as SearchIcon,
  Play,
  Settings as SettingsIcon,
  Settings2,
} from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Modules = lazy(() => import("@/pages/Modules"));
const LessonViewer = lazy(() => import("@/pages/LessonViewer"));
const Methodology = lazy(() => import("@/pages/Methodology"));
const Search = lazy(() => import("@/pages/Search"));
const Runs = lazy(() => import("@/pages/Runs"));
const Settings = lazy(() => import("@/pages/Settings"));
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
      { name: "Módulos", href: "/modules", icon: Layers, route: "modules" },
      { name: "Metodologia", href: "/methodology", icon: BookMarked, route: "methodology" },
      { name: "Busca", href: "/search", icon: SearchIcon, route: "search" },
      { name: "Processamentos", href: "/runs", icon: Play, route: "runs" },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configurações", href: "/settings", icon: SettingsIcon, route: "settings" },
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
      { name: "Módulos", href: "/modules", icon: Layers },
      { name: "Metodologia", href: "/methodology", icon: BookMarked },
      { name: "Busca", href: "/search", icon: SearchIcon },
      { name: "Processamentos", href: "/runs", icon: Play },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configurações", href: "/settings", icon: SettingsIcon },
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: GraduationCap,
  brandTitle: "Knowledge Extractor",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/modules", component: Modules },
    { path: "/lessons/:module/:lesson", component: LessonViewer },
    { path: "/methodology", component: Methodology },
    { path: "/search", component: Search },
    { path: "/runs", component: Runs },
    { path: "/settings", component: Settings },
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
