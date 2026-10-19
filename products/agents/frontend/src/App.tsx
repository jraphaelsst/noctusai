/**
 * Agentes App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, Bot, MessageCircle, CheckCircle2, KeyRound, SlidersHorizontal, Boxes, Sparkles, Wallet } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Finance organ (seed `FinanceShell`) -- `/financeiro/*`; section in the URL.
const Financeiro = lazy(() => import("@/pages/Financeiro"));
// Bia agents UI — contract §E (`projects/julia-agents-academia-CONTRACT.md`).
const Bia = lazy(() => import("@/pages/Bia"));
const Agentes = lazy(() => import("@/pages/Agentes"));
const BiaPersona = lazy(() => import("@/pages/BiaPersona"));
const Aprovacoes = lazy(() => import("@/pages/Aprovacoes"));
// Pre-rename routes (Julia -> Bia, lead-imob -> julia) — NOC-REMEDIATE[drop-julia-route-redirects].
const RedirectJuliaToBia = lazy(() => import("@/pages/LegacyRedirects").then((m) => ({ default: m.RedirectJuliaToBia })));
const RedirectJuliaPersonaToBia = lazy(() => import("@/pages/LegacyRedirects").then((m) => ({ default: m.RedirectJuliaPersonaToBia })));
const RedirectLeadImobStudioToJulia = lazy(() => import("@/pages/LegacyRedirects").then((m) => ({ default: m.RedirectLeadImobStudioToJulia })));
// Platform-admin pages (server-enforced by `require_platform_admin`).
const Credenciais = lazy(() => import("@/pages/Credenciais"));
const ChavesIA = lazy(() => import("@/pages/ChavesIA"));
const ConfiguracoesAgente = lazy(() => import("@/pages/ConfiguracoesAgente"));
// Agent Studio — `products/agents/projects/agent-studio-isaia/CONTRACT.md` §G.
const StudioList = lazy(() => import("@/pages/studio/StudioList"));
const StudioAgent = lazy(() => import("@/pages/studio/StudioAgent"));
const PromptByHash = lazy(() => import("@/pages/studio/PromptByHash"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Bia", href: "/bia", icon: MessageCircle, route: "bia" },
      { name: "Agentes", href: "/agentes", icon: Bot, route: "agentes" },
      { name: "Agent Studio", href: "/studio", icon: Boxes, route: "studio" },
      { name: "Aprovações", href: "/aprovacoes", icon: CheckCircle2, route: "aprovacoes" },
    ],
  },
  {
    key: "configuracao",
    label: "Configuração",
    icon: SlidersHorizontal,
    items: [
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Financeiro", href: "/financeiro", icon: Wallet, route: "financeiro" },
      { name: "Configurações do agente", href: "/configuracoes-agente", icon: SlidersHorizontal, route: "configuracoes-agente" },
      { name: "Credenciais", href: "/credenciais", icon: KeyRound, route: "credenciais" },
      { name: "Chaves de IA", href: "/chaves-ia", icon: Sparkles, route: "chaves-ia" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard },
      { name: "Bia", href: "/bia", icon: MessageCircle },
      { name: "Agentes", href: "/agentes", icon: Bot },
      { name: "Agent Studio", href: "/studio", icon: Boxes },
      { name: "Aprovações", href: "/aprovacoes", icon: CheckCircle2 },
    ],
  },
  {
    key: "configuracao",
    label: "Configuração",
    icon: SlidersHorizontal,
    items: [
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Financeiro", href: "/financeiro", icon: Wallet },
      { name: "Configurações do agente", href: "/configuracoes-agente", icon: SlidersHorizontal },
      { name: "Credenciais", href: "/credenciais", icon: KeyRound },
      { name: "Chaves de IA", href: "/chaves-ia", icon: Sparkles },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Bot,
  brandTitle: "Agentes",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/bia", component: Bia },
    { path: "/agentes", component: Agentes },
    { path: "/agentes/bia/persona", component: BiaPersona },
    { path: "/julia", component: RedirectJuliaToBia },
    { path: "/agentes/julia/persona", component: RedirectJuliaPersonaToBia },
    { path: "/aprovacoes", component: Aprovacoes },
    { path: "/equipe", component: Equipe },
    { path: "/financeiro/*", component: Financeiro },
    { path: "/credenciais", component: Credenciais },
    { path: "/chaves-ia", component: ChavesIA },
    { path: "/configuracoes-agente", component: ConfiguracoesAgente },
    { path: "/studio", component: StudioList },
    // Declared before `/studio/:key` for readability; react-router ranks the
    // static `prompts` segment above the `:key` param regardless.
    { path: "/studio/prompts/:hash", component: PromptByHash },
    { path: "/studio/lead-imob", component: RedirectLeadImobStudioToJulia },
    { path: "/studio/:key", component: StudioAgent },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
