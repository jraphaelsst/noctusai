/**
 * Shared store factories for NoctusAI products.
 *
 * Usage:
 *   // authStore.ts
 *   import { createAuthStore } from '@noctusai/lib/stores';
 *   export const useAuthStore = createAuthStore();
 *
 *   // filtrosStore.ts
 *   import { createFiltrosStore } from '@noctusai/lib/stores';
 *   export const useFiltrosStore = createFiltrosStore('erp-filtros', 'global');
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ---------------------------------------------------------------------------
// Auth store
// ---------------------------------------------------------------------------

/**
 * The authenticated user held by the store. The platform has TWO auth models —
 * Supabase (a `@supabase/supabase-js` `User`) and the seed's session auth (a
 * `SessionUser` = `{ id, email }`). Rather than binding the shared store to the
 * Supabase `User` class (which a session-auth product like social-wiring can't
 * satisfy), we type it as the minimal common account shape with a passthrough
 * index signature — both models fit, and provider-specific fields
 * (`user_metadata`, `roles`, …) still resolve. Same structural-seam principle
 * as the framework's supabase config typing.
 */
export interface AuthUser {
  id: string;
  email?: string | null;
  [key: string]: any;
}

export interface AuthState {
  user: AuthUser | null;
  isInitialized: boolean;
  setUser: (user: AuthUser | null) => void;
  setInitialized: () => void;
}

export function createAuthStore() {
  return create<AuthState>((set) => ({
    user: null,
    isInitialized: false,
    setUser: (user) => set({ user }),
    setInitialized: () => set({ isInitialized: true }),
  }));
}

// ---------------------------------------------------------------------------
// Filtros store (base — date range + periodo)
// ---------------------------------------------------------------------------

export interface BaseFiltrosState {
  periodo: string;
  dataInicio: string | undefined;
  dataFim: string | undefined;
  setPeriodo: (periodo: string) => void;
  setDataInicio: (data: string | undefined) => void;
  setDataFim: (data: string | undefined) => void;
  limparFiltros: () => void;
}

/**
 * Creates a persisted date-range filter store.
 *
 * @param storeName  localStorage key used by zustand/persist
 * @param defaultPeriodo  initial periodo value (e.g. 'global', 'mensal')
 *
 * Products can extend by creating their own store that includes extra fields
 * alongside the base ones returned here.
 */
export function createFiltrosStore(storeName: string, defaultPeriodo = 'mes') {
  return create<BaseFiltrosState>()(
    persist(
      (set) => ({
        periodo: defaultPeriodo,
        dataInicio: undefined,
        dataFim: undefined,
        setPeriodo: (periodo) => set({ periodo }),
        setDataInicio: (data) => set({ dataInicio: data }),
        setDataFim: (data) => set({ dataFim: data }),
        limparFiltros: () =>
          set({
            periodo: defaultPeriodo,
            dataInicio: undefined,
            dataFim: undefined,
          }),
      }),
      { name: storeName },
    ),
  );
}
