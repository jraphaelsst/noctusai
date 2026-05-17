/**
 * YouTube Crawler App — the simplest possible product.
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
import {
  LayoutDashboard,
  Users,
  Home,
  MessageCircle,
  PlaySquare,
  Settings as SettingsIcon,
  Settings2,
  Smartphone,
  Activity,
  Upload as UploadIcon,
} from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Chat = lazy(() => import("@/pages/Chat"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const Settings = lazy(() => import("@/pages/Settings"));
const Upload = lazy(() => import("@/pages/Upload"));
const Videos = lazy(() => import("@/pages/Videos"));
const Conexao = lazy(() => import("@/pages/Conexao"));
const Monitor = lazy(() => import("@/pages/Monitor"));
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
      { name: "Agente", href: "/chat", icon: MessageCircle, route: "chat" },
      { name: "Videos", href: "/videos", icon: PlaySquare, route: "videos" },
      { name: "Upload", href: "/upload", icon: UploadIcon, route: "upload" },
    ],
  },
  {
    key: "whatsapp",
    label: "WhatsApp",
    icon: Smartphone,
    defaultOpen: true,
    items: [
      { name: "Conexao", href: "/conexao", icon: Smartphone, route: "conexao" },
      { name: "Monitor", href: "/monitor", icon: Activity, route: "monitor" },
    ],
  },
  {
    key: "config",
    label: "Configuracao",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configuracoes", href: "/configuracoes", icon: SettingsIcon, route: "configuracoes" },
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
      { name: "Agente", href: "/chat", icon: MessageCircle },
      { name: "Videos", href: "/videos", icon: PlaySquare },
      { name: "Upload", href: "/upload", icon: UploadIcon },
    ],
  },
  {
    key: "whatsapp",
    label: "WhatsApp",
    icon: Smartphone,
    defaultOpen: true,
    items: [
      { name: "Conexao", href: "/conexao", icon: Smartphone },
      { name: "Monitor", href: "/monitor", icon: Activity },
    ],
  },
  {
    key: "config",
    label: "Configuracao",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configuracoes", href: "/configuracoes", icon: SettingsIcon },
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: PlaySquare,
  brandTitle: "YouTube Crawler",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/videos", component: Videos },
    { path: "/upload", component: Upload },
    { path: "/conexao", component: Conexao },
    { path: "/monitor", component: Monitor },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes", component: Settings },
  ],
  // /chat is public — the backend chat router is also unauthenticated
  // by current product direction, so the frontend route matches that
  // posture. When real auth lands on /api/chat/*, we move /chat back
  // into the `routes` array.
  publicRoutes: [
    { path: "/chat", component: Chat },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
