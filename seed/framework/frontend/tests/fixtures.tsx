/**
 * Shared test fixtures for createProductApp tests.
 *
 * Two auth shapes are covered:
 *   - `mockSupabaseAuth()`   — default path: returns a fake Supabase client
 *     + a `useAuthStore` hook that surfaces `{ user, isInitialized }` plus
 *     the Zustand-shape writers (`setUser`, `setInitialized`) the default
 *     `createAuthProvider` calls via `useSupabaseAuthInit`.
 *   - `mockAuthProvider()`   — custom path: returns a `CustomAuthProvider`
 *     whose AuthProvider is a no-op wrapper and whose useAuth returns a
 *     test-controllable `{ user, isInitialized }`.
 *
 * Tests compose these to exercise both branches of `createProductApp`.
 */
import type { CustomAuthProvider } from "../src/app";

/** Fake Supabase client with the minimum surface `createAuthProvider` touches. */
export function mockSupabaseAuth() {
  const onAuthStateChange = () => ({
    data: { subscription: { unsubscribe: () => {} } },
  });
  const getSession = async () => ({ data: { session: null }, error: null });

  const client = {
    auth: {
      onAuthStateChange,
      getSession,
    },
  };

  // Zustand-shape store hook. In real products this is a Zustand store;
  // here a function returning a stable object is enough for the test shape.
  const state = { user: null as unknown, isInitialized: true };
  const useAuthStore = () => ({
    user: state.user,
    isInitialized: state.isInitialized,
    setUser: (u: unknown) => { state.user = u; },
    setInitialized: () => { state.isInitialized = true; },
  });

  return { supabase: client as any, useAuthStore, _state: state };
}

/** Custom auth provider — no-op AuthProvider + test-controllable useAuth. */
export function mockAuthProvider(
  initial: { user: unknown; isInitialized: boolean } = { user: null, isInitialized: true },
): CustomAuthProvider & { _set: (u: unknown, inited?: boolean) => void } {
  let current = { ...initial };
  const AuthProvider = ({ children }: { children: React.ReactNode }) => <>{children}</>;
  const useAuth = () => current;
  return {
    AuthProvider,
    useAuth,
    _set: (user, isInitialized = true) => {
      current = { user, isInitialized };
    },
  };
}
