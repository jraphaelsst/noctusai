/**
 * Product Infrastructure Factory
 *
 * Creates all the boilerplate that every product needs from just
 * a schema name. Products import one object instead of maintaining
 * 6+ identical files.
 *
 * Usage:
 *   import { createProductInfra } from "@noctusai/seed";
 *   export const infra = createProductInfra({ schema: "mailing" });
 *
 * Then in App.tsx:
 *   export default createProductApp({
 *     ...infra.appConfig,
 *     routes: [...],
 *     Layout,
 *   });
 */
import { createProductSupabase } from "@noctusai/lib/supabase";
import { createAuthStore } from "@noctusai/lib/stores";
import { createApiClient } from "@noctusai/lib/api";
import { createNotificationHooks } from "@noctusai/lib/notifications";
import { createAuthProvider } from "@noctusai/lib/components";
import { NotificationBell as SharedNotificationBell } from "@noctusai/lib/design-system";

interface ProductInfraConfig {
  /** Database schema name. Optional — auto-detected from VITE_PRODUCT_SCHEMA
   *  (injected by createViteConfig). Only pass explicitly if overriding. */
  schema?: string;
}

// Re-entrancy guard: a page fires many requests at once, so a dead session
// produces a BURST of 401s. Collapse them to a single logout + redirect.
let _handlingDeadSession = false;

/**
 * A request came back 401 with no recovery (no token, or refresh failed / the
 * retry still 401'd) — the session is dead. Clear the local auth state + sign
 * out (purging the stale token from storage), which flips the app's `!user`
 * gate in `createProductApp` and redirects to Landing/login. Without this the
 * user is stranded on a logged-in-looking shell that 401s every call
 * ("[401] Token ausente" on every page — the 2026-07-03 report).
 *
 * Idempotent (guarded); never redirects when already on a public auth route
 * (/login, /sso) to avoid a loop; best-effort throughout (never throws into the
 * fetch path). Clearing `user` drives a CLIENT-side redirect (React Router
 * `<Navigate>`), so no full reload; `signOut()` also fires `onAuthStateChange`
 * → `setUser(null)` as a belt.
 */
function handleDeadSession(supabase: { auth: { signOut?: () => Promise<unknown> } }, useAuthStore: {
  getState: () => { setUser?: (u: null) => void };
}): void {
  if (_handlingDeadSession) return;
  const path = typeof window !== "undefined" ? window.location.pathname : "";
  if (path.startsWith("/login") || path.startsWith("/sso")) return;
  _handlingDeadSession = true;
  try { useAuthStore.getState().setUser?.(null); } catch { /* best-effort */ }
  try { void supabase.auth.signOut?.()?.catch?.(() => {}); } catch { /* best-effort */ }
  // Reset the guard so a later genuine re-login → expiry can redirect again.
  if (typeof window !== "undefined") {
    window.setTimeout(() => { _handlingDeadSession = false; }, 3000);
  }
}

/**
 * Creates all product infrastructure from a schema name.
 *
 * Returns:
 *   - supabase: Supabase client targeting the product schema
 *   - useAuthStore: Zustand auth store
 *   - api: API client wired to the backend (port from createViteConfig)
 *   - AuthProvider: React provider for auth state
 *   - NotificationBell: Pre-wired notification bell component
 *   - notification hooks: useNotificacoes, useContagemNaoLidas, etc.
 *   - appConfig: { supabase, useAuthStore } ready to spread into createProductApp
 */
export function createProductInfra(config: ProductInfraConfig = {}) {
  const schema = config.schema || import.meta.env.VITE_PRODUCT_SCHEMA || "public";

  // Supabase client targeting this product's schema
  const supabase = createProductSupabase(schema);

  // Auth store
  const useAuthStore = createAuthStore();

  // API client — house single-container model: uvicorn serves SPA + API
  // on ONE port via the seed `serve_spa` seam, so the default is
  // **same-origin** (empty string → fetch sees a relative URL → same
  // host:port the page loaded from). `VITE_BACKEND_API_URL` overrides
  // for bare-vite-dev (`vite dev` on the frontend port talks to a
  // separately-run backend) or staging that points elsewhere.
  //
  // Historic bug (fixed 2026-05-20): the default was `http://localhost:8000`
  // which silently routed every non-core product's FE at CORE — CORS
  // blocked, fetch threw, every endpoint toasted "Servidor indisponivel".
  // Core happened to work only because its BE is also on :8000.
  const backendUrl = import.meta.env.VITE_BACKEND_API_URL ?? "";
  const api = createApiClient({
    getBaseUrl: () => backendUrl,
    getAuthToken: async () => {
      const { data } = await supabase.auth.getSession();
      return data?.session?.access_token ?? null;
    },
    onTokenExpired: async () => {
      const { data: { session } } = await supabase.auth.refreshSession();
      return session?.access_token ?? null;
    },
    // Dead session (401 the refresh couldn't recover) → clear auth + redirect to
    // login, instead of stranding the user on a shell that 401s every call.
    onUnauthenticated: () => handleDeadSession(supabase, useAuthStore),
  });

  // Auth provider
  const AuthProvider = createAuthProvider(supabase, useAuthStore);

  // Notification hooks
  const {
    useNotificacoes,
    useContagemNaoLidas,
    useMarcarComoLida,
    useMarcarTodasComoLidas,
  } = createNotificationHooks(api, useAuthStore);

  // Pre-wired notification bell
  const notificationHooks = { useNotificacoes, useContagemNaoLidas, useMarcarComoLida, useMarcarTodasComoLidas };
  function NotificationBell() {
    return <SharedNotificationBell hooks={notificationHooks} />;
  }

  return {
    supabase,
    useAuthStore,
    api,
    AuthProvider,
    NotificationBell,
    useNotificacoes,
    useContagemNaoLidas,
    useMarcarComoLida,
    useMarcarTodasComoLidas,

    /** Spread into createProductApp config */
    appConfig: {
      supabase,
      useAuthStore,
    },
  };
}

/**
 * Default product infrastructure singleton.
 *
 * Auto-detects schema from VITE_PRODUCT_SCHEMA (injected by createViteConfig).
 * Products import directly — no per-product infra.ts file needed.
 *
 * Usage in pages:
 *   import { supabase, useAuthStore, api } from "@noctusai/seed/infra";
 *
 * Usage in App.tsx:
 *   import infra from "@noctusai/seed/infra";
 *   const Layout = createProductLayout({ ...infra.appConfig, ... });
 */
const infra = createProductInfra();

export const { supabase, useAuthStore, api, AuthProvider, NotificationBell } = infra;
export const { useNotificacoes, useContagemNaoLidas, useMarcarComoLida, useMarcarTodasComoLidas } = infra;
export const { appConfig } = infra;
export default infra;
