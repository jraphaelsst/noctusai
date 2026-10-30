/**
 * Brand identity -- client-side validation + CSS building (`noctus.brand-tokens/v1`).
 *
 * Defense in depth over the server's validation (CONTRACT §2): everything that reaches the DOM
 * here is re-checked against the same regexes, so a compromised/buggy response can never inject
 * CSS. Values are only ever emitted from validated triplets/lengths/families; nothing from the
 * response is concatenated into a stylesheet unvalidated.
 */

export const HSL_TRIPLET = /^\d{1,3}(\.\d+)? \d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$/;
export const RADIUS = /^\d+(\.\d+)?(rem|px)$/;
export const FONT_FAMILY = /^[A-Za-z0-9 -]{1,64}$/;
/** A CSS custom-property name suffix (the key list itself is server-owned; derived from tokens.css). */
const TOKEN_KEY = /^[a-z0-9-]{1,40}$/;
const FONT_SLOTS = ['heading', 'body', 'ui'] as const;
export type FontSlot = (typeof FONT_SLOTS)[number];

export interface BrandFont { family: string; weights: number[]; source: 'google' | 'asset' | 'system' }
export interface BrandTokens {
  light: Record<string, string>;
  dark: Record<string, string>;
  radius: string | null;
  fonts: Partial<Record<FontSlot, BrandFont>>;
}

export interface BrandAssets {
  logo_light?: string | null;
  logo_dark?: string | null;
  logo_mark?: string | null;
  favicon?: string | null;
  fonts?: Array<{ family?: string; weight?: number; url?: string | null }> | null;
}

/** `GET /api/brand/current` (CONTRACT §3). */
export interface BrandCurrent {
  source: 'org' | 'platform';
  identity_id: string | null;
  version: number | null;
  tokens: unknown;
  assets: BrandAssets | null;
  updated_at: string | null;
}

function cleanSet(raw: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!raw || typeof raw !== 'object') return out;
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (TOKEN_KEY.test(k) && typeof v === 'string' && HSL_TRIPLET.test(v)) out[k] = v;
  }
  return out;
}

/** Keep only values that pass the contract regexes; everything else is dropped (never repaired). */
export function sanitizeTokens(raw: unknown): BrandTokens {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const fonts: BrandTokens['fonts'] = {};
  const rf = (r.fonts && typeof r.fonts === 'object' ? r.fonts : {}) as Record<string, any>;
  for (const slot of FONT_SLOTS) {
    const f = rf[slot];
    if (!f || typeof f.family !== 'string' || !FONT_FAMILY.test(f.family)) continue;
    const source = f.source === 'google' || f.source === 'asset' ? f.source : 'system';
    const weights = Array.isArray(f.weights)
      ? f.weights.filter((w: unknown): w is number => Number.isInteger(w) && (w as number) >= 100 && (w as number) <= 900)
      : [];
    fonts[slot] = { family: f.family, weights, source };
  }
  return {
    light: cleanSet(r.light),
    dark: cleanSet(r.dark),
    radius: typeof r.radius === 'string' && RADIUS.test(r.radius) ? r.radius : null,
    fonts,
  };
}

/**
 * The override stylesheet text, built ONLY from sanitized tokens. `:root` then `.dark` (same
 * specificity, later wins) so the dark set overrides the light set when `html.dark` is on.
 */
export function buildBrandCss(t: BrandTokens): string {
  const decl = (set: Record<string, string>) =>
    Object.entries(set).map(([k, v]) => `--${k}:${v};`).join('');
  const root = decl(t.light) + (t.radius ? `--radius:${t.radius};` : '')
    + FONT_SLOTS.filter((s) => t.fonts[s])
      .map((s) => `--font-${s}:"${t.fonts[s]!.family}",system-ui,sans-serif;`).join('');
  return `:root{${root}}.dark{${decl(t.dark)}}`;
}

/** Google Fonts stylesheet URL for the `source: google` fonts, or null when there are none. */
export function googleFontsHref(t: BrandTokens): string | null {
  const fams = FONT_SLOTS.map((s) => t.fonts[s]).filter((f): f is BrandFont => !!f && f.source === 'google');
  if (!fams.length) return null;
  const q = fams.map((f) => {
    const w = [...new Set(f.weights)].sort((a, b) => a - b);
    return `family=${encodeURIComponent(f.family).replace(/%20/g, '+')}${w.length ? `:wght@${w.join(';')}` : ''}`;
  }).join('&');
  return `https://fonts.googleapis.com/css2?${q}&display=swap`;
}

/** Only https (signed storage URLs) or same-origin relative URLs may reach `src`/FontFace/favicon. */
export function safeAssetUrl(u: unknown): string | null {
  if (typeof u !== 'string' || !u) return null;
  return /^https:\/\/[^\s"'<>]+$/.test(u) || /^\/(?!\/)[^\s"'<>]*$/.test(u) ? u : null;
}
