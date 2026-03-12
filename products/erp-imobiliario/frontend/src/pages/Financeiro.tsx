import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
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
} from '@/components/ui/alert-dialog';
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Plus,
  Pencil,
  Trash2,
  BarChart3,
  Receipt,
} from 'lucide-react';
import { EmptyState } from '@/components/ui/empty-state';
import { MetricsTableSkeleton } from '@/components/ui/page-skeleton';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  useFinanceiro,
  useResumoFinanceiro,
  useFluxoCaixa,
  useCreateLancamento,
  useUpdateLancamento,
  useDeleteLancamento,
} from '@/hooks/useFinanceiro';
import {
  TipoLancamento,
  StatusLancamento,
  LancamentoUpdateData,
  Lancamento,
} from '@/types/financeiro';

const STATUS_CONFIG: Record<StatusLancamento, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  pago: { label: 'Pago', variant: 'default' },
  atrasado: { label: 'Atrasado', variant: 'destructive' },
  cancelado: { label: 'Cancelado', variant: 'secondary' },
};

const TIPO_CONFIG: Record<TipoLancamento, { label: string; className: string }> = {
  receita: { label: 'Receita', className: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  despesa: { label: 'Despesa', className: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
};

const CATEGORIAS = [
  'Comissão',
  'Aluguel',
  'IPTU',
  'Condomínio',
  'Manutenção',
  'Marketing',
  'Documentação',
  'Outros',
];

const FORMAS_PAGAMENTO = [
  'Dinheiro',
  'PIX',
  'Cartão de Crédito',
  'Cartão de Débito',
  'Transferência',
  'Boleto',
  'Cheque',
];

const lancamentoSchema = z.object({
  tipo: z.enum(['receita', 'despesa']),
  categoria: z.string().min(1, 'Selecione uma categoria'),
  descricao: z.string().min(1, 'Descrição é obrigatória'),
  valor: z.coerce.number().positive('Valor deve ser maior que zero'),
  data_vencimento: z.string().min(1, 'Data de vencimento é obrigatória'),
  data_pagamento: z.string().optional(),
  status: z.enum(['pendente', 'pago', 'atrasado', 'cancelado']).default('pendente'),
  forma_pagamento: z.string().optional(),
  recorrente: z.boolean().default(false),
  observacoes: z.string().optional(),
});

type LancamentoFormData = z.infer<typeof lancamentoSchema>;

export default function Financeiro() {
  const [filtroTipo, setFiltroTipo] = useState<string>('todos');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLancamento, setEditingLancamento] = useState<Lancamento | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [showFluxo, setShowFluxo] = useState(false);

  const {
    register,
    handleSubmit: rhfHandleSubmit,
    formState: { errors },
    reset,
    setValue,
    watch,
  } = useForm<LancamentoFormData>({
    resolver: zodResolver(lancamentoSchema),
    defaultValues: {
      tipo: 'receita',
      categoria: '',
      descricao: '',
      valor: 0,
      data_vencimento: '',
      data_pagamento: '',
      status: 'pendente',
      forma_pagamento: '',
      recorrente: false,
      observacoes: '',
    },
  });

  const tipoValue = watch('tipo');
  const categoriaValue = watch('categoria');
  const formaPagamentoValue = watch('forma_pagamento');
  const statusValue = watch('status');

  const { data: financeiroData, isLoading } = useFinanceiro({
    tipo: filtroTipo !== 'todos' ? filtroTipo : undefined,
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
  });
  const lancamentos = financeiroData?.data || [];

  const { data: resumo } = useResumoFinanceiro();
  const { data: fluxoCaixa } = useFluxoCaixa(12);

  const { mutate: createLancamento, isPending: isCreating } = useCreateLancamento();
  const { mutate: updateLancamento, isPending: isUpdating } = useUpdateLancamento();
  const { mutate: deleteLancamento } = useDeleteLancamento();

  const handleOpenCreate = () => {
    setEditingLancamento(null);
    reset({
      tipo: 'receita',
      categoria: '',
      descricao: '',
      valor: 0,
      data_vencimento: '',
      data_pagamento: '',
      status: 'pendente',
      forma_pagamento: '',
      recorrente: false,
      observacoes: '',
    });
    setModalOpen(true);
  };

  const handleOpenEdit = (lancamento: Lancamento) => {
    setEditingLancamento(lancamento);
    reset({
      tipo: lancamento.tipo,
      categoria: lancamento.categoria,
      descricao: lancamento.descricao,
      valor: lancamento.valor,
      data_vencimento: lancamento.data_vencimento,
      data_pagamento: lancamento.data_pagamento || '',
      status: lancamento.status,
      forma_pagamento: lancamento.forma_pagamento || '',
      recorrente: lancamento.recorrente,
      observacoes: lancamento.observacoes || '',
    });
    setModalOpen(true);
  };

  const onSubmit = (data: LancamentoFormData) => {
    const payload = {
      ...data,
      data_pagamento: data.data_pagamento || undefined,
      forma_pagamento: data.forma_pagamento || undefined,
      observacoes: data.observacoes || undefined,
    };

    if (editingLancamento) {
      updateLancamento(
        { id: editingLancamento.id, ...payload },
        { onSuccess: () => setModalOpen(false) }
      );
    } else {
      createLancamento(payload, { onSuccess: () => setModalOpen(false) });
    }
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteLancamento(deleteId);
      setDeleteId(null);
    }
  };

  const formatMes = (mes: string) => {
    const [year, month] = mes.split('-');
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${meses[parseInt(month) - 1]}/${year}`;
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Financeiro</h1>
          <p className="text-muted-foreground">Controle de receitas e despesas</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowFluxo(!showFluxo)}>
            <BarChart3 className="w-4 h-4 mr-2" />
            Fluxo de Caixa
          </Button>
          <Button onClick={handleOpenCreate}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Lancamento
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Receitas</CardTitle>
            <TrendingUp className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {formatCurrency(resumo?.receitas || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Despesas</CardTitle>
            <TrendingDown className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {formatCurrency(resumo?.despesas || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Saldo</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(resumo?.saldo || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {formatCurrency(resumo?.saldo || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Atrasados</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {resumo?.atrasados || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Cash Flow Section */}
      {showFluxo && fluxoCaixa && fluxoCaixa.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Fluxo de Caixa Mensal</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Mes</TableHead>
                    <TableHead className="text-right">Receitas</TableHead>
                    <TableHead className="text-right">Despesas</TableHead>
                    <TableHead className="text-right">Saldo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fluxoCaixa.map((item) => (
                    <TableRow key={item.mes}>
                      <TableCell className="font-medium">{formatMes(item.mes)}</TableCell>
                      <TableCell className="text-right text-green-600">
                        {formatCurrency(item.receitas)}
                      </TableCell>
                      <TableCell className="text-right text-red-600">
                        {formatCurrency(item.despesas)}
                      </TableCell>
                      <TableCell className={`text-right font-semibold ${item.saldo >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {formatCurrency(item.saldo)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4">
            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Tipos</SelectItem>
                <SelectItem value="receita">Receita</SelectItem>
                <SelectItem value="despesa">Despesa</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                <SelectItem value="pendente">Pendente</SelectItem>
                <SelectItem value="pago">Pago</SelectItem>
                <SelectItem value="atrasado">Atrasado</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Transactions Table */}
      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <MetricsTableSkeleton cards={0} />
          ) : lancamentos.length === 0 ? (
            <EmptyState
              icon={Receipt}
              title="Nenhum lançamento encontrado"
              description="Crie um lançamento para começar a controlar suas finanças"
              action={{ label: 'Novo Lançamento', onClick: handleOpenCreate }}
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Descricao</TableHead>
                    <TableHead>Categoria</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Pagamento</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lancamentos.map((lancamento) => (
                    <TableRow key={lancamento.id}>
                      <TableCell>
                        <Badge className={TIPO_CONFIG[lancamento.tipo].className}>
                          {TIPO_CONFIG[lancamento.tipo].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {lancamento.descricao}
                      </TableCell>
                      <TableCell>{lancamento.categoria}</TableCell>
                      <TableCell className={`text-right font-semibold ${lancamento.tipo === 'receita' ? 'text-green-600' : 'text-red-600'}`}>
                        {formatCurrency(lancamento.valor)}
                      </TableCell>
                      <TableCell>{formatDate(lancamento.data_vencimento)}</TableCell>
                      <TableCell>
                        {lancamento.data_pagamento ? formatDate(lancamento.data_pagamento) : '-'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATUS_CONFIG[lancamento.status].variant}>
                          {STATUS_CONFIG[lancamento.status].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenEdit(lancamento)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteId(lancamento.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create/Edit Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingLancamento ? 'Editar Lancamento' : 'Novo Lancamento'}
            </DialogTitle>
          </DialogHeader>

          <form onSubmit={rhfHandleSubmit(onSubmit)}>
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Tipo</Label>
                  <Select value={tipoValue} onValueChange={(v) => setValue('tipo', v as TipoLancamento)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="receita">Receita</SelectItem>
                      <SelectItem value="despesa">Despesa</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Categoria</Label>
                  <Select value={categoriaValue} onValueChange={(v) => setValue('categoria', v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione..." />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIAS.map((cat) => (
                        <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {errors.categoria && <p className="text-sm text-destructive">{errors.categoria.message}</p>}
                </div>
              </div>

              <div className="space-y-2">
                <Label>Descrição</Label>
                <Input {...register('descricao')} placeholder="Descrição do lançamento" />
                {errors.descricao && <p className="text-sm text-destructive">{errors.descricao.message}</p>}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Valor (R$)</Label>
                  <Input type="number" min="0" step="0.01" {...register('valor')} placeholder="0,00" />
                  {errors.valor && <p className="text-sm text-destructive">{errors.valor.message}</p>}
                </div>

                <div className="space-y-2">
                  <Label>Forma de Pagamento</Label>
                  <Select value={formaPagamentoValue || ''} onValueChange={(v) => setValue('forma_pagamento', v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione..." />
                    </SelectTrigger>
                    <SelectContent>
                      {FORMAS_PAGAMENTO.map((fp) => (
                        <SelectItem key={fp} value={fp}>{fp}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Data de Vencimento</Label>
                  <Input type="date" {...register('data_vencimento')} />
                  {errors.data_vencimento && <p className="text-sm text-destructive">{errors.data_vencimento.message}</p>}
                </div>

                <div className="space-y-2">
                  <Label>Data de Pagamento</Label>
                  <Input type="date" {...register('data_pagamento')} />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Status</Label>
                  <Select value={statusValue} onValueChange={(v) => setValue('status', v as StatusLancamento)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pendente">Pendente</SelectItem>
                      <SelectItem value="pago">Pago</SelectItem>
                      <SelectItem value="atrasado">Atrasado</SelectItem>
                      <SelectItem value="cancelado">Cancelado</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-end space-x-2 pb-1">
                  <input type="checkbox" id="recorrente" {...register('recorrente')} className="h-4 w-4" />
                  <Label htmlFor="recorrente">Recorrente</Label>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Observações</Label>
                <Textarea {...register('observacoes')} placeholder="Observações adicionais..." rows={3} />
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setModalOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={isCreating || isUpdating}>
                {editingLancamento ? 'Salvar' : 'Criar'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Lancamento</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este lancamento? Esta acao e irreversivel.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
