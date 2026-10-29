/**
 * The organs' message lookup: `t(key, vars?)` over a pt-BR table (+ optional host overrides). An unknown key renders
 * as the key itself (visible, never blank); `{var}` placeholders are interpolated.
 *
 * NOC-REMEDIATE[organ-translator-dry]: commerce / purchasing / quotes / contracts / inventory / erp-dashboard /
 * finance / parties still carry their own copy of this function -- fold each into `createOrganTranslator` (the
 * leads + clients organs already use it). — 2026-10-29
 */
export type OrganTranslate = (key: string, vars?: Record<string, string | number>) => string;

export function createOrganTranslator(messages: Record<string, string>, overrides?: Record<string, string>): OrganTranslate {
  const table = overrides ? { ...messages, ...overrides } : messages;
  return (key, vars) => {
    const raw = table[key] ?? key;
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
  };
}
