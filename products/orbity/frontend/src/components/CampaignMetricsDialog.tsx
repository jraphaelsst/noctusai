/**
 * CampaignMetricsDialog — manual daily metrics entry + history for one campaign.
 *
 * There is no live Meta sync: every number is typed here (PUT upsert keyed by
 * campaign + date). The history list is the campaign's own rows, so what you
 * enter is exactly what you read back. All four states are owned here.
 */
import { useState } from 'react';
import { format } from 'date-fns';
import { Loader2, X } from 'lucide-react';
import { ListSkeleton, RetryError, EmptyState } from '@noctusai/lib/organ-kit';
import {
  useCampaignMetrics,
  useUpsertCampaignMetric,
  type Campaign,
} from '@/hooks/useMetaAds';

function fmtMoney(v: number): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v);
}

function fmtDay(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

const INPUT =
  'flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

export function CampaignMetricsDialog({
  campaign,
  onClose,
}: {
  campaign: Campaign;
  onClose: () => void;
}) {
  const metricsQ = useCampaignMetrics(campaign.id);
  const upsert = useUpsertCampaignMetric(campaign.id);

  const [date, setDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [spend, setSpend] = useState('');
  const [impressions, setImpressions] = useState('');
  const [leads, setLeads] = useState('');

  const showSkeleton = metricsQ.isPending && !metricsQ.data;
  const rows = metricsQ.data ?? [];

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const spendN = parseFloat(spend);
    const impN = parseInt(impressions, 10);
    const leadsN = parseInt(leads, 10);
    if ([spendN, impN, leadsN].some((n) => Number.isNaN(n) || n < 0)) return;
    upsert.mutate(
      {
        date,
        spend: spendN,
        impressions: impN,
        leads: leadsN,
        cpl: leadsN > 0 ? Math.round((spendN / leadsN) * 100) / 100 : undefined,
      },
      {
        onSuccess: () => {
          setSpend('');
          setImpressions('');
          setLeads('');
        },
      },
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={`Métricas de ${campaign.name}`}
        className="w-full max-w-[calc(100vw-2rem)] sm:max-w-2xl max-h-[90vh] overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            Métricas — {campaign.name}
          </h2>
          <button
            onClick={onClose}
            aria-label="Fechar"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mb-6 space-y-3">
          <p className="text-xs text-muted-foreground">
            Lançamento manual — nada é buscado da Meta. Salvar de novo na mesma
            data substitui o valor daquele dia.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label htmlFor="metric-date" className="mb-1 block text-sm font-medium">Data *</label>
              <input id="metric-date" type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label htmlFor="metric-spend" className="mb-1 block text-sm font-medium">Investimento (R$) *</label>
              <input id="metric-spend" type="number" min="0" step="0.01" required value={spend} onChange={(e) => setSpend(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label htmlFor="metric-impressions" className="mb-1 block text-sm font-medium">Impressões *</label>
              <input id="metric-impressions" type="number" min="0" step="1" required value={impressions} onChange={(e) => setImpressions(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label htmlFor="metric-leads" className="mb-1 block text-sm font-medium">Leads *</label>
              <input id="metric-leads" type="number" min="0" step="1" required value={leads} onChange={(e) => setLeads(e.target.value)} className={INPUT} />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={upsert.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {upsert.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Salvar métricas
            </button>
          </div>
        </form>

        <h3 className="mb-2 text-sm font-semibold text-foreground">Histórico</h3>
        {showSkeleton ? (
          <ListSkeleton rows={3} />
        ) : metricsQ.isError && !metricsQ.data ? (
          <RetryError
            message="Não foi possível carregar o histórico de métricas."
            onRetry={() => void metricsQ.refetch()}
            retryLabel="Tentar novamente"
          />
        ) : rows.length === 0 ? (
          <EmptyState message="Nenhuma métrica lançada para esta campanha ainda." />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-muted/50">
                <tr>
                  <th className="px-3 py-2 font-medium text-muted-foreground">Data</th>
                  <th className="px-3 py-2 font-medium text-muted-foreground">Investimento</th>
                  <th className="px-3 py-2 font-medium text-muted-foreground">Impressões</th>
                  <th className="px-3 py-2 font-medium text-muted-foreground">Leads</th>
                  <th className="px-3 py-2 font-medium text-muted-foreground">CPL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((m) => (
                  <tr key={m.id}>
                    <td className="px-3 py-2">{fmtDay(m.date)}</td>
                    <td className="px-3 py-2">{fmtMoney(m.spend)}</td>
                    <td className="px-3 py-2">{m.impressions}</td>
                    <td className="px-3 py-2">{m.leads}</td>
                    <td className="px-3 py-2">{m.cpl != null ? fmtMoney(m.cpl) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
