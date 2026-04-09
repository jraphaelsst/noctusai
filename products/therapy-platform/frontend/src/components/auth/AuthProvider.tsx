import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';
import { useSupabaseAuthInit } from '@noctusai/shared/auth';

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { setUser, setInitialized } = useAuthStore();

  // Core auth initialization (session + listener) via shared hook
  useSupabaseAuthInit(supabase, setUser, setInitialized);

  return <>{children}</>;
}
