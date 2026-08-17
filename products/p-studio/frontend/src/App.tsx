/**
 * P Studio App — house seed standard.
 *
 * Infrastructure comes from @noctusai/seed/infra (one createProductInfra
 * call, schema defaults to "public" — this product's FE only ever talks
 * to Supabase for `.auth`; every domain read/write goes through the
 * FastAPI backend, so the schema option is irrelevant here). Structure
 * comes from createProductApp + createProductLayout, same shape as
 * social-wiring / igig.
 *
 * Auth: standard Supabase session (infra.appConfig), the same mechanism
 * every other product uses — NOT the bespoke `useAuth` zustand store +
 * `/api/me` health-gate the product carried while it lived outside noc.
 * That store is gone; the piece of it that mattered (an anonymous visitor
 * must never reach a protected route) is enforced identically here by
 * createProductApp's own `!user` gate. See PROJECT.md /
 * p-studio-fe-seed-standard branch notes for the full trade-off writeup.
 *
 * No Landing page (direct-to-login product, same as the pre-existing
 * shape) — `unauthRedirect="/login"` is REQUIRED here per
 * ProductAppConfig's own doc comment, to avoid the "/" redirect loop
 * that fires when no Landing is configured.
 */
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from "@noctusai/seed/infra";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import { lazyWithReload } from "@noctusai/lib";
import {
  LayoutDashboard,
  KanbanSquare,
  Calendar,
  Clapperboard,
  Building2,
  ListChecks,
  Wallet,
  Camera,
  Users,
  Home,
} from "lucide-react";

// Pages
const Login = lazyWithReload(() => import("@/pages/Login"));
const Dashboard = lazyWithReload(() => import("@/pages/Dashboard"));
const CRM = lazyWithReload(() => import("@/pages/CRM"));
const Agenda = lazyWithReload(() => import("@/pages/Agenda"));
const Producao = lazyWithReload(() => import("@/pages/Producao"));
const Imoveis = lazyWithReload(() => import("@/pages/Imoveis"));
const Servicos = lazyWithReload(() => import("@/pages/Servicos"));
const Financeiro = lazyWithReload(() => import("@/pages/Financeiro"));
const Equipamentos = lazyWithReload(() => import("@/pages/Equipamentos"));
const Clientes = lazyWithReload(() => import("@/pages/Clientes"));
const NotFound = lazyWithReload(() => import("@/pages/NotFound"));

// Nav — os nove destinos do produto, mesma ordem/labels do AppLayout anterior.
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "CRM Comercial", href: "/crm", icon: KanbanSquare, route: "crm" },
      { name: "Agenda", href: "/agenda", icon: Calendar, route: "agenda" },
      { name: "Produção", href: "/producao", icon: Clapperboard, route: "producao" },
      { name: "Imóveis", href: "/imoveis", icon: Building2, route: "imoveis" },
      { name: "Serviços", href: "/servicos", icon: ListChecks, route: "servicos" },
      { name: "Financeiro", href: "/financeiro", icon: Wallet, route: "financeiro" },
      { name: "Equipamentos", href: "/equipamentos", icon: Camera, route: "equipamentos" },
      { name: "Clientes", href: "/clientes", icon: Users, route: "clientes" },
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
      { name: "CRM Comercial", href: "/crm", icon: KanbanSquare },
      { name: "Agenda", href: "/agenda", icon: Calendar },
      { name: "Produção", href: "/producao", icon: Clapperboard },
      { name: "Imóveis", href: "/imoveis", icon: Building2 },
      { name: "Serviços", href: "/servicos", icon: ListChecks },
      { name: "Financeiro", href: "/financeiro", icon: Wallet },
      { name: "Equipamentos", href: "/equipamentos", icon: Camera },
      { name: "Clientes", href: "/clientes", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: Camera,
  brandTitle: "P Studio",
  brandSubtitleOverride: "Operação e Financeiro",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/crm", component: CRM },
    { path: "/agenda", component: Agenda },
    { path: "/producao", component: Producao },
    { path: "/imoveis", component: Imoveis },
    { path: "/servicos", component: Servicos },
    { path: "/financeiro", component: Financeiro },
    { path: "/equipamentos", component: Equipamentos },
    { path: "/clientes", component: Clientes },
  ],
  Layout,
  ...infra.appConfig,
  Login,
  NotFound,
  // No Landing page (product goes straight to login, same as before) —
  // required per ProductAppConfig's own doc comment to avoid the "/"
  // redirect loop that a Landing-less product hits otherwise.
  unauthRedirect: "/login",
});
