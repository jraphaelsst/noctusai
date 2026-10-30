/** Props every agent-page section renderer receives (agents-unified CONTRACT §7). */
import type { AgentePainel } from "@/api/agentes/types";

export interface SecaoProps {
  agentKey: string;
  agente: AgentePainel;
}
