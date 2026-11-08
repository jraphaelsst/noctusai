/**
 * The inline `<head>` no-flash theme script (contract §4, P6): now the seed's `createThemeInlineScript`
 * (`@noctusai/lib/marketing`) with the default `nx.theme` key. Runs before first paint and sets `data-theme`
 * and `.dark` on `<html>`; see the seed module for the SSR rules.
 */
export { THEME_INLINE_SCRIPT, THEME_STORAGE_KEY } from "@noctusai/lib/marketing";
