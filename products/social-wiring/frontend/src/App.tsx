/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav:
 *   Principal     · Dashboard / Criação de mídia / Email Marketing / YouTube
 *   WhatsApp      · Conexão / Monitor
 *   Configuração  · Configurações / Equipe / Integrações
 *
 * The former "Agente" / "Vídeos" / "Upload" entries are consolidated under
 * ONE "YouTube" page (Vídeos + Upload tabs; Agente is now Upload→Chat). The
 * `/chat` route stays public for direct access. pt-BR copy preserved.
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
  Mail,
  Plug,
  Settings as SettingsIcon,
  Settings2,
  Smartphone,
  Activity,
  Share2,
  Wand2,
  Youtube,
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
const YouTube = lazy(() => import("@/pages/YouTube"));
const Conexao = lazy(() => import("@/pages/Conexao"));
const Monitor = lazy(() => import("@/pages/Monitor"));
const MediaCreation = lazy(() => import("@/pages/MediaCreation"));
const EmailMarketing = lazy(() => import("@/pages/EmailMarketing"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Integrations = lazy(() => import("@/pages/Integrations"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2, route: "media_creation" },
      { name: "Email Marketing", href: "/email-marketing", icon: Mail, route: "email_marketing" },
      { name: "YouTube", href: "/youtube", icon: Youtube, route: "youtube" },
    ],
  },
  {
    key: "whatsapp",
    label: "WhatsApp",
    icon: Smartphone,
    defaultOpen: true,
    items: [
      { name: "Conexão", href: "/conexao", icon: Smartphone, route: "conexao" },
      { name: "Monitor", href: "/monitor", icon: Activity, route: "monitor" },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configurações", href: "/configuracoes", icon: SettingsIcon, route: "configuracoes" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Integrações", href: "/integrations", icon: Plug, route: "integrations" },
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
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2 },
      { name: "Email Marketing", href: "/email-marketing", icon: Mail },
      { name: "YouTube", href: "/youtube", icon: Youtube },
    ],
  },
  {
    key: "whatsapp",
    label: "WhatsApp",
    icon: Smartphone,
    defaultOpen: true,
    items: [
      { name: "Conexão", href: "/conexao", icon: Smartphone },
      { name: "Monitor", href: "/monitor", icon: Activity },
    ],
  },
  {
    key: "config",
    label: "Configuração",
    icon: Settings2,
    defaultOpen: false,
    items: [
      { name: "Configurações", href: "/configuracoes", icon: SettingsIcon },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Integrações", href: "/integrations", icon: Plug },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Share2,
  brandTitle: "Social Wiring",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/media-creation", component: MediaCreation },
    { path: "/email-marketing", component: EmailMarketing },
    { path: "/youtube", component: YouTube },
    { path: "/conexao", component: Conexao },
    { path: "/monitor", component: Monitor },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes", component: Settings },
    { path: "/integrations", component: Integrations },
  ],
  // /chat is public — the backend chat router is unauthenticated by
  // current product direction, so the frontend route matches that
  // posture. The same panel renders as YouTube → Upload → Chat.
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
