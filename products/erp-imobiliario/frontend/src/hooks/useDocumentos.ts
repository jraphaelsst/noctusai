import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import {
  Documento,
  DocumentoCreateData,
  DocumentTemplate,
  TemplateCreateData,
  GenerateDocumentData,
} from '@/types/documentos';

interface FiltrosDocumentos {
  tipo?: string;
  imovel_id?: string;
  cliente_id?: string;
  proposta_id?: string;
  page?: number;
  page_size?: number;
}

export function useDocumentos(filtros?: FiltrosDocumentos) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['documentos', filtros],
    queryFn: async () => {
      const result = await api.get('/api/documentos', {
        tipo: filtros?.tipo,
        imovel_id: filtros?.imovel_id,
        cliente_id: filtros?.cliente_id,
        proposta_id: filtros?.proposta_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Documento[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useDocumento(id?: string) {
  return useQuery({
    queryKey: ['documento', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/documentos/${id}`);
      return result.data as Documento;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useTemplates(filtros?: { tipo?: string; ativo?: boolean }) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['document-templates', filtros],
    queryFn: async () => {
      const result = await api.get('/api/documentos/templates', {
        tipo: filtros?.tipo,
        ativo: filtros?.ativo ?? true,
      });
      return {
        data: (result.data || []) as DocumentTemplate[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useCreateDocumento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: DocumentoCreateData) => {
      const result = await api.post('/api/documentos', data);
      return result.data as Documento;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documentos'] });
      toast.success('Documento criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar documento', { description: error.message });
    },
  });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: TemplateCreateData) => {
      const result = await api.post('/api/documentos/templates', data);
      return result.data as DocumentTemplate;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-templates'] });
      toast.success('Template criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar template', { description: error.message });
    },
  });
}

export function useGenerateDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: GenerateDocumentData) => {
      const result = await api.post('/api/documentos/generate', data);
      return result.data as Documento;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documentos'] });
      toast.success('Documento gerado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao gerar documento', { description: error.message });
    },
  });
}

export function useDeleteDocumento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/documentos/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documentos'] });
      toast.success('Documento excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir documento', { description: error.message });
    },
  });
}

/**
 * Toggle the LGPD per-document portal-sharing flag.
 *
 * Calls `PATCH /api/documentos/{id}/compartilhamento` with `{ shared }` and
 * invalidates the docs query on success. Backend (`toggle_compartilhamento`)
 * audit-logs the change and role-gates it; the public client portal only
 * surfaces docs with `compartilhado_portal = true`.
 */
export function useToggleCompartilhamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, shared }: { id: string; shared: boolean }) => {
      const result = await api.patch(`/api/documentos/${id}/compartilhamento`, {
        shared,
      });
      // Backend returns the updated row via success_response(row); never
      // returns undefined — mutationFn yields the typed Documento.
      return result.data as Documento;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['documentos'] });
      toast.success(
        variables.shared
          ? 'Documento compartilhado com o portal do cliente'
          : 'Documento removido do portal do cliente',
      );
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar compartilhamento', {
        description: error.message,
      });
    },
  });
}
