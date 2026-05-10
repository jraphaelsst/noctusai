import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  TrendingUp,
  DollarSign,
  Wallet,
  Download,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  useAdminSummary,
  useAdminTransactions,
  useAdminCommissions,
  useAdminWallets,
  useAdminPayouts,
  useProcessPayout,
  useSaveCommission,
  useDeleteCommissionOverride,
} from '@/hooks/useAdminFinancials';
import {
  TRANSACTION_STATUS_CONFIG,
  PAYOUT_STATUS_CONFIG,
} from '@/types/financial';

// ── Owner type labels ──────────────────────────────────────────────

const OWNER_TYPE_LABELS: Record<string, string> = {
  patient: 'Paciente',
  therapist: 'Terapeuta',
  clinic: 'Clinica',
};

// ── Component ──────────────────────────────────────────────────────

export default function AdminFinancials() {
  const [txPage, setTxPage] = useState(1);
  const [payoutPage, setPayoutPage] = useState(1);
  const [txFilters, setTxFilters] = useState<Record<string, string>>({});
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideEntityId, setOverrideEntityId] = useState('');
  const [overrideEntityType, setOverrideEntityType] = useState('clinic');
  const [overrideRate, setOverrideRate] = useState('');
  const [editingGlobalRate, setEditingGlobalRate] = useState(false);
  const [globalRateInput, setGlobalRateInput] = useState('');

  const { data: summary } = useAdminSummary();
  const { data: txData } = useAdminTransactions(txFilters, txPage, 15);
  const { data: commData } = useAdminCommissions();
  const { data: wallets } = useAdminWallets();
  const { data: payoutsData } = useAdminPayouts(payoutPage, 10);
  const processPayout = useProcessPayout();
  const saveComm = useSaveCommission();
  const deleteOverride = useDeleteCommissionOverride();

  const transactions = txData?.data ?? [];
  const txTotal = txData?.total ?? 0;
  const payouts = payoutsData?.data ?? [];
  const payoutsTotal = payoutsData?.total ?? 0;
  const overrides = commData?.overrides ?? [];

  function handleSaveGlobalRate() {
    const rate = parseFloat(globalRateInput);
    if (isNaN(rate) || rate < 0 || rate > 100) return;
    saveComm.mutate({ global_rate_pct: rate }, {
      onSuccess: () => setEditingGlobalRate(false),
    });
  }

  function handleAddOverride() {
    const rate = parseFloat(overrideRate);
    if (!overrideEntityId || isNaN(rate)) return;
    saveComm.mutate(
      { override: { entity_id: overrideEntityId, entity_type: overrideEntityType, rate_pct: rate } },
      { onSuccess: () => { setOverrideOpen(false); setOverrideEntityId(''); setOverrideRate(''); } },
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Financeiro da Plataforma</h1>
        <p className="text-muted-foreground">Visao global de transacoes, comissoes e payouts</p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Receita Total</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(summary?.total_revenue ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Comissoes da Plataforma</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(summary?.platform_fees ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Payouts Processados</CardTitle>
            <Download className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(summary?.payouts_completed ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Payouts Pendentes</CardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(summary?.payouts_pending ?? 0)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Global ledger */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Ledger Global</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <div className="w-40">
              <Select
                value={txFilters.status || 'all'}
                onValueChange={(v) => {
                  setTxFilters((f) => {
                    const next = { ...f };
                    if (v === 'all') delete next.status;
                    else next.status = v;
                    return next;
                  });
                  setTxPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="pre_authorized">Pre-autorizado</SelectItem>
                  <SelectItem value="captured">Capturado</SelectItem>
                  <SelectItem value="refunded">Reembolsado</SelectItem>
                  <SelectItem value="failed">Falhou</SelectItem>
                  <SelectItem value="released">Liberado</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Input
              className="w-48"
              placeholder="Data inicio (YYYY-MM-DD)"
              value={txFilters.date_start ?? ''}
              onChange={(e) => { setTxFilters((f) => ({ ...f, date_start: e.target.value })); setTxPage(1); }}
            />
            <Input
              className="w-48"
              placeholder="Data fim (YYYY-MM-DD)"
              value={txFilters.date_end ?? ''}
              onChange={(e) => { setTxFilters((f) => ({ ...f, date_end: e.target.value })); setTxPage(1); }}
            />
          </div>

          {transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma transacao encontrada.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 pr-3">Data</th>
                      <th className="pb-2 pr-3">Paciente</th>
                      <th className="pb-2 pr-3">Terapeuta</th>
                      <th className="pb-2 pr-3">Clinica</th>
                      <th className="pb-2 pr-3 text-right">Bruto</th>
                      <th className="pb-2 pr-3 text-right">Taxa Plataforma</th>
                      <th className="pb-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((tx) => {
                      const cfg = TRANSACTION_STATUS_CONFIG[tx.status];
                      return (
                        <tr key={tx.id} className="border-b last:border-0">
                          <td className="py-3 pr-3 whitespace-nowrap">{formatDate(tx.created_at)}</td>
                          <td className="py-3 pr-3">{tx.patient_id}</td>
                          <td className="py-3 pr-3">{tx.therapist_id}</td>
                          <td className="py-3 pr-3">{tx.clinic_id ?? '-'}</td>
                          <td className="py-3 pr-3 text-right">{formatCurrency(tx.gross_amount)}</td>
                          <td className="py-3 pr-3 text-right text-muted-foreground">
                            {formatCurrency(tx.platform_fee_amount)}
                          </td>
                          <td className="py-3">
                            <Badge variant={cfg?.variant ?? 'outline'}>{cfg?.label ?? tx.status}</Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {txTotal > 15 && (
                <div className="flex justify-center gap-2">
                  <Button variant="outline" size="sm" disabled={txPage <= 1} onClick={() => setTxPage((p) => p - 1)}>Anterior</Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {txPage} de {Math.ceil(txTotal / 15)}
                  </span>
                  <Button variant="outline" size="sm" disabled={txPage >= Math.ceil(txTotal / 15)} onClick={() => setTxPage((p) => p + 1)}>Proxima</Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Commission management */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Gestao de Comissoes</CardTitle>
          <Button size="sm" onClick={() => setOverrideOpen(true)}>Adicionar Override</Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium">Taxa Global:</span>
            {editingGlobalRate ? (
              <div className="flex items-center gap-2">
                <Input
                  className="w-20"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={globalRateInput}
                  onChange={(e) => setGlobalRateInput(e.target.value)}
                />
                <span className="text-sm">%</span>
                <Button size="sm" onClick={handleSaveGlobalRate} disabled={saveComm.isPending}>Salvar</Button>
                <Button size="sm" variant="ghost" onClick={() => setEditingGlobalRate(false)}>Cancelar</Button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold">{commData?.global_rate_pct ?? 0}%</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => { setGlobalRateInput(String(commData?.global_rate_pct ?? 0)); setEditingGlobalRate(true); }}
                >
                  Editar
                </Button>
              </div>
            )}
          </div>

          {overrides.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Entidade</th>
                    <th className="pb-2 pr-4">Tipo</th>
                    <th className="pb-2 pr-4 text-right">Taxa</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {overrides.map((o) => (
                    <tr key={o.id} className="border-b last:border-0">
                      <td className="py-3 pr-4">{o.entity_name}</td>
                      <td className="py-3 pr-4">
                        <Badge variant="outline">{o.entity_type === 'clinic' ? 'Clinica' : 'Terapeuta'}</Badge>
                      </td>
                      <td className="py-3 pr-4 text-right font-medium">{o.rate_pct}%</td>
                      <td className="py-3 text-right">
                        <Button variant="ghost" size="sm" className="text-destructive" onClick={() => deleteOverride.mutate(o.id)}>
                          Remover
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Override dialog */}
      <Dialog open={overrideOpen} onOpenChange={setOverrideOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar Override de Comissao</DialogTitle>
            <DialogDescription>Defina uma taxa personalizada para uma clinica ou terapeuta</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Tipo</Label>
              <Select value={overrideEntityType} onValueChange={setOverrideEntityType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="clinic">Clinica</SelectItem>
                  <SelectItem value="therapist">Terapeuta</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>ID da Entidade</Label>
              <Input placeholder="UUID" value={overrideEntityId} onChange={(e) => setOverrideEntityId(e.target.value)} />
            </div>
            <div>
              <Label>Taxa (%)</Label>
              <Input type="number" min="0" max="100" step="0.1" value={overrideRate} onChange={(e) => setOverrideRate(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleAddOverride} disabled={saveComm.isPending || !overrideEntityId || !overrideRate}>
              {saveComm.isPending ? 'Salvando...' : 'Adicionar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Wallets overview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Visao Geral de Carteiras</CardTitle>
        </CardHeader>
        <CardContent>
          {!wallets || wallets.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma carteira encontrada.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Nome</th>
                    <th className="pb-2 pr-4">Tipo</th>
                    <th className="pb-2 text-right">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {wallets.map((w) => (
                    <tr key={w.id} className="border-b last:border-0">
                      <td className="py-3 pr-4">{w.owner_name}</td>
                      <td className="py-3 pr-4">
                        <Badge variant="outline">{OWNER_TYPE_LABELS[w.owner_type] ?? w.owner_type}</Badge>
                      </td>
                      <td className="py-3 text-right font-medium">{formatCurrency(w.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Payouts */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Payouts</CardTitle>
        </CardHeader>
        <CardContent>
          {payouts.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum payout encontrado.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 pr-3">Data</th>
                      <th className="pb-2 pr-3">Destinatario</th>
                      <th className="pb-2 pr-3">Tipo</th>
                      <th className="pb-2 pr-3 text-right">Valor</th>
                      <th className="pb-2 pr-3 text-right">Liquido</th>
                      <th className="pb-2 pr-3">Status</th>
                      <th className="pb-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {payouts.map((p) => {
                      const cfg = PAYOUT_STATUS_CONFIG[p.status];
                      return (
                        <tr key={p.id} className="border-b last:border-0">
                          <td className="py-3 pr-3 whitespace-nowrap">{formatDate(p.requested_at)}</td>
                          <td className="py-3 pr-3">{p.recipient_id}</td>
                          <td className="py-3 pr-3">
                            <Badge variant="outline">{OWNER_TYPE_LABELS[p.recipient_type] ?? p.recipient_type}</Badge>
                          </td>
                          <td className="py-3 pr-3 text-right">{formatCurrency(p.amount)}</td>
                          <td className="py-3 pr-3 text-right font-medium">{formatCurrency(p.net_amount)}</td>
                          <td className="py-3 pr-3">
                            <Badge variant={cfg?.variant ?? 'outline'}>{cfg?.label ?? p.status}</Badge>
                          </td>
                          <td className="py-3 text-right">
                            {p.status === 'pending' && (
                              <Button
                                size="sm"
                                onClick={() => processPayout.mutate(p.id)}
                                disabled={processPayout.isPending}
                              >
                                Processar
                              </Button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {payoutsTotal > 10 && (
                <div className="flex justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={payoutPage <= 1} onClick={() => setPayoutPage((p) => p - 1)}>Anterior</Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {payoutPage} de {Math.ceil(payoutsTotal / 10)}
                  </span>
                  <Button variant="outline" size="sm" disabled={payoutPage >= Math.ceil(payoutsTotal / 10)} onClick={() => setPayoutPage((p) => p + 1)}>Proxima</Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
