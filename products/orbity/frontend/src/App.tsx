/**
 * Orbity App — agency-management SaaS routes + nav.
 *
 * Infrastructure comes from @/infra (one file, one createProductInfra call).
 * Structure comes from createProductApp + createProductLayout.
 * This file only defines pages — nav lives in `nav/navGroups.ts` (seed module groups).
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import { Box } from "lucide-react";
import { NAV_GROUPS, NAV_FALLBACK, STANDALONE_ITEMS, STANDALONE_FALLBACK } from "@/nav/navGroups";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
// Public pages — no auth required
const RelatorioPublico = lazy(() => import("@/pages/RelatorioPublico"));
const AprovacaoPublica = lazy(() => import("@/pages/AprovacaoPublica"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Financeiro = lazy(() => import("@/pages/Financeiro"));
// CRM module
const Clientes = lazy(() => import("@/pages/Clientes"));
const Funil = lazy(() => import("@/pages/Funil"));
// Tasks + Agenda + Routines module
const Tarefas = lazy(() => import("@/pages/Tarefas"));
const Agenda = lazy(() => import("@/pages/Agenda"));
const Rotinas = lazy(() => import("@/pages/Rotinas"));
const Relatorios = lazy(() => import("@/pages/Relatorios"));
// Meta Ads / Tráfego module
const Trafego = lazy(() => import("@/pages/Trafego"));
const Automacao = lazy(() => import("@/pages/Automacao"));
const Whatsapp = lazy(() => import("@/pages/Whatsapp"));
// Content / Social Studio module
const Conteudo = lazy(() => import("@/pages/Conteudo"));

const Layout = createProductLayout({
  brandIcon: Box,
  brandTitle: "Orbity",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  standaloneItems: STANDALONE_ITEMS,
  standaloneItemsFallback: STANDALONE_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  publicRoutes: [
    { path: "/relatorio/:token", component: RelatorioPublico },
    { path: "/aprovar/:token", component: AprovacaoPublica },
  ],
  routes: [
    { path: "/", component: Dashboard },
    { path: "/equipe", component: Equipe },
    { path: "/financeiro/*", component: Financeiro }, // splat: the organ owns /financeiro/<section>
    { path: "/clientes", component: Clientes },
    { path: "/funil", component: Funil },
    { path: "/tarefas", component: Tarefas },
    { path: "/agenda", component: Agenda },
    { path: "/rotinas", component: Rotinas },
    { path: "/relatorios", component: Relatorios },
    { path: "/trafego", component: Trafego },
    { path: "/automacao", component: Automacao },
    { path: "/whatsapp", component: Whatsapp },
    { path: "/conteudo", component: Conteudo },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
