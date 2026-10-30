/**
 * Brand identity — client-side mirror of `projects/org-brand-identity/CONTRACT.md` (§2/§3).
 * The server is the authority; these checks only refuse early what it would refuse anyway.
 * Token KEYS are never listed here: the editor derives them from the identity the server returns
 * (which is filled from the platform row built out of `tokens.css`) — derive, don't sync.
 */

export type BrandStatus = 'draft' | 'active' | 'archived' | 'failed';
export type FontSource = 'google' | 'asset' | 'system';
export type FontRole = 'heading' | 'body' | 'ui';

export interface BrandFont { family: string; weights: number[]; source: FontSource }

export interface BrandTokens {
  schema?: string;
  light: Record<string, string>;
  dark: Record<string, string>;
  radius: string;
  fonts: Partial<Record<FontRole, BrandFont>>;
}

export type AssetSlot = 'logo_light' | 'logo_dark' | 'logo_mark' | 'favicon';
export const ASSET_SLOTS: { slot: AssetSlot; label: string }[] = [
  { slot: 'logo_light', label: 'Logo (fundo claro)' },
  { slot: 'logo_dark', label: 'Logo (fundo escuro)' },
  { slot: 'logo_mark', label: 'Marca (símbolo)' },
  { slot: 'favicon', label: 'Favicon' },
];

/** `GET /api/brand/current` */
export interface BrandCurrent {
  source: 'org' | 'platform';
  identity_id: string | null;
  version: number | null;
  tokens: BrandTokens;
  assets: Partial<Record<AssetSlot, string | null>>;
  updated_at: string | null;
}

export interface ContrastWarning { message?: string; pair?: string; ratio?: number; mode?: string }

export interface BrandValidation {
  warnings?: Array<string | ContrastWarning>;
  filled_from_default?: string[];
  [k: string]: unknown;
}

/** `GET /api/brand/identities` row (no voice). */
export interface BrandIdentitySummary {
  id: string;
  version: number;
  status: BrandStatus;
  created_at: string;
  activated_at: string | null;
}

export interface BrandVoice {
  tone?: string;
  vocabulary?: string;
  do?: string;
  dont?: string;
  [k: string]: unknown;
}

/** `GET /api/brand/identities/{id}` */
export interface BrandIdentity extends BrandIdentitySummary {
  tokens: BrandTokens;
  brand_book: string;
  voice: BrandVoice;
  assets: Record<string, unknown>;
  validation: BrandValidation;
  source?: { error?: string; [k: string]: unknown };
}

export type BrandJobStatus = 'queued' | 'running' | 'done' | 'failed';
export interface BrandJob { status: BrandJobStatus; identity_id?: string; error?: string }
export const jobEmAndamento = (s: BrandJobStatus | undefined) => s === 'queued' || s === 'running';

// ── upload limits (CONTRACT §3 ingest) ──────────────────────────────────────
export const MAX_FILES = 10;
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_TOTAL_BYTES = 25 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = ['md', 'pdf', 'png', 'jpg', 'jpeg', 'webp', 'woff2'] as const;
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(',');

const extOf = (name: string) => (name.includes('.') ? name.split('.').pop()!.toLowerCase() : '');
const mb = (n: number) => `${Math.round(n / (1024 * 1024))} MB`;

/** Refusal reasons for a batch (empty = ok). SVG is refused by the server, so by us. */
export function validateBrandFiles(existing: File[], incoming: File[]): string[] {
  const errors: string[] = [];
  let count = existing.length;
  let total = existing.reduce((n, f) => n + f.size, 0);
  for (const f of incoming) {
    const ext = extOf(f.name);
    if (ext === 'svg') { errors.push(`"${f.name}": SVG não é aceito — envie PNG, JPG ou WEBP.`); continue; }
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) {
      errors.push(`"${f.name}": formato não aceito (use md, pdf, png, jpg, webp ou woff2).`); continue;
    }
    if (f.size > MAX_FILE_BYTES) { errors.push(`"${f.name}": maior que ${mb(MAX_FILE_BYTES)}.`); continue; }
    if (count + 1 > MAX_FILES) { errors.push(`"${f.name}": limite de ${MAX_FILES} arquivos.`); continue; }
    if (total + f.size > MAX_TOTAL_BYTES) { errors.push(`"${f.name}": o total passaria de ${mb(MAX_TOTAL_BYTES)}.`); continue; }
    count += 1;
    total += f.size;
  }
  return errors;
}

// ── value shapes (same regexes as the server guard) ─────────────────────────
export const HSL_RE = /^\d{1,3}(\.\d+)? \d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$/;
export const RADIUS_RE = /^\d+(\.\d+)?(rem|px)$/;
export const FAMILY_RE = /^[A-Za-z0-9 -]{1,64}$/;

/** `"H S% L%"` → `#rrggbb` (for the native color input). */
export function hslTripletToHex(triplet: string): string {
  const m = HSL_RE.test(triplet) ? triplet.replace(/%/g, '').split(' ').map(Number) : [0, 0, 0];
  const [h, s, l] = [m[0] % 360, m[1] / 100, m[2] / 100];
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const hex = (x: number) => Math.round(x * 255).toString(16).padStart(2, '0');
  return `#${hex(f(0))}${hex(f(8))}${hex(f(4))}`;
}

/** `#rrggbb` → `"H S% L%"`. */
export function hexToHslTriplet(hex: string): string {
  const v = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!v) return '0 0% 0%';
  const n = parseInt(v[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => x / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  let h = 0;
  let s = 0;
  if (d !== 0) {
    s = d / (1 - Math.abs(2 * l - 1));
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h = (h * 60 + 360) % 360;
  }
  const r1 = (x: number) => Math.round(x * 10) / 10;
  return `${r1(h)} ${r1(s * 100)}% ${r1(l * 100)}%`;
}

function luminance(triplet: string): number {
  const hex = hslTripletToHex(triplet);
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => {
    const c = x / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

/** WCAG contrast ratio. Live hint only — the server's recomputed report is the record. */
export function contrastRatio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

/** The pairs worth a live hint, DERIVED from the token names: `X` + `X-foreground`, and background/foreground. */
export function contrastPairs(tokens: Record<string, string>): Array<{ fg: string; bg: string }> {
  const pairs: Array<{ fg: string; bg: string }> = [];
  for (const key of Object.keys(tokens)) {
    if (key.endsWith('-foreground') && tokens[key.slice(0, -'-foreground'.length)]) {
      pairs.push({ fg: key, bg: key.slice(0, -'-foreground'.length) });
    }
  }
  if (tokens.foreground && tokens.background) pairs.push({ fg: 'foreground', bg: 'background' });
  return pairs;
}

/** Group token keys for the editor by their first segment; order of first appearance. */
export function groupTokenKeys(keys: string[]): Array<{ group: string; keys: string[] }> {
  const groups = new Map<string, string[]>();
  for (const k of keys) {
    const g = k.startsWith('chart-') ? 'chart' : k.startsWith('sidebar') ? 'sidebar' : k.split('-')[0];
    groups.set(g, [...(groups.get(g) ?? []), k]);
  }
  return [...groups].map(([group, ks]) => ({ group, keys: ks }));
}

export function warningText(w: string | ContrastWarning): string {
  if (typeof w === 'string') return w;
  if (w.message) return w.message;
  const ratio = typeof w.ratio === 'number' ? ` (${w.ratio.toFixed(2)}:1, mínimo 4.5:1)` : '';
  return `Contraste insuficiente${w.pair ? ` em ${w.pair}` : ''}${ratio}`;
}
