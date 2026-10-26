/** `t(key, vars?)` over the pt-BR table of the leads organ. */
import { MESSAGES } from './messages';

export const t = (key: string, vars?: Record<string, string | number>): string => {
  const raw = (MESSAGES as Record<string, string>)[key] ?? key;
  return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
};
