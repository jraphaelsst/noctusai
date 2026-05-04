/**
 * Agents grid page — 11 cards, one per canonical specialist.
 *
 * Uses react-query for fetch lifecycle. The list endpoint already returns
 * the snapshot in canonical order (matching `dev_team_proxy.AGENT_NAMES`)
 * so we render directly in array order without re-sorting.
 */
import { useQuery } from "@tanstack/react-query";
import { Loader2, AlertCircle, Bot } from "lucide-react";
import { listAgents } from "@/lib/api";
import { AgentCard } from "@/components/AgentCard";
import type { AgentSnapshot } from "@/lib/types";

export default function AgentsPage() {
  const { data, isLoading, isError, error } = useQuery<AgentSnapshot[]>({
    queryKey: ["dev-team", "agents"],
    queryFn: listAgents,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Bot className="h-5 w-5 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground">
            11 specialists. Last-24h snapshot per agent.
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {isError && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
          <AlertCircle className="h-5 w-5" />
          <div>
            <p className="font-semibold">Failed to load agents</p>
            <p className="text-xs">{error instanceof Error ? error.message : String(error)}</p>
          </div>
        </div>
      )}

      {data && (
        <div
          data-testid="agents-grid"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
        >
          {data.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>
      )}
    </div>
  );
}
