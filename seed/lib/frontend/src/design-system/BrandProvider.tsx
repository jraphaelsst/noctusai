/**
 * BrandProvider -- the org's visual identity, applied by construction (org-brand-identity
 * CONTRACT §5). Mounted ONCE in the seed app shell (`createProductApp`); core and every
 * product wear the selected org's identity, falling back to the NOC standard (`tokens.css`).
 *
 * - Fetches `GET /api/brand/current` on CORE (`coreApi`, same auth channel as `/api/me/access`);
 *   the query key (`brandCurrentQueryKey`) carries the org id so org A's identity never survives under org B.
 * - Applies ONLY client-validated values (`brand-tokens.ts`) through a generated override
 *   stylesheet (light `:root` + `.dark`), Google fonts via `<link>`, signed font URLs via
 *   `FontFace`, favicon via `<link rel=icon>`.
 * - The last identity applied per org is cached in localStorage (tokens only -- signed asset
 *   URLs expire) and applied synchronously at boot: no flash of the NOC theme.
 * - Loading signals derive from `data` (never `isLoading`): `isLoading` = nothing to show yet.
 *   No `placeholderData`: the brand is org-scoped, so a previous org's answer must never stand
 *   in for the next org's.
 * - Failure keeps what is applied (cache or NOC standard), is logged, and `source` is
 *   `"platform"` -- never a crash, never silent.
 */
import { createContext, useContext, useLayoutEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { coreApi, api } from '@noctusai/seed/infra';
import { meAccessQueryOptions, type MeAccess } from '../access';
import {
  buildBrandCss, googleFontsHref, safeAssetUrl, sanitizeTokens,
  type BrandCurrent, type BrandTokens,
} from './brand-tokens';

/** THE cache key of `GET /api/brand/current` (shared with core's "Identidade visual" page, which writes it on activate so a swap reskins live). */
export const brandCurrentQueryKey = (orgId: string | null) => ['core', 'brand', orgId ?? 'none', 'current'] as const;
const CACHE_PREFIX = 'noc:brand:';
const LAST_ORG_KEY = 'noc:brand:last-org';
const STYLE_ID = 'noc-brand-tokens';
const GOOGLE_LINK_ID = 'noc-brand-google-fonts';
const FAVICON_ID = 'noc-brand-favicon';

export interface BrandLogo { light: string | null; dark: string | null; mark: string | null }
export interface BrandContextValue {
  logo: BrandLogo;
  favicon: string | null;
  source: 'org' | 'platform';
  /** Nothing to show yet (no cache, no answer): a first load, never a background refetch. */
  isLoading: boolean;
}
const NOC_STANDARD: BrandContextValue = {
  logo: { light: null, dark: null, mark: null }, favicon: null, source: 'platform', isLoading: false,
};
const BrandContext = createContext<BrandContextValue>(NOC_STANDARD);

/** `{logo, favicon, source, isLoading}` for Sidebar/Header logos. Safe without a provider (NOC standard). */
export function useBrand(): BrandContextValue {
  return useContext(BrandContext);
}

// ── storage (try/catch: private mode / disabled storage must never break boot) ─────────────
function readCache(orgId: string): BrandTokens | null {
  try {
    const raw = window.localStorage.getItem(CACHE_PREFIX + orgId);
    return raw ? sanitizeTokens(JSON.parse(raw)) : null;
  } catch (err) {
    console.warn('[brand] cache read failed', err);
    return null;
  }
}
function writeCache(orgId: string, tokens: BrandTokens): void {
  try {
    window.localStorage.setItem(CACHE_PREFIX + orgId, JSON.stringify(tokens));
    window.localStorage.setItem(LAST_ORG_KEY, orgId);
  } catch (err) {
    console.warn('[brand] cache write failed', err);
  }
}
function clearCache(orgId: string): void {
  try { window.localStorage.removeItem(CACHE_PREFIX + orgId); } catch { /* storage unavailable: nothing cached to clear */ }
}
function lastOrgTokens(): BrandTokens | null {
  try {
    const org = window.localStorage.getItem(LAST_ORG_KEY);
    return org ? readCache(org) : null;
  } catch (err) {
    console.warn('[brand] cache read failed', err);
    return null;
  }
}

// ── DOM application ─────────────────────────────────────────────────────────────────────
function upsert<K extends keyof HTMLElementTagNameMap>(tag: K, id: string): HTMLElementTagNameMap[K] {
  let el = document.getElementById(id) as HTMLElementTagNameMap[K] | null;
  if (!el) {
    el = document.createElement(tag);
    el.id = id;
    document.head.appendChild(el);
  }
  return el;
}
function remove(id: string) { document.getElementById(id)?.remove(); }

const loadedFaces = new Set<string>();
function applyTokens(t: BrandTokens | null): void {
  if (!t) { remove(STYLE_ID); remove(GOOGLE_LINK_ID); return; }
  upsert('style', STYLE_ID).textContent = buildBrandCss(t);
  const href = googleFontsHref(t);
  if (href) {
    const link = upsert('link', GOOGLE_LINK_ID);
    link.rel = 'stylesheet';
    if (link.href !== href) link.href = href;
  } else remove(GOOGLE_LINK_ID);
}

function applyAssetFonts(tokens: BrandTokens, assets: BrandCurrent['assets']): void {
  if (typeof FontFace === 'undefined') return;
  for (const f of assets?.fonts ?? []) {
    const url = safeAssetUrl(f?.url);
    const family = f?.family;
    if (!url || !family || !Object.values(tokens.fonts).some((x) => x?.family === family && x.source === 'asset')) continue;
    const weight = Number.isInteger(f.weight) ? String(f.weight) : '400';
    const key = `${family}|${weight}|${url}`;
    if (loadedFaces.has(key)) continue;
    loadedFaces.add(key);
    const face = new FontFace(family, `url("${url}")`, { weight });
    face.load().then(
      (loaded) => { document.fonts.add(loaded); },
      (err) => { loadedFaces.delete(key); console.error('[brand] font load failed', family, err); },
    );
  }
}

function applyFavicon(href: string | null): void {
  if (!href) { remove(FAVICON_ID); return; }
  const link = upsert('link', FAVICON_ID);
  link.rel = 'icon';
  link.href = href;
}

/** Boot-time apply from the last org's cache, before the first paint of the provider tree. */
function bootApply(): BrandTokens | null {
  if (typeof document === 'undefined') return null;
  const cached = lastOrgTokens();
  if (cached) applyTokens(cached);
  return cached;
}

export interface BrandProviderProps {
  children: ReactNode;
  /** The session is authenticated; the identity is only fetched then. Default true. */
  authenticated?: boolean;
}

export function BrandProvider({ children, authenticated = true }: BrandProviderProps) {
  const [booted] = useState(bootApply);

  // Same cache entry as the picker/gate (`meAccessQueryOptions`); only enabled when authenticated.
  const access = useQuery<MeAccess>({
    ...meAccessQueryOptions(() => api.get<MeAccess>('/api/me/access')),
    enabled: authenticated,
  });
  const accessAnswered = access.data !== undefined || access.isError;
  const orgId = access.data?.org?.id ?? null;

  const brand = useQuery<BrandCurrent>({
    queryKey: brandCurrentQueryKey(orgId),
    queryFn: () => coreApi.get<BrandCurrent>('/api/brand/current'),
    enabled: authenticated && accessAnswered,
    staleTime: 5 * 60_000,
    retry: false,
  });

  const data = brand.data;
  const tokens = useMemo(() => (data ? sanitizeTokens(data.tokens) : null), [data]);

  useLayoutEffect(() => {
    if (!authenticated) return;
    if (tokens && data) {
      applyTokens(tokens);
      applyAssetFonts(tokens, data.assets);
      if (orgId) {
        if (data.source === 'org') writeCache(orgId, tokens);
        else clearCache(orgId);
      }
      return;
    }
    if (orgId && brand.isError) {
      console.error('[brand] /api/brand/current failed; keeping the applied identity', brand.error);
      return;
    }
    // Org known, answer pending: show that org's cached identity, else the NOC standard.
    if (orgId) applyTokens(readCache(orgId));
  }, [authenticated, tokens, data, orgId, brand.isError, brand.error]);

  const value = useMemo<BrandContextValue>(() => {
    const a = data?.assets;
    const favicon = safeAssetUrl(a?.favicon);
    return {
      logo: {
        light: safeAssetUrl(a?.logo_light), dark: safeAssetUrl(a?.logo_dark), mark: safeAssetUrl(a?.logo_mark),
      },
      favicon,
      source: data && !brand.isError ? data.source : 'platform',
      // Never `isLoading`: nothing to show = no answer AND no boot-applied cache.
      isLoading: authenticated && !data && !brand.isError && !booted,
    };
  }, [data, brand.isError, authenticated, booted]);

  useLayoutEffect(() => { applyFavicon(value.favicon); }, [value.favicon]);

  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
}
