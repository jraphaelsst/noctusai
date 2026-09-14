/**
 * Matrícula extraction hooks — `/api/matriculas/*` ("Extrator de Matrículas").
 *
 * Ported from `products/erp-imobiliario/frontend/src/hooks/useMatriculas.ts`
 * (ERP is being retired). Behaviour is verbatim — same query keys, same
 * staleTimes, same polling contract, same pt-BR toasts. Two adaptations,
 * both mandatory in this product:
 *
 *   1. UPLOAD goes through the seed `api.upload()` seam instead of ERP's
 *      hand-rolled `fetch(BACKEND_URL + …)` + `supabase.auth.getSession()`
 *      block. ERP's `VITE_BACKEND_API_URL || 'http://localhost:8001'`
 *      default is ERP's OWN backend port — in social-wiring the base URL is
 *      runtime-resolved (single-container same-origin, dev port 8011) by the
 *      seed client, so hard-coding it here would talk to the wrong backend.
 *      `api.upload` exists precisely for multipart (`post` would silently
 *      send an empty JSON body for a FormData argument).
 *   2. Upload errors surface the backend's `detail` sentence WITHOUT the
 *      `[422] ` status prefix `ApiError` prepends — the 422 for a missing
 *      API key is a sentence Marina is meant to read and act on (it points
 *      at Configurações → Chaves de API).
 *
 * Polling contract (do not weaken): `refetchInterval` returns 3000 ONLY
 * while a row is `pendente`/`processando`, else `false`. That is what makes
 * the status column live without a websocket.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';

export interface MatriculaExtracao {
  id: string;
  org_id?: string;
  user_id?: string;
  nome_arquivo: string;
  tamanho_bytes: number;
  num_paginas: number | null;
  texto_extraido: string | null;
  status: 'pendente' | 'processando' | 'concluida' | 'erro';
  erro_mensagem: string | null;
  /** The imóvel this transcription is filed under, uppercased — `null` for
   *  the legacy unlinked upload shape. */
  codigo: string | null;
  /** The imóvel document store row this extraction was transcribed FROM,
   *  when it came from `POST /extracoes/de-documento` rather than a direct
   *  upload. */
  imovel_documento_id: string | null;
  created_at: string;
}

/** True while the backend still owes us text for this extraction. */
function isInFlight(status: MatriculaExtracao['status']): boolean {
  return status === 'pendente' || status === 'processando';
}

/**
 * `ApiError.message` keeps the historical `[<status>] <message>` shape. For a
 * toast the prefix is noise — the backend sentence is the actionable part.
 * Mirrors the same strip in `components/portal-roi/CampanhaManagerDialog.tsx`.
 * Exported — `useMatriculaEstrutura.ts` reuses it for its own mutations
 * rather than re-implementing the same regex a third time.
 */
export function readableError(error: Error): string {
  return error.message.replace(/^\[\d+\]\s*/, '').trim();
}

export interface MatriculaExtracoesFiltro {
  /** Narrow to one imóvel's matrículas — uppercased server-side. */
  codigo?: string;
  /** Substring match on `nome_arquivo`. */
  busca?: string;
}

export function useMatriculaExtracoes(filtro?: MatriculaExtracoesFiltro) {
  const { user } = useAuthStore();
  const codigo = filtro?.codigo;
  const busca = filtro?.busca;

  return useQuery({
    // `codigo`/`busca` join the key so switching either refetches instead of
    // reusing a stale page cached under the unfiltered key.
    queryKey: ['matricula-extracoes', codigo ?? null, busca ?? null],
    queryFn: async () => {
      const result = await api.get('/api/matriculas/extracoes', { codigo, busca });
      return (result.data || []) as MatriculaExtracao[];
    },
    enabled: !!user,
    staleTime: 30 * 1000,
    refetchInterval: (query) => {
      const data = query.state.data as MatriculaExtracao[] | undefined;
      if (data?.some((e) => isInFlight(e.status))) {
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
      if (data && isInFlight(data.status)) {
        return 3000;
      }
      return false;
    },
  });
}

export interface UploadMatriculaInput {
  file: File;
  /** When set, the PDF is KEPT as that imóvel's `matricula` document and the
   *  extraction is linked to it — the backend's `codigo` form field. */
  codigo?: string;
}

export function useUploadMatricula() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: File | UploadMatriculaInput): Promise<MatriculaExtracao> => {
      // Accepts a bare `File` too — every existing call site (`Matriculas.tsx`
      // pre-this-feature) passes one, and widening the signature must not
      // break them.
      const { file, codigo } = input instanceof File ? { file: input, codigo: undefined } : input;
      const formData = new FormData();
      formData.append('file', file);
      if (codigo) formData.append('codigo', codigo);
      const result = await api.upload('/api/matriculas/extrair', formData);
      return result.data as MatriculaExtracao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      toast.success('PDF enviado! Extraindo texto...');
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar PDF', { description: readableError(error) });
    },
  });
}

/**
 * Transcribe a matrícula PDF the imóvel ALREADY holds (no re-upload) —
 * `POST /api/matriculas/extracoes/de-documento`. 409 when that document
 * already carries a non-`erro` extraction; the caller surfaces the server's
 * own message rather than a generic one, since it names which extraction.
 */
export function useCriarExtracaoDeDocumento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      codigo: string;
      imovelDocumentoId: string;
    }): Promise<MatriculaExtracao> => {
      const result = await api.post('/api/matriculas/extracoes/de-documento', {
        codigo: input.codigo,
        imovel_documento_id: input.imovelDocumentoId,
      });
      return result.data as MatriculaExtracao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      toast.success('Transcrição iniciada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao transcrever', { description: readableError(error) });
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
      toast.error('Erro ao excluir', { description: readableError(error) });
    },
  });
}
