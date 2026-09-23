/**
 * Assembles the `<head>` markup for one prerendered page (09 §Per-page SEO
 * contract, contract §4). Pure string building — called once per route by
 * `scripts/prerender-site.mjs`. Kept as plain functions (no React) so the
 * exact same logic is trivially testable from the build-output check.
 */
import { THEME_INLINE_SCRIPT } from "./themeScript";
import { ROUTES, type RouteDef } from "./routes";
import type { PageMeta } from "./pageMeta";
import type { Locale } from "../content/types";

const ORIGIN = "https://noctusai.com";

function escapeAttr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export interface HeadOptions {
  route: RouteDef;
  locale: Locale;
  path: string; // the specific pt or en path being rendered
  meta: PageMeta;
  assetTags: string; // <script>/<link> tags from the Vite manifest
  ogImagePath: string; // e.g. "/_site/og/home-pt.png"
  settingsJson: string; // "__NX_SETTINGS__" placeholder or the real defaults JSON for local previews
}

export function buildHead(opts: HeadOptions): string {
  const { route, locale, path, meta, assetTags, ogImagePath, settingsJson } = opts;
  const htmlLang = locale === "en" ? "en" : "pt-BR";
  const canonical = `${ORIGIN}${path}`;
  const ogUrl = `${ORIGIN}${ogImagePath}`;

  const alternates = [
    `<link rel="alternate" hreflang="pt-BR" href="${ORIGIN}${route.pt}" />`,
    `<link rel="alternate" hreflang="en" href="${ORIGIN}${route.en}" />`,
    `<link rel="alternate" hreflang="x-default" href="${ORIGIN}${route.pt}" />`,
  ].join("\n    ");

  const jsonLdScripts = meta.jsonLd
    .map((node) => `<script type="application/ld+json">${JSON.stringify(node)}</script>`)
    .join("\n    ");

  return `<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(meta.title)}</title>
    <meta name="description" content="${escapeAttr(meta.description)}" />
    <link rel="canonical" href="${canonical}" />
    ${alternates}
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="NoctusAI" />
    <meta property="og:title" content="${escapeAttr(meta.title)}" />
    <meta property="og:description" content="${escapeAttr(meta.description)}" />
    <meta property="og:url" content="${canonical}" />
    <meta property="og:image" content="${ogUrl}" />
    <meta property="og:locale" content="${locale === "en" ? "en_US" : "pt_BR"}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeAttr(meta.title)}" />
    <meta name="twitter:description" content="${escapeAttr(meta.description)}" />
    <meta name="twitter:image" content="${ogUrl}" />
    <link rel="preload" as="font" type="font/woff2" href="/_site/fonts/inter-latin-400.woff2" crossorigin="anonymous" />
    <link rel="preload" as="font" type="font/woff2" href="/_site/fonts/jetbrains-mono-latin-400.woff2" crossorigin="anonymous" />
    <script>${THEME_INLINE_SCRIPT}</script>
    <script id="nx-settings" type="application/json">${settingsJson}</script>
    ${jsonLdScripts}
    ${assetTags}
  </head>`;
}

export function htmlLangFor(locale: Locale): string {
  return locale === "en" ? "en" : "pt-BR";
}

export { ROUTES };
