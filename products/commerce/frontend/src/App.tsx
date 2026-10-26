/**
 * Commerce — the reference host product of the commerce organ (P3).
 *
 * Two audiences on one SPA:
 *   - **Storefront** (public, no login, host-resolved by the backend): `/`,
 *     `/p/:slug`, `/carrinho`, `/checkout`, `/pedido/:token`,
 *     `/minhas-compras`, `/privacidade`, `/privacidade/verificar`, and the customer's signed quote link
 *     `/orcamento/:token` (accept / decline, no login) —
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
import { Navigate } from "react-router-dom";
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
  Truck,
  FileText,
  FileSignature,
  Settings,
} from "lucide-react";

// Seed public pages
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// Back office
const AdminHome = lazy(() => import("@/pages/admin/AdminHome"));
const Categories = lazy(() => import("@/pages/admin/Categories"));
const Products = lazy(() => import("@/pages/admin/Products"));
const ProductEdit = lazy(() => import("@/pages/admin/ProductEdit"));
const Coupons = lazy(() => import("@/pages/admin/Coupons"));
const Orders = lazy(() => import("@/pages/admin/Orders"));
const OrderView = lazy(() => import("@/pages/admin/OrderView"));
const Customers = lazy(() => import("@/pages/admin/Customers"));
const Configuracoes = lazy(() => import("@/pages/admin/Configuracoes"));
const Financeiro = lazy(() => import("@/pages/admin/Financeiro"));
const Itens = lazy(() => import("@/pages/admin/Itens"));
const Parceiros = lazy(() => import("@/pages/admin/Parceiros"));
const Estoque = lazy(() => import("@/pages/admin/Estoque"));
const Compras = lazy(() => import("@/pages/admin/Compras"));
const Orcamentos = lazy(() => import("@/pages/admin/Orcamentos"));
const Contratos = lazy(() => import("@/pages/admin/Contratos"));
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

// Customer-facing quote link (public, signed token — no login, outside the authed shell)
const QuoteAccept = lazy(() => import("@/pages/quote/QuoteAccept"));

// Route-table components are lazy; a redirect is a one-line lazy component.
const redirectTo = (to: string) => lazy(async () => ({ default: () => <Navigate to={to} replace /> }));

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
      { name: "Compras", href: "/admin/compras", icon: Truck, route: "compras" },
      { name: "Orçamentos", href: "/admin/orcamentos", icon: FileText, route: "orcamentos" },
      { name: "Contratos", href: "/admin/contratos", icon: FileSignature, route: "contratos" },
    ],
  },
  {
    key: "configuracoes",
    label: "Configurações",
    icon: Settings,
    items: [
      { name: "Configurações da loja", href: "/admin/configuracoes/loja", icon: Building2, route: "configuracoes" },
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
    { path: "/admin/compras", component: Compras },
    { path: "/admin/orcamentos", component: Orcamentos },
    { path: "/admin/contratos", component: Contratos },
    { path: "/admin/configuracoes/*", component: Configuracoes },
    // Old settings pages (bookmarks, emails): now tabs of /admin/configuracoes.
    { path: "/admin/loja", component: redirectTo("/admin/configuracoes/loja") },
    { path: "/admin/enderecos", component: redirectTo("/admin/configuracoes/enderecos") },
    { path: "/admin/integracoes", component: redirectTo("/admin/configuracoes/integracoes") },
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
    { path: "/orcamento/:token", component: QuoteAccept },
  ],
  Layout,
  ...infra.appConfig,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
  unauthRedirect: "/login",
});
