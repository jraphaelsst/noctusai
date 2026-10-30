/**
 * Admin "Créditos" — every org's AI credit wallet (platform admins; `CoreLayout` gates `/admin/*`,
 * the server enforces every call).
 *
 * Carteiras: balance + mode per org, grant dialog (credits OR US$, with a reason — the same ledger
 * path as a paid purchase), mode switch (pré-pago / pós-pago confiável / BYOK). Margem: usage
 * revenue vs provider cost per org → product. Preços: the versioned pricing formula (a new
 * version takes effect now; past versions are never edited).
 */
import { Fragment, useMemo, useState } from 'react';
import {
  Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, EmptyState, ErrorState, Field, Input, Select,
  StatTile, StatTileRow, TableSkeleton, Textarea,
} from '@noctusai/lib/design-system';
import {
  formatBrl, formatCredits, formatPct, MODE_LABEL, useAdminWallets, useCreatePricing, useGrantCredits,
  useMarginReport, usePricingVersions, useSetWalletMode, type AdminWalletRow, type PricingInput, type WalletMode,
} from '../../lib/credits';

type Tab = 'carteiras' | 'margem' | 'precos';
const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'carteiras', label: 'Carteiras' },
  { key: 'margem', label: 'Margem' },
  { key: 'precos', label: 'Preços' },
];

function GrantDialog({ initialOrgId, onClose }: { initialOrgId: string; onClose: () => void }) {
  const grant = useGrantCredits();
  const [orgId, setOrgId] = useState(initialOrgId);
  const [unit, setUnit] = useState<'usd' | 'credits'>('usd');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const valid = /^[0-9a-f-]{36}$/i.test(orgId.trim()) && Number(amount) > 0 && reason.trim().length >= 3;
  return (
    <Dialog open onClose={onClose} title="Conceder créditos">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          grant.mutate(
            { orgId: orgId.trim(), reason: reason.trim(), ...(unit === 'usd' ? { usd: amount } : { credits: amount }) },
            { onSuccess: onClose },
          );
        }}
      >
        <DialogHeader><h3 className="font-semibold text-foreground">Conceder créditos</h3></DialogHeader>
        <DialogBody>
          <div className="space-y-3">
            <Field label="Organização (id)">
              <Input value={orgId} onChange={(e) => setOrgId(e.target.value)} aria-label="Id da organização" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Unidade">
                <Select aria-label="Unidade" value={unit} onChange={(e) => setUnit(e.target.value as 'usd' | 'credits')}>
                  <option value="usd">US$</option>
                  <option value="credits">Créditos</option>
                </Select>
              </Field>
              <Field label="Quantidade">
                <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Quantidade" />
              </Field>
            </div>
            <Field label="Motivo">
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Motivo" rows={2} />
            </Field>
            <p className="text-xs text-muted-foreground">
              Em US$ o valor é convertido pela PTAX do dia ao preço de varejo do crédito (sem margem).
              A concessão segue o mesmo caminho de uma compra paga.
            </p>
            {grant.error && <p role="alert" className="text-sm text-destructive">{grant.error.message}</p>}
          </div>
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
          <Button type="submit" disabled={!valid || grant.isPending}>{grant.isPending ? 'Concedendo…' : 'Conceder'}</Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function ModeSelect({ row }: { row: AdminWalletRow }) {
  const setMode = useSetWalletMode();
  return (
    <div className="flex items-center gap-2">
      <Select
        aria-label={`Modo de ${row.org_nome ?? row.org_id}`}
        value={row.mode ?? 'prepaid'}
        disabled={setMode.isPending}
        onChange={(e) => setMode.mutate({ orgId: row.org_id, mode: e.target.value as WalletMode })}
      >
        {(Object.keys(MODE_LABEL) as WalletMode[]).map((m) => <option key={m} value={m}>{MODE_LABEL[m]}</option>)}
      </Select>
      {setMode.error && <span role="alert" className="text-xs text-destructive">{setMode.error.message}</span>}
    </div>
  );
}

function WalletsTab() {
  const { data, isPending, isFetching, error } = useAdminWallets();
  const [granting, setGranting] = useState<string | null>(null);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Button onClick={() => setGranting('')}>Conceder créditos</Button>
        {isFetching && !!data && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {isPending && !data ? (
        <TableSkeleton rows={5} columns={5} />
      ) : error && !data ? (
        <ErrorState message={`Não foi possível carregar as carteiras: ${error.message}`} />
      ) : data && data.length === 0 ? (
        <EmptyState message="Nenhuma organização tem carteira de créditos ainda. Uma concessão cria a carteira." />
      ) : data ? (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Organização</th>
                <th className="px-3 py-2">Modo</th>
                <th className="px-3 py-2 text-right">Saldo (créditos)</th>
                <th className="px-3 py-2 text-right">Saldo (R$)</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.org_id} className="border-t border-border">
                  <td className="px-3 py-2">
                    <div className="font-medium text-foreground">{row.org_nome ?? row.org_id}</div>
                    {row.blocked && <Badge variant="destructive">Bloqueada</Badge>}
                  </td>
                  <td className="px-3 py-2"><ModeSelect row={row} /></td>
                  <td className="px-3 py-2 text-right">{formatCredits(row.balance_credits)}</td>
                  <td className="px-3 py-2 text-right">{formatBrl(row.balance_brl)}</td>
                  <td className="px-3 py-2 text-right">
                    <Button size="sm" variant="outline" onClick={() => setGranting(row.org_id)}>Conceder</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {granting !== null && <GrantDialog initialOrgId={granting} onClose={() => setGranting(null)} />}
    </div>
  );
}

function MarginTab() {
  const range = useMemo(() => {
    const to = new Date();
    to.setUTCMinutes(0, 0, 0);
    return { from: new Date(to.getTime() - 30 * 86_400_000).toISOString(), to: to.toISOString() };
  }, []);
  const { data, isPending, error } = useMarginReport(range.from, range.to);
  if (isPending && !data) return <TableSkeleton rows={4} columns={5} />;
  if (error && !data) return <ErrorState message={`Não foi possível carregar a margem: ${error.message}`} />;
  if (!data) return null;
  return (
    <div className="space-y-4">
      <StatTileRow>
        <StatTile label="Receita de uso (30 dias)" value={formatBrl(data.totals.revenue_brl)} />
        <StatTile label="Custo dos provedores" value={formatBrl(data.totals.provider_cost_brl)} />
        <StatTile label="Margem bruta" value={formatPct(data.totals.gross_margin_pct)}
          hint={formatBrl(data.totals.gross_margin_brl)} />
        <StatTile label="Compras / concessões" value={formatBrl(data.totals.purchased_brl)}
          hint={`${formatBrl(data.totals.granted_brl)} concedidos`} />
      </StatTileRow>
      {data.per_org.length === 0 ? (
        <EmptyState message="Nenhum débito de uso no período." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Organização / produto</th>
                <th className="px-3 py-2 text-right">Receita</th>
                <th className="px-3 py-2 text-right">Custo</th>
                <th className="px-3 py-2 text-right">Margem</th>
                <th className="px-3 py-2 text-right">BYOK</th>
              </tr>
            </thead>
            <tbody>
              {data.per_org.map((o) => (
                <Fragment key={o.org_id}>
                  <tr className="border-t border-border font-medium">
                    <td className="px-3 py-2 font-mono text-xs">{o.org_id}</td>
                    <td className="px-3 py-2 text-right">{formatBrl(o.revenue_brl)}</td>
                    <td className="px-3 py-2 text-right">{formatBrl(o.provider_cost_brl)}</td>
                    <td className="px-3 py-2 text-right">{formatPct(o.gross_margin_pct)}</td>
                    <td className="px-3 py-2 text-right">{o.byok_calls}</td>
                  </tr>
                  {o.per_product.map((p) => (
                    <tr key={`${o.org_id}:${p.product}`} className="border-t border-border text-muted-foreground">
                      <td className="px-3 py-1.5 pl-8">{p.product}</td>
                      <td className="px-3 py-1.5 text-right">{formatBrl(p.revenue_brl)}</td>
                      <td className="px-3 py-1.5 text-right">{formatBrl(p.provider_cost_brl)}</td>
                      <td className="px-3 py-1.5 text-right">{formatPct(p.gross_margin_pct)}</td>
                      <td className="px-3 py-1.5 text-right">{p.byok_calls}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const PRICING_FIELDS: Array<{ key: keyof PricingInput; label: string }> = [
  { key: 'credit_unit_brl', label: 'Valor do crédito (R$)' },
  { key: 'margin', label: 'Markup (1.0 = 100%)' },
  { key: 'fx_buffer_brl', label: 'Folga de câmbio (R$/US$)' },
  { key: 'iof_rate', label: 'IOF' },
  { key: 'import_tax_rate', label: 'Imposto de importação' },
  { key: 'simples_rate', label: 'Simples Nacional' },
  { key: 'gateway_fee_rate', label: 'Taxa do gateway' },
];

function PricingTab() {
  const { data, isPending, error } = usePricingVersions();
  const create = useCreatePricing();
  const [draft, setDraft] = useState<PricingInput | null>(null);
  const current = data?.[0];
  const startDraft = () => current && setDraft({
    credit_unit_brl: String(current.credit_unit_brl), margin: String(current.margin),
    fx_buffer_brl: String(current.fx_buffer_brl), iof_rate: String(current.iof_rate),
    import_tax_rate: String(current.import_tax_rate), simples_rate: String(current.simples_rate),
    gateway_fee_rate: String(current.gateway_fee_rate), notes: '',
  });
  if (isPending && !data) return <TableSkeleton rows={3} columns={6} />;
  if (error && !data) return <ErrorState message={`Não foi possível carregar os preços: ${error.message}`} />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        preço = custo US$ × (PTAX + folga) × (1 + IOF + importação) ÷ (1 − Simples − gateway) × (1 + markup)
      </p>
      {draft ? (
        <form
          className="space-y-3 rounded-lg border border-border bg-card p-4"
          onSubmit={(e) => { e.preventDefault(); create.mutate(draft, { onSuccess: () => setDraft(null) }); }}
        >
          <p className="text-sm font-medium text-foreground">Rascunho — nova versão (não salva)</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {PRICING_FIELDS.map((f) => (
              <Field key={f.key} label={f.label}>
                <Input inputMode="decimal" aria-label={f.label} value={draft[f.key] ?? ''}
                  onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })} />
              </Field>
            ))}
          </div>
          <Field label="Notas">
            <Textarea aria-label="Notas" rows={2} value={draft.notes ?? ''} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
          </Field>
          {create.error && <p role="alert" className="text-sm text-destructive">{create.error.message}</p>}
          <div className="flex gap-2">
            <Button type="submit" disabled={create.isPending}>{create.isPending ? 'Salvando…' : 'Publicar versão'}</Button>
            <Button type="button" variant="outline" onClick={() => setDraft(null)}>Descartar</Button>
          </div>
        </form>
      ) : (
        <Button onClick={startDraft} disabled={!current}>Nova versão de preço</Button>
      )}
      {data && data.length === 0 ? (
        <EmptyState message="Nenhuma versão de preço — aplique a migração 093." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Versão</th>
                <th className="px-3 py-2 text-right">Crédito</th>
                <th className="px-3 py-2 text-right">Markup</th>
                <th className="px-3 py-2 text-right">Margem bruta</th>
                <th className="px-3 py-2">Vigente desde</th>
                <th className="px-3 py-2">Notas</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((v, i) => (
                <tr key={v.version} className="border-t border-border">
                  <td className="px-3 py-2">v{v.version} {i === 0 && <Badge>Vigente</Badge>}</td>
                  <td className="px-3 py-2 text-right">{formatBrl(v.credit_unit_brl)}</td>
                  <td className="px-3 py-2 text-right">{formatPct(v.margin)}</td>
                  <td className={`px-3 py-2 text-right ${v.gross_margin < 0.5 ? 'text-destructive' : ''}`}>{formatPct(v.gross_margin)}</td>
                  <td className="px-3 py-2">{v.effective_from ? new Date(v.effective_from).toLocaleString('pt-BR') : '—'}</td>
                  <td className="px-3 py-2 text-muted-foreground">{v.notes ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AdminCreditos() {
  const [tab, setTab] = useState<Tab>('carteiras');
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Créditos de IA</h1>
        <p className="text-sm text-muted-foreground">Carteiras pré-pagas por organização, margem de uso e tabela de preços.</p>
      </div>
      <div role="tablist" className="flex gap-2 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t.key ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'carteiras' && <WalletsTab />}
      {tab === 'margem' && <MarginTab />}
      {tab === 'precos' && <PricingTab />}
    </div>
  );
}
