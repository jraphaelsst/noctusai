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

/**
 * `noctusai_lib.integrations.documents.formatting.FormatRange` on the wire —
 * offsets `[start, end)` into the owning plain text. ABNT formatting project
 * (`projects/abnt-formatting-CONTRACT.md` § 1); shared shape for BOTH
 * matrícula extractions and certidão transcriptions, so `useCertidoes.ts`
 * imports this type rather than redeclaring it.
 */
export interface FormatRange {
  start: number;
  end: number;
  bold: boolean;
  underline: boolean;
}

export interface MatriculaExtracao {
  id: string;
  org_id?: string;
  user_id?: string;
  nome_arquivo: string;
  tamanho_bytes: number;
  num_paginas: number | null;
  texto_extraido: string | null;
  /** `render_word_html(FormattedDocument)` — `null` when there is no text
   *  yet. The "Copiar" action's rich-text source (`copyRichText`'s `html`
   *  argument); ABNT formatting project § 4. */
  texto_html: string | null;
  /** Bold/underline ranges into `texto_extraido`. Not consumed directly by
   *  this page today (the backend already bakes them into `texto_html`) —
   *  carried through so the wire type matches the contract. */
  formatacao: FormatRange[];
  status: 'pendente' | 'processando' | 'concluida' | 'erro';
  erro_mensagem: string | null;
  /** The imóvel this transcription is filed under, uppercased — `null` for
   *  the legacy unlinked upload shape. */
  codigo: string | null;
  /** The imóvel document store row this extraction was transcribed FROM,
   *  when it came from `POST /extracoes/de-documento` rather than a direct
   *  upload. */
  imovel_documento_id: string | null;
  /** The standalone retained-PDF row (migration 135) this extraction was
   *  transcribed from, for an upload made with no `codigo`. Mutually
   *  exclusive with `imovel_documento_id` — never both set. */
  arquivo_origem_id: string | null;
  /** Set once this extraction has been RE-transcribed — points at the new
   *  row. `null` means this is the current/live version. A superseded row
   *  is kept (never deleted) but should not offer "Retranscrever" again. */
  substituida_por: string | null;
  /** True when `texto_extraido` still carries a literal `**`/`<u>` marker
   *  instead of parsed bold/underline — a pre-migration-135 transcription
   *  (no source to fix it from) or a malformed vision reply. The text must
   *  not be quoted into a contract as-is; the backend's contract generator
   *  refuses it independently of this flag, but the operator should not
   *  wait for that refusal to find out. */
  possui_marcacao_bruta: boolean;
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
  /**
   * Only transcriptions with NO `codigo` — a transcription uploaded before
   * an imóvel had a registry identity yet, or standalone (migration 135).
   * `MatriculaAtosSelector`'s "Matrículas sem imóvel vinculado" section reads
   * this so an operator can attach an existing unlinked transcription to a
   * negociação's imóvel instead of it being permanently unreachable from any
   * codigo-scoped search. Mutually exclusive with `codigo` in practice — the
   * backend param name (`sem_imovel`) mirrors the boolean intent, ASSUMED
   * from the brief (no existing param to read off the primary checkout's
   * `listar_extracoes` at the time this shipped — confirm against the live
   * router if this 422s).
   */
  semImovel?: boolean;
}

export function useMatriculaExtracoes(filtro?: MatriculaExtracoesFiltro) {
  const { user } = useAuthStore();
  const codigo = filtro?.codigo;
  const busca = filtro?.busca;
  const semImovel = filtro?.semImovel;

  return useQuery({
    // `codigo`/`busca`/`semImovel` join the key so switching any of them
    // refetches instead of reusing a stale page cached under a different key.
    queryKey: ['matricula-extracoes', codigo ?? null, busca ?? null, semImovel ?? null],
    queryFn: async () => {
      const result = await api.get('/api/matriculas/extracoes', {
        codigo,
        busca,
        ...(semImovel ? { sem_imovel: true } : {}),
      });
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

/**
 * A matrícula transcribed by TYPING/PASTING its text — no PDF, no vision AI
 * (migration 149). `POST /api/matriculas/extracoes/manual`. Lands
 * `status='concluida'` SYNCHRONOUSLY (unlike every upload path above): there
 * is no I/O-bound step, so the returned row is already the finished one.
 */
export function useCriarExtracaoManual() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: { codigo: string; texto: string }): Promise<MatriculaExtracao> => {
      const result = await api.post('/api/matriculas/extracoes/manual', {
        codigo: input.codigo,
        texto: input.texto,
      });
      return result.data as MatriculaExtracao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      toast.success('Transcrição manual criada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar transcrição manual', { description: readableError(error) });
    },
  });
}

/**
 * Link an EXISTING, previously-unlinked transcription to an imóvel —
 * `PUT /api/matriculas/extracoes/{id}/imovel` (migration 149's manual-imóvel
 * paths, contract-gate follow-up). The counterpart to `useUploadMatricula`'s
 * `codigo` field for a transcription that predates the imóvel having one, or
 * that was uploaded standalone — without this there was no way to attach it
 * after the fact, so it sat in "Matrículas sem imóvel vinculado" forever.
 *
 * 422 when `codigo` has no registry identity; 409 when the extraction is
 * already linked to a DIFFERENT codigo and `substituir` was not set — both
 * surface the server's own sentence, same as every other mutation here.
 */
export function useVincularExtracaoImovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      extracaoId: string;
      codigo: string;
      substituir?: boolean;
    }): Promise<MatriculaExtracao> => {
      const result = await api.put(`/api/matriculas/extracoes/${input.extracaoId}/imovel`, {
        codigo: input.codigo,
        ...(input.substituir ? { substituir: true } : {}),
      });
      return result.data as MatriculaExtracao;
    },
    onSuccess: (data) => {
      // Every list this could now appear in/disappear from: the codigo-scoped
      // list it just joined, the unlinked list it just left, and its own
      // single-extraction cache.
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      queryClient.invalidateQueries({ queryKey: ['matricula-extracao', data.id] });
      toast.success('Matrícula vinculada ao imóvel!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao vincular matrícula', { description: readableError(error) });
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

/**
 * Re-run transcription of a CONCLUDED extraction from its retained source
 * (migration 135) — `POST /extracoes/{id}/retranscrever`. SUPERSEDES: the
 * backend inserts a new row and marks the old one `substituida_por`; both
 * lists refetch so the history table shows the new row and the old one's
 * updated state in the same pass. 409 when there is nothing retained to
 * re-run from (a pre-135 extraction) — the server's own sentence names that.
 */
export function useRetranscreverExtracao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string): Promise<MatriculaExtracao> => {
      const result = await api.post(`/api/matriculas/extracoes/${id}/retranscrever`);
      return result.data as MatriculaExtracao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matricula-extracoes'] });
      queryClient.invalidateQueries({ queryKey: ['matricula-extracao'] });
      toast.success('Retranscrição iniciada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao retranscrever', { description: readableError(error) });
    },
  });
}

/**
 * A short-TTL signed URL for the SOURCE PDF an extraction was transcribed
 * from — `GET /extracoes/{id}/arquivo-original`. Minted fresh per request
 * (never cached across a long session — `expires_at` is short), which is
 * why this is a mutation (fire-on-click) rather than a query. 409 when the
 * extraction kept no source (a pre-135 row).
 */
export function useArquivoOriginalExtracao() {
  return useMutation({
    mutationFn: async (id: string): Promise<{ url: string; expires_at: string }> => {
      const result = await api.get(`/api/matriculas/extracoes/${id}/arquivo-original`);
      return result.data as { url: string; expires_at: string };
    },
    onError: (error: Error) => {
      toast.error('Erro ao abrir o documento original', {
        description: readableError(error),
      });
    },
  });
}
