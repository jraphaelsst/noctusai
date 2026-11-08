/**
 * `defineFunnel(schema)` — validates a funnel schema once (at module load) and resolves the
 * per-card questions (`tabsFor`, `hubIdOf`, `actionsAt`). A malformed schema THROWS: a funnel
 * with two tabs of the same id would otherwise render one of them silently.
 */
import type { FunnelActionDef, FunnelCard, FunnelSchema, FunnelTab } from './types';

export interface DefinedFunnel<TCard extends FunnelCard = FunnelCard> {
  schema: FunnelSchema<TCard>;
  /** Visible tabs for this card, ordered by `order` then declaration. */
  tabsFor: (card: TCard) => FunnelTab<TCard>[];
  hubIdOf: (card: TCard) => string | null;
  actionsAt: (placement: FunnelActionDef['placement']) => FunnelActionDef[];
  action: (code: string) => FunnelActionDef | undefined;
}

function assertUnique(kind: string, ids: string[], where: string) {
  const seen = new Set<string>();
  for (const id of ids) {
    if (seen.has(id)) throw new Error(`defineFunnel(${where}): ${kind} duplicado "${id}"`);
    seen.add(id);
  }
}

export function defineFunnel<TCard extends FunnelCard = FunnelCard>(
  schema: FunnelSchema<TCard>,
): DefinedFunnel<TCard> {
  if (!schema.id) throw new Error('defineFunnel: schema.id é obrigatório');
  if (schema.tabs.length === 0) {
    throw new Error(`defineFunnel(${schema.id}): declare ao menos uma aba`);
  }
  assertUnique('aba', schema.tabs.map((t) => t.id), schema.id);
  assertUnique('ação', (schema.actions ?? []).map((a) => a.code), schema.id);
  if (schema.defaultTab && !schema.tabs.some((t) => t.id === schema.defaultTab)) {
    throw new Error(`defineFunnel(${schema.id}): defaultTab "${schema.defaultTab}" não existe`);
  }

  const ordered = schema.tabs
    .map((tab, index) => ({ tab, index }))
    .sort((a, b) => (a.tab.order ?? 0) - (b.tab.order ?? 0) || a.index - b.index)
    .map(({ tab }) => tab);
  const actions = schema.actions ?? [];

  return {
    schema,
    tabsFor: (card) => ordered.filter((t) => !t.when || t.when(card)),
    hubIdOf: (card) => (schema.hubEntityId ? schema.hubEntityId(card) : card.hub_entity_id) ?? null,
    actionsAt: (placement) => actions.filter((a) => a.placement === placement),
    action: (code) => actions.find((a) => a.code === code),
  };
}
