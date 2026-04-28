/**
 * Adapter that packages core's custom auth (JWT + refresh-token, no Supabase)
 * into the shape `createProductApp` expects via its `authProvider` slot.
 *
 * Core is the identity provider — Supabase delegates to core's backend for
 * every consumer product's auth. That's why core's frontend cannot use the
 * default Supabase-based wiring inside `createProductApp`; it supplies this
 * adapter instead.
 */
import type { CustomAuthProvider } from '@noctusai/seed';
import { AuthProvider as CoreAuthProvider, useAuth } from './auth-context';

function useSeedAuth() {
  const { user, loading } = useAuth();
  return { user, isInitialized: !loading };
}

export const coreAuthProvider: CustomAuthProvider = {
  AuthProvider: CoreAuthProvider,
  useAuth: useSeedAuth,
};
