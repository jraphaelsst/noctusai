/**
 * Website-local i18n. NOC-REMEDIATE[seed-promotion]: lift to `@noctusai/lib`
 * once a second consumer needs static-string pt/en translation (contract D3).
 *
 * SSR-safe: no `window`/`document` read at module scope. Locale is derived
 * from the current path (see `lib/routes.ts`), never from the browser.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";
import ptBR from "../i18n/pt-BR.json";
import en from "../i18n/en.json";
import type { Locale } from "../content/types";

const DICTS: Record<Locale, Record<string, unknown>> = { "pt-BR": ptBR, en };

function lookup(dict: Record<string, unknown>, path: string): string | undefined {
  const value = path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object") return (acc as Record<string, unknown>)[key];
    return undefined;
  }, dict);
  return typeof value === "string" ? value : undefined;
}

export type TFn = (key: string, params?: Record<string, string | number>) => string;

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return Object.entries(params).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), template);
}

const LocaleContext = createContext<Locale>("pt-BR");

export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

export function useT(): TFn {
  const locale = useLocale();
  return useMemo(() => {
    const dict = DICTS[locale] ?? DICTS["pt-BR"];
    const fallback = DICTS["pt-BR"];
    return (key: string, params?: Record<string, string | number>) => {
      const raw = lookup(dict, key) ?? lookup(fallback, key) ?? key;
      return interpolate(raw, params);
    };
  }, [locale]);
}

/** Pick the pt/en field of an `L10n` value for the current locale. */
export function useL10n(): (value: { pt: string; en: string }) => string {
  const locale = useLocale();
  return (value) => (locale === "en" ? value.en : value.pt);
}
