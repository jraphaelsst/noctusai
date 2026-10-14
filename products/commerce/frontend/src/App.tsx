/**
 * Commerce — the reference host product of the commerce organ (P3).
 *
 * Two audiences on one SPA:
 *   - **Storefront** (public, no login, host-resolved by the backend): `/`,
 *     `/p/:slug`, `/carrinho`, `/checkout`, `/pedido/:token`,
 *     `/minhas-compras`, `/privacidade`, `/privacidade/verificar` —
 *     `publicRoutes`, so they render for anonymous buyers. The paths match
 *     the organ's e-mailed link templates (`CommerceConfig.*_path_template`).
 *   - **Back office** (`/admin/*`, license-gated staff): flat `routes` under
 *     the seed layout.
 *
 * `/` is the storefront, so there is no marketing Landing: an anonymous
 * visitor to `/admin/*` goes to `/login` (`unauthRedirect`). On the back-office
 * host itself the storefront shows the organ's "no store on this address"
 * state and sends a signed-in staff member on to `/admin`.
 *
 * Consent routes (`/consent*`) are seed-mounted by `createProductApp` — never
 * re-declared here.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from "@noctusai/seed/infra";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import {
  Store,
  Package,
  Tags,
  TicketPercent,
  ShoppingCart,
  Users,
  UserCog,
  Building2,
  Landmark,
  Boxes,
  Warehouse,
  Handshake,
  Globe,
  KeyRound,
  Settings,
} from "lucide-react";

// Seed public pages
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// Back office
const AdminHome = lazy(() => import("@/pages/admin/AdminHome"));
const StoreProfile = lazy(() => import("@/pages/admin/StoreProfile"));
const StorefrontHosts = lazy(() => import("@/pages/admin/StorefrontHosts"));
const Categories = lazy(() => import("@/pages/admin/Categories"));
const Products = lazy(() => import("@/pages/admin/Products"));
const ProductEdit = lazy(() => import("@/pages/admin/ProductEdit"));
const Coupons = lazy(() => import("@/pages/admin/Coupons"));
const Orders = lazy(() => import("@/pages/admin/Orders"));
const OrderView = lazy(() => import("@/pages/admin/OrderView"));
const Customers = lazy(() => import("@/pages/admin/Customers"));
const ApiKeys = lazy(() => import("@/pages/admin/ApiKeys"));
const Financeiro = lazy(() => import("@/pages/admin/Financeiro"));
const Itens = lazy(() => import("@/pages/admin/Itens"));
const Parceiros = lazy(() => import("@/pages/admin/Parceiros"));
const Estoque = lazy(() => import("@/pages/admin/Estoque"));
const Equipe = lazy(() => import("@/pages/Equipe"));

// Storefront (public)
const StoreHome = lazy(() => import("@/pages/storefront/StoreHome"));
const StoreProduct = lazy(() => import("@/pages/storefront/StoreProduct"));
const StoreCart = lazy(() => import("@/pages/storefront/StoreCart"));
const StoreCheckout = lazy(() => import("@/pages/storefront/StoreCheckout"));
const StoreOrder = lazy(() => import("@/pages/storefront/StoreOrder"));
const MyOrders = lazy(() => import("@/pages/storefront/MyOrders"));
const PrivacyRequest = lazy(() => import("@/pages/storefront/PrivacyRequest"));
const PrivacyVerify = lazy(() => import("@/pages/storefront/PrivacyVerify"));

// Nav — `route` keys are `status_pagina.nome_pagina` rows (an item without a row is hidden).
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "vendas",
    label: "Vendas",
    icon: ShoppingCart,
    items: [
      { name: "Pedidos", href: "/admin/pedidos", icon: ShoppingCart, route: "pedidos" },
      { name: "Clientes", href: "/admin/clientes", icon: Users, route: "clientes" },
      { name: "Cupons", href: "/admin/cupons", icon: TicketPercent, route: "cupons" },
    ],
  },
  {
    key: "catalogo",
    label: "Catálogo",
    icon: Package,
    items: [
      { name: "Produtos", href: "/admin/produtos", icon: Package, route: "produtos" },
      { name: "Categorias", href: "/admin/categorias", icon: Tags, route: "categorias" },
    ],
  },
  {
    key: "gestao",
    label: "Gestão",
    icon: Landmark,
    items: [
      { name: "Financeiro", href: "/admin/financeiro", icon: Landmark, route: "financeiro" },
      { name: "Itens", href: "/admin/itens", icon: Boxes, route: "itens" },
      { name: "Parceiros", href: "/admin/parceiros", icon: Handshake, route: "parceiros" },
      { name: "Estoque", href: "/admin/estoque", icon: Warehouse, route: "estoque" },
    ],
  },
  {
    key: "configuracoes",
    label: "Configurações",
    icon: Settings,
    items: [
      { name: "Perfil da loja", href: "/admin/loja", icon: Building2, route: "loja" },
      { name: "Endereços da vitrine", href: "/admin/enderecos", icon: Globe, route: "enderecos" },
      { name: "Integrações", href: "/admin/integracoes", icon: KeyRound, route: "integracoes" },
      { name: "Equipe", href: "/admin/equipe", icon: UserCog, route: "equipe" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = NAV_GROUPS.map((g) => ({
  key: g.key,
  label: g.label,
  icon: g.icon,
  items: g.items.map(({ name, href, icon }) => ({ name, href, icon })),
}));

const Layout = createProductLayout({
  brandIcon: Store,
  brandTitle: "Commerce",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/admin", component: AdminHome },
    { path: "/admin/pedidos", component: Orders },
    { path: "/admin/pedidos/:id", component: OrderView },
    { path: "/admin/clientes", component: Customers },
    { path: "/admin/cupons", component: Coupons },
    { path: "/admin/produtos", component: Products },
    { path: "/admin/produtos/:id", component: ProductEdit },
    { path: "/admin/categorias", component: Categories },
    { path: "/admin/financeiro/*", component: Financeiro },
    { path: "/admin/itens", component: Itens },
    { path: "/admin/parceiros", component: Parceiros },
    { path: "/admin/estoque", component: Estoque },
    { path: "/admin/loja", component: StoreProfile },
    { path: "/admin/enderecos", component: StorefrontHosts },
    { path: "/admin/integracoes", component: ApiKeys },
    { path: "/admin/equipe", component: Equipe },
  ],
  publicRoutes: [
    { path: "/", component: StoreHome },
    { path: "/p/:slug", component: StoreProduct },
    { path: "/carrinho", component: StoreCart },
    { path: "/checkout", component: StoreCheckout },
    { path: "/pedido/:token", component: StoreOrder },
    { path: "/minhas-compras", component: MyOrders },
    { path: "/privacidade", component: PrivacyRequest },
    { path: "/privacidade/verificar", component: PrivacyVerify },
  ],
  Layout,
  ...infra.appConfig,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
  unauthRedirect: "/login",
});
