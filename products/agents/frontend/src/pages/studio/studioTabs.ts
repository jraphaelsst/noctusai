/**
 * Agent Studio tab registry — CONTRACT §G (tab order + labels) and §J2.4 (each
 * tab is its own file under `./tabs/`, default-exporting
 * `function XTab({ agentKey }: { agentKey: string })`).
 *
 * The URL carries the tab as `?tab=<id>`; deep links add `secao=<section id>`
 * (Prompt) or `skill=<skill id>` (Skills) so the inspector can click through
 * to a block's source.
 */
export const STUDIO_TABS = [
  { id: "visao-geral", label: "Visão geral" },
  { id: "prompt", label: "Prompt" },
  { id: "skills", label: "Skills" },
  { id: "configuracoes", label: "Configurações" },
  { id: "conhecimento", label: "Conhecimento" },
  { id: "avaliacoes", label: "Avaliações" },
  { id: "clientes", label: "Clientes" },
  { id: "canais", label: "Canais" },
  { id: "aprendizados", label: "Aprendizados" },
  { id: "versoes", label: "Versões" },
  { id: "compilado", label: "Prompt compilado" },
  { id: "conversar", label: "Conversar" },
  // Julia v2 (CONTRACT §2.3, §3, §5.3): tabs of platform-defined agents; a `legado`/`org` agent never sees them.
  { id: "textos", label: "Textos do sistema" },
  { id: "ferramentas", label: "Ferramentas" },
  { id: "decisoes", label: "Decisões" },
  { id: "qualificacao", label: "Qualificação" },
  { id: "biblioteca", label: "Skills da biblioteca" },
  { id: "especificacoes", label: "Especificações declaradas" },
  { id: "especificacoes-org", label: "Especificações da org" },
  { id: "controles", label: "Controles" },
  { id: "conversas", label: "Conversas" },
  { id: "conformidade", label: "Conformidade" },
] as const;

export type StudioTabId = (typeof STUDIO_TABS)[number]["id"];

export const DEFAULT_TAB: StudioTabId = "visao-geral";

export function isStudioTab(value: string | null): value is StudioTabId {
  return !!value && STUDIO_TABS.some((t) => t.id === value);
}

/** Tabs that only exist for one agent kind (Agent Packages §D3). */
const RUNTIME_ONLY: readonly StudioTabId[] = ["clientes", "canais"];
const DEV_ADVISOR_ONLY: readonly StudioTabId[] = ["aprendizados"];

/** Tabs that exist only on the platform-defined / org-instance surfaces (Julia v2). */
export const JULIA_TABS: readonly StudioTabId[] = [
  "textos",
  "ferramentas",
  "decisoes",
  "qualificacao",
  "biblioteca",
  "especificacoes",
  "especificacoes-org",
  "controles",
  "conversas",
  "conformidade",
];

/** `canais` follows the agent's own `usa_canais` flag (API data) — never its key. */
export function isTabVisibleForKind(tab: StudioTabId, kind: string, usaCanais: boolean = false): boolean {
  if (JULIA_TABS.includes(tab)) return false;
  if (tab === "canais" && !usaCanais) return false;
  if (kind === "dev-advisor") return !RUNTIME_ONLY.includes(tab);
  return !DEV_ADVISOR_ONLY.includes(tab);
}

/** Builds `/agentes/:key?tab=…&…` for in-app links (the unified agent page; agents-unified CONTRACT §7). */
export function studioTabHref(agentKey: string, tab: StudioTabId, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ tab, ...extra });
  return `/agentes/${encodeURIComponent(agentKey)}?${params.toString()}`;
}

// ── Julia v2 tiers (CONTRACT §0.4) ──────────────────────────────────────────

/**
 * The Studio surface the SERVER chose for an agent row: `definition_scope` on
 * `/api/studio/agents[/{key}]` — `plataforma` (the definition, platform org: platform admins),
 * `instancia` (this org's instance of it: org admins), anything else is a plain org agent
 * (`legado`) and keeps the pre-v2 tab set. The role string is never read here.
 */
export type StudioTier = "plataforma" | "organizacao" | "legado";

export function studioTier(agent: { definition_scope?: string } | null | undefined): StudioTier {
  if (agent?.definition_scope === "plataforma") return "plataforma";
  if (agent?.definition_scope === "instancia") return "organizacao";
  return "legado";
}

const PLATAFORMA_TABS: readonly StudioTabId[] = [
  "visao-geral",
  "prompt",
  "textos",
  "ferramentas",
  "decisoes",
  "qualificacao",
  "biblioteca",
  "especificacoes",
  "avaliacoes",
  "configuracoes",
  "conformidade",
  "conversas",
  "versoes",
  "compilado",
];

const ORG_ADMIN_TABS: readonly StudioTabId[] = ["visao-geral", "especificacoes-org", "controles", "conversas"];

export interface TabAccess {
  /** UX hint only (`useIsAdmin`): the server re-enforces every route. */
  isOrgAdmin: boolean;
  /** UX hint only (`useIsPlatformAdmin`): decides whether to ASK for the per-org compiled view. */
  platformAdminHint: boolean;
}

/** The tabs a visitor sees for this agent row. Org members get none of the Studio content tabs. */
export function visibleTabsFor(
  agent: { definition_scope?: string; kind?: string; usa_canais?: boolean } | null | undefined,
  access: TabAccess,
): readonly { id: StudioTabId; label: string }[] {
  const tier = studioTier(agent);
  if (tier === "plataforma")
    return STUDIO_TABS.filter((t) => PLATAFORMA_TABS.includes(t.id) || (t.id === "canais" && agent?.usa_canais === true));
  if (tier === "organizacao") {
    if (!access.isOrgAdmin && !access.platformAdminHint) return [];
    const ids = access.isOrgAdmin ? [...ORG_ADMIN_TABS] : ["visao-geral" as StudioTabId];
    if (access.platformAdminHint) ids.push("compilado");
    return STUDIO_TABS.filter((t) => ids.includes(t.id));
  }
  return STUDIO_TABS.filter((t) => isTabVisibleForKind(t.id, agent?.kind ?? "runtime", agent?.usa_canais === true));
}
