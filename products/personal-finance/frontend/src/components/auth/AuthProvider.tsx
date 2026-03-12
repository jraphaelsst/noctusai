import { supabase } from "@/integrations/supabase/client";
import { useAuthStore } from "@/store/authStore";
import { useSupabaseAuthInit } from "@noctusai/shared/auth";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setUser, setInitialized } = useAuthStore();

  useSupabaseAuthInit(supabase, setUser, setInitialized);

  return <>{children}</>;
}
