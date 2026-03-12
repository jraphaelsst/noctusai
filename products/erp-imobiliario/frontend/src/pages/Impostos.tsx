import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TableSkeleton } from '@/components/ui/page-skeleton';
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
  AlertTriangle,
  Plus,
  Pencil,
  Trash2,
  Receipt,
  CheckCircle,
} from 'lucide-react';
import { formatCurrency, formatDate } from '@/lib/utils';
import {
  useImpostos,
  useResumoImpostos,
  useCreateImposto,
  useUpdateImposto,
  useDeleteImposto,
} from '@/hooks/useImpostos';
import {
  TipoImposto,
  StatusImposto,
  ImpostoCreateData,
  ImpostoUpdateData,
  Imposto,
} from '@/types/impostos';

const STATUS_CONFIG: Record<StatusImposto, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  pendente: { label: 'Pendente', variant: 'outline' },
  parcial: { label: 'Parcial', variant: 'secondary' },
  pago: { label: 'Pago', variant: 'default' },
  atrasado: { label: 'Atrasado', variant: 'destructive' },
  isento: { label: 'Isento', variant: 'secondary' },
};

const TIPO_LABELS: Record<TipoImposto, string> = {
  iptu: 'IPTU',
  itbi: 'ITBI',
  txa_lixo: 'Taxa de Lixo',
  contribuicao_melhoria: 'Contrib. Melhoria',
  outro: 'Outro',
};

const emptyForm: ImpostoCreateData = {
  imovel_id: '',
  tipo: 'iptu',
  ano: new Date().getFullYear(),
  valor_total: 0,
  valor_pago: 0,
  num_parcelas: 1,
  parcela_atual: 1,
  desconto_cota_unica: 0,
  data_vencimento: '',
  status: 'pendente',
  numero_guia: undefined,
  comprovante_url: undefined,
  observacoes: undefined,
};

export default function Impostos() {
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [filtroTipo, setFiltroTipo] = useState<string>('todos');
  const [filtroAno, setFiltroAno] = useState<number | undefined>(undefined);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingImposto, setEditingImposto] = useState<Imposto | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [formData, setFormData] = useState<ImpostoCreateData>(emptyForm);

  const { data: impostosData, isLoading } = useImpostos({
    status: filtroStatus !== 'todos' ? filtroStatus : undefined,
    tipo: filtroTipo !== 'todos' ? filtroTipo : undefined,
    ano: filtroAno,
  });
  const impostos = impostosData?.data || [];

  const { data: resumo } = useResumoImpostos({
    ano: filtroAno,
  });

  const { mutate: createImposto, isPending: isCreating } = useCreateImposto();
  const { mutate: updateImposto, isPending: isUpdating } = useUpdateImposto();
  const { mutate: deleteImposto } = useDeleteImposto();

  const handleOpenCreate = () => {
    setEditingImposto(null);
    setFormData(emptyForm);
    setModalOpen(true);
  };

  const handleOpenEdit = (imposto: Imposto) => {
    setEditingImposto(imposto);
    setFormData({
      imovel_id: imposto.imovel_id,
      tipo: imposto.tipo,
      ano: imposto.ano,
      valor_total: imposto.valor_total,
      valor_pago: imposto.valor_pago,
      num_parcelas: imposto.num_parcelas,
      parcela_atual: imposto.parcela_atual,
      desconto_cota_unica: imposto.desconto_cota_unica,
      data_vencimento: imposto.data_vencimento,
      status: imposto.status,
      numero_guia: imposto.numero_guia || undefined,
      comprovante_url: imposto.comprovante_url || undefined,
      observacoes: imposto.observacoes || undefined,
    });
    setModalOpen(true);
  };

  const handleSubmit = () => {
    if (!formData.imovel_id || !formData.valor_total || !formData.data_vencimento) {
      return;
    }

    if (editingImposto) {
      const updateData: ImpostoUpdateData = {
        id: editingImposto.id,
        valor_pago: formData.valor_pago,
        parcela_atual: formData.parcela_atual,
        status: formData.status,
        numero_guia: formData.numero_guia,
        comprovante_url: formData.comprovante_url,
        observacoes: formData.observacoes,
      };
      updateImposto(updateData, {
        onSuccess: () => setModalOpen(false),
      });
    } else {
      createImposto(formData, {
        onSuccess: () => setModalOpen(false),
      });
    }
  };

  const handleDelete = () => {
    if (deleteId) {
      deleteImposto(deleteId);
      setDeleteId(null);
    }
  };

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold">Impostos</h1>
          <p className="text-muted-foreground">IPTU e tributos imobiliarios</p>
        </div>
        <Button onClick={handleOpenCreate}>
          <Plus className="w-4 h-4 mr-2" />
          Novo Imposto
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Devido</CardTitle>
            <Receipt className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(resumo?.total_devido || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Pago</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {formatCurrency(resumo?.total_pago || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendente</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {formatCurrency(resumo?.total_pendente || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Atrasado</CardTitle>
            <AlertTriangle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">
              {formatCurrency(resumo?.total_atrasado || 0)}
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
                <SelectItem value="pendente">Pendente</SelectItem>
                <SelectItem value="parcial">Parcial</SelectItem>
                <SelectItem value="pago">Pago</SelectItem>
                <SelectItem value="atrasado">Atrasado</SelectItem>
                <SelectItem value="isento">Isento</SelectItem>
              </SelectContent>
            </Select>

            <Select value={filtroTipo} onValueChange={setFiltroTipo}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos os Tipos</SelectItem>
                <SelectItem value="iptu">IPTU</SelectItem>
                <SelectItem value="itbi">ITBI</SelectItem>
                <SelectItem value="txa_lixo">Taxa de Lixo</SelectItem>
                <SelectItem value="contribuicao_melhoria">Contrib. Melhoria</SelectItem>
                <SelectItem value="outro">Outro</SelectItem>
              </SelectContent>
            </Select>

            <Input
              type="number"
              placeholder="Ano"
              className="w-[120px]"
              value={filtroAno || ''}
              onChange={(e) => setFiltroAno(e.target.value ? parseInt(e.target.value) : undefined)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Impostos Table */}
      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <TableSkeleton rows={4} />
          ) : impostos.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              Nenhum imposto encontrado
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Imovel ID</TableHead>
                    <TableHead>Ano</TableHead>
                    <TableHead className="text-right">Valor Total</TableHead>
                    <TableHead className="text-right">Valor Pago</TableHead>
                    <TableHead>Parcela</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Acoes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {impostos.map((imposto) => (
                    <TableRow key={imposto.id}>
                      <TableCell className="font-medium">
                        {TIPO_LABELS[imposto.tipo]}
                      </TableCell>
                      <TableCell className="max-w-[150px] truncate">
                        {imposto.imovel_id}
                      </TableCell>
                      <TableCell>{imposto.ano}</TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatCurrency(imposto.valor_total)}
                      </TableCell>
                      <TableCell className="text-right text-green-600">
                        {formatCurrency(imposto.valor_pago)}
                      </TableCell>
                      <TableCell>
                        {imposto.parcela_atual}/{imposto.num_parcelas}
                      </TableCell>
                      <TableCell>{formatDate(imposto.data_vencimento)}</TableCell>
                      <TableCell>
                        <Badge variant={STATUS_CONFIG[imposto.status].variant}>
                          {STATUS_CONFIG[imposto.status].label}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenEdit(imposto)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteId(imposto.id)}
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
              {editingImposto ? 'Editar Imposto' : 'Novo Imposto'}
            </DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Imovel ID</Label>
                <Input
                  value={formData.imovel_id}
                  onChange={(e) => setFormData({ ...formData, imovel_id: e.target.value })}
                  placeholder="ID do imovel"
                />
              </div>

              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select
                  value={formData.tipo}
                  onValueChange={(v) => setFormData({ ...formData, tipo: v as TipoImposto })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="iptu">IPTU</SelectItem>
                    <SelectItem value="itbi">ITBI</SelectItem>
                    <SelectItem value="txa_lixo">Taxa de Lixo</SelectItem>
                    <SelectItem value="contribuicao_melhoria">Contrib. Melhoria</SelectItem>
                    <SelectItem value="outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Ano</Label>
                <Input
                  type="number"
                  value={formData.ano || ''}
                  onChange={(e) => setFormData({ ...formData, ano: parseInt(e.target.value) || new Date().getFullYear() })}
                  placeholder="2026"
                />
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
                <Label>Valor Pago (R$)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.valor_pago || ''}
                  onChange={(e) => setFormData({ ...formData, valor_pago: parseFloat(e.target.value) || 0 })}
                  placeholder="0,00"
                />
              </div>

              <div className="space-y-2">
                <Label>Num. Parcelas</Label>
                <Input
                  type="number"
                  min="1"
                  value={formData.num_parcelas || ''}
                  onChange={(e) => setFormData({ ...formData, num_parcelas: parseInt(e.target.value) || 1 })}
                  placeholder="1"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Data de Vencimento</Label>
                <Input
                  type="date"
                  value={formData.data_vencimento}
                  onChange={(e) => setFormData({ ...formData, data_vencimento: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label>Status</Label>
                <Select
                  value={formData.status || 'pendente'}
                  onValueChange={(v) => setFormData({ ...formData, status: v as StatusImposto })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pendente">Pendente</SelectItem>
                    <SelectItem value="parcial">Parcial</SelectItem>
                    <SelectItem value="pago">Pago</SelectItem>
                    <SelectItem value="atrasado">Atrasado</SelectItem>
                    <SelectItem value="isento">Isento</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Numero da Guia</Label>
              <Input
                value={formData.numero_guia || ''}
                onChange={(e) => setFormData({ ...formData, numero_guia: e.target.value || undefined })}
                placeholder="Numero da guia de pagamento"
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
              disabled={isCreating || isUpdating || !formData.imovel_id || !formData.valor_total || !formData.data_vencimento}
            >
              {editingImposto ? 'Salvar' : 'Criar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir Imposto</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja excluir este imposto? Esta acao e irreversivel.
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
