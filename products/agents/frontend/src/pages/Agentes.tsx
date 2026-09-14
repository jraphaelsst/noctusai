/**
 * Agentes page — contract §E.2 (`GET /api/agents`,
 * `POST /api/agents/{key}/toggle`), `/agentes`.
 *
 * Lists every agent (`julia`, `one-chat`). For `one-chat` shows the live
 * social-wiring auto-reply state (`estado_externo.auto_reply_enabled`), or
 * `aviso` when `estado_externo` is null (not configured / unreachable). The
 * on/off toggle is admin/owner-only (`useIsAdmin`) — members see read-only
 * badges, matching the backend's `require_admin` on the toggle route.
 */
import { Link } from "react-router-dom";
import { Bot, Cpu, Settings, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@noctusai/lib/design-system";
import { useAgents, useToggleAgent, type Agent } from "@/hooks/useAgents";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";

const AGENT_ICON: Record<string, typeof Bot> = {
  julia: Bot,
  "one-chat": Cpu,
};

function AgentSkeletonRow() {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
      <div className="h-9 w-9 flex-shrink-0 animate-pulse rounded-full bg-muted" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3.5 w-32 animate-pulse rounded bg-muted" />
        <div className="h-3 w-48 animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}

function AgentToggle({ agent, isAdmin }: { agent: Agent; isAdmin: boolean }) {
  const toggleAgent = useToggleAgent();

  if (!isAdmin) {
    return (
      <Badge variant={agent.ativo ? "default" : "muted"} data-testid={`agent-status-${agent.key}`}>
        {agent.ativo ? "Ligado" : "Desligado"}
      </Badge>
    );
  }

  async function handleToggle(next: boolean) {
    try {
      await toggleAgent.mutateAsync({ key: agent.key, ativo: next });
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <button
      type="button"
      role="switch"
      aria-checked={agent.ativo}
      aria-label={`Ligar/desligar ${agent.nome}`}
      disabled={toggleAgent.isPending}
      onClick={() => handleToggle(!agent.ativo)}
      data-testid={`agent-toggle-${agent.key}`}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        agent.ativo ? "bg-primary" : "bg-muted"
      }`}
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition-transform ${
          agent.ativo ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </button>
  );
}

export default function Agentes() {
  const { data: agents, showSkeleton, isError } = useAgents();
  const isAdmin = useIsAdmin();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bot className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agentes</h1>
          <p className="text-sm text-muted-foreground">Ligue, desligue e configure os agentes da organização.</p>
        </div>
      </div>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="agents-skeleton">
          <AgentSkeletonRow />
          <AgentSkeletonRow />
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground">
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">Erro ao carregar agentes.</p>
        </div>
      ) : !agents || agents.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground">
          <Bot className="h-6 w-6 opacity-30" />
          <p className="text-sm">Nenhum agente configurado.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="agents-list">
          {agents.map((agent) => {
            const Icon = AGENT_ICON[agent.key] ?? Bot;
            return (
              <div
                key={agent.key}
                className="flex items-center gap-3 rounded-lg border border-border bg-card p-4"
                data-testid={`agent-row-${agent.key}`}
              >
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-semibold text-foreground">{agent.nome}</p>
                    {agent.key === "julia" && (
                      <Badge variant={agent.ativo ? "default" : "muted"}>
                        {agent.ativo ? "Ligada" : "Desligada"}
                      </Badge>
                    )}
                  </div>
                  {agent.key === "one-chat" ? (
                    agent.estado_externo ? (
                      <p className="text-xs text-muted-foreground">
                        Auto-resposta:{" "}
                        <span className="font-medium text-foreground">
                          {agent.estado_externo.auto_reply_enabled ? "ativada" : "desativada"}
                        </span>
                      </p>
                    ) : (
                      <p className="text-xs text-amber-600" data-testid={`agent-aviso-${agent.key}`}>
                        {agent.aviso ?? "Estado externo indisponível."}
                      </p>
                    )
                  ) : (
                    <p className="truncate text-xs text-muted-foreground">
                      {agent.runtime === "claude_sdk" ? "Agente de IA" : agent.owner_product ?? "—"}
                    </p>
                  )}
                </div>

                {agent.key === "julia" && isAdmin && (
                  <Link
                    to="/agentes/julia/persona"
                    className="inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
                    data-testid="agent-persona-link"
                  >
                    <Settings className="h-3.5 w-3.5" />
                    Persona
                  </Link>
                )}

                <AgentToggle agent={agent} isAdmin={isAdmin} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
