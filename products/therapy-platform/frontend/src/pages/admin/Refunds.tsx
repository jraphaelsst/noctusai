import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { RefreshCw } from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import { useRefundRequests, useReviewRefund } from '@/hooks/useRefunds';
import { REFUND_STATUS_CONFIG } from '@/types/financial';
import type { RefundRequest } from '@/types/financial';

export default function AdminRefunds() {
  const [page, setPage] = useState(1);
  const [denyDialogOpen, setDenyDialogOpen] = useState(false);
  const [selectedRefund, setSelectedRefund] = useState<RefundRequest | null>(null);
  const [denyReason, setDenyReason] = useState('');

  const { data: refundsData } = useRefundRequests(page, 20);
  const reviewMut = useReviewRefund();

  const allRefunds = refundsData?.data ?? [];
  const total = refundsData?.total ?? 0;
  const pendingRefunds = allRefunds.filter((r) => r.status === 'pending');
  const historyRefunds = allRefunds.filter((r) => r.status !== 'pending');

  function handleApprove(refund: RefundRequest) {
    reviewMut.mutate({ id: refund.id, status: 'approved' });
  }

  function openDenyDialog(refund: RefundRequest) {
    setSelectedRefund(refund);
    setDenyReason('');
    setDenyDialogOpen(true);
  }

  function handleDeny() {
    if (!selectedRefund || !denyReason) return;
    reviewMut.mutate(
      { id: selectedRefund.id, status: 'denied', review_response: denyReason },
      { onSuccess: () => { setDenyDialogOpen(false); setSelectedRefund(null); } },
    );
  }

  function RefundRow({ refund, showActions }: { refund: RefundRequest; showActions: boolean }) {
    const cfg = REFUND_STATUS_CONFIG[refund.status];
    return (
      <div className="rounded-lg border p-4 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{refund.patient_name ?? refund.patient_id}</span>
              <Badge variant={cfg?.variant ?? 'outline'}>{cfg?.label ?? refund.status}</Badge>
            </div>
            {refund.therapist_name && (
              <p className="text-sm text-muted-foreground">Terapeuta: {refund.therapist_name}</p>
            )}
            {refund.session_date && (
              <p className="text-sm text-muted-foreground">Sessao: {formatDate(refund.session_date)}</p>
            )}
          </div>
          <div className="text-right">
            <p className="text-lg font-bold">{formatCurrency(refund.refund_amount)}</p>
            <p className="text-xs text-muted-foreground">{formatDate(refund.created_at)}</p>
          </div>
        </div>

        <div className="rounded-md bg-muted p-3">
          <p className="text-sm font-medium mb-1">Motivo:</p>
          <p className="text-sm text-muted-foreground">{refund.reason}</p>
        </div>

        {refund.review_response && (
          <div className="rounded-md bg-muted p-3">
            <p className="text-sm font-medium mb-1">Resposta:</p>
            <p className="text-sm text-muted-foreground">{refund.review_response}</p>
          </div>
        )}

        {showActions && refund.status === 'pending' && (
          <div className="flex gap-2 justify-end">
            <Button
              size="sm"
              onClick={() => handleApprove(refund)}
              disabled={reviewMut.isPending}
            >
              Aprovar
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => openDenyDialog(refund)}
              disabled={reviewMut.isPending}
            >
              Negar
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Reembolsos</h1>
        <p className="text-muted-foreground">Gerencie solicitacoes de reembolso dos pacientes</p>
      </div>

      {/* Feature status */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-3">
            <RefreshCw className="h-5 w-5 text-primary" />
            <div>
              <p className="font-medium">Sistema de Reembolsos</p>
              <p className="text-sm text-muted-foreground">
                Ativo — solicitacoes de reembolso estao habilitadas para pacientes.
                Para desabilitar, acesse Configuracoes da Plataforma.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="pendentes">
        <TabsList>
          <TabsTrigger value="pendentes">
            Pendentes {pendingRefunds.length > 0 && `(${pendingRefunds.length})`}
          </TabsTrigger>
          <TabsTrigger value="historico">Historico</TabsTrigger>
        </TabsList>

        <TabsContent value="pendentes" className="space-y-3 mt-4">
          {pendingRefunds.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground text-center">
                  Nenhuma solicitacao de reembolso pendente.
                </p>
              </CardContent>
            </Card>
          ) : (
            pendingRefunds.map((r) => (
              <RefundRow key={r.id} refund={r} showActions />
            ))
          )}
        </TabsContent>

        <TabsContent value="historico" className="space-y-3 mt-4">
          {historyRefunds.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground text-center">
                  Nenhum reembolso processado ainda.
                </p>
              </CardContent>
            </Card>
          ) : (
            historyRefunds.map((r) => (
              <RefundRow key={r.id} refund={r} showActions={false} />
            ))
          )}
        </TabsContent>
      </Tabs>

      {total > 20 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </Button>
          <span className="text-sm text-muted-foreground flex items-center px-2">
            Pagina {page} de {Math.ceil(total / 20)}
          </span>
          <Button variant="outline" size="sm" disabled={page >= Math.ceil(total / 20)} onClick={() => setPage((p) => p + 1)}>
            Proxima
          </Button>
        </div>
      )}

      {/* Deny reason dialog */}
      <Dialog open={denyDialogOpen} onOpenChange={setDenyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Negar Reembolso</DialogTitle>
            <DialogDescription>
              Informe o motivo da negacao para {selectedRefund?.patient_name ?? 'o paciente'}
            </DialogDescription>
          </DialogHeader>
          <div>
            <Label>Motivo da Negacao</Label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 min-h-[100px] mt-1"
              placeholder="Descreva o motivo..."
              value={denyReason}
              onChange={(e) => setDenyReason(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDenyDialogOpen(false)}>Cancelar</Button>
            <Button
              variant="destructive"
              onClick={handleDeny}
              disabled={reviewMut.isPending || !denyReason}
            >
              {reviewMut.isPending ? 'Negando...' : 'Confirmar Negacao'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
