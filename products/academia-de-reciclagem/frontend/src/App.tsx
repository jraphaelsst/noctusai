/**
 * Academia de Reciclagem App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, Recycle, BookOpen, Scale, HelpCircle, ListTodo, UserPlus } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Domain pages — contract `projects/julia-agents-academia-CONTRACT.md` §B.1-B.4.
const Kb = lazy(() => import("@/pages/Kb"));
const KbDetail = lazy(() => import("@/pages/KbDetail"));
const Decisoes = lazy(() => import("@/pages/Decisoes"));
const Perguntas = lazy(() => import("@/pages/Perguntas"));
const Roadmap = lazy(() => import("@/pages/Roadmap"));
// Public site — contract `projects/interessados-CONTRACT.md`.
const OProjeto = lazy(() => import("@/pages/OProjeto"));
const ACarta = lazy(() => import("@/pages/ACarta"));
const Interessados = lazy(() => import("@/pages/Interessados"));
const ComoFuncionaRedirect = lazy(() => import("@/pages/ComoFuncionaRedirect"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Base de conhecimento", href: "/kb", icon: BookOpen, route: "kb" },
      { name: "Decisões", href: "/decisoes", icon: Scale, route: "decisoes" },
      { name: "Perguntas abertas", href: "/perguntas", icon: HelpCircle, route: "perguntas" },
      { name: "Roadmap e tarefas", href: "/roadmap", icon: ListTodo, route: "roadmap" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
      { name: "Interessados", href: "/interessados", icon: UserPlus, route: "interessados" },
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
      { name: "Base de conhecimento", href: "/kb", icon: BookOpen },
      { name: "Decisões", href: "/decisoes", icon: Scale },
      { name: "Perguntas abertas", href: "/perguntas", icon: HelpCircle },
      { name: "Roadmap e tarefas", href: "/roadmap", icon: ListTodo },
      { name: "Equipe", href: "/equipe", icon: Users },
      { name: "Interessados", href: "/interessados", icon: UserPlus },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Recycle,
  brandTitle: "Academia de Reciclagem",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/kb", component: Kb },
    { path: "/kb/:slug", component: KbDetail },
    { path: "/decisoes", component: Decisoes },
    { path: "/perguntas", component: Perguntas },
    { path: "/roadmap", component: Roadmap },
    { path: "/equipe", component: Equipe },
    { path: "/interessados", component: Interessados },
  ],
  // Public site — reachable regardless of auth state (contract `projects/
  // interessados-CONTRACT.md`). Header/footer/nav are shared with `Landing`
  // via `components/site/`.
  publicRoutes: [
    { path: "/o-projeto", component: OProjeto },
    // Old path, kept alive as a redirect — see the component's own doc.
    { path: "/como-funciona", component: ComoFuncionaRedirect },
    { path: "/a-carta", component: ACarta },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
