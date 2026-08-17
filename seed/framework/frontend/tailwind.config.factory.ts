/**
 * Tailwind config factory — one-line absorption for product tailwind.config.ts.
 *
 * Before: every product had a near-identical 11-line config with the same
 * preset import, same plugin, same content globs (varying only by whether
 * `./index.html` was included). With 11 products, that's 11 places to keep
 * in sync.
 *
 * After: products call this factory:
 *
 *   import { createTailwindConfig } from "../../../seed/framework/frontend/tailwind.config.factory";
 *   export default createTailwindConfig();
 *
 * Or, when the product needs extra content globs (e.g. an `index.html`
 * scanned for class names):
 *
 *   export default createTailwindConfig({ extraContent: ["./index.html"] });
 *
 * The seed-side base config + plugins live in `noctusai_lib`, so any future
 * product gets the same shape by default. Pattern mirrors the existing
 * `vite.config.factory.ts` factory.
 *
 * ── Theme seam (own-theme opt-out) ──────────────────────────────────────
 * Every field above still assumes the product wants the shared colour
 * system: `presets: [base]`, whose tokens are `hsl(var(--x))` (see
 * `tailwind.config.base.ts`). A product whose palette lives in a
 * DIFFERENT colour space — e.g. OKLCH, `oklch(var(--x) / <alpha-value>)`,
 * where the `<alpha-value>` form is load-bearing for opacity modifiers
 * like `bg-primary/10` — cannot adopt that preset as-is: Tailwind would
 * try to resolve its `hsl(...)` colour function against OKLCH components,
 * breaking every colour that resolves through it.
 *
 * The naive fix — keep the preset AND layer the product's own
 * `theme.extend.colors` on top — was deliberately rejected. Tailwind's
 * preset merge is per-KEY: any base colour token the product does NOT
 * ALSO redeclare (e.g. `success`, `warning`, `primary.light`) would
 * silently survive as `hsl(var(--x))`, pointed at a CSS custom property
 * the product's OKLCH stylesheet never defines. That is a *silent* merge
 * of two colour spaces — invisible until the day someone reaches for
 * `bg-success` and gets nothing. `KB § PATTERNS/frontend/frontend.md` bans
 * exactly that shape of half-migrated config.
 *
 * So the seam is a full opt-OUT, not a partial override: pass `ownTheme`
 * (+ `darkMode` if it isn't the base preset's `"class"`) and the base
 * preset is DROPPED, not merged. `theme` becomes 100% product-owned.
 * Everything else this factory centralises — the content globs (so the
 * seed's own `AppShell`/`Sidebar`/`Header` source is always scanned) and
 * the `tailwindcss-animate` plugin — is still inherited; only the
 * colour-bearing preset is swappable.
 *
 * TRADE-OFF, on the record: a product on `ownTheme` no longer inherits
 * ANY future addition to the base preset — new shared colour tokens, the
 * `container` centering config, the accordion keyframes — automatically.
 * That is the correct price for owning an incompatible colour space; if a
 * product later needs one of those, it re-declares that specific piece
 * itself (p-studio, the first consumer of this seam, currently needs
 * none of them — see `products/p-studio/frontend/tailwind.config.ts`).
 */

import type { Config } from "tailwindcss";
import base from "../../lib/frontend/src/design-system/tailwind.config.base";

export interface CreateTailwindConfigOptions {
  /**
   * Additional content globs beyond the canonical defaults
   * (`./src/**\/*.{ts,tsx}` + the shared lib's design-system).
   * Use for product-specific HTML / MDX / template paths.
   */
  extraContent?: string[];

  /**
   * Additional Tailwind plugins beyond the default `tailwindcss-animate`.
   * Each entry is forwarded to the `plugins` array as-is.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  extraPlugins?: any[];

  /**
   * Product-owned `theme`, replacing the base preset entirely (see the
   * "Theme seam" doc above for why this is an opt-OUT, not a merge).
   * When provided, `presets: [base]` is DROPPED — this factory no longer
   * contributes ANY colour/radius/keyframe tokens, only the content globs
   * and plugin list. Leave unset to keep inheriting the shared design
   * system (every current consumer's behaviour, unchanged).
   */
  ownTheme?: Config["theme"];

  /**
   * Product-owned `darkMode`, used only alongside `ownTheme` (the base
   * preset — the normal source of `darkMode: "class"` — is skipped in
   * that mode, so the product must state its own). Ignored when
   * `ownTheme` is unset.
   */
  darkMode?: Config["darkMode"];
}

const DEFAULT_CONTENT: string[] = [
  "./src/**/*.{ts,tsx}",
  "./index.html",
  "../../../seed/lib/frontend/src/**/*.{ts,tsx}",
  // The framework ships seed-mounted pages (e.g. ConsentSettingsPage, the
  // public /consent legal pages) whose utility classes must be generated into
  // every product's CSS — scan the framework src too, or those pages render
  // unstyled (esp. arbitrary values like text-[0.95rem] / scroll-mt-20).
  "../../../seed/framework/frontend/src/**/*.{ts,tsx}",
];

export function createTailwindConfig(
  options: CreateTailwindConfigOptions = {},
): Config {
  const { extraContent = [], extraPlugins = [], ownTheme, darkMode } = options;
  const usesOwnTheme = ownTheme !== undefined;

  return {
    ...(usesOwnTheme ? {} : { presets: [base] }),
    ...(usesOwnTheme && darkMode !== undefined ? { darkMode } : {}),
    content: [...DEFAULT_CONTENT, ...extraContent],
    ...(usesOwnTheme ? { theme: ownTheme } : {}),
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    plugins: [require("tailwindcss-animate"), ...extraPlugins],
  } satisfies Config;
}
