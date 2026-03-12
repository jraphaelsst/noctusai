import { SSOCallback } from '@noctusai/shared/components';
import { supabase } from '@/integrations/supabase/client';

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL || 'http://localhost:8000';
const CORE_URL = import.meta.env.VITE_CORE_URL || 'http://localhost:5173';

export default function ERPSSOCallback() {
  return (
    <SSOCallback
      supabase={supabase}
      coreApiUrl={CORE_API_URL}
      coreUrl={CORE_URL}
    />
  );
}
