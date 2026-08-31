import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@noctusai/seed/components/ui/card';
import { TableSkeleton } from '@/components/ui/page-skeleton';
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
  Shield,
  DollarSign,
  FileText,
  AlertTriangle,
  Plus,
  Pencil,
  Trash2,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  useSeguros,
  useVencimentosSeguros,
  useCreateSeguro,
  useUpdateSeguro,
  useDeleteSeguro,
} from '@/hooks/useSeguros';
import {
  TipoCobertura,
  StatusSeguro,
  SeguroCreateData,
  SeguroUpdateData,
  Seguro,
} from '@/types/seguros';

const STATUS_CONFIG: Record<StatusSeguro, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  ativo: { label: 'Ativo', variant: 'default' },
  vencido: { label: 'Vencido', variant: 'destructive' },
  cancelado: { label: 'Cancelado', variant: 'secondary' },
  renovado: { label: 'Renovado', variant: 'outline' },
};

const COBERTURA_LABELS: Record<TipoCobertura, string> = {
  incendio: 'Incendio',
  completo: 'Completo',
  responsabilidade_civil: 'Resp. Civil',
  vida: 'Vida',
  fianca_locaticia: 'Fianca Locaticia',
  outro: 'Outro',
};

const emptyForm: SeguroCreateData = {
  imovel_id: '',
  cliente_id: undefined,
  seguradora: '',
  numero_apolice: undefined,
  tipo_cobertura: 'completo',
  valor_cobertura: 0,
  valor_premio: 0,
  data_inicio: '',
  data_vencimento: '',
  auto_renovar: false,
  observacoes: undefined,
};

export default function Seguros() {
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [filtroCobertura, setFiltroCobertura] = useState<string>('todos');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSeguro, setEditingSeguro] = useState<Seguro | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [formData, setFormData] = useState<SeguroCreateData>(emptyForm);

  const segurosQuery = useSeguros({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
    tipo_cobertura: filtroCobertura !== 'todos' ? filtroCobertura : undefined,
  });
  const segurosData = segurosQuery.data;
  const showSegurosSkeleton = segurosQuery.isPending && !segurosQuery.data;
  const seguros = segurosData?.data || [];

  const { data: vencimentos } = useVencimentosSeguros(30);

  const { mutate: createSeguro, isPending: isCreating } = useCreateSeguro();
  const { mutate: updateSeguro, isPending: isUpdating } = useUpdateSeguro();
  const { mutate: deleteSeguro } = useDeleteSeguro();

  // Compute summary from local data
  const resumo = {
    ativos: seguros.filter((s) => s.status === 'ativo').length,
    total_cobertura: seguros
      .filter((s) => s.status === 'ativo')
      .reduce((sum, s) => sum + s.valor_cobertura, 0),
    total_premio_anual: seguros
      .filter((s) => s.status === 'ativo')
      .reduce((sum, s) => sum + s.valor_premio, 0),
    vencendo_30d: vencimentos?.length || 0,
  };

  const handleOpenCreate = () => {
    setEditingSeguro(null);
    setFormData(emptyForm);
    setModalOpen(true);
  };

  const handleOpenEdit = (seguro: Seguro) => {
    setEditingSeguro(seguro);
    setFormData({
      imovel_id: seguro.imovel_id,
      cliente_id: seguro.cliente_id || undefined,
      seguradora: seguro.seguradora,
      numero_apolice: seguro.numero_apolice || undefined,
      tipo_cobertura: seguro.tipo_cobertura,
      valor_cobertura: seguro.valor_cobertura,
      valor_premio: seguro.valor_premio,
      data_inicio: seguro.data_inicio,
      data_vencimento: seguro.data_vencimento,
      auto_renovar: seguro.auto_renovar,
      observacoes: seguro.observacoes || undefined,
    });
    setModalOpen(true);
  };

  const handleSubmit = () => {
    if (!formData.seguradora || !formData.imovel_id || !formData.valor_cobertura || !formData.valor_premio || !formData.data_inicio || !formData.data_vencimento) {
      return;
    }

    if (editingSeguro) {
      const updateData: SeguroUpdateData = {
        id: editingSeguro.id,
        seguradora: formData.seguradora,
        numero_apolice: formData.numero_apolice,
        tipo_cobertura: formData.tipo_cobertura,
        valor_cobertura: formData.valor_cobertura,
        valor_premio: formData.valor_premio,
        data_inicio: formData.data_inicio,
        data_vencimento: formData.data_vencimento,
        auto_renovar: formData.auto_renovar,
        observacoes: formData.observacoes,
      };
      updateSeguro(updateData, {
        onSuccess: () => setModalOpen(false),
      });
    } else {
      createSeguro(formData, {
        onSuccess: () => setModalOpen(false),
      });
    }
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteSeguro(deleteId);
      setDeleteId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Seguros</h1>
          <p className="text-muted-foreground">Gerenciamento de apolices e coberturas</p>
        </div>
        <Button onClick={handleOpenCreate}>
          <Plus className="w-4 h-4 mr-2" />
          Novo Seguro
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Apolices Ativas</CardTitle>
            <FileText className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {resumo.ativos}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Cobertura Total</CardTitle>
            <Shield className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {formatCurrency(resumo.total_cobertura)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Premio Anual</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(resumo.total_premio_anual)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencendo em 30d</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {resumo.vencendo_30d}
            </div>
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
                <SelectItem value="ativo">Ativo</SelectItem>
                <SelectItem value="vencido">Vencido</SelectItem>
                <SelectItem value="cancelado">Cancelado</SelectItem>
                <SelectItem value="renovado">Renovado</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroCobertura} onValueChange={setFiltroCobertura}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Tipo de Cobertura" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todas as Coberturas</SelectItem>
                <SelectItem value="incendio">Incendio</SelectItem>
                <SelectItem value="completo">Completo</SelectItem>
                <SelectItem value="responsabilidade_civil">Resp. Civil</SelectItem>
                <SelectItem value="vida">Vida</SelectItem>
                <SelectItem value="fianca_locaticia">Fianca Locaticia</SelectItem>
                <SelectItem value="outro">Outro</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Seguros Table */}
      <Card>
        <CardContent className="pt-6">
          {showSegurosSkeleton ? (
            <TableSkeleton rows={4} />
          ) : seguros.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              Nenhum seguro encontrado
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Seguradora</TableHead>
                    <TableHead>Apolice</TableHead>
                    <TableHead>Cobertura</TableHead>
                    <TableHead>Imovel ID</TableHead>
                    <TableHead className="text-right">Premio</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {seguros.map((seguro) => (
                    <TableRow key={seguro.id}>
                      <TableCell className="font-medium">
                        {seguro.seguradora}
                      </TableCell>
                      <TableCell>
                        {seguro.numero_apolice || '-'}
                      </TableCell>
                      <TableCell>
                        {COBERTURA_LABELS[seguro.tipo_cobertura]}
                      </TableCell>
                      <TableCell className="max-w-[120px] truncate">
                        {seguro.imovel_id}
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatCurrency(seguro.valor_premio)}
                      </TableCell>
                      <TableCell>{formatDate(seguro.data_vencimento)}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_CONFIG[seguro.status].variant}>
                          {STATUS_CONFIG[seguro.status].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenEdit(seguro)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteId(seguro.id)}
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
              {editingSeguro ? 'Editar Seguro' : 'Novo Seguro'}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Seguradora</Label>
                <Input
                  value={formData.seguradora}
                  onChange={(e) => setFormData({ ...formData, seguradora: e.target.value })}
                  placeholder="Nome da seguradora"
                />
              </div>

              <div className="space-y-2">
                <Label>Numero da Apolice</Label>
                <Input
                  value={formData.numero_apolice || ''}
                  onChange={(e) => setFormData({ ...formData, numero_apolice: e.target.value || undefined })}
                  placeholder="Ex: APL-123456"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo de Cobertura</Label>
                <Select
                  value={formData.tipo_cobertura}
                  onValueChange={(v) => setFormData({ ...formData, tipo_cobertura: v as TipoCobertura })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="incendio">Incendio</SelectItem>
                    <SelectItem value="completo">Completo</SelectItem>
                    <SelectItem value="responsabilidade_civil">Resp. Civil</SelectItem>
                    <SelectItem value="vida">Vida</SelectItem>
                    <SelectItem value="fianca_locaticia">Fianca Locaticia</SelectItem>
                    <SelectItem value="outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
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

            <div className="space-y-2">
              <Label>Cliente ID</Label>
              <Input
                value={formData.cliente_id || ''}
                onChange={(e) => setFormData({ ...formData, cliente_id: e.target.value || undefined })}
                placeholder="ID do cliente (opcional)"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Valor da Cobertura (R$)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.valor_cobertura || ''}
                  onChange={(e) => setFormData({ ...formData, valor_cobertura: parseFloat(e.target.value) || 0 })}
                  placeholder="0,00"
                />
              </div>

              <div className="space-y-2">
                <Label>Valor do Premio (R$)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.valor_premio || ''}
                  onChange={(e) => setFormData({ ...formData, valor_premio: parseFloat(e.target.value) || 0 })}
                  placeholder="0,00"
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
                <Label>Data de Vencimento</Label>
                <Input
                  type="date"
                  value={formData.data_vencimento}
                  onChange={(e) => setFormData({ ...formData, data_vencimento: e.target.value })}
                />
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="auto_renovar"
                checked={formData.auto_renovar || false}
                onChange={(e) => setFormData({ ...formData, auto_renovar: e.target.checked })}
                className="h-4 w-4"
              />
              <Label htmlFor="auto_renovar">Auto Renovar</Label>
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
              disabled={isCreating || isUpdating || !formData.seguradora || !formData.imovel_id || !formData.valor_cobertura || !formData.valor_premio || !formData.data_inicio || !formData.data_vencimento}
            >
              {editingSeguro ? 'Salvar' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Seguro</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este seguro? Esta acao e irreversivel.
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
