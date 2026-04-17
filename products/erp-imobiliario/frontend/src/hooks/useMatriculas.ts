import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore, supabase } from '@noctusai/seed/infra';

export interface MatriculaExtracao {
  id: string;
  nome_arquivo: string;
  tamanho_bytes: number;
  num_paginas: number | null;
  texto_extraido: string | null;
  status: 'pendente' | 'processando' | 'concluida' | 'erro';
  erro_mensagem: string | null;
  created_at: string;
}

const BACKEND_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8001';

async function getAuthToken(): Promise<string> {
  let { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) {
    // Try refreshing before giving up
    const { data: refreshed } = await supabase.auth.refreshSession();
    session = refreshed.session;
  }
  if (!session?.access_token) throw new Error('Nao autenticado');
  return session.access_token;
}

export function useMatriculaExtracoes() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['matricula-extracoes'],
    queryFn: async () => {
      const result = await api.get('/api/matriculas/extracoes');
      return (result.data || []) as MatriculaExtracao[];
    },
    enabled: !!user,
    staleTime: 30 * 1000,
    refetchInterval: (query) => {
      const data = query.state.data as MatriculaExtracao[] | undefined;
      if (data?.some((e) => e.status === 'pendente' || e.status === 'processando')) {
        return 3000;
      }
      return false;
    },
  });
}

export function useMatriculaExtracao(id?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['matricula-extracao', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/matriculas/extracoes/${id}`);
      return result.data as MatriculaExtracao;
    },
    enabled: !!user && !!id,
    staleTime: 10 * 1000,
    refetchInterval: (query) => {
      const data = query.state.data as MatriculaExtracao | null | undefined;
      if (data && (data.status === 'pendente' || data.status === 'processando')) {
        return 3000;
      }
      return false;
    },
  });
}

export function useUploadMatricula() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (file: File): Promise<MatriculaExtracao> => {
      const token = await getAuthToken();
      const formData = new FormData();
      formData.append('file', file);

      const resp = await fetch(`${BACKEND_URL}/api/matriculas/extrair`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        throw new Error(body?.detail || `Erro ${resp.status}`);
      }

      const json = await resp.json();
      return json.data as MatriculaExtracao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      toast.success('PDF enviado! Extraindo texto...');
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar PDF', { description: error.message });
    },
  });
}

export function useDeleteExtracao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/matriculas/extracoes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      queryClient.invalidateQueries({ queryKey: ['matricula-extracao'] });
      toast.success('Extração excluída!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir', { description: error.message });
    },
  });
}
