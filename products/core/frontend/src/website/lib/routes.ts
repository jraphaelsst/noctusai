/**
 * Route table — single source of truth for pt-BR/EN localised paths.
 *
 * Consumed by: `routes.tsx` (React Router config), `entry-server.tsx` +
 * `scripts/prerender-site.mjs` (which page to render per route), the header
 * nav, the footer, `LocaleBar` (equivalent-page switch) and the manifest
 * writer (contract §4 `manifest.json`).
 *
 * `PRODUCT_ORDER` in `content/products.ts` supplies the product slugs; a
 * product route is generated for every curated slug, in both languages.
 */
import { PRODUCT_ORDER } from "../content/products";
import type { Locale } from "../content/types";

export interface RouteDef {
  /** Stable id shared by the pt/en twins (hreflang + hydration reads it). */
  id: string;
  pt: string;
  en: string;
  /** Curated product slug this route renders, if any. */
  product?: string;
}

export const ROUTES: RouteDef[] = [
  { id: "home", pt: "/", en: "/en" },
  { id: "products-index", pt: "/produtos", en: "/en/products" },
  ...PRODUCT_ORDER.map((slug) => ({
    id: `product-${slug}`,
    pt: `/produtos/${slug}`,
    en: `/en/products/${slug}`,
    product: slug,
  })),
  { id: "solutions", pt: "/solucoes", en: "/en/solutions" },
  { id: "pricing", pt: "/precos", en: "/en/pricing" },
  { id: "contact", pt: "/contato", en: "/en/contact" },
  { id: "waitlist", pt: "/lista-de-espera", en: "/en/waitlist" },
  { id: "about", pt: "/sobre", en: "/en/about" },
  { id: "not-found", pt: "/404", en: "/en/404" },
];

export function pathFor(id: string, locale: Locale): string {
  const route = ROUTES.find((r) => r.id === id);
  if (!route) return locale === "en" ? "/en" : "/";
  return locale === "en" ? route.en : route.pt;
}

export function routeForPath(path: string): RouteDef | undefined {
  const normalized = path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
  return ROUTES.find((r) => r.pt === normalized || r.en === normalized);
}

export function localeOfPath(path: string): Locale {
  return path === "/en" || path.startsWith("/en/") ? "en" : "pt-BR";
}

/** The equivalent page in the OTHER language, for the locale bar + hreflang. */
export function twinPath(path: string): string | null {
  const route = routeForPath(path);
  if (!route) return null;
  return localeOfPath(path) === "en" ? route.pt : route.en;
}

export const EXTERNAL = {
  login: "https://core.noctusai.com/login",
  signup: "https://core.noctusai.com/login?mode=signup",
  privacyPolicy: "/consent/privacy-policy",
  termsOfUse: "/consent/terms-of-use",
};
