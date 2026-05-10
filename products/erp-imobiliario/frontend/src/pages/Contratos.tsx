import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { Input } from '@noctusai/seed/components/ui/input';
import { Label } from '@noctusai/seed/components/ui/label';
import { Textarea } from '@noctusai/seed/components/ui/textarea';
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
  FileText,
  Plus,
  Pencil,
  Trash2,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import { CONTRATO_STATUS_CONFIG, CONTRATO_TIPO_CONFIG } from '@/lib/constants';
import {
  useContratos,
  useResumoContratos,
  useCreateContrato,
  useUpdateContrato,
  useDeleteContrato,
} from '@/hooks/useContratos';
import {
  TipoContrato,
  StatusContrato,
  ContratoCreateData,
  ContratoUpdateData,
  Contrato,
} from '@/types/contratos';
import { MetricsTableSkeleton } from '@/components/ui/page-skeleton';

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  rascunho: 'outline',
  ativo: 'default',
  concluido: 'secondary',
  cancelado: 'destructive',
  distratado: 'destructive',
};

const TIPO_CLASS: Record<string, string> = {
  venda: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  locacao: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
};

const emptyForm: ContratoCreateData = {
  tipo: 'venda',
  cliente_id: '',
  imovel_id: '',
  proposta_id: undefined,
  valor_total: 0,
  valor_entrada: undefined,
  num_parcelas: undefined,
  data_inicio: '',
  data_fim: undefined,
  data_assinatura: undefined,
  observacoes: undefined,
};

export default function Contratos() {
  const navigate = useNavigate();
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [filtroTipo, setFiltroTipo] = useState<string>('todos');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingContrato, setEditingContrato] = useState<Contrato | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [formData, setFormData] = useState<ContratoCreateData>(emptyForm);

  const { data: contratosData, isLoading } = useContratos({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
    tipo: filtroTipo !== 'todos' ? filtroTipo : undefined,
  });
  const contratos = contratosData?.data || [];

  const { data: resumo } = useResumoContratos();

  const { mutate: createContrato, isPending: isCreating } = useCreateContrato();
  const { mutate: updateContrato, isPending: isUpdating } = useUpdateContrato();
  const { mutate: deleteContrato } = useDeleteContrato();

  const handleOpenCreate = () => {
    setEditingContrato(null);
    setFormData(emptyForm);
    setModalOpen(true);
  };

  const handleOpenEdit = (contrato: Contrato) => {
    setEditingContrato(contrato);
    setFormData({
      tipo: contrato.tipo,
      cliente_id: contrato.cliente_id,
      imovel_id: contrato.imovel_id,
      proposta_id: contrato.proposta_id || undefined,
      valor_total: contrato.valor_total,
      valor_entrada: contrato.valor_entrada || undefined,
      num_parcelas: contrato.num_parcelas || undefined,
      data_inicio: contrato.data_inicio,
      data_fim: contrato.data_fim || undefined,
      data_assinatura: contrato.data_assinatura || undefined,
      observacoes: contrato.observacoes || undefined,
    });
    setModalOpen(true);
  };

  const handleSubmit = () => {
    if (!formData.cliente_id || !formData.imovel_id || !formData.valor_total || !formData.data_inicio) {
      return;
    }

    if (editingContrato) {
      const updateData: ContratoUpdateData = {
        id: editingContrato.id,
        ...formData,
      };
      updateContrato(updateData, {
        onSuccess: () => setModalOpen(false),
      });
    } else {
      createContrato(formData, {
        onSuccess: () => setModalOpen(false),
      });
    }
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteContrato(deleteId);
      setDeleteId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Contratos</h1>
          <p className="text-muted-foreground">Gerenciamento de contratos de venda e locacao</p>
        </div>
        <Button onClick={handleOpenCreate}>
          <Plus className="w-4 h-4 mr-2" />
          Novo Contrato
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Contratos</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {resumo ? Object.values(resumo.por_status).reduce((a, b) => a + b, 0) : 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Total</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(resumo?.valor_total || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {resumo?.por_status?.ativo || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Inadimplencia</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {resumo?.inadimplencia?.parcelas_atrasadas || 0}
            </div>
            {resumo?.inadimplencia?.taxa_inadimplencia != null && (
              <p className="text-xs text-muted-foreground">
                {resumo.inadimplencia.taxa_inadimplencia.toFixed(1)}% de inadimplencia
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap gap-4">
            <Select value={filtroStatus} onValueChange={setFiltroStatus}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Status</SelectItem>
                <SelectItem value="rascunho">Rascunho</SelectItem>
                <SelectItem value="ativo">Ativo</SelectItem>
                <SelectItem value="concluido">Concluido</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
                <SelectItem value="distratado">Distratado</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Tipos</SelectItem>
                <SelectItem value="venda">Venda</SelectItem>
                <SelectItem value="locacao">Locacao</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Contracts Table */}
      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <MetricsTableSkeleton cards={0} />
          ) : contratos.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              Nenhum contrato encontrado
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Cliente ID</TableHead>
                    <TableHead>Imovel ID</TableHead>
                    <TableHead className="text-right">Valor Total</TableHead>
                    <TableHead>Data Inicio</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {contratos.map((contrato) => (
                    <TableRow key={contrato.id} className="cursor-pointer hover:bg-muted/50" onClick={() => navigate(`/contratos/${contrato.id}`)}>
                      <TableCell>
                        <Badge className={TIPO_CLASS[contrato.tipo]}>
                          {CONTRATO_TIPO_CONFIG[contrato.tipo]?.label || contrato.tipo}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[150px] truncate">
                        {contrato.cliente_id}
                      </TableCell>
                      <TableCell className="max-w-[150px] truncate">
                        {contrato.imovel_id}
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatCurrency(contrato.valor_total)}
                      </TableCell>
                      <TableCell>{formatDate(contrato.data_inicio)}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_VARIANT[contrato.status]}>
                          {CONTRATO_STATUS_CONFIG[contrato.status]?.label || contrato.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenEdit(contrato)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteId(contrato.id)}
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
              {editingContrato ? 'Editar Contrato' : 'Novo Contrato'}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select
                  value={formData.tipo}
                  onValueChange={(v) => setFormData({ ...formData, tipo: v as TipoContrato })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="venda">Venda</SelectItem>
                    <SelectItem value="locacao">Locacao</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Valor Total (R$)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.valor_total || ''}
                  onChange={(e) => setFormData({ ...formData, valor_total: parseFloat(e.target.value) || 0 })}
                  placeholder="0,00"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Cliente ID</Label>
                <Input
                  value={formData.cliente_id}
                  onChange={(e) => setFormData({ ...formData, cliente_id: e.target.value })}
                  placeholder="ID do cliente"
                />
              </div>

              <div className="space-y-2">
                <Label>Imovel ID</Label>
                <Input
                  value={formData.imovel_id}
                  onChange={(e) => setFormData({ ...formData, imovel_id: e.target.value })}
                  placeholder="ID do imovel"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Valor Entrada (R$)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.valor_entrada || ''}
                  onChange={(e) => setFormData({ ...formData, valor_entrada: parseFloat(e.target.value) || undefined })}
                  placeholder="0,00"
                />
              </div>

              <div className="space-y-2">
                <Label>Numero de Parcelas</Label>
                <Input
                  type="number"
                  min="1"
                  step="1"
                  value={formData.num_parcelas || ''}
                  onChange={(e) => setFormData({ ...formData, num_parcelas: parseInt(e.target.value) || undefined })}
                  placeholder="Ex: 12"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Data de Inicio</Label>
                <Input
                  type="date"
                  value={formData.data_inicio}
                  onChange={(e) => setFormData({ ...formData, data_inicio: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label>Data de Fim</Label>
                <Input
                  type="date"
                  value={formData.data_fim || ''}
                  onChange={(e) => setFormData({ ...formData, data_fim: e.target.value || undefined })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Data de Assinatura</Label>
              <Input
                type="date"
                value={formData.data_assinatura || ''}
                onChange={(e) => setFormData({ ...formData, data_assinatura: e.target.value || undefined })}
              />
            </div>

            <div className="space-y-2">
              <Label>Observacoes</Label>
              <Textarea
                value={formData.observacoes || ''}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value || undefined })}
                placeholder="Observacoes adicionais..."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={isCreating || isUpdating || !formData.cliente_id || !formData.imovel_id || !formData.valor_total || !formData.data_inicio}
            >
              {editingContrato ? 'Salvar' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Contrato</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este contrato? Esta acao e irreversivel.
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
