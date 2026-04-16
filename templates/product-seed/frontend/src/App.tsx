/**
 * {{PRODUCT_NAME}} App — born from the seed frontend framework.
 *
 * The simplest possible product frontend. Just pages + config.
 * All structural wiring (providers, routing, auth, error boundaries)
 * is inherited from createProductApp().
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import type { NavGroupWithRoute } from "@noctusai/shared";
import type { NavGroup } from "@noctusai/shared/design-system";
import { LayoutDashboard, Users, Home, {{PRODUCT_ICON}} } from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
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
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

// Layout from framework
const Layout = createProductLayout({
  brandIcon: {{PRODUCT_ICON}},
  brandTitle: "{{PRODUCT_NAME}}",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  supabase,
  useAuthStore,
  NotificationBell,
});

// App from framework
export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  supabase,
  useAuthStore,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
});
