/**
 * Store App.
 *
 * Infrastructure comes from @/infra (one file, one createProductInfra call).
 * Structure comes from createProductApp + createProductLayout.
 *
 * Public surface: `/` (sales landing) and `/obrigado` are `publicRoutes` — they
 * match BEFORE the seed's authenticated `/*` catch-all, so a signed-in admin
 * visiting `/` still sees the public landing. The seed `Landing` slot is
 * deliberately NOT used (it would only serve `/` to signed-out users and bounce
 * every other protected path to it); with no Landing the guard sends signed-out
 * visitors of `/admin*` to `/login` (`unauthRedirect`). There is no login link on
 * any public page — the owner reaches `/login` directly.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import { Home, Receipt, ShoppingBag, Store } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Obrigado = lazy(() => import("@/pages/Obrigado"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Admin = lazy(() => import("@/pages/Admin"));
const Vendas = lazy(() => import("@/pages/Vendas"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// Nav — `route` keys MUST equal the `store.status_pagina.nome_pagina` rows
// (an unlisted key is silently hidden by `filterNavByPageStatus`).
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Loja",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Página de vendas", href: "/admin", icon: Store, route: "admin" },
      { name: "Vendas", href: "/admin/vendas", icon: Receipt, route: "vendas" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = [
  {
    key: "principal",
    label: "Loja",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Página de vendas", href: "/admin", icon: Store },
      { name: "Vendas", href: "/admin/vendas", icon: Receipt },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: ShoppingBag,
  brandTitle: "Store",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/admin", component: Admin },
    { path: "/admin/vendas", component: Vendas },
  ],
  publicRoutes: [
    { path: "/", component: Landing },
    { path: "/obrigado", component: Obrigado },
  ],
  Layout,
  ...infra.appConfig,
  unauthRedirect: "/login",
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
