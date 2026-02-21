import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useAuthStore } from "@/store/authStore";

export function useIsDev() {
  const { user } = useAuthStore();

  const { data: isDev, isLoading } = useQuery({
    queryKey: ["is-dev", user?.id],
    queryFn: async () => {
      if (!user) return false;

      const { data, error } = await supabase
        .from("user_roles")
        .select("role")
        .eq("user_id", user.id)
        .in("role", ["dev", "admin"]);

      if (error) throw error;
      if (!data || data.length === 0) return false;
      
      const roles = data.map((r) => r.role);
      return roles.includes("dev") || roles.includes("admin");
    },
    enabled: !!user,
  });

  return { isDev: isDev ?? false, isLoading };
}
