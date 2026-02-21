import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Meta, NovaMetaForm } from "@/types";
import { toast } from "@/hooks/use-toast";
import { useRegisterAction } from "@/hooks/useActionLog";
import { getDisplayCategoria } from "@/lib/categorias";

// Helper para obter data atual de São Paulo do banco
async function getDataHojeSP(): Promise<string> {
  const { data, error } = await supabase.rpc('current_date_sao_paulo');
  if (error) throw error;
  return data;
}

export function useMetas(corretorId?: string) {
  return useQuery({
    queryKey: ["metas", corretorId],
    staleTime: 1000 * 60 * 2, // 2 minutos para dados de metas
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      
      if (!user) {
        throw new Error("Usuário não autenticado");
      }

      // Verificar o role do usuário - buscar todas as roles
      const { data: rolesData } = await supabase
        .from('user_roles')
        .select('role')
        .eq('user_id', user.id);

      // Verificar se o usuário tem role de admin
      const canViewAll = rolesData?.some(r => r.role === 'admin') || false;

      // Iniciar query base com join para pegar dados do usuário
      let query = supabase
        .from("metas")
        .select("*")
        .order("created_at", { ascending: false });

      // Se não puder ver tudo, filtrar apenas metas do próprio usuário
      if (!canViewAll && !corretorId) {
        query = query.eq("usuario_id", user.id);
      }

      // Se um usuário específico foi fornecido, filtrar por ele
      if (corretorId) {
        query = query.eq("usuario_id", corretorId);
      }

      const { data, error } = await query;

      if (error) throw error;
      return data as Meta[];
    },
  });
}

export function useCreateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (novaMeta: NovaMetaForm) => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error("Usuário não autenticado");

      // Se data_prazo não foi fornecida, ela já deve ter sido calculada no frontend
      const dataPrazo = novaMeta.data_prazo || await getDataHojeSP();

      // CRIAÇÃO MANUAL: Sempre criar nova meta, mesmo que já exista outra do mesmo tipo/categoria/período
      const { data: novaMeta_inserted, error: insertError } = await supabase
        .from("metas")
        .insert({
          usuario_id: novaMeta.usuario_id,
          tipo: novaMeta.tipo,
          categoria: novaMeta.categoria,
          categoria_custom: novaMeta.categoria_custom,
          meta_pretendida: novaMeta.meta_pretendida,
          meta_realizada: 0,
          data_prazo: dataPrazo,
          status: 'aberta',
          detalhes: novaMeta.detalhes,
          nome: novaMeta.nome,
          criada_manualmente: true
        })
        .select()
        .single();

      if (insertError) throw insertError;

      // Registrar ação (não bloqueia se falhar)
      supabase.from("user_actions_log").insert({
        usuario_id: novaMeta.usuario_id,
        tipo_acao: 'criar',
        tipo_entidade: 'meta',
        entidade_id: novaMeta_inserted.id,
        descricao: `Criou meta ${novaMeta.tipo} de ${getDisplayCategoria({ categoria: novaMeta.categoria, categoria_custom: novaMeta.categoria_custom })}`,
        detalhes: { tipo: novaMeta.tipo, categoria: novaMeta.categoria }
      }).then();

      return novaMeta_inserted;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast({
        title: "Sucesso!",
        description: "Meta criada com sucesso.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao cadastrar meta.",
        variant: "destructive",
      });
    },
  });
}

export function useUpdateMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...updates }: Partial<Meta> & { id: string }) => {
      // Verificar se é uma meta agregada
      const { data: meta } = await supabase
        .from("metas")
        .select("tipo, categoria, categoria_custom")
        .eq("id", id)
        .single();

      if (meta && ['semanal', 'mensal', 'anual'].includes(meta.tipo)) {
        throw new Error("Metas agregadas são read-only. Edite as metas diárias.");
      }

      // Filtrar 'vence_amanha' do status, pois é apenas para display
      // e criar um objeto compatível com o tipo do Supabase
      const { status, ...otherUpdates } = updates;
      const dbUpdates: any = { ...otherUpdates };
      
      // Se há status e não é 'vence_amanha', adicionar ao update
      if (status && status !== 'vence_amanha') {
        dbUpdates.status = status;
      } else if (status === 'vence_amanha') {
        dbUpdates.status = 'no_prazo';
      }

      const { data, error } = await supabase
        .from("metas")
        .update(dbUpdates)
        .eq("id", id)
        .select()
        .single();

      if (error) throw error;

      // Registrar ação (não bloqueia se falhar)
      const isConclusion = updates.status === 'concluida';
      supabase.from("user_actions_log").insert({
        usuario_id: data.usuario_id,
        tipo_acao: isConclusion ? 'concluir' : 'editar',
        tipo_entidade: 'meta',
        entidade_id: id,
        descricao: isConclusion 
          ? `Concluiu meta de ${getDisplayCategoria(meta)}`
          : `Editou meta de ${getDisplayCategoria(meta)}`,
        detalhes: updates
      }).then();

      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast({
        title: "Sucesso!",
        description: "Meta atualizada com sucesso.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao atualizar meta.",
        variant: "destructive",
      });
    },
  });
}

export function useDeleteMeta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      console.log("useMetas: Executando exclusão para ID:", id);
      
      // Buscar a meta para obter informações (para mensagens de erro mais claras)
      const { data: meta, error: fetchError } = await supabase
        .from("metas")
        .select("id, tipo, status, usuario_id, categoria, categoria_custom")
        .eq("id", id)
        .single();
      
      if (fetchError) {
        console.error("useMetas: Erro ao buscar meta:", fetchError);
        throw new Error(`Meta não encontrada: ${fetchError.message}`);
      }
      
      if (!meta) {
        throw new Error("Meta não encontrada");
      }
      
      console.log("useMetas: Meta encontrada:", meta);
      
      // Executar a exclusão (o RLS cuidará das permissões)
      const { error } = await supabase
        .from("metas")
        .delete()
        .eq("id", id);

      if (error) {
        console.error("useMetas: Erro na exclusão:", error);
        
        // Fornecer mensagens de erro mais claras baseadas no tipo e status
        if (error.code === '42501') { // Código de erro para violação de RLS
          if (meta.status === 'concluida') {
            throw new Error("Apenas administradores podem excluir metas concluídas.");
          }
          if (['semanal', 'mensal', 'anual'].includes(meta.tipo)) {
            throw new Error("Apenas administradores podem excluir metas agregadas (semanais, mensais, anuais).");
          }
          throw new Error("Você não tem permissão para excluir esta meta.");
        }
        
        throw new Error(`Erro ao excluir meta: ${error.message}`);
      }
      
      console.log("useMetas: Meta excluída com sucesso:", id);

      // Registrar ação (não bloqueia se falhar)
      supabase.from("user_actions_log").insert({
        usuario_id: meta.usuario_id,
        tipo_acao: 'excluir',
        tipo_entidade: 'meta',
        entidade_id: id,
        descricao: `Excluiu meta ${meta.tipo} de ${getDisplayCategoria(meta)}`,
        detalhes: { tipo: meta.tipo, categoria: meta.categoria }
      }).then(({ error }) => {
        if (error) {
          console.error("useMetas: Erro ao registrar log de ação:", error);
        } else {
          console.log("useMetas: Log de ação registrado com sucesso");
        }
      });

      return id;
    },
    onSuccess: (id) => {
      console.log("useMetas: onSuccess chamado para ID:", id);
      // Invalidar e refazer queries relacionadas a metas
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      queryClient.refetchQueries({ queryKey: ["metas"], type: 'active' });
      
      // Atualização otimista: remove a meta da cache imediatamente
      queryClient.setQueriesData(
        { queryKey: ["metas"] },
        (oldData: Meta[] | undefined) => {
          if (!oldData) return oldData;
          return oldData.filter(meta => meta.id !== id);
        }
      );
    },
    onError: (error: any) => {
      console.error("useMetas: onError chamado:", error);
      throw error;
    },
  });
}
