/**
 * Chat (P2) over `/api/media-creation/chat` (contract §4.6 #41–48) plus the two
 * hooks the chat needs from other areas: save-a-headline (`POST /headlines`,
 * §4.4 #29) and mic dictation through the shared `POST /api/transcricoes`
 * submit (transcription-contract §4, `contexto_tipo=chat_ditado`).
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * never `isLoading`. Mutations invalidate the `["sw","geracao"]` family.
 *
 * Streaming (#45) is a `fetch` + the seed `readSseStream`; frames:
 * `meta` -> `delta`... -> (`truncated`) -> `done` | `error`. Pre-stream refusals
 * (409 / 429 / 503) are plain HTTP and surface as a pt-BR message.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { readSseStream } from "@noctusai/lib";
import { api, getAuthToken } from "@noctusai/seed/infra";

import { FILTROS_VAZIOS } from "@/components/geracao/biblioteca/filtros";
import { apiUrl } from "@/lib/apiBase";
import { uploadMultipart } from "@/hooks/useCardHub";
import type { Agente, Conversa, Headline, Memoria, Mencao, MencaoTipo, Mensagem, ViralCard } from "@/types/geracao";
import { viraisParams, type ViraisPage } from "./useBiblioteca";
import { GERACAO_KEY } from "./useHeadlineMutations";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T,>(res: Envelope<T>): T => res.data;
const enc = encodeURIComponent;

const BASE = "/api/media-creation/chat";
export const CHAT_KEY = [...GERACAO_KEY, "chat"] as const;
export const CONVERSAS_POR_PAGINA = 15;
export const MENSAGENS_POR_PAGINA = 100;
export const LIMITE_CONTEXTO_AVISO = 50_000;
export const MAX_REFERENCIAS = 10;

export type ReferenciaEnvio = { tipo: MencaoTipo; id: string };

// ─── Conversas ──────────────────────────────────────────────────────────────

export function useConversas(marcaId: string | null, agente: Agente) {
  const query = useInfiniteQuery({
    queryKey: [...CHAT_KEY, "conversas", marcaId, agente],
    enabled: !!marcaId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.get<Envelope<{ items: Conversa[]; tem_mais: boolean }>>(
          `${BASE}/conversas?marca_id=${enc(marcaId as string)}&agente=${agente}&limit=${CONVERSAS_POR_PAGINA}&offset=${pageParam}`,
        ),
      ),
    getNextPageParam: (last, all) => (last.tem_mais ? all.length * CONVERSAS_POR_PAGINA : undefined),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    conversas: query.data?.pages.flatMap((p) => p.items) ?? [],
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !query.isFetchingNextPage && !!query.data,
  };
}

export function useCriarConversa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { marca_id: string; agente: Agente; titulo?: string }) =>
      unwrap(await api.post<Envelope<Conversa>>(`${BASE}/conversas`, v)),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...CHAT_KEY, "conversas"] }),
  });
}

export function useRenomearConversa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { id: string; titulo: string }) =>
      unwrap(await api.patch<Envelope<Conversa>>(`${BASE}/conversas/${enc(v.id)}`, { titulo: v.titulo })),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...CHAT_KEY, "conversas"] }),
  });
}

export function useApagarConversa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/conversas/${enc(id)}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: CHAT_KEY }),
  });
}

// ─── Mensagens (older pages via the `antes` cursor) ─────────────────────────

export function useMensagens(conversaId: string | null) {
  const query = useInfiniteQuery({
    queryKey: [...CHAT_KEY, "mensagens", conversaId],
    enabled: !!conversaId,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.get<Envelope<{ items: Mensagem[]; tem_mais: boolean }>>(
          `${BASE}/conversas/${enc(conversaId as string)}/mensagens?limit=${MENSAGENS_POR_PAGINA}${
            pageParam ? `&antes=${enc(pageParam)}` : ""
          }`,
        ),
      ),
    // Items come oldest-first within a page; the cursor is the oldest id of the page.
    getNextPageParam: (last) => (last.tem_mais && last.items.length > 0 ? last.items[0].id : undefined),
    placeholderData: keepPreviousData,
  });
  // pages[0] is the newest page; older pages come after it.
  const mensagens = (query.data?.pages ?? [])
    .slice()
    .reverse()
    .flatMap((p) => p.items);
  return {
    ...query,
    mensagens,
    showSkeleton: !!conversaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !query.isFetchingNextPage && !!query.data,
  };
}

export function useContextoChat(conversaId: string | null) {
  const query = useQuery({
    queryKey: [...CHAT_KEY, "contexto", conversaId],
    enabled: !!conversaId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<{ contexto_chars: number; limite: number }>>(
          `${BASE}/contexto?conversa_id=${enc(conversaId as string)}`,
        ),
      ),
    placeholderData: keepPreviousData,
  });
  return { ...query, showSkeleton: !!conversaId && query.isPending && !query.data };
}

// ─── Menções (@) ────────────────────────────────────────────────────────────

export function useMencoes(marcaId: string | null, tipo: MencaoTipo, q: string, enabled: boolean) {
  const query = useQuery({
    queryKey: [...CHAT_KEY, "mencoes", marcaId, tipo, q],
    enabled: enabled && !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({ marca_id: marcaId as string, tipo });
      if (q.trim()) p.set("q", q.trim());
      return unwrap(await api.get<Envelope<Mencao[]>>(`${BASE}/mencoes?${p.toString()}`));
    },
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: enabled && !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

// ─── Memória ────────────────────────────────────────────────────────────────

export function useMemorias(marcaId: string | null, enabled = true) {
  const query = useQuery({
    queryKey: [...CHAT_KEY, "memorias", marcaId],
    enabled: enabled && !!marcaId,
    queryFn: async () =>
      unwrap(await api.get<Envelope<Memoria[]>>(`${BASE}/memorias?marca_id=${enc(marcaId as string)}`)),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: enabled && !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useAdicionarMemoria() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { marca_id: string; texto: string }) =>
      unwrap(await api.post<Envelope<Memoria>>(`${BASE}/memorias`, v)),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...CHAT_KEY, "memorias"] }),
  });
}

export function useRemoverMemoria() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/memorias/${enc(id)}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: [...CHAT_KEY, "memorias"] }),
  });
}

// ─── Citação `(estrutura #N)` -> viral ─────────────────────────────────────

/**
 * Resolves a cited structure code to its viral through the Biblioteca list
 * (`codigo` filter, #7). The endpoint is scoped to the marca's allow-list, so a
 * code outside the user's library resolves to `null` — a citation can never open
 * a viral the user cannot see.
 */
export async function resolverViralPorCodigo(marcaId: string, codigo: number): Promise<ViralCard | null> {
  const page = await unwrap(
    await api.get<Envelope<ViraisPage>>(
      `/api/media-creation/biblioteca/virais?${viraisParams(marcaId, { ...FILTROS_VAZIOS, codigo, verTodos: true, somenteVirais: false })}`,
    ),
  );
  return page.items.find((v) => v.codigo === codigo) ?? null;
}

// ─── Salvar headline (#29) ──────────────────────────────────────────────────

export function useSalvarHeadline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { marca_id: string; texto: string }) =>
      unwrap(await api.post<Envelope<Headline>>("/api/media-creation/headlines", { ...v, favoritar: true })),
    onSuccess: () => qc.invalidateQueries({ queryKey: GERACAO_KEY }),
  });
}

// ─── Streaming (#45) ────────────────────────────────────────────────────────

export type FrameChat = {
  meta?: { mensagem_usuario_id?: string; contexto_chars?: number; codigos_permitidos?: number[] };
  delta?: string;
  truncated?: boolean;
  done?: { mensagem_id?: string };
  error?: { code?: string; message?: string };
};

export interface EstadoStream {
  ativo: boolean;
  /** The user message being answered (shown optimistically until the refetch lands). */
  usuario: string | null;
  texto: string;
  truncada: boolean;
  erro: string | null;
  contextoChars: number | null;
  /** Viral codes the server allows as `(estrutura #N)` links for this answer, when sent. */
  codigosPermitidos: number[] | null;
}

const ESTADO_INICIAL: EstadoStream = {
  ativo: false,
  usuario: null,
  texto: "",
  truncada: false,
  erro: null,
  contextoChars: null,
  codigosPermitidos: null,
};

const ERROS_PRE_STREAM: Record<string, string> = {
  stream_em_andamento: "Já existe uma resposta sendo gerada. Aguarde ela terminar.",
  ia_nao_configurada: "A IA ainda não está configurada para a sua organização.",
  orcamento_ia_excedido: "O orçamento de IA do período foi atingido. Tente novamente mais tarde.",
};

export function mensagemPreStream(status: number, code: string | null, message: string | null): string {
  if (code && ERROS_PRE_STREAM[code]) return ERROS_PRE_STREAM[code];
  if (status === 409) return ERROS_PRE_STREAM.stream_em_andamento;
  if (status === 429) return message || "Limite de uso do chat atingido. Tente novamente mais tarde.";
  if (status === 503) return message || "O chat está indisponível no momento.";
  return message || "Não foi possível enviar a mensagem.";
}

export function useEnviarMensagem() {
  const qc = useQueryClient();
  const [estado, setEstado] = useState<EstadoStream>(ESTADO_INICIAL);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const parar = useCallback(() => abortRef.current?.abort(), []);

  const enviar = useCallback(
    async (conversaId: string, conteudo: string, referencias: ReferenciaEnvio[]): Promise<boolean> => {
      if (abortRef.current) return false;
      const controller = new AbortController();
      abortRef.current = controller;
      setEstado({ ...ESTADO_INICIAL, ativo: true, usuario: conteudo });
      let erro: string | null = null;
      let enviou = false;
      try {
        const token = await getAuthToken();
        const res = await fetch(apiUrl(`${BASE}/conversas/${enc(conversaId)}/mensagens`), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ conteudo, referencias }),
          signal: controller.signal,
        });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          const e = body?.error ?? body;
          throw new Error(
            mensagemPreStream(res.status, e?.code ?? e?.codigo ?? null, e?.message ?? e?.mensagem ?? null),
          );
        }
        enviou = true;
        for await (const f of readSseStream<FrameChat>(res, { signal: controller.signal })) {
          if (f.meta) {
            const m = f.meta;
            setEstado((s) => ({
              ...s,
              contextoChars: m.contexto_chars ?? s.contextoChars,
              codigosPermitidos: m.codigos_permitidos ?? s.codigosPermitidos,
            }));
          }
          if (f.delta) {
            const d = f.delta;
            setEstado((s) => ({ ...s, texto: s.texto + d }));
          }
          if (f.truncated) setEstado((s) => ({ ...s, truncada: true }));
          if (f.error) {
            erro = f.error.message || "A resposta foi interrompida por um erro.";
            break;
          }
        }
      } catch (e) {
        if (!(e instanceof Error && e.name === "AbortError")) {
          erro = e instanceof Error ? e.message : "Não foi possível enviar a mensagem.";
        }
        // An abort after the request went out: the server saved the user message
        // and a `parcial` answer, so the refetch below picks both up.
      } finally {
        abortRef.current = null;
      }
      if (enviou) {
        await qc.invalidateQueries({ queryKey: [...CHAT_KEY, "mensagens", conversaId] });
        await qc.invalidateQueries({ queryKey: [...CHAT_KEY, "contexto", conversaId] });
        void qc.invalidateQueries({ queryKey: [...CHAT_KEY, "conversas"] });
      }
      setEstado({ ...ESTADO_INICIAL, erro });
      return enviou && !erro;
    },
    [qc],
  );

  return { estado, enviar, parar };
}

// ─── Ditado (mic) ───────────────────────────────────────────────────────────

type TranscricaoResp = {
  id: string;
  status: "na_fila" | "processando" | "concluida" | "falhou" | "cancelada";
  texto?: string | null;
  erro?: { codigo?: string; mensagem?: string } | null;
};
const unwrapTranscricao = (r: TranscricaoResp | Envelope<TranscricaoResp>): TranscricaoResp =>
  "data" in r && r.data ? r.data : (r as TranscricaoResp);

const POLL_RAPIDO_MS = 3000;
const POLL_LENTO_MS = 10_000;
const POLL_JANELA_MS = 30_000;

/**
 * Dictation: upload the recorded Blob to the shared submit (`POST /api/transcricoes`,
 * `contexto_tipo=chat_ditado`), poll 3 s for 30 s then 10 s, and hand the transcript
 * to `onTexto` ONCE. The text only fills the composer — it never auto-sends.
 */
export function useDitadoChat(marcaId: string | null, onTexto: (texto: string) => void) {
  const [id, setId] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const inicio = useRef<number>(0);
  const entregue = useRef<string | null>(null);
  const onTextoRef = useRef(onTexto);
  onTextoRef.current = onTexto;

  const consulta = useQuery({
    queryKey: ["sw", "transcricao", id],
    enabled: !!id,
    queryFn: async () =>
      unwrapTranscricao(
        await api.get<TranscricaoResp | Envelope<TranscricaoResp>>(`/api/transcricoes/${enc(id as string)}`),
      ),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (s === "concluida" || s === "falhou" || s === "cancelada") return false;
      return Date.now() - inicio.current < POLL_JANELA_MS ? POLL_RAPIDO_MS : POLL_LENTO_MS;
    },
  });

  const data = consulta.data;
  useEffect(() => {
    if (!id || !data) return;
    if (data.status === "concluida" && entregue.current !== id) {
      entregue.current = id;
      setId(null);
      if (data.texto?.trim()) onTextoRef.current(data.texto.trim());
      else setErro("Não foi possível entender o áudio.");
    } else if (data.status === "falhou" || data.status === "cancelada") {
      setErro(data.erro?.mensagem || "A transcrição falhou. Tente gravar novamente.");
      setId(null);
    }
  }, [id, data]);

  const enviarAudio = useMutation({
    mutationFn: async (v: { blob: Blob; mime: string }) => {
      const ext = v.mime.includes("ogg") ? "ogg" : v.mime.includes("mp4") ? "m4a" : v.mime.includes("wav") ? "wav" : "webm";
      const form = new FormData();
      form.set("arquivo", v.blob, `ditado.${ext}`);
      form.set("contexto_tipo", "chat_ditado");
      form.set("contexto_ref", marcaId ?? "");
      return unwrapTranscricao(
        await uploadMultipart<TranscricaoResp | Envelope<TranscricaoResp>>("/api/transcricoes", form),
      );
    },
    onMutate: () => setErro(null),
    onSuccess: (r) => {
      inicio.current = Date.now();
      setId(r.id);
    },
    onError: (e) => setErro(e instanceof Error ? e.message : "Não foi possível enviar o áudio."),
  });

  return {
    enviar: (blob: Blob, mime: string) => enviarAudio.mutate({ blob, mime }),
    transcrevendo: enviarAudio.isPending || !!id,
    erro,
  };
}
