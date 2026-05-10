import { useState } from 'react';
import {
  useComissoes,
  useComissaoResumo,
  useCreateComissao,
  useUpdateComissao,
  useDeleteComissao,
} from '@/hooks/useComissoes';
import type {
  ComissaoStatus,
  ComissaoCreateData,
  SplitInput,
} from '@/types/comissoes';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
import { Badge } from '@noctusai/seed/components/ui/badge';
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
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import {
  DollarSign,
  Clock,
  CheckCircle2,
  XCircle,
  Plus,
  Trash2,
  Users,
} from 'lucide-react';
import { MetricsTableSkeleton } from '@/components/ui/page-skeleton';
import { formatCurrency, formatDate } from '@/lib/utils';

const statusConfig: Record<ComissaoStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pendente: { label: 'Pendente', variant: 'secondary' },
  aprovada: { label: 'Aprovada', variant: 'outline' },
  paga: { label: 'Paga', variant: 'default' },
  cancelada: { label: 'Cancelada', variant: 'destructive' },
};

export default function Comissoes() {
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [dialogAberto, setDialogAberto] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const statusParam = filtroStatus === 'todos' ? undefined : filtroStatus as ComissaoStatus;
  const { data: comissoesResult, isLoading } = useComissoes({ status: statusParam });
  const { data: resumo } = useComissaoResumo();
  const createMutation = useCreateComissao();
  const updateMutation = useUpdateComissao();
  const deleteMutation = useDeleteComissao();

  const comissoes = comissoesResult?.data || [];
  const totais = resumo?.totais;

  // Form state
  const [formData, setFormData] = useState<{
    valor_venda: string;
    percentual_comissao: string;
    data_venda: string;
    observacoes: string;
    splits: SplitInput[];
  }>({
    valor_venda: '',
    percentual_comissao: '6',
    data_venda: '',
    observacoes: '',
    splits: [{ corretor_id: '', corretor_nome: '', percentual: 100 }],
  });

  const resetForm = () => {
    setFormData({
      valor_venda: '',
      percentual_comissao: '6',
      data_venda: '',
      observacoes: '',
      splits: [{ corretor_id: '', corretor_nome: '', percentual: 100 }],
    });
  };

  const handleAddSplit = () => {
    const currentTotal = formData.splits.reduce((sum, s) => sum + s.percentual, 0);
    const remaining = Math.max(0, 100 - currentTotal);
    setFormData({
      ...formData,
      splits: [...formData.splits, { corretor_id: '', corretor_nome: '', percentual: remaining }],
    });
  };

  const handleRemoveSplit = (index: number) => {
    if (formData.splits.length <= 1) return;
    const newSplits = formData.splits.filter((_, i) => i !== index);
    setFormData({ ...formData, splits: newSplits });
  };

  const handleSplitChange = (index: number, field: keyof SplitInput, value: string | number) => {
    const newSplits = [...formData.splits];
    newSplits[index] = { ...newSplits[index], [field]: value };
    setFormData({ ...formData, splits: newSplits });
  };

  const handleAutoDistribute = () => {
    const count = formData.splits.length;
    if (count === 0) return;
    const each = parseFloat((100 / count).toFixed(2));
    const newSplits = formData.splits.map((s, i) => ({
      ...s,
      percentual: i === count - 1 ? parseFloat((100 - each * (count - 1)).toFixed(2)) : each,
    }));
    setFormData({ ...formData, splits: newSplits });
  };

  const handleSubmit = () => {
    const valorVenda = parseFloat(formData.valor_venda);
    const percentual = parseFloat(formData.percentual_comissao);

    if (!valorVenda || valorVenda <= 0) return;
    if (!percentual || percentual <= 0 || percentual > 100) return;

    const validSplits = formData.splits.filter(s => s.corretor_id && s.corretor_nome);

    const data: ComissaoCreateData = {
      valor_venda: valorVenda,
      percentual_comissao: percentual,
      splits: validSplits.length > 0 ? validSplits : undefined,
    };

    if (formData.data_venda) data.data_venda = formData.data_venda;
    if (formData.observacoes) data.observacoes = formData.observacoes;

    createMutation.mutate(data, {
      onSuccess: () => {
        setDialogAberto(false);
        resetForm();
      },
    });
  };

  const handleStatusChange = (comissaoId: string, newStatus: ComissaoStatus) => {
    updateMutation.mutate({
      id: comissaoId,
      status: newStatus,
      data_pagamento: newStatus === 'paga' ? new Date().toISOString().split('T')[0] : undefined,
    });
  };

  const handleDelete = (id: string) => {
    deleteMutation.mutate(id, {
      onSuccess: () => setConfirmDelete(null),
    });
  };

  const splitsTotal = formData.splits.reduce((sum, s) => sum + (s.percentual || 0), 0);
  const valorVendaNum = parseFloat(formData.valor_venda) || 0;
  const percentualNum = parseFloat(formData.percentual_comissao) || 0;
  const valorComissaoPreview = valorVendaNum * (percentualNum / 100);

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Comissoes</h1>
          <p className="text-muted-foreground">Gerencie comissoes de vendas e splits entre corretores</p>
        </div>
        <Button onClick={() => setDialogAberto(true)}>
          <Plus className="h-4 w-4 mr-2" />Nova Comissao
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Pendente</CardTitle>
            <Clock className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totais?.total_pendente || 0)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Aprovada</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totais?.total_aprovada || 0)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Paga</CardTitle>
            <DollarSign className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totais?.total_paga || 0)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Geral</CardTitle>
            <DollarSign className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totais?.total_geral || 0)}</div>
            <p className="text-xs text-muted-foreground">{totais?.quantidade || 0} comissoes</p>
          </CardContent>
        </Card>
      </div>

      {/* Agent Summary */}
      {resumo?.por_corretor && resumo.por_corretor.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Resumo por Corretor
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Corretor</TableHead>
                  <TableHead className="text-right">Pendente</TableHead>
                  <TableHead className="text-right">Paga</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-right">Qtd</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resumo.por_corretor.map((c) => (
                  <TableRow key={c.corretor_id}>
                    <TableCell className="font-medium">{c.corretor_nome}</TableCell>
                    <TableCell className="text-right">{formatCurrency(c.total_pendente)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(c.total_paga)}</TableCell>
                    <TableCell className="text-right font-semibold">{formatCurrency(c.total_geral)}</TableCell>
                    <TableCell className="text-right">{c.quantidade}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Filter and Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Comissoes</CardTitle>
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os status</SelectItem>
                <SelectItem value="pendente">Pendente</SelectItem>
                <SelectItem value="aprovada">Aprovada</SelectItem>
                <SelectItem value="paga">Paga</SelectItem>
                <SelectItem value="cancelada">Cancelada</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <MetricsTableSkeleton cards={0} />
          ) : comissoes.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <DollarSign className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg">Nenhuma comissao encontrada</p>
              <p className="text-sm">Crie uma nova comissao para comecar</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Valor Venda</TableHead>
                  <TableHead>%</TableHead>
                  <TableHead>Comissao</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data Venda</TableHead>
                  <TableHead>Data Pgto</TableHead>
                  <TableHead>Splits</TableHead>
                  <TableHead className="text-right">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {comissoes.map((comissao) => {
                  const cfg = statusConfig[comissao.status];
                  return (
                    <TableRow key={comissao.id}>
                      <TableCell className="font-medium">{formatCurrency(comissao.valor_venda)}</TableCell>
                      <TableCell>{comissao.percentual_comissao}%</TableCell>
                      <TableCell className="font-semibold">{formatCurrency(comissao.valor_comissao)}</TableCell>
                      <TableCell>
                        <Badge variant={cfg.variant}>{cfg.label}</Badge>
                      </TableCell>
                      <TableCell>{formatDate(comissao.data_venda)}</TableCell>
                      <TableCell>{formatDate(comissao.data_pagamento)}</TableCell>
                      <TableCell>
                        {comissao.splits && comissao.splits.length > 0 ? (
                          <div className="space-y-1">
                            {comissao.splits.map((s) => (
                              <div key={s.id} className="text-xs">
                                {s.corretor_nome}: {s.percentual}% ({formatCurrency(s.valor)})
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-xs">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Select
                            value={comissao.status}
                            onValueChange={(v) => handleStatusChange(comissao.id, v as ComissaoStatus)}
                          >
                            <SelectTrigger className="h-8 w-[120px] text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="pendente">Pendente</SelectItem>
                              <SelectItem value="aprovada">Aprovada</SelectItem>
                              <SelectItem value="paga">Paga</SelectItem>
                              <SelectItem value="cancelada">Cancelada</SelectItem>
                            </SelectContent>
                          </Select>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive"
                            onClick={() => setConfirmDelete(comissao.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create Commission Dialog */}
      <Dialog open={dialogAberto} onOpenChange={(open) => { setDialogAberto(open); if (!open) resetForm(); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Nova Comissao</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="valor_venda">Valor da Venda (R$)</Label>
                <Input
                  id="valor_venda"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="500000.00"
                  value={formData.valor_venda}
                  onChange={(e) => setFormData({ ...formData, valor_venda: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="percentual">Percentual (%)</Label>
                <Input
                  id="percentual"
                  type="number"
                  min="0.01"
                  max="100"
                  step="0.01"
                  value={formData.percentual_comissao}
                  onChange={(e) => setFormData({ ...formData, percentual_comissao: e.target.value })}
                />
              </div>
            </div>

            {valorVendaNum > 0 && percentualNum > 0 && (
              <div className="bg-muted p-3 rounded-lg">
                <p className="text-sm text-muted-foreground">Valor da comissao:</p>
                <p className="text-xl font-bold text-primary">{formatCurrency(valorComissaoPreview)}</p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="data_venda">Data da Venda</Label>
              <Input
                id="data_venda"
                type="date"
                value={formData.data_venda}
                onChange={(e) => setFormData({ ...formData, data_venda: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="observacoes">Observacoes</Label>
              <Textarea
                id="observacoes"
                placeholder="Detalhes adicionais..."
                value={formData.observacoes}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value })}
              />
            </div>

            {/* Splits */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base font-semibold">Divisao entre Corretores</Label>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={handleAutoDistribute}>
                    Distribuir igualmente
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={handleAddSplit}>
                    <Plus className="h-3 w-3 mr-1" />Adicionar
                  </Button>
                </div>
              </div>

              {formData.splits.map((split, index) => (
                <div key={index} className="flex items-end gap-2 p-3 border rounded-lg">
                  <div className="flex-1 space-y-1">
                    <Label className="text-xs">ID do Corretor</Label>
                    <Input
                      placeholder="UUID do corretor"
                      value={split.corretor_id}
                      onChange={(e) => handleSplitChange(index, 'corretor_id', e.target.value)}
                    />
                  </div>
                  <div className="flex-1 space-y-1">
                    <Label className="text-xs">Nome</Label>
                    <Input
                      placeholder="Nome do corretor"
                      value={split.corretor_nome}
                      onChange={(e) => handleSplitChange(index, 'corretor_nome', e.target.value)}
                    />
                  </div>
                  <div className="w-24 space-y-1">
                    <Label className="text-xs">%</Label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={split.percentual}
                      onChange={(e) => handleSplitChange(index, 'percentual', parseFloat(e.target.value) || 0)}
                    />
                  </div>
                  <div className="w-28 text-right">
                    <p className="text-sm font-medium">
                      {formatCurrency(valorComissaoPreview * (split.percentual / 100))}
                    </p>
                  </div>
                  {formData.splits.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9 text-destructive"
                      onClick={() => handleRemoveSplit(index)}
                    >
                      <XCircle className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}

              <div className={`text-sm font-medium ${Math.abs(splitsTotal - 100) > 0.01 ? 'text-destructive' : 'text-green-600'}`}>
                Total: {splitsTotal.toFixed(2)}%
                {Math.abs(splitsTotal - 100) > 0.01 && ' (deve ser 100%)'}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setDialogAberto(false); resetForm(); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={
                createMutation.isPending ||
                !valorVendaNum ||
                !percentualNum
              }
            >
              {createMutation.isPending ? 'Criando...' : 'Criar Comissao'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!confirmDelete} onOpenChange={(open) => !open && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir comissao?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acao nao pode ser desfeita. A comissao e todos os splits serao removidos permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => confirmDelete && handleDelete(confirmDelete)}
            >
              {deleteMutation.isPending ? 'Excluindo...' : 'Excluir'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
