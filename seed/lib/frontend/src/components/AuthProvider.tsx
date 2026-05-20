/**
 * Shared AuthProvider factory.
 *
 * Creates a React component that initializes Supabase auth (session + listener)
 * via the shared `useSupabaseAuthInit` hook and renders children.
 *
 * Products with no extra auth logic (e.g. Personal Finance) use this directly:
 *   export const AuthProvider = createAuthProvider(supabase, useAuthStore);
 *
 * Products with extra effects (e.g. ERP activity tracking, Therapy inactivity
 * warning) wrap the base component and add their own hooks alongside it.
 *
 * Wave-3 dual-mode (platform-auth-modernization 2026-05-20):
 *   `createSessionAuthProvider(useAuthStore)` ships alongside as the
 *   HttpOnly-cookie-session sibling — wires `useSessionAuthInit`
 *   instead of `useSupabaseAuthInit`. First consumer: social-wiring.
 */
import { useSupabaseAuthInit, useSessionAuthInit } from '../auth';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

interface AuthStoreActions {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setUser: (user: any) => void;
  setInitialized?: () => void;
}

export function createAuthProvider(
  supabase: AnySupabaseClient,
  useAuthStore: () => AuthStoreActions,
) {
  return function AuthProvider({ children }: { children: React.ReactNode }) {
    const { setUser, setInitialized } = useAuthStore();
    useSupabaseAuthInit(supabase, setUser, setInitialized);
    return <>{children}</>;
  };
}

/**
 * Session-cookie sibling of `createAuthProvider`.
 *
 * Wires `useSessionAuthInit` — boots by GETting `/api/auth/me` so the
 * server-side session populates the auth store on page load.
 * No Supabase client needed; the browser carries the cookie.
 *
 * Usage (social-wiring):
 *   export const AuthProvider = createSessionAuthProvider(useAuthStore);
 */
export function createSessionAuthProvider(
  useAuthStore: () => AuthStoreActions,
) {
  return function SessionAuthProvider({ children }: { children: React.ReactNode }) {
    const { setUser, setInitialized } = useAuthStore();
    useSessionAuthInit(setUser, setInitialized);
    return <>{children}</>;
  };
}
