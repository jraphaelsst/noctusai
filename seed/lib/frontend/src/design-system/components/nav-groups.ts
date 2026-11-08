/**
 * Canonical module-group order + labels for the module-grouped sidebar.
 *
 * Every product that groups its nav by platform module (CRM, Redes Sociais,
 * ...) orders and labels those groups through this module, so the order is
 * defined once. Pure data + one pure helper — no React.
 */

/** Canonical order of module groups (keys). */
export const MODULE_GROUP_ORDER = [
  "crm",
  "redes-sociais",
  "erp",
  "cms",
  "corestudio",
  "banib",
  "emissoes",
  "integracoes",
  "configuracoes",
] as const;

export type ModuleGroupKey = (typeof MODULE_GROUP_ORDER)[number];

/** pt-BR display labels for the canonical module groups. */
export const MODULE_GROUP_LABELS: Record<ModuleGroupKey, string> = {
  crm: "CRM",
  "redes-sociais": "Redes Sociais",
  erp: "ERP",
  cms: "CMS",
  corestudio: "CoreStudio",
  banib: "Banib",
  emissoes: "Emissões",
  integracoes: "Integrações",
  configuracoes: "Configurações",
};

/**
 * Order groups canonically: keys listed in `order` first (in that order),
 * unknown keys after, keeping their original relative order. Nothing is
 * dropped or duplicated; the input array is not mutated.
 */
export function orderNavGroups<T extends { key: string }>(
  groups: readonly T[],
  order: readonly string[] = MODULE_GROUP_ORDER,
): T[] {
  const rank = new Map(order.map((k, i) => [k, i] as const));
  const known: T[] = [];
  const unknown: T[] = [];
  for (const g of groups) (rank.has(g.key) ? known : unknown).push(g);
  // Array.prototype.sort is stable (ES2019): duplicate keys keep input order.
  known.sort((a, b) => rank.get(a.key)! - rank.get(b.key)!);
  return [...known, ...unknown];
}
