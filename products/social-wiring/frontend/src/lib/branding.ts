/**
 * Branding — token resolution, safe preview documents, folder reading.
 *
 * A branding's `tokens` (the design system's tokens.json) are validated by the
 * backend (`branding/tokens_schema.py`); this module only READS them. Because
 * token values end up inside CSS custom properties of a sandboxed preview
 * document, every value is re-checked here (`isSafeCssValue`) — a value that
 * could close a declaration, open a tag or fetch a URL is dropped, never
 * emitted. Component preview HTML is never injected into the page DOM:
 * `buildPreviewDocument` produces a `srcdoc` string for a sandboxed iframe.
 */

// ─── Types (mirror backend/branding/tokens_schema.py) ───────────────────────

export type ColorValue = string | Record<string, string>;

export interface TokenEntry {
  name: string;
  value: ColorValue;
  usage?: string;
}

export interface TypeStyle {
  name: string;
  fontSize: string;
  lineHeight: string | number;
  fontWeight: string | number;
  letterSpacing?: string;
  sample?: string;
  usage?: string;
}

export interface TypeGroup {
  name: string;
  family: string;
  styles: TypeStyle[];
}

export interface FontFaceToken {
  family: string;
  file: string;
  weight: string | number;
}

export interface BrandingTokens {
  name: string;
  version?: number;
  meta?: { source?: string };
  color: { themes: { id: string; name: string }[]; tokens: TokenEntry[] };
  type: {
    fonts: FontFaceToken[];
    families: Record<string, string>;
    groups: TypeGroup[];
  };
  // spacing / radius / opacity / any other scale: { tokens: [...] }
  [scale: string]: unknown;
}

const BASE_KEYS = new Set(["name", "version", "meta", "color", "type"]);

/** Non-base scales (spacing, radius, opacity …) in declaration order. */
export function scalesOf(tokens: BrandingTokens): { key: string; tokens: TokenEntry[] }[] {
  const out: { key: string; tokens: TokenEntry[] }[] = [];
  for (const [key, value] of Object.entries(tokens)) {
    if (BASE_KEYS.has(key)) continue;
    const list = (value as { tokens?: TokenEntry[] } | undefined)?.tokens;
    if (Array.isArray(list)) out.push({ key, tokens: list });
  }
  return out;
}

// ─── Colour resolution ──────────────────────────────────────────────────────

const REF = /^\{([A-Za-z0-9][A-Za-z0-9_.-]{0,63})\}$/;
const FORBIDDEN_CHARS = /[;{}<>\\]/;
const FORBIDDEN_FRAGMENTS = ["url(", "expression(", "javascript:", "@import", "/*", "*/"];

/** True when `value` cannot escape a CSS declaration or fetch a URL. */
export function isSafeCssValue(value: unknown): value is string {
  if (typeof value !== "string" || !value.trim() || value.length > 200) return false;
  if (FORBIDDEN_CHARS.test(value)) return false;
  const low = value.toLowerCase();
  return !FORBIDDEN_FRAGMENTS.some((f) => low.includes(f));
}

function rawColor(entry: TokenEntry, themeId: string): string | null {
  if (typeof entry.value === "string") return entry.value;
  const map = entry.value;
  if (themeId in map) return map[themeId];
  const first = Object.values(map)[0];
  return first ?? null;
}

/** Resolve a colour token for a theme (following `{ref}`s). `null` = unresolvable. */
export function resolveColor(
  tokens: BrandingTokens,
  name: string,
  themeId: string,
  depth = 0,
): string | null {
  if (depth > 8) return null;
  const entry = tokens.color.tokens.find((t) => t.name === name);
  if (!entry) return null;
  const raw = rawColor(entry, themeId);
  if (raw === null) return null;
  const m = REF.exec(raw);
  if (m) return resolveColor(tokens, m[1], themeId, depth + 1);
  return isSafeCssValue(raw) ? raw : null;
}

export interface ResolvedColor {
  name: string;
  value: string | null;
  usage: string;
  /** True for a role token that points at another token ("surface" -> "{ground}"). */
  derived: boolean;
}

export function resolveColors(tokens: BrandingTokens, themeId: string): ResolvedColor[] {
  return tokens.color.tokens.map((t) => ({
    name: t.name,
    value: resolveColor(tokens, t.name, themeId),
    usage: t.usage ?? "",
    derived: typeof t.value !== "string" || REF.test(t.value),
  }));
}

// ─── Preview document ───────────────────────────────────────────────────────

/** CSS custom properties a component preview can read (`var(--ground)`, `var(--font-ui)`, `var(--radius-pill)` …). */
export function buildPreviewVars(tokens: BrandingTokens, themeId: string): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const t of tokens.color.tokens) {
    const v = resolveColor(tokens, t.name, themeId);
    if (v) vars[`--${t.name}`] = v;
  }
  for (const [key, fam] of Object.entries(tokens.type?.families ?? {})) {
    if (isSafeCssValue(fam)) vars[`--font-${key}`] = fam;
  }
  for (const { tokens: list } of scalesOf(tokens)) {
    for (const t of list) {
      if (typeof t.value === "string" && isSafeCssValue(t.value) && !REF.test(t.value)) {
        vars[`--${t.name}`] = t.value;
      }
    }
  }
  return vars;
}

export interface PreviewFont {
  family: string;
  weight: string | number;
  /** Short-TTL signed URL of the uploaded font file. */
  url: string;
}

const FONT_FAMILY_NAME = /^[A-Za-z0-9 _-]{1,80}$/;
const FONT_WEIGHT = /^(\d{3}|normal|bold)$/;
const SAFE_HTTPS_URL = /^https:\/\/[^\s"'()<>\\]+$/;

function fontFaceCss(fonts: PreviewFont[]): { css: string; origins: string[] } {
  const rules: string[] = [];
  const origins = new Set<string>();
  for (const f of fonts) {
    const weight = String(f.weight);
    if (!FONT_FAMILY_NAME.test(f.family) || !FONT_WEIGHT.test(weight) || !SAFE_HTTPS_URL.test(f.url)) continue;
    rules.push(`@font-face{font-family:"${f.family}";font-weight:${weight};src:url("${f.url}")}`);
    origins.add(new URL(f.url).origin);
  }
  return { css: rules.join(""), origins: [...origins] };
}

/**
 * The `srcdoc` of a SANDBOXED preview iframe. A CSP meta locks the document
 * down (no script, no frames, no connections; styles inline + the web-font
 * stylesheet host; images only as data:), and the sandbox attribute on the
 * iframe (see SandboxedPreview) grants no permissions at all.
 */
export function buildPreviewDocument(opts: {
  html: string;
  tokens: BrandingTokens;
  themeId: string;
  fonts?: PreviewFont[];
}): string {
  const vars = buildPreviewVars(opts.tokens, opts.themeId);
  const rootCss = `:root{${Object.entries(vars)
    .map(([k, v]) => `${k}:${v}`)
    .join(";")}}`;
  const { css: fontCss, origins } = fontFaceCss(opts.fonts ?? []);
  const csp = [
    "default-src 'none'",
    "style-src 'unsafe-inline' https://fonts.googleapis.com",
    `font-src https://fonts.gstatic.com ${origins.join(" ")} data:`.trim(),
    "img-src data:",
  ].join("; ");
  return (
    `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${csp}">` +
    `<style>${fontCss}${rootCss}html,body{margin:0}</style></head><body>${opts.html}</body></html>`
  );
}

/** Height hint from a design-system card comment (`<!-- @dsCard height=110 -->`). */
export function previewHeight(html: string, fallback = 220): number {
  const m = /@dsCard[^>]*?height=(\d{2,4})/.exec(html);
  return m ? Math.min(Number(m[1]), 800) : fallback;
}

// ─── Reading a picked design-system folder ──────────────────────────────────

export interface ImportFilePayload {
  path: string;
  content_base64: string;
}

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error(`Falha ao ler ${file.name}`));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

/** Files picked with `<input webkitdirectory>` -> import payload (paths as picked). */
export async function readDesignSystemFiles(files: ArrayLike<File>): Promise<ImportFilePayload[]> {
  const out: ImportFilePayload[] = [];
  for (const file of Array.from(files)) {
    if (file.name === ".DS_Store") continue;
    const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    out.push({ path, content_base64: await readAsBase64(file) });
  }
  return out;
}

/** Read a File as base64 (single asset upload). */
export const fileToBase64 = readAsBase64;

/** Every individual problem of a rejected bundle (`{detail, code, errors}` body), or `[]`. */
export function bundleErrors(err: unknown): string[] {
  const errors = (err as { body?: { errors?: unknown } } | null | undefined)?.body?.errors;
  return Array.isArray(errors) ? errors.filter((e): e is string => typeof e === "string") : [];
}
