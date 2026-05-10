import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  Wallet,
  TrendingUp,
  DollarSign,
  ArrowUpRight,
  RefreshCw,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import { useWallet, useWalletMovements, useWithdraw } from '@/hooks/useWallet';
import { useTransactions } from '@/hooks/useTransactions';
import { TRANSACTION_STATUS_CONFIG, MOVEMENT_TYPE_LABELS } from '@/types/financial';

export default function TherapistFinancials() {
  const [txPage, setTxPage] = useState(1);
  const [movPage, setMovPage] = useState(1);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState('');

  const { data: wallet } = useWallet();
  const { data: txData } = useTransactions(undefined, txPage, 10);
  const { data: movData } = useWalletMovements(movPage, 10);
  const withdrawMut = useWithdraw();

  const transactions = txData?.data ?? [];
  const txTotal = txData?.total ?? 0;
  const movements = movData?.data ?? [];
  const movTotal = movData?.total ?? 0;

  const totalReceita = transactions.reduce((acc, tx) => acc + tx.therapist_share_amount, 0);
  const sessoesPagas = transactions.filter((tx) => tx.status === 'captured' || tx.status === 'released').length;

  const withdrawAmountNum = parseFloat(withdrawAmount) || 0;
  const withdrawFeePct = 2.5;
  const withdrawFee = withdrawAmountNum * (withdrawFeePct / 100);
  const withdrawNet = withdrawAmountNum - withdrawFee;

  function handleWithdraw() {
    if (withdrawAmountNum < 10) return;
    withdrawMut.mutate({ amount: withdrawAmountNum }, {
      onSuccess: () => {
        setWithdrawOpen(false);
        setWithdrawAmount('');
      },
    });
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Financeiro</h1>
        <p className="text-muted-foreground">Acompanhe sua receita e movimentacoes</p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Saldo Disponivel</CardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(wallet?.balance ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Receita Total</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(totalReceita)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Sessoes Pagas</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{sessoesPagas}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Recorrentes Ativos</CardTitle>
            <RefreshCw className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">-</p>
          </CardContent>
        </Card>
      </div>

      {/* Withdrawal section */}
      <div className="flex justify-end">
        <Button onClick={() => setWithdrawOpen(true)}>
          <ArrowUpRight className="h-4 w-4 mr-1" />
          Solicitar Saque
        </Button>
        <Dialog open={withdrawOpen} onOpenChange={setWithdrawOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Solicitar Saque</DialogTitle>
              <DialogDescription>Minimo de R$ 10,00 por saque</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Valor (R$)</Label>
                <Input
                  type="number"
                  min="10"
                  step="0.01"
                  placeholder="0,00"
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                />
              </div>
              {withdrawAmountNum >= 10 && (
                <div className="rounded-md bg-muted p-3 text-sm space-y-1">
                  <div className="flex justify-between">
                    <span>Valor solicitado</span>
                    <span>{formatCurrency(withdrawAmountNum)}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Taxa ({withdrawFeePct}%)</span>
                    <span>- {formatCurrency(withdrawFee)}</span>
                  </div>
                  <div className="flex justify-between font-semibold border-t pt-1">
                    <span>Valor liquido</span>
                    <span>{formatCurrency(withdrawNet)}</span>
                  </div>
                </div>
              )}
            </div>
            <DialogFooter>
              <Button
                onClick={handleWithdraw}
                disabled={withdrawMut.isPending || withdrawAmountNum < 10}
              >
                {withdrawMut.isPending ? 'Processando...' : 'Solicitar Saque'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Statement table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Extrato de Sessoes</CardTitle>
        </CardHeader>
        <CardContent>
          {transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma transacao encontrada.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 pr-4">Data</th>
                      <th className="pb-2 pr-4">Paciente</th>
                      <th className="pb-2 pr-4 text-right">Bruto</th>
                      <th className="pb-2 pr-4 text-right">Plataforma</th>
                      <th className="pb-2 pr-4 text-right">Clinica</th>
                      <th className="pb-2 pr-4 text-right">Liquido</th>
                      <th className="pb-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((tx) => {
                      const statusCfg = TRANSACTION_STATUS_CONFIG[tx.status];
                      return (
                        <tr key={tx.id} className="border-b last:border-0">
                          <td className="py-3 pr-4 whitespace-nowrap">{formatDate(tx.created_at)}</td>
                          <td className="py-3 pr-4">{tx.patient_id}</td>
                          <td className="py-3 pr-4 text-right">{formatCurrency(tx.gross_amount)}</td>
                          <td className="py-3 pr-4 text-right text-muted-foreground">
                            {tx.platform_fee_pct}% ({formatCurrency(tx.platform_fee_amount)})
                          </td>
                          <td className="py-3 pr-4 text-right text-muted-foreground">
                            {tx.clinic_commission_pct != null
                              ? `${tx.clinic_commission_pct}% (${formatCurrency(tx.clinic_share_amount ?? 0)})`
                              : '-'}
                          </td>
                          <td className="py-3 pr-4 text-right font-medium">
                            {formatCurrency(tx.therapist_share_amount)}
                          </td>
                          <td className="py-3">
                            <Badge variant={statusCfg?.variant ?? 'outline'}>
                              {statusCfg?.label ?? tx.status}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {txTotal > 10 && (
                <div className="flex justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={txPage <= 1} onClick={() => setTxPage((p) => p - 1)}>
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {txPage} de {Math.ceil(txTotal / 10)}
                  </span>
                  <Button variant="outline" size="sm" disabled={txPage >= Math.ceil(txTotal / 10)} onClick={() => setTxPage((p) => p + 1)}>
                    Proxima
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Movement history */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Historico de Movimentacoes</CardTitle>
        </CardHeader>
        <CardContent>
          {movements.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma movimentacao encontrada.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 pr-4">Data</th>
                      <th className="pb-2 pr-4">Tipo</th>
                      <th className="pb-2 pr-4 text-right">Valor</th>
                      <th className="pb-2">Descricao</th>
                    </tr>
                  </thead>
                  <tbody>
                    {movements.map((m) => (
                      <tr key={m.id} className="border-b last:border-0">
                        <td className="py-3 pr-4 whitespace-nowrap">{formatDate(m.created_at)}</td>
                        <td className="py-3 pr-4">
                          <Badge variant="outline">
                            {MOVEMENT_TYPE_LABELS[m.reference_type] ?? m.reference_type}
                          </Badge>
                        </td>
                        <td className={`py-3 pr-4 text-right font-medium ${m.type === 'credit' ? 'text-green-600' : 'text-red-600'}`}>
                          {m.type === 'credit' ? '+' : '-'} {formatCurrency(m.amount)}
                        </td>
                        <td className="py-3 text-muted-foreground">{m.description ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {movTotal > 10 && (
                <div className="flex justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={movPage <= 1} onClick={() => setMovPage((p) => p - 1)}>
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {movPage} de {Math.ceil(movTotal / 10)}
                  </span>
                  <Button variant="outline" size="sm" disabled={movPage >= Math.ceil(movTotal / 10)} onClick={() => setMovPage((p) => p + 1)}>
                    Proxima
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
