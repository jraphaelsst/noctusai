import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuthStore } from "@/store/authStore";

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
  const { user } = useAuthStore();

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
    enabled: !!user,
  });
}

