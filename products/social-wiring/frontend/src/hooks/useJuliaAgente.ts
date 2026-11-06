/**
 * Julia › Agente — the platform connection (status only; routing lives in `useJuliaRoteamento`).
 *
 *   GET  /api/julia/agente                                 org member: connection status (`conexao_plataforma`), agent status
 *   POST /api/julia/agente/conexao-plataforma/verificar    admin: re-probe the connection -> `{data: <conexao_plataforma>}`
 *
 * The connection is a PLATFORM grant (julia-line CONTRACT §D): nobody on the product side pastes or edits a token,
 * and the full token is never sent to the browser — only `token_mascarado`.
 *
 * Envelope `{data: …}`; typed server refusals are `AppException`s
 * (`{error: {code, message}}`) — `mensagemErroJulia` maps every code the Agente
 * page can provoke to its own pt-BR sentence so the UI never depends on the
 * wording the server happens to ship.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { mensagemErroServidor } from "@/lib/erroServidor";

export interface JuliaConexaoAgente {
  connection_id: string;
  label: string;
  agente_leads_ativo: boolean;
  agente_leads_key: string | null;
  authorized_numbers_count: number;
  agente_leads_ativado_em: string | null;
  agente_handoff_notificar_user_id: string | null;
}

export interface JuliaStatusAgente {
  agent_key: string;
  nome: string;
  ativo: boolean;
  versao_ativa: number | string | null;
  provider: string | null;
  model: string | null;
  llm_configurado: boolean;
  /** Platform-wide kill (agents). Julia answers nobody in any org while true. */
  desligado_plataforma?: boolean;
  /** Per-org operating mode (agents); anything but `ligado` means she is not answering. */
  modo?: string | null;
}

export type StatusConexaoPlataforma = "nao_configurada" | "ativa" | "com_falha" | "revogada" | "expirada";
export type MotivoFalhaConexao = "token_rejeitado" | "agents_indisponivel";

/** What SW knows about the platform grant that lets the WhatsApp talk to Julia. The token itself is never here. */
export interface ConexaoPlataforma {
  status: StatusConexaoPlataforma;
  conectada: boolean;
  /** Only set while `status === "com_falha"`. */
  motivo: MotivoFalhaConexao | null;
  token_prefix: string | null;
  /** First 4 + last 4 of the token, the middle hidden. Read-only, display only. */
  token_mascarado: string | null;
  conectada_em: string | null;
  agent_key: string | null;
  verificada_em: string | null;
  ultima_falha_em: string | null;
  expires_at: string | null;
}

export type MotivoBloqueioLigar = "julia_nao_publicada" | "julia_desligada_no_agents" | "agents_indisponivel";

/** Why the switch cannot go on: the same sentence for the read (`motivo_bloqueio`) and for the 409/503 on the PUT. */
export const MENSAGEM_BLOQUEIO_LIGAR: Record<MotivoBloqueioLigar, string> = {
  julia_nao_publicada: "A Julia ainda não foi liberada para esta empresa pela NoctusAI. Assim que for, você poderá ligá-la aqui.",
  julia_desligada_no_agents: "A Julia está pausada pela NoctusAI no momento. Você poderá ligá-la aqui quando ela for reativada.",
  agents_indisponivel: "Não foi possível confirmar agora se a Julia pode ser ligada. Tente novamente em instantes.",
};

export interface JuliaAgente {
  conexoes: JuliaConexaoAgente[];
  conexao_plataforma: ConexaoPlataforma;
  status_agente: JuliaStatusAgente | null;
  /** False = the switch cannot be turned ON (turning OFF is always allowed). */
  pode_ligar?: boolean;
  motivo_bloqueio?: MotivoBloqueioLigar | null;
  erro: string | null;
}

export const JULIA_AGENTE_KEY = ["sw", "julia", "agente"] as const;

/** pt-BR sentence per refusal code the Agente page can provoke. */
const MENSAGENS_POR_CODIGO: Record<string, string> = {
  julia_nao_publicada: MENSAGEM_BLOQUEIO_LIGAR.julia_nao_publicada,
  julia_desligada_no_agents: MENSAGEM_BLOQUEIO_LIGAR.julia_desligada_no_agents,
  webhook_hmac_required:
    "O webhook do WhatsApp ainda não tem assinatura (HMAC) configurada. Configure-a antes de ligar a Julia.",
  aviso_incompleto:
    "O aviso de privacidade ainda está incompleto (nome da empresa e contato). Fale com o suporte NoctusAI para completá-lo antes de ligar a Julia.",
  url_publica_indisponivel:
    "Não foi possível montar o link público do aviso de privacidade. Fale com o suporte.",
  destinatario_invalido: "O destinatário do aviso precisa ser owner ou admin da organização.",
  agents_nao_configurado: "A Julia ainda não foi conectada pela plataforma. Peça ao suporte NoctusAI para conectá-la.",
  conversa_sem_agente: "A Julia ainda não atendeu esta conversa, então não há o que pausar ou retomar.",
  transicao_invalida: "A conversa não pode mudar para esse estado agora.",
  agents_indisponivel: "Não foi possível falar com a Julia agora. Tente novamente em instantes.",
  agents_token_invalido: "A conexão da Julia com a plataforma foi recusada. Peça ao suporte NoctusAI para reconectar.",
  agente_nao_conectado: "A Julia ainda não está conectada à plataforma. Veja o cartão “Conexão com a plataforma”.",
  gerenciada_pela_plataforma: "Esta conexão é gerenciada pela plataforma NoctusAI e não pode ser alterada aqui.",
  link_obrigatorio: "A mensagem inicial precisa conter {link} (o link do aviso de privacidade).",
  secoes_invalidas: "As seções do aviso estão inválidas: cada bloco deve ser um parágrafo ou uma lista.",
};

function codigoDoErro(err: unknown): string | null {
  const code = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return typeof code === "string" ? code : null;
}

export function codigoErroJulia(err: unknown): string | null {
  return codigoDoErro(err);
}

export function mensagemErroJulia(err: unknown, fallback: string): string {
  const code = codigoDoErro(err);
  if (code && MENSAGENS_POR_CODIGO[code]) return MENSAGENS_POR_CODIGO[code];
  return mensagemErroServidor(err, fallback);
}

export function useJuliaAgente() {
  return useQuery({
    queryKey: JULIA_AGENTE_KEY,
    queryFn: async () => (await api.get<{ data: JuliaAgente }>("/api/julia/agente")).data,
  });
}

/**
 * "Testar conexão": the server re-probes the grant and answers the fresh `conexao_plataforma`, which replaces the one
 * in the cached agente read (so the badge and times agree with the toast before any refetch).
 */
export function useVerificarConexaoPlataforma() {
  return useCacheWriteMutation<ConexaoPlataforma, void>({
    mutationFn: async () =>
      (await api.post<{ data: ConexaoPlataforma }>("/api/julia/agente/conexao-plataforma/verificar", {})).data,
    targets: [
      {
        queryKey: JULIA_AGENTE_KEY,
        commit: (old: JuliaAgente | undefined, conexao) => (old ? { ...old, conexao_plataforma: conexao } : old),
      },
    ],
  });
}
