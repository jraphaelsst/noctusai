/**
 * Julia › Agente (`/julia/agente`) — LINE ROUTING only (julia-v2 CONTRACT Q4 / 0.3, white-label, any org).
 *
 * Julia lives in the agents app; this page never configures her behaviour (no prompts, rules or texts here — IP stays
 * in agents). It shows: the link to configure her there, the agents link health (token + status), which WhatsApp
 * lines feed her + the handoff notification target, and the privacy notice (legal, lives in SW).
 * Reads are for any org member; every write is core owner/admin (server-enforced — `useIsOrgAdmin` only decides what
 * the UI offers).
 *
 * Loading = two signals off `data` (never `isLoading`):
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { AlertCircle, Loader2 } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { AgentsLinkCard } from "@/components/julia/AgentsLinkCard";
import { AvisoPrivacidadeCard } from "@/components/julia/AvisoPrivacidadeCard";
import { ConfigurarNoAgentes } from "@/components/julia/ConfigurarNoAgentes";
import { RoteamentoCard } from "@/components/julia/RoteamentoCard";
import { useJuliaAgente } from "@/hooks/useJuliaAgente";
import { useJuliaRoteamento } from "@/hooks/useJuliaRoteamento";
import { JULIA_LABEL, JULIA_PAGES } from "@/nav/julia";

export default function JuliaAgente() {
  const isAdmin = useIsOrgAdmin();
  const rot = useJuliaRoteamento();
  const agente = useJuliaAgente();
  const showSkeleton = rot.isPending && !rot.data;
  const isRefreshing = (rot.isFetching && !!rot.data) || (agente.isFetching && !!agente.data);

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">
            {JULIA_LABEL} · {JULIA_PAGES.agente.name}
          </h1>
          <p className="text-sm text-muted-foreground">
            Aqui você escolhe quais números de WhatsApp atendem leads com a Julia e quem é avisado quando ela passa um
            lead para uma pessoa. O comportamento da Julia (conteúdo, perguntas, regras) é configurado no app de agentes.
          </p>
          <ConfigurarNoAgentes agentsUrl={rot.data?.agents_url ?? agente.data?.agents_url} />
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="agente-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </header>

      {showSkeleton ? (
        <div className="space-y-4" data-testid="agente-skeleton">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : rot.data ? (
        <>
          {agente.data ? (
            <AgentsLinkCard data={agente.data} isAdmin={isAdmin} />
          ) : agente.isPending ? (
            <div className="h-24 animate-pulse rounded-lg bg-muted" data-testid="agents-link-skeleton" />
          ) : (
            <p role="alert" className="text-sm text-destructive" data-testid="agents-link-erro">
              Não foi possível consultar o estado da conexão com o app de agentes.
            </p>
          )}
          <RoteamentoCard data={rot.data} isAdmin={isAdmin} />
          <AvisoPrivacidadeCard isAdmin={isAdmin} />
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="agente-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as linhas de WhatsApp.</p>
          <Button variant="outline" size="sm" onClick={() => rot.refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}
    </div>
  );
}
