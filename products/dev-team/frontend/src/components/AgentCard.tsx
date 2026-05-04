/**
 * Single agent card — renders one row of the agents grid.
 *
 * Layout: name + model on top, three metrics below (24h events, 24h cost,
 * success rate). Click anywhere on the card → navigate to detail page.
 */
import { Link } from "react-router-dom";
import { Bot, Clock, DollarSign, CheckCircle } from "lucide-react";
import type { AgentSnapshot } from "@/lib/types";

interface AgentCardProps {
  agent: AgentSnapshot;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(value);
}

function formatRate(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0%";
  return `${(value * 100).toFixed(1)}%`;
}

export function AgentCard({ agent }: AgentCardProps) {
  return (
    <Link
      to={`/agents/${encodeURIComponent(agent.name)}`}
      data-testid="agent-card"
      className="block rounded-lg border border-border bg-card p-5 hover:border-primary transition-colors"
    >
      <div className="flex items-center gap-2 mb-3">
        <Bot className="h-4 w-4 text-primary" />
        <h3 className="font-semibold text-foreground">{agent.name}</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-4 truncate" title={agent.model}>
        {agent.model || "unknown"}
      </p>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="flex items-center gap-1 text-muted-foreground mb-1">
            <Clock className="h-3 w-3" /> 24h
          </dt>
          <dd className="font-medium text-foreground">{agent.last_24h_events}</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-muted-foreground mb-1">
            <DollarSign className="h-3 w-3" /> Cost
          </dt>
          <dd className="font-medium text-foreground">{formatCurrency(agent.last_24h_cost)}</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-muted-foreground mb-1">
            <CheckCircle className="h-3 w-3" /> OK
          </dt>
          <dd className="font-medium text-foreground">{formatRate(agent.success_rate)}</dd>
        </div>
      </dl>
    </Link>
  );
}
