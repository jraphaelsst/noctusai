import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';
import { useSupabaseAuthInit } from '@noctusai/shared/auth';
import { useActivityRefresh } from '@noctusai/shared/design-system/useActivityRefresh';
import { InactivityWarning } from '@noctusai/shared/design-system/InactivityWarning';

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { user, setUser, setInitialized } = useAuthStore();
  const navigate = useNavigate();

  // Core auth initialization (session + listener) via shared hook
  useSupabaseAuthInit(supabase, setUser, setInitialized);

  // Proactive token refresh while user is active
  useActivityRefresh({
    onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
    enabled: !!user,
  });

  return (
    <>
      {children}
      {user && (
        <InactivityWarning
          onExtend={async () => { await supabase.auth.refreshSession(); }}
          onExpired={() => { supabase.auth.signOut(); navigate('/login'); }}
        />
      )}
    </>
  );
}
