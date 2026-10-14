/** Quotes i18n: pt-BR table; unknown key -> the key itself (visible, never blank). */
import { QUOTES_MESSAGES } from './messages';

export type QuotesTranslate = (key: string, vars?: Record<string, string | number>) => string;

export function createQuotesTranslator(overrides?: Record<string, string>): QuotesTranslate {
  const table = { ...(QUOTES_MESSAGES as Record<string, string>), ...(overrides ?? {}) };
  return (key, vars) => {
    const raw = table[key] ?? key;
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
  };
}

export const defaultQuotesT: QuotesTranslate = createQuotesTranslator();
