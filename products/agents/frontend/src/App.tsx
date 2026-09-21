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
import { LayoutDashboard, Users, Home, Bot, MessageCircle, CheckCircle2, KeyRound, SlidersHorizontal, Boxes } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Julia agents UI — contract §E (`projects/julia-agents-academia-CONTRACT.md`).
const Julia = lazy(() => import("@/pages/Julia"));
const Agentes = lazy(() => import("@/pages/Agentes"));
const JuliaPersona = lazy(() => import("@/pages/JuliaPersona"));
const Aprovacoes = lazy(() => import("@/pages/Aprovacoes"));
// Platform-admin pages (server-enforced by `require_platform_admin`).
const Credenciais = lazy(() => import("@/pages/Credenciais"));
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
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Julia", href: "/julia", icon: MessageCircle, route: "julia" },
      { name: "Agentes", href: "/agentes", icon: Bot, route: "agentes" },
      { name: "Agent Studio", href: "/studio", icon: Boxes, route: "studio" },
      { name: "Aprovações", href: "/aprovacoes", icon: CheckCircle2, route: "aprovacoes" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Configurações do agente", href: "/configuracoes-agente", icon: SlidersHorizontal, route: "configuracoes-agente" },
      { name: "Credenciais", href: "/credenciais", icon: KeyRound, route: "credenciais" },
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
      { name: "Julia", href: "/julia", icon: MessageCircle },
      { name: "Agentes", href: "/agentes", icon: Bot },
      { name: "Agent Studio", href: "/studio", icon: Boxes },
      { name: "Aprovações", href: "/aprovacoes", icon: CheckCircle2 },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Configurações do agente", href: "/configuracoes-agente", icon: SlidersHorizontal },
      { name: "Credenciais", href: "/credenciais", icon: KeyRound },
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
    { path: "/julia", component: Julia },
    { path: "/agentes", component: Agentes },
    { path: "/agentes/julia/persona", component: JuliaPersona },
    { path: "/aprovacoes", component: Aprovacoes },
    { path: "/equipe", component: Equipe },
    { path: "/credenciais", component: Credenciais },
    { path: "/configuracoes-agente", component: ConfiguracoesAgente },
    { path: "/studio", component: StudioList },
    // Declared before `/studio/:key` for readability; react-router ranks the
    // static `prompts` segment above the `:key` param regardless.
    { path: "/studio/prompts/:hash", component: PromptByHash },
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
