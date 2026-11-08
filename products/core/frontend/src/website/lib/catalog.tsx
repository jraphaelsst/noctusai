/**
 * Public product catalog — `GET /api/website/catalog` (core `website_catalog_service`).
 *
 * Where the data comes from, in order:
 *  1. a BUILD-TIME SNAPSHOT: `scripts/prerender-site.mjs` fetches the endpoint when it can and
 *     bakes the rows into every page as `<script id="nx-catalog" type="application/json">`
 *     (the prerendered HTML is rendered from the same rows, so hydration agrees);
 *  2. a CLIENT REFRESH on mount, which replaces the snapshot with the live rows.
 *
 * No snapshot (build had no network) => the first paint is the LOADING state, never an empty
 * grid, and never a made-up list. Two signals (`KB § PATTERNS/frontend/lying-loading-state.md`):
 * `isLoading = nothing to show yet`, `isRefreshing = a refresh over data` (no early return).
 * A failed refresh keeps the snapshot (stale, flagged) and only surfaces an error when there is
 * nothing at all to show.
 *
 * SSR-safe: nothing here touches `window`/`document` outside effects / the explicit reader.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchCatalog, parseCatalog, type CatalogRow } from "./api";

export const CATALOG_SCRIPT_ID = "nx-catalog";

export interface CatalogState {
  /** `null` = nothing known yet (no snapshot, first fetch pending or failed). */
  products: CatalogRow[] | null;
  /** Nothing to show and a fetch is in flight. */
  isLoading: boolean;
  /** A refresh is running over data we already show. */
  isRefreshing: boolean;
  /** The last fetch failed (with `products` present they are the stale snapshot). */
  isError: boolean;
  refetch: () => void;
}

const NOOP_STATE: CatalogState = { products: null, isLoading: true, isRefreshing: false, isError: false, refetch: () => {} };
const CatalogContext = createContext<CatalogState>(NOOP_STATE);

/** Client-only: read the snapshot the prerender baked into the page (null when absent/unparseable). */
export function readInlineCatalog(): CatalogRow[] | null {
  if (typeof document === "undefined") return null;
  const el = document.getElementById(CATALOG_SCRIPT_ID);
  const text = el?.textContent?.trim();
  if (!text || text === "null" || text === "__NX_CATALOG__") return null;
  try {
    return parseCatalog(JSON.parse(text));
  } catch {
    return null;
  }
}

export function CatalogProvider({ initial, children }: { initial: CatalogRow[] | null; children: ReactNode }) {
  const [products, setProducts] = useState<CatalogRow[] | null>(initial);
  const [isFetching, setIsFetching] = useState(false);
  const [isError, setIsError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsFetching(true);
    fetchCatalog()
      .then((rows) => {
        if (cancelled) return;
        setProducts(rows);
        setIsError(false);
      })
      .catch(() => {
        if (!cancelled) setIsError(true);
      })
      .finally(() => {
        if (!cancelled) setIsFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const refetch = useCallback(() => setAttempt((n) => n + 1), []);
  // Before the first effect runs there is no fetch flag yet: "no data and no error" IS loading.
  const isLoading = products === null && !isError;

  return (
    <CatalogContext.Provider value={{ products, isLoading, isRefreshing: isFetching && products !== null, isError, refetch }}>
      {children}
    </CatalogContext.Provider>
  );
}

export function useCatalog(): CatalogState {
  return useContext(CatalogContext);
}
