/** Inventory i18n: pt-BR table; unknown key -> the key itself (visible, never blank). */
import { INVENTORY_MESSAGES } from './messages';

export type InventoryTranslate = (key: string, vars?: Record<string, string | number>) => string;

export function createInventoryTranslator(overrides?: Record<string, string>): InventoryTranslate {
  const table = { ...(INVENTORY_MESSAGES as Record<string, string>), ...(overrides ?? {}) };
  return (key, vars) => {
    const raw = table[key] ?? key;
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
  };
}

export const defaultInventoryT: InventoryTranslate = createInventoryTranslator();
