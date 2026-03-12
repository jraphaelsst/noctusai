/**
 * Shared auth initialization hook.
 *
 * Handles the common pattern of:
 * 1. Getting the initial Supabase session
 * 2. Calling setUser + setInitialized
 * 3. Subscribing to auth state changes
 *
 * Products that need extra logic (e.g. ERP's activity tracking) can still
 * use this as a base and add their own effects alongside it.
 */
import { useEffect } from 'react';
import type { User } from '@supabase/supabase-js';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySupabaseClient = { auth: any };

export function useSupabaseAuthInit(
  supabase: AnySupabaseClient,
  setUser: (user: User | null) => void,
  setInitialized?: () => void,
) {
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }: { data: { session: any } }) => {
      setUser(session?.user ?? null);
      setInitialized?.();
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event: any, session: any) => {
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, [supabase, setUser, setInitialized]);
}
