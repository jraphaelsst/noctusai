/**
 * "Funil de atendimento" — leads → roteiro → visitas → propostas, with the
 * average time between steps (CONTRACT sw-lead-to-contract §3.5). Everything is
 * computed server-side from rows; this card only renders it.
 */
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMetricasFunil } from "@/hooks/useMetricasFunil";
import { MOTIVOS_NAO_REALIZADA } from "@/types/cardHub";

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

            {Object.keys(data.visitas_nao_realizadas).length > 0 && (
              <div data-testid="painel-funil-nao-realizadas">
                <p className="mb-1 text-xs font-medium text-muted-foreground">Visitas não realizadas</p>
                <ul className="flex flex-wrap gap-1.5">
                  {Object.entries(data.visitas_nao_realizadas).map(([motivo, n]) => (
                    <li key={motivo} className="rounded-full bg-rose-100 px-2 py-0.5 text-xs text-rose-900">
                      {MOTIVOS_NAO_REALIZADA.find((m) => m.value === motivo)?.label ?? motivo}: {n}
                    </li>
                  ))}
                </ul>
              </div>
            )}

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
