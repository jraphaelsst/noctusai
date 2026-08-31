import { useState } from 'react';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { useParcelas, useGerarParcelas, useUpdateParcela } from '@/hooks/useContratos';
import { formatCurrency, formatDate } from '@/lib/utils';
import { StatusParcela } from '@/types/contratos';
import { Plus, CheckCircle } from 'lucide-react';

const STATUS_PARCELA: Record<StatusParcela, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  pago: { label: 'Pago', variant: 'default' },
  atrasado: { label: 'Atrasado', variant: 'destructive' },
  cancelado: { label: 'Cancelado', variant: 'secondary' },
};

interface ContratoParcelasProps {
  contratoId: string;
  valorTotal: number;
}

export function ContratoParcelas({ contratoId, valorTotal }: ContratoParcelasProps) {
  const parcelasQuery = useParcelas(contratoId);
  const { data: parcelas = [] } = parcelasQuery;
  const { mutate: gerarParcelas, isPending: isGenerating } = useGerarParcelas();
  const { mutate: updateParcela } = useUpdateParcela();

  const [gerarOpen, setGerarOpen] = useState(false);
  const [numParcelas, setNumParcelas] = useState(12);
  const [valorEntrada, setValorEntrada] = useState(0);

  const handleGerar = () => {
    gerarParcelas(
      { contratoId, valor_entrada: valorEntrada, num_parcelas: numParcelas },
      { onSuccess: () => setGerarOpen(false) }
    );
  };

  const handleMarcarPago = (parcelaId: string) => {
    updateParcela({ parcelaId, status: 'pago', data_pagamento: new Date().toISOString().split('T')[0] });
  };

  // isPending && !data — never isLoading — per
  // KB § PATTERNS/frontend/lying-loading-state.md (Shape 5).
  if (parcelasQuery.isPending && !parcelasQuery.data) {
    return (
      <Card className="p-8 text-center">
        <p className="text-muted-foreground">Carregando parcelas...</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Parcelas ({parcelas.length})
        </h3>
        {parcelas.length === 0 && (
          <Button onClick={() => setGerarOpen(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Gerar Parcelas
          </Button>
        )}
      </div>

      {parcelas.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">Nenhuma parcela gerada ainda</p>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead>Vencimento</TableHead>
                  <TableHead>Pagamento</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {parcelas.map((parcela) => {
                  const statusCfg = STATUS_PARCELA[parcela.status] || STATUS_PARCELA.pendente;
                  return (
                    <TableRow key={parcela.id}>
                      <TableCell className="font-medium">{parcela.numero}</TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatCurrency(parcela.valor)}
                      </TableCell>
                      <TableCell>{formatDate(parcela.data_vencimento)}</TableCell>
                      <TableCell>
                        {parcela.data_pagamento ? formatDate(parcela.data_pagamento) : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusCfg.variant}>{statusCfg.label}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {parcela.status === 'pendente' || parcela.status === 'atrasado' ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleMarcarPago(parcela.id)}
                          >
                            <CheckCircle className="w-4 h-4 mr-1 text-green-600" />
                            Pago
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {/* Gerar Parcelas Dialog */}
      <Dialog open={gerarOpen} onOpenChange={setGerarOpen}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Gerar Parcelas</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="text-sm text-muted-foreground">
              Valor total do contrato: <strong>{formatCurrency(valorTotal)}</strong>
            </div>
            <div className="space-y-2">
              <Label>Valor de Entrada (R$)</Label>
              <Input
                type="number"
                min={0}
                step={0.01}
                value={valorEntrada || ''}
                onChange={(e) => setValorEntrada(parseFloat(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-2">
              <Label>Número de Parcelas</Label>
              <Input
                type="number"
                min={1}
                max={360}
                value={numParcelas}
                onChange={(e) => setNumParcelas(parseInt(e.target.value) || 1)}
              />
            </div>
            {numParcelas > 0 && (
              <div className="text-sm text-muted-foreground">
                Valor por parcela: <strong>{formatCurrency((valorTotal - valorEntrada) / numParcelas)}</strong>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGerarOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleGerar} disabled={isGenerating}>
              {isGenerating ? 'Gerando...' : 'Gerar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
