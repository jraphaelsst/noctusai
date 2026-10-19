/**
 * Blocos do atendimento — maya-blocks CONTRACT §4.1 / §4.2.
 *
 *   GET /api/atendimento-blocos   → BlocosConfig (any org member)
 *   PUT /api/atendimento-blocos   → BlocosConfig (owner/admin; partial body)
 *
 * Success bodies arrive as `{data: …}` (contract §4) and the seed `api` client
 * does not unwrap them — the fetchers here do. The closed block list,
 * its order, labels, pipelines and the allowed agents all come FROM the
 * server — this file never re-declares them (the backend `BLOCOS` constant is
 * the one source).
 *
 * Loading = two signals off `data` (never `isLoading`), computed here.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export type PipelineBloco = "funil" | "processos_venda";

export interface BlocoAtendimento {
  bloco: string;
  rotulo: string;
  ordem: number;
  agent_key: string | null;
  ativo: boolean;
  /** `null` only for `sdr` (the pre-card phase). Fixed per block server-side. */
  pipeline: PipelineBloco | null;
  etapas: string[];
  origem: "padrao" | "org";
  updated_at: string | null;
  updated_by: string | null;
}

export interface EtapaSemBloco {
  pipeline: PipelineBloco;
  slug: string;
  label: string;
}

export interface BlocosConfig {
  blocos: BlocoAtendimento[];
  etapas_sem_bloco: EtapaSemBloco[];
  agentes_por_bloco: Record<string, string[]>;
  supervisao_ativa: boolean;
}

/** One item of the partial PUT body (§4.2) — `pipeline` is never sent. */
export interface BlocoAlteracao {
  bloco: string;
  agent_key: string | null;
  ativo: boolean;
  etapas: string[];
}

export const BLOCOS_KEY = ["sw", "atendimento-blocos"] as const;
const PATH = "/api/atendimento-blocos";

/** Display name for a block agent key; unknown keys show the key itself. */
const AGENTES_ROTULO: Record<string, string> = { "lead-imob": "Julia" };
export function rotuloAgente(agentKey: string | null): string {
  if (agentKey === null) return "Humanos (equipe)";
  const nome = AGENTES_ROTULO[agentKey];
  return nome ? `${nome} (${agentKey})` : agentKey;
}

export function useAtendimentoBlocos() {
  const q = useQuery({
    queryKey: BLOCOS_KEY,
    queryFn: async () => (await api.get<{ data: BlocosConfig }>(PATH)).data,
  });
  return {
    ...q,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
  };
}

export function useSalvarAtendimentoBlocos() {
  const qc = useQueryClient();
  return useMutation<BlocosConfig, unknown, BlocoAlteracao[]>({
    mutationFn: async (blocos) => (await api.put<{ data: BlocosConfig }>(PATH, { blocos })).data,
    // 200 = the state after (§4.2) — seed the cache with it, no refetch needed.
    onSuccess: (estado) => qc.setQueryData(BLOCOS_KEY, estado),
    // A concurrent save means our copy is stale: re-GET (the contract's remedy).
    onError: (err) => {
      if (codigoErro(err) === "conflito_concorrente") void qc.invalidateQueries({ queryKey: BLOCOS_KEY });
    },
  });
}

/** `error.code` of the contract's `{error: {code, message}}` envelope, if any. */
export function codigoErro(err: unknown): string | null {
  const code = (err as { body?: { error?: { code?: unknown } } } | null)?.body?.error?.code;
  return typeof code === "string" ? code : null;
}

/** Fallback sentences per §4.2 code — the server's own message wins when present
 * for `etapa_em_dois_blocos` (it names the slug and both blocks). */
const MENSAGENS: Record<string, string> = {
  etapa_em_dois_blocos: "Uma etapa ficou em dois blocos. Cada etapa só pode pertencer a um bloco.",
  etapa_desconhecida: "Uma das etapas escolhidas não existe (ou está inativa) neste funil.",
  sdr_sem_etapas: "O bloco SDR atua antes do card e não recebe etapas.",
  agente_indisponivel: "Esse agente não está disponível para o bloco.",
  conflito_concorrente:
    "Outra pessoa salvou os blocos ao mesmo tempo. Recarregamos a configuração — revise e salve de novo.",
  FORBIDDEN: "Apenas o proprietário ou um administrador pode alterar os blocos.",
};

export function mensagemErroBlocos(err: unknown): string {
  const code = codigoErro(err);
  if (code === "etapa_em_dois_blocos") {
    const doServidor = (err as { body?: { error?: { message?: unknown } } }).body?.error?.message;
    return typeof doServidor === "string" && doServidor ? doServidor : MENSAGENS[code];
  }
  if (code && MENSAGENS[code]) return MENSAGENS[code];
  return mensagemErroServidor(err, "Não foi possível salvar os blocos.");
}
