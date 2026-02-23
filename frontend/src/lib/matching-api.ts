/**
 * Utility to call the matching API.
 * Routes through FastAPI backend if VITE_BACKEND_API_URL is set,
 * otherwise falls back to Supabase Edge Functions.
 */
import { supabase } from '@/integrations/supabase/client';

const BACKEND_API_URL = import.meta.env.VITE_BACKEND_API_URL || '';

export async function triggerMatching(params: {
  ativo_origem_id?: string;
  ativo_destino_id?: string;
}): Promise<{ total: number }> {
  if (BACKEND_API_URL) {
    const { data: { session } } = await supabase.auth.getSession();
    const response = await fetch(`${BACKEND_API_URL}/api/matching/gerar`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${session?.access_token}`,
      },
      body: JSON.stringify(params),
    });
    if (!response.ok) throw new Error('Matching request failed');
    return response.json();
  } else {
    const { data, error } = await supabase.functions.invoke('gerar-matches', {
      body: params,
    });
    if (error) throw error;
    return data;
  }
}
