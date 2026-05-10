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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@noctusai/seed/components/ui/select';
import {
  Wallet,
  TrendingUp,
  DollarSign,
  Users,
  ArrowUpRight,
  ArrowDownLeft,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import { useWallet, useWithdraw } from '@/hooks/useWallet';
import { useClinicFinancials, useClinicTransfers, useCreateClinicTransfer } from '@/hooks/useClinicFinancials';

export default function ClinicFinancials() {
  const [transferOpen, setTransferOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [transferTherapist, setTransferTherapist] = useState('');
  const [transferAmount, setTransferAmount] = useState('');
  const [transferReason, setTransferReason] = useState('');
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [transferPage, setTransferPage] = useState(1);

  const { data: wallet } = useWallet();
  const { data: financials } = useClinicFinancials();
  const { data: transfersData } = useClinicTransfers(transferPage, 10);
  const createTransfer = useCreateClinicTransfer();
  const withdrawMut = useWithdraw();

  const transfers = transfersData?.data ?? [];
  const transfersTotal = transfersData?.total ?? 0;
  const breakdown = financials?.therapist_breakdown ?? [];

  const withdrawAmountNum = parseFloat(withdrawAmount) || 0;
  const withdrawFeePct = 2.5;
  const withdrawFee = withdrawAmountNum * (withdrawFeePct / 100);
  const withdrawNet = withdrawAmountNum - withdrawFee;

  function handleTransfer() {
    const amount = parseFloat(transferAmount);
    if (!transferTherapist || !amount || amount <= 0 || !transferReason) return;
    createTransfer.mutate(
      { therapist_id: transferTherapist, amount, reason: transferReason },
      {
        onSuccess: () => {
          setTransferOpen(false);
          setTransferTherapist('');
          setTransferAmount('');
          setTransferReason('');
        },
      },
    );
  }

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
        <h1 className="text-2xl font-bold">Financeiro da Clinica</h1>
        <p className="text-muted-foreground">Visao geral de receita, comissoes e terapeutas</p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Receita Total</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(financials?.total_revenue ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Comissao da Plataforma</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(financials?.platform_fees ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Saldo da Clinica</CardTitle>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{formatCurrency(financials?.clinic_balance ?? 0)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Terapeutas</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{financials?.total_therapists ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Per-therapist breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Detalhamento por Terapeuta</CardTitle>
        </CardHeader>
        <CardContent>
          {breakdown.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum terapeuta vinculado.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4">Terapeuta</th>
                    <th className="pb-2 pr-4 text-right">Sessoes</th>
                    <th className="pb-2 pr-4 text-right">Receita Bruta</th>
                    <th className="pb-2 pr-4 text-right">Comissao Clinica</th>
                    <th className="pb-2 pr-4 text-right">Parte Clinica</th>
                    <th className="pb-2 pr-4 text-right">Parte Terapeuta</th>
                    <th className="pb-2">Origem</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.map((t) => (
                    <tr key={t.therapist_id} className="border-b last:border-0">
                      <td className="py-3 pr-4 font-medium">{t.therapist_name}</td>
                      <td className="py-3 pr-4 text-right">{t.sessions_count}</td>
                      <td className="py-3 pr-4 text-right">{formatCurrency(t.gross_revenue)}</td>
                      <td className="py-3 pr-4 text-right text-muted-foreground">{t.clinic_commission_pct}%</td>
                      <td className="py-3 pr-4 text-right">{formatCurrency(t.clinic_share)}</td>
                      <td className="py-3 pr-4 text-right">{formatCurrency(t.therapist_share)}</td>
                      <td className="py-3">
                        <Badge variant="outline">
                          {t.patient_origin === 'clinic_sourced' ? 'Clinica' : 'Terapeuta'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Wallet & actions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Carteira da Clinica</CardTitle>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => setTransferOpen(true)}>
              <ArrowDownLeft className="h-4 w-4 mr-1" />
              Transferir para Terapeuta
            </Button>
            <Button size="sm" variant="outline" onClick={() => setWithdrawOpen(true)}>
              <ArrowUpRight className="h-4 w-4 mr-1" />
              Solicitar Saque
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 mb-6">
            <div className="rounded-full bg-primary/10 p-3">
              <Wallet className="h-6 w-6 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Saldo Disponivel</p>
              <p className="text-2xl font-bold">{formatCurrency(wallet?.balance ?? 0)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Transfer dialog */}
      <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Transferir para Terapeuta</DialogTitle>
            <DialogDescription>Transferencia voluntaria do saldo da clinica</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Terapeuta</Label>
              <Select value={transferTherapist} onValueChange={setTransferTherapist}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione o terapeuta" />
                </SelectTrigger>
                <SelectContent>
                  {breakdown.map((t) => (
                    <SelectItem key={t.therapist_id} value={t.therapist_id}>
                      {t.therapist_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Valor (R$)</Label>
              <Input
                type="number"
                min="1"
                step="0.01"
                placeholder="0,00"
                value={transferAmount}
                onChange={(e) => setTransferAmount(e.target.value)}
              />
            </div>
            <div>
              <Label>Motivo</Label>
              <textarea
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 min-h-[80px]"
                placeholder="Descreva o motivo da transferencia"
                value={transferReason}
                onChange={(e) => setTransferReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={handleTransfer}
              disabled={createTransfer.isPending || !transferTherapist || !transferAmount || !transferReason}
            >
              {createTransfer.isPending ? 'Transferindo...' : 'Transferir'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Withdraw dialog */}
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

      {/* Transfer history */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Historico de Transferencias</CardTitle>
        </CardHeader>
        <CardContent>
          {transfers.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma transferencia realizada.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 pr-4">Data</th>
                      <th className="pb-2 pr-4">Terapeuta</th>
                      <th className="pb-2 pr-4 text-right">Valor</th>
                      <th className="pb-2">Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transfers.map((t) => (
                      <tr key={t.id} className="border-b last:border-0">
                        <td className="py-3 pr-4 whitespace-nowrap">{formatDate(t.created_at)}</td>
                        <td className="py-3 pr-4">{t.therapist_name ?? t.therapist_id}</td>
                        <td className="py-3 pr-4 text-right font-medium">{formatCurrency(t.amount)}</td>
                        <td className="py-3 text-muted-foreground">{t.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {transfersTotal > 10 && (
                <div className="flex justify-center gap-2 mt-4">
                  <Button variant="outline" size="sm" disabled={transferPage <= 1} onClick={() => setTransferPage((p) => p - 1)}>
                    Anterior
                  </Button>
                  <span className="text-sm text-muted-foreground flex items-center px-2">
                    Pagina {transferPage} de {Math.ceil(transfersTotal / 10)}
                  </span>
                  <Button variant="outline" size="sm" disabled={transferPage >= Math.ceil(transfersTotal / 10)} onClick={() => setTransferPage((p) => p + 1)}>
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
