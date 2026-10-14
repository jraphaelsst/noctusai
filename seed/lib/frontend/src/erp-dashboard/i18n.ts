/** ERP dashboard i18n: pt-BR table; unknown key -> the key itself (visible, never blank). */
import { ERP_DASHBOARD_MESSAGES } from './messages';

export type ErpDashboardTranslate = (key: string, vars?: Record<string, string | number>) => string;

export function createErpDashboardTranslator(overrides?: Record<string, string>): ErpDashboardTranslate {
  const table = { ...(ERP_DASHBOARD_MESSAGES as Record<string, string>), ...(overrides ?? {}) };
  return (key, vars) => {
    const raw = table[key] ?? key;
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
  };
}

export const defaultErpDashboardT: ErpDashboardTranslate = createErpDashboardTranslator();
