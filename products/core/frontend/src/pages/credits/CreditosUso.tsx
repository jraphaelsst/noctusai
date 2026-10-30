/**
 * "Créditos e uso" — the org's AI credit wallet (owner / admin / manager of the selected org).
 *
 * Balance (credits + R$), the usage of the period broken down org → product → feature (credits,
 * R$ at the retail credit price, tokens) with a per-product daily chart, and "Comprar créditos"
 * (PIX / boleto / card on the platform's billing gateway; the balance moves when the payment
 * lands). Provider cost and margin are never shown here.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Coins, Cpu, Receipt, Wallet } from 'lucide-react';
import {
  Badge, BarChart, Button, ChartCard, EmptyState, ErrorState, Field, Input, Select, Skeleton, StatTile,
  StatTileRow, TableSkeleton,
} from '@noctusai/lib/design-system';
import {
  formatBrl, formatCredits, formatPct, formatTokens, KIND_LABEL, MODE_LABEL,
  useBuyCredits, useMyUsage, useMyWallet, type PurchaseResult, type UsageReport,
} from '../../lib/credits';

const RANGES = [
  { key: '7', label: 'Últimos 7 dias', days: 7 },
  { key: '30', label: 'Últimos 30 dias', days: 30 },
  { key: '90', label: 'Últimos 90 dias', days: 90 },
] as const;

function rangeFor(days: number): { from: string; to: string } {
  const to = new Date();
  to.setUTCMinutes(0, 0, 0); // a stable key within the hour (no refetch storm on every render)
  const from = new Date(to.getTime() - days * 86_400_000);
  return { from: from.toISOString(), to: to.toISOString() };
}

function BuyCredits({ gateways, unit, onDone }: { gateways: Array<'asaas' | 'stripe'>; unit: number;
  onDone: (r: PurchaseResult) => void }) {
  const buy = useBuyCredits();
  const [amount, setAmount] = useState('100');
  const [method, setMethod] = useState<'pix' | 'boleto' | 'card'>('pix');
  const [taxId, setTaxId] = useState('');
  const gateway = gateways.includes('asaas') ? 'asaas' : 'stripe';
  const value = Number(amount.replace(',', '.'));
  const valid = Number.isFinite(value) && value >= 10 && value <= 50000 && (gateway !== 'asaas' || taxId.trim().length >= 11);
  if (gateways.length === 0) {
    return <p className="text-sm text-muted-foreground">A compra de créditos não está disponível no momento.</p>;
  }
  return (
    <form
      className="grid gap-3 sm:grid-cols-4 sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        buy.mutate(
          { amount_brl: value.toFixed(2), gateway, billing_method: gateway === 'stripe' ? 'card' : method,
            ...(gateway === 'asaas' ? { tax_id: taxId.trim() } : {}) },
          { onSuccess: onDone },
        );
      }}
    >
      <Field label="Valor (R$)">
        <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Valor em reais" />
      </Field>
      {gateway === 'asaas' && (
        <>
          <Field label="Forma de pagamento">
            <Select aria-label="Forma de pagamento" value={method} onChange={(e) => setMethod(e.target.value as typeof method)}>
              <option value="pix">PIX</option>
              <option value="boleto">Boleto</option>
              <option value="card">Cartão</option>
            </Select>
          </Field>
          <Field label="CPF/CNPJ">
            <Input value={taxId} onChange={(e) => setTaxId(e.target.value)} aria-label="CPF ou CNPJ" />
          </Field>
        </>
      )}
      <div className="space-y-1">
        <Button type="submit" disabled={!valid || buy.isPending}>
          {buy.isPending ? 'Gerando cobrança…' : 'Comprar créditos'}
        </Button>
        {Number.isFinite(value) && value > 0 && (
          <p className="text-xs text-muted-foreground">≈ {formatCredits(value / unit)} créditos</p>
        )}
      </div>
      {buy.error && <p role="alert" className="text-sm text-destructive sm:col-span-4">{buy.error.message}</p>}
    </form>
  );
}

function PurchaseInstructions({ result }: { result: PurchaseResult }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 text-sm" role="status">
      <p className="font-medium text-foreground">
        Cobrança criada: {formatCredits(result.credits)} créditos por {formatBrl(result.amount_cents / 100)}.
      </p>
      <p className="mt-1 text-muted-foreground">Os créditos entram no saldo assim que o pagamento for confirmado.</p>
      {result.pix_qr && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-start">
          <img src={`data:image/png;base64,${result.pix_qr.encoded_image}`} alt="QR Code PIX" className="h-40 w-40" />
          <code className="break-all rounded-md bg-muted p-2 text-xs text-foreground">{result.pix_qr.payload}</code>
        </div>
      )}
      {result.checkout_url && (
        <a className="mt-3 inline-block text-primary hover:underline" href={result.checkout_url} target="_blank" rel="noreferrer">
          Abrir página de pagamento
        </a>
      )}
    </div>
  );
}

function UsageTable({ data }: { data: UsageReport }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2">Produto / funcionalidade</th>
            <th className="px-3 py-2 text-right">Chamadas</th>
            <th className="px-3 py-2 text-right">Tokens</th>
            <th className="px-3 py-2 text-right">Créditos</th>
            <th className="px-3 py-2 text-right">R$</th>
          </tr>
        </thead>
        <tbody>
          {data.per_product.map((p) => (
            <ProductRows key={p.product} product={p} />
          ))}
        </tbody>
        <tfoot className="border-t border-border font-medium">
          <tr>
            <td className="px-3 py-2">Total</td>
            <td className="px-3 py-2 text-right">{data.totals.calls}</td>
            <td className="px-3 py-2 text-right">{formatTokens(data.totals.tokens)}</td>
            <td className="px-3 py-2 text-right">{formatCredits(data.totals.credits)}</td>
            <td className="px-3 py-2 text-right">{formatBrl(data.totals.brl)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function ProductRows({ product }: { product: UsageReport['per_product'][number] }) {
  return (
    <>
      <tr className="border-t border-border bg-card font-medium text-foreground">
        <td className="px-3 py-2">{product.product}</td>
        <td className="px-3 py-2 text-right">{product.calls}</td>
        <td className="px-3 py-2 text-right">{formatTokens(product.tokens)}</td>
        <td className="px-3 py-2 text-right">{formatCredits(product.credits)}</td>
        <td className="px-3 py-2 text-right">{formatBrl(product.brl)}</td>
      </tr>
      {product.per_feature.map((f) => (
        <tr key={f.feature} className="border-t border-border text-muted-foreground">
          <td className="px-3 py-1.5 pl-8">{f.feature}</td>
          <td className="px-3 py-1.5 text-right">{f.calls}</td>
          <td className="px-3 py-1.5 text-right">{formatTokens(f.tokens)}</td>
          <td className="px-3 py-1.5 text-right">{formatCredits(f.credits)}</td>
          <td className="px-3 py-1.5 text-right">{formatBrl(f.brl)}</td>
        </tr>
      ))}
    </>
  );
}

export function CreditosUso() {
  const navigate = useNavigate();
  const [rangeKey, setRangeKey] = useState<(typeof RANGES)[number]['key']>('30');
  const range = useMemo(() => rangeFor(RANGES.find((r) => r.key === rangeKey)!.days), [rangeKey]);
  const wallet = useMyWallet();
  const usage = useMyUsage(range.from, range.to);
  const [lastPurchase, setLastPurchase] = useState<PurchaseResult | null>(null);

  const w = wallet.data?.wallet;
  const walletSkeleton = wallet.isPending && !wallet.data;
  const usageSkeleton = usage.isPending && !usage.data;

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <button onClick={() => navigate('/org-settings')} className="text-sm text-primary hover:underline">
        &larr; Configurações da organização
      </button>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Créditos e uso</h1>
          <p className="text-sm text-muted-foreground">Saldo de créditos de IA da organização e o consumo por produto.</p>
        </div>
        {(wallet.isFetching && !!wallet.data) || (usage.isFetching && !!usage.data) ? (
          <span className="text-xs text-muted-foreground">Atualizando…</span>
        ) : null}
      </div>

      {wallet.error && !wallet.data ? (
        <ErrorState message={`Não foi possível carregar o saldo: ${wallet.error.message}`} />
      ) : (
        <StatTileRow>
          <StatTile icon={Wallet} label="Saldo" loading={walletSkeleton}
            value={w ? `${formatCredits(w.balance_credits)} créditos` : '—'}
            hint={w ? formatBrl(w.balance_brl) : undefined} />
          <StatTile icon={Coins} label="Consumido desde a última recarga" loading={walletSkeleton}
            value={w ? formatPct(w.consumed_pct) : '—'}
            hint={w?.mode ? MODE_LABEL[w.mode] : 'Sem carteira — uso não cobrado'} />
          <StatTile icon={Receipt} label="Uso no período" loading={usageSkeleton}
            value={usage.data ? `${formatCredits(usage.data.totals.credits)} créditos` : '—'}
            hint={usage.data ? formatBrl(usage.data.totals.brl) : undefined} />
          <StatTile icon={Cpu} label="Tokens no período" loading={usageSkeleton}
            value={usage.data ? formatTokens(usage.data.totals.tokens) : '—'} />
        </StatTileRow>
      )}

      {w?.blocked && (
        <div role="alert" className="rounded-lg border border-destructive bg-card p-3 text-sm text-destructive">
          Os créditos acabaram: as funcionalidades de IA estão bloqueadas até uma nova recarga.
        </div>
      )}

      {w?.mode !== 'byok' && (
        <section className="space-y-3 rounded-lg border border-border bg-card p-4">
          <h2 className="font-semibold text-foreground">Comprar créditos</h2>
          {walletSkeleton ? <Skeleton className="h-10 w-full" /> : wallet.data && (
            <BuyCredits gateways={wallet.data.gateways} unit={wallet.data.wallet.credit_unit_brl} onDone={setLastPurchase} />
          )}
          {lastPurchase && <PurchaseInstructions result={lastPurchase} />}
        </section>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold text-foreground">Uso por produto</h2>
          <Select aria-label="Período" value={rangeKey} onChange={(e) => setRangeKey(e.target.value as typeof rangeKey)}>
            {RANGES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </Select>
        </div>
        <ChartCard
          title="Créditos por dia"
          subtitle="Empilhado por produto"
          loading={usageSkeleton}
          error={usage.error && !usage.data ? usage.error.message : null}
          isEmpty={!!usage.data && usage.data.daily.length === 0}
          emptyMessage="Nenhum uso de IA no período."
        >
          {usage.data && (
            <BarChart
              data={usage.data.daily}
              xKey="day"
              series={usage.data.products.map((p) => ({ key: p, label: p }))}
              stacked
              valueFormatter={(v) => formatCredits(v)}
              xTickFormatter={(d) => d.slice(8, 10) + '/' + d.slice(5, 7)}
            />
          )}
        </ChartCard>
        {usageSkeleton ? (
          <TableSkeleton rows={4} columns={5} />
        ) : usage.error && !usage.data ? (
          <ErrorState message={`Não foi possível carregar o uso: ${usage.error.message}`} />
        ) : usage.data && usage.data.per_product.length === 0 ? (
          <EmptyState message="Nenhum uso de IA no período." />
        ) : usage.data ? (
          <UsageTable data={usage.data} />
        ) : null}
        {usage.data && usage.data.totals.pending_calls > 0 && (
          <p className="text-xs text-muted-foreground">
            {usage.data.totals.pending_calls} chamada(s) ainda não cobrada(s) — o débito acontece a cada minuto.
          </p>
        )}
      </section>

      {wallet.data && (wallet.data.entries.length > 0 || wallet.data.purchases.length > 0) && (
        <section className="space-y-2">
          <h2 className="font-semibold text-foreground">Movimentações</h2>
          <ul className="divide-y divide-border rounded-lg border border-border bg-card text-sm">
            {wallet.data.purchases.filter((p) => p.status !== 'paid').map((p) => (
              <li key={p.id} className="flex items-center justify-between px-3 py-2">
                <span>Compra de {formatCredits(p.credits)} créditos ({formatBrl(p.amount_cents / 100)})</span>
                <Badge variant={p.status === 'pending' ? 'muted' : 'outline'}>{p.status === 'pending' ? 'Aguardando pagamento' : p.status}</Badge>
              </li>
            ))}
            {wallet.data.entries.map((e) => (
              <li key={e.id} className="flex items-center justify-between px-3 py-2">
                <span>{KIND_LABEL[e.kind]}{e.reason ? ` — ${e.reason}` : ''}</span>
                <span className={e.credits < 0 ? 'text-destructive' : 'text-success'}>
                  {e.credits > 0 ? '+' : ''}{formatCredits(e.credits)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
