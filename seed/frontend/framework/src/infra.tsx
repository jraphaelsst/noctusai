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

  // API client — backend URL injected by createViteConfig via envDir
  const backendUrl = import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8000";
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
