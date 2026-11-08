/**
 * Central-login entry helpers (contract: products/core/CONTRACTS/sso-entry.md).
 *
 * `produto` is a catalog SLUG, never a URL; `next` is a PATH inside the product. The product
 * URL only ever comes from the server (`GET /api/sso/produto/{slug}` / `POST /api/sso/token`),
 * so there is no URL parameter to abuse as an open redirect.
 */
import { api } from './api';

export type SsoPrompt = 'none' | 'login';

export interface SsoEntry {
  produto: string;
  next: string | null;
  prompt: SsoPrompt;
}

export interface SsoProduto {
  slug: string;
  nome: string;
  icone: string | null;
  landing_url: string;
}

/** Path-only: "/x", never "//host", a scheme, a backslash or a control char. Else `null`. */
export function sanitizeNext(raw: string | null | undefined): string | null {
  if (!raw) return null;
  // eslint-disable-next-line no-control-regex
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\') || /[\u0000-\u001f\u007f]/.test(raw)) {
    return null;
  }
  return raw;
}

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;

/** Reads `produto/next/prompt`; `null` when there is no (well-formed) `produto`. */
export function readSsoEntry(params: URLSearchParams): SsoEntry | null {
  const produto = (params.get('produto') ?? '').trim().toLowerCase();
  if (!SLUG_RE.test(produto)) return null;
  return {
    produto,
    next: sanitizeNext(params.get('next')),
    prompt: params.get('prompt') === 'none' ? 'none' : 'login',
  };
}

/** `?produto=..&next=..` (never `prompt`) to carry through core's own pages. */
export function entryQuery(entry: SsoEntry | null): string {
  if (!entry) return '';
  const q = new URLSearchParams({ produto: entry.produto });
  if (entry.next) q.set('next', entry.next);
  return `?${q.toString()}`;
}

// --- OAuth round trip: the provider sends the browser back to a bare /login -------------------

const STASH_KEY = 'noctus:sso-entry';
const STASH_TTL_MS = 10 * 60 * 1000;

export function stashSsoEntry(entry: SsoEntry): void {
  try {
    sessionStorage.setItem(STASH_KEY, JSON.stringify({ ...entry, at: Date.now() }));
  } catch {
    /* storage blocked: the visitor lands on core's home instead of the product; nothing is lost */
  }
}

/** Reads (without removing) a fresh stash; an expired or malformed one is dropped. */
export function peekStashedSsoEntry(): SsoEntry | null {
  try {
    const raw = sessionStorage.getItem(STASH_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<SsoEntry> & { at?: number };
    const fresh = typeof v.at === 'number' && Date.now() - v.at < STASH_TTL_MS;
    const entry = fresh ? readSsoEntry(new URLSearchParams({ produto: String(v.produto ?? ''), ...(v.next ? { next: v.next } : {}), prompt: v.prompt ?? 'login' })) : null;
    if (!entry) sessionStorage.removeItem(STASH_KEY);
    return entry;
  } catch {
    return null;
  }
}

export function clearStashedSsoEntry(): void {
  try {
    sessionStorage.removeItem(STASH_KEY);
  } catch {
    /* nothing to clear */
  }
}

// --- Launch -----------------------------------------------------------------------------------

/** Server `redirect_url` + the post-entry path. `&next=` extends the token's own fragment/query. */
export function withNextPath(redirectUrl: string, next: string | null): string {
  return next ? `${redirectUrl}&next=${encodeURIComponent(next)}` : redirectUrl;
}

/** The `prompt=none` bounce back to the product when core has no session. */
export function loginRequiredUrl(landingUrl: string): string {
  return `${landingUrl}#sso=login_required`;
}

/**
 * ONE `POST /api/sso/token` (the call Dashboard uses), then a same-tab replace. Throws the api
 * error on refusal (403 no licence, 409 cross-site, ...) so the page can show it ON CORE.
 */
export async function launchProduct(entry: SsoEntry, navigate: (url: string) => void = (u) => window.location.replace(u)): Promise<void> {
  const res = await api.post('/api/sso/token', { product_slug: entry.produto });
  clearStashedSsoEntry();
  navigate(withNextPath(res.redirect_url, entry.next));
}
