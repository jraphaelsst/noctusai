/**
 * ERP API client — powered by the shared factory.
 * All data operations go through the FastAPI backend.
 * The only direct Supabase usage is for auth (login/signup/session).
 */
import { createApiClient } from '@noctusai/shared/api';
import { supabase } from '@/integrations/supabase/client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

export const api = createApiClient({
  getBaseUrl: () => BACKEND_URL,
  getAuthToken: async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session?.access_token) {
      throw new Error('Nao autenticado');
    }
    return session.access_token;
  },
});
