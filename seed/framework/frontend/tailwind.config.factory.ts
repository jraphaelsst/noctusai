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
}

const DEFAULT_CONTENT: string[] = [
  "./src/**/*.{ts,tsx}",
  "./index.html",
  "../../../seed/lib/frontend/src/**/*.{ts,tsx}",
];

export function createTailwindConfig(
  options: CreateTailwindConfigOptions = {},
): Config {
  const { extraContent = [], extraPlugins = [] } = options;

  return {
    presets: [base],
    content: [...DEFAULT_CONTENT, ...extraContent],
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    plugins: [require("tailwindcss-animate"), ...extraPlugins],
  } satisfies Config;
}
