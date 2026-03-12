import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { TipoMeta, CategoriaMeta } from "@/types";
import { toast } from "sonner";
import { useAuthStore } from "@/store/authStore";

export interface MetaConfig {
  id: string;
  usuario_id: string;
  tipo: TipoMeta;
  categoria: CategoriaMeta;
  categoria_custom?: string;
  meta_pretendida: number;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface MetaConfigForm {
  categoria: CategoriaMeta;
  categoria_custom?: string;
  meta_pretendida: number;
  ativo?: boolean;
}

export function useMetasConfig() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["metas-config"],
    queryFn: async () => {
      const result = await api.get("/api/metas/config");
      return (result.data || []) as MetaConfig[];
    },
    enabled: !!user,
    staleTime: 10 * 60 * 1000,
  });
}

export function useUpsertMetaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (config: MetaConfigForm) => {
      // Upsert the config via backend
      const result = await api.post("/api/metas/config", {
        categoria: config.categoria,
        categoria_custom: config.categoria_custom,
        meta_pretendida: config.meta_pretendida,
        ativo: config.ativo ?? true,
      });

      // If config is active, create metas from configs
      if (config.ativo ?? true) {
        await api.post("/api/metas/criar-hoje");
      }

      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas-config"] });
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast.success("Sucesso!", { description: "Configurações salvas e metas criadas com sucesso." });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao salvar configuração." });
    },
  });
}

export function useDeleteMetaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/metas/config/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas-config"] });
      toast.success("Sucesso!", { description: "Configuração removida com sucesso." });
    },
    onError: (error: Error) => {
      toast.error("Erro", { description: error.message || "Erro ao remover configuração." });
    },
  });
}
