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
 */
import { useSupabaseAuthInit } from '../auth';

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
