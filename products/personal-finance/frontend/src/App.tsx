/**
 * Personal Finance App — born from the seed frontend framework.
 *
 * Financial management: accounts, transactions, budgets, goals, investments.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import {
  LayoutDashboard, Users, Home, DollarSign, Wallet, ArrowLeftRight,
  Tags, PiggyBank, Target, CalendarClock, LineChart, TrendingUp,
  Eye, ArrowUpDown, FileBarChart, Landmark,
} from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Contas = lazy(() => import("@/pages/Contas"));
const ContaDetalhes = lazy(() => import("@/pages/ContaDetalhes"));
const Transacoes = lazy(() => import("@/pages/Transacoes"));
const Categorias = lazy(() => import("@/pages/Categorias"));
const Orcamentos = lazy(() => import("@/pages/Orcamentos"));
const OrcamentoDetalhes = lazy(() => import("@/pages/OrcamentoDetalhes"));
const Metas = lazy(() => import("@/pages/Metas"));
const MetaDetalhes = lazy(() => import("@/pages/MetaDetalhes"));
const Recorrentes = lazy(() => import("@/pages/Recorrentes"));
const Carteira = lazy(() => import("@/pages/Carteira"));
const CarteiraDetalhes = lazy(() => import("@/pages/CarteiraDetalhes"));
const Watchlist = lazy(() => import("@/pages/Watchlist"));
const WatchlistDetalhes = lazy(() => import("@/pages/WatchlistDetalhes"));
const Operacoes = lazy(() => import("@/pages/Operacoes"));
const Patrimonio = lazy(() => import("@/pages/Patrimonio"));
const Relatorios = lazy(() => import("@/pages/Relatorios"));
const Equipe = lazy(() => import("@/pages/Equipe"));
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
      { name: "Contas", href: "/contas", icon: Wallet, route: "contas" },
      { name: "Transacoes", href: "/transacoes", icon: ArrowLeftRight, route: "transacoes" },
      { name: "Categorias", href: "/categorias", icon: Tags, route: "categorias" },
    ],
  },
  {
    key: "planejamento",
    label: "Planejamento",
    icon: Target,
    defaultOpen: true,
    items: [
      { name: "Orcamentos", href: "/orcamentos", icon: PiggyBank, route: "orcamentos" },
      { name: "Metas", href: "/metas", icon: Target, route: "metas" },
      { name: "Recorrentes", href: "/recorrentes", icon: CalendarClock, route: "recorrentes" },
    ],
  },
  {
    key: "investimentos",
    label: "Investimentos",
    icon: LineChart,
    defaultOpen: true,
    items: [
      { name: "Investimentos", href: "/carteira", icon: TrendingUp, route: "carteira" },
      { name: "Watchlist", href: "/watchlist", icon: Eye, route: "watchlist" },
      { name: "Operacoes", href: "/operacoes", icon: ArrowUpDown, route: "operacoes" },
    ],
  },
  {
    key: "relatorios",
    label: "Relatorios",
    icon: FileBarChart,
    defaultOpen: true,
    items: [
      { name: "Patrimonio", href: "/patrimonio", icon: Landmark, route: "patrimonio" },
      { name: "Relatorios", href: "/relatorios", icon: FileBarChart, route: "relatorios" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = NAV_GROUPS.map(g => ({
  ...g,
  items: g.items.map(({ route, ...item }) => item),
})) as NavGroup[];

const Layout = createProductLayout({
  brandIcon: DollarSign,
  brandTitle: "Financas Pessoais",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
  defaultRoleLabel: "Financas Pessoais",
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/contas", component: Contas },
    { path: "/contas/:id", component: ContaDetalhes },
    { path: "/transacoes", component: Transacoes },
    { path: "/categorias", component: Categorias },
    { path: "/orcamentos", component: Orcamentos },
    { path: "/orcamentos/:id", component: OrcamentoDetalhes },
    { path: "/metas", component: Metas },
    { path: "/metas/:id", component: MetaDetalhes },
    { path: "/recorrentes", component: Recorrentes },
    { path: "/carteira", component: Carteira },
    { path: "/carteira/:id", component: CarteiraDetalhes },
    { path: "/watchlist", component: Watchlist },
    { path: "/watchlist/:id", component: WatchlistDetalhes },
    { path: "/operacoes", component: Operacoes },
    { path: "/patrimonio", component: Patrimonio },
    { path: "/relatorios", component: Relatorios },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
