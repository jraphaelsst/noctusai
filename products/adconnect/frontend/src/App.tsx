/**
 * AdConnect App — the simplest possible product.
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
import {
  LayoutDashboard,
  Users,
  Home,
  ShoppingCart,
  Package,
  ClipboardList,
  FileText,
  Award,
} from "lucide-react";

// Pages — framework
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// Pages — distributor MVP (Phase 7 skeleton)
const Catalog = lazy(() => import("@/pages/Catalog"));
const ProductDetail = lazy(() => import("@/pages/ProductDetail"));
const Cart = lazy(() => import("@/pages/Cart"));
const Checkout = lazy(() => import("@/pages/Checkout"));
const Orders = lazy(() => import("@/pages/Orders"));
const OrderDetail = lazy(() => import("@/pages/OrderDetail"));
const SelloutReportSubmit = lazy(() => import("@/pages/SelloutReportSubmit"));
const SelloutHistory = lazy(() => import("@/pages/SelloutHistory"));
const RewardsLedger = lazy(() => import("@/pages/RewardsLedger"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
    ],
  },
  {
    key: "marketplace",
    label: "Marketplace",
    icon: ShoppingCart,
    defaultOpen: true,
    items: [
      { name: "Catálogo", href: "/catalog", icon: Package, route: "catalog" },
      { name: "Carrinho", href: "/cart", icon: ShoppingCart, route: "cart" },
      { name: "Pedidos", href: "/orders", icon: ClipboardList, route: "orders" },
    ],
  },
  {
    key: "rewards",
    label: "Recompensas e sellout",
    icon: Award,
    defaultOpen: false,
    items: [
      { name: "Recompensas", href: "/rewards", icon: Award, route: "rewards" },
      { name: "Sellout", href: "/sellout", icon: FileText, route: "sellout" },
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
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
  {
    key: "marketplace",
    label: "Marketplace",
    icon: ShoppingCart,
    defaultOpen: true,
    items: [
      { name: "Catálogo", href: "/catalog", icon: Package },
      { name: "Carrinho", href: "/cart", icon: ShoppingCart },
      { name: "Pedidos", href: "/orders", icon: ClipboardList },
    ],
  },
  {
    key: "rewards",
    label: "Recompensas e sellout",
    icon: Award,
    defaultOpen: false,
    items: [
      { name: "Recompensas", href: "/rewards", icon: Award },
      { name: "Sellout", href: "/sellout", icon: FileText },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: ShoppingCart,
  brandTitle: "AdConnect",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/equipe", component: Equipe },
    // Distributor MVP — Phase 7 skeleton (no API integration yet)
    { path: "/catalog", component: Catalog },
    { path: "/catalog/:id", component: ProductDetail },
    { path: "/cart", component: Cart },
    { path: "/checkout", component: Checkout },
    { path: "/orders", component: Orders },
    { path: "/orders/:id", component: OrderDetail },
    { path: "/sellout", component: SelloutHistory },
    { path: "/sellout/submit", component: SelloutReportSubmit },
    { path: "/rewards", component: RewardsLedger },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
