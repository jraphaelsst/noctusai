/**
 * Julia › Especificações do negócio (julia-line CONTRACT §C4 / S9): the business's own data that Julia uses —
 * declared by the agent's active version, filled in by SW users, validated server-side. They are DATA, never
 * instructions; Julia's core stays managed by NoctusAI.
 *
 *   GET /api/julia/especificacoes   org member: declarations + current values + what is missing / invalid
 *   PUT /api/julia/especificacoes   org admin:  {"valores": {chave: texto}} — a blank value clears that key
 *
 * Refusals (all typed): 422 (block mode) `{code, detail, violacoes[]}`; 409 `agente_nao_conectado`;
 * 502/503 `agents_indisponivel` | `agents_token_invalido`. Where the code sits in the body varies with how the server
 * raised it, so `leituraErroEspec` reads all the known places.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export type TipoEspecificacao =
  | "texto_curto"
  | "texto"
  | "texto_longo"
  | "url"
  | "dominios"
  | "contatos"
  | "cnpj"
  | "creci"
  | "horario"
  | "duracao"
  | "lista";

export interface EspecificacaoDeclarada {
  id: string;
  chave: string;
  rotulo: string;
  descricao: string | null;
  tipo: TipoEspecificacao;
  obrigatoria: boolean;
  exemplo: string | null;
}

export interface ValorEspecificacao {
  chave: string;
  valor: string;
  updated_at: string | null;
  /** Who last changed it (display name). Optional: absent/null until the backend provides it. */
  updated_by_nome?: string | null;
}

export interface ViolacaoEspecificacao {
  chave: string;
  codigo: string;
  motivo: string;
  mensagem: string;
}

export interface Especificacoes {
  agent_key: string;
  version_id: string | null;
  versao: number | string | null;
  declaradas: EspecificacaoDeclarada[];
  valores: ValorEspecificacao[];
  faltando: string[];
  /** In report mode the server saves anyway and lists what it judged invalid. */
  invalidas: ViolacaoEspecificacao[];
  modo_validacao: string;
}

export const JULIA_ESPECIFICACOES_KEY = ["sw", "julia", "especificacoes"] as const;
const URL = "/api/julia/especificacoes";

/** The answer may or may not come in the usual `{data}` envelope; both are accepted. */
function desembrulhar(r: Especificacoes | { data: Especificacoes }): Especificacoes {
  return "data" in r && r.data ? r.data : (r as Especificacoes);
}

export interface ErroEspec {
  status: number | null;
  code: string | null;
  violacoes: ViolacaoEspecificacao[];
}

export function leituraErroEspec(err: unknown): ErroEspec {
  const e = err as { status?: unknown; body?: Record<string, unknown> | null } | null | undefined;
  const body = e?.body ?? {};
  const aninhados = [body, body.error, body.detail].filter((x): x is Record<string, unknown> => !!x && typeof x === "object");
  const code = aninhados.map((o) => o.code).find((c): c is string => typeof c === "string") ?? null;
  const violacoes = aninhados.map((o) => o.violacoes).find((v): v is ViolacaoEspecificacao[] => Array.isArray(v)) ?? [];
  return { status: typeof e?.status === "number" ? e.status : null, code, violacoes };
}

/** The pt-BR sentence for a refusal the card can provoke; null = not one of ours (use the generic message). */
export function mensagemErroEspec(err: unknown): string | null {
  switch (leituraErroEspec(err).code) {
    case "agente_nao_conectado":
      return "A Julia ainda não está conectada à plataforma. Veja o cartão “Conexão com a plataforma”.";
    case "agents_indisponivel":
      return "A Julia está indisponível agora, então não conseguimos ler ou salvar as especificações. Tente de novo em instantes.";
    case "agents_token_invalido":
      return "A conexão da Julia com a plataforma foi recusada. Peça ao suporte NoctusAI para reconectar.";
    default:
      return null;
  }
}

export function useJuliaEspecificacoes() {
  return useQuery({
    queryKey: JULIA_ESPECIFICACOES_KEY,
    queryFn: async () => desembrulhar(await api.get<Especificacoes | { data: Especificacoes }>(URL)),
    // A typed 4xx (not connected, token refused) will not fix itself on a retry.
    retry: (n, err) => {
      const s = leituraErroEspec(err).status;
      return (s === null || s >= 500) && n < 2;
    },
  });
}

export function useSalvarEspecificacoes() {
  return useCacheWriteMutation<Especificacoes, { valores: Record<string, string> }>({
    mutationFn: async (body) => desembrulhar(await api.put<Especificacoes | { data: Especificacoes }>(URL, body)),
    // The server validates and normalises: the draft is not a prediction of the answer, so there is no optimistic
    // draw; the answer replaces the cached read.
    targets: [{ queryKey: JULIA_ESPECIFICACOES_KEY, commit: (_old: Especificacoes | undefined, saved) => saved }],
  });
}
