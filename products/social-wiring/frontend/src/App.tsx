/**
 * Social Wiring App — media-wiring CMS.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call). Structure comes from createProductApp + createProductLayout.
 * This file only defines pages and nav — zero boilerplate.
 *
 * Nav:
 *   Principal     · Dashboard / Criação de mídia / Contatos / Leads / YouTube / Meta / WhatsApp
 *   Conexões      · Marcas / Monitor
 *   Configuração  · Configurações / Equipe
 *
 * The former "Integrações" nav item is folded into "Conexões" — both the
 * /conexoes and /integrations routes point to the same Conexoes page.
 * The former separate "Conexão" (WhatsApp-only) is now embedded inside Conexoes.
 * The standalone /conexao route is kept for back-compat (direct WAHA management).
 *
 * WhatsApp (`/whatsapp-chat`) is back in nav as of the SocialDashboardShell
 * remodel (componentization wave, N=3) — it's now a full dashboard (Chat +
 * Configurações subtabs), not just the connection-scoped Chat tab MarcaModal
 * already surfaces. The `whatsapp_chat` status_pagina row already exists
 * (migration 014, status='producao') from when this route was last in nav —
 * no new migration needed to make it visible again.
 * pt-BR copy preserved.
 */
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
  KanbanSquare,
  Workflow,
  TrendingUp,
  UserCheck,
  GitMerge,
  CalendarClock,
  BarChart3,
  Globe,
} from "lucide-react";

import { lazyWithReload } from "@noctusai/lib";

// Pages
const Landing = lazyWithReload(() => import("@/pages/Landing"));
const Login = lazyWithReload(() => import("@/pages/Login"));
const AcceptInvite = lazyWithReload(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazyWithReload(() => import("@/pages/ForgotPassword"));
const Chat = lazyWithReload(() => import("@/pages/Chat"));
const Dashboard = lazyWithReload(() => import("@/pages/Dashboard"));
const Equipe = lazyWithReload(() => import("@/pages/Equipe"));
const Settings = lazyWithReload(() => import("@/pages/Settings"));
const YouTube = lazyWithReload(() => import("@/pages/YouTube"));
const N8n = lazyWithReload(() => import("@/pages/N8n"));
const RedirectToMarcas = lazyWithReload(() => import("@/pages/RedirectToMarcas"));
const RedirectToMeta = lazyWithReload(() => import("@/pages/RedirectToMeta"));
const Monitor = lazyWithReload(() => import("@/pages/Monitor"));
const MediaCreation = lazyWithReload(() => import("@/pages/MediaCreation"));
const EmailMarketing = lazyWithReload(() => import("@/pages/EmailMarketing"));
const Contatos = lazyWithReload(() => import("@/pages/Contatos"));
const EmailListas = lazyWithReload(() => import("@/pages/EmailListas"));
const EmailTemplates = lazyWithReload(() => import("@/pages/EmailTemplates"));
const EmailCampanhas = lazyWithReload(() => import("@/pages/EmailCampanhas"));
const EmailMarketingConfig = lazyWithReload(() => import("@/pages/EmailMarketingConfig"));
const EmailMembros = lazyWithReload(() => import("@/pages/EmailMembros"));
const NotFound = lazyWithReload(() => import("@/pages/NotFound"));
const WhatsAppChat = lazyWithReload(() => import("@/pages/WhatsAppChat"));
const Marcas = lazyWithReload(() => import("@/pages/Marcas"));
const Imoveis = lazyWithReload(() => import("@/pages/Imoveis"));
const ImovelDetalhes = lazyWithReload(() => import("@/pages/ImovelDetalhes"));
const MetaDashboard = lazyWithReload(() => import("@/pages/MetaDashboard"));
const Leads = lazyWithReload(() => import("@/pages/leads/Leads"));
const FunilVendas = lazyWithReload(() => import("@/pages/funil/FunilVendas"));
const ProcessosVenda = lazyWithReload(() => import("@/pages/funil/ProcessosVenda"));
const PortalRoi = lazyWithReload(() => import("@/pages/PortalRoi"));
const ClientesBoard = lazyWithReload(() => import("@/pages/clientes/ClientesBoard"));
const RevisaoFila = lazyWithReload(() => import("@/pages/clientes/RevisaoFila"));
const Agendamentos = lazyWithReload(() => import("@/pages/scheduling/Agendamentos"));
const EmailPainel = lazyWithReload(() => import("@/pages/email/Painel"));
const EmailCampanhasNoc = lazyWithReload(() => import("@/pages/email/Campanhas"));
const EmailContatosNoc = lazyWithReload(() => import("@/pages/email/Contatos"));
const EmailListasNoc = lazyWithReload(() => import("@/pages/email/Listas"));
const EmailTemplatesNoc = lazyWithReload(() => import("@/pages/email/Templates"));
const EmailAutomacoes = lazyWithReload(() => import("@/pages/email/Automacoes"));
const EmailDominios = lazyWithReload(() => import("@/pages/email/Dominios"));

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
      { name: "WhatsApp", href: "/whatsapp-chat", icon: Smartphone, route: "whatsapp_chat" },
      { name: "Agendamentos", href: "/agendamentos", icon: CalendarClock, route: "agendamentos" },
      { name: "n8n", href: "/n8n", icon: Workflow, route: "n8n" },
      { name: "Imóveis", href: "/imoveis", icon: Building2, route: "imoveis" },
    ],
  },
  {
    // Leads is a GROUP, not a single item: the base surface and the two boards
    // that consume it belong together, and a lead flows Leads → Funil →
    // Processos. Each item is nav-gated by its own `status_pagina` row
    // (migration 034 seeds `funil` + `processos_venda`), so an unlisted route
    // stays hidden rather than 404-ing.
    key: "leads",
    label: "Leads",
    icon: Target,
    defaultOpen: true,
    items: [
      { name: "Leads", href: "/leads", icon: Target, route: "leads" },
      { name: "Funil de Vendas", href: "/funil", icon: KanbanSquare, route: "funil" },
      { name: "Processos de Venda", href: "/processos-venda", icon: Workflow, route: "processos_venda" },
      { name: "ROI por Portal", href: "/portal-roi", icon: TrendingUp, route: "portal_roi" },
    ],
  },
  {
    // lead-card-hub Phase 1 (PROJECT.md) — clientes is the new PERSON layer,
    // additive alongside the leads-based group above (Phase 1 does not
    // retire `leads`; Phases 2-5 attach the rest of the card-hub here).
    // Each item is nav-gated by its own status_pagina row, owned by the
    // backend slice landing the 048 migration — not seeded yet as of this
    // slice, so both items stay hidden until that row exists.
    key: "clientes",
    label: "Clientes",
    icon: UserCheck,
    defaultOpen: true,
    items: [
      { name: "Clientes", href: "/clientes", icon: UserCheck, route: "clientes" },
      { name: "Revisão de Duplicados", href: "/clientes/revisao", icon: GitMerge, route: "clientes_revisao" },
    ],
  },
  {
    // The product's OWN mailing engine (Resend-backed, tables in
    // social_wiring). Distinct from the Mailchimp-proxy group below — two
    // different products in one app, named apart so neither is mistaken for
    // the other. Shipped 2026-09-01; the module had 62 routes and no UI.
    key: "email-noc",
    label: "Email Marketing",
    icon: Mail,
    defaultOpen: false,
    items: [
      { name: "Painel", href: "/email", icon: BarChart3, route: "email_painel" },
      { name: "Campanhas", href: "/email/campanhas", icon: Send, route: "email_campanhas_noc" },
      { name: "Contatos", href: "/email/contatos", icon: UserRound, route: "email_contatos_noc" },
      { name: "Listas", href: "/email/listas", icon: List, route: "email_listas_noc" },
      { name: "Templates", href: "/email/templates", icon: FileText, route: "email_templates_noc" },
      { name: "Automações", href: "/email/automacoes", icon: Workflow, route: "email_automacoes_noc" },
      { name: "Domínios", href: "/email/dominios", icon: Globe, route: "email_dominios_noc" },
    ],
  },
  {
    // Mailchimp-backed (a CONNECTED account proxied through /api/mailchimp/*).
    // Renamed from "Email Marketing" when the own-engine group above shipped:
    // every page here already says "sua conta Mailchimp" in its own subtitle,
    // so the label now matches the screen. No route or page changed.
    key: "email",
    label: "Mailchimp",
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
      { name: "Marcas", href: "/marcas", icon: Building2, route: "marcas" },
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
      { name: "WhatsApp", href: "/whatsapp-chat", icon: Smartphone },
      { name: "Agendamentos", href: "/agendamentos", icon: CalendarClock },
      { name: "n8n", href: "/n8n", icon: Workflow },
      { name: "Imóveis", href: "/imoveis", icon: Building2 },
    ],
  },
  {
    key: "leads",
    label: "Leads",
    icon: Target,
    defaultOpen: true,
    items: [
      { name: "Leads", href: "/leads", icon: Target },
      { name: "Funil de Vendas", href: "/funil", icon: KanbanSquare },
      { name: "Processos de Venda", href: "/processos-venda", icon: Workflow },
      { name: "ROI por Portal", href: "/portal-roi", icon: TrendingUp },
    ],
  },
  {
    key: "clientes",
    label: "Clientes",
    icon: UserCheck,
    defaultOpen: true,
    items: [
      { name: "Clientes", href: "/clientes", icon: UserCheck },
      { name: "Revisão de Duplicados", href: "/clientes/revisao", icon: GitMerge },
    ],
  },
  {
    key: "email-noc",
    label: "Email Marketing",
    icon: Mail,
    defaultOpen: false,
    items: [
      { name: "Painel", href: "/email", icon: BarChart3 },
      { name: "Campanhas", href: "/email/campanhas", icon: Send },
      { name: "Contatos", href: "/email/contatos", icon: UserRound },
      { name: "Listas", href: "/email/listas", icon: List },
      { name: "Templates", href: "/email/templates", icon: FileText },
      { name: "Automações", href: "/email/automacoes", icon: Workflow },
      { name: "Domínios", href: "/email/dominios", icon: Globe },
    ],
  },
  {
    key: "email",
    label: "Mailchimp",
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
      { name: "Marcas", href: "/marcas", icon: Building2 },
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
    { path: "/funil", component: FunilVendas },
    { path: "/processos-venda", component: ProcessosVenda },
    { path: "/portal-roi", component: PortalRoi },
    { path: "/clientes", component: ClientesBoard },
    { path: "/clientes/revisao", component: RevisaoFila },
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
    // Retired routes — connection management now lives inside MarcaModal
    { path: "/conexoes", component: RedirectToMarcas },
    { path: "/integrations", component: RedirectToMarcas },
    { path: "/conexao", component: RedirectToMarcas },
    { path: "/marcas", component: Marcas },
    { path: "/imoveis", component: Imoveis },
    { path: "/imoveis/:codigo", component: ImovelDetalhes },
    { path: "/agendamentos", component: Agendamentos },
    { path: "/email", component: EmailPainel },
    { path: "/email/campanhas", component: EmailCampanhasNoc },
    { path: "/email/contatos", component: EmailContatosNoc },
    { path: "/email/listas", component: EmailListasNoc },
    { path: "/email/templates", component: EmailTemplatesNoc },
    { path: "/email/automacoes", component: EmailAutomacoes },
    { path: "/email/dominios", component: EmailDominios },
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
