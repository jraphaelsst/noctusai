/**
 * Core's site theme = the seed's SSR-safe 3-state theme (`@noctusai/lib/marketing`), lifted from this file
 * so every landing shares one implementation. Names are kept (`ThemeProvider`, `useSiteTheme`) so the site's
 * routes and nav are unchanged; the storage key stays `nx.theme` (the seed default) so persisted choices survive.
 */
export {
  LandingThemeProvider as ThemeProvider,
  useLandingTheme as useSiteTheme,
} from "@noctusai/lib/marketing";
export type { ResolvedTheme, ThemeChoice } from "@noctusai/lib/marketing";
