/**
 * Agentes — `/agentes`, the unified listing (agents-unified CONTRACT §4.1/§7).
 *
 * ONE card per agent of the org (`GET /api/agents/painel`): role agents, platform instances, org Studio agents and
 * the legacy ones, side by side. Every card opens the same dynamic page, `/agentes/:key`. What a card shows is the
 * painel DATA (`origem`, `papel`, `estado_externo`, `pode_alternar`) — never an agent key. The on/off switch is
 * offered only when the server says so (`pode_alternar`: a legacy agent + an org admin); a platform instance is
 * switched in its Controles section.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, ChevronRight, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import type { AgenteOrigem, AgentePainel } from "@/api/agentes/types";
import { useAgentesPainel } from "@/hooks/useAgentesPainel";
import { useToggleAgent } from "@/hooks/useAgents";
import { errorMessage } from "@/lib/errors";

export const ORIGEM_LABEL: Record<AgenteOrigem, string> = {
  legado: "Agente legado",
  plataforma: "Definição da plataforma",
  instancia: "Agente da plataforma",
  org: "Agente da organização",
};

export const PAPEL_LABEL: Record<string, string> = {
  sdr: "SDR / leads",
  operador: "Operador",
  academia: "Academia",
};

export function papelLabel(papel: string): string {
  return PAPEL_LABEL[papel.toLowerCase()] ?? papel;
}

function CardSkeleton() {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      <div className="h-3 w-full animate-pulse rounded bg-muted" />
      <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
    </div>
  );
}

export function AgenteSwitch({ agente }: { agente: AgentePainel }) {
  const toggle = useToggleAgent();
  if (!agente.pode_alternar) {
    return (
      <Badge variant={agente.ativo ? "default" : "muted"} data-testid={`agente-status-${agente.key}`}>
        {agente.ativo ? "Ligado" : "Desligado"}
      </Badge>
    );
  }
  async function alternar() {
    try {
      await toggle.mutateAsync({ key: agente.key, ativo: !agente.ativo });
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }
  return (
    <button
      type="button"
      role="switch"
      aria-checked={agente.ativo}
      aria-label={`Ligar/desligar ${agente.nome}`}
      disabled={toggle.isPending}
      onClick={alternar}
      data-testid={`agente-toggle-${agente.key}`}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        agente.ativo ? "bg-primary" : "bg-muted"
      }`}
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition-transform ${
          agente.ativo ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </button>
  );
}

/** One line under the name: the external product's state for an external agent, else the public description. */
export function AgenteResumo({ agente }: { agente: AgentePainel }) {
  if (agente.runtime === "external") {
    return agente.estado_externo ? (
      <p className="text-xs text-muted-foreground">
        Auto-resposta:{" "}
        <span className="font-medium text-foreground">{agente.estado_externo.auto_reply_enabled ? "ativada" : "desativada"}</span>
      </p>
    ) : (
      <p className="text-xs text-amber-600" data-testid={`agente-aviso-${agente.key}`}>
        {agente.aviso ?? "Estado externo indisponível."}
      </p>
    );
  }
  return <p className="line-clamp-2 text-sm text-muted-foreground">{agente.descricao ?? "Sem descrição."}</p>;
}

function AgenteCard({ agente }: { agente: AgentePainel }) {
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4" data-testid={`agente-card-${agente.key}`}>
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bot className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-foreground">{agente.nome}</h2>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {agente.papel && <Badge variant="default">{papelLabel(agente.papel)}</Badge>}
            <Badge variant="outline" data-testid={`agente-origem-${agente.key}`}>
              {ORIGEM_LABEL[agente.origem]}
            </Badge>
          </div>
        </div>
        <AgenteSwitch agente={agente} />
      </div>
      <AgenteResumo agente={agente} />
      {agente.capacidades.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {agente.capacidades.map((c) => (
            <li key={c} className="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs text-foreground">
              {c}
            </li>
          ))}
        </ul>
      )}
      <Link
        to={`/agentes/${encodeURIComponent(agente.key)}`}
        className="mt-auto inline-flex items-center gap-1 self-end text-xs font-medium text-primary hover:underline"
        data-testid={`agente-abrir-${agente.key}`}
      >
        Abrir <ChevronRight className="h-3.5 w-3.5" />
      </Link>
    </article>
  );
}

export default function Agentes() {
  const { data, showSkeleton, isRefreshing, isError, refetch } = useAgentesPainel();
  const [papel, setPapel] = useState("todos");
  const papeis = useMemo(
    () => Array.from(new Set((data ?? []).map((a) => a.papel).filter((p): p is string => !!p))),
    [data],
  );
  const visiveis = useMemo(() => (data ?? []).filter((a) => papel === "todos" || a.papel === papel), [data, papel]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bot className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agentes</h1>
          <p className="text-sm text-muted-foreground">
            Todos os agentes da organização, cada um com a sua página.
            {isRefreshing && <span className="ml-2 text-xs" data-testid="agentes-refreshing">Atualizando…</span>}
          </p>
        </div>
      </div>

      {showSkeleton ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="agentes-skeleton">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : isError && !data ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground" role="alert" data-testid="agentes-error">
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">Erro ao carregar os agentes.</p>
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : !data || data.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground" data-testid="agentes-empty">
          <Bot className="h-6 w-6 opacity-30" />
          <p className="text-sm">Nenhum agente nesta organização.</p>
        </div>
      ) : (
        <>
          {papeis.length > 1 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por papel">
              {["todos", ...papeis].map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-pressed={papel === p}
                  onClick={() => setPapel(p)}
                  data-testid={`agentes-filtro-${p}`}
                  className={`rounded-full border px-3 py-1 text-xs font-medium ${
                    papel === p ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background text-foreground hover:bg-accent"
                  }`}
                >
                  {p === "todos" ? "Todos" : papelLabel(p)}
                </button>
              ))}
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="agentes-list">
            {visiveis.map((a) => (
              <AgenteCard key={a.key} agente={a} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
