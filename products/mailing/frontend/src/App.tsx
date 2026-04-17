/**
 * NoctusAI Mailing — born from the seed frontend framework.
 *
 * Email marketing & automation: contacts, templates, campaigns, automations, analytics.
 */
import { lazy } from "react";
import { createProductApp, createProductLayout } from "@noctusai/seed";
import infra from '@noctusai/seed/infra';
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";
import {
  LayoutDashboard, Users, Home, Mail, Send,
  UserCircle, ListFilter, FileText, GitBranch,
  BarChart3, TrendingUp, Settings,
} from "lucide-react";

// Pages — public
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));

// Pages — authenticated
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Contacts = lazy(() => import("@/pages/Contacts"));
const ContactDetail = lazy(() => import("@/pages/ContactDetail"));
const Lists = lazy(() => import("@/pages/Lists"));
const Templates = lazy(() => import("@/pages/Templates"));
const TemplateEditor = lazy(() => import("@/pages/TemplateEditor"));
const Campaigns = lazy(() => import("@/pages/Campaigns"));
const CampaignCreate = lazy(() => import("@/pages/CampaignCreate"));
const CampaignDetail = lazy(() => import("@/pages/CampaignDetail"));
const Automations = lazy(() => import("@/pages/Automations"));
const AutomationCreate = lazy(() => import("@/pages/AutomationCreate"));
const AutomationDetail = lazy(() => import("@/pages/AutomationDetail"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const MailingSettings = lazy(() => import("@/pages/Settings"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));

// Pages — public (no auth)
const Unsubscribe = lazy(() => import("@/pages/Unsubscribe"));

// Nav
const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Contatos", href: "/contacts", icon: UserCircle, route: "contacts" },
      { name: "Listas", href: "/lists", icon: ListFilter, route: "lists" },
    ],
  },
  {
    key: "marketing",
    label: "Marketing",
    icon: Mail,
    defaultOpen: true,
    items: [
      { name: "Templates", href: "/templates", icon: FileText, route: "templates" },
      { name: "Campanhas", href: "/campaigns", icon: Send, route: "campaigns" },
      { name: "Automacoes", href: "/automations", icon: GitBranch, route: "automations" },
    ],
  },
  {
    key: "insights",
    label: "Insights",
    icon: BarChart3,
    defaultOpen: false,
    items: [
      { name: "Analytics", href: "/analytics", icon: TrendingUp, route: "analytics" },
    ],
  },
  {
    key: "configuracao",
    label: "Configuracao",
    icon: Settings,
    defaultOpen: false,
    items: [
      { name: "Configuracoes", href: "/settings", icon: Settings, route: "settings" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = NAV_GROUPS.map(g => ({
  ...g,
  items: g.items.map(({ route, ...item }) => item),
})) as NavGroup[];

const Layout = createProductLayout({
  brandIcon: Mail,
  brandTitle: "Mailing",
  navGroups: NAV_GROUPS,
  navGroupsFallback: NAV_FALLBACK,
  ...infra.appConfig,
  NotificationBell: infra.NotificationBell,
});

export default createProductApp({
  routes: [
    { path: "/", component: Dashboard },
    { path: "/contacts", component: Contacts },
    { path: "/contacts/:id", component: ContactDetail },
    { path: "/lists", component: Lists },
    { path: "/templates", component: Templates },
    { path: "/templates/new", component: TemplateEditor },
    { path: "/templates/:id/edit", component: TemplateEditor },
    { path: "/campaigns", component: Campaigns },
    { path: "/campaigns/new", component: CampaignCreate },
    { path: "/campaigns/:id", component: CampaignDetail },
    { path: "/automations", component: Automations },
    { path: "/automations/new", component: AutomationCreate },
    { path: "/automations/:id", component: AutomationDetail },
    { path: "/analytics", component: Analytics },
    { path: "/settings", component: MailingSettings },
    { path: "/equipe", component: Equipe },
  ],
  Layout,
  ...infra.appConfig,
  Landing,
  Login,
  AcceptInvite,
  ForgotPassword,
  NotFound,
  publicRoutes: [
    { path: "/unsubscribe/:token", component: Unsubscribe },
  ],
});
