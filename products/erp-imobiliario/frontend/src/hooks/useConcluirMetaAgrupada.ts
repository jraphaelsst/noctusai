import { useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "@/hooks/use-toast";

export function useConcluirMetaAgrupada() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (metaId: string) => {
      const { data, error } = await supabase.rpc('concluir_meta_agrupada', {
        p_meta_id: metaId
      });

      if (error) throw error;
      
      const result = data as { success: boolean; error?: string; message?: string };
      
      if (!result.success) {
        throw new Error(result.error || 'Erro ao concluir meta');
      }
      
      return result;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast({
        title: "Sucesso!",
        description: data.message || "Meta concluída com sucesso.",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao concluir meta.",
        variant: "destructive",
      });
    },
  });
}
