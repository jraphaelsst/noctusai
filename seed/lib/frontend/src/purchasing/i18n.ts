/** Purchasing i18n: pt-BR table; unknown key -> the key itself (visible, never blank). */
import { PURCHASING_MESSAGES } from './messages';

export type PurchasingTranslate = (key: string, vars?: Record<string, string | number>) => string;

export function createPurchasingTranslator(overrides?: Record<string, string>): PurchasingTranslate {
  const table = { ...(PURCHASING_MESSAGES as Record<string, string>), ...(overrides ?? {}) };
  return (key, vars) => {
    const raw = table[key] ?? key;
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
  };
}

export const defaultPurchasingT: PurchasingTranslate = createPurchasingTranslator();
