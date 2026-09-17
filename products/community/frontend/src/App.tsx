/**
 * Community App — the simplest possible product.
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
import { LayoutDashboard, Users, Home, UsersRound, Boxes, UserRound, Wallet, ClipboardList, CircleDollarSign, MessageCircle, Repeat, Megaphone } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));
// Placeholder domain page — rename + replace per
// `products/seed/frontend/src/pages/Example.tsx`. Backend mirror at
// `app/routers/example_router.py`.
const Example = lazy(() => import("@/pages/Example"));

// Module 1 — Membros + Planos + Inscrições (community-m1-contract.md).
// Backend mirror at `app/routers/{membros,planos,aplicacoes}_router.py`.
const Membros = lazy(() => import("@/pages/Membros"));
const Planos = lazy(() => import("@/pages/Planos"));
const Inscricoes = lazy(() => import("@/pages/Inscricoes"));
// PUBLIC — the application form, mounted below as a `publicRoute` (no
// auth, no Layout — a visitor with no session must be able to reach it).
const Inscrever = lazy(() => import("@/pages/Inscrever"));

// Module 2 — Checkout + Pagamentos + Assinaturas (community-m2-contract.md).
// Backend mirror at `app/routers/{checkout,webhooks,assinaturas,pagamentos,
// gateway_refs}_router.py`.
const Financeiro = lazy(() => import("@/pages/Financeiro"));
// PUBLIC — the checkout form, mounted below as a `publicRoute`, same seam
// as `/inscrever` (no auth, no Layout).
const Assinar = lazy(() => import("@/pages/Assinar"));

// Module 3 — WhatsApp: grupos, sincronização, transmissões
// (community-m3-contract.md). Backend mirror at
// `app/routers/whatsapp_{grupos,lotes,transmissoes,flags}_router.py` +
// `app/routers/webhooks_router.py` (`POST /api/webhooks/whatsapp`, PUBLIC).
const WhatsApp = lazy(() => import("@/pages/WhatsApp"));
const Sincronizacao = lazy(() => import("@/pages/whatsapp/Sincronizacao"));
const Transmissoes = lazy(() => import("@/pages/whatsapp/Transmissoes"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Membros", href: "/membros", icon: UserRound, route: "membros" },
      { name: "Planos", href: "/planos", icon: Wallet, route: "planos" },
      { name: "Inscrições", href: "/inscricoes", icon: ClipboardList, route: "inscricoes" },
      { name: "Financeiro", href: "/financeiro", icon: CircleDollarSign, route: "financeiro" },
      { name: "WhatsApp", href: "/whatsapp", icon: MessageCircle, route: "whatsapp" },
      { name: "Sincronização", href: "/whatsapp/sincronizacao", icon: Repeat, route: "whatsapp-sincronizacao" },
      { name: "Transmissões", href: "/whatsapp/transmissoes", icon: Megaphone, route: "whatsapp-transmissoes" },
      { name: "Example", href: "/example", icon: Boxes, route: "example" },
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
      { name: "Membros", href: "/membros", icon: UserRound },
      { name: "Planos", href: "/planos", icon: Wallet },
      { name: "Inscrições", href: "/inscricoes", icon: ClipboardList },
      { name: "Financeiro", href: "/financeiro", icon: CircleDollarSign },
      { name: "WhatsApp", href: "/whatsapp", icon: MessageCircle },
      { name: "Sincronização", href: "/whatsapp/sincronizacao", icon: Repeat },
      { name: "Transmissões", href: "/whatsapp/transmissoes", icon: Megaphone },
      { name: "Example", href: "/example", icon: Boxes },
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: UsersRound,
  brandTitle: "Community",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/membros", component: Membros },
    { path: "/planos", component: Planos },
    { path: "/inscricoes", component: Inscricoes },
    { path: "/financeiro", component: Financeiro },
    { path: "/whatsapp", component: WhatsApp },
    { path: "/whatsapp/sincronizacao", component: Sincronizacao },
    { path: "/whatsapp/transmissoes", component: Transmissoes },
    { path: "/example", component: Example },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
  // PUBLIC — no auth, no Layout. The public application form must render
  // for a visitor with no session (community-m1-contract.md §Frontend).
  // `/assinar` is the module 2 public checkout page, same seam
  // (community-m2-contract.md §Frontend).
  publicRoutes: [
    { path: "/inscrever", component: Inscrever },
    { path: "/assinar", component: Assinar },
  ],
});
