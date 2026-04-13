import { useEffect } from "react";
import { useAuthStore } from "@/store/authStore";
import { useSupabaseAuthInit } from "@noctusai/shared/auth";
import { supabase } from "@/integrations/supabase/client";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setUser, setInitialized } = useAuthStore();

  useSupabaseAuthInit(supabase, {
    onUser: (user) => setUser(user),
    onSignOut: () => setUser(null),
  });

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setInitialized();
    });
  }, []);

  return <>{children}</>;
}
