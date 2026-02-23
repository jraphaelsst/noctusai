import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export type TipoAcao = 'criar' | 'editar' | 'excluir' | 'concluir' | 'arquivar' | 'desarquivar' | 'mover' | 'login' | 'logout';
export type TipoEntidade = 'meta' | 'cliente' | 'usuario' | 'atividade' | 'config_meta' | 'auth' | 'ativo';

export interface ActionLog {
  id: string;
  usuario_id: string;
  tipo_acao: TipoAcao;
  tipo_entidade: TipoEntidade;
  entidade_id?: string;
  descricao: string;
  detalhes?: any;
  created_at: string;
  usuario?: { nome: string; email: string };
}

export function useActionLogs(usuarioId?: string, dataInicio?: Date, dataFim?: Date) {
  return useQuery({
    queryKey: ["action-logs", usuarioId, dataInicio, dataFim],
    queryFn: async () => {
      const result = await api.get("/api/logs", {
        usuario_id: usuarioId,
        data_inicio: dataInicio?.toISOString(),
        data_fim: dataFim ? new Date(dataFim.setHours(23, 59, 59, 999)).toISOString() : undefined,
      });
      return (result.data || []) as ActionLog[];
    },
  });
}

// Action logging is now done server-side.
// This hook is kept as a no-op for backward compatibility.
export function useRegisterAction() {
  return useMutation({
    mutationFn: async (_params: any) => {
      // No-op: all action logging is handled server-side in the backend routers.
      // This hook is kept for API compatibility.
    },
  });
}