/**
 * Chat (P2) over `/api/media-creation/chat` (contract §4.6 #41–48) plus the two
 * hooks the chat needs from other areas: save-a-headline (`POST /headlines`,
 * §4.4 #29) and mic dictation through the shared `POST /api/transcricoes`
 * submit (transcription-contract §4, `contexto_tipo=chat_ditado`).
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * never `isLoading`. Mutations write the server row into the cached reads, then settle by invalidating.
 *
 * Streaming (#45) is a `fetch` + the seed `readSseStream`; frames:
 * `meta` -> `delta`... -> (`truncated`) -> `done` | `error`. Pre-stream refusals
 * (409 / 429 / 503) are plain HTTP and surface as a pt-BR message.
 *
 * Unified chat (Estruturas contract §6.5, §9.2): one conversation per (user, marca);
 * the `done` frame carries the server-parsed `propostas`; `POST …/escolher` turns one
 * into a saved headline + roteiro + card (a resumable saga on the server), and the
 * `roteiro_gerado` message it creates is written straight into the messages cache.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { keepPreviousData, useInfiniteQuery, type InfiniteData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, jobPolling, readSseStream } from "@noctusai/lib";
import { infiniteOps, listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api, getAuthToken } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";
import { uploadMultipart } from "@/hooks/useCardHub";
import type { Fluxo, Proposta, ResolucaoPerfis } from "@/types/estruturas";
import type { Conversa, Headline, Memoria, Mencao, MencaoTipo, Mensagem } from "@/types/geracao";
import { ESTEIRA_KEY, ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
import { GERACAO_KEY } from "@/lib/geracaoKeys";

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

export function useConversas(marcaId: string | null) {
  const query = useInfiniteQuery({
    queryKey: [...CHAT_KEY, "conversas", marcaId],
    enabled: !!marcaId,
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.get<Envelope<{ items: Conversa[]; tem_mais: boolean }>>(
          `${BASE}/conversas?marca_id=${enc(marcaId as string)}&limit=${CONVERSAS_POR_PAGINA}&offset=${pageParam}`,
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

type ConversasCache = { pages: { items: Conversa[]; tem_mais: boolean }[]; pageParams: unknown[] };
const CONVERSAS_KEY = [...CHAT_KEY, "conversas"] as const;

export function useCriarConversa() {
  return useCacheWriteMutation<Conversa, { marca_id: string; titulo?: string }>({
    mutationFn: async (v) => unwrap(await api.post<Envelope<Conversa>>(`${BASE}/conversas`, v)),
    // The list is newest-activity first: the new conversa heads the first page.
    targets: (v) => [
      {
        queryKey: [...CONVERSAS_KEY, v.marca_id],
        commit: (old: ConversasCache | undefined, saved) => infiniteOps.prepend(old, saved),
      },
    ],
  });
}

export function useRenomearConversa() {
  return useCacheWriteMutation<Conversa, { id: string; titulo: string }>({
    mutationFn: async (v) =>
      unwrap(await api.patch<Envelope<Conversa>>(`${BASE}/conversas/${enc(v.id)}`, { titulo: v.titulo })),
    targets: (v) => [
      {
        queryKey: CONVERSAS_KEY,
        match: "prefix",
        optimistic: (old: ConversasCache | undefined, vars) => infiniteOps.patch(old, vars.id, { titulo: vars.titulo }),
        commit: (old: ConversasCache | undefined, saved) => infiniteOps.patch(old, v.id, saved),
      },
    ],
  });
}

export function useApagarConversa() {
  return useCacheWriteMutation<void, string>({
    mutationFn: async (id) => {
      await api.delete(`${BASE}/conversas/${enc(id)}`);
    },
    targets: (id) => [
      {
        queryKey: CONVERSAS_KEY,
        match: "prefix",
        optimistic: (old: ConversasCache | undefined) => infiniteOps.remove(old, id),
      },
    ],
    // Messages / contexto of the deleted conversa live under the same family.
    invalidate: [CHAT_KEY],
  });
}

// ─── Mensagens (older pages via the `antes` cursor) ─────────────────────────

type MensagensPage = { items: Mensagem[]; tem_mais: boolean };
type MensagensCache = { pages: MensagensPage[]; pageParams: unknown[] };
const MENSAGENS_KEY = [...CHAT_KEY, "mensagens"] as const;
export const FLUXO_POLL_MS = 3000;

/**
 * A `roteiro_gerado` message whose flow is still moving but has no roteiro row yet (the
 * saga is between headline and roteiro): nothing else can tell us it advanced, so the
 * messages read polls. Once the roteiro exists the card polls the roteiro itself.
 */
export function fluxoAguardandoRoteiro(data: { pages: MensagensPage[] } | undefined): boolean {
  return !!data?.pages.some((p) =>
    p.items.some(
      (m) =>
        m.fluxo &&
        // roteiro-first: the roteiro is born complete, so nothing polls it; the headline/card/caption steps only show up here.
        ((m.fluxo.direcao === "roteiro_primeiro" && (m.fluxo.etapa === "roteiro_salvo" || m.fluxo.etapa === "headline_gerando")) ||
          (!m.fluxo.roteiro && (m.fluxo.etapa === "headline_salva" || m.fluxo.etapa === "roteiro_gerando"))),
    ),
  );
}

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
    // Never carry another conversation's messages over: the unified chat shares one cache family.
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[3] === conversaId ? prev : undefined),
    ...jobPolling<InfiniteData<MensagensPage, string | null>>(fluxoAguardandoRoteiro, FLUXO_POLL_MS),
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

const MEMORIAS_KEY = [...CHAT_KEY, "memorias"] as const;

export function useAdicionarMemoria() {
  return useCacheWriteMutation<Memoria, { marca_id: string; texto: string }>({
    mutationFn: async (v) => unwrap(await api.post<Envelope<Memoria>>(`${BASE}/memorias`, v)),
    targets: (v) => [
      {
        queryKey: [...MEMORIAS_KEY, v.marca_id],
        commit: (old: Memoria[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
  });
}

export function useRemoverMemoria() {
  return useCacheWriteMutation<void, string>({
    mutationFn: async (id) => {
      await api.delete(`${BASE}/memorias/${enc(id)}`);
    },
    targets: (id) => [
      {
        queryKey: MEMORIAS_KEY,
        match: "prefix",
        optimistic: (old: Memoria[] | undefined) => listOps.remove(old, id),
      },
    ],
  });
}

// ─── Salvar headline (#29) ──────────────────────────────────────────────────

export function useSalvarHeadline() {
  return useCacheWriteMutation<Headline, { marca_id: string; texto: string }>({
    mutationFn: async (v) =>
      unwrap(await api.post<Envelope<Headline>>("/api/media-creation/headlines", { ...v, favoritar: true })),
    // Saved as favorita: it heads the marca's default favoritas list (server sorts newest first).
    targets: (v) => [
      {
        queryKey: [...GERACAO_KEY, "headlines", v.marca_id, "lista", "favoritas", "", "", 0],
        commit: (old: unknown, saved) => pageOps.prependNewest(old, saved),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

// ─── Streaming (#45) ────────────────────────────────────────────────────────

export type ModoEstrutura = "post" | "mencoes" | "auto" | "perfil_ambiguo" | "perfil_nao_encontrado";

export type FrameChat = {
  meta?: {
    mensagem_usuario_id?: string;
    contexto_chars?: number;
    /** Estrutura `codigo`s the answer may cite as `(estrutura #N)`. */
    codigos_permitidos?: number[];
    modo_estrutura?: ModoEstrutura;
    resolucao_perfis?: ResolucaoPerfis;
  };
  delta?: string;
  truncated?: boolean;
  done?: { mensagem_id?: string; propostas?: Proposta[] };
  error?: { code?: string; message?: string };
};

/**
 * Profile names the server could not resolve by itself (`meta.resolucao_perfis`): the user
 * picks one and the SAME message is sent again with that profile as a `perfil:<uuid>`
 * reference. Kept after the stream ends (until the next send / conversation change).
 */
export interface PerfilPendente {
  modo: "perfil_ambiguo" | "perfil_nao_encontrado";
  grupos: { trecho: string; candidatos: { perfil_id: string; handle: string; nome: string | null }[] }[];
  conteudo: string;
  referencias: ReferenciaEnvio[];
}

export interface EstadoStream {
  ativo: boolean;
  /** The user message being answered (shown optimistically until the refetch lands). */
  usuario: string | null;
  texto: string;
  truncada: boolean;
  erro: string | null;
  /** The refusal was a daily limit (429): the screen offers "Ajustar limites" to whoever can raise it. */
  erroLimiteDiario: boolean;
  contextoChars: number | null;
  /** Estrutura codes the server allows as `(estrutura #N)` links for this answer, when sent. */
  codigosPermitidos: number[] | null;
}

const ESTADO_INICIAL: EstadoStream = {
  ativo: false,
  usuario: null,
  texto: "",
  truncada: false,
  erro: null,
  erroLimiteDiario: false,
  contextoChars: null,
  codigosPermitidos: null,
};

const ERROS_PRE_STREAM: Record<string, string> = {
  stream_em_andamento: "Já existe uma resposta sendo gerada. Aguarde ela terminar.",
  ia_nao_configurada: "A IA ainda não está configurada para a sua organização.",
  orcamento_ia_excedido: "O orçamento de IA do período foi atingido. Tente novamente mais tarde.",
  geracao_indisponivel: "A geração está indisponível no momento. Tente novamente em instantes.",
  limite_de_mensagens: "Limite de mensagens do chat atingido. Tente novamente mais tarde.",
  estrutura_inativa: "Esta estrutura não está ativa.",
  perfil_optout: "Este criador pediu para não ser monitorado.",
};

/**
 * A refusal body in either shape the server uses: flat `{code, detail, ...}` (a coded
 * refusal) or `{error: {code, message}}` (a plain-string `detail`, e.g. 403).
 */
export function lerErroCorpo(body: unknown): { code: string | null; message: string | null } {
  const b = (body ?? {}) as Record<string, unknown>;
  const e = (b.error && typeof b.error === "object" ? b.error : b) as Record<string, unknown>;
  const code = typeof e.code === "string" ? e.code : null;
  const msg = [e.message, e.detail, b.detail].find((v) => typeof v === "string" && v) as string | undefined;
  return { code, message: msg ?? null };
}

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
  const [perfilPendente, setPerfilPendente] = useState<PerfilPendente | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const parar = useCallback(() => abortRef.current?.abort(), []);

  const enviar = useCallback(
    async (conversaId: string, conteudo: string, referencias: ReferenciaEnvio[]): Promise<boolean> => {
      if (abortRef.current) return false;
      const controller = new AbortController();
      abortRef.current = controller;
      setEstado({ ...ESTADO_INICIAL, ativo: true, usuario: conteudo });
      setPerfilPendente(null);
      let erro: string | null = null;
      let limiteDiario = false;
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
          const e = lerErroCorpo(await res.json().catch(() => null));
          limiteDiario = res.status === 429;
          throw new Error(mensagemPreStream(res.status, e.code, e.message));
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
            const pendente = perfilPendenteDoMeta(m, conteudo, referencias);
            if (pendente) setPerfilPendente(pendente);
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
      setEstado({ ...ESTADO_INICIAL, erro, erroLimiteDiario: limiteDiario && !!erro });
      return enviou && !erro;
    },
    [qc],
  );

  const limparPerfilPendente = useCallback(() => setPerfilPendente(null), []);
  return { estado, enviar, parar, perfilPendente, limparPerfilPendente };
}

/** `meta` → the profile-choice prompt, or null when every name resolved (pure; exported for tests). */
export function perfilPendenteDoMeta(
  meta: NonNullable<FrameChat["meta"]>,
  conteudo: string,
  referencias: ReferenciaEnvio[],
): PerfilPendente | null {
  const r = meta.resolucao_perfis;
  if (meta.modo_estrutura === "perfil_ambiguo") {
    const grupos = (r?.ambiguos ?? []).map((a) => ({ trecho: a.trecho, candidatos: a.candidatos }));
    return grupos.length ? { modo: "perfil_ambiguo", grupos, conteudo, referencias } : null;
  }
  if (meta.modo_estrutura === "perfil_nao_encontrado") {
    const grupos = (r?.nao_encontrados ?? []).map((a) => ({ trecho: a.trecho, candidatos: a.sugestoes }));
    return grupos.length ? { modo: "perfil_nao_encontrado", grupos, conteudo, referencias } : null;
  }
  return null;
}

// ─── Escolher uma proposta (§6.5 / §9.2) ────────────────────────────────────

export type EscolherInput = { conversaId: string } & ({ proposta_id: string } | { headline_id: string });
export type EscolherResposta = {
  proposta: Proposta;
  fluxo: Fluxo;
  mensagem_id: string;
  ja_existia: boolean;
  em_andamento: boolean;
};

export const TEXTO_ROTEIRO_GERADO = "Criei o roteiro desta headline e o card na Esteira.";

const ERROS_ESCOLHER: Record<string, string> = {
  proposta_nao_encontrada: "Esta headline não foi encontrada. Atualize a conversa e tente de novo.",
  limite_diario_roteiros: "Você atingiu o limite diário de roteiros. Tente novamente amanhã.",
  ia_nao_configurada: ERROS_PRE_STREAM.ia_nao_configurada,
  orcamento_ia_excedido: ERROS_PRE_STREAM.orcamento_ia_excedido,
  geracao_indisponivel: ERROS_PRE_STREAM.geracao_indisponivel,
  headline_ja_em_post: "Esta headline já está em um card da Esteira.",
  roteiro_ja_em_post: "Este roteiro já está em um card da Esteira.",
};

/** pt-BR message for a refused `escolher` (never silent; the headline stays saved on the server). */
export function mensagemEscolher(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code && ERROS_ESCOLHER[e.code]) return ERROS_ESCOLHER[e.code];
    if (e.status === 404) return ERROS_ESCOLHER.proposta_nao_encontrada;
    if (e.status === 429) return ERROS_ESCOLHER.limite_diario_roteiros;
    if (e.status === 503) return ERROS_ESCOLHER.geracao_indisponivel;
  }
  return "Não foi possível criar o roteiro. Tente novamente.";
}

const mapMensagens = (old: MensagensCache | undefined, fn: (m: Mensagem) => Mensagem): MensagensCache | undefined =>
  old && Array.isArray(old.pages)
    ? { ...old, pages: old.pages.map((p) => ({ ...p, items: p.items.map(fn) })) }
    : old;

/** The newest page's tail gets the `roteiro_gerado` message (idempotent: a known id is replaced). */
function anexarMensagem(old: MensagensCache | undefined, nova: Mensagem): MensagensCache | undefined {
  if (!old || !Array.isArray(old.pages) || old.pages.length === 0) return old;
  const existe = old.pages.some((p) => p.items.some((m) => m.id === nova.id));
  if (existe) return mapMensagens(old, (m) => (m.id === nova.id ? nova : m));
  const [primeira, ...resto] = old.pages;
  return { ...old, pages: [{ ...primeira, items: [...primeira.items, nova] }, ...resto] };
}

/**
 * Clicking a proposta: the server saves the headline, creates the roteiro and the card, and
 * posts the `roteiro_gerado` message. We write what the answer carries into the messages cache
 * (proposta marked `escolhida` + the new message with its `fluxo`) and settle the families the
 * saga touched in the background: headline lists, roteiros, the Esteira board and card origin.
 */
export function useEscolherProposta() {
  return useCacheWriteMutation<EscolherResposta, EscolherInput>({
    mutationFn: async ({ conversaId, ...corpo }) =>
      unwrap(await api.post<Envelope<EscolherResposta>>(`${BASE}/conversas/${enc(conversaId)}/escolher`, corpo)),
    targets: (v) => [
      {
        queryKey: [...MENSAGENS_KEY, v.conversaId],
        commit: (old: MensagensCache | undefined, saved) => {
          const marcada = mapMensagens(old, (m) =>
            m.propostas.some((p) => p.id === saved.proposta.id)
              ? { ...m, propostas: m.propostas.map((p) => (p.id === saved.proposta.id ? { ...p, ...saved.proposta } : p)) }
              : m,
          );
          return anexarMensagem(marcada, {
            id: saved.mensagem_id,
            role: "assistant",
            conteudo: TEXTO_ROTEIRO_GERADO,
            referencias: [],
            status: "completa",
            truncada: false,
            created_at: new Date().toISOString(),
            tipo: "roteiro_gerado",
            propostas: [],
            fluxo: saved.fluxo,
          });
        },
      },
    ],
    // The saga created: a favorite headline, a roteiro, a card + its origin. Settled in the background.
    invalidate: [[...GERACAO_KEY, "headlines"], [...GERACAO_KEY, "roteiros"], [ESTEIRA_PIPELINE_KEY], ESTEIRA_KEY],
  });
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
    // poll-budget: 3s for 30s then 10s until concluida|falhou|cancelada; ~5 calls/tick; worst 43200/day per open tab (never-terminal job); hidden=paused
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
