/**
 * Julia › Agente — the agents LINK (status only; routing lives in `useJuliaRoteamento`).
 *
 *   GET /api/julia/agente                       org member: token flag, link health, agent status
 *   PUT /api/julia/agente/token                 admin: paste the org's agents channel token (204)
 *
 * Envelope `{data: …}`; typed server refusals are `AppException`s
 * (`{error: {code, message}}`) — `mensagemErroJulia` maps every code the Agente
 * page can provoke to its own pt-BR sentence so the UI never depends on the
 * wording the server happens to ship.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
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
}

export interface JuliaAgente {
  conexoes: JuliaConexaoAgente[];
  token_configurado: boolean;
  status_agente: JuliaStatusAgente | null;
  erro: string | null;
  /** Base URL of the agents product (resolved server-side). Null = unresolvable. */
  agents_url?: string | null;
}

export const JULIA_AGENTE_KEY = ["sw", "julia", "agente"] as const;

/** pt-BR sentence per refusal code the Agente page can provoke. */
const MENSAGENS_POR_CODIGO: Record<string, string> = {
  authorized_numbers_required:
    "Cadastre ao menos um número autorizado nesta conexão antes de ligar a Julia — sem isso ela responderia a qualquer pessoa, inclusive à equipe.",
  webhook_hmac_required:
    "O webhook do WhatsApp ainda não tem assinatura (HMAC) configurada. Configure-a antes de ligar a Julia.",
  aviso_incompleto:
    "O aviso de privacidade ainda está incompleto (nome da empresa e contato). Preencha-o abaixo antes de ligar a Julia.",
  url_publica_indisponivel:
    "Não foi possível montar o link público do aviso de privacidade. Fale com o suporte.",
  snapshot_falhou:
    "Não foi possível ler as conversas existentes deste número; a Julia continua desligada.",
  destinatario_invalido: "O destinatário do aviso precisa ser owner ou admin da organização.",
  agents_nao_configurado: "O app de agentes ainda não está configurado para esta organização.",
  conversa_sem_agente: "A Julia ainda não atendeu esta conversa, então não há o que pausar ou retomar.",
  transicao_invalida: "A conversa não pode mudar para esse estado agora.",
  token_invalido: "O Agents recusou este token. Confira se copiou o token inteiro do canal.",
  agents_indisponivel: "Não foi possível validar o token com o Agents agora. Tente novamente em instantes.",
  link_obrigatorio: "A mensagem inicial precisa conter {link} (o link do aviso de privacidade).",
  secoes_invalidas: "As seções do aviso estão inválidas: cada bloco deve ser um parágrafo ou uma lista.",
};

function codigoDoErro(err: unknown): string | null {
  const code = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return typeof code === "string" ? code : null;
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

/** The token is write-only: it goes up once and is never read back. */
export function useSalvarTokenAgents() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, { token: string }>({
    mutationFn: ({ token }) => api.put("/api/julia/agente/token", { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: JULIA_AGENTE_KEY }),
  });
}
