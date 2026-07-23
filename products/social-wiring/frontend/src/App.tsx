/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav:
 *   Principal     · Dashboard / Criação de mídia / Contatos / Leads / YouTube / Meta / WhatsApp
 *   Conexões      · Clientes / Monitor
 *   Configuração  · Configurações / Equipe
 *
 * The former "Integrações" nav item is folded into "Conexões" — both the
 * /conexoes and /integrations routes point to the same Conexoes page.
 * The former separate "Conexão" (WhatsApp-only) is now embedded inside Conexoes.
 * The standalone /conexao route is kept for back-compat (direct WAHA management).
 *
 * WhatsApp (`/whatsapp-chat`) is back in nav as of the SocialDashboardShell
 * remodel (componentization wave, N=3) — it's now a full dashboard (Chat +
 * Configurações subtabs), not just the connection-scoped Chat tab ClienteModal
 * already surfaces. The `whatsapp_chat` status_pagina row already exists
 * (migration 014, status='producao') from when this route was last in nav —
 * no new migration needed to make it visible again.
 * pt-BR copy preserved.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import { useSocialWiringLayoutEnrichment } from "@/hooks/useLayoutEnrichment";
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
  Target,
  Workflow,
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
const N8n = lazy(() => import("@/pages/N8n"));
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
const Leads = lazy(() => import("@/pages/leads/Leads"));

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
      { name: "Leads", href: "/leads", icon: Target, route: "leads" },
      { name: "YouTube", href: "/youtube", icon: Youtube, route: "youtube" },
      { name: "Meta", href: "/meta", icon: Instagram, route: "meta" },
      { name: "WhatsApp", href: "/whatsapp-chat", icon: Smartphone, route: "whatsapp_chat" },
      { name: "n8n", href: "/n8n", icon: Workflow, route: "n8n" },
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
      { name: "Leads", href: "/leads", icon: Target },
      { name: "YouTube", href: "/youtube", icon: Youtube },
      { name: "Meta", href: "/meta", icon: Instagram },
      { name: "WhatsApp", href: "/whatsapp-chat", icon: Smartphone },
      { name: "n8n", href: "/n8n", icon: Workflow },
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
  useLayoutEnrichment: useSocialWiringLayoutEnrichment,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/media-creation", component: MediaCreation },
    // Legacy /email-marketing repointed at EmailCampanhas (vestigial EmailMarketing.tsx stays but is unrouted)
    { path: "/email-marketing", component: EmailCampanhas },
    { path: "/contatos", component: Contatos },
    { path: "/leads", component: Leads },
    { path: "/email-marketing/listas", component: EmailListas },
    { path: "/email-marketing/templates", component: EmailTemplates },
    { path: "/email-marketing/campanhas", component: EmailCampanhas },
    { path: "/email-marketing/configuracao", component: EmailMarketingConfig },
    { path: "/email-marketing/membros", component: EmailMembros },
    { path: "/youtube", component: YouTube },
    { path: "/n8n", component: N8n },
    { path: "/meta", component: MetaDashboard },
    // Retired route — remodeled into the unified Meta dashboard (Wave 3)
    { path: "/instagram-insights", component: RedirectToMeta },
    // Retired routes — connection management now lives inside ClienteModal
    { path: "/conexoes", component: RedirectToClientes },
    { path: "/integrations", component: RedirectToClientes },
    { path: "/conexao", component: RedirectToClientes },
    { path: "/clientes", component: Clientes },
    { path: "/monitor", component: Monitor },
    // WhatsApp — full dashboard (Chat + Configurações), back in nav (see header comment)
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
