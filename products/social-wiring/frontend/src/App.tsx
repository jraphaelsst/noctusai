/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav mirrors the live-validated CMS source (ported in Wave 2.4):
 *   Principal     · Dashboard / Agente / Vídeos / Upload
 *   WhatsApp      · Conexão / Monitor
 *   Configuração  · Configurações / Equipe
 * pt-BR copy preserved verbatim from the validated workspace.
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
  MessageCircle,
  PlaySquare,
  Settings as SettingsIcon,
  Settings2,
  Smartphone,
  Activity,
  Upload as UploadIcon,
  Share2,
  Wand2,
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
const MediaCreation = lazy(() => import("@/pages/MediaCreation"));
const EmailMarketing = lazy(() => import("@/pages/EmailMarketing"));
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
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2, route: "media_creation" },
      { name: "Email Marketing", href: "/email-marketing", icon: Mail, route: "email_marketing" },
      { name: "Vídeos", href: "/videos", icon: PlaySquare, route: "videos" },
      { name: "Upload", href: "/upload", icon: UploadIcon, route: "upload" },
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
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2 },
      { name: "Email Marketing", href: "/email-marketing", icon: Mail },
      { name: "Vídeos", href: "/videos", icon: PlaySquare },
      { name: "Upload", href: "/upload", icon: UploadIcon },
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
    { path: "/videos", component: Videos },
    { path: "/upload", component: Upload },
    { path: "/conexao", component: Conexao },
    { path: "/monitor", component: Monitor },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes", component: Settings },
  ],
  // /chat is public — the backend chat router is unauthenticated by
  // current product direction, so the frontend route matches that
  // posture. When real auth lands on /api/chat/*, move /chat back
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
