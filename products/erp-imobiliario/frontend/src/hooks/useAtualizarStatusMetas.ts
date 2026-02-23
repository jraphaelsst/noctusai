import { useMutation } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "@/hooks/use-toast";

export function useAtualizarStatusMetas() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await supabase.functions.invoke('atualizar-status-metas');

      if (error) throw error;
      
      return data;
    },
    onSuccess: (data) => {
      toast({
        title: "Status atualizado!",
        description: `${data.metas_atualizadas} metas foram atualizadas.`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao atualizar status das metas.",
        variant: "destructive",
      });
    },
  });
}
