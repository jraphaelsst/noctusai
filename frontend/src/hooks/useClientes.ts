import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { Cliente, EtapaFunil } from '@/types/clientes';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

interface FiltrosClientes {
  busca?: string;
  responsavelId?: string;
  origem?: string;
  incluirArquivados?: boolean;
  dataInicio?: Date;
  dataFim?: Date;
  etapa?: EtapaFunil;
}

export function useClientes(filtros?: FiltrosClientes) {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['clientes', filtros, user?.id],
    staleTime: 1000 * 60 * 3, // 3 minutos para dados de clientes
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('clientes')
        .select(`
          *,
          usuario:profiles!clientes_usuario_id_fkey(id, nome, email)
        `)
        .order('kanban_pos', { ascending: true });

      // Aplicar filtros
      if (!isAdmin && filtros?.responsavelId !== 'todos') {
        query = query.eq('usuario_id', user.id);
      } else if (filtros?.responsavelId && filtros.responsavelId !== 'todos') {
        query = query.eq('usuario_id', filtros.responsavelId);
      }

      if (!filtros?.incluirArquivados) {
        query = query.eq('arquivado', false);
      }

      if (filtros?.etapa) {
        query = query.eq('etapa_atual', filtros.etapa);
      }

      if (filtros?.origem && filtros.origem !== 'todas') {
        query = query.eq('origem', filtros.origem);
      }

      if (filtros?.dataInicio) {
        query = query.gte('created_at', filtros.dataInicio.toISOString());
      }

      if (filtros?.dataFim) {
        query = query.lte('created_at', filtros.dataFim.toISOString());
      }

      const { data, error } = await query;

      if (error) throw error;

      let clientes = data as Cliente[];

      // Filtro de busca no cliente
      if (filtros?.busca) {
        const busca = filtros.busca.toLowerCase();
        clientes = clientes.filter(
          (c) =>
            c.nome.toLowerCase().includes(busca) ||
            c.email?.toLowerCase().includes(busca) ||
            c.telefone?.includes(busca)
        );
      }

      return clientes;
    },
    enabled: !!user,
  });
}

export function useCliente(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['cliente', id],
    staleTime: 1000 * 60 * 5, // 5 minutos para cliente individual
    queryFn: async () => {
      if (!id) return null;

      const { data, error } = await supabase
        .from('clientes')
        .select(`
          *,
          usuario:profiles!clientes_usuario_id_fkey(id, nome, email)
        `)
        .eq('id', id)
        .single();

      if (error) throw error;
      return data as Cliente;
    },
    enabled: !!user && !!id,
  });
}

interface CreateClienteData {
  nome: string;
  email?: string;
  telefone?: string;
  origem?: string;
  interesse?: string;
  observacoes?: string;
  probabilidade?: number;
  valor_estimado?: number;
}

export function useCreateCliente() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  return useMutation({
    mutationFn: async (data: CreateClienteData) => {
      if (!user) throw new Error('Usuário não autenticado');

      // Buscar maior kanban_pos da etapa qualificacao
      const { data: ultimoCliente } = await supabase
        .from('clientes')
        .select('kanban_pos')
        .eq('etapa_atual', 'qualificacao')
        .order('kanban_pos', { ascending: false })
        .limit(1)
        .maybeSingle();

      const novo_pos = ultimoCliente ? ultimoCliente.kanban_pos - 10 : 0;

      const { data: cliente, error } = await supabase
        .from('clientes')
        .insert({
          ...data,
          usuario_id: user.id,
          etapa_atual: 'qualificacao',
          kanban_pos: novo_pos,
        })
        .select(`
          *,
          usuario:profiles!clientes_usuario_id_fkey(id, nome, email)
        `)
        .single();

      if (error) throw error;

      // Registrar ação
      supabase.from("user_actions_log").insert({
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'cliente',
        entidade_id: cliente.id,
        descricao: `Criou cliente ${data.nome}`,
        detalhes: { nome: data.nome, etapa: 'qualificacao' }
      }).then();

      return cliente as Cliente;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success('Cliente criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar cliente', {
        description: error.message,
      });
    },
  });
}

interface UpdateClienteData {
  id: string;
  nome?: string;
  email?: string;
  telefone?: string;
  origem?: string;
  interesse?: string;
  observacoes?: string;
  probabilidade?: number;
  valor_estimado?: number;
}

export function useUpdateCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: UpdateClienteData) => {
      // Buscar nome do cliente antes de atualizar
      const { data: clienteAntes } = await supabase
        .from('clientes')
        .select('nome')
        .eq('id', id)
        .single();

      const { data: cliente, error } = await supabase
        .from('clientes')
        .update(data)
        .eq('id', id)
        .select(`
          *,
          usuario:profiles!clientes_usuario_id_fkey(id, nome, email)
        `)
        .single();

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: 'editar',
          tipo_entidade: 'cliente',
          entidade_id: id,
          descricao: `Editou cliente ${clienteAntes?.nome || cliente.nome}`,
          detalhes: data
        }).then();
      }

      return cliente as Cliente;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['cliente'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success('Cliente atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar cliente', {
        description: error.message,
      });
    },
  });
}

export function useToggleArquivarCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { data: clienteAtual } = await supabase
        .from('clientes')
        .select('arquivado, nome')
        .eq('id', id)
        .single();

      if (!clienteAtual) throw new Error('Cliente não encontrado');

      const { data, error } = await supabase
        .from('clientes')
        .update({ arquivado: !clienteAtual.arquivado })
        .eq('id', id)
        .select()
        .single();

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: data.arquivado ? 'arquivar' : 'desarquivar',
          tipo_entidade: 'cliente',
          entidade_id: id,
          descricao: `${data.arquivado ? 'Arquivou' : 'Desarquivou'} cliente ${clienteAtual.nome}`,
        }).then();
      }

      return data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['cliente'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success(
        data.arquivado ? 'Cliente arquivado' : 'Cliente desarquivado'
      );
    },
    onError: (error: Error) => {
      toast.error('Erro ao arquivar cliente', {
        description: error.message,
      });
    },
  });
}

export function useDeleteCliente() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      // Buscar dados do cliente antes de excluir
      const { data: cliente } = await supabase
        .from('clientes')
        .select('nome')
        .eq('id', id)
        .single();

      const { error } = await supabase
        .from('clientes')
        .delete()
        .eq('id', id);

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user && cliente) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: 'excluir',
          tipo_entidade: 'cliente',
          entidade_id: id,
          descricao: `Excluiu cliente ${cliente.nome}`,
        }).then();
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      toast.success('Cliente excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir cliente', {
        description: error.message,
      });
    },
  });
}
