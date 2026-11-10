/**
 * "Funil de atendimento" — leads → roteiro → visitas → propostas, with the
 * average time between steps (CONTRACT sw-lead-to-contract §3.5). Everything is
 * computed server-side from rows; this card only renders it.
 */
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMetricasFunil } from "@/hooks/useMetricasFunil";

function dias(v: number | null): string {
  return v === null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} d`;
}

export function FunilAtendimentoCard() {
  const { data, isPending, isFetching, isError } = useMetricasFunil();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <Card data-testid="painel-funil-atendimento">
      <CardContent className="p-5">
        <h2 className="mb-3 font-semibold">
          Funil de atendimento
          {isRefreshing && <span className="ml-2 text-xs text-muted-foreground">atualizando…</span>}
        </h2>
        {showSkeleton ? (
          <div data-testid="painel-funil-atendimento-loading">
            <Skeleton className="h-32" />
          </div>
        ) : isError || !data ? (
          <p className="py-6 text-center text-sm text-destructive">
            Não foi possível carregar o funil.
          </p>
        ) : (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Leads", data.leads],
                ["Com roteiro", data.com_roteiro],
                ["Visitas agendadas", data.visitas_agendadas],
                ["Visitas realizadas", data.visitas_realizadas],
                ["Propostas criadas", data.propostas_criadas],
                ["Aceitas", data.propostas_aceitas],
                ["Recusadas", data.propostas_recusadas],
              ].map(([rotulo, valor]) => (
                <div key={String(rotulo)}>
                  <dt className="text-xs text-muted-foreground">{rotulo}</dt>
                  <dd className="text-2xl font-semibold tabular-nums">{valor}</dd>
                </div>
              ))}
            </dl>

            <div data-testid="painel-funil-resultados">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Resultado das visitas</p>
              <ul className="flex flex-wrap gap-1.5">
                {[
                  ["Consolidadas", data.visitas_consolidadas, "bg-success-light text-foreground"],
                  ["Perdidas", data.visitas_perdidas, "bg-danger-light text-destructive"],
                  ["Neutras (reagendadas e pendentes)", data.visitas_neutras, "bg-muted text-muted-foreground"],
                ].map(([rotulo, n, cls]) => (
                  <li key={String(rotulo)} className={`rounded-full px-2 py-0.5 text-xs ${cls}`}>
                    {rotulo}: {n}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-muted-foreground" data-testid="painel-funil-perdidas-detalhe">
                Perdidas: {data.visitas_canceladas} canceladas, {data.visitas_nao_compareceu} não compareceu ·{" "}
                {data.visitas_reagendadas} reagendadas não contam.
              </p>
            </div>

            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Tempo médio entre etapas</p>
              <ul className="grid gap-1 text-sm sm:grid-cols-2">
                <li>Lead → roteiro: {dias(data.tempo_medio_dias.lead_a_roteiro)}</li>
                <li>Roteiro → visita: {dias(data.tempo_medio_dias.roteiro_a_visita)}</li>
                <li>Visita → proposta: {dias(data.tempo_medio_dias.visita_a_proposta)}</li>
                <li>Proposta → aceite: {dias(data.tempo_medio_dias.proposta_a_aceite)}</li>
              </ul>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
