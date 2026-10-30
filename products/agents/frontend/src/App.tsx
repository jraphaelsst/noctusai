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
import { LayoutDashboard, Users, Home, Bot, CheckCircle2, KeyRound, SlidersHorizontal, Sparkles, Wallet } from "lucide-react";

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
// Every agent in the same house — `products/agents/projects/agents-unified/CONTRACT.md` §7:
// ONE listing (`/agentes`) + ONE dynamic page per agent (`/agentes/:key`).
const Agentes = lazy(() => import("@/pages/Agentes"));
const AgentePage = lazy(() => import("@/pages/agente/AgentePage"));
// The new-agent wizard (CONTRACT §6) — platform admins only; the page renders the standard not-found otherwise.
const NovoAgente = lazy(() => import("@/pages/agente/NovoAgente"));
const Aprovacoes = lazy(() => import("@/pages/Aprovacoes"));
// The former per-agent shells + listing redirect to the unified page (query kept) — see LegacyRedirects.tsx.
const redirect = (name: keyof typeof import("@/pages/LegacyRedirects")) =>
  lazy(() => import("@/pages/LegacyRedirects").then((m) => ({ default: m[name] })));
const RedirectStudioAgent = redirect("RedirectStudioAgent");
const RedirectStudio = redirect("RedirectStudio");
const RedirectAgentePersona = redirect("RedirectAgentePersona");
const RedirectCatalogo = redirect("RedirectCatalogo");
const RedirectAcademiaChat = redirect("RedirectAcademiaChat");
const RedirectAcademiaPersona = redirect("RedirectAcademiaPersona");
const RedirectLeadImobStudioToJulia = redirect("RedirectLeadImobStudioToJulia");
// Platform-admin pages (server-enforced by `require_platform_admin`).
const Credenciais = lazy(() => import("@/pages/Credenciais"));
const ChavesIA = lazy(() => import("@/pages/ChavesIA"));
const ConfiguracoesAgente = lazy(() => import("@/pages/ConfiguracoesAgente"));
// Agent Studio leftovers — `products/agents/projects/agent-studio-isaia/CONTRACT.md` §G. The `/studio` console
// itself folded into `/agentes` (create = the wizard, import / delete / content token = the listing).
const SkillsBiblioteca = lazy(() => import("@/pages/studio/SkillsBiblioteca"));
const SkillBiblioteca = lazy(() => import("@/pages/studio/SkillBiblioteca"));
const PromptByHash = lazy(() => import("@/pages/studio/PromptByHash"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Agentes", href: "/agentes", icon: Bot, route: "agentes" },
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
      { name: "Agentes", href: "/agentes", icon: Bot },
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
    { path: "/agentes", component: Agentes },
    // react-router ranks static segments above `:key`, so these never read as an agent key.
    { path: "/agentes/catalogo", component: RedirectCatalogo },
    { path: "/agentes/novo", component: NovoAgente },
    { path: "/agentes/julia/persona", component: RedirectAcademiaPersona },
    { path: "/agentes/bia/persona", component: RedirectAcademiaPersona },
    { path: "/agentes/bia/conversar", component: RedirectAcademiaChat },
    { path: "/agentes/:key/persona", component: RedirectAgentePersona },
    { path: "/agentes/:key", component: AgentePage },
    { path: "/bia", component: RedirectAcademiaChat },
    { path: "/julia", component: RedirectAcademiaChat },
    { path: "/aprovacoes", component: Aprovacoes },
    { path: "/equipe", component: Equipe },
    { path: "/financeiro/*", component: Financeiro },
    { path: "/credenciais", component: Credenciais },
    { path: "/chaves-ia", component: ChavesIA },
    { path: "/configuracoes-agente", component: ConfiguracoesAgente },
    { path: "/studio", component: RedirectStudio },
    // Declared before `/studio/:key` for readability; react-router ranks the
    // static `prompts` segment above the `:key` param regardless.
    { path: "/studio/prompts/:hash", component: PromptByHash },
    { path: "/studio/biblioteca-skills", component: SkillsBiblioteca },
    { path: "/studio/biblioteca-skills/:chave", component: SkillBiblioteca },
    { path: "/studio/lead-imob", component: RedirectLeadImobStudioToJulia },
    { path: "/studio/:key", component: RedirectStudioAgent },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
