/**
 * Daily Life App — born from the seed frontend framework.
 *
 * Personal productivity hub: tasks, goals, schedule, notes.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import type { NavGroupWithRoute } from "@noctusai/shared";
import type { NavGroup } from "@noctusai/shared/design-system";
import {
  LayoutDashboard, Users, Home, CalendarCheck,
  ListTodo, Target, Calendar, StickyNote,
} from "lucide-react";

// Pages
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Tarefas = lazy(() => import("@/pages/Tarefas"));
const Metas = lazy(() => import("@/pages/Metas"));
const Agenda = lazy(() => import("@/pages/Agenda"));
const Notas = lazy(() => import("@/pages/Notas"));
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
      { name: "Tarefas", href: "/tarefas", icon: ListTodo, route: "tarefas" },
      { name: "Metas", href: "/metas", icon: Target, route: "metas" },
      { name: "Agenda", href: "/agenda", icon: Calendar, route: "agenda" },
      { name: "Notas", href: "/notas", icon: StickyNote, route: "notas" },
    ],
  },
  {
    key: "organizacao",
    label: "Organizacao",
    icon: Users,
    defaultOpen: false,
    items: [
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
      { name: "Tarefas", href: "/tarefas", icon: ListTodo },
      { name: "Metas", href: "/metas", icon: Target },
      { name: "Agenda", href: "/agenda", icon: Calendar },
      { name: "Notas", href: "/notas", icon: StickyNote },
    ],
  },
  {
    key: "organizacao",
    label: "Organizacao",
    icon: Users,
    defaultOpen: false,
    items: [
      { name: "Equipe", href: "/equipe", icon: Users },
    ],
  },
];

const Layout = createProductLayout({
  brandIcon: CalendarCheck,
  brandTitle: "Daily Life",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  supabase,
  useAuthStore,
  NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/tarefas", component: Tarefas },
    { path: "/metas", component: Metas },
    { path: "/agenda", component: Agenda },
    { path: "/notas", component: Notas },
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
