/**
 * ERP Imobiliario App — born from the seed frontend framework.
 *
 * Real estate CRM: clients, properties, deals, financials, marketing.
 * Uses createProductApp for structure + createProductLayout with enrichment
 * for domain-specific layout (DB profile, role-based admin panel, theme persistence).
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import { useERPLayoutEnrichment } from "@/hooks/useLayoutEnrichment";
import type { NavGroupWithRoute } from "@noctusai/shared";
import type { NavGroup } from "@noctusai/shared/design-system";
import type { NavItemWithRoute } from "@noctusai/shared";
import {
  Home, Target, Building2, LayoutDashboard, UserCircle, HomeIcon,
  ArrowLeftRight, FileText, ScrollText, Building, Percent, DollarSign,
  Receipt, Landmark, CreditCard, ClipboardList, CalendarDays, Search,
  Hammer, Key, MapPin, ShieldCheck, Megaphone, Mail, MessageSquare,
  Instagram, BellRing, FileBox, FileSignature, Globe, Users, Store,
  BarChart3, Sparkles, Trophy, GitBranch, Settings, Briefcase,
} from "lucide-react";

// ── Pages ────────────────────────────────────────────────────
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Funil = lazy(() => import("@/pages/Funil"));
const Clientes = lazy(() => import("@/pages/Clientes"));
const ClienteDetalhes = lazy(() => import("@/pages/ClienteDetalhes"));
const Imoveis = lazy(() => import("@/pages/Imoveis"));
const ImovelDetalhes = lazy(() => import("@/pages/ImovelDetalhes"));
const Condominios = lazy(() => import("@/pages/Condominios"));
const Permutas = lazy(() => import("@/pages/Permutas"));
const PermutaDetalhes = lazy(() => import("@/pages/PermutaDetalhes"));
const Negociacoes = lazy(() => import("@/pages/Negociacoes"));
const Metas = lazy(() => import("@/pages/Metas"));
const Usuarios = lazy(() => import("@/pages/Usuarios"));
const Admin = lazy(() => import("@/pages/Admin"));
const Comissoes = lazy(() => import("@/pages/Comissoes"));
const Portais = lazy(() => import("@/pages/Portais"));
const Financeiro = lazy(() => import("@/pages/Financeiro"));
const Propostas = lazy(() => import("@/pages/Propostas"));
const PropostaDetalhes = lazy(() => import("@/pages/PropostaDetalhes"));
const Documentos = lazy(() => import("@/pages/Documentos"));
const Locacoes = lazy(() => import("@/pages/Locacoes"));
const LocacaoDetalhes = lazy(() => import("@/pages/LocacaoDetalhes"));
const Vistorias = lazy(() => import("@/pages/Vistorias"));
const VistoriaDetalhes = lazy(() => import("@/pages/VistoriaDetalhes"));
const Relatorios = lazy(() => import("@/pages/Relatorios"));
const Distribuicao = lazy(() => import("@/pages/Distribuicao"));
const Marketing = lazy(() => import("@/pages/Marketing"));
const Agenda = lazy(() => import("@/pages/Agenda"));
const Dimob = lazy(() => import("@/pages/Dimob"));
const Gamificacao = lazy(() => import("@/pages/Gamificacao"));
const Chaves = lazy(() => import("@/pages/Chaves"));
const PortalExterno = lazy(() => import("@/pages/PortalExterno"));
const SiteImoveis = lazy(() => import("@/pages/SiteImoveis"));
const Campo = lazy(() => import("@/pages/Campo"));
const AnaliseCredito = lazy(() => import("@/pages/AnaliseCredito"));
const Filiais = lazy(() => import("@/pages/Filiais"));
const Contratos = lazy(() => import("@/pages/Contratos"));
const ContratoDetalhes = lazy(() => import("@/pages/ContratoDetalhes"));
const Assinaturas = lazy(() => import("@/pages/Assinaturas"));
const PortalCliente = lazy(() => import("@/pages/PortalCliente"));
const Manutencao = lazy(() => import("@/pages/Manutencao"));
const Seguros = lazy(() => import("@/pages/Seguros"));
const Impostos = lazy(() => import("@/pages/Impostos"));
const Banco = lazy(() => import("@/pages/Banco"));
const Emails = lazy(() => import("@/pages/Emails"));
const BI = lazy(() => import("@/pages/BI"));
const Matching = lazy(() => import("@/pages/Matching"));
const Configuracoes = lazy(() => import("@/pages/Configuracoes"));
const MetaAds = lazy(() => import("@/pages/MetaAds"));
const WhatsAppInbox = lazy(() => import("@/pages/WhatsAppInbox"));
const NotificacoesPage = lazy(() => import("@/pages/Notificacoes"));
const Certidoes = lazy(() => import("@/pages/Certidoes"));
const Matriculas = lazy(() => import("@/pages/Matriculas"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const LogAcoes = lazy(() => import("@/pages/LogAcoes"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// ── Nav ──────────────────────────────────────────────────────

const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal", label: "Principal", icon: Home, defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/dashboard", icon: Home, route: "dashboard" },
      { name: "Funil de Vendas", href: "/funil", icon: LayoutDashboard, route: "funil" },
      { name: "Clientes", href: "/clientes", icon: UserCircle, route: "clientes" },
      { name: "Metas", href: "/metas", icon: Target, route: "metas" },
    ],
  },
  {
    key: "comercial", label: "Comercial", icon: Briefcase, defaultOpen: true,
    items: [
      { name: "Imoveis", href: "/imoveis", icon: HomeIcon, route: "imoveis" },
      { name: "Condominios", href: "/condominios", icon: Building2, route: "condominios" },
      { name: "Permutas", href: "/permutas", icon: ArrowLeftRight, route: "permutas" },
      { name: "Negociacoes", href: "/negociacoes", icon: FileText, route: "negociacoes" },
      { name: "Propostas", href: "/propostas", icon: ScrollText, route: "propostas" },
      { name: "Contratos", href: "/contratos", icon: FileText, route: "contratos" },
      { name: "Locacoes", href: "/locacoes", icon: Building, route: "locacoes" },
      { name: "Comissoes", href: "/comissoes", icon: Percent, route: "comissoes" },
    ],
  },
  {
    key: "financeiro", label: "Financeiro", icon: DollarSign,
    items: [
      { name: "Financeiro", href: "/financeiro", icon: DollarSign, route: "financeiro" },
      { name: "Impostos", href: "/impostos", icon: Receipt, route: "impostos" },
      { name: "Banco", href: "/banco", icon: Landmark, route: "banco" },
      { name: "Analise de Credito", href: "/analise-credito", icon: CreditCard, route: "analise-credito" },
    ],
  },
  {
    key: "operacional", label: "Operacional", icon: ClipboardList,
    items: [
      { name: "Agenda", href: "/agenda", icon: CalendarDays, route: "agenda" },
      { name: "Vistorias", href: "/vistorias", icon: Search, route: "vistorias" },
      { name: "Manutencao", href: "/manutencao", icon: Hammer, route: "manutencao" },
      { name: "Chaves", href: "/chaves", icon: Key, route: "chaves" },
      { name: "Campo", href: "/campo", icon: MapPin, route: "campo" },
      { name: "Seguros", href: "/seguros", icon: ShieldCheck, route: "seguros" },
    ],
  },
  {
    key: "marketing", label: "Marketing & Comunicacao", icon: Megaphone,
    items: [
      { name: "Marketing", href: "/marketing", icon: Megaphone, route: "marketing" },
      { name: "Emails", href: "/emails", icon: Mail, route: "emails" },
      { name: "WhatsApp", href: "/whatsapp", icon: MessageSquare, route: "whatsapp" },
      { name: "Meta Ads", href: "/meta-ads", icon: Instagram, route: "meta-ads" },
      { name: "Notificacoes", href: "/notificacoes", icon: BellRing, route: "notificacoes" },
    ],
  },
  {
    key: "documentos", label: "Documentos", icon: FileBox,
    items: [
      { name: "Documentos", href: "/documentos", icon: FileBox, route: "documentos" },
      { name: "Certidoes", href: "/certidoes", icon: ShieldCheck, route: "certidoes" },
      { name: "Matriculas", href: "/matriculas", icon: FileText, route: "matriculas" },
      { name: "Assinaturas", href: "/assinaturas", icon: FileSignature, route: "assinaturas" },
      { name: "DIMOB", href: "/dimob", icon: FileText, route: "dimob" },
      { name: "Relatorios", href: "/relatorios", icon: ClipboardList, route: "relatorios" },
    ],
  },
  {
    key: "portais", label: "Portais & Site", icon: Globe,
    items: [
      { name: "Portal Cliente", href: "/portal-cliente", icon: Users, route: "portal-cliente" },
      { name: "Portal Externo", href: "/portal", icon: Globe, route: "portal" },
      { name: "Site Imoveis", href: "/site", icon: Store, route: "site" },
    ],
  },
  {
    key: "analytics", label: "Analytics & IA", icon: BarChart3,
    items: [
      { name: "BI", href: "/bi", icon: BarChart3, route: "bi" },
      { name: "Matching IA", href: "/matching", icon: Sparkles, route: "matching" },
      { name: "Gamificacao", href: "/gamificacao", icon: Trophy, route: "gamificacao" },
    ],
  },
];

const STANDALONE: NavItemWithRoute[] = [
  { name: "Distribuicao", href: "/distribuicao", icon: GitBranch, route: "distribuicao" },
  { name: "Filiais", href: "/filiais", icon: Building, route: "filiais" },
  { name: "Configuracoes", href: "/configuracoes", icon: Settings, route: "configuracoes" },
];

const NAV_FALLBACK: NavGroup[] = NAV_GROUPS.map(g => ({
  ...g, items: g.items.map(({ route, ...item }) => item),
})) as NavGroup[];

// ── Layout from framework + ERP enrichment ───────────────────

const Layout = createProductLayout({
  brandIcon: Building2,
  brandTitle: "ONE",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  standaloneItems: STANDALONE,
  supabase,
  useAuthStore,
  NotificationBell,
  brandSubtitleOverride: undefined, // enrichment provides org name
  useLayoutEnrichment: useERPLayoutEnrichment,
});

// ── App from framework ───────────────────────────────────────

export default createProductApp({
  routes: [
    { path: "/dashboard", component: Dashboard },
    { path: "/funil", component: Funil },
    { path: "/clientes", component: Clientes },
    { path: "/clientes/:id", component: ClienteDetalhes },
    { path: "/imoveis", component: Imoveis },
    { path: "/imoveis/:id", component: ImovelDetalhes },
    { path: "/condominios", component: Condominios },
    { path: "/permutas", component: Permutas },
    { path: "/permutas/:id", component: PermutaDetalhes },
    { path: "/negociacoes", component: Negociacoes },
    { path: "/metas", component: Metas },
    { path: "/usuarios", component: Usuarios },
    { path: "/admin", component: Admin },
    { path: "/comissoes", component: Comissoes },
    { path: "/portais", component: Portais },
    { path: "/financeiro", component: Financeiro },
    { path: "/propostas", component: Propostas },
    { path: "/propostas/:id", component: PropostaDetalhes },
    { path: "/documentos", component: Documentos },
    { path: "/locacoes", component: Locacoes },
    { path: "/locacoes/:id", component: LocacaoDetalhes },
    { path: "/vistorias", component: Vistorias },
    { path: "/vistorias/:id", component: VistoriaDetalhes },
    { path: "/relatorios", component: Relatorios },
    { path: "/distribuicao", component: Distribuicao },
    { path: "/marketing", component: Marketing },
    { path: "/agenda", component: Agenda },
    { path: "/dimob", component: Dimob },
    { path: "/gamificacao", component: Gamificacao },
    { path: "/chaves", component: Chaves },
    { path: "/portal", component: PortalExterno },
    { path: "/site", component: SiteImoveis },
    { path: "/campo", component: Campo },
    { path: "/analise-credito", component: AnaliseCredito },
    { path: "/filiais", component: Filiais },
    { path: "/contratos", component: Contratos },
    { path: "/contratos/:id", component: ContratoDetalhes },
    { path: "/assinaturas", component: Assinaturas },
    { path: "/portal-cliente", component: PortalCliente },
    { path: "/manutencao", component: Manutencao },
    { path: "/seguros", component: Seguros },
    { path: "/impostos", component: Impostos },
    { path: "/banco", component: Banco },
    { path: "/emails", component: Emails },
    { path: "/bi", component: BI },
    { path: "/matching", component: Matching },
    { path: "/configuracoes", component: Configuracoes },
    { path: "/meta-ads", component: MetaAds },
    { path: "/whatsapp", component: WhatsAppInbox },
    { path: "/notificacoes", component: NotificacoesPage },
    { path: "/certidoes", component: Certidoes },
    { path: "/matriculas", component: Matriculas },
    { path: "/equipe", component: Equipe },
    { path: "/log-acoes", component: LogAcoes },
  ],
  Layout,
  supabase,
  useAuthStore,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
