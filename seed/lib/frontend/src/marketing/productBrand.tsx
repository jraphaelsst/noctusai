/**
 * Per-product STATIC brand accent for the public (landing) pages.
 *
 * A product declares its accent ONCE (a `ProductBrand` const in its own config) and wraps its landing in
 * `<ProductBrandScope brand={…}>`. The accent is applied as CSS variables on a scope element, never on
 * `:root`, so it cannot leak into the authenticated app or other products.
 *
 * PRECEDENCE (documented decision), highest first:
 *   1. a `brand` override on a single element (e.g. a FeatureGrid card link carrying ANOTHER product's accent);
 *   2. this static product brand, inside the `ProductBrandScope`;
 *   3. the org-scoped `BrandProvider` (runtime `GET /api/brand/current`), which writes `:root` / `.dark`;
 *   4. the NOC standard tokens (`tokens.css`).
 * Because the scope sets variables on a descendant, it beats the `:root` org stylesheet regardless of
 * stylesheet order. That is intentional: a product's public landing is that product's identity. The org brand
 * still themes every authenticated screen (the scope is not mounted there) and any landing region outside the scope.
 *
 * Dark mode (`.dark`, the seed's Tailwind `darkMode: "class"` signal): the accent TEXT colour switches to
 * `primary-light` (utility `text-primary dark:text-primary-light`) and `--ring` becomes `primary-light`, so
 * the focus ring stays ≥ 3:1 on the dark background. `--primary` itself is the same in both themes (it only
 * carries white label text and tints).
 *
 * Values are validated with the same HSL-triplet contract as `BrandProvider` and emitted only if they pass:
 * nothing unvalidated is ever concatenated into the stylesheet.
 *
 * No web font: landings use the system font (owner decision). `headingFont` is intentionally not part of
 * the contract; add it with the seed's font loader when a product needs one.
 */
import type { CSSProperties, ReactNode } from "react";
import { HSL_TRIPLET } from "../design-system/brand-tokens";

/** HSL triplets without the `hsl()` wrapper, e.g. `"232 45% 42%"` (the token format used everywhere). */
export interface ProductBrand {
  /** Fills (buttons, tints) and light-theme accent text. White label text must reach AA on it. */
  primary: string;
  /** Accent text on dark surfaces (dark theme, inverse bands) and the dark-theme focus ring. */
  primaryLight: string;
  /** Hover / pressed fill. */
  primaryDark: string;
  /** Light-theme focus ring; defaults to `primary`. */
  ring?: string;
}

const SCOPE_ATTR = "data-product-brand";

function valid(v: string | undefined): v is string {
  return typeof v === "string" && HSL_TRIPLET.test(v);
}

/**
 * The CSS variables for a brand, or `{}` when the brand is invalid (an invalid brand is dropped, never
 * repaired, so the NOC tokens show). Usable as an inline `style` for a single element override.
 */
export function productBrandVars(brand: ProductBrand): CSSProperties {
  if (!valid(brand.primary) || !valid(brand.primaryLight) || !valid(brand.primaryDark)) return {};
  const ring = valid(brand.ring) ? brand.ring : brand.primary;
  return {
    "--primary": brand.primary,
    "--primary-light": brand.primaryLight,
    "--primary-dark": brand.primaryDark,
    "--ring": ring,
    "--sidebar-primary": brand.primary,
  } as CSSProperties;
}

/** The scoped stylesheet text (light set + the dark ring), built only from validated triplets. */
export function productBrandCss(brand: ProductBrand): string {
  const vars = productBrandVars(brand) as Record<string, string>;
  if (!vars["--primary"]) return "";
  const decl = Object.entries(vars).map(([k, v]) => `${k}:${v}`).join(";");
  return (
    `[${SCOPE_ATTR}]{${decl}}` +
    `.dark [${SCOPE_ATTR}]{--ring:${brand.primaryLight};--sidebar-ring:${brand.primaryLight}}`
  );
}

export interface ProductBrandScopeProps {
  brand: ProductBrand;
  children: ReactNode;
}

/**
 * Wraps a public page. Renders a `display: contents` element (no layout box) that carries the variables, plus
 * the scoped stylesheet. Portals (toasts, dialogs) render outside the scope and keep the standard tokens.
 */
export function ProductBrandScope({ brand, children }: ProductBrandScopeProps) {
  const css = productBrandCss(brand);
  return (
    <div {...{ [SCOPE_ATTR]: "" }} className="contents">
      {css ? <style>{css}</style> : null}
      {children}
    </div>
  );
}
