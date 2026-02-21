import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "@/hooks/use-toast";

export type TipoAcao = 'criar' | 'editar' | 'excluir' | 'concluir' | 'arquivar' | 'desarquivar' | 'mover' | 'login' | 'logout';
export type TipoEntidade = 'meta' | 'cliente' | 'usuario' | 'atividade' | 'config_meta' | 'auth';

export interface ActionLog {
  id: string;
  usuario_id: string;
  tipo_acao: TipoAcao;
  tipo_entidade: TipoEntidade;
  entidade_id?: string;
  descricao: string;
  detalhes?: any;
  created_at: string;
  usuario?: {
    nome: string;
    email: string;
  };
}

export interface RegisterActionParams {
  tipo_acao: TipoAcao;
  tipo_entidade: TipoEntidade;
  entidade_id?: string;
  descricao: string;
  detalhes?: any;
}

// Hook para buscar logs com filtros
export function useActionLogs(usuarioId?: string, dataInicio?: Date, dataFim?: Date) {
  return useQuery({
    queryKey: ["action-logs", usuarioId, dataInicio, dataFim],
    queryFn: async () => {
      let query = supabase
        .from("user_actions_log")
        .select("*")
        .order("created_at", { ascending: false });

      if (usuarioId && usuarioId !== "todos") {
        query = query.eq("usuario_id", usuarioId);
      }

      if (dataInicio) {
        query = query.gte("created_at", dataInicio.toISOString());
      }

      if (dataFim) {
        const endOfDay = new Date(dataFim);
        endOfDay.setHours(23, 59, 59, 999);
        query = query.lte("created_at", endOfDay.toISOString());
      }

      const { data: logs, error } = await query;

      if (error) throw error;

      // Buscar dados dos usuários separadamente
      if (logs && logs.length > 0) {
        const usuarioIds = [...new Set(logs.map(log => log.usuario_id))];
        const { data: usuarios } = await supabase
          .from("profiles")
          .select("id, nome, email")
          .in("id", usuarioIds);

        // Mapear usuários aos logs
        const usuariosMap = new Map(usuarios?.map(u => [u.id, u]));
        
        return logs.map(log => ({
          ...log,
          usuario: usuariosMap.get(log.usuario_id)
        })) as ActionLog[];
      }

      return logs as ActionLog[];
    },
  });
}

// Hook para registrar ação
export function useRegisterAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: RegisterActionParams) => {
      const { data: { user } } = await supabase.auth.getUser();
      
      if (!user) {
        throw new Error("Usuário não autenticado");
      }

      const { error } = await supabase
        .from("user_actions_log")
        .insert({
          usuario_id: user.id,
          tipo_acao: params.tipo_acao,
          tipo_entidade: params.tipo_entidade,
          entidade_id: params.entidade_id,
          descricao: params.descricao,
          detalhes: params.detalhes,
        });

      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["action-logs"] });
    },
    onError: (error: any) => {
      console.error("Erro ao registrar ação:", error);
      // Silenciosamente falhar para não interromper a UX
    },
  });
}