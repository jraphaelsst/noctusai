import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { createAuthProvider } from '@noctusai/lib/components';
import { useActivityRefresh } from '@noctusai/lib/design-system/useActivityRefresh';
import { InactivityWarning } from '@noctusai/lib/design-system/InactivityWarning';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';

const BaseAuthProvider = createAuthProvider(supabase, useAuthStore);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const navigate = useNavigate();

  // Proactive token refresh while user is active
  useActivityRefresh({
    onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
    enabled: !!user,
  });

  return (
    <BaseAuthProvider>
      {children}
      {user && (
        <InactivityWarning
          onExtend={async () => { await supabase.auth.refreshSession(); }}
          onExpired={() => { supabase.auth.signOut(); navigate('/login'); }}
        />
      )}
    </BaseAuthProvider>
  );
}
