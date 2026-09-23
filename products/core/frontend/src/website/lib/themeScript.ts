/**
 * The inline `<head>` no-flash theme script (contract §4, P6).
 *
 * Runs synchronously before first paint, BEFORE `<body>` exists — so it sets
 * `data-theme` on `<html>` (always present at `<head>` parse time), not on
 * the site root element. `[data-surface="site"]` is a STATIC attribute baked
 * onto `<html>` by every prerendered page (see `entry-server.tsx` /
 * `scripts/prerender-site.mjs`); only `data-theme` is ever toggled at
 * runtime, by this script and by `lib/theme.tsx`'s `ThemeProvider`.
 */
export const THEME_STORAGE_KEY = "nx.theme";

export const THEME_INLINE_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}";var s=localStorage.getItem(k);var t=s;if(!t||t==="system"){t=window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;
