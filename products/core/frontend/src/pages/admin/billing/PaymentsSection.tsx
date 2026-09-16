/** Charges with gateway fee and net — what each payment actually left us. */
import { useState } from 'react';
import { Badge, Button, TableSkeleton } from '@noctusai/lib/design-system';
import { formatCents, formatDate, useBillingPayments } from '../../../lib/billing';

const PAYMENT_LABEL = { pending: 'Pendente', paid: 'Pago', failed: 'Falhou', refunded: 'Estornado' } as const;
const METHOD_LABEL: Record<string, string> = { card: 'Cartão', pix: 'Pix', boleto: 'Boleto', unspecified: '—' };

export function PaymentsSection() {
  const [page, setPage] = useState(1);
  const { data, isPending, isFetching, error } = useBillingPayments(page);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const lastPage = Math.max(1, Math.ceil((data?.total ?? 0) / 50));

  if (showSkeleton) return <TableSkeleton rows={6} columns={7} />;
  if (error && !data) return <p role="alert" className="text-sm text-destructive">{error.message}</p>;
  if (!data) return null;

  const totals = data.page_totals_brl ?? { gross_cents: 0, fee_cents: 0, net_cents: 0 };
  return (
    <div className="space-y-4" aria-busy={isRefreshing}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[['Bruto (pagos, BRL, nesta página)', totals.gross_cents],
          ['Taxas', totals.fee_cents],
          ['Líquido', totals.net_cents]].map(([label, value]) => (
          <div key={label as string} className="rounded-lg border border-border bg-card p-4">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="text-xl font-semibold">{formatCents(value as number)}</div>
          </div>
        ))}
      </div>
      {data.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum pagamento registrado.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="p-2">Data</th><th>Organização</th><th>Gateway</th><th>Meio</th>
                <th>Status</th><th>Bruto</th><th>Taxa</th><th>Líquido</th>
              </tr>
            </thead>
            <tbody>
              {data.data.map((p) => (
                <tr key={p.id} className="border-t border-border">
                  <td className="p-2">{formatDate(p.paid_at ?? p.created_at)}</td>
                  <td>{p.organizations?.nome ?? p.org_id}</td>
                  <td>{p.gateway}{p.gateway_mode === 'test' ? ' (teste)' : ''}</td>
                  <td>{METHOD_LABEL[p.billing_method ?? 'unspecified'] ?? p.billing_method}</td>
                  <td><Badge variant={p.status === 'paid' ? 'default' : p.status === 'failed' ? 'destructive' : 'muted'}>{PAYMENT_LABEL[p.status]}</Badge></td>
                  <td>{formatCents(p.gross_cents, p.currency)}</td>
                  <td>{p.fee_pending ? 'aguardando' : formatCents(p.fee_cents, p.currency)}</td>
                  <td>{p.fee_pending ? '—' : formatCents(p.net_cents, p.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex items-center gap-2 text-sm">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
        <span>Página {page} de {lastPage}</span>
        <Button size="sm" variant="outline" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>Próxima</Button>
      </div>
    </div>
  );
}
