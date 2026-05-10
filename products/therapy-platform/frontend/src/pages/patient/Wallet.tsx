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
  DialogTrigger,
} from '@noctusai/seed/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import { Wallet as WalletIcon, ArrowUpRight, ArrowDownLeft, CreditCard } from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import { useWallet, useWalletMovements, useTopUp, useWithdraw } from '@/hooks/useWallet';
import { useTransactions } from '@/hooks/useTransactions';
import { MOVEMENT_TYPE_LABELS, TRANSACTION_STATUS_CONFIG } from '@/types/financial';

export default function PatientWallet() {
  const [movPage, setMovPage] = useState(1);
  const [txPage, setTxPage] = useState(1);
  const [topUpOpen, setTopUpOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [topUpAmount, setTopUpAmount] = useState('');
  const [topUpMethod, setTopUpMethod] = useState('card');
  const [withdrawAmount, setWithdrawAmount] = useState('');

  const { data: wallet, isLoading: walletLoading } = useWallet();
  const { data: movementsData } = useWalletMovements(movPage, 10);
  const { data: txData } = useTransactions(undefined, txPage, 10);
  const topUp = useTopUp();
  const withdraw = useWithdraw();

  const movements = movementsData?.data ?? [];
  const movTotal = movementsData?.total ?? 0;
  const transactions = txData?.data ?? [];
  const txTotal = txData?.total ?? 0;

  function handleTopUp() {
    const amount = parseFloat(topUpAmount);
    if (!amount || amount <= 0) return;
    topUp.mutate({ amount, method: topUpMethod }, {
      onSuccess: () => {
        setTopUpOpen(false);
        setTopUpAmount('');
      },
    });
  }

  function handleWithdraw() {
    const amount = parseFloat(withdrawAmount);
    if (!amount || amount < 10) return;
    withdraw.mutate({ amount }, {
      onSuccess: () => {
        setWithdrawOpen(false);
        setWithdrawAmount('');
      },
    });
  }

  const withdrawAmountNum = parseFloat(withdrawAmount) || 0;
  const withdrawFeePct = 2.5;
  const withdrawFee = withdrawAmountNum * (withdrawFeePct / 100);
  const withdrawNet = withdrawAmountNum - withdrawFee;

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Carteira</h1>
        <p className="text-muted-foreground">Gerencie seu saldo e movimentacoes</p>
      </div>

      {/* Balance card */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="rounded-full bg-primary/10 p-3">
                <WalletIcon className="h-8 w-8 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Saldo Disponivel</p>
                <p className="text-3xl font-bold">
                  {walletLoading ? '...' : formatCurrency(wallet?.balance ?? 0)}
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <Dialog open={topUpOpen} onOpenChange={setTopUpOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <ArrowDownLeft className="h-4 w-4 mr-1" />
                    Adicionar Creditos
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Adicionar Creditos</DialogTitle>
                    <DialogDescription>Insira o valor e selecione o metodo de pagamento</DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4">
                    <div>
                      <Label>Valor (R$)</Label>
                      <Input
                        type="number"
                        min="1"
                        step="0.01"
                        placeholder="0,00"
                        value={topUpAmount}
                        onChange={(e) => setTopUpAmount(e.target.value)}
                      />
                    </div>
                    <div>
                      <Label>Metodo de Pagamento</Label>
                      <Select value={topUpMethod} onValueChange={setTopUpMethod}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="card">Cartao de Credito</SelectItem>
                          <SelectItem value="pix">PIX</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button
                      onClick={handleTopUp}
                      disabled={topUp.isPending || !topUpAmount || parseFloat(topUpAmount) <= 0}
                    >
                      {topUp.isPending ? 'Processando...' : 'Adicionar'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              <Dialog open={withdrawOpen} onOpenChange={setWithdrawOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline">
                    <ArrowUpRight className="h-4 w-4 mr-1" />
                    Sacar
                  </Button>
                </DialogTrigger>
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
                      disabled={withdraw.isPending || withdrawAmountNum < 10}
                    >
                      {withdraw.isPending ? 'Processando...' : 'Solicitar Saque'}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>
          </div>
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
                        <td className={`py-3 pr-4 text-right font-medium whitespace-nowrap ${m.type === 'credit' ? 'text-green-600' : 'text-red-600'}`}>
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
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={movPage <= 1}
                    onClick={() => setMovPage((p) => p - 1)}
                  >
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {movPage} de {Math.ceil(movTotal / 10)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={movPage >= Math.ceil(movTotal / 10)}
                    onClick={() => setMovPage((p) => p + 1)}
                  >
                    Proxima
                  </Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Transactions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <CreditCard className="h-5 w-5" />
            Transacoes de Sessoes
          </CardTitle>
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
                      <th className="pb-2 pr-4">Terapeuta</th>
                      <th className="pb-2 pr-4 text-right">Valor</th>
                      <th className="pb-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((tx) => {
                      const statusCfg = TRANSACTION_STATUS_CONFIG[tx.status];
                      return (
                        <tr key={tx.id} className="border-b last:border-0">
                          <td className="py-3 pr-4 whitespace-nowrap">{formatDate(tx.created_at)}</td>
                          <td className="py-3 pr-4">{tx.therapist_id}</td>
                          <td className="py-3 pr-4 text-right font-medium">{formatCurrency(tx.gross_amount)}</td>
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
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={txPage <= 1}
                    onClick={() => setTxPage((p) => p - 1)}
                  >
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {txPage} de {Math.ceil(txTotal / 10)}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={txPage >= Math.ceil(txTotal / 10)}
                    onClick={() => setTxPage((p) => p + 1)}
                  >
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
