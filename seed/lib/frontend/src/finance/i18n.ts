/**
 * Finance i18n — pt-BR only (the organ's audience is a Brazilian store owner). Unknown key →
 * the key itself (visible, never blank); `{var}` placeholders are interpolated.
 */
import { MESSAGES } from './messages';

export type FinanceMessageKey = keyof typeof MESSAGES;
export type FinanceTranslate = (key: string, vars?: Record<string, string | number>) => string;

const table = MESSAGES as Record<string, string>;

export const t: FinanceTranslate = (key, vars) => {
  const raw = table[key] ?? key;
  return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
};

/** Hook-shaped accessor so components read like the commerce organ (`const { t } = useFinanceT()`). */
export function useFinanceT(): { t: FinanceTranslate } {
  return { t };
}
