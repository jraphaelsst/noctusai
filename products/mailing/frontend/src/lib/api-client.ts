/**
 * Seed Product API client — powered by the shared factory.
 */
import { createApiClient } from '@noctusai/lib/api';
import { supabase } from '@/integrations/supabase/client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8006';

export const api = createApiClient({
  getBaseUrl: () => BACKEND_URL,
  getAuthToken: async () => {
    const { data } = await supabase.auth.getSession();
    return data?.session?.access_token ?? null;
  },
  onTokenExpired: async () => {
    const { data: { session } } = await supabase.auth.refreshSession();
    return session?.access_token ?? null;
  },
});
