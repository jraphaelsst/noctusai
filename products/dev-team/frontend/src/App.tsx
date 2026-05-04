/**
 * dev-team product App — Vite/React via the seed framework.
 *
 * MVP shipped 2026-05-04 (engineer H, agno-dev-team-rollout B2):
 *   - / → Agents grid (11 cards)
 *   - /agents/:name → Agent detail (recharts time-series + recent events + ConfigForm)
 *   - /run → Run task page
 *
 * Auth + layout + nav come for free from `createProductApp` /
 * `createProductLayout`. The seed handles supabase wiring via
 * `infra.appConfig`.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from "@noctusai/seed/infra";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import { Bot, Home, ListChecks, Send } from "lucide-react";

// ── Pages ────────────────────────────────────────────────────
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const AgentsPage = lazy(() => import("@/pages/AgentsPage"));
const AgentDetailPage = lazy(() => import("@/pages/AgentDetailPage"));
const RunTaskPage = lazy(() => import("@/pages/RunTaskPage"));

// ── Nav ──────────────────────────────────────────────────────

const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Dev Team",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Agents", href: "/", icon: ListChecks, route: "agents" },
      { name: "Run task", href: "/run", icon: Send, route: "run" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = NAV_GROUPS.map((g) => ({
  ...g,
  items: g.items.map(({ route, ...item }) => item),
})) as NavGroup[];

// ── Layout ───────────────────────────────────────────────────

const Layout = createProductLayout({
  brandIcon: Bot,
  brandTitle: "Dev Team",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

// ── App ──────────────────────────────────────────────────────

export default createProductApp({
  routes: [
    { path: "/", component: AgentsPage },
    { path: "/agents/:name", component: AgentDetailPage },
    { path: "/run", component: RunTaskPage },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  NotFound,
});
