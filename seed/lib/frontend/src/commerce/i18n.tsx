/**
 * Commerce i18n — a small map keyed by locale. pt-BR is the default; `en` is
 * the second shipped locale. Unknown locale → pt-BR; unknown key → the key
 * itself (visible, never blank). A storefront's `locale` (from
 * `GET /api/storefront`) selects the language via `CommerceLocaleProvider`
 * (`StorefrontShell` mounts one).
 */
import * as React from 'react';
import { MESSAGES } from './messages';

export type CommerceLocale = keyof typeof MESSAGES;
export const COMMERCE_LOCALES = Object.keys(MESSAGES) as CommerceLocale[];
export const DEFAULT_COMMERCE_LOCALE: CommerceLocale = 'pt-BR';

export type Translate = (key: string, vars?: Record<string, string | number>) => string;

export function resolveLocale(locale: string | null | undefined): CommerceLocale {
  if (locale && locale in MESSAGES) return locale as CommerceLocale;
  const lang = locale?.split('-')[0]?.toLowerCase();
  const byLang = COMMERCE_LOCALES.find((l) => l.toLowerCase().split('-')[0] === lang);
  return byLang ?? DEFAULT_COMMERCE_LOCALE;
}

export function createTranslator(locale: string | null | undefined): Translate {
  const table = MESSAGES[resolveLocale(locale)] as Record<string, string>;
  const fallback = MESSAGES[DEFAULT_COMMERCE_LOCALE] as Record<string, string>;
  return (key, vars) => {
    const raw = table[key] ?? fallback[key] ?? key;
    return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
  };
}

const LocaleContext = React.createContext<string>(DEFAULT_COMMERCE_LOCALE);

export function CommerceLocaleProvider({ locale, children }: { locale: string; children: React.ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

/** `[t, locale]` — an explicit `locale` prop wins over the surrounding provider. */
export function useCommerceT(localeOverride?: string): { t: Translate; locale: CommerceLocale } {
  const ctx = React.useContext(LocaleContext);
  const locale = resolveLocale(localeOverride ?? ctx);
  const t = React.useMemo(() => createTranslator(locale), [locale]);
  return { t, locale };
}
