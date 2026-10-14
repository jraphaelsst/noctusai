/** `t(key, vars?)` over the pt-BR table. Unknown key -> the key itself (visible, never blank). */
import { MESSAGES } from './messages';

export type Translate = (key: string, vars?: Record<string, string | number>) => string;

export const t: Translate = (key, vars) => {
  const raw = (MESSAGES as Record<string, string>)[key] ?? key;
  return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
};
