/**
 * Orbity sidebar nav on the seed module manifests (W3-O1, crm-cms-erp-vertical-seeds
 * plan). Groups are the seed's canonical modules, ordered by `MODULE_GROUP_ORDER`
 * and labelled by `MODULE_GROUP_LABELS` (applied by `composeModules`). Dashboard is
 * a standalone item after the groups. Nav only: URLs, routes and status_pagina keys
 * are unchanged (each `pageKey` is the page's existing status_pagina key).
 *
 * Page -> group: CRM = Clientes, Funil, Agenda · Redes Sociais = Conteúdo, Tráfego,
 * WhatsApp, Automação · ERP = Financeiro, Tarefas, Rotinas, Relatórios ·
 * Configurações = Equipe. CMS and Integrações have no orbity pages yet: omitted.
 *
 * NOC-REMEDIATE[orbity-nav-extend-seed-modules]: groups are defined locally with
 * `defineModule` (declared deviation, same as SW) because the seed ships no base
 * crm/erp modules yet. Destination: plan slice W2-6, then `extendModule(base, ...)`. — 2026-11-11
 *
 * NOC-REMEDIATE[orbity-modules-enablement-endpoint]: orbity has no `GET /api/modules`,
 * so every module is enabled statically (all ON by default, owner 2026-11-08).
 * Destination: W1-1 follow-up (mount the seed modules router, then use
 * `useEnabledModules().enabledKeys`). — 2026-11-11
 */
import { composeModules, defineModule, stripNavRoutes } from "@noctusai/lib";
import type { ModuleItem, NavGroupWithRoute, NavItemWithRoute } from "@noctusai/lib";
import type { NavGroup, NavItem } from "@noctusai/lib/design-system";
import {
  LayoutDashboard,
  Users,
  DollarSign,
  UserCheck,
  Kanban,
  ClipboardList,
  CalendarDays,
  RefreshCw,
  FileBarChart2,
  Target,
  Zap,
  Megaphone,
  MessageCircle,
  Share2,
  Building2,
  Settings2,
} from "lucide-react";

type Icon = ModuleItem["icon"];

/** A page: nav-only (routes stay declared in App.tsx, URLs never move). */
const pg = (label: string, path: string, pageKey: string, icon: Icon): ModuleItem => ({ label, path, pageKey, icon });

const crm = defineModule({
  key: "crm",
  icon: UserCheck,
  items: [
    pg("Clientes", "/clientes", "clientes", UserCheck),
    pg("Funil", "/funil", "funil", Kanban),
    pg("Agenda", "/agenda", "agenda", CalendarDays),
  ],
});

const redesSociais = defineModule({
  key: "redes-sociais",
  icon: Share2,
  items: [
    pg("Conteúdo", "/conteudo", "conteudo", Megaphone),
    pg("Tráfego", "/trafego", "trafego", Target),
    pg("WhatsApp", "/whatsapp", "whatsapp", MessageCircle),
    pg("Automação", "/automacao", "automacao", Zap),
  ],
});

const erp = defineModule({
  key: "erp",
  icon: Building2,
  items: [
    pg("Financeiro", "/financeiro", "financeiro", DollarSign),
    pg("Tarefas", "/tarefas", "tarefas", ClipboardList),
    pg("Rotinas", "/rotinas", "rotinas", RefreshCw),
    pg("Relatórios", "/relatorios", "relatorios", FileBarChart2),
  ],
});

const configuracoes = defineModule({
  key: "configuracoes",
  icon: Settings2,
  items: [pg("Equipe", "/equipe", "equipe", Users)],
});

export const ORBITY_MODULES = [crm, redesSociais, erp, configuracoes] as const;

const composed = composeModules({
  modules: ORBITY_MODULES,
  // NOC-REMEDIATE[orbity-modules-enablement-endpoint]: static all-on (see docblock).
  enabledKeys: new Set(ORBITY_MODULES.map((m) => m.enablementKey)),
});

export const NAV_GROUPS: NavGroupWithRoute[] = composed.navGroups;

/** Dashboard stays a standalone item after the groups. */
export const STANDALONE_ITEMS: NavItemWithRoute[] = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
];

export const NAV_FALLBACK: NavGroup[] = stripNavRoutes(NAV_GROUPS) as NavGroup[];
export const STANDALONE_FALLBACK: NavItem[] = STANDALONE_ITEMS.map(({ route: _r, ...rest }) => rest as NavItem);
