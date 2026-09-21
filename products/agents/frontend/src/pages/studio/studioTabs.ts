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
  { id: "versoes", label: "Versões" },
  { id: "compilado", label: "Prompt compilado" },
  { id: "conversar", label: "Conversar" },
] as const;

export type StudioTabId = (typeof STUDIO_TABS)[number]["id"];

export const DEFAULT_TAB: StudioTabId = "visao-geral";

export function isStudioTab(value: string | null): value is StudioTabId {
  return !!value && STUDIO_TABS.some((t) => t.id === value);
}

/** Builds `/studio/:key?tab=…&…` for in-app links. */
export function studioTabHref(agentKey: string, tab: StudioTabId, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ tab, ...extra });
  return `/studio/${encodeURIComponent(agentKey)}?${params.toString()}`;
}
