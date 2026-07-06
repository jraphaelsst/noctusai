/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav:
 *   Principal     · Dashboard / Criação de mídia / Email Marketing / YouTube
 *   Conexões      · Conexões (unified: WhatsApp + YouTube + providers) / Monitor
 *   Configuração  · Configurações / Equipe
 *
 * The former "Integrações" nav item is folded into "Conexões" — both the
 * /conexoes and /integrations routes point to the same Conexoes page.
 * The former separate "Conexão" (WhatsApp-only) is now embedded inside Conexoes.
 * The standalone /conexao route is kept for back-compat (direct WAHA management).
 * pt-BR copy preserved.
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
  Settings as SettingsIcon,
  Settings2,
  Smartphone,
  Activity,
  Share2,
  Wand2,
  Youtube,
  Instagram,
  UserRound,
  List,
  FileText,
  Send,
  Building2,
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
const RedirectToClientes = lazy(() => import("@/pages/RedirectToClientes"));
const RedirectToMeta = lazy(() => import("@/pages/RedirectToMeta"));
const Monitor = lazy(() => import("@/pages/Monitor"));
const MediaCreation = lazy(() => import("@/pages/MediaCreation"));
const EmailMarketing = lazy(() => import("@/pages/EmailMarketing"));
const Contatos = lazy(() => import("@/pages/Contatos"));
const EmailListas = lazy(() => import("@/pages/EmailListas"));
const EmailTemplates = lazy(() => import("@/pages/EmailTemplates"));
const EmailCampanhas = lazy(() => import("@/pages/EmailCampanhas"));
const EmailMarketingConfig = lazy(() => import("@/pages/EmailMarketingConfig"));
const EmailMembros = lazy(() => import("@/pages/EmailMembros"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const WhatsAppChat = lazy(() => import("@/pages/WhatsAppChat"));
const Clientes = lazy(() => import("@/pages/Clientes"));
const MetaDashboard = lazy(() => import("@/pages/MetaDashboard"));

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
      { name: "Contatos", href: "/contatos", icon: UserRound, route: "contatos" },
      { name: "YouTube", href: "/youtube", icon: Youtube, route: "youtube" },
      { name: "Meta", href: "/meta", icon: Instagram, route: "meta" },
    ],
  },
  {
    key: "email",
    label: "Email Marketing",
    icon: Mail,
    defaultOpen: false,
    items: [
      { name: "Membros", href: "/email-marketing/membros", icon: Users, route: "email_membros" },
      { name: "Listas", href: "/email-marketing/listas", icon: List, route: "email_listas" },
      { name: "Templates", href: "/email-marketing/templates", icon: FileText, route: "email_templates" },
      { name: "Campanhas", href: "/email-marketing/campanhas", icon: Send, route: "email_campanhas" },
      { name: "Configuração", href: "/email-marketing/configuracao", icon: Settings2, route: "email_config" },
    ],
  },
  {
    key: "conexoes",
    label: "Conexões",
    icon: Smartphone,
    defaultOpen: true,
    items: [
      { name: "Clientes", href: "/clientes", icon: Building2, route: "clientes" },
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
      { name: "Criação de mídia", href: "/media-creation", icon: Wand2 },
      { name: "Contatos", href: "/contatos", icon: UserRound },
      { name: "YouTube", href: "/youtube", icon: Youtube },
      { name: "Meta", href: "/meta", icon: Instagram },
    ],
  },
  {
    key: "email",
    label: "Email Marketing",
    icon: Mail,
    defaultOpen: false,
    items: [
      { name: "Membros", href: "/email-marketing/membros", icon: Users },
      { name: "Listas", href: "/email-marketing/listas", icon: List },
      { name: "Templates", href: "/email-marketing/templates", icon: FileText },
      { name: "Campanhas", href: "/email-marketing/campanhas", icon: Send },
      { name: "Configuração", href: "/email-marketing/configuracao", icon: Settings2 },
    ],
  },
  {
    key: "conexoes",
    label: "Conexões",
    icon: Smartphone,
    defaultOpen: true,
    items: [
      { name: "Clientes", href: "/clientes", icon: Building2 },
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
    // Legacy /email-marketing repointed at EmailCampanhas (vestigial EmailMarketing.tsx stays but is unrouted)
    { path: "/email-marketing", component: EmailCampanhas },
    { path: "/contatos", component: Contatos },
    { path: "/email-marketing/listas", component: EmailListas },
    { path: "/email-marketing/templates", component: EmailTemplates },
    { path: "/email-marketing/campanhas", component: EmailCampanhas },
    { path: "/email-marketing/configuracao", component: EmailMarketingConfig },
    { path: "/email-marketing/membros", component: EmailMembros },
    { path: "/youtube", component: YouTube },
    { path: "/meta", component: MetaDashboard },
    // Retired route — remodeled into the unified Meta dashboard (Wave 3)
    { path: "/instagram-insights", component: RedirectToMeta },
    // Retired routes — connection management now lives inside ClienteModal
    { path: "/conexoes", component: RedirectToClientes },
    { path: "/integrations", component: RedirectToClientes },
    { path: "/conexao", component: RedirectToClientes },
    { path: "/clientes", component: Clientes },
    { path: "/monitor", component: Monitor },
    // /whatsapp-chat kept as unlisted route (removed from nav; Chat tab inside ClienteModal is now primary)
    { path: "/whatsapp-chat", component: WhatsAppChat },
    { path: "/equipe", component: Equipe },
    { path: "/configuracoes", component: Settings },
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
