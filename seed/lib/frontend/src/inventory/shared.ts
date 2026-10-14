/** Props every inventory organ takes: the hooks factory output + optional copy/label seams. */
import type { InventoryHooks } from './hooks';
import type { InventoryTranslate } from './i18n';

export interface InventoryOrganProps {
  hooks: InventoryHooks;
  /** Translator override (defaults to the shipped pt-BR table). */
  t?: InventoryTranslate;
  locale?: string;
  /** Item display name; the items organ owns names, so the host maps ids -> labels (default: short id). */
  itemLabel?: (itemId: string) => string;
}
