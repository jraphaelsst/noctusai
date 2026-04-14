import { createAuthProvider } from '@noctusai/shared/components';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';

export const AuthProvider = createAuthProvider(supabase, useAuthStore);
