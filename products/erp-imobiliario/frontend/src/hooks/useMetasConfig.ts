import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { TipoMeta, CategoriaMeta } from "@/types";
import { toast } from "@/hooks/use-toast";

// Helper para obter data atual de São Paulo do banco
async function getDataHojeSP(): Promise<string> {
  const { data, error } = await supabase.rpc('current_date_sao_paulo');
  if (error) throw error;
  return data;
}

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
  return useQuery({
    queryKey: ["metas-config"],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      
      if (!user) {
        throw new Error("Usuário não autenticado");
      }

      const { data, error } = await supabase
        .from("metas_config")
        .select("*")
        .eq("usuario_id", user.id)
        .order("tipo", { ascending: true });

      if (error) throw error;
      return data as MetaConfig[];
    },
  });
}

export function useUpsertMetaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (config: MetaConfigForm) => {
      console.log('[useUpsertMetaConfig] Iniciando mutationFn com config:', config);
      
      const { data: { user } } = await supabase.auth.getUser();
      
      if (!user) {
        throw new Error("Usuário não autenticado");
      }

      console.log('[useUpsertMetaConfig] Usuário autenticado:', user.id);

      // Verificar se já existe meta para esta categoria
      const hoje = await getDataHojeSP();
      const { data: metasExistentes } = await supabase
        .from("metas")
        .select("id")
        .eq("usuario_id", user.id)
        .eq("categoria", config.categoria)
        .eq("tipo", "mensal")
        .gte("data_prazo", hoje)
        .limit(1);

      const metasJaExistem = metasExistentes && metasExistentes.length > 0;
      console.log('[useUpsertMetaConfig] Metas já existem?', metasJaExistem);

      const { data, error } = await supabase
        .from("metas_config")
        .upsert({
          usuario_id: user.id,
          tipo: 'mensal', // Sempre mensal
          ...config,
          ativo: config.ativo ?? true,
        }, {
          onConflict: "usuario_id,tipo,categoria"
        })
        .select()
        .single();

      if (error) {
        console.error('[useUpsertMetaConfig] Erro ao fazer upsert:', error);
        throw error;
      }

      console.log('[useUpsertMetaConfig] Config salva com sucesso:', data);

      // Config mensal ativa - criar metas automaticamente APENAS se não existirem
      if (config.ativo ?? true) {
        try {
          console.log('[useUpsertMetaConfig] Processando metas para categoria:', config.categoria);
          
          // Para cada tipo de meta, verificar se existe, se não criar
          for (const tipo of ['diaria', 'semanal', 'mensal', 'anual'] as const) {
            // Buscar meta existente usando ensure_scaffold_meta
            const { data: metaIdExistente } = await supabase.rpc('ensure_scaffold_meta', {
              p_usuario_id: user.id,
              p_tipo: tipo,
              p_categoria: config.categoria,
              p_data_ref: hoje
            });
            
            // Se não existe, criar nova meta
            if (!metaIdExistente) {
              console.log(`[useUpsertMetaConfig] Criando nova meta ${tipo}...`);
              
              // Calcular meta_pretendida PROPORCIONAL aos dias restantes do período
              const { data: metaPretendida, error: calcError } = await supabase.rpc('calcular_meta_proporcional', {
                p_meta_mensal: config.meta_pretendida,
                p_tipo: tipo,
                p_data_ref: hoje
              });
              
              if (calcError) {
                console.error(`[useUpsertMetaConfig] Erro ao calcular meta proporcional:`, calcError);
                throw calcError;
              }
              
              // Obter data_prazo correta para o tipo
              const { data: dataPrazo } = await supabase.rpc('period_end_date', {
                tipo_meta: tipo,
                data_ref: hoje
              });
              
              console.log(`[useUpsertMetaConfig] Meta ${tipo} calculada: ${metaPretendida} (proporcional aos dias restantes)`);
              
              // Criar meta nova
              const { error: insertError } = await supabase
                .from("metas")
                .insert({
                  usuario_id: user.id,
                  tipo: tipo,
                  categoria: config.categoria,
                  categoria_custom: config.categoria_custom,
                  meta_pretendida: metaPretendida,
                  meta_realizada: 0,
                  data_prazo: dataPrazo,
                  status: 'no_prazo',
                  criada_manualmente: false
                });
              
              if (insertError) {
                console.error(`[useUpsertMetaConfig] Erro ao criar meta ${tipo}:`, insertError);
                throw insertError;
              }
              
              console.log(`[useUpsertMetaConfig] Meta ${tipo} criada com sucesso`);
            } else {
              console.log(`[useUpsertMetaConfig] Meta ${tipo} já existe, não criando nova`);
            }
          }
          
          console.log('[useUpsertMetaConfig] Metas processadas com sucesso para:', config.categoria);
        } catch (scaffoldError) {
          console.error('[useUpsertMetaConfig] Erro ao processar metas:', scaffoldError);
          throw new Error(`Erro ao processar metas: ${scaffoldError.message}`);
        }
      }

      // Registrar ação (não bloqueia se falhar)
      supabase.from("user_actions_log").insert({
        usuario_id: user.id,
        tipo_acao: 'editar',
        tipo_entidade: 'config_meta',
        descricao: `${config.ativo ?? true ? 'Ativou' : 'Desativou'} configuração de meta para ${config.categoria}`,
        detalhes: { categoria: config.categoria, meta_pretendida: config.meta_pretendida, ativo: config.ativo ?? true }
      }).then();

      return { data, metasJaExistem };
    },
    onSuccess: (result) => {
      console.log('[useUpsertMetaConfig] onSuccess chamado:', result);
      queryClient.invalidateQueries({ queryKey: ["metas-config"] });
      queryClient.invalidateQueries({ queryKey: ["metas"] });
      toast({
        title: "Sucesso!",
        description: result.metasJaExistem 
          ? "Configurações atualizadas com sucesso."
          : "Configurações salvas e metas criadas com sucesso.",
      });
    },
    onError: (error: any) => {
      console.error('[useUpsertMetaConfig] onError chamado:', error);
      toast({
        title: "Erro",
        description: error.message || "Erro ao salvar configuração.",
        variant: "destructive",
      });
    },
  });
}

export function useDeleteMetaConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase
        .from("metas_config")
        .delete()
        .eq("id", id);

      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["metas-config"] });
      toast({
        title: "Sucesso!",
        description: "Configuração removida com sucesso.",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Erro",
        description: error.message || "Erro ao remover configuração.",
        variant: "destructive",
      });
    },
  });
}
